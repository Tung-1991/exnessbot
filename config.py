# -*- coding: utf-8 -*-
# config.py - Trung tâm Quyền lực Exness Bot (v6.0 - FINAL)
# ĐÃ ĐƯỢC CẬP NHẬT ĐỂ TƯƠNG THÍCH 100% VỚI CÁC FILE v6.0 CỦA BẠN

# ==============================================================================
# I. CẤU HÌNH CỐT LÕI
# ==============================================================================
SYMBOL = 'ETHUSD'
TIMEFRAME = '15m'               # Khung thời gian GIAO DỊCH CHÍNH
TREND_TIMEFRAME = '1h'          # Khung thời gian XU HƯỚNG (để tính Supertrend, EMA 200...)
MAGIC_NUMBER = 23051999

ENABLE_LONG_TRADES = True
ENABLE_SHORT_TRADES = True
MAX_ACTIVE_TRADES = 1           # (Điểm 9) Giới hạn tổng số lệnh được mở cùng lúc
COOLDOWN_CANDLES = 0            # Số nến chờ sau khi 1 lệnh (thắng hoặc thua) đóng

# ==============================================================================
# II. HỆ THỐNG VÀO LỆNH 3 CẤP (Điểm 9)
# ==============================================================================
# Bot sẽ so sánh TỔNG ĐIỂM (ví dụ 130) với 3 mốc này để quyết định "Cấp độ Tự tin"
# CẤU TRÚC SỬA LẠI THÀNH LIST (để khớp với trade_manager.py)
ENTRY_SCORE_LEVELS = [90.0, 120.0, 150.0] # Tương ứng Cấp 1, Cấp 2, Cấp 3

# ==============================================================================
# III. QUẢN LÝ VỐN (POSITION SIZING - Điểm 5)
# ==============================================================================
# --- CHỌN 1 TRONG 2 CƠ CHẾ ---
ENABLE_FIXED_LOT_SIZING = False # True: Dùng Lot Cố Định. False: Dùng % Rủi ro

# 1. Cấu hình Lot Cố Định (nếu ENABLE_FIXED_LOT_SIZING = True)
# Tương ứng với 3 Cấp độ Tự tin (Cấp 1, 2, 3)
FIXED_LOT_LEVELS = [0.1, 0.2, 0.3]

# 2. Cấu hình % Rủi ro (nếu ENABLE_FIXED_LOT_SIZING = False)
# Tương ứng với 3 Cấp độ Tự tin (Cấp 1, 2, 3)
RISK_PERCENT_LEVELS = [1.0, 1.5, 2.0]

# --- Bộ lọc an toàn cho % Rủi ro ---
MAX_SL_PERCENT_OF_PRICE = 5.0
MIN_SL_PERCENT_OF_PRICE = 0.5
FORCE_MINIMUM_DISTANCE = True
ENABLE_FORCE_MIN_LOT = True
FORCED_MIN_LOT_SIZE = 0.1
MAX_FORCED_RISK_PERCENT = 5.0

# ==============================================================================
# IV. LOGIC THOÁT LỆNH (HYBRID EXIT - Điểm 4)
# ==============================================================================

# --- Cơ chế 1: Thoát lệnh theo Điểm số (Score-Based Exit) ---
ENABLE_SCORE_BASED_EXIT = True  # True: Bật tính năng thoát lệnh khi điểm số sụt giảm
EXIT_SCORE_THRESHOLD = 40.0     # Nếu điểm Long/Short rớt xuống DƯỚI ngưỡng này, lệnh sẽ đóng
EXIT_PARTIAL_CLOSE_PERCENT = 100.0 # Thoát 100% lệnh (hoặc 50% nếu muốn)

# --- Cơ chế 2: Thoát lệnh theo ATR (Cũng được điều chỉnh theo 3 Cấp độ) ---
# CẤU TRÚC SỬA LẠI THÀNH 2 LIST RIÊNG (để khớp với risk_manager.py)
# Tương ứng với 3 Cấp độ Tự tin (Cấp 1, 2, 3)
ATR_SL_MULTIPLIER_LEVELS = [2.0, 2.2, 2.5]
ATR_TP_MULTIPLIER_LEVELS = [3.0, 4.0, 5.0]

