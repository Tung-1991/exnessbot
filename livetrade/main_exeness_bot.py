# -*- coding: utf-8 -*-
# main_exness_bot.py
# Version: 2.3.0 - The Silent Operator
# Date: 2025-08-28
"""
CHANGELOG (v2.3.0):
- REFACTOR (Silent Operation): Loại bỏ toàn bộ thông báo sự kiện tức thời (mở/đóng lệnh).
- FEATURE (Consolidated Reporting): Gộp tất cả sự kiện vào Báo cáo Động duy nhất, tuân thủ cooldown nghiêm ngặt.
- REFACTOR (Smart Cooldown Logic): Cải tiến logic cooldown để linh hoạt và dễ cấu hình hơn.
"""

import os
import sys
import json
import uuid
import time
import logging
import math
import requests
import pytz
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv
import traceback

# --- CẤU HÌNH ĐƯỜNG DẪN & IMPORT ---
try:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(PROJECT_ROOT)
    if PARENT_DIR not in sys.path:
        sys.path.append(PARENT_DIR)

    load_dotenv(os.path.join(PARENT_DIR, '.env'))

    from exness_connector import ExnessConnector
    from indicator import calculate_indicators
    from trade_advisor import get_advisor_decision
except ImportError as e:
    sys.exit(f"Lỗi import module: {e}. Đảm bảo các file nằm đúng cấu trúc thư mục.")

# --- CẤU HÌNH THƯ MỤC & FILE ---
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "exness_state.json")
LOCK_FILE = STATE_FILE + ".lock"
TRADE_HISTORY_CSV = os.path.join(DATA_DIR, "exness_trade_history.csv")
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


# --- BIẾN TOÀN CỤC & LOGGER ---
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
logger = logging.getLogger("ExnessBot")

# ==============================================================================
# ==================== ⚙️ TRUNG TÂM CẤU HÌNH (UPGRADED) ⚙️ =====================
# ==============================================================================

GENERAL_CONFIG = {
    "SYMBOLS_TO_SCAN": [s.strip() for s in os.getenv("SYMBOLS_TO_SCAN", "BTCUSD,ETHUSD").split(',')], # Danh sách các cặp tiền tệ cần quét, đọc từ file .env hoặc mặc định
    "MAIN_TIMEFRAME": "5m",                                                  # Khung thời gian chính để bot phân tích và ra quyết định
    "MTF_TIMEFRAMES": ["5m", "15m", "1h"],                                   # Các khung thời gian phụ để phân tích đa khung thời gian (Multi-Timeframe Analysis)
    "LOOP_SLEEP_SECONDS": 2,                                                 # Thời gian (giây) tạm dừng giữa mỗi vòng lặp chính để giảm tải CPU
    "HEAVY_TASK_INTERVAL_MINUTES": 5,                                        # Chu kỳ (phút) chạy các tác vụ nặng (quét lệnh mới, cập nhật chỉ báo)
    "RECONCILIATION_INTERVAL_MINUTES": 15,                                   # Chu kỳ (phút) đối soát vị thế với sàn để phát hiện lệnh bị đóng thủ công
    "CANDLE_FETCH_COUNT": 300,                                               # Số lượng nến lịch sử cần tải về cho mỗi lần quét
    "TOP_N_OPPORTUNITIES_TO_CHECK": 5,                                       # Chỉ xem xét N cơ hội có điểm cao nhất để tiết kiệm thời gian
    "TRADE_COOLDOWN_HOURS": 1.0,                                             # Thời gian (giờ) chờ sau khi đóng một lệnh trên một cặp tiền
    "OVERRIDE_COOLDOWN_SCORE": 7.5,                                          # Điểm số tối thiểu để bot bỏ qua thời gian cooldown khi có tín hiệu cực mạnh
    "MAGIC_NUMBER": 202508,                                                  # Mã số định danh các lệnh của bot trên MT5 (phân biệt với lệnh thủ công)
    "DAILY_SUMMARY_TIMES": ["08:10", "20:10"],                               # Các mốc thời gian (HH:MM) để gửi báo cáo tổng kết hàng ngày
    "MIN_RAW_SCORE_THRESHOLD": 4.0,                                          # Ngưỡng điểm thô tối thiểu để một cơ hội được xem xét
    "CRITICAL_ERROR_COOLDOWN_MINUTES": 60,                                   # Thời gian (phút) chờ sau khi gửi thông báo lỗi nghiêm trọng để tránh spam
}

DYNAMIC_ALERT_CONFIG = {
    "ENABLED": True,                                                         # Bật/tắt toàn bộ tính năng báo cáo động (cập nhật trạng thái)
    "ALERT_COOLDOWN_MINUTES": 240,                                           # Thời gian (phút) chờ giữa các báo cáo động
    "PNL_CHANGE_THRESHOLD_PCT": 2.5,                                         # Ngưỡng thay đổi PnL (%) để kích hoạt báo cáo động
    "FORCE_UPDATE_MULTIPLIER": 2.5,                                          # Hệ số nhân để buộc cập nhật nếu quá thời gian cooldown (ví dụ: 240 * 2.5 = 600 phút)
}

MOMENTUM_FILTER_CONFIG = {
    "ENABLED": True,                                                         # Bật/tắt bộ lọc xác nhận động lượng
    "RULES_BY_TIMEFRAME": {                                                  # Quy tắc lọc theo khung thời gian ('WINDOW': số nến kiểm tra, 'REQUIRED_CANDLES': số nến đạt chuẩn)
        "5m": {"WINDOW": 5, "REQUIRED_CANDLES": 3},
        "15m": {"WINDOW": 5, "REQUIRED_CANDLES": 2},
        "1h": {"WINDOW": 4, "REQUIRED_CANDLES": 1}
    }
}

CAPITAL_MANAGEMENT_CONFIG = {
    "ENABLED": True,                                                         # Bật/tắt tính năng quản lý vốn tự động
    "AUTO_COMPOUND_THRESHOLD_PCT": 10.0,                                     # Ngưỡng tăng trưởng (%) để bot tự động tính lãi kép (cập nhật vốn nền tảng)
    "AUTO_DELEVERAGE_THRESHOLD_PCT": -10.0,                                  # Ngưỡng thua lỗ (%) để bot tự động giảm rủi ro (cập nhật vốn nền tảng)
    "CAPITAL_ADJUSTMENT_COOLDOWN_HOURS": 48,                                 # Thời gian (giờ) chờ giữa các lần điều chỉnh vốn tự động
    "DEPOSIT_DETECTION_MIN_USD": 20.0,                                       # Ngưỡng nạp/rút tối thiểu (USD) để bot nhận biết
    "DEPOSIT_DETECTION_THRESHOLD_PCT": 0.02,                                 # Ngưỡng nạp/rút tối thiểu (phần trăm vốn) để bot nhận biết
}

MTF_ANALYSIS_CONFIG = {
    "ENABLED": True,                                                         # Bật/tắt phân tích đa khung thời gian
    "BONUS_COEFFICIENT": 1.05,                                               # Hệ số thưởng khi xu hướng khung lớn trùng với khung nhỏ
    "PENALTY_COEFFICIENT": 0.95,                                             # Hệ số phạt khi xu hướng khung lớn ngược với khung nhỏ
    "SEVERE_PENALTY_COEFFICIENT": 0.85,                                      # Hệ số phạt nặng khi các khung lớn đều ngược xu hướng
    "SIDEWAYS_PENALTY_COEFFICIENT": 0.97,                                    # Hệ số phạt khi khung lớn đi ngang (sideways)
}

EXTREME_ZONE_ADJUSTMENT_CONFIG = {
    "ENABLED": True,                                                         # Bật/tắt việc điều chỉnh điểm số dựa trên vùng cực đoan (quá mua/quá bán)
    "MAX_BONUS_COEFF": 1.10, "MIN_PENALTY_COEFF": 0.90,                       # Hệ số điều chỉnh điểm số tối đa và tối thiểu
    "SCORING_WEIGHTS": { "RSI": 0.4, "BB_POS": 0.4, "CANDLE": 0.35, "SR_LEVEL": 0.35 }, # Trọng số của các yếu tố khi tính điểm vùng cực đoan
    "BASE_IMPACT": { "BONUS_PER_POINT": 0.07, "PENALTY_PER_POINT": -0.08 },   # Mức độ tác động cơ bản lên hệ số điều chỉnh
    "CONFLUENCE_MULTIPLIER": 1.6,                                            # Hệ số nhân khi có nhiều yếu tố cùng xác nhận
    "RULES_BY_TIMEFRAME": {                                                  # Ngưỡng RSI và Bollinger Bands để xác định vùng cực đoan
        "5m": {"OVERBOUGHT": {"RSI_ABOVE": 75, "BB_POS_ABOVE": 0.98}, "OVERSOLD": {"RSI_BELOW": 25, "BB_POS_BELOW": 0.05}},
        "15m": {"OVERBOUGHT": {"RSI_ABOVE": 73, "BB_POS_ABOVE": 0.95}, "OVERSOLD": {"RSI_BELOW": 27, "BB_POS_BELOW": 0.08}},
        "1h": {"OVERBOUGHT": {"RSI_ABOVE": 72, "BB_POS_ABOVE": 0.95}, "OVERSOLD": {"RSI_BELOW": 30, "BB_POS_BELOW": 0.10}}
    },
    "CONFIRMATION_BOOST": {                                                  # Cấu hình thưởng điểm từ nến xác nhận và mức cản
        "ENABLED": True,                                                     # Bật/tắt thưởng điểm xác nhận
        "BEARISH_CANDLES": ["shooting_star", "bearish_engulfing", "gravestone"], # Danh sách các mẫu nến giảm giá xác nhận
        "BULLISH_CANDLES": ["hammer", "bullish_engulfing", "dragonfly"],     # Danh sách các mẫu nến tăng giá xác nhận
        "RESISTANCE_PROXIMITY_PCT": 0.005, "SUPPORT_PROXIMITY_PCT": 0.005,    # Ngưỡng gần kháng cự/hỗ trợ (%) để được tính điểm
    }
}

