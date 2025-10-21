# -*- coding: utf-8 -*-
# signals/supertrend.py (v4.3 - Sửa lỗi KeyError)

import pandas as pd
from typing import Optional, Dict, Any, Tuple
import pandas_ta as ta

def calculate_supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo SuperTrend sử dụng thư viện pandas_ta.
    Đã sửa lỗi KeyError bằng cách lấy cột đầu tiên của kết quả trả về.
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        return None

    # Sử dụng thư viện pandas_ta, rất mạnh mẽ và đã được kiểm chứng
    st = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=atr_period, multiplier=multiplier)
    
    if st is None or st.empty:
        return None
        
    # SỬA LỖI Ở ĐÂY:
    # Thay vì truy cập bằng tên cột được hardcode, chúng ta lấy cột đầu tiên (iloc[:, 0]).
    # Cột đầu tiên luôn là đường Supertrend chính.
    # Điều này giúp code chống lại các thay đổi về cách đặt tên cột của thư viện trong tương lai.
    return st.iloc[:, 0]


def get_supertrend_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên vị trí của giá so với Supertrend.
    """
    cfg = config['SCORING_CONFIG']['SUPERTREND']
    if not cfg['enabled']:
        return 0.0, 0.0

    st_series = calculate_supertrend(
        df, 
        atr_period=cfg['params']['atr_period'], 
        multiplier=cfg['params']['multiplier']
    )
    # Thêm kiểm tra giá trị NaN để tránh lỗi
    if st_series is None or st_series.empty or pd.isna(st_series.iloc[-1]):
        return 0.0, 0.0

    last_close = df['close'].iloc[-1]
    last_st = st_series.iloc[-1]
    
    long_score, short_score = 0.0, 0.0
    
    score_on_align = cfg['score_levels'].get('aligned_with_trend', 0)

    if last_close > last_st:
        long_score = score_on_align
    elif last_close < last_st:
        short_score = score_on_align
        
    max_possible_score = score_on_align
    
    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0

    return final_long_score, final_short_score