# --- Cơ chế 3: Quản lý lệnh Năng động (TSL, TP1, PP) ---
ACTIVE_TRADE_MANAGEMENT = {
    "ENABLE_TSL": True,
    "TSL_ATR_MULTIPLIER": 2.5,

    "ENABLE_TP1": True,
    "TP1_RR_RATIO": 1.0,
    "TP1_PARTIAL_CLOSE_PERCENT": 50.0,
    "TP1_MOVE_SL_TO_ENTRY": True,

    "ENABLE_PROTECT_PROFIT": True,
    "PP_MIN_PEAK_R_TRIGGER": 1.2,
    "PP_DROP_R_TRIGGER": 0.4,
    "PP_PARTIAL_CLOSE_PERCENT": 50.0,
    "PP_MOVE_SL_TO_ENTRY": True,
}

# ==============================================================================
# V. CẤU HÌNH BỘ LỌC XU HƯỚNG (TREND FILTERS - MTF)
# ==============================================================================
TREND_FILTERS_CONFIG = {
    # Khớp 100% với signal_generator.py của bạn
    "USE_TREND_FILTER": "BOTH", # "BOTH", "SUPERTREND", "EMA", hoặc "NONE"

    "SUPERTREND": {
        "enabled": True,
        "params": {"atr_period": 10, "multiplier": 3.0}
    },
    "EMA": { 
        "enabled": True,
        "params": {"period": 200}
    }
}

# ==============================================================================
# VI. CẤU HÌNH TÍN HIỆU VÀO LỆNH (ENTRY SIGNALS)
# ==============================================================================
# Khớp 100% với signal_generator.py của bạn (dùng MAX_SCORE viết hoa)
ENTRY_SIGNALS_CONFIG = {

    "BOLLINGER_BANDS": {
        "enabled": True,
        "MAX_SCORE": 30, 
        "params": {"period": 20, "std_dev": 2.0},
        "score_levels": {
            "squeeze_breakout": 30,
            "walking_the_band": 25,
            "reversal_confirmation": 20,
            "middle_band_rejection": 15,
            "wick_touch": 5
        }
    },
    "RSI": {
        "enabled": True,
        "MAX_SCORE": 30, 
        "params": {"period": 14},
        "score_levels": {
            "divergence": 30,
            "deep_zone": 20,
            "oversold_overbought": 15,
            "entry_zone": 10,
            "cross_midline": 10,
            "above_below_midline": 5
        }
    },
    "MACD": {
        "enabled": True,
        "MAX_SCORE": 25, 
        "params": {"fast_ema": 12, "slow_ema": 26, "signal_sma": 9},
        "score_levels": {
            "divergence": 25,
            "zero_line_cross": 20,
            "signal_cross": 10,
            "histogram_momentum": 5
        }
    },
    "CANDLE_PATTERNS": {
        "enabled": True,
        "MAX_SCORE": 20, 
        "score_levels": {
            "strong_signal": 20,
            "medium_signal": 10
        }
    },
    "ADX": {
        "enabled": True,
        "MAX_SCORE": 10, 
        "params": {"period": 14},
        "threshold": 25
    },
    "VOLUME": {
        "enabled": True,
        "MAX_SCORE": 5, 
        "params": {
            "ma_period": 20,
            "multiplier": 1.5
        }
    }
}

# ==============================================================================
# VIII. CẤU HÌNH HỆ THỐNG
# ==============================================================================
CANDLE_FETCH_COUNT = 300      # Số nến lịch sử cần để tính toán các chỉ báo
LOOP_SLEEP_SECONDS = 2        # Thời gian chờ giữa các lần quét (cho bot live)

# Cấu hình chỉ báo ATR gốc (Dùng chung cho TSL và Risk Manager)
INDICATORS_CONFIG = {
    "ATR": {"PERIOD": 14}
}
# (risk_manager.py của bạn đã đọc ATR_PERIOD từ đây, rất chuẩn)