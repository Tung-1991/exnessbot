# -*- coding: utf-8 -*-
# Tên file: main.py

import logging
import sys
import os
import time
import pandas as pd
import threading
from datetime import datetime, timedelta
import re

# --- Cài đặt sys.path ---
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
except Exception as e:
    print(f"Lỗi cài đặt sys.path: {e}")
    sys.exit(1)

# --- Import các file "Cốt lõi" ---
from core.logger_setup import setup_logging
from core.trade_manager import TradeManager 
from core.exness_connector import ExnessConnector 

# --- Import file Config ---
import config

# --- Cài đặt Logger ---
setup_logging()
logger = logging.getLogger("ExnessBot")

# ==============================================================================
# HÀM HELPER - ĐỒNG HỒ ĐỒNG BỘ
# ==============================================================================

def _parse_timeframe_to_minutes(tf_str: str) -> int:
    """Helper: Chuyển đổi 'H1', 'M15' sang số phút."""
    tf_str = tf_str.lower()
    match = re.match(r"(\d+)([mhd])", tf_str)
    if not match:
        raise ValueError(f"Khung thời gian không hợp lệ: {tf_str}")
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm': return value
    elif unit == 'h': return value * 60
    elif unit == 'd': return value * 24 * 60
    return 0

def _get_sleep_time_to_next_candle(timeframe_str: str) -> int:
    """
    Tính toán số giây ngủ "thông minh" để chờ nến tiếp theo đóng.
    """
    try:
        minutes = _parse_timeframe_to_minutes(timeframe_str)
        if minutes == 0: return 60 # Dự phòng
        
        now = datetime.now()
        
        # Đặt 1 giây đệm để đảm bảo nến đã đóng
        next_run = now.replace(second=1, microsecond=0)
        
        # Làm tròn phút lên mốc tiếp theo (ví dụ: M15)
        minute_to_round = (now.minute // minutes) * minutes + minutes
        
        if minute_to_round >= 60:
            next_run = next_run.replace(minute=0, hour=now.hour + 1)
            # Xử lý qua ngày
            if next_run.hour == 0:
                next_run += timedelta(days=1)
        else:
            next_run = next_run.replace(minute=minute_to_round)
            
        sleep_seconds = (next_run - now).total_seconds()
        
        # Đảm bảo ngủ ít nhất 1 giây
        return max(1, int(sleep_seconds))
        
    except Exception as e:
        logger.error(f"Lỗi _get_sleep_time_to_next_candle: {e}. Dùng 60s mặc định.")
        return 60

# ==============================================================================
# TASK 1: LUỒNG TÍN HIỆU & TSL (CHẬM - ĐỒNG BỘ VỚI NẾN)
# ==============================================================================
def signal_task(tm: TradeManager, connector: ExnessConnector, config_dict: dict):
    """
    Luồng này chịu trách nhiệm cho mọi tính toán nặng:
    1. Tải dữ liệu
    2. Tìm tín hiệu vào lệnh
    3. Dời SL (Trailing Stop)
    Chỉ chạy khi đóng nến (ví dụ: mỗi 15 phút).
    """
    logger.info("[Luồng 1 - Signal/TSL] Bắt đầu... Đồng bộ với nến.")
    while True:
        try:
            # 1. Đồng bộ với nến (Ngủ cho đến khi nến đóng)
            entry_tf = config_dict["entry_timeframe"]
            sleep_sec = _get_sleep_time_to_next_candle(entry_tf)
            logger.info(f"[Luồng 1] Đã đồng bộ. Ngủ {sleep_sec}s chờ nến {entry_tf} đóng.")
            time.sleep(sleep_sec)
            
            logger.info(f"[Luồng 1] Thức dậy. Đang tải dữ liệu nến sạch...")
            
            # 2. Lấy dữ liệu
            data_h1 = connector.get_historical_data(config_dict["SYMBOL"], config_dict["trend_timeframe"].lower(), config_dict["NUM_H1_BARS"])
            data_m15 = connector.get_historical_data(config_dict["SYMBOL"], config_dict["entry_timeframe"].lower(), config_dict["NUM_M15_BARS"])

            if data_h1 is None or data_m15 is None or data_h1.empty or data_m15.empty:
                logger.warning("[Luồng 1] Không có dữ liệu, bỏ qua vòng lặp này.")
                continue

            # 3. Logic chính
            # A. Kiểm tra và Mở lệnh MỚI
            tm.check_and_open_new_trade(data_h1, data_m15)
            
            # B. Cập nhật TSL (Dời SL) cho các lệnh CŨ
            tm.update_all_trades(data_h1, data_m15)
            
        except Exception as e:
            logger.critical(f"[Luồng 1] Lỗi nghiêm trọng: {e}", exc_info=True)
            time.sleep(60) # Chờ 1 phút nếu có lỗi nghiêm trọng

# ==============================================================================
# TASK 2: LUỒNG ĐỐI CHIẾU (NHANH - REALTIME)
# ==============================================================================
def reconcile_task(tm: TradeManager, connector: ExnessConnector, config_dict: dict):
    """
    (ĐÃ SỬA TÊN HÀM)
    Luồng này chạy rất nhanh (ví dụ 5s/lần).
    Nhiệm vụ duy nhất: Đối chiếu (Reconcile) xem lệnh trên Exness còn sống hay chết.
    Không tải dữ liệu, không tính toán TSL.
    """
    sleep_interval = config_dict["LOOP_SLEEP_SECONDS"]
    logger.info(f"[Luồng 2 - Reconcile] Bắt đầu... Chạy mỗi {sleep_interval} giây.")
    while True:
        try:
            start_time = time.time()
            
            # Gọi hàm nhẹ nhàng để đối chiếu danh sách lệnh
            tm.reconcile_live_trades()

            # Ngủ đúng thời gian quy định (trừ đi thời gian thực thi)
            elapsed = time.time() - start_time
            sleep_time = max(0, sleep_interval - elapsed)
            
            if sleep_time > 0:
                time.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"[Luồng 2 - Reconcile] Lỗi: {e}", exc_info=False)
            time.sleep(sleep_interval)

