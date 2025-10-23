# Tên file: signals/adx.py (Bản Final V7.0)
# Mục đích: Tính ADX và chấm điểm bằng logic NỘI SUY (Interpolation)
#          để lấp đầy "khoảng mù" (thay vì threshold máy móc).

import pandas as pd
from typing import Dict, Any, Tuple
try:
    import pandas_ta as ta
except ImportError:
    print("VUI LÒNG CÀI ĐẶT THƯ VIỆN PANDAS_TA: pip install pandas_ta")
    ta = None

# --- HÀM HỖ TRỢ NỘI SUY (LOGIC MỚI v7.0) ---
# (Hàm này được sao chép từ rsi.py (v7.0) để file này hoạt động độc lập)
def _calculate_interpolation(current_val: float, neutral_val: float, full_score_val: float, max_score: float) -> float:
    """
    Hàm nội suy tuyến tính để chấm điểm "linh hoạt".
    """
    try:
        distance = abs(current_val - neutral_val)
        full_distance = abs(full_score_val - neutral_val)
        
        if full_distance == 0:
            return 0.0 # Tránh lỗi chia cho 0
        
        # Chỉ tính điểm nếu giá trị vượt qua mốc trung tính
        if (current_val > neutral_val and full_score_val > neutral_val) or \
           (current_val < neutral_val and full_score_val < neutral_val):
            
            score_factor = distance / full_distance
            return min(max_score * score_factor, max_score)
        
        return 0.0
    except:
        return 0.0

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V7.0 - NỘI SUY) ---
def get_adx_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính toán ADX để đo sức mạnh xu hướng (Logic Nội suy v7.0).
    Cộng điểm (linh hoạt) nếu xu hướng mạnh và rõ ràng.
    """
    long_score, short_score = 0.0, 0.0
    
    if ta is None:
        return 0.0, 0.0

    try:
        # ĐỌC CONFIG V7.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['ADX']
        if not cfg.get('enabled', False):
            return 0.0, 0.0
            
        params = cfg['params']
        max_score = cfg['MAX_SCORE'] # Lấy trọng số
        
        # Đọc các mốc neo MỚI cho logic nội suy (thay cho 'threshold' cũ)
        levels = cfg['score_levels']
        neutral_level = levels.get('neutral_level', 20.0)
        full_score_level = levels.get('full_score_level', 40.0)

        # Sử dụng pandas_ta để tính toán ADX
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=params['period'])
        
        if adx_df is None or adx_df.empty or len(adx_df) < 1:
            return 0.0, 0.0

        # Lấy giá trị của cây nến cuối cùng
        last_adx = adx_df.iloc[-1, 0] # ADX_14
        last_dmp = adx_df.iloc[-1, 1] # +DI
        last_dmn = adx_df.iloc[-1, 2] # -DI
        
        # --- Logic tính điểm Nội suy (v7.0) ---
        
        # 1. Tính "Điểm sức mạnh" (Strength Score)
        # (Điểm này = 0 nếu ADX < 20, và = max_score nếu ADX > 40)
        trend_strength_score = _calculate_interpolation(
            last_adx, neutral_level, full_score_level, max_score
        )
        
        if trend_strength_score > 0:
            # 2. Nếu có sức mạnh, gán điểm cho phe chiếm ưu thế
            if last_dmp > last_dmn:
                # Phe Bò mạnh (xu hướng tăng)
                long_score = trend_strength_score
            elif last_dmn > last_dmp:
                # Phe Gấu mạnh (xu hướng giảm)
                short_score = trend_strength_score
        
        # Nếu ADX < neutral_level, trend_strength_score = 0,
        # không cộng điểm cho cả hai phe.

    except Exception as e:
        # print(f"Lỗi khi tính điểm ADX (v7.0): {e}")
        pass

    # Không cần áp trần vì hàm _calculate_interpolation đã xử lý
    return long_score, short_score