ACTIVE_TRADE_MANAGEMENT_CONFIG = {
    "EARLY_CLOSE_ABS_THRESHOLD_L": 4.5, "EARLY_CLOSE_ABS_THRESHOLD_S": -4.5,   # Ngưỡng điểm số tuyệt đối để đóng lệnh sớm (L: Long, S: Short)
    "EARLY_CLOSE_REL_DROP_PCT": 0.30,                                        # Ngưỡng sụt giảm điểm tương đối (%) để đóng lệnh sớm một phần
    "PARTIAL_EARLY_CLOSE_PCT": 0.5,                                          # Tỷ lệ khối lượng (%) sẽ đóng khi tín hiệu suy yếu
    "PROFIT_PROTECTION": {                                                   # Cấu hình bảo vệ lợi nhuận khi giá quay đầu
        "ENABLED": True,                                                     # Bật/tắt tính năng bảo vệ lợi nhuận
        "MIN_PEAK_PNL_TRIGGER": 2.5,                                         # Mức PnL đỉnh tối thiểu (%) để kích hoạt
        "PNL_DROP_TRIGGER_PCT": 1.0,                                         # Mức sụt giảm PnL (%) từ đỉnh để kích hoạt chốt lời
        "PARTIAL_CLOSE_PCT": 0.5                                             # Tỷ lệ khối lượng (%) sẽ đóng để bảo vệ lợi nhuận
    },
    "SMART_TSL": {                                                           # Cấu hình Trailing Stop Loss (TSL) thông minh
        "ENABLED": True,                                                     # Bật/tắt TSL thông minh
        "ATR_REDUCTION_FACTOR": 0.8                                          # Yêu cầu ATR hiện tại phải nhỏ hơn ATR lúc vào lệnh * hệ số này
    }
}

RISK_RULES_CONFIG = {
    "RISK_PER_TRADE_PERCENT": 1.0,                                           # Rủi ro tối đa cho mỗi lệnh (tính theo % vốn)
    "MAX_ACTIVE_TRADES": 5,                                                  # Số lệnh tối đa được phép mở cùng lúc
    "MAX_TOTAL_RISK_EXPOSURE_PERCENT": 10.0,                                 # Tổng rủi ro tối đa của tất cả các lệnh đang mở (tính theo % vốn)
    "OPEN_TRADE_RETRY_LIMIT": 3,                                             # Số lần thử lại tối đa khi đặt lệnh
    "CLOSE_TRADE_RETRY_LIMIT": 3,                                            # Số lần thử lại tối đa khi đóng lệnh
    "RETRY_DELAY_SECONDS": 5,                                                # Thời gian (giây) chờ giữa các lần thử lại
    "STALE_TRADE_RULES": {                                                   # Quy tắc xử lý các lệnh "bị ứ đọng" (quá lâu không có tiến triển)
        "5m": {"HOURS": 8, "PROGRESS_THRESHOLD_PCT": 1.0},                   # Điều kiện cho khung 5m: giữ quá 8 giờ và PnL < 1%
        "STAY_OF_EXECUTION_SCORE_L": 6.0,                                    # Điểm số Long tối thiểu để lệnh được "ân xá"
        "STAY_OF_EXECUTION_SCORE_S": -6.0                                    # Điểm số Short tối thiểu để lệnh được "ân xá"
    }
}

DCA_CONFIG = {
    "ENABLED": True, "MAX_DCA_ENTRIES": 2,                                   # Bật/tắt tính năng Trung bình giá (DCA) và số lần DCA tối đa
    "STRATEGY": "aggressive",                                                # Chiến lược DCA: 'aggressive' (gấp thếp) hoặc 'conservative' (khiêm tốn)
    "MULTIPLIERS": {                                                         # Hệ số nhân lot size cho mỗi lần DCA
        "aggressive": 1.5,
        "conservative": 0.75
    },
    "TRIGGER_DROP_PCT_BY_TIMEFRAME": {"5m": -3.0, "15m": -4.0, "1h": -5.0},   # Ngưỡng sụt giảm giá (%) để kích hoạt DCA
    "SCORE_MIN_THRESHOLD_LONG": 6.5, "SCORE_MIN_THRESHOLD_SHORT": -6.5,       # Ngưỡng điểm tối thiểu để được phép DCA
    "DCA_COOLDOWN_HOURS": 4                                                  # Thời gian (giờ) chờ giữa các lần DCA cho cùng một lệnh
}

DISCORD_CONFIG = {
    "WEBHOOK_URL": os.getenv("DISCORD_EXNESS_WEBHOOK"),                      # URL Webhook để gửi thông báo Discord (lấy từ file .env)
    "CHUNK_DELAY_SECONDS": 2                                                 # Thời gian (giây) chờ giữa các chunk khi gửi tin nhắn dài
}

# Cấu hình cho file log
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024                                         # Kích thước tối đa của một file log (5MB)
LOG_FILE_BACKUP_COUNT = 3                                                    # Số lượng file log backup được giữ lại

# Định nghĩa các Vùng Thị trường
LEADING_ZONE, COINCIDENT_ZONE, LAGGING_ZONE, NOISE_ZONE = "LEADING", "COINCIDENT", "LAGGING", "NOISE"

# Chính sách điều chỉnh rủi ro dựa trên Vùng Thị trường
ZONE_BASED_POLICIES = {
    LEADING_ZONE: {"CAPITAL_RISK_MULTIPLIER": 0.8},                          # Giảm rủi ro khi thị trường có dấu hiệu sớm (có thể là fakeout)
    COINCIDENT_ZONE: {"CAPITAL_RISK_MULTIPLIER": 1.2},                       # Tăng rủi ro khi thị trường đang có tín hiệu đồng thuận, rõ ràng
    LAGGING_ZONE: {"CAPITAL_RISK_MULTIPLIER": 1.0},                          # Giữ rủi ro chuẩn khi thị trường đang trong xu hướng
    NOISE_ZONE: {"CAPITAL_RISK_MULTIPLIER": 0.5}                             # Giảm mạnh rủi ro khi thị trường nhiễu, không rõ xu hướng
}

# ==============================================================================
# ======================== TACTICS LAB - BỘ CHIẾN THUẬT =======================
# ==============================================================================

TACTICS_LAB = {
    # Chiến thuật "Giao dịch Cân bằng" - Long
    "Balanced_Trader_L": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [LAGGING_ZONE, COINCIDENT_ZONE],
        "TRADE_TYPE": "LONG",
        "ENTRY_SCORE": 6.3,
        "RR": 1.5,
        "ATR_SL_MULTIPLIER": 2.5,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.2,
        "TRAIL_DISTANCE_RR": 0.8,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.6,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": True
    },
    # Chiến thuật "Săn điểm Breakout" - Long
    "Breakout_Hunter_L": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE],
        "TRADE_TYPE": "LONG",
        "ENTRY_SCORE": 7.0,
        "RR": 1.7,
        "ATR_SL_MULTIPLIER": 2.4,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.3,
        "TRAIL_DISTANCE_RR": 0.9,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.6,
        "TP1_PROFIT_PCT": 0.5,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": False
    },
    # Chiến thuật "Săn điểm Hồi" - Long
    "Dip_Hunter_L": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE],
        "TRADE_TYPE": "LONG",
        "ENTRY_SCORE": 6.8,
        "RR": 1.4,
        "ATR_SL_MULTIPLIER": 3.2,
        "USE_TRAILING_SL": False,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.7,
        "USE_MOMENTUM_FILTER": False,
        "USE_EXTREME_ZONE_FILTER": True
    },
    # Chiến thuật "Phản công của AI" - Long
    "AI_Aggressor_L": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [COINCIDENT_ZONE],
        "TRADE_TYPE": "LONG",
        "ENTRY_SCORE": 6.6,
        "RR": 1.5,
        "ATR_SL_MULTIPLIER": 2.2,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.1,
        "TRAIL_DISTANCE_RR": 0.7,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.6,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": False
    },
    # Chiến thuật "Quan sát thận trọng" - Long
    "Cautious_Observer_L": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [NOISE_ZONE],
        "TRADE_TYPE": "LONG",
        "ENTRY_SCORE": 7.5,
        "RR": 1.3,
        "ATR_SL_MULTIPLIER": 1.8,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.0,
        "TRAIL_DISTANCE_RR": 0.6,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.7,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": True
    },
    # Chiến thuật "Giao dịch Cân bằng" - Short
    "Balanced_Seller_S": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [LAGGING_ZONE, COINCIDENT_ZONE],
        "TRADE_TYPE": "SHORT",
        "ENTRY_SCORE": -6.3,
        "RR": 1.5,
        "ATR_SL_MULTIPLIER": 2.5,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.2,
        "TRAIL_DISTANCE_RR": 0.8,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.6,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": True
    },
    # Chiến thuật "Săn điểm Breakdown" - Short
    "Breakdown_Hunter_S": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE],
        "TRADE_TYPE": "SHORT",
        "ENTRY_SCORE": -7.0,
        "RR": 1.7,
        "ATR_SL_MULTIPLIER": 2.4,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.3,
        "TRAIL_DISTANCE_RR": 0.9,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.6,
        "TP1_PROFIT_PCT": 0.5,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": False
    },
    # Chiến thuật "Bán đỉnh Hồi" - Short
    "Rally_Seller_S": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE],
        "TRADE_TYPE": "SHORT",
        "ENTRY_SCORE": -6.8,
        "RR": 1.4,
        "ATR_SL_MULTIPLIER": 3.2,
        "USE_TRAILING_SL": False,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.7,
        "USE_MOMENTUM_FILTER": False,
        "USE_EXTREME_ZONE_FILTER": True
    },
    # Chiến thuật "Phản công của AI" - Short
    "AI_Contrarian_S": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [COINCIDENT_ZONE],
        "TRADE_TYPE": "SHORT",
        "ENTRY_SCORE": -6.6,
        "RR": 1.5,
        "ATR_SL_MULTIPLIER": 2.2,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.1,
        "TRAIL_DISTANCE_RR": 0.7,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.6,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": False
    },
    # Chiến thuật "Bán khống Thận trọng" - Short
    "Cautious_Shorter_S": {
        "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
        "OPTIMAL_ZONE": [NOISE_ZONE],
        "TRADE_TYPE": "SHORT",
        "ENTRY_SCORE": -7.5,
        "RR": 1.3,
        "ATR_SL_MULTIPLIER": 1.8,
        "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR": 1.0,
        "TRAIL_DISTANCE_RR": 0.6,
        "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO": 0.5,
        "TP1_PROFIT_PCT": 0.7,
        "USE_MOMENTUM_FILTER": True,
        "USE_EXTREME_ZONE_FILTER": True
    },
}

