import unittest
from datetime import datetime
import pandas as pd
from unittest.mock import patch, MagicMock

from backtester import HistoricalDataLoader

class TestBacktester(unittest.TestCase):

    @patch('yfinance.download')
    def test_historical_data_loader(self, mock_yf_download):
        # Mock yfinance.download to return a sample DataFrame
        sample_data = {
            'Open': [100, 101, 102],
            'High': [102, 103, 104],
            'Low': [99, 100, 101],
            'Close': [101, 102, 103],
            'Volume': [1000, 1200, 1100],
        }
        index = pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03'])
        mock_df = pd.DataFrame(sample_data, index=index)
        mock_yf_download.return_value = mock_df

        loader = HistoricalDataLoader()
        df = loader.load_data("BBCA", "2023-01-01", "2023-01-03", "1d")

        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 3)
        self.assertIn('close', df.columns) # Ensure columns are lowercased
        mock_yf_download.assert_called_once_with(
            "BBCA.JK", start="2023-01-01", end="2023-01-03", interval="1d",
            progress=False, auto_adjust=True
        )

    @patch('yfinance.download')
    def test_historical_data_loader_empty_df(self, mock_yf_download):
        mock_yf_download.return_value = pd.DataFrame() # Empty DataFrame

        loader = HistoricalDataLoader()
        df = loader.load_data("BBCA", "2023-01-01", "2023-01-03", "1d")

        self.assertIsNone(df)

    @patch('yfinance.download', side_effect=Exception("Network error"))
    def test_historical_data_loader_error(self, mock_yf_download):
        loader = HistoricalDataLoader()
        df = loader.load_data("BBCA", "2023-01-01", "2023-01-03", "1d")
        self.assertIsNone(df)
