# Tên file: signals/bollinger_bands.py (Nâng cấp V6.0 - FINAL)
# Mục đích: Tính toán Bollinger Bands và chấm điểm dựa trên 5 cấp độ logic
#          để hỗ trợ cả chiến lược Trend-Following và Mean-Reversion.

import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, Any

# --- HÀM TÍNH TOÁN BB GỐC ---
def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    """
    Tính toán 3 đường của chỉ báo Bollinger Bands.
    (Hàm này giữ nguyên như file gốc của bạn - nó đã chuẩn)
    """
    if 'close' not in df.columns:
        return None

    middle_band = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    
    return upper_band, middle_band, lower_band

# --- HÀM TÍNH ĐIỂM SỐ CHÍNH (LOGIC MỚI V6.0) ---
def get_bb_score(df: pd.DataFrame, config: Dict[str, Any], trend_bias: int = 0) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên 5 cấp độ thang điểm của BB.
    'trend_bias' (1 cho Long, -1 cho Short, 0 cho Neutral) được truyền vào
    để hỗ trợ logic "Middle Band Rejection" và "Walking the Band".
    """
    long_score, short_score = 0.0, 0.0
    
    try:
        # ĐỌC CONFIG V6.0
        cfg = config['ENTRY_SIGNALS_CONFIG']['BOLLINGER_BANDS']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        params = cfg['params']
        levels = cfg['score_levels']
        
        bands = calculate_bollinger_bands(
            df, 
            period=params['period'], 
            std_dev=params['std_dev']
        )
        if bands is None:
            return 0.0, 0.0

        upper_band, middle_band, lower_band = bands
        
        # Cần ít nhất 3 nến để so sánh
        if len(df) < 3 or pd.isna(upper_band.iloc[-1]) or pd.isna(lower_band.iloc[-1]):
            return 0.0, 0.0
            
        # Lấy dữ liệu 3 cây nến gần nhất
        prev_candle_2 = df.iloc[-3]
        prev_candle = df.iloc[-2]
        last_candle = df.iloc[-1]
        
        # --- Logic 1: Squeeze & Breakout (Tín hiệu mạnh nhất, Ưu tiên 1) ---
        # Định nghĩa Squeeze: Độ rộng dải băng hiện tại là hẹp nhất trong 50 nến
        band_width = upper_band - lower_band
        # (Sử dụng 1.05 để cho phép một chút "khoan dung" thay vì .min() tuyệt đối)
        is_squeeze = band_width.iloc[-1] <= (band_width.rolling(window=50).min().iloc[-1] * 1.05)

        if is_squeeze:
            # Breakout TĂNG từ Squeeze
            if last_candle['close'] > upper_band.iloc[-1] and prev_candle['close'] <= upper_band.iloc[-2]:
                long_score = max(long_score, levels['squeeze_breakout'])
            # Breakout GIẢM từ Squeeze
            elif last_candle['close'] < lower_band.iloc[-1] and prev_candle['close'] >= lower_band.iloc[-2]:
                short_score = max(short_score, levels['squeeze_breakout'])
        
        # --- Chỉ kiểm tra các logic khác nếu KHÔNG CÓ SQUEEZE BREAKOUT ---
        if long_score == 0 and short_score == 0:
            
            # --- Logic 2: "Walking the Band" (Bám dải - Tín hiệu Trend-Following, Ưu tiên 2) ---
            # Điều kiện: Xu hướng H1 thuận (trend_bias != 0), và 2 nến gần nhất đều đóng cửa BÊN NGOÀI
            if trend_bias == 1 and \
               last_candle['close'] > upper_band.iloc[-1] and \
               prev_candle['close'] > upper_band.iloc[-2]:
                long_score = max(long_score, levels['walking_the_band'])
            
            elif trend_bias == -1 and \
                 last_candle['close'] < lower_band.iloc[-1] and \
                 prev_candle['close'] < lower_band.iloc[-2]:
                short_score = max(short_score, levels['walking_the_band'])

            # --- Logic 3: Reversal Confirmation (Xác nhận Đảo chiều - Mean-Reversion, Ưu tiên 3) ---
            # Điều kiện: Nến trước đó đóng cửa BÊN NGOÀI, nến hiện tại đóng cửa BÊN TRONG
            # (Chỉ kích hoạt nếu Logic 2 không xảy ra)
            if long_score == 0 and \
               prev_candle['close'] < lower_band.iloc[-2] and \
               last_candle['close'] > lower_band.iloc[-1] and \
               last_candle['close'] > last_candle['open']: # Phải là nến tăng xác nhận
                long_score = max(long_score, levels['reversal_confirmation'])

            elif short_score == 0 and \
                 prev_candle['close'] > upper_band.iloc[-2] and \
                 last_candle['close'] < upper_band.iloc[-1] and \
                 last_candle['close'] < last_candle['open']: # Phải là nến giảm xác nhận
                short_score = max(short_score, levels['reversal_confirmation'])

            # --- Logic 4: Middle Band Rejection (Bật lại từ dải giữa - Tín hiệu Trend-Following, Ưu tiên 4) ---
            # Điều kiện: Xu hướng H1 thuận (trend_bias != 0), giá chạm dải giữa và bật lại
            if long_score == 0 and trend_bias == 1 and \
               last_candle['low'] <= middle_band.iloc[-1] and \
               last_candle['close'] > middle_band.iloc[-1] and \
               last_candle['close'] > last_candle['open']: # Phải là nến tăng bật lên
                long_score = max(long_score, levels['middle_band_rejection'])
                
            elif short_score == 0 and trend_bias == -1 and \
                 last_candle['high'] >= middle_band.iloc[-1] and \
                 last_candle['close'] < middle_band.iloc[-1] and \
                 last_candle['close'] < last_candle['open']: # Phải là nến giảm bật xuống
                short_score = max(short_score, levels['middle_band_rejection'])

            # --- Logic 5: Wick Touch (Râu nến chạm - Tín hiệu Mean-Reversion yếu, Ưu tiên 5) ---
            # Điều kiện: Râu nến chạm, thân nến vẫn ở bên trong.
            if long_score == 0 and \
               last_candle['low'] <= lower_band.iloc[-1] and \
               last_candle['close'] > lower_band.iloc[-1]: # Thân nến đóng bên trong
                long_score = max(long_score, levels['wick_touch'])
                
            elif short_score == 0 and \
                 last_candle['high'] >= upper_band.iloc[-1] and \
                 last_candle['close'] < upper_band.iloc[-1]: # Thân nến đóng bên trong
                short_score = max(short_score, levels['wick_touch'])
                
    except Exception as e:
        # print(f"Lỗi khi tính điểm Bollinger Bands: {e}")
        pass

    # Áp dụng trần điểm
    max_score = cfg.get('max_score', 30)
    return min(long_score, max_score), min(short_score, max_score)