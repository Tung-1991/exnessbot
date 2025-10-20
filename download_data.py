# download_data.py (ĐÃ SỬA LỖI IMPORT)

import os
import pandas as pd
from datetime import datetime
import re

# Giả sử file exness_connector.py nằm trong thư mục /core
try:
    # SỬA LỖI IMPORT: Trỏ vào thư mục core
    from core.exness_connector import ExnessConnector
except ImportError:
    print("LỖI: Không tìm thấy 'core/exness_connector.py'.")
    print("Hãy đảm bảo bạn đang chạy file này từ thư mục gốc (exnessbot-main/).")
    exit()

# --- CẤU HÌNH ---
CONFIG = {
    "SYMBOL": "BTCUSD",
    "TIMEFRAME": "15m",  # '1m', '5m', '15m', '1h', '4h', '1d'
    "MONTHS_TO_DOWNLOAD": 6,
    "OUTPUT_FOLDER": "data",
    "OUTPUT_FILENAME": "ETHUSD_15m_6M.csv" # Tên file mà backtester.py cần
}

def parse_timeframe_to_minutes(tf_str: str) -> int:
    """
    Hàm chuyển đổi chuỗi timeframe (ví dụ: '5m', '1h', '1d') sang số phút.
    """
    tf_str = tf_str.lower()
    match = re.match(r"(\d+)([mhd])", tf_str)
    if not match:
        raise ValueError(f"Khung thời gian không hợp lệ: {tf_str}")
    
    value, unit = int(match.group(1)), match.group(2)
    
    if unit == 'm':
        return value
    elif unit == 'h':
        return value * 60
    elif unit == 'd':
        return value * 24 * 60
    return 0

def download_data():
    """Kết nối MT5, tải dữ liệu và lưu ra file CSV."""
    
    print("--- Bắt đầu quá trình tải dữ liệu từ Exness (MT5) ---")
    
    try:
        minutes_per_candle = parse_timeframe_to_minutes(CONFIG['TIMEFRAME'])
        if minutes_per_candle == 0: return
        
        candles_per_day = (24 * 60) / minutes_per_candle
        num_candles_to_fetch = int(candles_per_day * 30.5 * CONFIG['MONTHS_TO_DOWNLOAD'])
    except ValueError as e:
        print(f"LỖI CẤU HÌNH: {e}")
        return

    print(f"Cặp tiền: {CONFIG['SYMBOL']}")
    print(f"Khung thời gian: {CONFIG['TIMEFRAME']}")
    print(f"Số tháng: {CONFIG['MONTHS_TO_DOWNLOAD']}")
    print(f"Số nến sẽ tải (ước tính): {num_candles_to_fetch}")

    connector = ExnessConnector()

    print("\nBước 1: Đang kết nối tới Terminal MetaTrader 5...")
    if not connector.connect():
        print("LỖI: Không thể kết nối tới MT5. Hãy đảm bảo bạn đã mở sẵn Terminal MT5.")
        return

    print("✅ Kết nối thành công!")

    print(f"\nBước 2: Đang tải dữ liệu cho {CONFIG['SYMBOL']}...")
    df = connector.get_historical_data(
        CONFIG['SYMBOL'],
        CONFIG['TIMEFRAME'],
        num_candles_to_fetch
    )

    connector.shutdown() # Ngắt kết nối ngay sau khi lấy xong

    if df is None or df.empty:
        print("LỖI: Không nhận được dữ liệu từ MT5. Có thể do symbol sai hoặc không đủ dữ liệu trên server.")
        return

    print(f"✅ Đã tải thành công {len(df)} nến.")

    # Bước 3: Lưu file
    output_path = os.path.join(CONFIG['OUTPUT_FOLDER'], CONFIG['OUTPUT_FILENAME'])
    os.makedirs(CONFIG['OUTPUT_FOLDER'], exist_ok=True) 

    df.to_csv(output_path)

    print(f"\n--- HOÀN TẤT ---")
    print(f"Dữ liệu đã được lưu thành công tại: {output_path}")


if __name__ == "__main__":
    download_data()