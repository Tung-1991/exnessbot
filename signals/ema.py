# -*- coding: utf-8 -*-
# signals/ema.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Phân tích EMA 200 trên khung H1 (Trend Timeframe)
#          để cung cấp điểm thưởng XU HƯỚNG xác nhận.

import pandas as pd
from typing import Optional, Dict, Any, Tuple

def calculate_ema(df: pd.DataFrame, period: int) -> Optional[pd.Series]:
    """
    Tính toán một đường EMA duy nhất.
    """
    if 'close' not in df.columns:
        return None
    
    ema = df['close'].ewm(span=period, adjust=False).mean()
    return ema

def get_ema_trend_score(df_trend: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm Trend Bias dựa trên vị trí của giá so với EMA 200
    trên khung thời gian XU HƯỚNG (ví dụ: H1).
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0 (TREND_FILTERS_CONFIG)
        cfg = config['TREND_FILTERS_CONFIG']['EMA_TREND']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        score = cfg['max_score'] # Lấy điểm từ max_score

        # Tính toán EMA 200 trên dataframe H1
        ema_series = calculate_ema(df_trend, period=params['period'])
        
        if ema_series is None or pd.isna(ema_series.iloc[-1]):
            return 0.0, 0.0
            
        last_ema_value = ema_series.iloc[-1]
        last_close = df_trend['close'].iloc[-1]

        # --- Logic tính điểm ---
        if last_close > last_ema_value:
            # Giá nằm trên EMA 200 -> Xu hướng TĂNG
            long_score = score
        elif last_close < last_ema_value:
            # Giá nằm dưới EMA 200 -> Xu hướng GIẢM
            short_score = score

    except Exception as e:
        # print(f"Lỗi khi tính điểm EMA Trend: {e}")
        pass

    return long_score, short_score