# Tên file: signals/candle_patterns.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Phân tích các cây nến M15 cuối cùng để tìm các mô hình nến
#          và trả về điểm số dựa trên 2 cấp độ (mạnh/trung bình) từ config.

import pandas as pd
from typing import Dict, Any, Tuple

# --- CÁC HÀM HỖ TRỢ ĐỊNH NGHĨA NẾN (HELPER FUNCTIONS) ---

def _is_bullish_engulfing(prev: pd.Series, last: pd.Series) -> bool:
    """Kiểm tra mô hình Bullish Engulfing (Nhấn chìm Tăng) tiêu chuẩn."""
    # Nến trước là nến Giảm, nến sau là nến Tăng
    if (prev['close'] < prev['open']) and (last['close'] > last['open']):
        # Nến sau "nhấn chìm" hoàn toàn thân nến trước
        if last['close'] > prev['open'] and last['open'] < prev['close']:
            return True
    return False

def _is_bearish_engulfing(prev: pd.Series, last: pd.Series) -> bool:
    """Kiểm tra mô hình Bearish Engulfing (Nhấn chìm Giảm) tiêu chuẩn."""
    # Nến trước là nến Tăng, nến sau là nến Giảm
    if (prev['close'] > prev['open']) and (last['close'] < last['open']):
        # Nến sau "nhấn chìm" hoàn toàn thân nến trước
        if last['close'] < prev['open'] and last['open'] > prev['close']:
            return True
    return False

def _get_candle_ratios(candle: pd.Series) -> Tuple[float, float, float, float]:
    """
    Tính toán các tỷ lệ của một cây nến để xác định Pin Bar / Marubozu.
    Trả về (tỷ lệ thân, tỷ lệ râu trên, tỷ lệ râu dưới, tổng râu) so với tổng chiều dài nến.
    """
    body_size = abs(candle['close'] - candle['open'])
    candle_range = candle['high'] - candle['low']
    
    if candle_range == 0:
        return 0, 0, 0, 0 # Tránh lỗi chia cho 0 (ví dụ nến Doji 4 giá)

    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']
    wick_size = upper_wick + lower_wick

    body_ratio = body_size / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    wick_ratio = wick_size / candle_range
    
    return body_ratio, upper_wick_ratio, lower_wick_ratio, wick_ratio

def _is_marubozu(candle: pd.Series, body_ratio: float, wick_ratio: float) -> int:
    """
    Kiểm tra nến Marubozu (nến cường lực).
    Tiêu chí: Thân nến chiếm > 90% toàn bộ nến.
    Trả về 1 cho Bullish, -1 cho Bearish, 0 cho không có.
    """
    if body_ratio >= 0.90 and wick_ratio <= 0.10:
        if candle['close'] > candle['open']:
            return 1 # Bullish Marubozu
        else:
            return -1 # Bearish Marubozu
    return 0

def _is_hammer(candle: pd.Series, body_ratio: float, upper_wick_ratio: float, lower_wick_ratio: float) -> bool:
    """
    Kiểm tra nến Hammer (Bullish Pin Bar).
    Tiêu chí: Râu dưới dài, râu trên ngắn, thân nhỏ ở trên.
    """
    # Râu dưới > 2 lần thân, Râu trên rất nhỏ
    return (lower_wick_ratio >= 0.50 and # Râu dưới chiếm ít nhất 50%
            body_ratio <= 0.33 and       # Thân nến chiếm <= 1/3
            upper_wick_ratio <= 0.20)    # Râu trên ngắn

def _is_shooting_star(candle: pd.Series, body_ratio: float, upper_wick_ratio: float, lower_wick_ratio: float) -> bool:
    """
    Kiểm tra nến Shooting Star (Bearish Pin Bar).
    Tiêu chí: Râu trên dài, râu dưới ngắn, thân nhỏ ở dưới.
    """
    # Râu trên > 2 lần thân, Râu dưới rất nhỏ
    return (upper_wick_ratio >= 0.50 and # Râu trên chiếm ít nhất 50%
            body_ratio <= 0.33 and       # Thân nến chiếm <= 1/3
            lower_wick_ratio <= 0.20)    # Râu dưới ngắn

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V6.0) ---

def get_candle_pattern_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Phân tích cây nến M15 cuối cùng để tìm các mô hình nến đảo chiều mạnh mẽ
    và trả về điểm số tương ứng.
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['CANDLE_PATTERNS']
        if not cfg.get('enabled', False) or len(df) < 2:
            return 0.0, 0.0
            
        strong_score = cfg['score_levels']['strong_signal']
        medium_score = cfg['score_levels']['medium_signal']

        # Lấy dữ liệu 2 cây nến cuối cùng
        prev_candle = df.iloc[-2]
        last_candle = df.iloc[-1]

        # Lấy các tỷ lệ của nến cuối cùng
        body_r, up_wick_r, low_wick_r, wick_r = _get_candle_ratios(last_candle)
        
        # --- Logic 1: Marubozu (Tín hiệu mạnh nhất) ---
        marubozu_signal = _is_marubozu(last_candle, body_r, wick_r)
        if marubozu_signal == 1:
            long_score = max(long_score, strong_score)
        elif marubozu_signal == -1:
            short_score = max(short_score, strong_score)

        # --- Logic 2: Engulfing (Ưu tiên tiếp theo) ---
        if long_score == 0 and short_score == 0:
            if _is_bullish_engulfing(prev_candle, last_candle):
                last_body = abs(last_candle['close'] - last_candle['open'])
                prev_body = abs(prev_candle['close'] - prev_candle['open'])
                # Nếu nến tăng nhấn chìm mạnh (lớn hơn 1.5 lần nến trước)
                if last_body > (prev_body * 1.5):
                    long_score = max(long_score, strong_score)
                else:
                    long_score = max(long_score, medium_score)

            elif _is_bearish_engulfing(prev_candle, last_candle):
                last_body = abs(last_candle['close'] - last_candle['open'])
                prev_body = abs(prev_candle['close'] - prev_candle['open'])
                # Nếu nến giảm nhấn chìm mạnh
                if last_body > (prev_body * 1.5):
                    short_score = max(short_score, strong_score)
                else:
                    short_score = max(short_score, medium_score)

        # --- Logic 3: Hammer / Shooting Star (Ưu tiên cuối) ---
        if long_score == 0 and short_score == 0:
            if _is_hammer(last_candle, body_r, up_wick_r, low_wick_r):
                # Nếu râu dưới cực dài (ví dụ: > 65%), coi là tín hiệu mạnh
                if low_wick_r >= 0.65:
                    long_score = max(long_score, strong_score)
                else:
                    long_score = max(long_score, medium_score)

            elif _is_shooting_star(last_candle, body_r, up_wick_r, low_wick_r):
                 # Nếu râu trên cực dài (ví dụ: > 65%), coi là tín hiệu mạnh
                if up_wick_r >= 0.65:
                    short_score = max(short_score, strong_score)
                else:
                    short_score = max(short_score, medium_score)

    except Exception as e:
        # print(f"Lỗi khi tính điểm mô hình nến: {e}")
        pass

    # Áp dụng trần điểm
    max_score = cfg.get('max_score', 20)
    return min(long_score, max_score), min(short_score, max_score)