# ==============================================================================
# ==================== BIẾN TOÀN CỤC & HÀM TIỆN ÍCH ====================
# ==============================================================================

connector = None
state = {}
indicator_results = {}
price_dataframes = {}

SESSION_TEMP_KEYS = [
    'session_has_events', 'session_realized_pnl', 'session_orphan_alerts', 'session_events'
]

def setup_logging():
    global logger
    os.makedirs(LOG_DIR, exist_ok=True)
    log_filename = os.path.join(LOG_DIR, "exness_bot_info.log")
    file_handler = RotatingFileHandler(log_filename, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    error_log_filename = os.path.join(LOG_DIR, "exness_bot_error.log")
    error_file_handler = logging.FileHandler(error_log_filename, encoding='utf-8')
    error_file_handler.setLevel(logging.ERROR)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    
    # SỬA ĐỊNH DẠNG LOG CHO GIỐNG MẪU SẾP THÍCH
    formatter = logging.Formatter("[%(asctime)s] (ExnessBot) %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    file_handler.setFormatter(formatter)
    error_file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    if logger.hasHandlers(): logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(error_file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)
    
    # *** DÒNG THẦN THÁNH: Chặn log bị lặp ***
    # Ngăn logger này đẩy message lên cho logger cha (root logger), tránh in 2 lần.
    logger.propagate = False

def acquire_lock(timeout=10):
    if os.path.exists(LOCK_FILE):
        try:
            if (time.time() - os.path.getmtime(LOCK_FILE)) / 60 > 5:
                logger.warning("Lock file cũ. Tự động xóa.")
                release_lock()
        except Exception: pass
    start_time = time.time()
    while os.path.exists(LOCK_FILE):
        if time.time() - start_time > timeout: return False
        time.sleep(1)
    try:
        with open(LOCK_FILE, 'w') as f: f.write(str(os.getpid()))
        return True
    except IOError: return False

def release_lock():
    try:
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
    except OSError: pass

def load_state():
    global state
    default_state = {
        "active_trades": [], "trade_history": [], "initial_capital": 0.0,
        "last_dynamic_alert": {}, "last_reported_pnl_percent": 0.0,
        "last_error_sent_time": None, "last_capital_adjustment_time": None,
        "balance_end_of_last_session": 0.0, "realized_pnl_last_session": 0.0,
        "orphan_position_alerts": {},
    }
    if not os.path.exists(STATE_FILE):
        state = default_state
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f: state = json.load(f)
        for key, value in default_state.items(): state.setdefault(key, value)
    except (json.JSONDecodeError, FileNotFoundError): state = default_state

def save_state():
    temp_path = STATE_FILE + ".tmp"
    data_to_save = state.copy()
    for key in SESSION_TEMP_KEYS: data_to_save.pop(key, None)
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)
    os.replace(temp_path, STATE_FILE)

def format_price(price):
    if price is None: return "N/A"
    return f"{price:,.5f}" if price < 10 else f"{price:,.2f}"

def export_trade_to_csv(trade):
    try:
        df = pd.DataFrame([trade])
        df.to_csv(TRADE_HISTORY_CSV, mode='a', header=not os.path.exists(TRADE_HISTORY_CSV), index=False)
    except Exception as e: logger.error(f"Lỗi xuất CSV: {e}")

def get_current_pnl(trade, current_price):
    if not current_price or trade['entry_price'] <= 0: return 0.0, 0.0
    try:
        trade_type_str = "LONG" if trade['type'] == "LONG" else "SHORT"
        profit = connector.calculate_profit(trade['symbol'], trade_type_str, trade['lot_size'], trade['entry_price'], current_price)
        pnl_usd = profit if profit is not None else 0.0
        capital_at_risk = trade.get('risk_amount_usd', 1)
        pnl_percent = (pnl_usd / capital_at_risk) * 100 if capital_at_risk > 0 else 0.0
        return pnl_usd, pnl_percent
    except Exception: return 0.0, 0.0

def send_discord_message(content: str, force: bool = False, is_error: bool = False):
    webhook_url = DISCORD_CONFIG.get("WEBHOOK_URL")
    if not webhook_url: return
    max_len, lines, chunks, current_chunk = 1900, content.split('\n'), [], ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_len:
            if current_chunk: chunks.append(current_chunk)
            current_chunk = line
        else: current_chunk += ("\n" + line) if current_chunk else line
    if current_chunk: chunks.append(current_chunk)
    for i, chunk in enumerate(chunks):
        content_to_send = f"*(Phần {i+1}/{len(chunks)})*\n{chunk}" if len(chunks) > 1 else chunk
        try:
            requests.post(webhook_url, json={"content": content_to_send}, timeout=15).raise_for_status()
            if i < len(chunks) - 1: time.sleep(DISCORD_CONFIG["CHUNK_DELAY_SECONDS"])
        except requests.exceptions.RequestException as e:
            logger.error(f"Lỗi gửi Discord: {e}")
            break

def build_dynamic_alert_text(state: Dict, equity: float) -> str:
    now_vn_str = datetime.now(VIETNAM_TZ).strftime('%H:%M %d-%m-%Y')
    initial_capital = state.get('initial_capital', 1.0)
    pnl_total_usd = equity - initial_capital
    pnl_total_percent = (pnl_total_usd / initial_capital) * 100 if initial_capital > 0 else 0
    pnl_icon = "🟢" if pnl_total_usd >= 0 else "🔴"
    header = f"💰 Vốn BĐ: **${initial_capital:,.2f}** | 📊 Equity: **${equity:,.2f}** | 📈 PnL Tổng: {pnl_icon} **${pnl_total_usd:,.2f} ({pnl_total_percent:+.2f}%)**"
    lines = [f"💡 **CẬP NHẬT ĐỘNG EXNESS BOT** - `{now_vn_str}`", header]

    session_events = state.get('session_events', [])
    if session_events:
        lines.append(f"\n--- **Sự kiện gần đây** ---")
        lines.extend([f"    - {event}" for event in session_events])

    lines.append(f"\n--- **Vị thế đang mở ({len(state.get('active_trades', []))})** ---")
    if not state.get('active_trades'):
        lines.append("    (Không có vị thế nào)")
    else:
        for trade in sorted(state.get('active_trades', []), key=lambda x: x.get('entry_time', '')):
            tick = mt5.symbol_info_tick(trade['symbol'])
            if not tick: continue
            current_price = tick.bid if trade['type'] == "LONG" else tick.ask
            pnl_usd, pnl_percent = get_current_pnl(trade, current_price)
            icon_trade = "🟢" if pnl_usd >= 0 else "🔴"
            holding_hours = (datetime.now(VIETNAM_TZ) - datetime.fromisoformat(trade['entry_time'])).total_seconds() / 3600
            lines.append(f"    {icon_trade} **{trade['symbol']}** ({trade['type']}) | PnL: **${pnl_usd:+.2f} ({pnl_percent:+.2f}%)** | Giữ: `{holding_hours:.1f}h`")
    lines.append("\n====================================")
    return "\n".join(lines)

def should_send_report(state: Dict, equity: Optional[float]) -> Optional[str]:
    if not DYNAMIC_ALERT_CONFIG.get("ENABLED", False) or equity is None:
        return None

    now_vn = datetime.now(VIETNAM_TZ)
    last_summary_dt = None
    if state.get('last_summary_sent_time'):
        last_summary_dt = datetime.fromisoformat(state.get('last_summary_sent_time')).astimezone(VIETNAM_TZ)

    for time_str in GENERAL_CONFIG.get("DAILY_SUMMARY_TIMES", []):
        hour, minute = map(int, time_str.split(':'))
        scheduled_dt_today = now_vn.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now_vn >= scheduled_dt_today and (last_summary_dt is None or last_summary_dt < scheduled_dt_today):
            return "daily"

    last_alert_str = state.get('last_dynamic_alert', {}).get("timestamp")
    if last_alert_str:
        last_alert_dt = datetime.fromisoformat(last_alert_str).astimezone(VIETNAM_TZ)
        minutes_since_last_alert = (now_vn - last_alert_dt).total_seconds() / 60
        cooldown_minutes = DYNAMIC_ALERT_CONFIG["ALERT_COOLDOWN_MINUTES"]
        if minutes_since_last_alert < cooldown_minutes:
            return None

    if state.get('session_has_events', False):
        return "dynamic_event"

    initial_capital = state.get('initial_capital', 1.0)
    current_pnl_percent = ((equity - initial_capital) / initial_capital) * 100 if initial_capital > 0 else 0
    last_reported_pnl = state.get('last_reported_pnl_percent', 0.0)
    pnl_change_threshold = DYNAMIC_ALERT_CONFIG.get("PNL_CHANGE_THRESHOLD_PCT", 2.5)
    if abs(current_pnl_percent - last_reported_pnl) >= pnl_change_threshold:
        return "dynamic_pnl_change"

    if last_alert_str:
        last_alert_dt = datetime.fromisoformat(last_alert_str).astimezone(VIETNAM_TZ)
        minutes_since_last_alert = (now_vn - last_alert_dt).total_seconds() / 60
        cooldown_minutes = DYNAMIC_ALERT_CONFIG["ALERT_COOLDOWN_MINUTES"]
        force_multiplier = DYNAMIC_ALERT_CONFIG.get("FORCE_UPDATE_MULTIPLIER", 2.5)
        if minutes_since_last_alert >= (cooldown_minutes * force_multiplier):
            return "dynamic_force_update"

    return None

def load_all_indicators():
    symbols_to_load = list(set(GENERAL_CONFIG["SYMBOLS_TO_SCAN"] + [t['symbol'] for t in state.get('active_trades', [])]))
    for symbol in symbols_to_load:
        indicator_results[symbol], price_dataframes[symbol] = {}, {}
        for timeframe in GENERAL_CONFIG["MTF_TIMEFRAMES"]:
            df = connector.get_historical_data(symbol, timeframe, GENERAL_CONFIG["CANDLE_FETCH_COUNT"])
            if df is not None and not df.empty:
                indicator_results[symbol][timeframe] = calculate_indicators(df, symbol, timeframe)
                price_dataframes[symbol][timeframe] = df

def update_scores_for_active_trades():
    active_trades = state.get("active_trades", [])
    if not active_trades: return
    for trade in active_trades:
        indicators = indicator_results.get(trade['symbol'], {}).get(GENERAL_CONFIG['MAIN_TIMEFRAME'])
        if indicators:
            tactic_cfg = TACTICS_LAB.get(trade.get('opened_by_tactic'), {})
            tactic_weights = tactic_cfg.get("WEIGHTS")
            decision = get_advisor_decision(trade['symbol'], GENERAL_CONFIG['MAIN_TIMEFRAME'], indicators, {"WEIGHTS": tactic_weights})
            raw_score = decision.get('final_score', 0.0)
            mtf_coeff = get_mtf_adjustment_coefficient(trade['symbol'], GENERAL_CONFIG['MAIN_TIMEFRAME'], trade['type'])
            ez_coeff = 1.0
            if tactic_cfg.get("USE_EXTREME_ZONE_FILTER", False):
                ez_coeff = get_extreme_zone_adjustment_coefficient(indicators, GENERAL_CONFIG['MAIN_TIMEFRAME'])
            new_score = raw_score * mtf_coeff * ez_coeff
            trade['last_score'] = new_score
            trade['last_zone'] = determine_market_zone(indicators)

def determine_market_zone(indicators):
    scores = {LEADING_ZONE: 0, COINCIDENT_ZONE: 0, LAGGING_ZONE: 0, NOISE_ZONE: 0}
    adx, bb_width, trend = indicators.get('adx', 20), indicators.get('bb_width', 0), indicators.get('trend', "sideways")
    if adx < 20: scores[NOISE_ZONE] += 3
    if adx > 25 and trend != "sideways": scores[LAGGING_ZONE] += 2.5
    df = price_dataframes.get(indicators.get('symbol'), {}).get(indicators.get('interval'), pd.DataFrame())
    if not df.empty and 'bb_width' in df.columns and not df['bb_width'].isna().all():
        if bb_width < df['bb_width'].quantile(0.15): scores[LEADING_ZONE] += 2.5
    if indicators.get('breakout_signal', "none") != "none": scores[COINCIDENT_ZONE] += 3
    if indicators.get('macd_cross', "neutral") not in ["neutral", "no_cross"]: scores[COINCIDENT_ZONE] += 2
    ema_12, ema_26, ema_cross = indicators.get('ema_12', 0), indicators.get('ema_26', 0), indicators.get('ema_cross', 'none')
    if ema_cross in ['bullish', 'bearish']: scores[COINCIDENT_ZONE] += 2.5
    elif ema_12 > ema_26 and trend == 'uptrend': scores[LAGGING_ZONE] += 2
    elif ema_12 < ema_26 and trend == 'downtrend': scores[LAGGING_ZONE] += 2
    return max(scores, key=scores.get) if any(v > 0 for v in scores.values()) else NOISE_ZONE

def get_mtf_adjustment_coefficient(symbol, target_interval, trade_type):
    if not MTF_ANALYSIS_CONFIG["ENABLED"]: return 1.0
    trends = {tf: indicator_results.get(symbol, {}).get(tf, {}).get("trend", "sideways") for tf in GENERAL_CONFIG["MTF_TIMEFRAMES"]}
    fav_trend, unfav_trend = ("uptrend", "downtrend") if trade_type == "LONG" else ("downtrend", "uptrend")
    if target_interval == "5m":
        t15, t1h = trends.get("15m"), trends.get("1h")
        if t15 == unfav_trend and t1h == unfav_trend: return MTF_ANALYSIS_CONFIG["SEVERE_PENALTY_COEFFICIENT"]
        if t15 == unfav_trend or t1h == unfav_trend: return MTF_ANALYSIS_CONFIG["PENALTY_COEFFICIENT"]
        if t15 == fav_trend and t1h == fav_trend: return MTF_ANALYSIS_CONFIG["BONUS_COEFFICIENT"]
        return MTF_ANALYSIS_CONFIG["SIDEWAYS_PENALTY_COEFFICIENT"]
    return 1.0

def get_extreme_zone_adjustment_coefficient(indicators, interval):
    cfg = EXTREME_ZONE_ADJUSTMENT_CONFIG
    if not cfg.get("ENABLED", False): return 1.0
    weights, rules = cfg.get("SCORING_WEIGHTS", {}), cfg.get("RULES_BY_TIMEFRAME", {}).get(interval)
    if not rules: return 1.0
    price, rsi = indicators.get("price", 0), indicators.get("rsi_14", 50)
    bbu, bbm, bbl = indicators.get("bb_upper", 0), indicators.get("bb_middle", 0), indicators.get("bb_lower", 0)
    if not all([price > 0, bbu > bbm, bbm > bbl]): return 1.0
    bonus_score, penalty_score = 0.0, 0.0
    confirmation_cfg = cfg.get("CONFIRMATION_BOOST", {})
    oversold_rule = rules.get("OVERSOLD", {})
    bb_range = bbu - bbl
    if bb_range > 0:
        bb_pos = (price - bbl) / bb_range
        if rsi < oversold_rule.get("RSI_BELOW", 1): bonus_score += weights.get("RSI", 0)
        if bb_pos < oversold_rule.get("BB_POS_BELOW", 0.05): bonus_score += weights.get("BB_POS", 0)
    if confirmation_cfg.get("ENABLED"):
        candle, sup_level = indicators.get("candle_pattern"), indicators.get("support_level", 0)
        if candle in confirmation_cfg.get("BULLISH_CANDLES", []): bonus_score += weights.get("CANDLE", 0)
        is_near_support = sup_level > 0 and abs(price - sup_level) / price < confirmation_cfg.get("SUPPORT_PROXIMITY_PCT", 0.01)
        if is_near_support: bonus_score += weights.get("SR_LEVEL", 0)
    overbought_rule = rules.get("OVERBOUGHT", {})
    if bb_range > 0:
        bb_pos = (price - bbl) / bb_range
        if rsi > overbought_rule.get("RSI_ABOVE", 99): penalty_score += weights.get("RSI", 0)
        if bb_pos > overbought_rule.get("BB_POS_ABOVE", 0.98): penalty_score += weights.get("BB_POS", 0)
    if confirmation_cfg.get("ENABLED"):
        candle, res_level = indicators.get("candle_pattern"), indicators.get("resistance_level", 0)
        if candle in confirmation_cfg.get("BEARISH_CANDLES", []): penalty_score += weights.get("CANDLE", 0)
        is_near_resistance = res_level > 0 and abs(price - res_level) / price < confirmation_cfg.get("RESISTANCE_PROXIMITY_PCT", 0.01)
        if is_near_resistance: penalty_score += weights.get("SR_LEVEL", 0)
    if bonus_score >= (weights.get("RSI", 0.4) + weights.get("BB_POS", 0.4)): bonus_score *= cfg["CONFLUENCE_MULTIPLIER"]
    if penalty_score >= (weights.get("RSI", 0.4) + weights.get("BB_POS", 0.4)): penalty_score *= cfg["CONFLUENCE_MULTIPLIER"]
    base_impact = cfg.get("BASE_IMPACT", {})
    coeff_change = (bonus_score * base_impact.get("BONUS_PER_POINT", 0)) + (penalty_score * base_impact.get("PENALTY_PER_POINT", 0))
    calculated_coeff = 1.0 + coeff_change
    return max(cfg["MIN_PENALTY_COEFF"], min(calculated_coeff, cfg["MAX_BONUS_COEFF"]))

def is_momentum_confirmed(symbol, interval, direction="LONG"):
    config = MOMENTUM_FILTER_CONFIG
    if not config.get("ENABLED", False): return True
    rules = config.get("RULES_BY_TIMEFRAME", {}).get(interval, {"WINDOW": 3, "REQUIRED_CANDLES": 2})
    window, required_candles = rules.get("WINDOW", 3), rules.get("REQUIRED_CANDLES", 2)
    try:
        df = price_dataframes.get(symbol, {}).get(interval)
        if df is None or len(df) < window or 'volume_sma_20' not in df.columns: return True
        recent_candles, good_candles_count = df.iloc[-window:], 0
        for _, candle in recent_candles.iterrows():
            candle_range = candle['high'] - candle['low']
            if candle_range == 0: continue
            is_green = candle['close'] > candle['open']
            closing_position_ratio = (candle['close'] - candle['low']) / candle_range
            price_condition_met = (direction == "LONG" and (is_green or closing_position_ratio > 0.6)) or \
                                 (direction != "LONG" and (not is_green or closing_position_ratio < 0.4))
            volume_condition_met = candle['tick_volume'] > candle.get('volume_sma_20', 0)
            if price_condition_met and volume_condition_met: good_candles_count += 1
        return good_candles_count >= required_candles
    except Exception as e:
        logger.error(f"Lỗi is_momentum_confirmed: {e}")
        return True

def manage_dynamic_capital():
    if not CAPITAL_MANAGEMENT_CONFIG["ENABLED"]: return
    now_dt, account_info = datetime.now(VIETNAM_TZ), connector.get_account_info()
    if not account_info: return
    current_equity, current_balance, initial_capital = account_info['equity'], account_info['balance'], state.get('initial_capital', 0.0)
    if initial_capital <= 0:
        state.update({'initial_capital': current_equity, 'last_capital_adjustment_time': now_dt.isoformat(),
                      'balance_end_of_last_session': current_balance, 'realized_pnl_last_session': 0.0})
        logger.info(f"🌱 Thiết lập Vốn Nền tảng ban đầu: ${state['initial_capital']:,.2f}")
        save_state()
        return
    balance_prev_session, pnl_prev_session = state.get("balance_end_of_last_session", 0.0), state.get("realized_pnl_last_session", 0.0)
    if balance_prev_session > 0:
        expected_balance = balance_prev_session + pnl_prev_session
        net_deposit = current_balance - expected_balance
        threshold = max(CAPITAL_MANAGEMENT_CONFIG["DEPOSIT_DETECTION_MIN_USD"], state.get("initial_capital", 1) * CAPITAL_MANAGEMENT_CONFIG["DEPOSIT_DETECTION_THRESHOLD_PCT"])
        if abs(net_deposit) > threshold:
            reason = "Nạp tiền" if net_deposit > 0 else "Rút tiền"
            logger.info(f"💵 Phát hiện {reason} ròng: ${net_deposit:,.2f}. Cập nhật Vốn Nền tảng.")
            state["initial_capital"] = state.get("initial_capital", 0.0) + net_deposit
            state['last_capital_adjustment_time'] = now_dt.isoformat()
            logger.info(f"    Vốn Nền tảng được cập nhật: ${state['initial_capital']:,.2f}")
    last_adj_str, cooldown = state.get('last_capital_adjustment_time'), CAPITAL_MANAGEMENT_CONFIG["CAPITAL_ADJUSTMENT_COOLDOWN_HOURS"]
    if last_adj_str and (now_dt - datetime.fromisoformat(last_adj_str)).total_seconds() / 3600 < cooldown: return
    growth_pct = (current_equity / state["initial_capital"] - 1) * 100 if state["initial_capital"] > 0 else 0
    compound_threshold, delever_threshold = CAPITAL_MANAGEMENT_CONFIG["AUTO_COMPOUND_THRESHOLD_PCT"], CAPITAL_MANAGEMENT_CONFIG["AUTO_DELEVERAGE_THRESHOLD_PCT"]
    if growth_pct >= compound_threshold or growth_pct <= delever_threshold:
        reason = "Lãi kép" if growth_pct >= compound_threshold else "Giảm rủi ro"
        logger.info(f"💰 Hiệu suất ({growth_pct:+.2f}%) đạt ngưỡng. Lý do: {reason}. Cập nhật Vốn Nền tảng.")
        logger.info(f"    Vốn cũ: ${state['initial_capital']:,.2f}")
        state.update({"initial_capital": current_equity, 'last_capital_adjustment_time': now_dt.isoformat()})
        logger.info(f"    Vốn Nền tảng MỚI: ${state['initial_capital']:,.2f}")
        save_state()

def find_and_open_new_trades():
    # --- BƯỚC 1: KIỂM TRA ĐIỀU KIỆN TỔNG THỂ ---
    if len(state.get("active_trades", [])) >= RISK_RULES_CONFIG["MAX_ACTIVE_TRADES"]:
        logger.debug("Đã đạt giới hạn %d lệnh mở. Bỏ qua quét.", RISK_RULES_CONFIG["MAX_ACTIVE_TRADES"])
        return
        
    account_info = connector.get_account_info()
    if not account_info: return
    
    current_total_risk_usd = sum(t.get('risk_amount_usd', 0) for t in state.get("active_trades", []))
    risk_limit_pct = RISK_RULES_CONFIG["MAX_TOTAL_RISK_EXPOSURE_PERCENT"]
    risk_limit_usd = account_info['equity'] * (risk_limit_pct / 100)
    
    if current_total_risk_usd >= risk_limit_usd:
        logger.debug("Đã đạt giới hạn tổng rủi ro (%.2f/%.2f USD). Bỏ qua quét.", current_total_risk_usd, risk_limit_usd)
        return
    
    # --- BƯỚC 2: THU THẬP TẤT CẢ CƠ HỘI ---
    opportunities, now_vn, cooldown_map = [], datetime.now(VIETNAM_TZ), state.get('cooldown_until', {})
    
    for symbol in GENERAL_CONFIG["SYMBOLS_TO_SCAN"]:
        if any(t['symbol'] == symbol for t in state.get("active_trades", [])):
            continue
        cooldown_str = cooldown_map.get(symbol, {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if cooldown_str and now_vn < datetime.fromisoformat(cooldown_str):
            continue
            
        indicators = indicator_results.get(symbol, {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if not indicators:
            continue
            
        decision = get_advisor_decision(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], indicators, {"WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0}})
        raw_score = decision.get('final_score', 0.0)
        
        # === SỬA LOGIC Ở ĐÂY ===
        # BỎ QUA CÁI BỘ LỌC NGU NGỐC Ở ĐÂY. CỨ THU THẬP HẾT.
        
        market_zone, trade_type = determine_market_zone(indicators), "LONG" if raw_score > 0 else "SHORT"
        
        for tactic_name, tactic_cfg in TACTICS_LAB.items():
            if tactic_cfg["TRADE_TYPE"] != trade_type: continue
            if market_zone not in tactic_cfg.get("OPTIMAL_ZONE", []): continue
            
            mtf_coeff = get_mtf_adjustment_coefficient(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], trade_type)
            ez_coeff = 1.0
            if tactic_cfg.get("USE_EXTREME_ZONE_FILTER", False):
                ez_coeff = get_extreme_zone_adjustment_coefficient(indicators, GENERAL_CONFIG["MAIN_TIMEFRAME"])
            
            final_score = raw_score * mtf_coeff * ez_coeff
            
            if cooldown_str and abs(final_score) < GENERAL_CONFIG["OVERRIDE_COOLDOWN_SCORE"]:
                continue
                
            opportunities.append({
                "symbol": symbol, "score": final_score, "raw_score": raw_score, 
                "tactic_name": tactic_name, "tactic_cfg": tactic_cfg, 
                "indicators": indicators, "zone": market_zone, 
                "mtf_coeff": mtf_coeff, "ez_coeff": ez_coeff
            })

    # --- BƯỚC 3: SẮP XẾP VÀ ĐÁNH GIÁ CHI TIẾT ---
    if not opportunities:
        logger.info("=> Không tìm thấy bất kỳ cơ hội nào từ các cặp tiền được quét.")
        return
    
    top_n = GENERAL_CONFIG["TOP_N_OPPORTUNITIES_TO_CHECK"]
    
    # LỌC SAU KHI ĐÃ CÓ DANH SÁCH ĐẦY ĐỦ
    min_score_threshold = GENERAL_CONFIG["MIN_RAW_SCORE_THRESHOLD"]
    qualified_opps = [opp for opp in opportunities if abs(opp['raw_score']) >= min_score_threshold]

    if not qualified_opps:
        # BÁO CÁO NHỮNG THẰNG ĐIỂM CAO NHẤT BỊ LOẠI
        logger.info(f"=> Không có cơ hội nào đạt ngưỡng điểm tối thiểu ({min_score_threshold}).")
        top_rejected = sorted(opportunities, key=lambda x: abs(x['raw_score']), reverse=True)[:top_n]
        logger.info(f"---[📉 Top {len(top_rejected)} cơ hội bị loại vì điểm thấp]---")
        for i, opp in enumerate(top_rejected):
             logger.info(f"  #{i+1}: {opp['symbol']} | Tactic: {opp['tactic_name']} | Điểm gốc: {opp['raw_score']:.2f} (Không đủ)")
        return

    sorted_opps = sorted(qualified_opps, key=lambda x: abs(x['score']), reverse=True)[:top_n]
    
    logger.info(f"---[🏆 Tìm thấy {len(qualified_opps)} cơ hội đạt chuẩn. Xem xét {len(sorted_opps)} cơ hội tốt nhất (tối đa {top_n})]---")
    
    found_trade_to_open = False
    for i, opp in enumerate(sorted_opps):
        score, entry_thresh, tactic_name, symbol = opp['score'], opp['tactic_cfg']['ENTRY_SCORE'], opp['tactic_name'], opp['symbol']
        
        log_prefix = f"  #{i+1}: {symbol} | Tactic: {tactic_name}"
        log_score = f"| Gốc: {opp['raw_score']:.2f} | Final: {score:.2f} (Ngưỡng: {entry_thresh})"
        log_adjustments = f"      Chi tiết điều chỉnh: [MTF: x{opp['mtf_coeff']:.2f}] [Vùng Cực đoan: x{opp['ez_coeff']:.2f}]"
        
        logger.info(log_prefix + log_score)
        logger.info(log_adjustments)

        passes_score = (score >= entry_thresh) if score > 0 else (score <= entry_thresh)
        if not passes_score:
            logger.info("      => 📉 Không đạt ngưỡng điểm. Xem xét cơ hội tiếp theo...")
            continue
            
        passes_momentum = not opp['tactic_cfg']['USE_MOMENTUM_FILTER'] or is_momentum_confirmed(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], opp['tactic_cfg']['TRADE_TYPE'])
        if not passes_momentum:
            logger.info("      => 📉 Lọc động lượng thất bại. Xem xét cơ hội tiếp theo...")
            continue
            
        risk_dist_est = opp['indicators'].get('atr', 0) * opp['tactic_cfg'].get("ATR_SL_MULTIPLIER", 2.0)
        capital_base = state.get('initial_capital', account_info['equity'])
        adj_risk_pct = RISK_RULES_CONFIG["RISK_PER_TRADE_PERCENT"] * ZONE_BASED_POLICIES.get(opp['zone'], {}).get("CAPITAL_RISK_MULTIPLIER", 1.0)
        risk_amount_usd_est = capital_base * (adj_risk_pct / 100)
        
        passes_risk = (current_total_risk_usd + risk_amount_usd_est) <= risk_limit_usd
        if not passes_risk:
            logger.info("      => 📉 Vượt giới hạn tổng rủi ro. Xem xét cơ hội tiếp theo...")
            continue
            
        logger.info(f"      => ✅ Đạt mọi điều kiện. Tiến hành đặt lệnh...")
        execute_trade(opp)
        found_trade_to_open = True
        break
    
    if not found_trade_to_open:
        logger.info(f"  => Không có cơ hội nào trong top {len(sorted_opps)} đạt ngưỡng vào lệnh.")

def execute_trade(opportunity):
    symbol, tactic_cfg, indicators, score, tactic_name, zone = opportunity['symbol'], opportunity['tactic_cfg'], opportunity['indicators'], opportunity['score'], opportunity['tactic_name'], opportunity['zone']
    capital_base = state.get('initial_capital', connector.get_account_info()['equity'])
    order_type = mt5.ORDER_TYPE_BUY if tactic_cfg["TRADE_TYPE"] == "LONG" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return logger.error(f"Không thể lấy giá {symbol}")
    entry_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    risk_dist = indicators.get('atr', 0) * tactic_cfg.get("ATR_SL_MULTIPLIER", 2.0)
    if risk_dist <= 0: return logger.warning(f"ATR không hợp lệ cho {symbol}")
    sl_price = entry_price - risk_dist if order_type == mt5.ORDER_TYPE_BUY else entry_price + risk_dist
    tp_price = entry_price + (risk_dist * tactic_cfg.get("RR", 1.5)) if order_type == mt5.ORDER_TYPE_BUY else entry_price - (risk_dist * tactic_cfg.get("RR", 1.5))
    adjusted_risk_pct = RISK_RULES_CONFIG["RISK_PER_TRADE_PERCENT"] * ZONE_BASED_POLICIES.get(zone, {}).get("CAPITAL_RISK_MULTIPLIER", 1.0)
    risk_amount_usd = capital_base * (adjusted_risk_pct/100)
    lot_size = connector.calculate_lot_size(symbol, risk_amount_usd, sl_price)
    if lot_size is None or lot_size <= 0: return logger.warning(f"Lot size = {lot_size} không hợp lệ cho {symbol}")
    
    result = None
    retry_limit = RISK_RULES_CONFIG.get("OPEN_TRADE_RETRY_LIMIT", 3)
    for attempt in range(retry_limit):
        result = connector.place_order(symbol, order_type, lot_size, sl_price, tp_price, magic_number=GENERAL_CONFIG["MAGIC_NUMBER"])
        if result and result.retcode == mt5.TRADE_RETCODE_DONE: break
        time.sleep(RISK_RULES_CONFIG['RETRY_DELAY_SECONDS'])
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        new_trade = {
            "trade_id": str(uuid.uuid4()), "ticket_id": result.order, "symbol": symbol,
            "type": tactic_cfg["TRADE_TYPE"], "entry_price": result.price,
            "lot_size": result.volume, "initial_lot_size": result.volume,
            "sl_price": sl_price, "tp_price": tp_price, "initial_sl": sl_price,
            "risk_amount_usd": risk_amount_usd, "opened_by_tactic": tactic_name,
            "entry_time": datetime.now(VIETNAM_TZ).isoformat(),
            "entry_score": score, "last_score": score, "entry_zone": zone, "last_zone": zone,
            "peak_pnl_percent": 0.0, "dca_entries": [], "partial_pnl_details": {},
            "atr_at_entry": indicators.get('atr', 0)
        }
        state.setdefault("active_trades", []).append(new_trade)
        state['session_has_events'] = True
        event_time = datetime.now(VIETNAM_TZ).strftime('%H:%M')
        event_msg = f"[{event_time}] 🔥 Mở lệnh {tactic_cfg['TRADE_TYPE']} {symbol} | Tactic: {tactic_name}"
        state.setdefault('session_events', []).append(event_msg)
    else:
        error_msg = f"Đặt lệnh {symbol} thất bại sau {retry_limit} lần. Retcode: {result.retcode if result else 'N/A'}"
        logger.error(error_msg)
        send_discord_message(f"🚨 LỖI ĐẶT LỆNH: {error_msg}", is_error=True, force=True)

def close_trade_on_mt5(trade, reason, close_pct=1.0):
    position = next((p for p in connector.get_all_open_positions() if p.ticket == trade['ticket_id']), None)
    if not position:
        logger.warning(f"Không tìm thấy vị thế #{trade['ticket_id']} để đóng ({reason})")
        return False
    lot_to_close = round(position.volume * close_pct, 2)
    info = mt5.symbol_info(trade['symbol'])
    if info and lot_to_close < info.volume_min:
        if close_pct < 1.0:
            lot_to_close = position.volume
        else: return False
    result = None
    retry_limit = RISK_RULES_CONFIG.get("CLOSE_TRADE_RETRY_LIMIT", 3)
    for attempt in range(retry_limit):
        result = connector.close_position(position, volume_to_close=lot_to_close, comment=f"exness_{reason}")
        if result: break
        time.sleep(RISK_RULES_CONFIG['RETRY_DELAY_SECONDS'])
    if not result:
        error_msg = f"Đóng lệnh {trade['symbol']} thất bại sau {retry_limit} lần."
        logger.error(error_msg)
        send_discord_message(f"🚨 LỖI ĐÓNG LỆNH: {error_msg}", is_error=True, force=True)
        return False
    state['session_has_events'] = True
    time.sleep(2)
    deals = mt5.history_deals_get(position=trade['ticket_id'])
    closed_pnl = 0
    if deals:
        last_deal = deals[-1]
        if last_deal.entry == 1: closed_pnl = last_deal.profit

    event_time = datetime.now(VIETNAM_TZ).strftime('%H:%M')
    
    if lot_to_close >= trade['lot_size'] * 0.99:
        total_pnl_for_trade = sum(d.profit for d in deals if d.position_id == trade['ticket_id'])
        state['session_realized_pnl'] = state.get('session_realized_pnl', 0.0) + total_pnl_for_trade - sum(trade.get('partial_pnl_details', {}).values())
        trade.update({'status': f'Closed ({reason})', 'exit_price': last_deal.price if deals else 'N/A', 'exit_time': datetime.now(VIETNAM_TZ).isoformat(), 'pnl_usd': total_pnl_for_trade})
        state['active_trades'] = [t for t in state['active_trades'] if t['trade_id'] != trade['trade_id']]
        state.setdefault('trade_history', []).append(trade)
        cooldown_map = state.setdefault('cooldown_until', {}); cooldown_map.setdefault(trade['symbol'], {})[GENERAL_CONFIG["MAIN_TIMEFRAME"]] = (datetime.now(VIETNAM_TZ) + timedelta(hours=GENERAL_CONFIG["TRADE_COOLDOWN_HOURS"])).isoformat()
        export_trade_to_csv(trade)
        icon = "✅" if total_pnl_for_trade >= 0 else "❌"
        event_msg = f"[{event_time}] {icon} Đóng lệnh {trade['symbol']} ({reason}) | PnL: ${total_pnl_for_trade:,.2f}"
        state.setdefault('session_events', []).append(event_msg)
    else:
        state['session_realized_pnl'] = state.get('session_realized_pnl', 0.0) + closed_pnl
        trade['partial_pnl_details'][reason] = trade['partial_pnl_details'].get(reason, 0) + closed_pnl
        trade['lot_size'] = round(trade['lot_size'] - lot_to_close, 2)
        event_msg = f"[{event_time}] 💰 Chốt lời {close_pct*100:.0f}% lệnh {trade['symbol']} ({reason}) | PnL: ${closed_pnl:,.2f}"
        state.setdefault('session_events', []).append(event_msg)
    return True

def manage_open_positions():
    for trade in state.get("active_trades", [])[:]:
        symbol, tick = trade['symbol'], mt5.symbol_info_tick(trade['symbol'])
        if not tick: continue
        current_price = tick.bid if trade['type'] == "LONG" else tick.ask
        pnl_usd, pnl_percent = get_current_pnl(trade, current_price)
        trade['peak_pnl_percent'] = max(trade.get('peak_pnl_percent', 0.0), pnl_percent)
        if (trade['type'] == "LONG" and current_price <= trade['sl_price']) or (trade['type'] == "SHORT" and current_price >= trade['sl_price']):
            if close_trade_on_mt5(trade, "SL"): continue
        if (trade['type'] == "LONG" and current_price >= trade['tp_price']) or (trade['type'] == "SHORT" and current_price <= trade['tp_price']):
            if close_trade_on_mt5(trade, "TP"): continue
        tactic_cfg, last_score, entry_score = TACTICS_LAB.get(trade.get('opened_by_tactic'), {}), trade.get('last_score', 0), trade.get('entry_score', 0)
        threshold = ACTIVE_TRADE_MANAGEMENT_CONFIG['EARLY_CLOSE_ABS_THRESHOLD_L'] if trade['type'] == "LONG" else ACTIVE_TRADE_MANAGEMENT_CONFIG['EARLY_CLOSE_ABS_THRESHOLD_S']
        if (trade['type'] == "LONG" and last_score < threshold) or (trade['type'] == "SHORT" and last_score > threshold):
            if close_trade_on_mt5(trade, f"EC_Abs_{last_score:.1f}"): continue
        if abs(last_score) < abs(entry_score) * (1 - ACTIVE_TRADE_MANAGEMENT_CONFIG['EARLY_CLOSE_REL_DROP_PCT']) and not trade.get('partial_closed_by_score'):
            if close_trade_on_mt5(trade, f"EC_Rel_{last_score:.1f}", ACTIVE_TRADE_MANAGEMENT_CONFIG["PARTIAL_EARLY_CLOSE_PCT"]):
                trade['partial_closed_by_score'] = True
        initial_risk_dist = abs(trade['entry_price'] - trade['initial_sl'])
        if initial_risk_dist > 0:
            pnl_ratio = (current_price - trade['entry_price']) / initial_risk_dist if trade['type'] == 'LONG' else (trade['entry_price'] - current_price) / initial_risk_dist
            if tactic_cfg.get("USE_TRAILING_SL", False) and pnl_ratio >= tactic_cfg.get("TRAIL_ACTIVATION_RR", 1.2):
                smart_tsl_cfg = ACTIVE_TRADE_MANAGEMENT_CONFIG.get("SMART_TSL", {})
                volatility_check = True
                if smart_tsl_cfg.get("ENABLED"):
                    current_indicators = indicator_results.get(symbol, {}).get(GENERAL_CONFIG['MAIN_TIMEFRAME'])
                    if current_indicators:
                        current_atr = current_indicators.get('atr', trade.get('atr_at_entry', float('inf')))
                        atr_at_entry = trade.get('atr_at_entry', 0)
                        if atr_at_entry > 0:
                            volatility_check = current_atr < (atr_at_entry * smart_tsl_cfg.get("ATR_REDUCTION_FACTOR", 0.8))
                if volatility_check:
                    trail_dist = initial_risk_dist * tactic_cfg.get("TRAIL_DISTANCE_RR", 0.8)
                    new_sl = current_price - trail_dist if trade['type'] == 'LONG' else current_price + trail_dist
                    is_better = (new_sl > trade['sl_price']) if trade['type'] == 'LONG' else (new_sl < trade['sl_price'])
                    if is_better and abs(new_sl - trade['sl_price']) > (initial_risk_dist * 0.1):
                        if connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price']):
                            trade['sl_price'] = new_sl
                            logger.info(f"TSL {symbol}: SL được cập nhật lên {format_price(new_sl)}")
            if tactic_cfg.get("ENABLE_PARTIAL_TP", False) and not trade.get("tp1_hit", False) and pnl_ratio >= tactic_cfg.get("TP1_RR_RATIO", 0.6):
                if close_trade_on_mt5(trade, "TP1", tactic_cfg.get("TP1_PROFIT_PCT", 0.5)):
                    trade['tp1_hit'] = True
                    new_sl = trade['entry_price']
                    if connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price']):
                        trade['sl_price'] = new_sl
                        logger.info(f"TP1 {symbol}: Dời SL về entry {format_price(new_sl)}")
        pp_cfg = ACTIVE_TRADE_MANAGEMENT_CONFIG["PROFIT_PROTECTION"]
        if pp_cfg["ENABLED"] and not trade.get('profit_taken', False) and trade['peak_pnl_percent'] >= pp_cfg["MIN_PEAK_PNL_TRIGGER"]:
            if (trade['peak_pnl_percent'] - pnl_percent) >= pp_cfg["PNL_DROP_TRIGGER_PCT"]:
                if close_trade_on_mt5(trade, "PP", pp_cfg["PARTIAL_CLOSE_PCT"]):
                    trade['profit_taken'] = True
                    new_sl = trade['entry_price']
                    if connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price']):
                        trade['sl_price'] = new_sl
                        logger.info(f"PP {symbol}: Dời SL về entry {format_price(new_sl)}")

def handle_stale_trades():
    now_vn = datetime.now(VIETNAM_TZ)
    for trade in state.get("active_trades", [])[:]:
        rules = RISK_RULES_CONFIG["STALE_TRADE_RULES"].get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if not rules: continue
        holding_hours = (now_vn - datetime.fromisoformat(trade['entry_time'])).total_seconds() / 3600
        if holding_hours > rules["HOURS"]:
            tick = mt5.symbol_info_tick(trade['symbol'])
            if tick:
                current_price = tick.bid if trade['type'] == "LONG" else tick.ask
                _, pnl_pct = get_current_pnl(trade, current_price)
                score_thresh = rules["STAY_OF_EXECUTION_SCORE_L"] if trade['type'] == 'LONG' else rules["STAY_OF_EXECUTION_SCORE_S"]
                passes_score = (trade['last_score'] >= score_thresh) if trade['type'] == 'LONG' else (trade['last_score'] <= score_thresh)
                if pnl_pct < rules["PROGRESS_THRESHOLD_PCT"] and not passes_score:
                    close_trade_on_mt5(trade, "Stale")

def handle_dca_opportunities():
    if not DCA_CONFIG["ENABLED"]: return
    now = datetime.now(VIETNAM_TZ)
    for trade in state.get("active_trades", [])[:]:
        if len(trade.get("dca_entries", [])) >= DCA_CONFIG["MAX_DCA_ENTRIES"]: continue
        if trade.get('last_dca_time') and (now - datetime.fromisoformat(trade.get('last_dca_time'))).total_seconds() / 3600 < DCA_CONFIG['DCA_COOLDOWN_HOURS']: continue
        tick = mt5.symbol_info_tick(trade['symbol'])
        if not tick: continue
        current_price = tick.bid if trade['type'] == "LONG" else tick.ask
        last_entry_price = trade['dca_entries'][-1]['price'] if trade.get('dca_entries') else trade['entry_price']
        price_drop_pct = ((current_price - last_entry_price) / last_entry_price) * 100
        dca_trigger = DCA_CONFIG.get("TRIGGER_DROP_PCT_BY_TIMEFRAME", {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"], -3.0)
        is_triggered = (trade['type'] == 'LONG' and price_drop_pct <= dca_trigger) or (trade['type'] == 'SHORT' and price_drop_pct >= abs(dca_trigger))
        if not is_triggered: continue
        score_threshold = DCA_CONFIG["SCORE_MIN_THRESHOLD_LONG"] if trade['type'] == "LONG" else DCA_CONFIG["SCORE_MIN_THRESHOLD_SHORT"]
        if (trade['type'] == "LONG" and trade['last_score'] < score_threshold) or (trade['type'] == "SHORT" and trade['last_score'] > score_threshold): continue
        strategy = DCA_CONFIG.get("STRATEGY", "aggressive")
        multiplier = DCA_CONFIG.get("MULTIPLIERS", {}).get(strategy, 1.0)
        initial_lot_size = trade.get('initial_lot_size', trade['lot_size'])
        dca_lot_size = initial_lot_size * multiplier
        order_type = mt5.ORDER_TYPE_BUY if trade['type'] == "LONG" else mt5.ORDER_TYPE_SELL
        result = None
        retry_limit = RISK_RULES_CONFIG.get("OPEN_TRADE_RETRY_LIMIT", 3)
        for attempt in range(retry_limit):
            result = connector.place_order(trade['symbol'], order_type, dca_lot_size, 0, 0, magic_number=GENERAL_CONFIG["MAGIC_NUMBER"])
            if result and result.retcode == mt5.TRADE_RETCODE_DONE: break
            time.sleep(RISK_RULES_CONFIG['RETRY_DELAY_SECONDS'])
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            state['session_has_events'] = True
            trade['dca_entries'].append({"price": result.price, "lot_size": result.volume, "timestamp": now.isoformat()})
            total_value_before = trade['entry_price'] * trade['lot_size']
            dca_value, new_total_lots = result.price * result.volume, trade['lot_size'] + result.volume
            new_avg_price = (total_value_before + dca_value) / new_total_lots if new_total_lots > 0 else trade['entry_price']
            trade.update({'entry_price': new_avg_price, 'lot_size': new_total_lots, 'last_dca_time': now.isoformat()})
            event_time = datetime.now(VIETNAM_TZ).strftime('%H:%M')
            event_msg = f"[{event_time}] 🎯 DCA ({strategy}) {trade['symbol']} | Lot: {dca_lot_size} @ {format_price(result.price)}"
            state.setdefault('session_events', []).append(event_msg)
        else: logger.error(f"DCA cho {trade['symbol']} thất bại sau {retry_limit} lần thử.")

def reconcile_positions():
    logger.debug("Đối soát vị thế...")
    bot_tickets = {t['ticket_id'] for t in state.get("active_trades", [])}
    all_mt5_positions = connector.get_all_open_positions()
    mt5_tickets = {p.ticket for p in all_mt5_positions}
    closed_manually = bot_tickets - mt5_tickets
    if closed_manually:
        state['session_has_events'] = True
        for ticket in closed_manually: logger.warning(f"Vị thế #{ticket} do bot quản lý đã bị đóng thủ công hoặc bởi SL/TP của sàn.")
        closed_trades = [t for t in state["active_trades"] if t['ticket_id'] in closed_manually]
        for t in closed_trades: t.update({'status': 'Closed (Manual/Reconciled)', 'exit_time': datetime.now(VIETNAM_TZ).isoformat()})
        state.setdefault("trade_history", []).append(t)
        state["active_trades"] = [t for t in state["active_trades"] if t['ticket_id'] not in closed_manually]
    now = datetime.now(VIETNAM_TZ)
    orphan_alerts = state.setdefault('orphan_position_alerts', {})
    for pos in all_mt5_positions:
        if pos.magic != GENERAL_CONFIG["MAGIC_NUMBER"]:
            last_alert_str = orphan_alerts.get(str(pos.ticket))
            should_alert = True
            if last_alert_str:
                last_alert_dt = datetime.fromisoformat(last_alert_str)
                if (now - last_alert_dt).total_seconds() / 60 < DYNAMIC_ALERT_CONFIG["ALERT_COOLDOWN_MINUTES"]:
                    should_alert = False
            if should_alert:
                msg = (f"⚠️ CẢNH BÁO: Phát hiện vị thế lạ/mồ côi trên tài khoản.\n"
                       f"    - Ticket: `{pos.ticket}` | Symbol: `{pos.symbol}`\n"
                       f"    - Type: `{'BUY' if pos.type == 0 else 'SELL'}` | Lot: `{pos.volume}`\n"
                       f"    - Magic: `{pos.magic}` (khác với magic của bot: {GENERAL_CONFIG['MAGIC_NUMBER']})")
                logger.warning(f"Phát hiện vị thế lạ: Ticket #{pos.ticket} ({pos.symbol})")
                send_discord_message(msg, force=True, is_error=True)
                orphan_alerts[str(pos.ticket)] = now.isoformat()

def build_daily_summary():
    account_info = connector.get_account_info()
    if not account_info: return ""
    equity, balance = account_info['equity'], account_info['balance']
    initial_capital = state.get('initial_capital', balance)
    if initial_capital <= 0: initial_capital = balance
    pnl_total_usd = equity - initial_capital
    pnl_total_percent = (pnl_total_usd / initial_capital) * 100 if initial_capital > 0 else 0
    trade_history = state.get('trade_history', [])
    total_pnl_closed, win_rate_str, avg_win_str, avg_loss_str, pf_str = 0.0, "N/A", "$0.00", "$0.00", "N/A"
    pnl_by_tactic_report = []
    if trade_history:
        closed_trades_df = pd.DataFrame([t for t in trade_history if 'Closed' in t.get('status', '') and pd.notna(t.get('pnl_usd'))])
        if not closed_trades_df.empty:
            total_trades = len(closed_trades_df)
            winning_trades_df = closed_trades_df[closed_trades_df['pnl_usd'] > 0]
            num_wins = len(winning_trades_df)
            win_rate_str = f"{num_wins / total_trades * 100:.2f}% ({num_wins}/{total_trades})" if total_trades > 0 else "N/A"
            total_pnl_closed = closed_trades_df['pnl_usd'].sum()
            if num_wins > 0: avg_win_str = f"${winning_trades_df['pnl_usd'].mean():,.2f}"
            losing_trades_df = closed_trades_df[closed_trades_df['pnl_usd'] <= 0]
            if not losing_trades_df.empty: avg_loss_str = f"${losing_trades_df['pnl_usd'].mean():,.2f}"
            total_profit = winning_trades_df['pnl_usd'].sum()
            total_loss = abs(losing_trades_df['pnl_usd'].sum())
            pf_str = f"{total_profit / total_loss:.2f}" if total_loss > 0 else "∞"
            if 'opened_by_tactic' in closed_trades_df.columns:
                pnl_by_tactic = closed_trades_df.groupby('opened_by_tactic')['pnl_usd'].agg(['sum', 'count'])
                pnl_by_tactic_report.append("\n--- **Hiệu suất theo Tactic** ---")
                for tactic, data in pnl_by_tactic.iterrows():
                    pnl_by_tactic_report.append(f"  - `{tactic}`: **${data['sum']:+,.2f}** ({int(data['count'])} lệnh)")
    pnl_summary_line = f"🏆 Win Rate: **{win_rate_str}** | 📈 PF: **{pf_str}** | ✅ PnL Đóng: **${total_pnl_closed:,.2f}**\n"
    pnl_summary_line += f"🎯 AVG Lãi: **{avg_win_str}** | 🛡️ AVG Lỗ: **{avg_loss_str}**"
    report = [
        f"📊 **BÁO CÁO TỔNG KẾT EXNESS BOT** - {datetime.now(VIETNAM_TZ).strftime('%H:%M %d-%m-%Y')}",
        f"💰 Vốn Nền tảng: **${initial_capital:,.2f}** | 💵 Balance: **${balance:,.2f}**",
        f"📊 Equity: **${equity:,.2f}** | 📈 PnL Tổng: **${pnl_total_usd:+,.2f} ({pnl_total_percent:+.2f}%)**",
        "\n" + pnl_summary_line, ""
    ]
    active_trades = state.get('active_trades', [])
    if active_trades:
        report.append(f"--- **Vị thế đang mở ({len(active_trades)})** ---")
        for trade in active_trades:
            tick = mt5.symbol_info_tick(trade['symbol'])
            if tick:
                current_price = tick.bid if trade['type'] == "LONG" else tick.ask
                pnl_usd, _ = get_current_pnl(trade, current_price)
                icon = "🟢" if pnl_usd >= 0 else "🔴"
                holding_hours = (datetime.now(VIETNAM_TZ) - datetime.fromisoformat(trade['entry_time'])).total_seconds() / 3600
                report.append(f"  {icon} **{trade['symbol']}** ({trade['type']}) | PnL: **${pnl_usd:+.2f}** | Giữ: {holding_hours:.1f}h")
    else: report.append("Không có vị thế nào đang mở")
    if pnl_by_tactic_report: report.extend(pnl_by_tactic_report)
    return '\n'.join(report)

def main_loop():
    global state
    last_reconciliation_time = 0
    last_heavy_task_minute = -1
    while True:
        try:
            now_ts = time.time()
            now_vn = datetime.now(VIETNAM_TZ)
            
            # --- TÁC VỤ NHẸ - CHẠY MỖI VÒNG LẶP ---
            manage_open_positions()
            handle_stale_trades()
            handle_dca_opportunities()

            # --- KIỂM TRA BÁO CÁO ---
            account_info_for_report = connector.get_account_info()
            if account_info_for_report:
                current_equity = account_info_for_report['equity']
                report_type_to_send = should_send_report(state, current_equity)
                if report_type_to_send:
                    if report_type_to_send == "daily":
                        summary = build_daily_summary()
                        send_discord_message(summary, force=True)
                        state['last_summary_sent_time'] = now_vn.isoformat()
                    else:
                        alert_text = build_dynamic_alert_text(state, current_equity)
                        send_discord_message(alert_text, force=True)
                        state['last_dynamic_alert'] = {"timestamp": now_vn.isoformat()}
                        state['last_reported_pnl_percent'] = ((current_equity - state.get('initial_capital', 1)) / state.get('initial_capital', 1)) * 100
                        state['session_has_events'] = False
                        state['session_events'] = []

            # --- TÁC VỤ NẶNG - CHẠY THEO CHU KỲ ---
            interval_minutes = GENERAL_CONFIG["HEAVY_TASK_INTERVAL_MINUTES"]
            current_minute = now_vn.minute
            
            if (current_minute % interval_minutes == 0) and (current_minute != last_heavy_task_minute):
                last_heavy_task_minute = current_minute # ĐÁNH DẤU NGAY LẬP TỨC ĐỂ TRÁNH LẶP
                
                logger.info(f"--- [Chu kỳ {interval_minutes}m] Bắt đầu quét và phân tích... ---")
                manage_dynamic_capital()
                load_all_indicators()
                update_scores_for_active_trades()
                find_and_open_new_trades()
                save_state()
            
            # --- ĐỐI SOÁT - CHẠY THEO CHU KỲ RIÊNG ---
            if now_ts - last_reconciliation_time > GENERAL_CONFIG["RECONCILIATION_INTERVAL_MINUTES"] * 60:
                reconcile_positions()
                last_reconciliation_time = now_ts
                
            time.sleep(GENERAL_CONFIG["LOOP_SLEEP_SECONDS"])
        except KeyboardInterrupt:
            logger.info("Phát hiện KeyboardInterrupt. Đang dừng bot...")
            raise
        except Exception as e:
            # Ghi log lỗi vào file ở mức ERROR để luôn có dấu vết, dù có gửi thông báo hay không
            logger.error(f"Lỗi nghiêm trọng trong vòng lặp chính: {e}\n```{traceback.format_exc()}```")

            # Logic kiểm tra cooldown trước khi gửi thông báo
            now_dt = datetime.now(VIETNAM_TZ)
            last_alert_str = state.get('last_critical_error_alert_time')
            should_send_alert = True

            if last_alert_str:
                last_alert_dt = datetime.fromisoformat(last_alert_str)
                minutes_since = (now_dt - last_alert_dt).total_seconds() / 60
                cooldown_period = GENERAL_CONFIG.get("CRITICAL_ERROR_COOLDOWN_MINUTES", 60)
                
                if minutes_since < cooldown_period:
                    should_send_alert = False
                    logger.info(f"Lỗi lặp lại trong thời gian cooldown. Tạm thời không gửi thông báo Discord.")

            if should_send_alert:
                error_message = f"Lỗi nghiêm trọng trong vòng lặp chính: {e}\n```{traceback.format_exc()}```"
                # Ghi log ở mức CRITICAL chỉ khi gửi thông báo
                logger.critical(f"Gửi thông báo lỗi nghiêm trọng đến Discord: {e}")
                send_discord_message(f"🚨 LỖI NGHIÊM TRỌNG: {error_message}", is_error=True, force=True)
                
                # Cập nhật lại thời gian gửi thông báo lỗi cuối cùng
                state['last_critical_error_alert_time'] = now_dt.isoformat()
                save_state()

            # Luôn tạm dừng để tránh làm quá tải CPU khi lỗi lặp lại liên tục
            time.sleep(60)

def run_bot():
    global connector, state
    setup_logging()
    logger.info("=== KHỞI ĐỘNG EXNESS BOT V2.3 (THE SILENT OPERATOR) ===")
    connector = ExnessConnector()
    if not connector.connect():
        logger.critical("Không thể kết nối MT5!")
        return
    if not acquire_lock():
        logger.info("Bot đang chạy ở phiên khác. Thoát.")
        return
    try:
        load_state()
        for key in SESSION_TEMP_KEYS:
            if key == 'session_events':
                state[key] = []
            else:
                state[key] = state.get(key, 0.0 if 'pnl' in key else ({} if 'alerts' in key else False))

        account_info = connector.get_account_info()
        if not account_info: raise ConnectionError("Không thể lấy thông tin tài khoản khi khởi động.")
        if state.get('initial_capital', 0) <= 0:
            state['initial_capital'] = account_info['equity']
            state['balance_end_of_last_session'] = account_info['balance']
            save_state()
        logger.info(f"✅ Đã kết nối MT5 thành công. Tài khoản #{account_info['login']} | Vốn nền tảng: ${state.get('initial_capital', 0):,.2f}")
        main_loop()
    except KeyboardInterrupt:
        logger.info("Đã dừng bot theo yêu cầu người dùng.")
    except Exception as e:
        logger.critical(f"Lỗi không thể phục hồi: {e}", exc_info=True)
    finally:
        if connector and connector._is_connected:
            final_account_info = connector.get_account_info()
            if final_account_info:
                state['balance_end_of_last_session'] = final_account_info['balance']
                state['realized_pnl_last_session'] = state.get('session_realized_pnl', 0.0)
        save_state()
        release_lock()
        if connector: connector.shutdown()
        logger.info("=== BOT ĐÃ DỪNG ===")

if __name__ == "__main__":
    run_bot()