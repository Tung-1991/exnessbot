# Tên file: signals/macd.py (Bản Master V8.0)
# Mục đích: Tính điểm MACD bằng logic "CỘNG HƯỞNG 3 YẾU TỐ":
#          1. Trend (Xu hướng): Vị trí Macd Line (Nội suy)
#          2. Momentum (Đà): Vị trí Histogram (Nội suy)
#          3. Signal (Tín hiệu): Phân kỳ / Giao cắt (Cộng điểm)
#
# YÊU CẦU: Cần cập nhật file config.py để thêm 'v8_score_levels'

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
try:
    from scipy.signal import find_peaks
except ImportError:
    print("VUI LÒNG CÀI ĐẶT THƯ VIỆN SCIPY: pip install scipy")
    find_peaks = None

# --- HÀM HỖ TRỢ NỘI SUY (Copy từ rsi.py V7.0) ---
# (Chúng ta cần hàm này để chấm điểm "linh hoạt" cho Yếu tố 1 và 2)
def _calculate_interpolation(current_val: float, neutral_val: float, full_score_val: float, max_score: float) -> float:
    """
    Hàm nội suy tuyến tính để chấm điểm "linh hoạt".
    Lưu ý: Hàm này được đơn giản hóa để nội suy CẢ 2 CHIỀU (âm và dương).
    """
    try:
        # Chuẩn hóa giá trị (ví dụ: -5, 0, 5)
        # Giá trị tuyệt đối (0 đến 5)
        distance = abs(current_val - neutral_val)
        # Khoảng cách tối đa (5)
        full_distance = abs(full_score_val - neutral_val)
        
        if full_distance == 0:
            return 0.0 # Tránh lỗi chia cho 0
        
        # Tính hệ số điểm (từ 0.0 đến 1.0+)
        score_factor = distance / full_distance
        
        # Áp điểm và trả về (đảm bảo không vượt max_score)
        return min(max_score * score_factor, max_score)
    except:
        return 0.0

