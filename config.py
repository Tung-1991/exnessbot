# -*- coding: utf-8 -*-
# config.py - Trung tâm Quyền lực Exness Bot (Bản Final V8.1)
# ĐÃ CẬP NHẬT ĐÚNG THANG ĐIỂM 70/50/30

# ==============================================================================
# I. CẤU HÌNH CỐT LÕI (Giữ nguyên)
# ==============================================================================
SYMBOL = 'ETHUSD'
TIMEFRAME = '15m'
TREND_TIMEFRAME = '1h'
MAGIC_NUMBER = 23051999

ENABLE_LONG_TRADES = True
ENABLE_SHORT_TRADES = True
MAX_ACTIVE_TRADES = 1
COOLDOWN_CANDLES = 0

# ==============================================================================
# II. HỆ THỐNG VÀO LỆNH 3 CẤP (Giữ nguyên)
# ==============================================================================
# TỔNG ĐIỂM TỐI ĐA (V8.1): 70+70+70(RSI) + 50+50+50(Nến) + 30+30(Vol) = 400
ENTRY_SCORE_LEVELS = [90.0, 120.0, 150.0] # Cấp 1, Cấp 2, Cấp 3

# ==============================================================================
# III. QUẢN LÝ VỐN (Giữ nguyên)
# ==============================================================================
ENABLE_FIXED_LOT_SIZING = False 
FIXED_LOT_LEVELS = [0.1, 0.2, 0.3]
RISK_PERCENT_LEVELS = [1.0, 1.5, 2.0]
# (Các bộ lọc an toàn khác giữ nguyên)
MAX_SL_PERCENT_OF_PRICE = 5.0
MIN_SL_PERCENT_OF_PRICE = 0.5
FORCE_MINIMUM_DISTANCE = True
ENABLE_FORCE_MIN_LOT = True
FORCED_MIN_LOT_SIZE = 0.1
MAX_FORCED_RISK_PERCENT = 5.0

# ==============================================================================
# IV. LOGIC THOÁT LỆNH (Giữ nguyên)
# ==============================================================================
ENABLE_SCORE_BASED_EXIT = True
EXIT_SCORE_THRESHOLD = 40.0
# (Các cấu hình TSL, TP1, PP khác giữ nguyên)
ATR_SL_MULTIPLIER_LEVELS = [2.0, 2.2, 2.5]
ATR_TP_MULTIPLIER_LEVELS = [3.0, 4.0, 5.0]
ACTIVE_TRADE_MANAGEMENT = {
    "ENABLE_TSL": True, "TSL_ATR_MULTIPLIER": 2.5,
    "ENABLE_TP1": True, "TP1_RR_RATIO": 1.0, "TP1_PARTIAL_CLOSE_PERCENT": 50.0, "TP1_MOVE_SL_TO_ENTRY": True,
    "ENABLE_PROTECT_PROFIT": True, "PP_MIN_PEAK_R_TRIGGER": 1.2, "PP_DROP_R_TRIGGER": 0.4, "PP_PARTIAL_CLOSE_PERCENT": 50.0, "PP_MOVE_SL_TO_ENTRY": True,
}

# ==============================================================================
# V. CẤU HÌNH INDICATORS KHUNG H1 (Nâng cấp V8.1 - ĐÚNG THANG ĐIỂM 50)
# ==============================================================================
TREND_FILTERS_CONFIG = {
    "SUPERTREND": {
        "enabled": True,
        "MAX_SCORE": 50, # SỬA ĐÚNG TRẦN 50 ĐIỂM
        "params": {
            "atr_period": 10, 
            "multiplier": 3.0,
            "full_score_atr_distance": 2.0 
        }
    },
    "EMA": { 
        "enabled": True,
        "MAX_SCORE": 50, # SỬA ĐÚNG TRẦN 50 ĐIỂM
        "params": {
            "period": 200,
            "atr_period": 14,
            "full_score_atr_distance": 2.0
        }
    }
}

