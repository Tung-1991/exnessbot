# -*- coding: utf-8 -*-
# signals/macd.py (v5.0 - Logic Range Score 5 Cấp Độ)

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple

def calculate_macd(df: pd.DataFrame, fast_ema: int = 12, slow_ema: int = 26, signal_sma: int = 9) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    """
    Tính toán đường MACD, đường Signal, và Histogram.
    Hàm này được nâng cấp để trả về cả Histogram để phân tích.
    """
    if 'close' not in df.columns:
        return None

    ema_fast = df['close'].ewm(span=fast_ema, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_ema, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_sma, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def get_macd_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên 5 cấp độ chất lượng của tín hiệu MACD.
    """
    try:
        cfg = config['RAW_SCORE_CONFIG']['MACD']
    except KeyError:
        return 0.0, 0.0

    if not cfg.get('enabled', False) or len(df) < 3: # Cần ít nhất 3 nến để so sánh
        return 0.0, 0.0

    lines = calculate_macd(
        df,
        fast_ema=cfg['params']['fast_ema'],
        slow_ema=cfg['params']['slow_ema'],
        signal_sma=cfg['params']['signal_sma']
    )
    
    if lines is None:
        return 0.0, 0.0

    macd_line, signal_line, histogram = lines
    long_score, short_score = 0.0, 0.0
    
    # Lấy dữ liệu của 3 cây nến gần nhất để phân tích
    prev_macd, last_macd = macd_line.iloc[-2], macd_line.iloc[-1]
    prev_signal, last_signal = signal_line.iloc[-2], signal_line.iloc[-1]
    prev_hist, last_hist = histogram.iloc[-2], histogram.iloc[-1]
    
    score_map = {level['level']: level['score'] for level in cfg.get('score_levels', [])}

    # --- LOGIC CHẤM ĐIỂM CHO PHE MUA (LONG) ---
    is_bullish_crossover = prev_hist < 0 and last_hist > 0
    
    if is_bullish_crossover:
        # Cấp 1: Cú cắt bùng nổ
        if 'explosive_crossover' in score_map and last_hist > abs(prev_hist) * 1.5:
            long_score = score_map['explosive_crossover']
        # Cấp 2: Cú cắt mạnh
        elif 'strong_crossover' in score_map and (last_macd > prev_macd) and (last_signal > prev_signal):
            long_score = score_map['strong_crossover']
        # Cấp 3: Cú cắt tiêu chuẩn
        elif 'standard_crossover' in score_map:
            long_score = score_map['standard_crossover']
    # Cấp 5: Sắp giao cắt
    elif 'about_to_cross' in score_map and prev_hist < 0 and last_hist < 0 and last_hist > prev_hist:
         long_score = score_map['about_to_cross']


    # --- LOGIC CHẤM ĐIỂM CHO PHE BÁN (SHORT) ---
    is_bearish_crossover = prev_hist > 0 and last_hist < 0

    if is_bearish_crossover:
        # Cấp 1: Cú cắt bùng nổ
        if 'explosive_crossover' in score_map and abs(last_hist) > prev_hist * 1.5:
            short_score = score_map['explosive_crossover']
        # Cấp 2: Cú cắt mạnh
        elif 'strong_crossover' in score_map and (last_macd < prev_macd) and (last_signal < prev_signal):
            short_score = score_map['strong_crossover']
        # Cấp 3: Cú cắt tiêu chuẩn
        elif 'standard_crossover' in score_map:
            short_score = score_map['standard_crossover']
    # Cấp 5: Sắp giao cắt
    elif 'about_to_cross' in score_map and prev_hist > 0 and last_hist > 0 and last_hist < prev_hist:
         short_score = score_map['about_to_cross']

    # (Logic cho 'noisy_crossover' có thể phức tạp hơn, tạm thời dùng các logic trên)

    # Chuẩn hóa điểm theo trọng số (weight)
    max_possible_score = max(level['score'] for level in cfg.get('score_levels', [])) if cfg.get('score_levels') else 1

    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0

    return final_long_score, final_short_score