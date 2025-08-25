import pandas as pd
import ta
import numpy as np
from typing import Dict

def calculate_indicators(df: pd.DataFrame, symbol: str, interval: str) -> dict:
    if len(df) < 51:
        return {"price": df["close"].iloc[-1] if not df.empty else 0.0, "reason": "Thiếu dữ liệu"}
        
    closed_candle_idx = -2
    current_live_price = df["close"].iloc[-1]
    price = df["close"].iloc[closed_candle_idx]
    volume = df["volume"].iloc[closed_candle_idx]
    
    ema_9 = ta.trend.ema_indicator(df["close"], window=9).iloc[closed_candle_idx]
    ema_20 = ta.trend.ema_indicator(df["close"], window=20).iloc[closed_candle_idx]
    ema_50 = ta.trend.ema_indicator(df["close"], window=50).iloc[closed_candle_idx]
    ema_200 = ta.trend.ema_indicator(df["close"], window=200).iloc[closed_candle_idx] if len(df) >= 200 else 0.0
    
    trend_score = 0
    if ema_9 > ema_20: trend_score += 1
    if ema_20 > ema_50: trend_score += 1
    if ema_9 > ema_50: trend_score += 1
    
    ema_diff_pct = ((ema_9 - ema_20) / ema_20) * 100 if ema_20 > 0 else 0
    
    if trend_score >= 2 and ema_diff_pct > 0.02:
        trend = "uptrend"
    elif trend_score <= -2 and ema_diff_pct < -0.02:
        trend = "downtrend"
    else:
        trend = "sideways"
    
    rsi_series = ta.momentum.rsi(df["close"], window=14)
    rsi_14 = rsi_series.iloc[closed_candle_idx]
    
    rsi_divergence = "none"
    if len(df) >= 10:
        recent_prices = df['close'].iloc[-10:-2]
        recent_rsi = rsi_series.iloc[-10:-2]
        price_trend = 1 if recent_prices.iloc[-1] > recent_prices.iloc[0] else -1
        rsi_trend = 1 if recent_rsi.iloc[-1] > recent_rsi.iloc[0] else -1
        if price_trend > 0 and rsi_trend < 0 and rsi_14 > 60:
            rsi_divergence = "bearish"
        elif price_trend < 0 and rsi_trend > 0 and rsi_14 < 40:
            rsi_divergence = "bullish"
        
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[closed_candle_idx]
    bb_lower = bb.bollinger_lband().iloc[closed_candle_idx]
    bb_middle = bb.bollinger_mavg().iloc[closed_candle_idx]
    bb_width = bb.bollinger_wband().iloc[closed_candle_idx]
    
    macd = ta.trend.MACD(df["close"])
    macd_line = macd.macd().iloc[closed_candle_idx]
    macd_signal = macd.macd_signal().iloc[closed_candle_idx]
    macd_hist = macd.macd_diff().iloc[closed_candle_idx]
    
    macd_cross = "neutral"
    if len(macd.macd()) > abs(closed_candle_idx):
        prev_hist = macd.macd_diff().iloc[closed_candle_idx - 1]
        if prev_hist < 0 and macd_hist > 0:
            macd_cross = "bullish"
        elif prev_hist > 0 and macd_hist < 0:
            macd_cross = "bearish"
        
    adx = ta.trend.adx(df["high"], df["low"], df["close"], window=14).iloc[closed_candle_idx]
    vol_ma20 = df["volume"].rolling(window=20).mean().iloc[closed_candle_idx]
    cmf = ta.volume.chaikin_money_flow(df["high"], df["low"], df["close"], df["volume"], window=20).iloc[closed_candle_idx]
    
    atr_series = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14)
    atr_value = atr_series.iloc[closed_candle_idx]
    atr_percent = (atr_value / price) * 100 if price > 0 and not pd.isna(atr_value) else 0.0
    
    recent_data = df.iloc[-51:-1]
    support_level = recent_data["low"].rolling(10).min().iloc[-1]
    resistance_level = recent_data["high"].rolling(10).max().iloc[-1]
    
    breakout_signal = "none"
    if len(df) >= 50:
        bb_std = df["close"].rolling(20).std().iloc[closed_candle_idx]
        bb_mean_std = df["close"].rolling(20).std().rolling(30).mean().iloc[closed_candle_idx]
        is_squeezing = bb_std < bb_mean_std * 0.75 if not pd.isna(bb_mean_std) else False
        
        if is_squeezing and volume > vol_ma20 * 1.5:
            if price > bb_upper:
                breakout_signal = "bullish"
            elif price < bb_lower:
                breakout_signal = "bearish"
    
    candle_pattern = "none"
    if len(df) >= abs(closed_candle_idx) + 1:
        curr_o, curr_h, curr_l, curr_c = df["open"].iloc[closed_candle_idx], df["high"].iloc[closed_candle_idx], df["low"].iloc[closed_candle_idx], df["close"].iloc[closed_candle_idx]
        prev_o, prev_h, prev_l, prev_c = df["open"].iloc[closed_candle_idx-1], df["high"].iloc[closed_candle_idx-1], df["low"].iloc[closed_candle_idx-1], df["close"].iloc[closed_candle_idx-1]
        
        body = abs(curr_c - curr_o)
        upper_wick = curr_h - max(curr_c, curr_o)
        lower_wick = min(curr_c, curr_o) - curr_l
        
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            candle_pattern = "hammer"
        elif upper_wick > body * 2 and lower_wick < body * 0.5:
            candle_pattern = "shooting_star"
        elif curr_c > curr_o and prev_c < prev_o and curr_o < prev_c and curr_c > prev_o:
            candle_pattern = "bullish_engulfing"
        elif curr_c < curr_o and prev_c > prev_o and curr_o > prev_c and curr_c < prev_o:
            candle_pattern = "bearish_engulfing"
    
    result = {
        "symbol": symbol, "interval": interval, "price": current_live_price, "closed_candle_price": price,
        "ema_9": ema_9, "ema_20": ema_20, "ema_50": ema_50, "ema_200": ema_200, "trend": trend,
        "rsi_14": rsi_14, "rsi_divergence": rsi_divergence, "bb_upper": bb_upper, "bb_lower": bb_lower,
        "bb_middle": bb_middle, "bb_width": bb_width, "macd_line": macd_line, "macd_signal": macd_signal,
        "macd_hist": macd_hist, "macd_cross": macd_cross, "adx": adx, "volume": volume, "vol_ma20": vol_ma20,
        "cmf": cmf, "atr": atr_value, "atr_percent": atr_percent,
        "candle_pattern": candle_pattern, "support_level": support_level, "resistance_level": resistance_level,
        "breakout_signal": breakout_signal, "open": df["open"].iloc[closed_candle_idx],
        "high": df["high"].iloc[closed_candle_idx], "low": df["low"].iloc[closed_candle_idx],
        "prev_high": df["high"].iloc[closed_candle_idx - 1] if len(df) > abs(closed_candle_idx - 1) else 0,
        "prev_low": df["low"].iloc[closed_candle_idx - 1] if len(df) > abs(closed_candle_idx - 1) else 0,
        "prev_close": df["close"].iloc[closed_candle_idx - 1] if len(df) > abs(closed_candle_idx - 1) else 0,
    }
    
    for k, v in result.items():
        if isinstance(v, (np.floating, float)) and (np.isnan(v) or np.isinf(v)): 
            result[k] = 0.0
    return result