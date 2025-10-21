# -*- coding: utf-8 -*-
# signals/bollinger_bands.py (v4.0 - Phase 4)

import pandas as pd
from typing import Optional, Tuple, Dict, Any

def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    """
    Tính toán 3 đường của chỉ báo Bollinger Bands.
    Hàm này không thay đổi.
    """
    if 'close' not in df.columns:
        return None

    middle_band = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    
    return upper_band, middle_band, lower_band

def get_bb_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên các cấp độ của Bollinger Bands.
    Hàm này đã được viết lại hoàn toàn.
    """
    cfg = config['SCORING_CONFIG']['BOLLINGER_BANDS']
    if not cfg['enabled']:
        return 0.0, 0.0

    bands = calculate_bollinger_bands(df, period=cfg['params']['period'], std_dev=cfg['params']['std_dev'])
    if bands is None:
        return 0.0, 0.0

    upper_band, _, lower_band = bands
    
    # Lấy dữ liệu của cây nến gần nhất
    last_candle = df.iloc[-1]
    last_close = last_candle['close']
    last_low = last_candle['low']
    last_high = last_candle['high']
    last_lower_band = lower_band.iloc[-1]
    last_upper_band = upper_band.iloc[-1]
    
    long_score, short_score = 0.0, 0.0

    # --- Tính điểm cho phe MUA (LONG) ---
    # Ưu tiên tín hiệu mạnh nhất trước
    if 'cross_outside' in cfg['score_levels'] and last_close < last_lower_band:
        long_score = cfg['score_levels']['cross_outside']
    elif 'wick_outside' in cfg['score_levels'] and last_low < last_lower_band:
        long_score = cfg['score_levels']['wick_outside']
    # (Có thể thêm logic cho 'close_near' ở đây)
    
    # --- Tính điểm cho phe BÁN (SHORT) ---
    if 'cross_outside' in cfg['score_levels'] and last_close > last_upper_band:
        short_score = cfg['score_levels']['cross_outside']
    elif 'wick_outside' in cfg['score_levels'] and last_high > last_upper_band:
        short_score = cfg['score_levels']['wick_outside']
    # (Có thể thêm logic cho 'close_near' ở đây)

    # Chuẩn hóa điểm theo trọng số
    max_possible_score = max(cfg['score_levels'].values()) if cfg['score_levels'] else 1

    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    
    return final_long_score, final_short_score