# download_data.py (Nâng cấp MTF - Tự động tải 2 khung thời gian)

import os
import pandas as pd
from datetime import datetime
import re
# Import config chính của bot
import config as bot_config
from core.exness_connector import ExnessConnector

# --- CẤU HÌNH CHUNG ---
SYMBOL = bot_config.SYMBOL
MONTHS_TO_DOWNLOAD = 6 # Bạn có thể chỉnh số tháng ở đây
OUTPUT_FOLDER = "data"

def parse_timeframe_to_minutes(tf_str: str) -> int:
    # (Giữ nguyên hàm này)
    tf_str = tf_str.lower()
    match = re.match(r"(\d+)([mhd])", tf_str)
    if not match:
        raise ValueError(f"Khung thời gian không hợp lệ: {tf_str}")
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm': return value
    elif unit == 'h': return value * 60
    elif unit == 'd': return value * 24 * 60
    return 0

def download_single_timeframe(connector: ExnessConnector, timeframe: str):
    """Tải dữ liệu cho một khung thời gian cụ thể."""
    print(f"\n--- Bắt đầu tải dữ liệu cho {timeframe} ---")
    try:
        minutes_per_candle = parse_timeframe_to_minutes(timeframe)
        if minutes_per_candle == 0: return False
        candles_per_day = (24 * 60) / minutes_per_candle
        num_candles_to_fetch = int(candles_per_day * 30.5 * MONTHS_TO_DOWNLOAD)
    except ValueError as e:
        print(f"LỖI CẤU HÌNH Timeframe: {e}")
        return False

    print(f"Khung thời gian: {timeframe}")
    print(f"Số nến sẽ tải (ước tính): {num_candles_to_fetch}")

    print(f"Đang tải dữ liệu cho {SYMBOL}...")
    df = connector.get_historical_data(SYMBOL, timeframe, num_candles_to_fetch)

    if df is None or df.empty:
        print(f"LỖI: Không nhận được dữ liệu {timeframe} từ MT5.")
        return False

    print(f"✅ Đã tải thành công {len(df)} nến {timeframe}.")

    # Lưu file
    # Tạo tên file động dựa trên timeframe
    output_filename = f"{SYMBOL}_{timeframe}_{MONTHS_TO_DOWNLOAD}M.csv"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    df.to_csv(output_path)
    print(f"Dữ liệu {timeframe} đã được lưu tại: {output_path}")
    return True

def download_all_data():
    """Tải dữ liệu cho cả TIMEFRAME và TREND_TIMEFRAME từ config."""
    print("--- Bắt đầu quá trình tải dữ liệu MTF từ Exness (MT5) ---")
    print(f"Cặp tiền: {SYMBOL}")
    print(f"Số tháng: {MONTHS_TO_DOWNLOAD}")

    connector = ExnessConnector()
    print("\nBước 1: Đang kết nối tới Terminal MetaTrader 5...")
    if not connector.connect():
        print("LỖI: Không thể kết nối tới MT5.")
        return

    print("✅ Kết nối thành công!")

    # Bước 2: Tải data cho TIMEFRAME chính
    success1 = download_single_timeframe(connector, bot_config.TIMEFRAME)

    # Bước 3: Tải data cho TREND_TIMEFRAME
    success2 = False
    if bot_config.TIMEFRAME != bot_config.TREND_TIMEFRAME: # Chỉ tải nếu khác nhau
        success2 = download_single_timeframe(connector, bot_config.TREND_TIMEFRAME)
    else:
        success2 = True # Coi như thành công nếu timeframe giống nhau

    connector.shutdown() # Ngắt kết nối

    if success1 and success2:
        print("\n--- HOÀN TẤT TẢI DỮ LIỆU MTF ---")
    else:
        print("\n--- TẢI DỮ LIỆU MTF THẤT BẠI ---")


if __name__ == "__main__":
    download_all_data()