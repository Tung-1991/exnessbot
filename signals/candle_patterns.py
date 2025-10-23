# Tên file: signals/candle_patterns.py (Bản Final V7.0)
# Mục đích: Phân tích "trừu tượng" MỌI cây nến dựa trên 2 yếu tố:
#          1. Momentum (Thân nến) và 2. Rejection (Râu nến).
#          Sử dụng NỘI SUY và CỘNG DỒN, loại bỏ logic mẫu nến máy móc.

import pandas as pd
from typing import Dict, Any, Tuple

# --- HÀM HỖ TRỢ TÍNH TỶ LỆ NẾN (Giữ nguyên từ file cũ v6.0) ---
def _get_candle_ratios(candle: pd.Series) -> Tuple[float, float, float, float]:
    """
    Tính toán các tỷ lệ của một cây nến.
    Trả về (tỷ lệ thân, tỷ lệ râu trên, tỷ lệ râu dưới, tổng râu) so với tổng chiều dài nến.
    (Hàm này giữ nguyên từ file gốc v6.0 của bạn)
    """
    body_size = abs(candle['close'] - candle['open'])
    candle_range = candle['high'] - candle['low']
    
    if candle_range == 0:
        return 0, 0, 0, 0 # Tránh lỗi chia cho 0

    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']

    body_ratio = body_size / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    wick_ratio = (upper_wick + lower_wick) / candle_range
    
    return body_ratio, upper_wick_ratio, lower_wick_ratio, wick_ratio

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

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V7.0 - "TRỪU TƯỢNG") ---
def get_candle_pattern_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Phân tích cây nến M15 cuối cùng bằng logic "trừu tượng" (v7.0).
    Tính điểm CỘNG DỒN từ (Momentum + Rejection).
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V7.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['CANDLE_PATTERNS']
        if not cfg.get('enabled', False) or len(df) < 1:
            return 0.0, 0.0
            
        # Đọc các mức điểm MỚI cho logic v7.0
        levels = cfg['score_levels']
        
        # Cấu hình cho Logic 1: Momentum (Thân nến)
        momentum_max_score = levels.get('momentum_max_score', 15)
        momentum_neutral_ratio = levels.get('momentum_neutral_ratio', 0.1) # Thân nến 10% (Doji) = 0đ
        momentum_full_ratio = levels.get('momentum_full_ratio', 0.9) # Thân nến 90% (Marubozu) = max điểm

        # Cấu hình cho Logic 2: Rejection (Râu nến)
        rejection_max_score = levels.get('rejection_max_score', 10)
        rejection_neutral_ratio = levels.get('rejection_neutral_ratio', 0.1) # Râu nến 10% = 0đ
        rejection_full_ratio = levels.get('rejection_full_ratio', 0.7) # Râu nến 70% (Pin bar) = max điểm

        # Lấy cây nến cuối cùng
        last_candle = df.iloc[-1]

        # Lấy các tỷ lệ của nến cuối cùng
        body_r, up_wick_r, low_wick_r, _ = _get_candle_ratios(last_candle)
        
        # --- Logic 1: Phân tích Momentum (Thân nến) ---
        momentum_score = _calculate_interpolation(
            body_r, 
            momentum_neutral_ratio, 
            momentum_full_ratio, 
            momentum_max_score
        )
        
        if momentum_score > 0:
            if last_candle['close'] > last_candle['open']:
                long_score += momentum_score # <-- Dùng CỘNG DỒN
            elif last_candle['close'] < last_candle['open']:
                short_score += momentum_score # <-- Dùng CỘNG DỒN

        # --- Logic 2: Phân tích Rejection (Râu nến) ---
        
        # 2a. Râu dưới (Tín hiệu Long)
        rejection_long_score = _calculate_interpolation(
            low_wick_r, 
            rejection_neutral_ratio, 
            rejection_full_ratio, 
            rejection_max_score
        )
        long_score += rejection_long_score # <-- Dùng CỘNG DỒN
        
        # 2b. Râu trên (Tín hiệu Short)
        rejection_short_score = _calculate_interpolation(
            up_wick_r, 
            rejection_neutral_ratio, 
            rejection_full_ratio, 
            rejection_max_score
        )
        short_score += rejection_short_score # <-- Dùng CỘNG DỒN

    except Exception as e:
        # print(f"Lỗi khi tính điểm mô hình nến (v7.0): {e}")
        pass

    # Áp dụng trần điểm TỔNG (Weighting)
    max_score_cap = cfg.get('MAX_SCORE', 20)
    return min(long_score, max_score_cap), min(short_score, max_score_cap)