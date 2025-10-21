# -*- coding: utf-8 -*-
# signals/supertrend.py (v5.0 - Logic Bậc Thang 5 Cấp)

import pandas as pd
from typing import Optional, Dict, Any, Tuple
import pandas_ta as ta

# Import hàm tính ATR để đo khoảng cách
from signals.atr import calculate_atr

def calculate_supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo SuperTrend sử dụng thư viện pandas_ta.
    Hàm này không thay đổi.
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        return None

    st = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=atr_period, multiplier=multiplier)
    
    if st is None or st.empty:
        return None
        
    # Lấy cột đầu tiên (đường Supertrend chính) một cách an toàn
    return st.iloc[:, 0]


def get_supertrend_adjustment_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Tính điểm thưởng/phạt dựa trên vị trí của giá so với đường Supertrend.
    Sử dụng cơ chế bậc thang 5 cấp dựa trên khoảng cách ATR.
    """
    try:
        cfg = config['ADJUSTMENT_SCORE_CONFIG']['SUPERTREND_FILTER']
        atr_cfg = config['INDICATORS_CONFIG']['ATR']
    except KeyError:
        return 0.0

    if not cfg.get('enabled', False):
        return 0.0

    # Tính toán Supertrend
    st_series = calculate_supertrend(
        df, 
        atr_period=cfg['params']['atr_period'], 
        multiplier=cfg['params']['multiplier']
    )
    if st_series is None or pd.isna(st_series.iloc[-1]):
        return 0.0
        
    # Tính toán ATR
    atr_series = calculate_atr(df, period=atr_cfg['PERIOD'])
    if atr_series is None or pd.isna(atr_series.iloc[-1]) or atr_series.iloc[-1] == 0:
        return 0.0

    last_close = df['close'].iloc[-1]
    last_st = st_series.iloc[-1]
    last_atr = atr_series.iloc[-1]

    # Tính khoảng cách từ giá đến Supertrend bằng đơn vị ATR
    # Dương: giá trên ST (thuận xu hướng LONG)
    # Âm: giá dưới ST (ngược xu hướng LONG)
    distance_in_atr = (last_close - last_st) / last_atr
    
    final_score = 0
    
    # Sắp xếp các bậc thang để duyệt từ điều kiện chặt nhất
    tiers = sorted(cfg.get('score_tiers', []), key=lambda x: x['threshold_atr'], reverse=True)

    # Duyệt và tìm bậc thang phù hợp
    # Logic này giống hệt với EMA, chỉ khác là nó dựa trên đường Supertrend
    for tier in tiers:
        # Giả định threshold_atr trong config là cho phe LONG
        if distance_in_atr >= tier['threshold_atr']:
            final_score = tier['score']
            break
            
    return final_score # Trả về điểm thô (+15, -10, 0...)