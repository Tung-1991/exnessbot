# Tên file: signals/volume.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Tính toán và chấm điểm cho Volume,
#          dùng làm tín hiệu xác nhận cho Breakout hoặc Mô hình Nến.

import pandas as pd
from typing import Dict, Any, Tuple

def get_volume_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm cho Volume.
    Chỉ cộng điểm nếu volume của cây nến cuối cùng đủ lớn (vượt qua MA * multiplier).
    
    Lưu ý: Logic này giả định rằng cây nến cuối cùng (df.iloc[-1]) 
    CHÍNH LÀ cây nến tín hiệu (ví dụ: nến Breakout, nến Engulfing).
    """
    # Mặc định là 0. Volume chỉ cộng điểm xác nhận, không bao giờ tự tạo tín hiệu.
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['VOLUME']
        if not cfg.get('enabled', False) or 'volume' not in df.columns:
            return 0.0, 0.0

        params = cfg['params']
        
        # 1. Tính toán Volume Trung bình (Volume MA)
        volume_ma = df['volume'].rolling(window=params['ma_period']).mean()
        
        if volume_ma.empty or pd.isna(volume_ma.iloc[-1]):
            return 0.0, 0.0

        # 2. Lấy các giá trị cuối cùng
        last_volume = df['volume'].iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        
        # 3. So sánh với ngưỡng
        threshold_volume = avg_volume * params['multiplier']
        
        if last_volume > threshold_volume:
            # Nếu volume lớn, nó xác nhận cho BẤT KỲ tín hiệu nào đang hình thành
            # (cả Long và Short). 
            # signal_generator sẽ quyết định điểm này được cộng vào đâu.
            # Để đơn giản, chúng ta trả về điểm cho cả hai.
            score = cfg['max_score'] # Lấy điểm từ max_score
            long_score = score
            short_score = score

    except Exception as e:
        # print(f"Lỗi khi tính điểm Volume: {e}")
        pass

    # Không cần áp trần
    return long_score, short_score