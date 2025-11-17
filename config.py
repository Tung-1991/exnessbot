# -*- coding: utf-8 -*-
# Tên file: config.py

# === 1. HỆ THỐNG ===
LOOP_SLEEP_SECONDS = 5      # (Giây) Thời gian nghỉ của luồng TSL
NUM_H1_BARS = 70            # Số nến 1H (Trend) cần tải
NUM_M15_BARS = 70           # Số nến 15M (Entry) cần tải

# === 2. GIAO DỊCH CHUNG ===
SYMBOL = "ETHUSD"           # Cặp tiền giao dịch
CONTRACT_SIZE = 1           # Kích thước hợp đồng (ví dụ: 1 ETH/lot)
max_trade = 1               # Số lệnh tối đa cùng lúc
trend_timeframe = "1H"      # Khung thời gian xét Trend
entry_timeframe = "15M"     # Khung thời gian xét Entry
ALLOW_LONG_TRADES = True    # Cho phép lệnh Long
ALLOW_SHORT_TRADES = True   # Cho phép lệnh Short

# === 3. QUẢN LÝ VỐN & RỦI RO (RiskManager) ===
BACKTEST_INITIAL_CAPITAL = 1000.0  # Vốn khởi điểm (Backtest)
RISK_MANAGEMENT_MODE = "FIXED_LOT"  # Chế độ QLV: "FIXED_LOT", "RISK_PERCENT", "DYNAMIC"
fixed_lot = 5.0                     # Lô cố định (cho "FIXED_LOT" hoặc "DYNAMIC")
RISK_PERCENT_PER_TRADE = 2.0        # % rủi ro/lệnh (cho "RISK_PERCENT" hoặc "DYNAMIC")

# === 4. LỌC TREND (1H) ===
USE_TREND_FILTER = True         # Bật/Tắt bộ lọc Trend 1H
USE_SUPERTREND_FILTER = True    # Bật/Tắt lọc Supertrend
USE_EMA_TREND_FILTER = True     # Bật/Tắt lọc EMA 50
USE_ADX_FILTER = True           # Bật/Tắt lọc ADX (cho GĐ 1)
ADX_MIN_LEVEL = 20              # Ngưỡng ADX (phân biệt trend/sideways)

# === 5. LỌC ENTRY (15M) Nến + volume  ===
ENTRY_LOGIC_MODE = "DYNAMIC"   # Chế độ Entry: "BREAKOUT", "PULLBACK", "DYNAMIC"
PULLBACK_CANDLE_PATTERN = "ENGULFING" # Mẫu nến đảo chiều Pullback 
USE_CANDLE_FILTER = True        # Bật/Tắt lọc Nến (thân nến mạnh)
min_body_percent = 50.0         # % thân nến tối thiểu
USE_VOLUME_FILTER = True        # Bật/Tắt lọc Volume (đột biến)
volume_ma_period = 20           # Chu kỳ VMA (cho Volume)
volume_sd_multiplier = 0.5      # Hệ số nhân StdDev (cho Volume)


# === 6. QUẢN LÝ LỆNH (SL/TSL/Exit) ===
COOLDOWN_MINUTES = 1        # (Phút) Thời gian chờ giữa các lệnh
USE_EMERGENCY_EXIT = True       # Bật/Tắt Thoát khẩn cấp (theo 1H)

# --- SL Ban đầu ---
sl_atr_multiplier = 0.2       # Hệ số SL ban đầu (dựa trên ATR) + swingpoint

# --- Dời BE ---
isMoveToBE_Enabled = True       # Bật/Tắt dời SL về hòa vốn (BE)
tsl_trigger_R = 1.0             # Kích hoạt dời BE khi đạt R:R
be_atr_buffer = 0.8             # Hệ số SL dời BE (dựa trên ATR)

# --- Trailing Stop (TSL) ---
TSL_LOGIC_MODE = "DYNAMIC"       # Chế độ TSL: "STATIC", "DYNAMIC", "AGGRESSIVE"
trail_atr_buffer = 0.2         # Hệ số TSL (dựa trên ATR)

# === 7. CHỈ BÁO (Periods) ===
atr_period = 14                 # Chu kỳ ATR (cho SL/TSL)
swing_period = 5                # Chu kỳ Swing (cho SL/TSL)

ST_ATR_PERIOD = 10              # Chu kỳ ATR (của Supertrend)
ST_MULTIPLIER = 3.0             # Hệ số nhân (của Supertrend)

DI_PERIOD = 14                  # Chu kỳ DI (của ADX)
ADX_PERIOD = 14                 # Chu kỳ làm mượt (của ADX)

TREND_EMA_PERIOD = 50           # Chu kỳ EMA (Trend 1H)
ENTRY_EMA_PERIOD = 21           # Chu kỳ EMA (Entry 15M)

# === 8. HẠ TẦNG & DỮ LIỆU ===
DATA_DIR = "data"               # Thư mục chứa file CSV, logs, state
OUTPUT_DIR = "data"             # Thư mục lưu kết quả backtest
RESULTS_CSV_FILE = "backtest_results.csv" # Tên file CSV kết quả
MONTHS_TO_DOWNLOAD = 6          # Số tháng tải dữ liệu