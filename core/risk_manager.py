# -*- coding: utf-8 -*-
# File: core/risk_manager.py (v6.0 - Final)
# Đã nâng cấp để hỗ trợ Logic 3 Cấp và Fixed-Lot Sizing.

import pandas as pd
from typing import Dict, Any, Optional, Tuple
import logging

# Import hàm tính ATR từ signals
from signals.atr import calculate_atr

# Lấy logger
logger = logging.getLogger("ExnessBot")

def calculate_trade_details(
    df: pd.DataFrame,
    entry_price: float,
    signal_direction: int,
    account_balance: float,
    config: Dict[str, Any],
    score_level: int  # <-- THAM SỐ MỚI (nhận giá trị 1, 2, hoặc 3)
) -> Optional[Tuple[float, float, float]]:
    """
    Tính toán toàn bộ chi tiết cho một lệnh giao dịch: Lot Size, SL Price, TP Price.
    Tuân thủ logic 3 Cấp (về Vốn và ATR) và Fixed-Lot Sizing.
    """
    
    try:
        # === BƯỚC 1: LẤY CÁC THAM SỐ CẤU HÌNH 3 CẤP ===
        
        # Chuyển đổi level (1, 2, 3) sang index (0, 1, 2) để dùng cho list
        score_level_index = score_level - 1 
        
        # Lấy hệ số SL/TP tương ứng với cấp độ (Level) của tín hiệu (Điểm 4 & 9)
        sl_multiplier = config['ATR_SL_MULTIPLIER_LEVELS'][score_level_index]
        tp_multiplier = config['ATR_TP_MULTIPLIER_LEVELS'][score_level_index]
        atr_period = config.get('ATR_PERIOD', 14)

        # === BƯỚC 2: TÍNH KHOẢNG CÁCH SL LÝ TƯỞNG THEO ATR ===
        atr_series = calculate_atr(df, period=atr_period)
        if atr_series is None or atr_series.empty or pd.isna(atr_series.iloc[-1]):
            logger.warning("Không thể tính ATR, không thể quản lý rủi ro.")
            return None
        
        current_atr = atr_series.iloc[-1]
        sl_distance_from_atr = current_atr * sl_multiplier

        # === BƯỚC 3: ÁP DỤNG LOGIC MIN/MAX SL (Lọc an toàn của bạn) ===
        
        # Logic này được giữ nguyên từ file cũ của bạn (nó rất tốt)
        max_sl_distance_usd = entry_price * (config.get('MAX_SL_PERCENT_OF_PRICE', 5.0) / 100.0)
        min_sl_distance_usd = entry_price * (config.get('MIN_SL_PERCENT_OF_PRICE', 0.5) / 100.0)

        final_sl_distance = 0.0
        
        # BỘ LỌC 1: Thị trường "điên" (ATR SL quá xa)
        if sl_distance_from_atr > max_sl_distance_usd:
            logger.warning(f"Bỏ qua lệnh: ATR SL ({sl_distance_from_atr:.2f}) > MAX % ({max_sl_distance_usd:.2f})")
            return None
        
        # BỘ LỌC 2: Thị trường "tĩnh" (ATR SL quá gần)
        if sl_distance_from_atr < min_sl_distance_usd:
            if config.get('FORCE_MINIMUM_DISTANCE', True):
                final_sl_distance = min_sl_distance_usd # Ép dùng SL tối thiểu
                logger.debug(f"Thông tin: ATR SL ({sl_distance_from_atr:.2f}) < MIN. Sử dụng MIN SL = {final_sl_distance}")
            else:
                logger.warning(f"Bỏ qua lệnh: ATR SL ({sl_distance_from_atr:.2f}) < MIN.")
                return None
        else:
            final_sl_distance = sl_distance_from_atr # Dùng SL theo ATR

        # === BƯỚC 4: TÍNH GIÁ SL VÀ TP CUỐI CÙNG (Theo Logic 3 Cấp) ===
        is_long = signal_direction == 1
        sl_price, tp_price = 0.0, 0.0
        
        if is_long:
            sl_price = entry_price - final_sl_distance
            # Tính TP dựa trên tỷ lệ R:R (được định nghĩa bằng 2 hệ số SL/TP)
            tp_distance = final_sl_distance * (tp_multiplier / sl_multiplier)
            tp_price = entry_price + tp_distance
        else: # SHORT
            sl_price = entry_price + final_sl_distance
            tp_distance = final_sl_distance * (tp_multiplier / sl_multiplier)
            tp_price = entry_price - tp_distance

        # === BƯỚC 5: TÍNH TOÁN LOT SIZE (Hỗ trợ Fixed-Lot & 3 Cấp Risk - Điểm 5) ===
        
        lot_size = 0.0
        forced_min_lot = config.get('FORCED_MIN_LOT_SIZE', 0.1)

        if config.get('ENABLE_FIXED_LOT_SIZING', False):
            # --- Chế độ 1: Fixed-Lot Sizing (Điểm 5) ---
            lot_size = config['FIXED_LOT_LEVELS'][score_level_index]
            logger.debug(f"Chế độ Fixed-Lot: Sử dụng {lot_size} lot cho Cấp {score_level}.")
        
        else:
            # --- Chế độ 2: Risk Percent (Nâng cấp 3 Cấp) ---
            risk_percent = config['RISK_PERCENT_LEVELS'][score_level_index]
            risk_amount_usd = account_balance * (risk_percent / 100.0)
            
            # Tính Lot Size lý tưởng (Công thức này giả định 1 Lot = 1 ETH)
            ideal_lot_size = risk_amount_usd / final_sl_distance
            
            logger.debug(f"Chế độ Risk %: Cấp {score_level} (Risk {risk_percent}%) -> Lot lý tưởng: {ideal_lot_size:.4f}")

            # 3. Ép Lot Min (Cho vốn bé - Logic của bạn được giữ nguyên)
            if ideal_lot_size < forced_min_lot:
                if config.get('ENABLE_FORCE_MIN_LOT', True):
                    actual_risk_usd = final_sl_distance * forced_min_lot
                    actual_risk_percent = (actual_risk_usd / account_balance) * 100
                    
                    if actual_risk_percent <= config.get('MAX_FORCED_RISK_PERCENT', 5.0):
                        lot_size = forced_min_lot # Chấp nhận rủi ro cao hơn (ví dụ 1.5%)
                        logger.debug(f"Lot lý tưởng ({ideal_lot_size:.4f}) < Min. Ép dùng {lot_size} lot. Rủi ro thực tế: {actual_risk_percent:.2f}%")
                    else:
                        logger.warning(f"Bỏ qua lệnh: Rủi ro khi ép lot ({actual_risk_percent:.2f}%) > ngưỡng ({config.get('MAX_FORCED_RISK_PERCENT', 5.0)}%)")
                        return None
                else:
                    logger.warning(f"Bỏ qua lệnh: Lot lý tưởng ({ideal_lot_size:.4f}) < Min ({forced_min_lot}) và chế độ ép lot đang TẮT.")
                    return None
            else:
                lot_size = ideal_lot_size

        # Làm tròn lot size (Exness 2 chữ số thập phân)
        lot_size = round(lot_size, 2)
        
        if lot_size < forced_min_lot:
            # Check lại lần cuối sau khi làm tròn
            logger.warning(f"Bỏ qua lệnh: Lot size cuối cùng ({lot_size}) < mức tối thiểu ({forced_min_lot}).")
            return None

        logger.info(f"Tính toán rủi ro Cấp {score_level} thành công: Lot={lot_size}, SL={sl_price:.4f}, TP={tp_price:.4f}")
        return lot_size, sl_price, tp_price

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng trong calculate_trade_details: {e}", exc_info=True)
        return None
