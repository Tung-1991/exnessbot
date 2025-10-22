# Tên file: signals/supertrend.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Phân tích Supertrend trên khung H1 (Trend Timeframe)
#          để cung cấp điểm thưởng XU HƯỚNG xác nhận.

import pandas as pd
import pandas_ta as ta
from typing import Optional, Dict, Any, Tuple

# --- HÀM TÍNH TOÁN SUPERTREND GỐC ---
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
    return st.iloc[:, 0]

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V6.0) ---
def get_supertrend_score(df_trend: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm Trend Bias dựa trên vị trí của giá so với Supertrend
    trên khung thời gian XU HƯỚNG (ví dụ: H1).
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0 (TREND_FILTERS_CONFIG)
        cfg = config['TREND_FILTERS_CONFIG']['SUPERTREND']
        if not cfg.get('enabled', False):
            return 0.0, 0.0
            
        params = cfg['params']
        score = cfg['max_score'] # Lấy điểm từ max_score

        # Tính toán Supertrend trên dataframe H1
        st_series = calculate_supertrend(
            df_trend, 
            atr_period=params['atr_period'], 
            multiplier=params['multiplier']
        )
        
        if st_series is None or pd.isna(st_series.iloc[-1]):
            return 0.0, 0.0
            
        last_st_value = st_series.iloc[-1]
        last_close = df_trend['close'].iloc[-1]

        # --- Logic tính điểm ---
        if last_close > last_st_value:
            # Giá nằm trên Supertrend -> Xu hướng TĂNG
            long_score = score
        elif last_close < last_st_value:
            # Giá nằm dưới Supertrend -> Xu hướng GIẢM
            short_score = score

    except Exception as e:
        # print(f"Lỗi khi tính điểm Supertrend: {e}")
        pass

    return long_score, short_score