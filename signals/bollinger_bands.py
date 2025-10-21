# -*- coding: utf-8 -*-
# signals/bollinger_bands.py (v5.1 - Sửa lỗi NameError)

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
    Tính điểm thô cho LONG và SHORT dựa trên 5 cấp độ tương tác với Bollinger Bands.
    Hàm này đã được viết lại hoàn toàn để đọc cấu trúc range score từ config.
    """
    try:
        cfg = config['RAW_SCORE_CONFIG']['BOLLINGER_BANDS']
    except KeyError:
        return 0.0, 0.0 # Trả về 0 nếu config không đúng cấu trúc

    if not cfg.get('enabled', False):
        return 0.0, 0.0

    bands = calculate_bollinger_bands(
        df, 
        period=cfg['params']['period'], 
        std_dev=cfg['params']['std_dev']
    )
    if bands is None:
        return 0.0, 0.0

    upper_band, middle_band, lower_band = bands
    
    # Lấy dữ liệu của cây nến gần nhất
    last_candle = df.iloc[-1]
    last_close = last_candle['close']
    last_low = last_candle['low']
    last_high = last_candle['high']
    last_open = last_candle['open']
    
    # Kiểm tra để đảm bảo có đủ dữ liệu
    # === DÒNG SỬA LỖI Ở ĐÂY ===
    if pd.isna(lower_band.iloc[-1]) or pd.isna(upper_band.iloc[-1]):
        return 0.0, 0.0
        
    last_lower_band_val = lower_band.iloc[-1]
    last_upper_band_val = upper_band.iloc[-1]
    last_middle_band_val = middle_band.iloc[-1]

    long_score, short_score = 0.0, 0.0
    
    # Tạo một dictionary để dễ dàng lấy điểm từ config
    score_map = {level['level']: level['score'] for level in cfg.get('score_levels', [])}

    # --- LOGIC CHẤM ĐIỂM CHO PHE MUA (LONG) ---
    # Duyệt từ tín hiệu mạnh nhất đến yếu nhất, nếu thỏa mãn thì lấy điểm và dừng lại
    if 'cross_outside_full' in score_map and last_close < last_lower_band_val and last_open < last_lower_band_val:
        long_score = score_map['cross_outside_full']
    elif 'cross_outside_half_body' in score_map and last_close < last_lower_band_val and (last_open + last_close)/2 < last_lower_band_val:
        long_score = score_map['cross_outside_half_body']
    elif 'wick_outside' in score_map and last_low < last_lower_band_val:
        long_score = score_map['wick_outside']
    elif 'touch_band' in score_map and last_low <= last_lower_band_val and last_close > last_lower_band_val:
        long_score = score_map['touch_band']
    elif 'close_near' in score_map:
        # Tính khoảng cách tương đối để xác định "gần"
        band_width = last_upper_band_val - last_lower_band_val
        if band_width > 0 and (last_close - last_lower_band_val) / band_width < 0.1: # Gần 10%
             long_score = score_map['close_near']

    # --- LOGIC CHẤM ĐIỂM CHO PHE BÁN (SHORT) ---
    if 'cross_outside_full' in score_map and last_close > last_upper_band_val and last_open > last_upper_band_val:
        short_score = score_map['cross_outside_full']
    elif 'cross_outside_half_body' in score_map and last_close > last_upper_band_val and (last_open + last_close)/2 > last_upper_band_val:
        short_score = score_map['cross_outside_half_body']
    elif 'wick_outside' in score_map and last_high > last_upper_band_val:
        short_score = score_map['wick_outside']
    elif 'touch_band' in score_map and last_high >= last_upper_band_val and last_close < last_upper_band_val:
        short_score = score_map['touch_band']
    elif 'close_near' in score_map:
        band_width = last_upper_band_val - last_lower_band_val
        if band_width > 0 and (last_upper_band_val - last_close) / band_width < 0.1: # Gần 10%
            short_score = score_map['close_near']
            
    # Chuẩn hóa điểm theo trọng số (weight)
    max_possible_score = max(level['score'] for level in cfg.get('score_levels', [])) if cfg.get('score_levels') else 1
    
    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0

    return final_long_score, final_short_score