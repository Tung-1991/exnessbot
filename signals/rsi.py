# Tên file: signals/rsi.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Tính RSI và chấm điểm dựa trên thang đo chi tiết VÀ phát hiện phân kỳ.

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
try:
    # Scipy là thư viện tiêu chuẩn vàng để tìm đỉnh/đáy (peaks/troughs)
    # Nó giúp logic phát hiện phân kỳ trở nên cực kỳ chính xác và mạnh mẽ.
    from scipy.signal import find_peaks
except ImportError:
    print("VUI LÒNG CÀI ĐẶT THƯ VIỆN SCIPY: pip install scipy")
    # Nếu không có scipy, chúng ta không thể chạy logic phân kỳ
    find_peaks = None

# --- HÀM TÍNH TOÁN RSI GỐC ---
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
    rs = rs.replace([np.inf, -np.inf], 100).fillna(100)

    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- HÀM HỖ TRỢ TÌM PHÂN KỲ ---
def _find_divergence(price_data: pd.Series, indicator_data: pd.Series, lookback: int) -> Tuple[bool, bool]:
    """
    Hàm nội bộ để tìm phân kỳ tăng và giảm trong 'lookback' nến gần nhất.
    """
    if find_peaks is None:
        return False, False # Không thể tìm phân kỳ nếu thiếu thư viện scipy

    bullish_divergence = False
    bearish_divergence = False
    
    # Chỉ xem xét 'lookback' nến cuối cùng
    price = price_data.iloc[-lookback:]
    indicator = indicator_data.iloc[-lookback:]

    # 1. Tìm Phân kỳ Tăng (Bullish Divergence) - So sánh các đáy
    try:
        # Tìm 2 đáy gần nhất của Giá (dùng -price để tìm đáy)
        price_troughs, _ = find_peaks(-price, distance=5, prominence=0.1)
        
        # Tìm 2 đáy gần nhất của RSI (dùng -indicator để tìm đáy)
        indicator_troughs, _ = find_peaks(-indicator, distance=5, prominence=0.1)

        if len(price_troughs) >= 2 and len(indicator_troughs) >= 2:
            # Lấy 2 chỉ số (index) của 2 đáy giá cuối cùng
            p_low_1_idx = price.index[price_troughs[-2]]
            p_low_2_idx = price.index[price_troughs[-1]]
            
            # Lấy 2 chỉ số của 2 đáy RSI cuối cùng
            i_low_1_idx = indicator.index[indicator_troughs[-2]]
            i_low_2_idx = indicator.index[indicator_troughs[-1]]

            # Đảm bảo chúng ta đang so sánh cùng một cặp đáy
            if p_low_1_idx == i_low_1_idx and p_low_2_idx == i_low_2_idx:
                # Giá tạo đáy sau thấp hơn đáy trước (Lower Low)
                if price[p_low_2_idx] < price[p_low_1_idx]:
                    # RSI tạo đáy sau cao hơn đáy trước (Higher Low)
                    if indicator[i_low_2_idx] > indicator[i_low_1_idx]:
                        bullish_divergence = True
    except Exception:
        pass # Bỏ qua nếu không tìm thấy đỉnh/đáy

    # 2. Tìm Phân kỳ Giảm (Bearish Divergence) - So sánh các đỉnh
    try:
        # Tìm 2 đỉnh gần nhất của Giá
        price_peaks, _ = find_peaks(price, distance=5, prominence=0.1)
        
        # Tìm 2 đỉnh gần nhất của RSI
        indicator_peaks, _ = find_peaks(indicator, distance=5, prominence=0.1)

        if len(price_peaks) >= 2 and len(indicator_peaks) >= 2:
            # Lấy 2 chỉ số (index) của 2 đỉnh giá cuối cùng
            p_high_1_idx = price.index[price_peaks[-2]]
            p_high_2_idx = price.index[price_peaks[-1]]
            
            # Lấy 2 chỉ số của 2 đỉnh RSI cuối cùng
            i_high_1_idx = indicator.index[indicator_peaks[-2]]
            i_high_2_idx = indicator.index[indicator_peaks[-1]]

            # Đảm bảo chúng ta đang so sánh cùng một cặp đỉnh
            if p_high_1_idx == i_high_1_idx and p_high_2_idx == i_high_2_idx:
                # Giá tạo đỉnh sau cao hơn đỉnh trước (Higher High)
                if price[p_high_2_idx] > price[p_high_1_idx]:
                    # RSI tạo đỉnh sau thấp hơn đỉnh trước (Lower High)
                    if indicator[i_high_2_idx] < indicator[i_high_1_idx]:
                        bearish_divergence = True
    except Exception:
        pass # Bỏ qua nếu không tìm thấy đỉnh/đáy

    return bullish_divergence, bearish_divergence

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V6.0) ---
def get_rsi_score(df: pd.DataFrame, config: Dict[str, Any], trend_bias: int = 0) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên thang điểm chi tiết của RSI.
    'trend_bias' (1 cho Long, -1 cho Short, 0 cho Neutral) được truyền vào
    để xử lý logic "vượt ngưỡng 50 thuận xu hướng".
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['RSI']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        levels = cfg['score_levels']
        
        rsi_series = calculate_rsi(df, period=params['period'])
        
        if rsi_series is None or rsi_series.empty or len(rsi_series) < 2:
            return 0.0, 0.0

        last_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]
        
        # --- Logic 1: Vùng quá bán (cho Long) ---
        if last_rsi < 20:
            long_score = max(long_score, levels['deep_zone'])
        elif last_rsi < 25:
            long_score = max(long_score, levels['oversold_overbought'])
        elif last_rsi < 30:
            long_score = max(long_score, levels['entry_zone'])
            
        # --- Logic 2: Vùng quá mua (cho Short) ---
        if last_rsi > 80:
            short_score = max(short_score, levels['deep_zone'])
        elif last_rsi > 75:
            short_score = max(short_score, levels['oversold_overbought'])
        elif last_rsi > 70:
            short_score = max(short_score, levels['entry_zone'])
            
        # --- Logic 3: Tín hiệu Momentum Vùng Trung tâm (CẦN trend_bias) ---
        if trend_bias == 1: # Xu hướng H1 là TĂNG
            if prev_rsi <= 50 and last_rsi > 50:
                long_score = max(long_score, levels['cross_midline'])
            if last_rsi > 50: # Bao gồm cả trường hợp vừa vượt và trường hợp duy trì
                 long_score = max(long_score, levels['above_below_midline'])
        
        elif trend_bias == -1: # Xu hướng H1 là GIẢM
            if prev_rsi >= 50 and last_rsi < 50:
                short_score = max(short_score, levels['cross_midline'])
            if last_rsi < 50: # Bao gồm cả trường hợp vừa vượt và trường hợp duy trì
                 short_score = max(short_score, levels['above_below_midline'])

        # --- Logic 4: Phân kỳ (Divergence) - ĐÃ BAO GỒM ---
        if find_peaks is not None:
            # Chúng ta sẽ tìm phân kỳ trong 50 nến gần nhất
            lookback_period = 50 
            is_bullish_div, is_bearish_div = _find_divergence(
                price_data=df['close'], 
                indicator_data=rsi_series, 
                lookback=lookback_period
            )
            
            if is_bullish_div:
                long_score = max(long_score, levels['divergence'])
            
            if is_bearish_div:
                short_score = max(short_score, levels['divergence'])

    except Exception as e:
        # print(f"Lỗi khi tính điểm RSI: {e}")
        pass

    # Áp dụng trần điểm
    max_score = cfg.get('max_score', 30)
    return min(long_score, max_score), min(short_score, max_score)