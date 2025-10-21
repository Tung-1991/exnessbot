# -*- coding: utf-8 -*-
# config.py - Trung tâm điều khiển Exness Bot (v4.0 - Phase 4)

# ==============================================================================
# I. CẤU HÌNH CỐT LÕI
# ==============================================================================
SYMBOL = 'ETHUSD'               # Cặp tiền tệ để giao dịch
TIMEFRAME = '15m'               # Khung thời gian chính ('1m', '5m', '15m'...)
MAGIC_NUMBER = 20251020         # ID riêng để bot quản lý lệnh

ENABLE_LONG_TRADES = True       # (True/False) Cho phép bot vào lệnh LONG
ENABLE_SHORT_TRADES = True      # (True/False) Cho phép bot vào lệnh SHORT

# ==============================================================================
# II. QUẢN LÝ RỦI RO & LỆNH
# ==============================================================================
# --- Rủi ro trên mỗi lệnh ---
RISK_PERCENT = 1.0              # % rủi ro MONG MUỐN cho mỗi lệnh

# --- Giới hạn Stop Loss (Bộ lọc rủi ro cuối cùng) ---
# Đây là "người gác cổng" quyền lực nhất, sẽ hủy lệnh nếu SL nằm ngoài vùng an toàn
MAX_SL_PERCENT_OF_PRICE = 5.0   # SL không được xa hơn 5% giá vào lệnh
MIN_SL_PERCENT_OF_PRICE = 0.5   # SL không được gần hơn 0.5% giá vào lệnh
FORCE_MINIMUM_DISTANCE = True   # Nếu SL tính theo ATR < MIN, ép dùng khoảng cách MIN

# --- Quản lý lệnh chung ---
MAX_ACTIVE_TRADES = 1           # Số lệnh tối đa được phép mở cùng lúc
COOLDOWN_CANDLES = 3            # Số nến cần chờ sau khi một lệnh đóng

# --- Dành cho vốn bé ---
ENABLE_FORCE_MIN_LOT = True     # True: Bật cơ chế "cố đấm ăn xôi"
FORCED_MIN_LOT_SIZE = 0.1       # Lot size tối thiểu để "cố" (0.1 cho ETH)
MAX_FORCED_RISK_PERCENT = 5.0   # Ngưỡng rủi ro % tối đa chấp nhận khi "cố"

# ==============================================================================
# III. HỆ THỐNG ĐIỂM SỐ & BỘ LỌC (PHASE 4 - LOGIC MỚI)
# ==============================================================================
# Ngưỡng điểm tối thiểu để một tín hiệu được coi là đủ chất lượng để vào lệnh.
# Bot sẽ tính điểm cho phe MUA và BÁN riêng biệt. Phe nào thắng và vượt ngưỡng này sẽ được thực thi.
ENTRY_SCORE_THRESHOLD = 70.0

# ------------------------------------------------------------------------------
# IV. CẤU HÌNH ĐIỂM SỐ CÁC CHỈ BÁO TÍN HIỆU (Tổng thang điểm = 100)
# ------------------------------------------------------------------------------
# Đây là những chỉ báo "châm ngòi", dùng để TÍNH ĐIỂM cho phe MUA và BÁN.
# Mỗi chỉ báo có thể được bật/tắt và có các cấp độ điểm khác nhau (range score).
SCORING_CONFIG = {
    "BOLLINGER_BANDS": {
        "enabled": True,
        "weight": 50,  # Điểm tối đa mà BB có thể đóng góp là 50/100
        "params": {"period": 20, "std_dev": 2.0},
        "score_levels": {
            # Cấp độ 1: Nến đóng cửa hoàn toàn bên ngoài dải -> Tín hiệu mạnh nhất
            "cross_outside": 50,
            # Cấp độ 2: Râu nến chạm/vượt ra ngoài dải
            "wick_outside": 35,
            # Cấp độ 3: Nến đóng cửa rất gần dải
            "close_near": 20
        }
    },
    "SUPERTREND": {
        "enabled": True,
        "weight": 30, # Điểm tối đa là 30/100
        "params": {"atr_period": 10, "multiplier": 3.0},
        "score_levels": {
            # Chỉ có 1 cấp độ: Giá đóng cửa phía trên/dưới Supertrend -> 30 điểm
            "aligned_with_trend": 30
        }
    },
    "RSI": {
        "enabled": True,
        "weight": 10, # Điểm tối đa là 10/100
        "params": {"period": 14},
        "score_levels": {
            # Càng đi sâu vào vùng quá mua/bán, điểm càng cao
            "extreme": {"threshold": [30, 70], "score": 10}, # RSI < 30 hoặc > 70
            "deep":    {"threshold": [20, 80], "score": 15}  # Ghi chú: điểm ở đây sẽ được chuẩn hóa theo weight. Ví dụ 15 -> 10 * (15/10) = 15, nhưng tổng cuối vẫn bị chặn bởi weight
        }
    },
    "MACD": {
        "enabled": True,
        "weight": 10, # Điểm tối đa là 10/100
        "params": {"fast_ema": 12, "slow_ema": 26, "signal_sma": 9},
        "score_levels": {
            # Giao cắt rõ ràng giữa MACD và Signal line
            "crossover": 10
        }
    }
}

