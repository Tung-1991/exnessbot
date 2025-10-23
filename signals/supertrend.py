# -*- coding: utf-8 -*-
# Tên file: signals/supertrend.py (Bản Final V7.0)
# Mục đích: Tính điểm Supertrend H1 (nội suy) dựa trên khoảng cách (chuẩn hóa ATR)
#          để cộng vào tổng điểm (Logic v7.0).

import pandas as pd
import pandas_ta as ta
from typing import Optional, Dict, Any, Tuple

# Import ATR để "chuẩn hóa" khoảng cách
from signals.atr import calculate_atr 

# --- HÀM TÍNH TOÁN SUPERTREND GỐC (Giữ nguyên từ file cũ của bạn) ---
def calculate_supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo SuperTrend sử dụng thư viện pandas_ta.
    (Hàm này giữ nguyên như file gốc của bạn)
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        return None

    # Tính toán Supertrend
    st = ta.supertrend(
        high=df['high'], 
        low=df['low'], 
        close=df['close'], 
        length=atr_period, 
        multiplier=multiplier
    )
    
    if st is None or st.empty:
        return None
        
    # Trả về cột đầu tiên (chứa giá trị của đường Supertrend)
    # File gốc của bạn đã làm đúng điều này.
    return st.iloc[:, 0] 

# --- HÀM TÍNH ĐIỂM SỐ MỚI (v7.0) ---
def get_supertrend_score(df_trend: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm Trend Bias dựa trên KHOẢNG CÁCH (đã chuẩn hóa ATR) 
    từ giá H1 đến đường Supertrend H1 (Logic Nội suy v7.0).
    
    Hàm này được gọi bởi signal_generator.py (v7.0)
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V7.0 (Từ TREND_FILTERS_CONFIG)
        cfg_section = config.get('TREND_FILTERS_CONFIG', {})
        cfg = cfg_section.get('SUPERTREND', {}) 
        
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg.get('params', {})
        max_score = cfg.get('MAX_SCORE', 15) # Lấy trọng số

        # Đọc các tham số của Supertrend
        st_atr_period = params.get('atr_period', 10)
        st_multiplier = params.get('multiplier', 3.0)
        
        # Đọc tham số cho logic nội suy (lấy ATR_PERIOD từ config chung)
        atr_config = config.get('INDICATORS_CONFIG', {}).get('ATR', {})
        norm_atr_period = atr_config.get('PERIOD', 14) 
        full_score_dist = params.get('full_score_atr_distance', 2.0) 

        if full_score_dist == 0: full_score_dist = 2.0 # Tránh lỗi chia cho 0

        # --- 1. Tính toán các chỉ báo trên H1 ---
        st_series = calculate_supertrend(
            df_trend, 
            atr_period=st_atr_period, 
            multiplier=st_multiplier
        )
        atr_series = calculate_atr(df_trend, period=norm_atr_period) # ATR để chuẩn hóa
        
        if st_series is None or atr_series is None or \
           pd.isna(st_series.iloc[-1]) or pd.isna(atr_series.iloc[-1]) or \
           atr_series.iloc[-1] == 0: # Check ATR != 0
            return 0.0, 0.0
            
        last_st = st_series.iloc[-1]
        last_atr = atr_series.iloc[-1]
        last_close = df_trend['close'].iloc[-1]

        # --- 2. Tính khoảng cách đã chuẩn hóa (normalized distance) ---
        # distance_usd sẽ > 0 nếu giá trên ST (Long), < 0 nếu giá dưới ST (Short)
        distance_usd = last_close - last_st
        distance_in_atr = distance_usd / last_atr

        # --- 3. Logic Nội suy (Interpolation) ---
        
        # Tính toán hệ số điểm (ví dụ: 0.0 -> 1.0+)
        score_factor = abs(distance_in_atr) / full_score_dist
        
        if distance_in_atr > 0:
            # Giá Nằm trên Supertrend (Xu hướng TĂNG)
            long_score = max_score * score_factor
        
        elif distance_in_atr < 0:
            # Giá Nằm dưới Supertrend (Xu hướng GIẢM)
            short_score = max_score * score_factor

        # Áp trần điểm (nếu khoảng cách > full_score_dist ATRs)
        long_score = min(long_score, max_score)
        short_score = min(short_score, max_score)

    except Exception as e:
        # print(f"Lỗi khi tính điểm Supertrend (v7.0): {e}")
        pass

    return long_score, short_score