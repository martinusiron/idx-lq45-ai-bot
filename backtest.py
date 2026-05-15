import sys
import logging
import asyncio
from datetime import datetime, timedelta
import yfinance as yf
from analyzer import StockAnalyzer
from config import LQ45_SYMBOLS, HIGH_PROB_THRESHOLD

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_backtest(days_back: int = 365, threshold: int = HIGH_PROB_THRESHOLD):
    logger.info(f"🚀 Memulai Backtest Offline untuk {days_back} hari terakhir...")
    logger.info(f"Target Skor Threshold: {threshold}")

    analyzer = StockAnalyzer()
    analyzer._goapi_ok = False  # Paksa pakai yfinance untuk backtest massal historis

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back + 365) # +1 tahun untuk indikator

    # Download semua data LQ45 menggunakan yf.download secara bulk
    logger.info("📡 Mengunduh data massal dari Yahoo Finance...")
    tickers = [s + ".JK" for s in LQ45_SYMBOLS]
    data = yf.download(tickers, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), progress=True)

    if data.empty:
        logger.error("❌ Gagal mengunduh data.")
        return

    # TODO: Implementasi logika simulasi iteratif per candle
    # Karena pandas DataFrame yang dihasilkan sangat kompleks, untuk iterasi pertama:
    logger.info("🛠️ Modul backtest ini sedang dalam pengembangan tahap awal.")
    logger.info("Nantinya akan mensimulasikan buy/sell rule secara iteratif.")

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    run_backtest(days)
