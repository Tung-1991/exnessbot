# -*- coding: utf-8 -*-
# signals/ema.py

import pandas as pd
from typing import Optional, Dict, Any, Tuple

def calculate_emas(df: pd.DataFrame, config: Dict[str, Any]) -> Optional[Tuple[pd.Series, pd.Series]]:
    """
    Tính toán các đường Exponential Moving Average (EMA).

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá với cột 'close'.
        config (Dict[str, Any]): Toàn bộ file cấu hình.

    Returns:
        Tuple[pd.Series, pd.Series]: Một tuple chứa (slow_ema, fast_ema), hoặc None nếu có lỗi.
    """
    if 'close' not in df.columns:
        return None

    ema_config = config['INDICATORS_CONFIG']['EMA']
    
    slow_ema = df['close'].ewm(span=ema_config['SLOW_PERIOD'], adjust=False).mean()
    fast_ema = df['close'].ewm(span=ema_config['FAST_PERIOD'], adjust=False).mean()
    
    return slow_ema, fast_ema

def get_ema_score(df: pd.DataFrame, config: Dict[str, Any], signal_direction: int) -> float:
    """
    Kiểm tra xem tín hiệu có đi ngược lại xu hướng dài hạn (EMA chậm) không.
    Trả về điểm phạt nếu có.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá.
        config (Dict[str, Any]): Toàn bộ file cấu hình.
        signal_direction (int): Hướng tín hiệu dự kiến (+1 cho Mua, -1 cho Bán).

    Returns:
        float: Điểm phạt (số âm) nếu đi ngược xu hướng, hoặc 0.0 nếu thuận xu hướng.
    """
    if signal_direction == 0:
        return 0.0

    penalty_weights = config['PENALTY_WEIGHTS']
    emas = calculate_emas(df, config)
    
    if emas is None:
        return 0.0

    slow_ema, _ = emas
    last_close = df['close'].iloc[-1]
    last_slow_ema = slow_ema.iloc[-1]
    
    # Xác định xu hướng dài hạn
    is_long_term_uptrend = last_close > last_slow_ema

    # Logic phạt điểm
    # Nếu định MUA nhưng xu hướng dài hạn đang là GIẢM -> Phạt
    if signal_direction == 1 and not is_long_term_uptrend:
        return -penalty_weights['COUNTER_EMA_TREND_PENALTY']
        
    # Nếu định BÁN nhưng xu hướng dài hạn đang là TĂNG -> Phạt
    elif signal_direction == -1 and is_long_term_uptrend:
        return -penalty_weights['COUNTER_EMA_TREND_PENALTY']
        
    else:
        # Tín hiệu thuận theo xu hướng, không phạt điểm
        return 0.0