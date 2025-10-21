# -*- coding: utf-8 -*-
# signals/volume.py (v5.0 - Logic Bậc Thang 5 Cấp)

import pandas as pd
from typing import Optional, Dict, Any

def get_volume_adjustment_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Tính điểm thưởng/phạt dựa trên sức mạnh của volume.
    Sử dụng cơ chế bậc thang 5 cấp dựa trên tỷ lệ so với volume trung bình.
    """
    try:
        cfg = config['ADJUSTMENT_SCORE_CONFIG']['VOLUME_FILTER']
    except KeyError:
        return 0.0

    if not cfg.get('enabled', False) or 'volume' not in df.columns:
        return 0.0

    # Tính toán volume trung bình
    ma_period = cfg['params']['ma_period']
    if len(df) < ma_period:
        return 0.0
        
    volume_ma = df['volume'].rolling(window=ma_period).mean()
    if pd.isna(volume_ma.iloc[-1]) or volume_ma.iloc[-1] == 0:
        return 0.0

    last_volume = df['volume'].iloc[-1]
    avg_volume = volume_ma.iloc[-1]
    
    # Tính tỷ lệ để so sánh
    ratio = last_volume / avg_volume

    final_score = 0
    
    # Sắp xếp các bậc thang theo ngưỡng tăng dần
    tiers = sorted(cfg.get('score_tiers', []), key=lambda x: x['threshold_ratio'])

    # Duyệt từ trên xuống, tìm bậc thang phù hợp đầu tiên
    for tier in tiers:
        if ratio < tier['threshold_ratio']:
            final_score = tier['score']
            break
            
    return final_score # Trả về điểm thô (+15, -10, 0...)