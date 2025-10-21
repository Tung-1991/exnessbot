# -*- coding: utf-8 -*-
# signals/rsi.py (v5.2 - Sửa lỗi KeyError triệt để và xử lý đa logic)

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo Relative Strength Index (RSI).
    """
    if 'close' not in df.columns:
        return None

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    # Tránh lỗi chia cho 0
    rs = gain / loss
    rs = rs.replace([np.inf, -np.inf], 100).fillna(100)

    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_rsi_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT.
    Hàm được nâng cấp để xử lý nhiều loại 'score_levels' một cách an toàn.
    """
    try:
        cfg = config['RAW_SCORE_CONFIG']['RSI']
    except KeyError:
        return 0.0, 0.0

    if not cfg.get('enabled', False) or len(df) < 2:
        return 0.0, 0.0

    rsi_series = calculate_rsi(df, period=cfg['params']['period'])
    if rsi_series is None or rsi_series.empty or pd.isna(rsi_series.iloc[-1]):
        return 0.0, 0.0

    last_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-2]
    
    long_score, short_score = 0.0, 0.0
    
    # --- PHÂN LOẠI VÀ XỬ LÝ ĐA LOGIC ---
    
    score_levels = cfg.get('score_levels', [])
    
    # 1. Xử lý các cấp độ dựa trên ngưỡng (threshold)
    threshold_levels = [level for level in score_levels if 'threshold' in level]
    if threshold_levels:
        long_thresholds = sorted(threshold_levels, key=lambda x: x['threshold'])
        short_thresholds = sorted(threshold_levels, key=lambda x: x['threshold'], reverse=True)

        for level in long_thresholds:
            if last_rsi < level['threshold']:
                long_score = max(long_score, level['score']) # Luôn lấy điểm cao nhất
        
        for level in short_thresholds:
            if last_rsi > (100 - level['threshold']):
                short_score = max(short_score, level['score']) # Luôn lấy điểm cao nhất

    # 2. Xử lý các cấp độ dựa trên sự kiện (level)
    level_map = {level['level']: level['score'] for level in score_levels if 'level' in level}
    if 'enter_zone' in level_map:
        # Logic cho phe LONG (vừa đi vào vùng quá bán)
        if prev_rsi >= 30 and last_rsi < 30:
            long_score = max(long_score, level_map['enter_zone'])
            
        # Logic cho phe SHORT (vừa đi vào vùng quá mua)
        if prev_rsi <= 70 and last_rsi > 70:
            short_score = max(short_score, level_map['enter_zone'])
            
    # (Có thể thêm các logic cho "divergence" ở đây trong tương lai)

    # --- CHUẨN HÓA ĐIỂM ---
    all_scores = [level['score'] for level in score_levels]
    max_possible_score = max(all_scores) if all_scores else 1

    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0

    return final_long_score, final_short_score