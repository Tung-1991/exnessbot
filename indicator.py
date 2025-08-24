import pandas as pd
import ta
import numpy as np
from typing import Dict

def calculate_indicators(df: pd.DataFrame, symbol: str, interval: str) -> dict:
    """
    Tính toán các chỉ báo kỹ thuật từ DataFrame của nến.
    
    Args:
        df: DataFrame chứa dữ liệu nến (open, high, low, close, volume).
        symbol: Tên symbol (ví dụ: BTCUSD).
        interval: Khung thời gian (ví dụ: 5m, 1h).
    
    Returns:
        Một dict chứa các giá trị của chỉ báo.
    """
    # Trả về lỗi nếu không đủ dữ liệu
    if len(df) < 51:
        return {"price": df["close"].iloc[-1] if not df.empty else 0.0, "reason": "Thiếu dữ liệu"}
        
    closed_candle_idx = -2
    current_live_price = df["close"].iloc[-1]
    price = df["close"].iloc[closed_candle_idx]
    volume = df["volume"].iloc[closed_candle_idx]
    
    # Tính toán các chỉ báo
    ema_9 = ta.trend.ema_indicator(df["close"], window=9).iloc[closed_candle_idx]
    ema_20 = ta.trend.ema_indicator(df["close"], window=20).iloc[closed_candle_idx]
    ema_50 = ta.trend.ema_indicator(df["close"], window=50).iloc[closed_candle_idx]
    ema_200 = ta.trend.ema_indicator(df["close"], window=200).iloc[closed_candle_idx] if len(df) >= 200 else 0.0
    
    # 🟢 Đã sửa: Nới lỏng định nghĩa trend để tăng độ nhạy
    trend = "sideway"
    if ema_9 > ema_20:
        trend = "uptrend"
    elif ema_9 < ema_20:
        trend = "downtrend"
    
    rsi_series = ta.momentum.rsi(df["close"], window=14)
    rsi_14 = rsi_series.iloc[closed_candle_idx]
    
    rsi_divergence = "none"
    if len(df) >= abs(closed_candle_idx) + 1:
        px_curr, px_prev = df['close'].iloc[closed_candle_idx], df['close'].iloc[closed_candle_idx - 1]
        rsi_curr, rsi_prev = rsi_series.iloc[closed_candle_idx], rsi_series.iloc[closed_candle_idx - 1]
        if px_curr < px_prev and rsi_curr > rsi_prev and rsi_curr < 50: rsi_divergence = "bullish"
        elif px_curr > px_prev and rsi_curr < rsi_prev and rsi_curr > 50: rsi_divergence = "bearish"
        
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    bb_upper, bb_lower = bb.bollinger_hband().iloc[closed_candle_idx], bb.bollinger_lband().iloc[closed_candle_idx]
    bb_middle, bb_width = bb.bollinger_mavg().iloc[closed_candle_idx], bb.bollinger_wband().iloc[closed_candle_idx]
    
    macd = ta.trend.MACD(df["close"])
    macd_line, macd_signal, macd_hist = macd.macd().iloc[closed_candle_idx], macd.macd_signal().iloc[closed_candle_idx], macd.macd_diff().iloc[closed_candle_idx]
    
    macd_cross = "neutral"
    if len(macd.macd()) > abs(closed_candle_idx):
        prev_macd_line, prev_macd_signal = macd.macd().iloc[closed_candle_idx - 1], macd.macd_signal().iloc[closed_candle_idx - 1]
        if prev_macd_line < prev_macd_signal and macd_line > macd_signal: macd_cross = "bullish"
        elif prev_macd_line > prev_macd_signal and macd_line < macd_signal: macd_cross = "bearish"
        
    adx = ta.trend.adx(df["high"], df["low"], df["close"], window=14).iloc[closed_candle_idx]
    vol_ma20 = df["volume"].rolling(window=20).mean().iloc[closed_candle_idx]
    cmf = ta.volume.chaikin_money_flow(df["high"], df["low"], df["close"], df["volume"], window=20).iloc[closed_candle_idx]
    
    atr_series = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14)
    atr_value = atr_series.iloc[closed_candle_idx]
    atr_percent = (atr_value / price) * 100 if price > 0 and not pd.isna(atr_value) else 0.0
    
    fib_0_618 = 0.0
    if len(df) >= 50:
        recent_low, recent_high = df["low"].iloc[-50:].min(), df["high"].iloc[-50:].max()
        if recent_high > recent_low:
            fib_0_618 = recent_high - (recent_high - recent_low) * 0.618
            
    doji_type, candle_pattern = "none", "none"
    if len(df) >= abs(closed_candle_idx) + 1:
        prev_c, curr_c = df.iloc[closed_candle_idx - 1], df.iloc[closed_candle_idx]
        if (curr_c["close"] > curr_c["open"] and curr_c["open"] < prev_c["close"] and curr_c["close"] > prev_c["open"] and prev_c["close"] < prev_c["open"]): candle_pattern = "bullish_engulfing"
        elif (curr_c["close"] < curr_c["open"] and curr_c["open"] > prev_c["close"] and curr_c["close"] < prev_c["open"] and prev_c["close"] > prev_c["open"]): candle_pattern = "bearish_engulfing"
        
    recent_data = df.iloc[-51:-1]
    support_level, resistance_level = recent_data["low"].min(), recent_data["high"].max()
    
    breakout_signal = "none"
    avg_bb_width = bb.bollinger_wband().rolling(50).mean().iloc[closed_candle_idx]
    is_squeezing = bb_width < avg_bb_width * 0.85 if not pd.isna(avg_bb_width) else False
    closed_price = df["close"].iloc[closed_candle_idx]
    if is_squeezing and (vol_ma20 > 0 and volume > vol_ma20 * 1.8):
        if closed_price > bb_upper: breakout_signal = "bullish"
        elif closed_price < bb_lower: breakout_signal = "bearish"
        
    result = {
        "symbol": symbol, "interval": interval, "price": current_live_price, "closed_candle_price": price,
        "ema_9": ema_9, "ema_20": ema_20, "ema_50": ema_50, "ema_200": ema_200, "trend": trend,
        "rsi_14": rsi_14, "rsi_divergence": rsi_divergence, "bb_upper": bb_upper, "bb_lower": bb_lower,
        "bb_middle": bb_middle, "bb_width": bb_width, "macd_line": macd_line, "macd_signal": macd_signal,
        "macd_hist": macd_hist, "macd_cross": macd_cross, "adx": adx, "volume": volume, "vol_ma20": vol_ma20,
        "cmf": cmf, "atr": atr_value, "atr_percent": atr_percent, "fib_0_618": fib_0_618,
        "candle_pattern": candle_pattern, "support_level": support_level, "resistance_level": resistance_level,
        "breakout_signal": breakout_signal, "open": df["open"].iloc[closed_candle_idx]
    }
    
    result.update({
        "high": df["high"].iloc[closed_candle_idx],
        "low": df["low"].iloc[closed_candle_idx],
        # Thêm thêm nếu cần cho price action
        "prev_high": df["high"].iloc[closed_candle_idx - 1] if len(df) > abs(closed_candle_idx - 1) else 0,
        "prev_low": df["low"].iloc[closed_candle_idx - 1] if len(df) > abs(closed_candle_idx - 1) else 0,
        "prev_close": df["close"].iloc[closed_candle_idx - 1] if len(df) > abs(closed_candle_idx - 1) else 0,
    })

    for k, v in result.items():
        if isinstance(v, (np.floating, float)) and (np.isnan(v) or np.isinf(v)): result[k] = 0.0
    return result