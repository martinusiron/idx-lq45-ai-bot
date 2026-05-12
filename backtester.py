import logging
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

class HistoricalDataLoader:
    def load_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str,
    ) -> pd.DataFrame | None:
        try:
            ticker = f"{symbol}.JK" if not symbol.endswith(".JK") else symbol
            df = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                interval=interval,
                progress=False,
                auto_adjust=True
            )

            if df.empty:
                logger.warning(f"[{symbol}] No data fetched for {start_date} to {end_date}")
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]

            return df
        except Exception as exc:
            logger.error(f"[{symbol}] Error fetching data: {exc}")
            return None