# ==============================================================================
# VI. CẤU HÌNH INDICATORS KHUNG M15 (NÂNG CẤP V8.1 - ĐÚNG THANG ĐIỂM)
# ==============================================================================
ENTRY_SIGNALS_CONFIG = {

    "BOLLINGER_BANDS": {
        "enabled": True,
        "MAX_SCORE": 70, # Trần 70 điểm (Logic V8.0 Cộng hưởng)
        "params": {"period": 20, "std_dev": 2.0},
        "v8_score_levels": {
            "CONTEXT": { "squeeze_score": 20, "squeeze_threshold_pct": 2.5, "expansion_score": 10, "expansion_threshold_pct": 8.0 },
            "POSITION": { "max_score": 30, "neutral_level_long": 0.5, "full_score_level_long": 0.0, "neutral_level_short": 0.5, "full_score_level_short": 1.0 },
            "PRICE_ACTION": { "fakey_reversal_score": 20, "walking_the_band_score": 20, "middle_band_bounce_score": 15 }
        }
    },

    "MACD": {
        "enabled": True,
        "MAX_SCORE": 70, # Trần 70 điểm (Logic V8.0 Cộng hưởng)
        "params": {"fast_ema": 12, "slow_ema": 26, "signal_sma": 9},
        "v8_score_levels": {
            "TREND": { "max_score": 25, "full_score_value_norm": 0.5 },
            "MOMENTUM": { "max_score": 15, "full_score_value_norm": 0.1 },
            "SIGNALS": { "divergence_score": 30, "signal_cross_score": 15 }
        }
    },
    
    "RSI": {
        "enabled": True,
        "MAX_SCORE": 70, # SỬA ĐÚNG TRẦN 70 ĐIỂM
        "params": {"period": 14},
        # (Giữ nguyên cấu hình NỘI SUY V7.0)
        # LƯU Ý: Tổng điểm của 2 yếu tố (momentum + divergence) CÓ THỂ vượt 70
        # nhưng MAX_SCORE sẽ giới hạn nó lại ở 70.
        "score_levels": {
            "max_momentum_score": 40, # Nâng điểm momentum
            "neutral_level": 50.0,
            "full_score_level_long": 30.0,
            "full_score_level_short": 70.0,
            "divergence_score": 30 # Cộng thêm 30 nếu có phân kỳ
        }
    },
    
    "CANDLE_PATTERNS": {
        "enabled": True,
        "MAX_SCORE": 50, # SỬA ĐÚNG TRẦN 50 ĐIỂM
        # (Giữ nguyên cấu hình "Trừu tượng" V7.0)
        "score_levels": {
            "momentum_max_score": 30, # Nâng điểm momentum
            "momentum_neutral_ratio": 0.1,
            "momentum_full_ratio": 0.9,
            "rejection_max_score": 20, # Nâng điểm rejection
            "rejection_neutral_ratio": 0.1,
            "rejection_full_ratio": 0.7
        }
    },
    
    "ADX": {
        "enabled": True,
        "MAX_SCORE": 30, # SỬA ĐÚNG TRẦN 30 ĐIỂM
        "params": {"period": 14},
        # (Cấu hình NỘI SUY v8.1 - "Tinh chỉnh")
        "score_levels": {
            "neutral_level": 18.0,
            "full_score_level": 35.0
        }
    },
    
    "VOLUME": {
        "enabled": True,
        "MAX_SCORE": 30, # SỬA ĐÚNG TRẦN 30 ĐIỂM
        "params": {"ma_period": 20},
        # (Cấu hình BẬC THANG v8.1 - "Tinh chỉnh")
        "score_levels": {
            "high_volume_multiplier": 1.2,
            "high_score": 15, # Nâng điểm
            "spike_volume_multiplier": 2.0,
            "spike_score": 30 # Nâng điểm
        }
    }
}

# ==============================================================================
# VIII. CẤU HÌNH HỆ THỐNG (Giữ nguyên)
# ==============================================================================
CANDLE_FETCH_COUNT = 300
LOOP_SLEEP_SECONDS = 2
INDICATORS_CONFIG = { "ATR": {"PERIOD": 14} }