# Tên file: signals/adx.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Tính toán ADX để đo sức mạnh xu hướng.
#          Cộng điểm nếu xu hướng mạnh và rõ ràng.

import pandas as pd
from typing import Dict, Any, Tuple

try:
    # pandas_ta là thư viện bên ngoài, nhưng nó là cách
    # tiêu chuẩn và chính xác nhất để tính ADX.
    import pandas_ta as ta
except ImportError:
    print("VUI LÒNG CÀI ĐẶT THƯ VIỆN PANDAS_TA: pip install pandas_ta")
    ta = None

def get_adx_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính toán ADX để đo sức mạnh xu hướng.
    Chỉ cộng điểm nếu xu hướng đang mạnh (ADX > ngưỡng) và rõ ràng (+DI > -DI hoặc ngược lại).
    """
    long_score, short_score = 0.0, 0.0
    
    # Kiểm tra xem thư viện có tồn tại không
    if ta is None:
        print("Bỏ qua tính điểm ADX do thiếu thư viện pandas_ta.")
        return 0.0, 0.0

    try:
        # Lấy config
        cfg = config['ENTRY_SIGNALS_CONFIG']['ADX']
        if not cfg.get('enabled', False):
            return 0.0, 0.0
            
        period = cfg['params']['period']
        adx_threshold = cfg['threshold']
        score = cfg['max_score']

        # Sử dụng pandas_ta để tính toán ADX
        # Nó sẽ trả về 3 cột: ADX_14, DMP_14 (+DI), DMN_14 (-DI)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=period)
        
        if adx_df is None or adx_df.empty or len(adx_df) < 1:
            return 0.0, 0.0

        # Lấy giá trị của cây nến cuối cùng
        last_adx = adx_df.iloc[-1, 0] # ADX_14
        last_dmp = adx_df.iloc[-1, 1] # +DI
        last_dmn = adx_df.iloc[-1, 2] # -DI
        
        # --- Logic tính điểm ---
        
        # 1. Kiểm tra xem xu hướng có ĐỦ MẠNH không
        if last_adx > adx_threshold:
            # 2. Nếu đủ mạnh, kiểm tra xem phe nào đang chiếm ưu thế
            if last_dmp > last_dmn:
                # Phe Bò mạnh (xu hướng tăng)
                long_score = score
            elif last_dmn > last_dmp:
                # Phe Gấu mạnh (xu hướng giảm)
                short_score = score
        
        # Nếu ADX < ngưỡng, thị trường không có xu hướng,
        # không cộng điểm cho cả hai phe (điểm = 0).

    except Exception as e:
        # print(f"Lỗi khi tính điểm ADX: {e}")
        pass

    return long_score, short_score