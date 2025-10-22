# Tên file: signals/macd.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Tính MACD và chấm điểm dựa trên thang đo chi tiết VÀ phát hiện phân kỳ.

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
try:
    from scipy.signal import find_peaks
except ImportError:
    print("VUI LÒNG CÀI ĐẶT THƯ VIỆN SCIPY: pip install scipy")
    find_peaks = None

# --- HÀM TÍNH TOÁN MACD GỐC ---
def calculate_macd(df: pd.DataFrame, fast_ema: int = 12, slow_ema: int = 26, signal_sma: int = 9) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    """
    Tính toán đường MACD, đường Signal, và Histogram.
    """
    if 'close' not in df.columns:
        return None

    ema_fast = df['close'].ewm(span=fast_ema, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_ema, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_sma, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

# --- HÀM HỖ TRỢ TÌM PHÂN KỲ (Sử dụng chung, tương tự như trong rsi.py) ---
def _find_divergence(price_data: pd.Series, indicator_data: pd.Series, lookback: int) -> Tuple[bool, bool]:
    """
    Hàm nội bộ để tìm phân kỳ tăng và giảm trong 'lookback' nến gần nhất.
    """
    if find_peaks is None:
        return False, False 

    bullish_divergence = False
    bearish_divergence = False
    
    price = price_data.iloc[-lookback:]
    indicator = indicator_data.iloc[-lookback:]

    # 1. Tìm Phân kỳ Tăng (Bullish Divergence) - So sánh các đáy
    try:
        price_troughs, _ = find_peaks(-price, distance=5, prominence=0.1)
        indicator_troughs, _ = find_peaks(-indicator, distance=5, prominence=0.1)

        if len(price_troughs) >= 2 and len(indicator_troughs) >= 2:
            p_low_1_idx = price.index[price_troughs[-2]]
            p_low_2_idx = price.index[price_troughs[-1]]
            i_low_1_idx = indicator.index[indicator_troughs[-2]]
            i_low_2_idx = indicator.index[indicator_troughs[-1]]

            if p_low_1_idx == i_low_1_idx and p_low_2_idx == i_low_2_idx:
                if price[p_low_2_idx] < price[p_low_1_idx]: # Giá: Đáy sau thấp hơn
                    if indicator[i_low_2_idx] > indicator[i_low_1_idx]: # MACD: Đáy sau cao hơn
                        bullish_divergence = True
    except Exception:
        pass 

    # 2. Tìm Phân kỳ Giảm (Bearish Divergence) - So sánh các đỉnh
    try:
        price_peaks, _ = find_peaks(price, distance=5, prominence=0.1)
        indicator_peaks, _ = find_peaks(indicator, distance=5, prominence=0.1)

        if len(price_peaks) >= 2 and len(indicator_peaks) >= 2:
            p_high_1_idx = price.index[price_peaks[-2]]
            p_high_2_idx = price.index[price_peaks[-1]]
            i_high_1_idx = indicator.index[indicator_peaks[-2]]
            i_high_2_idx = indicator.index[indicator_peaks[-1]]

            if p_high_1_idx == i_high_1_idx and p_high_2_idx == i_high_2_idx:
                if price[p_high_2_idx] > price[p_high_1_idx]: # Giá: Đỉnh sau cao hơn
                    if indicator[i_high_2_idx] < indicator[i_high_1_idx]: # MACD: Đỉnh sau thấp hơn
                        bearish_divergence = True
    except Exception:
        pass 

    return bullish_divergence, bearish_divergence

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V6.0) ---
def get_macd_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên thang điểm chi tiết của MACD,
    bao gồm Phân kỳ, Giao cắt, và Momentum của Histogram.
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['MACD']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        levels = cfg['score_levels']
        
        lines = calculate_macd(
            df,
            fast_ema=params['fast_ema'],
            slow_ema=params['slow_ema'],
            signal_sma=params['signal_sma']
        )
        
        if lines is None or len(df) < 3: # Cần ít nhất 3 nến để so sánh momentum
            return 0.0, 0.0

        macd_line, signal_line, histogram = lines
        
        # Lấy dữ liệu 3 cây nến gần nhất
        prev_hist_2 = histogram.iloc[-3]
        prev_hist = histogram.iloc[-2]
        last_hist = histogram.iloc[-1]
        
        last_macd = macd_line.iloc[-1]

        # --- Logic 1: Phân kỳ (Divergence) - Tín hiệu mạnh nhất ---
        if find_peaks is not None:
            lookback_period = 50 
            is_bullish_div, is_bearish_div = _find_divergence(
                price_data=df['close'], 
                # Chú ý: Chúng ta tìm phân kỳ trên đường MACD, không phải Histogram
                indicator_data=macd_line, 
                lookback=lookback_period
            )
            
            if is_bullish_div:
                long_score = max(long_score, levels['divergence'])
            
            if is_bearish_div:
                short_score = max(short_score, levels['divergence'])

        # --- Logic 2: Giao cắt Zero Line (Zero Line Cross) ---
        # Chỉ tính điểm này nếu Phân kỳ chưa xảy ra
        if long_score == 0 and short_score == 0:
            # Giao cắt TĂNG (từ âm sang dương)
            if last_macd > 0 and macd_line.iloc[-2] <= 0:
                # Và Histogram đang tăng (xác nhận momentum)
                if last_hist > prev_hist:
                    long_score = max(long_score, levels['zero_line_cross'])
            
            # Giao cắt GIẢM (từ dương sang âm)
            elif last_macd < 0 and macd_line.iloc[-2] >= 0:
                # Và Histogram đang giảm (xác nhận momentum)
                if last_hist < prev_hist:
                    short_score = max(short_score, levels['zero_line_cross'])

        # --- Logic 3: Giao cắt thông thường (Signal Cross) ---
        # Chỉ tính điểm này nếu 2 tín hiệu trên chưa xảy ra
        if long_score == 0 and short_score == 0:
            # Giao cắt TĂNG (Histogram chuyển từ âm sang dương)
            if last_hist > 0 and prev_hist <= 0:
                long_score = max(long_score, levels['signal_cross'])
                
            # Giao cắt GIẢM (Histogram chuyển từ dương sang âm)
            elif last_hist < 0 and prev_hist >= 0:
                short_score = max(short_score, levels['signal_cross'])

        # --- Logic 4: Histogram Momentum (Xác nhận xu hướng) ---
        # Chỉ tính điểm này nếu 3 tín hiệu trên chưa xảy ra
        if long_score == 0 and short_score == 0:
            # Histogram TĂNG (đã dương và đang tăng tốc)
            if last_hist > 0 and prev_hist > 0 and last_hist > prev_hist:
                # Kiểm tra 3 nến liên tiếp để chắc chắn
                if prev_hist > prev_hist_2:
                    long_score = max(long_score, levels['histogram_momentum'])
            
            # Histogram GIẢM (đã âm và đang giảm tốc)
            elif last_hist < 0 and prev_hist < 0 and last_hist < prev_hist:
                 # Kiểm tra 3 nến liên tiếp để chắc chắn
                if prev_hist < prev_hist_2:
                    short_score = max(short_score, levels['histogram_momentum'])

    except Exception as e:
        # print(f"Lỗi khi tính điểm MACD: {e}")
        pass

    # Áp dụng trần điểm
    max_score = cfg.get('max_score', 25)
    return min(long_score, max_score), min(short_score, max_score)