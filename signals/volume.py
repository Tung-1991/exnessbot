# Tên file: signals/volume.py (Bản Final V7.0)
# Mục đích: Tính điểm Volume (xác nhận) bằng logic BẬC THANG
#          và gán điểm ĐÚNG HƯỚNG nến (Long/Short).

import pandas as pd
from typing import Dict, Any, Tuple

def get_volume_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm cho Volume (Logic Bậc thang v7.0).
    - Volume cao trên NẾN TĂNG -> + Điểm Long
    - Volume cao trên NẾN GIẢM -> + Điểm Short
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V7.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['VOLUME']
        if not cfg.get('enabled', False) or 'volume' not in df.columns:
            return 0.0, 0.0

        params = cfg['params']
        levels = cfg['score_levels']
        
        # Đọc các ngưỡng và điểm số cho logic bậc thang
        spike_multiplier = levels.get('spike_volume_multiplier', 2.5)
        spike_score = levels.get('spike_score', 10) # Điểm cao nhất
        high_multiplier = levels.get('high_volume_multiplier', 1.5)
        high_score = levels.get('high_score', 5) # Điểm trung bình

        # 1. Tính toán Volume Trung bình (Volume MA)
        volume_ma = df['volume'].rolling(window=params['ma_period']).mean()
        
        if volume_ma.empty or pd.isna(volume_ma.iloc[-1]):
            return 0.0, 0.0

        # 2. Lấy các giá trị cuối cùng
        last_volume = df['volume'].iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        
        # 3. Logic Bậc thang (v7.0)
        score = 0.0
        if last_volume > (avg_volume * spike_multiplier):
            score = spike_score
        elif last_volume > (avg_volume * high_multiplier):
            score = high_score
            
        # 4. Gán điểm ĐÚNG HƯỚNG NẾN (Sửa lỗi logic v6.0)
        if score > 0:
            last_candle = df.iloc[-1]
            if last_candle['close'] > last_candle['open']:
                # Nến TĂNG (Bullish candle)
                long_score = score
            elif last_candle['close'] < last_candle['open']:
                # Nến GIẢM (Bearish candle)
                short_score = score

    except Exception as e:
        # print(f"Lỗi khi tính điểm Volume (v7.0): {e}")
        pass

    # Áp dụng trần điểm TỔNG (Weighting)
    max_score_cap = cfg.get('MAX_SCORE', 10) # Lấy MAX_SCORE (ví dụ 10)
    return min(long_score, max_score_cap), min(short_score, max_score_cap)