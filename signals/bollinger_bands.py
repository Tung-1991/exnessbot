# Tên file: signals/bollinger_bands.py (Bản Master V8.0)
# Mục đích: Tính điểm BB bằng logic "CỘNG HƯỞNG 3 YẾU TỐ":
#          1. Context (Bối cảnh): Thị trường Squeeze hay Mở rộng? (Nội suy)
#          2. Position (Vị trí): Giá đang ở đâu so với dải? (Nội suy)
#          3. Price Action (Hành động giá): Nến đang làm gì? (Cộng điểm)
#
# YÊU CẦU: Cần cập nhật file config.py để thêm 'v8_score_levels'

import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any

# --- HÀM HỖ TRỢ NỘI SUY (Copy từ rsi.py V7.0) ---
# (Chúng ta cần hàm này để chấm điểm "linh hoạt" cho Yếu tố 1 và 2)
def _calculate_interpolation(current_val: float, neutral_val: float, full_score_val: float, max_score: float) -> float:
    """
    Hàm nội suy tuyến tính để chấm điểm "linh hoạt".
    """
    try:
        distance = abs(current_val - neutral_val)
        full_distance = abs(full_score_val - neutral_val)
        if full_distance == 0: return 0.0
        
        # Chỉ tính điểm nếu giá trị vượt qua mốc trung tính (theo đúng hướng)
        if (current_val > neutral_val and full_score_val > neutral_val) or \
           (current_val < neutral_val and full_score_val < neutral_val):
            
            score_factor = distance / full_distance
            return min(max_score * score_factor, max_score)
        return 0.0
    except:
        return 0.0

