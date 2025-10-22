# Tên file: signals/candle_patterns.py
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

def _get_pin_bar_ratios(candle: pd.Series) -> Tuple[float, float, float]:
    """
    Tính toán các tỷ lệ của một cây nến để xác định Pin Bar.
    Trả về (tỷ lệ thân, tỷ lệ râu trên, tỷ lệ râu dưới) so với tổng chiều dài nến.
    """
    body_size = abs(candle['close'] - candle['open'])
    candle_range = candle['high'] - candle['low']
    
    if candle_range == 0:
        return 0, 0, 0 # Tránh lỗi chia cho 0 (ví dụ nến Doji)

    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']

    body_ratio = body_size / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    
    return body_ratio, upper_wick_ratio, lower_wick_ratio

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH ---

def get_candle_pattern_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Phân tích cây nến M15 cuối cùng để tìm các mô hình nến đảo chiều mạnh mẽ
    và trả về điểm số tương ứng.
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # Lấy config
        cfg = config['ENTRY_SIGNALS_CONFIG']['CANDLE_PATTERNS']
        if not cfg.get('enabled', False) or len(df) < 2:
            return 0.0, 0.0
            
        strong_score = cfg['score_levels']['strong_signal']
        medium_score = cfg['score_levels']['medium_signal']

        # Lấy dữ liệu 2 cây nến cuối cùng
        prev_candle = df.iloc[-2]
        last_candle = df.iloc[-1]

        # --- Logic 1: Bullish Engulfing (Nhấn chìm Tăng) ---
        if _is_bullish_engulfing(prev_candle, last_candle):
            last_body = abs(last_candle['close'] - last_candle['open'])
            prev_body = abs(prev_candle['close'] - prev_candle['open'])
            
            # Nếu nến tăng nhấn chìm mạnh (ví dụ: lớn hơn 1.5 lần nến trước)
            if last_body > (prev_body * 1.5):
                long_score = strong_score
            else:
                long_score = medium_score

        # --- Logic 2: Bearish Engulfing (Nhấn chìm Giảm) ---
        elif _is_bearish_engulfing(prev_candle, last_candle):
            last_body = abs(last_candle['close'] - last_candle['open'])
            prev_body = abs(prev_candle['close'] - prev_candle['open'])
            
            # Nếu nến giảm nhấn chìm mạnh
            if last_body > (prev_body * 1.5):
                short_score = strong_score
            else:
                short_score = medium_score

        # Nếu không phải Engulfing, kiểm tra Pin Bar (không thể vừa Engulfing vừa Pin Bar)
        else:
            body_ratio, upper_wick_ratio, lower_wick_ratio = _get_pin_bar_ratios(last_candle)

            # --- Logic 3: Hammer / Bullish Pin Bar (Râu dưới dài) ---
            # Tiêu chí: Râu dưới phải chiếm ít nhất 50% toàn bộ nến
            #            Thân nến phải nhỏ (ví dụ: < 30%)
            #            Râu trên phải rất ngắn (ví dụ: < 15%)
            if lower_wick_ratio >= 0.5 and body_ratio <= 0.3 and upper_wick_ratio <= 0.2:
                # Nếu râu dưới cực dài (ví dụ: > 65%), coi là tín hiệu mạnh
                if lower_wick_ratio >= 0.65:
                    long_score = strong_score
                else:
                    long_score = medium_score

            # --- Logic 4: Shooting Star / Bearish Pin Bar (Râu trên dài) ---
            # Tiêu chí: Râu trên phải chiếm ít nhất 50% toàn bộ nến
            #            Thân nến phải nhỏ (ví dụ: < 30%)
            #            Râu dưới phải rất ngắn (ví dụ: < 15%)
            elif upper_wick_ratio >= 0.5 and body_ratio <= 0.3 and lower_wick_ratio <= 0.2:
                 # Nếu râu trên cực dài (ví dụ: > 65%), coi là tín hiệu mạnh
                if upper_wick_ratio >= 0.65:
                    short_score = strong_score
                else:
                    short_score = medium_score

    except Exception as e:
        # print(f"Lỗi khi tính điểm mô hình nến: {e}")
        pass

    return long_score, short_score