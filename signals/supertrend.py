# -*- coding: utf-8 -*-
# signals/supertrend.py

import pandas as pd
from typing import Optional, Dict, Any

def calculate_supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo SuperTrend.

    Args:
        df (pd.DataFrame): DataFrame chứa 'high', 'low', 'close'.
        atr_period (int): Chu kỳ để tính ATR.
        multiplier (float): Hệ số nhân cho ATR.

    Returns:
        pd.Series: Một Series chứa giá trị của đường SuperTrend.
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        return None

    # Tính toán ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/atr_period, adjust=False).mean()

    # Tính toán dải băng trên và dưới cơ bản
    basic_upper_band = (df['high'] + df['low']) / 2 + multiplier * atr
    basic_lower_band = (df['high'] + df['low']) / 2 - multiplier * atr

    # Tính toán dải băng trên và dưới cuối cùng
    final_upper_band = pd.Series(index=df.index, dtype=float)
    final_lower_band = pd.Series(index=df.index, dtype=float)

    for i in range(1, len(df)):
        if basic_upper_band.iloc[i] < final_upper_band.iloc[i-1] or df['close'].iloc[i-1] > final_upper_band.iloc[i-1]:
            final_upper_band.iloc[i] = basic_upper_band.iloc[i]
        else:
            final_upper_band.iloc[i] = final_upper_band.iloc[i-1]

        if basic_lower_band.iloc[i] > final_lower_band.iloc[i-1] or df['close'].iloc[i-1] < final_lower_band.iloc[i-1]:
            final_lower_band.iloc[i] = basic_lower_band.iloc[i]
        else:
            final_lower_band.iloc[i] = final_lower_band.iloc[i-1]

    # Tính toán đường SuperTrend
    supertrend = pd.Series(index=df.index, dtype=float)
    for i in range(1, len(df)):
        if supertrend.iloc[i-1] == final_upper_band.iloc[i-1] and df['close'].iloc[i] <= final_upper_band.iloc[i]:
            supertrend.iloc[i] = final_upper_band.iloc[i]
        elif supertrend.iloc[i-1] == final_upper_band.iloc[i-1] and df['close'].iloc[i] > final_upper_band.iloc[i]:
            supertrend.iloc[i] = final_lower_band.iloc[i]
        elif supertrend.iloc[i-1] == final_lower_band.iloc[i-1] and df['close'].iloc[i] >= final_lower_band.iloc[i]:
            supertrend.iloc[i] = final_lower_band.iloc[i]
        elif supertrend.iloc[i-1] == final_lower_band.iloc[i-1] and df['close'].iloc[i] < final_lower_band.iloc[i]:
            supertrend.iloc[i] = final_upper_band.iloc[i]
            
    return supertrend

def get_supertrend_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Xác định điểm số dựa trên xu hướng của SuperTrend.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá.
        config (Dict[str, Any]): Toàn bộ file cấu hình.

    Returns:
        float: Điểm số cho tín hiệu (+ cho Mua, - cho Bán, 0 cho trung lập).
    """
    st_config = config['INDICATORS_CONFIG']['SUPERTREND']
    weights = config['SCORING_WEIGHTS']

    supertrend_series = calculate_supertrend(
        df, 
        atr_period=st_config['ATR_PERIOD'], 
        multiplier=st_config['MULTIPLIER']
    )
    if supertrend_series is None or supertrend_series.empty:
        return 0.0

    last_close = df['close'].iloc[-1]
    last_supertrend = supertrend_series.iloc[-1]

    # Logic xác định điểm số
    # Nếu giá nằm trên đường SuperTrend -> Xu hướng tăng
    if last_close > last_supertrend:
        return weights['SUPERTREND_ALIGN_SCORE']  # Ví dụ: trả về +3.0
    # Nếu giá nằm dưới đường SuperTrend -> Xu hướng giảm
    elif last_close < last_supertrend:
        return -weights['SUPERTREND_ALIGN_SCORE'] # Ví dụ: trả về -3.0
    else:
        return 0.0