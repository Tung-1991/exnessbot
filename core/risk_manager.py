# File: core/risk_manager.py (ĐÃ NÂNG CẤP LÊN LOGIC %)

import pandas as pd
from typing import Dict, Any, Optional, Tuple
from signals.atr import calculate_atr

def calculate_trade_details(
    df: pd.DataFrame,
    entry_price: float,
    signal_direction: int,
    account_balance: float,
    config: Dict[str, Any]
) -> Optional[Tuple[float, float, float]]:
    """
    Tính toán toàn bộ chi tiết cho một lệnh giao dịch: Lot Size, SL Price, TP Price.
    (ĐÃ NÂNG CẤP LÊN LOGIC % FILTER)
    """
    
    # === BƯỚC 1: LẤY CÁC THAM SỐ CẤU HÌNH ===
    atr_cfg = config['INDICATORS_CONFIG']['ATR']
    
    # === BƯỚC 2: TÍNH KHOẢNG CÁCH SL LÝ TƯỞNG THEO ATR ===
    atr_series = calculate_atr(df, period=atr_cfg['PERIOD'])
    if atr_series is None or atr_series.empty:
        return None
    
    current_atr = atr_series.iloc[-1]
    sl_distance_from_atr = current_atr * atr_cfg['SL_MULTIPLIER']

    # === BƯỚC 3: ÁP DỤNG LOGIC MIN/MAX SL (LOGIC % MỚI) ===
    
    # Tính toán giới hạn MIN/MAX (bằng USD) dựa trên % giá vào lệnh
    # Đây là logic "dynamic" mày muốn
    max_sl_distance_usd = entry_price * (config.get('MAX_SL_PERCENT_OF_PRICE', 5.0) / 100.0)
    min_sl_distance_usd = entry_price * (config.get('MIN_SL_PERCENT_OF_PRICE', 0.5) / 100.0)

    final_sl_distance = 0
    
    # BỘ LỌC 1: Thị trường "điên" (ATR SL quá xa)
    if sl_distance_from_atr > max_sl_distance_usd:
        # (Nếu mày muốn tắt, đặt MAX_SL_PERCENT_OF_PRICE = 9999)
        # print(f"Bỏ qua lệnh: ATR SL ({sl_distance_from_atr:.2f}) > MAX % ({max_sl_distance_usd:.2f})")
        return None
    
    # BỘ LỌC 2: Thị trường "tĩnh" (ATR SL quá gần)
    if sl_distance_from_atr < min_sl_distance_usd:
        if config.get('FORCE_MINIMUM_DISTANCE', True):
            final_sl_distance = min_sl_distance_usd # Ép dùng SL tối thiểu
            # print(f"Thông tin: ATR SL ({sl_distance_from_atr:.2f}) < MIN. Sử dụng MIN SL = {final_sl_distance}")
        else:
            # print(f"Bỏ qua lệnh: ATR SL ({sl_distance_from_atr:.2f}) < MIN.")
            return None
    else:
        final_sl_distance = sl_distance_from_atr # Dùng SL theo ATR

    # === BƯỚC 4: TÍNH GIÁ SL VÀ TP CUỐI CÙNG ===
    is_long = signal_direction == 1
    sl_price, tp_price = 0.0, 0.0
    
    if is_long:
        sl_price = entry_price - final_sl_distance
        # Tính TP dựa trên tỷ lệ R:R (SL_MULTIPLIER / TP_MULTIPLIER)
        tp_distance = final_sl_distance * (atr_cfg['TP_MULTIPLIER'] / atr_cfg['SL_MULTIPLIER'])
        tp_price = entry_price + tp_distance
    else: # SHORT
        sl_price = entry_price + final_sl_distance
        tp_distance = final_sl_distance * (atr_cfg['TP_MULTIPLIER'] / atr_cfg['SL_MULTIPLIER'])
        tp_price = entry_price - tp_distance

    # === BƯỚC 5: TÍNH TOÁN LOT SIZE (VẪN LÀ "VUA") ===
    
    # 1. Tính số tiền mày muốn lỗ (USD)
    risk_amount_usd = account_balance * (config['RISK_PERCENT'] / 100)
    
    # 2. Tính Lot Size (Công thức này đã đúng vì 1 Lot = 1 ETH)
    # Lot Size = (Số Tiền Lỗ Mày Muốn) / (Khoảng Cách SL bằng $)
    ideal_lot_size = risk_amount_usd / final_sl_distance

    # 3. Ép Lot Min (Cho vốn bé)
    forced_min_lot = config.get('FORCED_MIN_LOT_SIZE', 0.1)
    
    if ideal_lot_size < forced_min_lot:
        if config.get('ENABLE_FORCE_MIN_LOT', True):
            # Kiểm tra xem ép lot min thì có cháy tài khoản không
            actual_risk_usd = final_sl_distance * forced_min_lot
            actual_risk_percent = (actual_risk_usd / account_balance) * 100
            
            if actual_risk_percent <= config.get('MAX_FORCED_RISK_PERCENT', 5.0):
                lot_size = forced_min_lot # Chấp nhận rủi ro cao hơn (ví dụ 1.5%)
            else:
                # print(f"Bỏ qua lệnh: Rủi ro khi force lot ({actual_risk_percent:.2f}%) > ngưỡng ({config.get('MAX_FORCED_RISK_PERCENT', 5.0)}%)")
                return None
        else:
            return None # Lệnh quá bé, hủy
    else:
        lot_size = ideal_lot_size

    # Làm tròn lot size (Exness 2 chữ số thập phân, min 0.1)
    lot_size = round(lot_size, 2)
    
    if lot_size < forced_min_lot:
         # print(f"Bỏ qua lệnh: Lot size cuối cùng ({lot_size}) < mức tối thiểu sàn yêu cầu.")
         return None

    return lot_size, sl_price, tp_price