# ==============================================================================
# HÀM CHẠY CHÍNH
# ==============================================================================
def run_live_bot():
    """
    Hàm Vòng lặp 24/7 (Realtime) - Kiến trúc 2 Luồng Tối Ưu.
    """
    logger.info("--- KHỞI ĐỘNG [CHẾ ĐỘ LIVE] - KIẾN TRÚC 2 LUỒNG TỐI ƯU ---")

    try:
        # === [SỬA LỖI] Chuyển module config sang dictionary ===
        config_dict = {key: getattr(config, key) 
                       for key in dir(config) 
                       if not key.startswith('__')}
        # === [HẾT SỬA LỖI] ===
        
        # Khởi tạo TradeManager với config_dict
        trade_manager = TradeManager(config=config_dict, mode="live")
        
        # Tạo 1 kết nối duy nhất cho cả 2 luồng
        data_connector = ExnessConnector()
        if not data_connector.connect():
            raise ConnectionError("Không thể tạo data_connector chính.")
            
    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi khởi tạo: {e}", exc_info=True)
        logger.critical("Bot không thể chạy. Vui lòng kiểm tra kết nối MT5.")
        return # Dừng

    # Khởi chạy 2 Luồng
    # Luồng 1: Signal + TSL (Chậm, nặng)
    thread1 = threading.Thread(target=signal_task, args=(trade_manager, data_connector, config_dict), daemon=True)
    
    # Luồng 2: Reconcile (Nhanh, nhẹ)
    thread2 = threading.Thread(target=reconcile_task, args=(trade_manager, data_connector, config_dict), daemon=True)

    thread1.start()
    thread2.start()

    logger.info("Bot đang chạy với 2 Luồng song song. Nhấn Ctrl+C để thoát.")
    
    # Giữ luồng chính chạy (để bắt Ctrl+C)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Phát hiện Ctrl+C. Đang tắt bot...")
        data_connector.shutdown()
        logger.info("Đã đóng kết nối MT5. Tạm biệt.")


if __name__ == "__main__":
    run_live_bot()