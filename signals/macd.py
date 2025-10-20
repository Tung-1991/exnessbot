# -*- coding: utf-8 -*-
# signals/macd.py

import pandas as pd
from typing import Optional, Dict, Any, Tuple

def calculate_macd(df: pd.DataFrame, fast_ema: int = 12, slow_ema: int = 26, signal_sma: int = 9) -> Optional[Tuple[pd.Series, pd.Series]]:
    """
    Tính toán đường MACD và đường Signal.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá với cột 'close'.
        fast_ema (int): Chu kỳ của EMA nhanh.
        slow_ema (int): Chu kỳ của EMA chậm.
        signal_sma (int): Chu kỳ để tính đường Signal.

    Returns:
        Tuple[pd.Series, pd.Series]: Một tuple chứa (macd_line, signal_line), hoặc None nếu có lỗi.
    """
    if 'close' not in df.columns:
        return None

    # Tính toán hai đường EMA
    ema_fast = df['close'].ewm(span=fast_ema, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_ema, adjust=False).mean()
    
    # Tính toán đường MACD
    macd_line = ema_fast - ema_slow
    
    # Tính toán đường Signal
    signal_line = macd_line.ewm(span=signal_sma, adjust=False).mean()
    
    return macd_line, signal_line

def get_macd_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Xác định điểm số dựa trên sự giao cắt giữa đường MACD và đường Signal.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá.
        config (Dict[str, Any]): Toàn bộ file cấu hình.

    Returns:
        float: Điểm số cho tín hiệu (+ cho Mua, - cho Bán, 0 cho trung lập).
    """
    macd_config = config['INDICATORS_CONFIG']['MACD']
    weights = config['SCORING_WEIGHTS']
    
    lines = calculate_macd(
        df,
        fast_ema=macd_config['FAST_EMA'],
        slow_ema=macd_config['SLOW_EMA'],
        signal_sma=macd_config['SIGNAL_SMA']
    )
    
    if lines is None or len(df) < 2:
        return 0.0

    macd_line, signal_line = lines
    
    # Lấy dữ liệu của 2 cây nến gần nhất để xác định sự giao cắt
    prev_macd = macd_line.iloc[-2]
    prev_signal = signal_line.iloc[-2]
    last_macd = macd_line.iloc[-1]
    last_signal = signal_line.iloc[-1]
    
    # Logic xác định điểm số
    # Bullish Crossover: MACD cắt lên trên đường Signal
    if prev_macd < prev_signal and last_macd > last_signal:
        return weights['MACD_CROSS_SCORE']  # Ví dụ: trả về +2.0
        
    # Bearish Crossover: MACD cắt xuống dưới đường Signal
    elif prev_macd > prev_signal and last_macd < last_signal:
        return -weights['MACD_CROSS_SCORE'] # Ví dụ: trả về -2.0
        
    else:
        return 0.0