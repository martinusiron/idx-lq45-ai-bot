class ConservativeRiskManager:
    def __init__(self, balance):
        self.balance = balance
        self.positions = {}
        self.daily_pnl = 0
        self.max_daily_loss = balance * 0.03  # Rp120k

    def safe_position_size(self, price, sl_pct=0.01):
        risk_amount = self.balance * 0.01  # Rp40k max
        sl_diff = price * sl_pct
        qty = int(risk_amount / sl_diff / 100) * 100

        # Max 25% capital
        max_capital = self.balance * 0.25
        qty = min(qty, int(max_capital / price / 100) * 100)

        return max(100, qty)  # Min 1 lot

    def can_trade(self):
        return (len(self.positions) < 3 and
                self.daily_pnl > -self.max_daily_loss)
