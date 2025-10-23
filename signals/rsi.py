# Tên file: signals/rsi.py (Bản Final V7.0)
# Mục đích: Tính RSI và chấm điểm bằng logic NỘI SUY (Interpolation)
#          để lấp đầy "khoảng mù 30-70".
#          Đã LOẠI BỎ 'trend_bias' và dùng logic CỘNG DỒN.

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
try:
    from scipy.signal import find_peaks
except ImportError:
    print("VUI LÒNG CÀI ĐẶT THƯ VIỆN SCIPY: pip install scipy")
    find_peaks = None

# --- HÀM TÍNH TOÁN RSI GỐC (Giữ nguyên từ file cũ) ---
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo Relative Strength Index (RSI).
    """
    if 'close' not in df.columns:
        return None

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rs = rs.replace([np.inf, -np.inf], 100).fillna(100) # Sửa lỗi chia cho 0

    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- HÀM HỖ TRỢ TÌM PHÂN KỲ (Giữ nguyên từ file cũ) ---
def _find_divergence(price_data: pd.Series, indicator_data: pd.Series, lookback: int) -> Tuple[bool, bool]:
    """
    Hàm nội bộ để tìm phân kỳ tăng và giảm trong 'lookback' nến gần nhất.
    (Hàm này giữ nguyên từ file gốc v6.0 của bạn)
    """
    if find_peaks is None:
        return False, False 

    bullish_divergence = False
    bearish_divergence = False
    
    price = price_data.iloc[-lookback:]
    indicator = indicator_data.iloc[-lookback:]

    # (Logic tìm đỉnh/đáy giữ nguyên... vì nó đã chuẩn)
    # 1. Tìm Phân kỳ Tăng (Bullish Divergence) - So sánh các đáy
    try:
        price_troughs, _ = find_peaks(-price, distance=5, prominence=0.1)
        indicator_troughs, _ = find_peaks(-indicator, distance=5, prominence=0.1)
        if len(price_troughs) >= 2 and len(indicator_troughs) >= 2:
            p_low_1_idx, p_low_2_idx = price.index[price_troughs[-2]], price.index[price_troughs[-1]]
            i_low_1_idx, i_low_2_idx = indicator.index[indicator_troughs[-2]], indicator.index[indicator_troughs[-1]]
            if p_low_1_idx == i_low_1_idx and p_low_2_idx == i_low_2_idx:
                if price[p_low_2_idx] < price[p_low_1_idx]:
                    if indicator[i_low_2_idx] > indicator[i_low_1_idx]:
                        bullish_divergence = True
    except Exception: pass

    # 2. Tìm Phân kỳ Giảm (Bearish Divergence) - So sánh các đỉnh
    try:
        price_peaks, _ = find_peaks(price, distance=5, prominence=0.1)
        indicator_peaks, _ = find_peaks(indicator, distance=5, prominence=0.1)
        if len(price_peaks) >= 2 and len(indicator_peaks) >= 2:
            p_high_1_idx, p_high_2_idx = price.index[price_peaks[-2]], price.index[price_peaks[-1]]
            i_high_1_idx, i_high_2_idx = indicator.index[indicator_peaks[-2]], indicator.index[indicator_peaks[-1]]
            if p_high_1_idx == i_high_1_idx and p_high_2_idx == i_high_2_idx:
                if price[p_high_2_idx] > price[p_high_1_idx]:
                    if indicator[i_high_2_idx] < indicator[i_high_1_idx]:
                        bearish_divergence = True
    except Exception: pass

    return bullish_divergence, bearish_divergence

# --- HÀM HỖ TRỢ NỘI SUY (LOGIC MỚI v7.0) ---
def _calculate_interpolation(current_val: float, neutral_val: float, full_score_val: float, max_score: float) -> float:
    """
    Hàm nội suy tuyến tính để chấm điểm "linh hoạt".
    Ví dụ: current=40, neutral=50, full_score=30, max=25
    -> distance = 10, full_distance = 20
    -> score_factor = 0.5 -> return 12.5
    """
    try:
        # Tính khoảng cách
        distance = abs(current_val - neutral_val)
        full_distance = abs(full_score_val - neutral_val)
        
        if full_distance == 0:
            return 0.0 # Tránh lỗi chia cho 0

        # Tính hệ số điểm (từ 0.0 đến 1.0+)
        score_factor = distance / full_distance
        
        # Áp điểm và trả về (đảm bảo không vượt max_score)
        return min(max_score * score_factor, max_score)
    except:
        return 0.0

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V7.0) ---
def get_rsi_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên logic NỘI SUY (Interpolation)
    và CỘNG DỒN với điểm Phân kỳ (Divergence).
    
    ĐÃ LOẠI BỎ 'trend_bias'.
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V7.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['RSI']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        # Đọc các mức điểm MỚI cho logic v7.0
        levels = cfg['score_levels']
        
        # Các mốc neo cho nội suy
        neutral_level = levels.get('neutral_level', 50.0)
        full_score_long = levels.get('full_score_level_long', 30.0)
        full_score_short = levels.get('full_score_level_short', 70.0)
        # Điểm tối đa cho riêng phần nội suy
        momentum_score = levels.get('max_momentum_score', 20) 
        
        # Điểm riêng cho phân kỳ
        divergence_score = levels.get('divergence_score', 30)

        # Tính RSI
        rsi_series = calculate_rsi(df, period=params['period'])
        
        if rsi_series is None or rsi_series.empty or len(rsi_series) < 2:
            return 0.0, 0.0

        last_rsi = rsi_series.iloc[-1]
        
        # --- Logic 1: Tính điểm Momentum (Nội suy) ---
        # (Logic này thay thế 5 logic cũ 'deep_zone', 'oversold', 'entry_zone', 'cross_midline', 'above_midline')
        
        momentum_long_score, momentum_short_score = 0.0, 0.0
        
        if last_rsi < neutral_level:
            # RSI < 50, thị trường yếu (tín hiệu Long tiềm năng)
            momentum_long_score = _calculate_interpolation(
                last_rsi, neutral_level, full_score_long, momentum_score
            )
        elif last_rsi > neutral_level:
            # RSI > 50, thị trường mạnh (tín hiệu Short tiềm năng)
            momentum_short_score = _calculate_interpolation(
                last_rsi, neutral_level, full_score_short, momentum_score
            )
            
        # --- Logic 2: Tính điểm Phân kỳ (Divergence) ---
        div_long_score, div_short_score = 0.0, 0.0
        
        if find_peaks is not None and divergence_score > 0:
            lookback_period = 50 
            is_bullish_div, is_bearish_div = _find_divergence(
                price_data=df['close'], 
                indicator_data=rsi_series, 
                lookback=lookback_period
            )
            
            if is_bullish_div:
                div_long_score = divergence_score
            
            if is_bearish_div:
                div_short_score = divergence_score

        # --- Logic 3: Cộng dồn điểm (Additive Logic) ---
        long_score = momentum_long_score + div_long_score
        short_score = momentum_short_score + div_short_score

    except Exception as e:
        # print(f"Lỗi khi tính điểm RSI (v7.0): {e}")
        pass

    # Áp dụng trần điểm TỔNG (từ config)
    max_score_cap = cfg.get('MAX_SCORE', 30)
    return min(long_score, max_score_cap), min(short_score, max_score_cap)