# -*- coding: utf-8 -*-
# Tên file: download_data.py

import os
import re
import pandas as pd
from datetime import datetime
import logging

# Import các file "Giữ nguyên"
from core.exness_connector import ExnessConnector
# Import file config
import config

logger = logging.getLogger("ExnessBot")

# (Hàm này giữ nguyên như file cũ của bạn, rất tốt)
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

def _download_single_timeframe(
    connector: ExnessConnector, 
    symbol: str,
    timeframe: str, 
    output_path: str,
    months_to_download: int
) -> bool:
    """Hàm helper: Tải 1 khung thời gian cụ thể."""
    try:
        logger.info(f"--- Bắt đầu tải cho {timeframe} ---")
        minutes_per_candle = _parse_timeframe_to_minutes(timeframe)
        if minutes_per_candle == 0: return False
        
        candles_per_day = (24 * 60) / minutes_per_candle
        # Ước tính số nến (dùng 30.5 ngày/tháng)
        num_candles_to_fetch = int(candles_per_day * 30.5 * months_to_download)

        logger.info(f"Số nến {timeframe} sẽ tải (ước tính): {num_candles_to_fetch}")
        
        df = connector.get_historical_data(symbol, timeframe.lower(), num_candles_to_fetch)
        
        if df is None or df.empty:
            logger.error(f"LỖI: Không nhận được dữ liệu {timeframe} từ MT5.")
            return False

        # Lưu file
        df.to_csv(output_path, index=True, index_label='timestamp')
        logger.info(f"✅ Đã lưu thành công {len(df)} nến {timeframe} vào: {output_path}")
        return True

    except ValueError as e:
        logger.error(f"LỖI CẤU HÌNH Timeframe: {e}")
        return False
    except Exception as e:
        logger.error(f"Lỗi ngoại lệ khi tải {timeframe}: {e}")
        return False

def download_all_data():
    """
    Hàm chính (Code lại): Tải CẢ HAI khung thời gian (Trend và Entry).
    """
    logger.info("--- Bắt đầu quá trình tải dữ liệu (H1 & M15) ---")
    
    # Đọc từ config
    SYMBOL = config.SYMBOL
    TREND_TIMEFRAME = config.trend_timeframe
    ENTRY_TIMEFRAME = config.entry_timeframe
    MONTHS_TO_DOWNLOAD = config.MONTHS_TO_DOWNLOAD
    DATA_DIR = config.DATA_DIR
    
    os.makedirs(DATA_DIR, exist_ok=True) # Tạo thư mục /data nếu chưa có
    
    # Xác định đường dẫn file
    path_h1 = os.path.join(DATA_DIR, f"{SYMBOL}_{TREND_TIMEFRAME}.csv")
    path_m15 = os.path.join(DATA_DIR, f"{SYMBOL}_{ENTRY_TIMEFRAME}.csv")

    connector = ExnessConnector()
    logger.info("Bước 1: Đang kết nối tới Terminal MetaTrader 5...")
    if not connector.connect():
        logger.critical("LỖI: Không thể kết nối tới MT5. Hủy tải dữ liệu.")
        return

    logger.info("✅ Kết nối thành công!")

    # Bước 2: Tải H1
    success_h1 = _download_single_timeframe(
        connector, SYMBOL, TREND_TIMEFRAME, path_h1, MONTHS_TO_DOWNLOAD
    )
    
    # Bước 3: Tải M15
    success_m15 = _download_single_timeframe(
        connector, SYMBOL, ENTRY_TIMEFRAME, path_m15, MONTHS_TO_DOWNLOAD
    )

    connector.shutdown()
    
    if success_h1 and success_m15:
        logger.info("--- HOÀN TẤT: Đã tải thành công CẢ HAI file dữ liệu. ---")
    else:
        logger.error("--- LỖI: Không tải được đầy đủ 2 file. Vui lòng kiểm tra log. ---")

if __name__ == "__main__":
    # (Setup logger cơ bản nếu chạy file này trực tiếp)
    try:
        from core.logger_setup import setup_logging
        setup_logging()
    except ImportError:
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] - %(message)s")
        
    download_all_data()