# -*- coding: utf-8 -*-
# signals/rsi.py

import pandas as pd
from typing import Optional, Dict, Any

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo Relative Strength Index (RSI).

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá với cột 'close'.
        period (int): Chu kỳ để tính toán RSI.

    Returns:
        pd.Series: Một Series chứa giá trị RSI, hoặc None nếu có lỗi.
    """
    if 'close' not in df.columns:
        return None

    # Tính toán sự thay đổi giá
    delta = df['close'].diff()

    # Tách biệt các thay đổi giá dương (gain) và âm (loss)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Tính toán Relative Strength (RS)
    rs = gain / loss
    
    # Tính toán RSI
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def get_rsi_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Xác định điểm số dựa trên trạng thái quá mua/quá bán của RSI.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá.
        config (Dict[str, Any]): Toàn bộ file cấu hình.

    Returns:
        float: Điểm số cho tín hiệu (+ cho Mua, - cho Bán, 0 cho trung lập).
    """
    rsi_config = config['INDICATORS_CONFIG']['RSI']
    weights = config['SCORING_WEIGHTS']
    
    rsi_series = calculate_rsi(df, period=rsi_config['PERIOD'])
    if rsi_series is None or rsi_series.empty:
        return 0.0

    last_rsi = rsi_series.iloc[-1]
    
    # Logic xác định điểm số
    if last_rsi < rsi_config['OVERSOLD']:
        return weights['RSI_EXTREME_SCORE']  # Ví dụ: trả về +2.0
    elif last_rsi > rsi_config['OVERBOUGHT']:
        return -weights['RSI_EXTREME_SCORE'] # Ví dụ: trả về -2.0
    else:
        return 0.0