# ------------------------------------------------------------------------------
# V. CẤU HÌNH CÁC BỘ LỌC XÁC NHẬN (Hệ số nhân)
# ------------------------------------------------------------------------------
# Đây là những chỉ báo "kiểm định chất lượng", hoạt động như một hệ số nhân
# để khuếch đại (thưởng) hoặc làm suy yếu (phạt) tổng điểm tính được ở trên.
FILTER_CONFIG = {
    "EMA_TREND_FILTER": {
        "enabled": True,
        "params": {"period": 200},
        "multipliers": {
            # Nếu tín hiệu THUẬN theo xu hướng EMA -> THƯỞNG 10% tổng điểm
            "in_trend_multiplier": 1.1,
            # Nếu tín hiệu NGƯỢC theo xu hướng EMA -> PHẠT 20% tổng điểm (nhân 0.8)
            "counter_trend_multiplier": 0.9
        }
    },
    "VOLUME_FILTER": {
        "enabled": True,
        "params": {"ma_period": 20},
        # Hệ thống bậc thang: Bot sẽ duyệt từ trên xuống và chọn bậc đầu tiên thỏa mãn
        "tiered_multipliers": [
            # Bậc 1: Volume RẤT YẾU (dưới 80% so với trung bình) -> Phạt nặng
            {"threshold_ratio": 0.8, "multiplier": 0.8},
            # Bậc 2: Volume TRUNG BÌNH (từ 80% -> 150%) -> Không thưởng/phạt
            {"threshold_ratio": 1.5, "multiplier": 1.0},
            # Bậc 3: Volume ĐỘT BIẾN (trên 150%) -> Thưởng cho tín hiệu chất lượng cao
            {"threshold_ratio": 999, "multiplier": 1.2}
        ]
    }
}


# ==============================================================================
# VI. CẤU HÌNH CHỈ BÁO GỐC (Dành cho Risk Manager & Backtester)
# ==============================================================================
# Cấu hình này vẫn giữ lại để các hàm tính toán gốc có thể truy cập
INDICATORS_CONFIG = {
    "ATR": {"PERIOD": 14, "SL_MULTIPLIER": 2.0, "TP_MULTIPLIER": 3.0},
    # Các chỉ báo khác sẽ lấy params từ SCORING_CONFIG ở trên
    "BB": SCORING_CONFIG["BOLLINGER_BANDS"]["params"],
    "RSI": SCORING_CONFIG["RSI"]["params"],
    "MACD": SCORING_CONFIG["MACD"]["params"],
    "SUPERTREND": SCORING_CONFIG["SUPERTREND"]["params"],
    "EMA": {"SLOW_PERIOD": FILTER_CONFIG["EMA_TREND_FILTER"]["params"]["period"], "FAST_PERIOD": 50},
    "VOLUME": {"MA_PERIOD": FILTER_CONFIG["VOLUME_FILTER"]["params"]["ma_period"]}
}


# ==============================================================================
# VII. QUẢN LÝ LỆNH NĂNG ĐỘNG (PHASE 3)
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
# VIII. CẤU HÌNH HỆ THỐNG
# ==============================================================================
CANDLE_FETCH_COUNT = 300
LOOP_SLEEP_SECONDS = 2