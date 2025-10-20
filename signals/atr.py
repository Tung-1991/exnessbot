# -*- coding: utf-8 -*-
# signals/atr.py

import pandas as pd
from typing import Optional

def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo Average True Range (ATR).

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá với các cột 'high', 'low', 'close'.
        period (int): Chu kỳ để tính toán ATR.

    Returns:
        pd.Series: Một Series chứa giá trị ATR, hoặc None nếu có lỗi.
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        # Ghi log lỗi ở đây sau này, ví dụ: logger.error("...")
        return None

    # Tính toán True Range (TR)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # Tính toán ATR bằng Exponential Moving Average (EMA) của TR
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    return atr