# --- HÀM TÍNH TOÁN BB GỐC (Giữ nguyên) ---
def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Optional[Tuple[pd.Series, pd.Series, pd.Series, pd.Series]]:
    """
    Tính toán 3 đường của chỉ báo Bollinger Bands VÀ độ rộng (Bandwidth).
    """
    if 'close' not in df.columns:
        return None

    middle_band = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    
    # Tính độ rộng của BB (Bandwidth)
    band_width = ((upper_band - lower_band) / middle_band) * 100
    
    return upper_band, middle_band, lower_band, band_width

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V8.0 - CỘNG HƯỞNG) ---
def get_bb_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên logic "CỘNG HƯỞNG 3 YẾU TỐ".
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V8.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['BOLLINGER_BANDS']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        
        # *** LƯU Ý: Đọc cấu hình V8.0 MỚI ***
        # (Bạn sẽ cần cập nhật file config.py)
        levels = cfg.get('v8_score_levels', {}) 
        if not levels:
             # Fallback nếu config chưa cập nhật, nhưng sẽ không chạy
             return 0.0, 0.0 

        bands = calculate_bollinger_bands(
            df, 
            period=params['period'], 
            std_dev=params['std_dev']
        )
        if bands is None:
            return 0.0, 0.0

        upper_band, middle_band, lower_band, band_width = bands
        
        if len(df) < 3 or pd.isna(upper_band.iloc[-1]) or pd.isna(middle_band.iloc[-1]):
            return 0.0, 0.0
            
        # Lấy dữ liệu nến
        prev_candle = df.iloc[-2]
        last_candle = df.iloc[-1]
        
        # Lấy giá trị cuối cùng
        last_upper = upper_band.iloc[-1]
        last_middle = middle_band.iloc[-1]
        last_lower = lower_band.iloc[-1]
        last_width = band_width.iloc[-1]
        
        # ==========================================================
        # === YẾU TỐ 1: BỐI CẢNH (Context) - Squeeze / Expansion ===
        # ==========================================================
        # Chấm điểm dựa trên độ rộng của dải (Bandwidth)
        
        ctx_cfg = levels.get('CONTEXT', {})
        squeeze_score = ctx_cfg.get('squeeze_score', 0)
        squeeze_thresh = ctx_cfg.get('squeeze_threshold_pct', 2.0)
        expansion_score = ctx_cfg.get('expansion_score', 0)
        expansion_thresh = ctx_cfg.get('expansion_threshold_pct', 8.0)

        if last_width <= squeeze_thresh:
            # "Thắt cổ chai" -> Sắp bùng nổ 2 chiều
            long_score += squeeze_score
            short_score += squeeze_score
        elif last_width >= expansion_thresh:
            # "Mở rộng" -> Thị trường đang có trend/biến động mạnh
            long_score += expansion_score
            short_score += expansion_score

        # ==========================================================
        # === YẾU TỐ 2: VỊ TRÍ (Position) - Chạm dải (Nội suy) ===
        # ==========================================================
        # Chấm điểm "linh hoạt" dựa trên vị trí của giá đóng cửa
        
        pos_cfg = levels.get('POSITION', {})
        max_score = pos_cfg.get('max_score', 0)
        
        # Tính "Vị trí chuẩn hóa" (từ 0.0 đến 1.0+)
        # 0.0 = ở dải dưới, 0.5 = ở dải giữa, 1.0 = ở dải trên
        total_range = last_upper - last_lower
        if total_range > 0:
            normalized_position = (last_candle['close'] - last_lower) / total_range
            
            # Tính điểm Long (khi giá gần dải dưới)
            # (Nội suy từ 0.5 (0 điểm) đến 0.0 (max điểm))
            long_score += _calculate_interpolation(
                normalized_position, 
                pos_cfg.get('neutral_level_long', 0.5), # 0.5 = Dải giữa
                pos_cfg.get('full_score_level_long', 0.0), # 0.0 = Dải dưới
                max_score
            )
            
            # Tính điểm Short (khi giá gần dải trên)
            # (Nội suy từ 0.5 (0 điểm) đến 1.0 (max điểm))
            short_score += _calculate_interpolation(
                normalized_position, 
                pos_cfg.get('neutral_level_short', 0.5), # 0.5 = Dải giữa
                pos_cfg.get('full_score_level_short', 1.0), # 1.0 = Dải trên
                max_score
            )

        # ==========================================================
        # === YẾU TỐ 3: HÀNH ĐỘNG GIÁ (Price Action) - Tín hiệu ===
        # ==========================================================
        # Cộng điểm trực tiếp cho các "sự kiện" hành động giá
        
        pa_cfg = levels.get('PRICE_ACTION', {})

        # --- 3a. Tín hiệu Đảo chiều "Fakey" (Reversal) ---
        # (Giá thò ra ngoài dải nhưng đóng cửa bên trong)
        if last_candle['low'] < last_lower and last_candle['close'] > last_lower:
            long_score += pa_cfg.get('fakey_reversal_score', 0)
            
        if last_candle['high'] > last_upper and last_candle['close'] < last_upper:
            short_score += pa_cfg.get('fakey_reversal_score', 0)

        # --- 3b. Tín hiệu Tiếp diễn "Walking the Band" (Continuation) ---
        # (Giá đóng cửa 2 nến liên tiếp bên ngoài dải)
        if last_candle['close'] > last_upper and prev_candle['close'] > upper_band.iloc[-2]:
            long_score += pa_cfg.get('walking_the_band_score', 0)
            
        if last_candle['close'] < last_lower and prev_candle['close'] < lower_band.iloc[-2]:
            short_score += pa_cfg.get('walking_the_band_score', 0)
            
        # --- 3c. Tín hiệu Bật lại từ Dải giữa (Middle Band Bounce) ---
        is_uptrending_mb = last_middle > middle_band.iloc[-2]
        is_downtrending_mb = last_middle < middle_band.iloc[-2]

        if is_uptrending_mb and \
           last_candle['low'] <= last_middle and \
           last_candle['close'] > last_middle: 
            long_score += pa_cfg.get('middle_band_bounce_score', 0)
            
        elif is_downtrending_mb and \
             last_candle['high'] >= last_middle and \
             last_candle['close'] < last_middle:
            short_score += pa_cfg.get('middle_band_bounce_score', 0)

    except Exception as e:
        # print(f"Lỗi khi tính điểm Bollinger Bands (v8.0): {e}")
        pass

    # Áp dụng trần điểm TỔNG (Weighting)
    max_score_cap = cfg.get('MAX_SCORE', 70) # Lấy trần 70 điểm của bạn
    return min(long_score, max_score_cap), min(short_score, max_score_cap)