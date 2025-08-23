# config.py
# Đây là Trung tâm Cấu hình Chiến lược DUY NHẤT cho toàn bộ hệ thống Bot Exness.
# Mọi tinh chỉnh về hành vi, rủi ro, và chiến thuật đều được thực hiện tại đây.

from typing import Dict, List, Any, Literal
import os

# ==============================================================================
# ================== ⚙️ TRUNG TÂM CẤU HÌNH ⚙️ ===================
# ==============================================================================
BOT_CONFIG = {
    "SYMBOL": "BTCUSD",
    "TIMEFRAME": "5m",
    "CANDLE_FETCH_COUNT": 300,
    "RISK_PER_TRADE_PERCENT": 1.0,
    "ENTRY_SCORE_THRESHOLD": 7.0,
    "ATR_SL_MULTIPLIER": 2.0,
    "RR_RATIO": 2.0
}

# --- CẤU HÌNH CHUNG ---
GENERAL_CONFIG = {
    "DATA_FETCH_LIMIT": 300,
    "CRON_JOB_INTERVAL_MINUTES": 1,
    "PENDING_TRADE_RETRY_LIMIT": 3,
    "CLOSE_TRADE_RETRY_LIMIT": 3,
    "CRITICAL_ERROR_ALERT_COOLDOWN_MINUTES": 45,
    "RECONCILIATION_QTY_THRESHOLD": 0.95,
    "MIN_ORDER_VALUE_USDT": 11.0,
    "ORPHAN_ASSET_MIN_VALUE_USDT": 10.0,
    "HEAVY_REFRESH_MINUTES": 15,
    "TOP_N_OPPORTUNITIES_TO_CHECK": 7,
    "TRADE_COOLDOWN_HOURS": 1.5,
    "OVERRIDE_COOLDOWN_SCORE": 7.5,
    "MOMENTUM_FILTER_CONFIG": {
        "ENABLED": True,
        "RULES_BY_TIMEFRAME": {
            "1h": {"WINDOW": 5, "REQUIRED_CANDLES": 3},
            "4h": {"WINDOW": 5, "REQUIRED_CANDLES": 2},
            "1d": {"WINDOW": 4, "REQUIRED_CANDLES": 1}
        }
    },
    "DEPOSIT_DETECTION_MIN_USD": 10.0,
    "DEPOSIT_DETECTION_THRESHOLD_PCT": 0.01,
    "AUTO_COMPOUND_THRESHOLD_PCT": 10.0,
    "AUTO_DELEVERAGE_THRESHOLD_PCT": -10.0,
    "CAPITAL_ADJUSTMENT_COOLDOWN_HOURS": 48,
    "DAILY_SUMMARY_TIMES": ["08:10", "20:10"],
}

# --- PHÂN TÍCH ĐA KHUNG THỜI GIAN (MTF) ---
MTF_ANALYSIS_CONFIG = {
    "ENABLED": True,
    "BONUS_COEFFICIENT": 1.03,
    "PENALTY_COEFFICIENT": 0.95,
    "SEVERE_PENALTY_COEFFICIENT": 0.93,
    "SIDEWAYS_PENALTY_COEFFICIENT": 0.97,
}

# --- QUẢN LÝ LỆNH ĐANG MỞ ---
ACTIVE_TRADE_MANAGEMENT_CONFIG = {
    "EARLY_CLOSE_ABSOLUTE_THRESHOLD": 4.8,
    "EARLY_CLOSE_RELATIVE_DROP_PCT": 0.23,
    "PARTIAL_EARLY_CLOSE_PCT": 0.4,
    "PROFIT_PROTECTION": {
        "ENABLED": True,
        "MIN_PEAK_PNL_TRIGGER": 4.5,
        "PNL_DROP_TRIGGER_PCT": 2.0,
        "PARTIAL_CLOSE_PCT": 0.5
    }
}

# --- CẢNH BÁO ĐỘNG ---
DYNAMIC_ALERT_CONFIG = {
    "ENABLED": True,
    "COOLDOWN_HOURS": 2.5,
    "FORCE_UPDATE_HOURS": 10,
    "PNL_CHANGE_THRESHOLD_PCT": 2.0
}

# --- LUẬT RỦI RO ---
RISK_RULES_CONFIG = {
    "MAX_ACTIVE_TRADES": 7,
    "MAX_SL_PERCENT_BY_TIMEFRAME": {"1h": 0.08, "4h": 0.12, "1d": 0.16},
    "MAX_TP_PERCENT_BY_TIMEFRAME": {"1h": 0.11, "4h": 0.17, "1d": 0.22},
    "MIN_RISK_DIST_PERCENT_BY_TIMEFRAME": {"1h": 0.06, "4h": 0.08, "1d": 0.10},
    "STALE_TRADE_RULES": {
        "1h": {"HOURS": 48, "PROGRESS_THRESHOLD_PCT": 15.0},
        "4h": {"HOURS": 96, "PROGRESS_THRESHOLD_PCT": 15.0},
        "1d": {"HOURS": 240, "PROGRESS_THRESHOLD_PCT": 10.0},
        "STAY_OF_EXECUTION_SCORE": 6.8
    }
}

# --- QUẢN LÝ VỐN TỔNG THỂ ---
CAPITAL_MANAGEMENT_CONFIG = {
    "MAX_TOTAL_EXPOSURE_PCT": 0.80
}

