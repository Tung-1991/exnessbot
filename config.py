# -*- coding: utf-8 -*-
# config.py - Trung tâm điều khiển Exness Bot (v5.1 - Bộ Luật V2.4 Chuẩn hóa)

# ==============================================================================
# I. CẤU HÌNH CỐT LÕI
# ==============================================================================
SYMBOL = 'ETHUSD'               # Cặp tiền tệ để giao dịch
TIMEFRAME = '1h'                # Khung thời gian chính ('1m', '5m', '15m'...)
MAGIC_NUMBER = 23051999         # ID riêng để bot quản lý lệnh

ENABLE_LONG_TRADES = True       # (True/False) Cho phép bot vào lệnh LONG
ENABLE_SHORT_TRADES = True      # (True/False) Cho phép bot vào lệnh SHORT

# ==============================================================================
# II. QUẢN LÝ RỦI RO & LỆNH
# ==============================================================================
RISK_PERCENT = 1.0              # % rủi ro MONG MUỐN cho mỗi lệnh
MAX_ACTIVE_TRADES = 1           # Số lệnh tối đa được phép mở cùng lúc
COOLDOWN_CANDLES = 3            # Số nến cần chờ sau khi một lệnh đóng

# --- Giới hạn Stop Loss (An toàn) ---
MAX_SL_PERCENT_OF_PRICE = 5.0   # SL không được xa hơn 5% giá vào lệnh
MIN_SL_PERCENT_OF_PRICE = 0.5   # SL không được gần hơn 0.5% giá vào lệnh
FORCE_MINIMUM_DISTANCE = True   # Nếu SL tính theo ATR < MIN, ép dùng khoảng cách MIN

# --- Dành cho vốn bé (Tùy chọn) ---
ENABLE_FORCE_MIN_LOT = True     # True: Bật cơ chế "cố đấm ăn xôi"
FORCED_MIN_LOT_SIZE = 0.1       # Lot size tối thiểu để "cố" (ví dụ: 0.1 cho ETH)
MAX_FORCED_RISK_PERCENT = 5.0   # Ngưỡng rủi ro % tối đa chấp nhận khi "cố"

# ==============================================================================
# III. HỆ THỐNG ĐIỂM SỐ & QUYẾT ĐỊNH (BỘ LUẬT V2.4)
# ==============================================================================
# Ngưỡng điểm tối thiểu để một tín hiệu được coi là đủ chất lượng để vào lệnh.
ENTRY_SCORE_THRESHOLD = 70.0

# ------------------------------------------------------------------------------
# IV. ĐIỂM KHỞI TẠO (RAW SCORE - TỔNG 100 ĐIỂM)
# ------------------------------------------------------------------------------
# Triết lý: Tổng trọng số (weight) của tất cả các chỉ báo nên bằng 100.
# Mỗi chỉ báo có thang điểm nội bộ (score) từ 0-100.
# 'weight' quyết định % đóng góp tối đa của chỉ báo đó vào tổng điểm khởi tạo.
RAW_SCORE_CONFIG = {
    # Tín hiệu đảo chiều chính, chiếm 50% sức mạnh tín hiệu
    "BOLLINGER_BANDS": {
        "enabled": True,
        "weight": 50, # 50 điểm
        "params": {"period": 20, "std_dev": 2.0},
        "score_levels": [
            {"level": "cross_outside_full", "score": 100}, # Tín hiệu mạnh nhất
            {"level": "cross_outside_half_body", "score": 75},
            {"level": "wick_outside", "score": 60},
            {"level": "touch_band", "score": 35},
            {"level": "close_near", "score": 15}
        ]
    },
    # Tín hiệu quá mua/bán, chiếm 30% sức mạnh tín hiệu
    "RSI": {
        "enabled": True,
        "weight": 30, # 30 điểm
        "params": {"period": 14},
        "score_levels": [
            # Tín hiệu sự kiện "sắc bén", điểm cao nhất
            {"level": "enter_zone", "score": 100}, # Vừa vào vùng quá bán/mua -> tín hiệu mạnh
            
            # Tín hiệu trạng thái "sâu", điểm giảm dần
            {"threshold": 20, "score": 80}, # Ở rất sâu trong vùng quá bán
            {"threshold": 25, "score": 60}, # Ở sâu trong vùng quá bán
            {"threshold": 30, "score": 40}, # Mới ở trong vùng quá bán
            
            # Ghi chú cho tương lai: Phân kỳ là tín hiệu rất mạnh, có thể cho điểm thưởng cao
            # {"level": "divergence", "score": 120}
        ]
    },
    # Tín hiệu giao cắt/momentum, chiếm 20% sức mạnh tín hiệu
    "MACD": {
        "enabled": True,
        "weight": 20, # 20 điểm
        "params": {"fast_ema": 12, "slow_ema": 26, "signal_sma": 9},
        "score_levels": [
            {"level": "explosive_crossover", "score": 100}, # Giao cắt bùng nổ
            {"level": "strong_crossover", "score": 80},
            {"level": "standard_crossover", "score": 60},
            {"level": "noisy_crossover", "score": 40},
            {"level": "about_to_cross", "score": 20}
        ]
    }
} # TỔNG CỘNG: 50 + 30 + 20 = 100 ĐIỂM

