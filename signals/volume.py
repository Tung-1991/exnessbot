# -*- coding: utf-8 -*-
# signals/volume.py

import pandas as pd
from typing import Optional, Dict, Any

def get_volume_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Kiểm tra xem volume có xác nhận cho tín hiệu hay không.
    Trả về điểm phạt nếu volume yếu.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá với cột 'volume'.
        config (Dict[str, Any]): Toàn bộ file cấu hình.

    Returns:
        float: Điểm phạt (số âm) nếu volume yếu, hoặc 0.0 nếu volume đủ mạnh.
    """
    if 'volume' not in df.columns:
        return 0.0

    vol_config = config['INDICATORS_CONFIG']['VOLUME']
    penalty_weights = config['PENALTY_WEIGHTS']
    
    # Tính toán volume trung bình
    volume_ma = df['volume'].rolling(window=vol_config['MA_PERIOD']).mean()
    if volume_ma.empty:
        return 0.0

    last_volume = df['volume'].iloc[-1]
    avg_volume = volume_ma.iloc[-1]
    
    # Lấy hệ số yêu cầu từ config, nếu không có thì mặc định là 1.0
    surge_ratio = vol_config.get('SURGE_RATIO', 1.0)

    # Logic phạt điểm
    # Nếu volume hiện tại thấp hơn volume trung bình * hệ số -> tín hiệu yếu
    if last_volume < (avg_volume * surge_ratio):
        return -penalty_weights['LOW_VOLUME_CONFIRMATION_PENALTY'] # Trả về điểm phạt, ví dụ -3.0
    else:
        return 0.0 # Volume đủ mạnh, không phạt điểm