# --- TRUNG BÌNH GIÁ (DCA) ---
DCA_CONFIG = {
    "ENABLED": True,
    "MAX_DCA_ENTRIES": 2,
    "TRIGGER_DROP_PCT_BY_TIMEFRAME": {
        "1h": -5.0,
        "4h": -7.0,
        "1d": -9.0
    },
    "SCORE_MIN_THRESHOLD": 6.5,
    "CAPITAL_MULTIPLIER": 0.5,
    "DCA_COOLDOWN_HOURS": 8
}

# --- CẢNH BÁO ---
ALERT_CONFIG = {
    "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_LIVE_WEBHOOK"),
    "DISCORD_CHUNK_DELAY_SECONDS": 2
}


# ==============================================================================
# ================= 🚀 CORE STRATEGY: 4-ZONE MODEL 🚀 =================
# ==============================================================================
LEADING_ZONE = "LEADING"
COINCIDENT_ZONE = "COINCIDENT"
LAGGING_ZONE = "LAGGING"
NOISE_ZONE = "NOISE"
ZONES = [LEADING_ZONE, COINCIDENT_ZONE, LAGGING_ZONE, NOISE_ZONE]

# --- QUẢN LÝ VỐN THEO VÙNG ---
ZONE_BASED_POLICIES = {
    LEADING_ZONE: {"NOTES": "Dò mìn cơ hội tiềm năng.", "CAPITAL_PCT": 0.040},
    COINCIDENT_ZONE: {"NOTES": "Vùng tốt nhất, quyết đoán vào lệnh.", "CAPITAL_PCT": 0.060},
    LAGGING_ZONE: {"NOTES": "An toàn, đi theo trend đã rõ.", "CAPITAL_PCT": 0.050},
    NOISE_ZONE: {"NOTES": "Nguy hiểm, vốn siêu nhỏ.", "CAPITAL_PCT": 0.030}
}

# --- PHÒNG THÍ NGHIỆM CHIẾN THUẬT (TACTICS LAB) ---
TACTICS_LAB = {
    "Balanced_Trader": {
        "OPTIMAL_ZONE": [LAGGING_ZONE, COINCIDENT_ZONE],
        "NOTES": "Chiến binh SWING TRADE chủ lực. Vào lệnh sớm hơn, gồng lệnh lì đòn qua các đợt điều chỉnh.",
        "WEIGHTS": {'tech': 0.4, 'context': 0.2, 'ai': 0.4},
        "ENTRY_SCORE": 6.3,
        "RR": 1.5,
        "ATR_SL_MULTIPLIER": 2.6,
        "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.6, "TRAIL_DISTANCE_RR": 1.2,
        "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.6, "TP1_PROFIT_PCT": 0.5,
        "USE_MOMENTUM_FILTER": True
    },
    "Breakout_Hunter": {
        "OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE],
        "NOTES": "Chuyên săn các điểm PHÁ VỠ đã được xác nhận. SL rộng để sống sót qua cú retest.",
        "WEIGHTS": {'tech': 0.6, 'context': 0.1, 'ai': 0.3},
        "ENTRY_SCORE": 7.0,
        "RR": 1.7,
        "ATR_SL_MULTIPLIER": 2.4,
        "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.5, "TRAIL_DISTANCE_RR": 1.0,
        "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.7, "TP1_PROFIT_PCT": 0.5,
        "USE_MOMENTUM_FILTER": True
    },
    "Dip_Hunter": {
        "OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE],
        "NOTES": "Bắt đáy/sóng hồi với một cái lưới an toàn CỰC RỘNG. Ăn nhanh, thoát nhanh.",
        "WEIGHTS": {'tech': 0.5, 'context': 0.2, 'ai': 0.3},
        "ENTRY_SCORE": 6.8,
        "RR": 1.4,
        "ATR_SL_MULTIPLIER": 3.2,
        "USE_TRAILING_SL": False,
        "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.6, "TP1_PROFIT_PCT": 0.6,
        "USE_MOMENTUM_FILTER": False
    },
    "AI_Aggressor": {
        "OPTIMAL_ZONE": [COINCIDENT_ZONE],
        "NOTES": "Chuyên gia chớp nhoáng: Tận dụng điểm AI siêu cao để vào nhanh, ăn ngắn, thoát nhanh.",
        "WEIGHTS": {'tech': 0.3, 'context': 0.1, 'ai': 0.6},
        "ENTRY_SCORE": 6.6,
        "RR": 1.5,
        "ATR_SL_MULTIPLIER": 2.2,
        "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.3, "TRAIL_DISTANCE_RR": 0.9,
        "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.8, "TP1_PROFIT_PCT": 0.6,
        "USE_MOMENTUM_FILTER": True
    },
    "Cautious_Observer": {
        "OPTIMAL_ZONE": NOISE_ZONE,
        "NOTES": "Bắn tỉa cơ hội VÀNG trong vùng nhiễu. SL chặt, ăn nhanh, sai là cắt.",
        "WEIGHTS": {'tech': 0.6, 'context': 0.2, 'ai': 0.2},
        "ENTRY_SCORE": 8.0,
        "RR": 1.4,
        "ATR_SL_MULTIPLIER": 1.8,
        "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.0, "TRAIL_DISTANCE_RR": 0.7,
        "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.7, "TP1_PROFIT_PCT": 0.7,
        "USE_MOMENTUM_FILTER": True
    },
}