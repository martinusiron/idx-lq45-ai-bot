from __future__ import annotations

from dataclasses import dataclass
from math import floor

import pandas as pd


@dataclass
class PositionPlan:
    qty: int
    lot_count: int
    risk_amount: float
    planned_notional: float
    effective_entry: float
    effective_stop: float
    size_mode: str
    notes: str


class RiskEngine:
    def __init__(
        self,
        account_size: float,
        risk_per_trade_pct: float,
        daily_max_loss_r: float,
        max_open_positions: int,
        lot_size: int,
        buy_fee_pct: float,
        sell_fee_pct: float,
        slippage_pct: float,
        partial_exit_ratio: float,
        risk_off_mode: str,
        risk_off_size_multiplier: float,
    ):
        self.account_size = float(account_size)
        self.risk_per_trade_pct = float(risk_per_trade_pct)
        self.daily_max_loss_r = float(daily_max_loss_r)
        self.max_open_positions = int(max_open_positions)
        self.lot_size = int(lot_size)
        self.buy_fee_pct = float(buy_fee_pct)
        self.sell_fee_pct = float(sell_fee_pct)
        self.slippage_pct = float(slippage_pct)
        self.partial_exit_ratio = float(partial_exit_ratio)
        self.risk_off_mode = risk_off_mode
        self.risk_off_size_multiplier = float(risk_off_size_multiplier)

    def can_open_trade(self, open_positions: int, realized_r: float) -> tuple[bool, str]:
        if open_positions >= self.max_open_positions:
            return False, f"Maks posisi harian tercapai ({self.max_open_positions})."
        if realized_r <= -abs(self.daily_max_loss_r):
            return False, f"Daily max loss tercapai ({realized_r:.2f}R)."
        return True, ""

    def plan_position(
        self,
        entry: float,
        stop: float,
        open_positions: int,
        realized_r: float,
        risk_off: bool = False,
        ihsg_chg: float | None = None,
    ) -> tuple[PositionPlan | None, str]:
        can_open, reason = self.can_open_trade(open_positions, realized_r)
        if not can_open:
            return None, reason

        if risk_off and self.risk_off_mode == "block":
            return None, "Risk-off aktif: pembukaan posisi baru diblokir."

        effective_entry = entry * (1 + self.buy_fee_pct + self.slippage_pct)
        effective_stop = stop * (1 - self.sell_fee_pct - self.slippage_pct)
        per_share_risk = effective_entry - effective_stop
        if per_share_risk <= 0:
            return None, "Risk per share tidak valid."

        risk_amount = self.account_size * self.risk_per_trade_pct
        size_mode = "normal"
        notes = "Ukuran posisi normal."
        
        # ── Dynamic Position Sizing ──────────────────────────────────────
        if risk_off:
            risk_amount *= self.risk_off_size_multiplier
            size_mode = "risk_off_reduced"
            notes = "Risk-off aktif: ukuran posisi diperkecil."
        elif ihsg_chg is not None:
            if ihsg_chg >= 0.5:
                risk_amount *= 1.25 # Aggressive Mode (+25% risk)
                size_mode = "aggressive"
                notes = "IHSG Bullish (>0.5%): Risk dinaikkan (Aggressive)."
            elif ihsg_chg <= -0.5:
                risk_amount *= 0.75 # Defensive Mode (-25% risk)
                size_mode = "defensive"
                notes = "IHSG Bearish (<-0.5%): Risk diturunkan (Defensive)."

        raw_qty = floor(risk_amount / per_share_risk)
        lot_qty = (raw_qty // self.lot_size) * self.lot_size
        if lot_qty < self.lot_size:
            return None, "Ukuran posisi terlalu kecil setelah pembulatan lot."

        return PositionPlan(
            qty=lot_qty,
            lot_count=lot_qty // self.lot_size,
            risk_amount=round(risk_amount, 2),
            planned_notional=round(lot_qty * entry, 2),
            effective_entry=round(effective_entry, 4),
            effective_stop=round(effective_stop, 4),
            size_mode=size_mode,
            notes=notes,
        ), ""

    def evaluate_trade(
        self,
        candles: pd.DataFrame,
        signal_timestamp: str,
        entry: float,
        stop: float,
        tp1: float,
        tp2: float,
        qty: int,
        finalize: bool,
    ) -> dict:
        path = self._slice_path(candles, signal_timestamp)
        if path.empty:
            return self._unfilled_result(entry, qty, "Belum ada candle setelah sinyal.")

        fill_index = self._find_fill_index(path, entry)
        if fill_index is None:
            last_close = float(path["close"].iloc[-1])
            if finalize:
                return self._unfilled_result(entry, qty, "Entry limit tidak tersentuh sampai evaluasi.")
            return self._snapshot_unfilled(entry, qty, last_close)

        filled_at = path.index[fill_index]
        post_fill = path.iloc[fill_index:]
        partial_qty = int(qty * self.partial_exit_ratio)
        partial_qty -= partial_qty % self.lot_size
        if partial_qty <= 0:
            partial_qty = 0
        remaining_qty = qty - partial_qty
        fill_price = float(entry)

        realized_amount = 0.0
        realized_qty = 0
        events: list[str] = []
        stop_price = float(stop)
        status = "OPEN"
        exit_price = None
        exit_reason = "Masih terbuka"
        partial_taken = False

        for row in post_fill.itertuples():
            hit_stop = float(row.low) <= stop_price
            hit_tp1 = float(row.high) >= tp1
            hit_tp2 = float(row.high) >= tp2

            if partial_taken:
                if hit_stop and hit_tp2:
                    status = "TP1_SL_HIT"
                    exit_price = stop_price
                    exit_reason = "Ambigu candle setelah TP1: asumsi konservatif breakeven (SL) kena lebih dulu."
                    if remaining_qty > 0:
                        realized_amount += self._net_pnl(fill_price, exit_price, remaining_qty)
                        realized_qty += remaining_qty
                    events.append("BE")
                    break

                if hit_stop:
                    status = "TP1_SL_HIT"
                    exit_price = stop_price
                    exit_reason = "Sisa posisi keluar di breakeven (SL) setelah TP1."
                    if remaining_qty > 0:
                        realized_amount += self._net_pnl(fill_price, exit_price, remaining_qty)
                        realized_qty += remaining_qty
                    events.append("BE")
                    break

                if hit_tp2:
                    status = "TP2_HIT"
                    exit_price = float(tp2)
                    exit_reason = "TP2 tercapai setelah partial TP1."
                    if remaining_qty > 0:
                        realized_amount += self._net_pnl(fill_price, exit_price, remaining_qty)
                        realized_qty += remaining_qty
                    events.append("TP2")
                    break

                continue

            if hit_stop and (hit_tp1 or hit_tp2):
                status = "SL_HIT"
                exit_price = stop_price
                exit_reason = "Ambigu candle: asumsi konservatif stop kena lebih dulu."
                realized_amount += self._net_pnl(fill_price, exit_price, qty)
                realized_qty = qty
                events.append("SL")
                break

            if hit_stop:
                status = "SL_HIT"
                exit_price = stop_price
                exit_reason = "Stop loss tersentuh."
                realized_amount += self._net_pnl(fill_price, exit_price, qty)
                realized_qty = qty
                events.append("SL")
                break

            if hit_tp2:
                status = "TP2_HIT"
                exit_price = float(tp2)
                exit_reason = "TP2 tercapai."
                realized_amount += self._net_pnl(fill_price, exit_price, qty)
                realized_qty = qty
                events.append("TP2")
                break

            if hit_tp1:
                partial_taken = True
                status = "TP1_HIT"
                events.append("TP1")
                if partial_qty > 0:
                    realized_amount += self._net_pnl(fill_price, float(tp1), partial_qty)
                    realized_qty += partial_qty
                stop_price = fill_price
                exit_reason = "TP1 tercapai, sisa posisi diproteksi ke breakeven."
                continue

        last_close = float(post_fill["close"].iloc[-1])
        if realized_qty < qty:
            unresolved_qty = qty - realized_qty
            if finalize:
                exit_price = last_close
                final_status = "TP1_EXIT_EOD" if partial_taken else "EXIT_EOD"
                exit_reason = "Posisi ditutup di harga evaluasi terakhir (akhir sesi)."
                realized_amount += self._net_pnl(fill_price, last_close, unresolved_qty)
                realized_qty += unresolved_qty
                status = final_status
            else:
                mtm_amount = realized_amount + self._net_pnl(fill_price, last_close, unresolved_qty)
                return self._result_payload(
                    status=status,
                    fill_status="FILLED",
                    filled_at=str(filled_at),
                    filled_price=fill_price,
                    last_price=last_close,
                    exit_price=None,
                    exit_reason=exit_reason,
                    pnl_amount=mtm_amount,
                    qty=qty,
                    realized_qty=realized_qty,
                    events=events,
                    finalized=False,
                )

        return self._result_payload(
            status=status,
            fill_status="FILLED",
            filled_at=str(filled_at),
            filled_price=fill_price,
            last_price=last_close,
            exit_price=exit_price,
            exit_reason=exit_reason,
            pnl_amount=realized_amount,
            qty=qty,
            realized_qty=realized_qty,
            events=events,
            finalized=finalize,
        )

    def _slice_path(self, candles: pd.DataFrame, signal_timestamp: str) -> pd.DataFrame:
        signal_ts = pd.Timestamp(signal_timestamp)
        idx = candles.index
        if getattr(idx, "tz", None) is not None and signal_ts.tzinfo is None:
            signal_ts = signal_ts.tz_localize(idx.tz)
        elif getattr(idx, "tz", None) is None and signal_ts.tzinfo is not None:
            signal_ts = signal_ts.tz_convert(None)
        return candles.loc[candles.index >= signal_ts]

    @staticmethod
    def _find_fill_index(path: pd.DataFrame, entry: float) -> int | None:
        for i, row in enumerate(path.itertuples()):
            if float(row.low) <= entry <= float(row.high):
                return i
        return None

    def _net_pnl(self, entry: float, exit_price: float, qty: int) -> float:
        gross_buy = entry * qty
        gross_sell = exit_price * qty
        buy_cost = gross_buy * (self.buy_fee_pct + self.slippage_pct)
        sell_cost = gross_sell * (self.sell_fee_pct + self.slippage_pct)
        return round((gross_sell - sell_cost) - (gross_buy + buy_cost), 2)

    def _result_payload(
        self,
        status: str,
        fill_status: str,
        filled_at: str | None,
        filled_price: float | None,
        last_price: float,
        exit_price: float | None,
        exit_reason: str,
        pnl_amount: float,
        qty: int,
        realized_qty: int,
        events: list[str],
        finalized: bool,
    ) -> dict:
        base_cost = (filled_price or last_price) * qty
        pnl_pct = round((pnl_amount / base_cost) * 100, 2) if base_cost else 0.0
        risk_unit = self.account_size * self.risk_per_trade_pct
        realized_r = round(pnl_amount / risk_unit, 2) if risk_unit else 0.0
        return {
            "status": status,
            "fill_status": fill_status,
            "filled_at": filled_at,
            "filled_price": round(filled_price, 2) if filled_price is not None else None,
            "last_price": round(last_price, 2),
            "exit_price": round(exit_price, 2) if exit_price is not None else None,
            "exit_reason": exit_reason,
            "pnl_amount": round(pnl_amount, 2),
            "pnl_pct": pnl_pct,
            "realized_r": realized_r,
            "realized_qty": realized_qty,
            "events": ", ".join(events) if events else "-",
            "finalized": finalized,
        }

    def _unfilled_result(self, entry: float, qty: int, reason: str) -> dict:
        return {
            "status": "UNFILLED",
            "fill_status": "UNFILLED",
            "filled_at": None,
            "filled_price": None,
            "last_price": round(entry, 2),
            "exit_price": None,
            "exit_reason": reason,
            "pnl_amount": 0.0,
            "pnl_pct": 0.0,
            "realized_r": 0.0,
            "realized_qty": 0,
            "events": "-",
            "finalized": True,
        }

    def _snapshot_unfilled(self, entry: float, qty: int, last_close: float) -> dict:
        return {
            "status": "WAIT_ENTRY",
            "fill_status": "UNFILLED",
            "filled_at": None,
            "filled_price": None,
            "last_price": round(last_close, 2),
            "exit_price": None,
            "exit_reason": "Entry limit belum tersentuh.",
            "pnl_amount": 0.0,
            "pnl_pct": 0.0,
            "realized_r": 0.0,
            "realized_qty": 0,
            "events": "-",
            "finalized": False,
        }