# ------------------------------------------------------------------------------
# V. ĐIỂM ĐIỀU CHỈNH (ADJUSTMENT SCORE - THƯỞNG/PHẠT)
# ------------------------------------------------------------------------------
# Các chỉ báo "xác nhận" bối cảnh thị trường. Điểm có thể là số âm hoặc dương.
ADJUSTMENT_SCORE_CONFIG = {
    "EMA_TREND_FILTER": {
        "enabled": True,
        "params": {"period": 200},
        # Ngưỡng dựa trên khoảng cách (tính bằng ATR) từ giá tới EMA.
        # Được sắp xếp logic từ ngược xu hướng nhất đến thuận xu hướng nhất.
        "score_tiers": [
            {"threshold_atr": -1.0, "score": -15}, # Giá < EMA - 1 ATR (Rất ngược xu hướng)
            {"threshold_atr": -0.2, "score": -10}, # Giá < EMA - 0.2 ATR (Hơi ngược xu hướng)
            {"threshold_atr": 0.2,  "score": 0},   # Giá đi ngang quanh EMA
            {"threshold_atr": 1.0,  "score": +10}, # Giá > EMA + 1 ATR (Hơi thuận xu hướng)
            {"threshold_atr": 999,  "score": +15}  # Giá > EMA + 1 ATR (Rất thuận xu hướng)
        ]
    },
    "SUPERTREND_FILTER": {
        "enabled": True,
        "params": {"atr_period": 10, "multiplier": 3.0},
        # Logic tương tự EMA, đo khoảng cách từ giá tới đường Supertrend.
        "score_tiers": [
            {"threshold_atr": -1.0, "score": -15},
            {"threshold_atr": -0.2, "score": -10},
            {"threshold_atr": 0.2,  "score": 0},
            {"threshold_atr": 1.0,  "score": +10},
            {"threshold_atr": 999,  "score": +15}
        ]
    },
    "VOLUME_FILTER": {
        "enabled": True,
        "params": {"ma_period": 20},
        # Ngưỡng dựa trên tỷ lệ Volume hiện tại / Volume trung bình.
        "score_tiers": [
            {"threshold_ratio": 0.5, "score": -15}, # Volume < 50% TB (Rất yếu)
            {"threshold_ratio": 0.8, "score": -10}, # Volume < 80% TB (Yếu)
            {"threshold_ratio": 1.5, "score": 0},   # Volume bình thường
            {"threshold_ratio": 2.0, "score": +10}, # Volume > 200% TB (Mạnh)
            {"threshold_ratio": 999, "score": +15}  # Volume > 200% TB (Đột biến)
        ]
    }
}

# ==============================================================================
# VI. CẤU HÌNH CHỈ BÁO GỐC (Dành cho Risk Manager)
# ==============================================================================
INDICATORS_CONFIG = {
    "ATR": {"PERIOD": 14, "SL_MULTIPLIER": 2.0, "TP_MULTIPLIER": 3.0},
}

# ==============================================================================
# VII. QUẢN LÝ LỆNH NĂNG ĐỘNG
# ==============================================================================
ACTIVE_TRADE_MANAGEMENT = {
    "ENABLE_TSL": True,
    # SỬA LỖI: Tên biến phải khớp với backtest.py
    "TSL_ATR_MULTIPLIER": 2.5,

    "ENABLE_TP1": True,
    "TP1_RR_RATIO": 1.0,
    "TP1_PARTIAL_CLOSE_PERCENT": 50.0, # (Tính năng chưa lập trình, để sẵn)
    "TP1_MOVE_SL_TO_ENTRY": True,

    "ENABLE_PROTECT_PROFIT": True,
    "PP_MIN_PEAK_R_TRIGGER": 1.2,
    "PP_DROP_R_TRIGGER": 0.4,
    "PP_PARTIAL_CLOSE_PERCENT": 50.0, # (Tính năng chưa lập trình, để sẵn)
    "PP_MOVE_SL_TO_ENTRY": True,
}

# ==============================================================================
# VIII. CẤU HÌNH HỆ THỐNG
# ==============================================================================
CANDLE_FETCH_COUNT = 300      # Số nến lịch sử cần để tính toán các chỉ báo
LOOP_SLEEP_SECONDS = 2        # Thời gian chờ giữa các lần quét (cho bot live)