# --- HÀM TÍNH TOÁN MACD GỐC (Giữ nguyên) ---
def calculate_macd(df: pd.DataFrame, fast_ema: int = 12, slow_ema: int = 26, signal_sma: int = 9) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    if 'close' not in df.columns: return None
    ema_fast = df['close'].ewm(span=fast_ema, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_ema, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_sma, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# --- HÀM HỖ TRỢ TÌM PHÂN KỲ (Giữ nguyên) ---
def _find_divergence(price_data: pd.Series, indicator_data: pd.Series, lookback: int) -> Tuple[bool, bool]:
    if find_peaks is None: return False, False 
    bullish_divergence, bearish_divergence = False, False
    price = price_data.iloc[-lookback:]
    indicator = indicator_data.iloc[-lookback:]
    try:
        price_troughs, _ = find_peaks(-price, distance=5, prominence=0.1)
        indicator_troughs, _ = find_peaks(-indicator, distance=5, prominence=0.1)
        if len(price_troughs) >= 2 and len(indicator_troughs) >= 2:
            p_low_1_idx, p_low_2_idx = price.index[price_troughs[-2]], price.index[price_troughs[-1]]
            i_low_1_idx, i_low_2_idx = indicator.index[indicator_troughs[-2]], indicator.index[indicator_troughs[-1]]
            if p_low_1_idx == i_low_1_idx and p_low_2_idx == i_low_2_idx:
                if price[p_low_2_idx] < price[p_low_1_idx] and indicator[i_low_2_idx] > indicator[i_low_1_idx]:
                    bullish_divergence = True
    except Exception: pass
    try:
        price_peaks, _ = find_peaks(price, distance=5, prominence=0.1)
        indicator_peaks, _ = find_peaks(indicator, distance=5, prominence=0.1)
        if len(price_peaks) >= 2 and len(indicator_peaks) >= 2:
            p_high_1_idx, p_high_2_idx = price.index[price_peaks[-2]], price.index[price_peaks[-1]]
            i_high_1_idx, i_high_2_idx = indicator.index[indicator_peaks[-2]], indicator.index[indicator_peaks[-1]]
            if p_high_1_idx == i_high_1_idx and p_high_2_idx == i_high_2_idx:
                if price[p_high_2_idx] > price[p_high_1_idx] and indicator[i_high_2_idx] < indicator[i_high_1_idx]:
                    bearish_divergence = True
    except Exception: pass
    return bullish_divergence, bearish_divergence

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V8.0 - CỘNG HƯỞNG) ---
def get_macd_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên logic "CỘNG HƯỞNG 3 YẾU TỐ".
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V8.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['MACD']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        
        # *** LƯU Ý: Đọc cấu hình V8.0 MỚI ***
        levels = cfg.get('v8_score_levels', {})
        if not levels:
             # Fallback nếu config chưa cập nhật, nhưng sẽ không chạy
             return 0.0, 0.0 
        
        lines = calculate_macd(
            df,
            fast_ema=params['fast_ema'],
            slow_ema=params['slow_ema'],
            signal_sma=params['signal_sma']
        )
        
        if lines is None or len(df) < 2:
            return 0.0, 0.0

        macd_line, signal_line, histogram = lines
        
        # Lấy dữ liệu 2 cây nến gần nhất
        prev_hist = histogram.iloc[-2]
        last_hist = histogram.iloc[-1]
        last_macd = macd_line.iloc[-1]
        
        # Chuẩn hóa giá trị MACD (ví dụ ETHUSD) để nội suy
        # (Lấy ATR 100 nến để đo lường biến động)
        atr_100 = df['close'].rolling(100).apply(lambda x: (x.max() - x.min()) / 2, raw=True).iloc[-1]
        if atr_100 == 0: atr_100 = 1 # Tránh chia cho 0
        
        norm_macd = last_macd / atr_100 * 100
        norm_hist = last_hist / atr_100 * 100
        
        # ==========================================================
        # === YẾU TỐ 1: XU HƯỚNG (Trend) - Vị trí Macd Line ===
        # ==========================================================
        # Chấm điểm "linh hoạt" dựa trên vị trí của Macd Line
        
        trend_cfg = levels.get('TREND', {})
        trend_max_score = trend_cfg.get('max_score', 0)
        trend_full_val = trend_cfg.get('full_score_value_norm', 0.5) # 0.5%
        
        if norm_macd > 0:
            long_score += _calculate_interpolation(
                norm_macd, 0, trend_full_val, trend_max_score
            )
        elif norm_macd < 0:
            short_score += _calculate_interpolation(
                norm_macd, 0, -trend_full_val, trend_max_score
            )

        # ==========================================================
        # === YẾU TỐ 2: ĐÀ (Momentum) - Vị trí Histogram ===
        # ==========================================================
        # Chấm điểm "linh hoạt" dựa trên vị trí của Histogram
        
        mom_cfg = levels.get('MOMENTUM', {})
        mom_max_score = mom_cfg.get('max_score', 0)
        mom_full_val = mom_cfg.get('full_score_value_norm', 0.1) # 0.1%
        
        if norm_hist > 0:
            long_score += _calculate_interpolation(
                norm_hist, 0, mom_full_val, mom_max_score
            )
        elif norm_hist < 0:
            short_score += _calculate_interpolation(
                norm_hist, 0, -mom_full_val, mom_max_score
            )
            
        # ==========================================================
        # === YẾU TỐ 3: TÍN HIỆU (Signal) - Events ===
        # ==========================================================
        # Cộng điểm trực tiếp cho các "sự kiện" hành động giá
        
        sig_cfg = levels.get('SIGNALS', {})
        
        # --- 3a. Tín hiệu Phân kỳ (Divergence) ---
        if find_peaks is not None and sig_cfg.get('divergence_score', 0) > 0:
            lookback_period = 50 
            is_bullish_div, is_bearish_div = _find_divergence(
                price_data=df['close'], 
                indicator_data=macd_line, 
                lookback=lookback_period
            )
            if is_bullish_div:
                long_score += sig_cfg['divergence_score']
            if is_bearish_div:
                short_score += sig_cfg['divergence_score']

        # --- 3b. Tín hiệu Giao cắt (Signal Cross) ---
        # (Histogram vừa cắt qua đường 0)
        if last_hist > 0 and prev_hist <= 0:
            long_score += sig_cfg.get('signal_cross_score', 0)
            
        elif last_hist < 0 and prev_hist >= 0:
            short_score += sig_cfg.get('signal_cross_score', 0)
            
    except Exception as e:
        # print(f"Lỗi khi tính điểm MACD (v8.0): {e}")
        pass

    # Áp dụng trần điểm TỔNG (Weighting)
    max_score_cap = cfg.get('MAX_SCORE', 70) # Lấy trần 70 điểm của bạn
    return min(long_score, max_score_cap), min(short_score, max_score_cap)