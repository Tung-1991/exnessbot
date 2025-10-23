# -*- coding: utf-8 -*-
# Tên file: signals/ema.py (Bản Final V7.0)
# Mục đích: Tính điểm EMA H1 (nội suy) dựa trên khoảng cách (chuẩn hóa ATR)
#          để cộng vào tổng điểm (Logic v7.0).

import pandas as pd
from typing import Optional, Dict, Any, Tuple

# Import ATR để "chuẩn hóa" khoảng cách
from signals.atr import calculate_atr 

# --- HÀM TÍNH EMA GỐC (Giữ nguyên) ---
def calculate_ema(df: pd.DataFrame, period: int) -> Optional[pd.Series]:
    """
    Tính toán một đường EMA duy nhất.
    """
    if 'close' not in df.columns:
        return None
    
    ema = df['close'].ewm(span=period, adjust=False).mean()
    return ema

# --- HÀM TÍNH ĐIỂM SỐ MỚI (v7.0) ---
def get_ema_score(df_trend: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm Trend Bias dựa trên KHOẢNG CÁCH (đã chuẩn hóa ATR) 
    từ giá H1 đến đường EMA H1 (Logic Nội suy v7.0).
    
    Hàm này được gọi bởi signal_generator.py (v7.0)
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V7.0 (Từ TREND_FILTERS_CONFIG)
        # (signal_generator.py (v7.0) gọi config từ 'EMA')
        cfg_section = config.get('TREND_FILTERS_CONFIG', {})
        cfg = cfg_section.get('EMA', {}) 
        
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg.get('params', {})
        # Lấy MAX_SCORE (trọng số)
        max_score = cfg.get('MAX_SCORE', 15) 

        # Đọc các tham số mới cho logic nội suy
        ema_period = params.get('period', 200)
        atr_period = params.get('atr_period', 14) # Cần 1 chu kỳ ATR
        # Khoảng cách (tính bằng ATR) để đạt điểm tối đa
        full_score_dist = params.get('full_score_atr_distance', 2.0) 

        if full_score_dist == 0: full_score_dist = 2.0 # Tránh lỗi chia cho 0

        # --- 1. Tính toán các chỉ báo trên H1 ---
        ema_series = calculate_ema(df_trend, period=ema_period)
        atr_series = calculate_atr(df_trend, period=atr_period)
        
        if ema_series is None or atr_series is None or \
           pd.isna(ema_series.iloc[-1]) or pd.isna(atr_series.iloc[-1]) or \
           atr_series.iloc[-1] == 0: # Check ATR != 0
            return 0.0, 0.0
            
        last_ema = ema_series.iloc[-1]
        last_atr = atr_series.iloc[-1]
        last_close = df_trend['close'].iloc[-1]

        # --- 2. Tính khoảng cách đã chuẩn hóa (normalized distance) ---
        distance_usd = last_close - last_ema
        distance_in_atr = distance_usd / last_atr

        # --- 3. Logic Nội suy (Interpolation) ---
        
        # Tính toán hệ số điểm (ví dụ: 0.0 -> 1.0+)
        # (Hệ số này sẽ được nhân với max_score)
        score_factor = abs(distance_in_atr) / full_score_dist
        
        if distance_in_atr > 0:
            # Giá Nằm trên EMA (Xu hướng TĂNG)
            long_score = max_score * score_factor
        
        elif distance_in_atr < 0:
            # Giá Nằm dưới EMA (Xu hướng GIẢM)
            short_score = max_score * score_factor

        # Áp trần điểm (nếu khoảng cách > full_score_dist ATRs)
        long_score = min(long_score, max_score)
        short_score = min(short_score, max_score)

    except Exception as e:
        # print(f"Lỗi khi tính điểm EMA (v7.0): {e}")
        pass

    return long_score, short_score