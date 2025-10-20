# File: core/risk_manager.py (ĐÃ SỬA LỖI)

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
    """
    # === BƯỚC 1: LẤY CÁC THAM SỐ CẤU HÌNH (ĐÃ SỬA) ===
    # Lấy trực tiếp từ config, không qua 'RISK_MANAGEMENT' nữa
    atr_cfg = config['INDICATORS_CONFIG']['ATR']
    
    # === BƯỚC 2: TÍNH KHOẢNG CÁCH SL LÝ TƯỞNG THEO ATR ===
    atr_series = calculate_atr(df, period=atr_cfg['PERIOD'])
    if atr_series is None or atr_series.empty:
        return None
    
    current_atr = atr_series.iloc[-1]
    sl_distance_from_atr = current_atr * atr_cfg['SL_MULTIPLIER']

    # === BƯỚC 3: ÁP DỤNG LOGIC MIN/MAX SL (ĐÃ SỬA) ===
    final_sl_distance = 0
    
    if sl_distance_from_atr > config['MAX_SL_DISTANCE']:
        print(f"Bỏ qua lệnh: ATR SL ({sl_distance_from_atr:.2f}) > MAX ({config['MAX_SL_DISTANCE']})")
        return None
    
    if sl_distance_from_atr < config['MIN_SL_DISTANCE']:
        if config['FORCE_MINIMUM_DISTANCE']:
            final_sl_distance = config['MIN_SL_DISTANCE']
            print(f"Thông tin: ATR SL ({sl_distance_from_atr:.2f}) < MIN. Sử dụng MIN SL = {final_sl_distance}")
        else:
            print(f"Bỏ qua lệnh: ATR SL ({sl_distance_from_atr:.2f}) < MIN.")
            return None
    else:
        final_sl_distance = sl_distance_from_atr

    # === BƯỚC 4: TÍNH GIÁ SL VÀ TP CUỐI CÙNG ===
    is_long = signal_direction == 1
    if is_long:
        sl_price = entry_price - final_sl_distance
        tp_distance = final_sl_distance * (atr_cfg['TP_MULTIPLIER'] / atr_cfg['SL_MULTIPLIER'])
        tp_price = entry_price + tp_distance
    else: # SHORT
        sl_price = entry_price + final_sl_distance
        tp_distance = final_sl_distance * (atr_cfg['TP_MULTIPLIER'] / atr_cfg['SL_MULTIPLIER'])
        tp_price = entry_price - tp_distance

    # === BƯỚC 5: TÍNH TOÁN LOT SIZE (ĐÂY LÀ PHẦN LOGIC MỚI CHO VỐN BÉ) ===
    
    # Ưu tiên #1: Thử tính theo RISK_PERCENT
    risk_amount_usd = account_balance * (config['RISK_PERCENT'] / 100)
    # Giả định giá trị 1 điểm = $1, 1 lot = 1 ETH. Sẽ thay bằng hàm connector sau.
    ideal_lot_size = risk_amount_usd / final_sl_distance

    # Ưu tiên #2 & #3: Nếu lot tính ra quá nhỏ, thử "cố đấm ăn xôi"
    if ideal_lot_size < config['FORCED_MIN_LOT_SIZE'] and config['ENABLE_FORCE_MIN_LOT']:
        print(f"Thông tin: Lot lý tưởng ({ideal_lot_size:.3f}) < lot tối thiểu. Thử chế độ 'Force Min Lot'.")
        forced_lot_size = config['FORCED_MIN_LOT_SIZE']
        actual_risk_usd = final_sl_distance * forced_lot_size
        actual_risk_percent = (actual_risk_usd / account_balance) * 100
        
        if actual_risk_percent <= config['MAX_FORCED_RISK_PERCENT']:
            print(f"CẢNH BÁO: Vào lệnh với lot tối thiểu {forced_lot_size}. Rủi ro thực tế: {actual_risk_percent:.2f}% (${actual_risk_usd:.2f})")
            lot_size = forced_lot_size
        else:
            print(f"Bỏ qua lệnh: Rủi ro khi force lot ({actual_risk_percent:.2f}%) > ngưỡng cho phép ({config['MAX_FORCED_RISK_PERCENT']}%)")
            return None
    else:
        lot_size = ideal_lot_size

    # Làm tròn lot size về 2 chữ số thập phân
    lot_size = round(lot_size, 2)
    
    if lot_size < config['FORCED_MIN_LOT_SIZE']:
         print(f"Bỏ qua lệnh: Lot size cuối cùng ({lot_size}) < mức tối thiểu sàn yêu cầu.")
         return None

    return lot_size, sl_price, tp_price