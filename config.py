# -*- coding: utf-8 -*-
# config.py - Trung tâm điều khiển Exness Bot.

# ==============================================================================
# I. CẤU HÌNH CỐT LÕI
# ==============================================================================
SYMBOL = 'ETHUSD'               # Cặp tiền tệ để giao dịch
TIMEFRAME = '15m'               # Khung thời gian chính ('1m', '5m', '15m'...)
MAGIC_NUMBER = 20251020         # ID riêng để bot quản lý lệnh

# ==============================================================================
# II. QUẢN LÝ RỦI RO & LỆNH
# ==============================================================================
# --- Rủi ro trên mỗi lệnh ---
RISK_PERCENT = 1.0              # % rủi ro MONG MUỐN cho mỗi lệnh
ENABLE_FORCE_MIN_LOT = True     # True: Bật cơ chế "cố đấm ăn xôi" cho vốn bé
FORCED_MIN_LOT_SIZE = 0.1       # Lot size tối thiểu để "cố" (0.1 cho ETH)
MAX_FORCED_RISK_PERCENT = 5.0   # Ngưỡng rủi ro % tối đa chấp nhận khi "cố"

# --- Quản lý lệnh chung ---
MAX_ACTIVE_TRADES = 1           # Số lệnh tối đa được phép mở cùng lúc
COOLDOWN_CANDLES = 3            # Số nến cần chờ sau khi một lệnh đóng

# ==============================================================================
# III. CẤU HÌNH CHỈ BÁO KỸ THUẬT
# ==============================================================================
INDICATORS_CONFIG = {
    "BB": {"PERIOD": 20, "STD_DEV": 2.0},
    "ATR": {"PERIOD": 14, "SL_MULTIPLIER": 2.0, "TP_MULTIPLIER": 3.0},   
    "RSI": {"PERIOD": 14, "OVERBOUGHT": 70, "OVERSOLD": 30},
    "MACD": {"FAST_EMA": 12, "SLOW_EMA": 26, "SIGNAL_SMA": 9},
    "SUPERTREND": {"ATR_PERIOD": 10, "MULTIPLIER": 3.0},
    "EMA": {"SLOW_PERIOD": 200, "FAST_PERIOD": 50},
    "VOLUME": {"MA_PERIOD": 20} # So sánh volume hiện tại với volume trung bình 20 nến
}

# ==============================================================================
# IV. HỆ THỐNG ĐIỂM SỐ & BỘ LỌC
# ==============================================================================
ENTRY_SCORE_THRESHOLD = 7.0     # Ngưỡng điểm tối thiểu để vào lệnh MUA (hoặc -7.0 cho BÁN)

# --- Trọng số cho các tín hiệu CỘNG ĐIỂM ---
SCORING_WEIGHTS = {
    "BB_TRIGGER_SCORE": 5.0,
    "SUPERTREND_ALIGN_SCORE": 3.0,
    "RSI_EXTREME_SCORE": 2.0,
    "MACD_CROSS_SCORE": 2.0
}

# --- Trọng số cho các tín hiệu "PHẠT ĐIỂM" (bộ lọc) ---
PENALTY_WEIGHTS = {
    "COUNTER_EMA_TREND_PENALTY": 5.0,     # Điểm phạt khi giao dịch ngược xu hướng EMA 200
    "LOW_VOLUME_CONFIRMATION_PENALTY": 3.0  # Điểm phạt khi volume không xác nhận
}

# ==============================================================================
# V. QUẢN LÝ LỆNH NĂNG ĐỘNG (PHASE 3)
# ==============================================================================
ACTIVE_TRADE_MANAGEMENT = {
    "ENABLE_TSL": True,                   # Bật/Tắt Trailing Stop Loss
    "TSL_ATR_MULTIPLIER": 2.5,            # Khoảng cách TSL bám theo giá (tính bằng ATR)

    "ENABLE_TP1": True,                   # Bật/Tắt chốt lời TP1
    "TP1_RR_RATIO": 1.0,                  # Chốt lời TP1 khi lợi nhuận đạt R:R = 1:1
    "TP1_PARTIAL_CLOSE_PERCENT": 50.0,    # Chốt 50% khối lượng tại TP1
    "TP1_MOVE_SL_TO_ENTRY": True,         # True: Dời SL về điểm vào lệnh sau khi chốt TP1

    "ENABLE_PROTECT_PROFIT": True,        # Bật/Tắt cơ chế bảo vệ lợi nhuận
    "PP_MIN_PEAK_R_TRIGGER": 1.2,         # Kích hoạt khi lợi nhuận đỉnh đạt R:R > 1:1.2
    "PP_DROP_R_TRIGGER": 0.4,             # Chốt lời nếu lợi nhuận sụt giảm 0.4R từ đỉnh
    "PP_PARTIAL_CLOSE_PERCENT": 50.0,     # Chốt 50% khối lượng
    "PP_MOVE_SL_TO_ENTRY": True,          # True: Dời SL về điểm vào lệnh
}

# ==============================================================================
# VI. CẤU HÌNH HỆ THỐNG
# ==============================================================================
CANDLE_FETCH_COUNT = 300
LOOP_SLEEP_SECONDS = 2