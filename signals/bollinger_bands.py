# -*- coding: utf-8 -*-
# signals/bollinger_bands.py

import pandas as pd
from typing import Optional, Tuple

def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    """
    Tính toán 3 đường của chỉ báo Bollinger Bands.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá với cột 'close'.
        period (int): Chu kỳ để tính toán đường trung bình động.
        std_dev (float): Số lần độ lệch chuẩn để tính dải băng trên và dưới.

    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: Một tuple chứa (upper_band, middle_band, lower_band),
                                                hoặc None nếu có lỗi.
    """
    if 'close' not in df.columns:
        return None

    # Tính toán đường giữa (Simple Moving Average)
    middle_band = df['close'].rolling(window=period).mean()
    
    # Tính toán độ lệch chuẩn
    std = df['close'].rolling(window=period).std()
    
    # Tính toán dải băng trên và dưới
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    
    return upper_band, middle_band, lower_band

def get_bb_signal(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> int:
    """
    Xác định tín hiệu MUA/BÁN dựa trên vị trí của giá so với Bollinger Bands.
    Đây là logic cốt lõi cho Phase 1.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá.
        period (int): Chu kỳ của BB.
        std_dev (float): Độ lệch chuẩn của BB.

    Returns:
        int: +1 cho tín hiệu MUA, -1 cho tín hiệu BÁN, 0 cho không có tín hiệu.
    """
    bands = calculate_bollinger_bands(df, period, std_dev)
    if bands is None:
        return 0

    upper_band, _, lower_band = bands
    
    # Lấy dữ liệu của cây nến gần nhất đã đóng cửa
    last_close = df['close'].iloc[-1]
    last_upper_band = upper_band.iloc[-1]
    last_lower_band = lower_band.iloc[-1]
    
    # Logic xác định tín hiệu
    if last_close > last_upper_band:
        return -1  # Tín hiệu BÁN (SHORT)
    elif last_close < last_lower_band:
        return 1   # Tín hiệu MUA (LONG)
    else:
        return 0   # Không có tín hiệu