import pandas as pd
import pandas_ta as ta
import numpy as np

def ensemble_signal(df):
    """3 Strategy Consensus"""
    signals = []

    # 1. EMA Crossover
    df['ema12'] = ta.ema(df['close'], 12)
    df['ema26'] = ta.ema(df['close'], 26)
    signals.append('BUY' if df['ema12'].iloc[-1] > df['ema26'].iloc[-1] else 'SELL')

    # 2. RSI
    df['rsi'] = ta.rsi(df['close'], 14)
    signals.append('BUY' if df['rsi'].iloc[-1] < 35 else 'SELL' if df['rsi'].iloc[-1] > 65 else 'HOLD')

    # 3. Volume Breakout
    df['vol_ma'] = ta.sma(df['volume'], 20)
    vol_spike = df['volume'].iloc[-1] > df['vol_ma'].iloc[-1] * 1.5
    signals.append('BUY' if vol_spike and df['close'].iloc[-1] > df['high'].rolling(10).max().iloc[-2] else 'HOLD')

    buy_count = signals.count('BUY')
    return 'BUY' if buy_count >= 2 else 'HOLD'
