# -*- coding: utf-8 -*-
# main_exness_bot.py
# Version: 2.7.0 - The Apex Strategist
# Date: 2025-08-26
"""
CHANGELOG (v2.7.0):
- FEATURE (EMA Smoothing): Tích hợp cơ chế làm mượt điểm số bằng Exponential Moving Average (EMA).
    - EMA được đặt làm phương pháp mặc định, mang lại sự cân bằng tối ưu giữa tốc độ phản ứng và khả năng lọc nhiễu cho khung thời gian ngắn.
    - Cấu hình linh hoạt, cho phép dễ dàng chuyển đổi giữa các phương pháp: EMA, MA, Rate Limiting hoặc tắt hoàn toàn.
- REFACTOR (Core Logic): Tái cấu trúc và hoàn thiện các logic cốt lõi.
    - Hoàn thiện hàm `get_extreme_zone_adjustment_coefficient` với logic đối xứng, chính xác.
    - Loại bỏ hoàn toàn bộ lọc HTF cứng nhắc, trao toàn quyền quyết định cho hệ thống tính điểm thông minh.
- ENHANCEMENT (Logging): Nâng cấp hệ thống ghi log.
    - Log phân tích cơ hội giờ đây hiển thị chi tiết lý do và các tín hiệu đóng góp vào điểm số, giúp việc theo dõi và tối ưu hóa trở nên minh bạch hơn.
- OPTIMIZATION (Code Structure): Tối ưu hóa cấu trúc mã nguồn để dễ đọc, dễ bảo trì và mở rộng trong tương lai.
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
from collections import deque

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

# ==================================================================================================
# ==================================================================================================
# ================ 🎯 TRUNG TÂM CẤU HÌNH - PHIÊN BẢN "BALANCED INTRADAY" (ĐÃ SỬA LỖI) 🎯 =================
# ==================================================================================================
# ==================================================================================================

# ĐỊNH NGHĨA CÁC VÙNG THỊ TRƯỜNG (FIX LỖI NAMEERROR)
# Dòng này phải được đặt ở đây, trước khi các biến này được sử dụng trong các từ điển bên dưới.
LEADING_ZONE, COINCIDENT_ZONE, LAGGING_ZONE, NOISE_ZONE = "LEADING", "COINCIDENT", "LAGGING", "NOISE"

# ==================================================================================================
# I. CẤU HÌNH CỐT LÕI & VẬN HÀNH (Core & Operational Config)
# --------------------------------------------------------------------------------------------------
# Các thiết lập cơ bản về cách bot hoạt động, quét thị trường và các phiên giao dịch.
# ==================================================================================================

GENERAL_CONFIG = {
    "SYMBOLS_TO_SCAN": [s.strip() for s in os.getenv("SYMBOLS_TO_SCAN", "BTCUSD,ETHUSD").split(',')], # Các cặp tiền bot sẽ theo dõi.
    "MAIN_TIMEFRAME": "5m",                                    # Khung thời gian chính để phân tích và vào lệnh.
    "MTF_TIMEFRAMES": ["5m", "15m", "1h"],                     # Các khung thời gian phụ để xác nhận xu hướng (Multi-Timeframe Analysis).
    "LOOP_SLEEP_SECONDS": 2,                                  # Thời gian (giây) bot nghỉ giữa mỗi vòng lặp kiểm tra.
    "HEAVY_TASK_INTERVAL_MINUTES": 5,                         # Tần suất (phút) thực hiện các tác vụ nặng như quét tín hiệu mới.
    "RECONCILIATION_INTERVAL_MINUTES": 15,                    # Tần suất (phút) đối soát lệnh giữa bot và sàn MT5.
    "CANDLE_FETCH_COUNT": 300,                                # Số lượng nến tải về cho mỗi lần phân tích.
    "TOP_N_OPPORTUNITIES_TO_CHECK": 2,                        # Chỉ xem xét N cơ hội tốt nhất tại một thời điểm để vào lệnh.
    "TRADE_COOLDOWN_HOURS": 2.0,                              # [An toàn] Thời gian (giờ) chờ trước khi mở lệnh mới trên cùng 1 cặp tiền.
    "OVERRIDE_COOLDOWN_SCORE": 7.5,                           # Điểm số tín hiệu đủ mạnh để bỏ qua thời gian chờ (cooldown).
    "MAGIC_NUMBER": 202508,                                   # Mã định danh riêng để bot nhận diện các lệnh của mình.
    "DAILY_SUMMARY_TIMES": ["08:10", "20:10"],                # Các thời điểm trong ngày để gửi báo cáo tổng kết.
    "MIN_RAW_SCORE_THRESHOLD": 1.0,                           # Ngưỡng điểm thô tối thiểu để một cơ hội được xem xét.
    "CRITICAL_ERROR_COOLDOWN_MINUTES": 60,                    # Thời gian (phút) chờ trước khi gửi lại thông báo lỗi nghiêm trọng.
    "MIN_INTERVAL_SAME_SYMBOL_MINUTES": 60                    # Thời gian (phút) tối thiểu giữa 2 lệnh trên cùng 1 cặp tiền.
}

SESSION_RISK_CONFIG = {
    "ENABLED": True,                                          # True: Bật điều chỉnh rủi ro theo phiên Á/Âu/Mỹ.
    "QUIET_HOURS": {"START": 2, "END": 8, "MULTIPLIER": 0.7},  # Giảm 30% rủi ro trong phiên Á (2h-8h sáng VN).
    "ACTIVE_HOURS": {"START": 14, "END": 23, "MULTIPLIER": 1.1} # Tăng 10% rủi ro trong phiên Âu/Mỹ (14h-23h VN).
}


# ==================================================================================================
# II. QUẢN LÝ VỐN & RỦI RO (Capital & Risk Management)
# --------------------------------------------------------------------------------------------------
# Các quy tắc sắt về quản lý vốn, giới hạn thua lỗ và phân bổ rủi ro.
# ==================================================================================================

RISK_RULES_CONFIG = {
    "RISK_PER_TRADE_PERCENT": 1.0,                            # % vốn chấp nhận rủi ro cho mỗi giao dịch.
    "MAX_ACTIVE_TRADES": 3,                                   # [An toàn] Số lượng lệnh được phép mở đồng thời.
    "MAX_TOTAL_RISK_EXPOSURE_PERCENT": 5.0,                   # [An toàn] Tổng % rủi ro tối đa trên toàn bộ tài khoản.
    "OPEN_TRADE_RETRY_LIMIT": 3,                              # Số lần thử lại nếu đặt lệnh thất bại.
    "CLOSE_TRADE_RETRY_LIMIT": 3,                             # Số lần thử lại nếu đóng lệnh thất bại.
    "RETRY_DELAY_SECONDS": 5,                                 # Thời gian chờ giữa các lần thử lại.
    "DAILY_LOSS_LIMIT_PERCENT": -3.0,                         # Ngưỡng lỗ tối đa trong ngày (% vốn), chạm ngưỡng này bot sẽ ngừng giao dịch.
    "MAX_TRADES_PER_DIRECTION": 2,                            # Số lệnh Long/Short tối đa được mở cùng lúc.
    "STALE_TRADE_RULES": {
        "5m": {"HOURS": 8, "PROGRESS_THRESHOLD_PCT": 1.0},    # Đóng lệnh "ì" (không có lợi nhuận) sau 8 giờ.
        "STAY_OF_EXECUTION_SCORE_L": 6.0,                     # Giữ lệnh "ì" nếu điểm số vẫn tốt (>= 6.0 cho lệnh Long).
        "STAY_OF_EXECUTION_SCORE_S": -6.0                     # Giữ lệnh "ì" nếu điểm số vẫn tốt (<= -6.0 cho lệnh Short).
    }
}

ZONE_BASED_POLICIES = {
    LEADING_ZONE: {"CAPITAL_RISK_MULTIPLIER": 0.9},            # Rủi ro 0.9x khi có tín hiệu sớm (leading).
    COINCIDENT_ZONE: {"CAPITAL_RISK_MULTIPLIER": 1.25},        # Rủi ro 1.25x khi tín hiệu đồng thuận (breakout).
    LAGGING_ZONE: {"CAPITAL_RISK_MULTIPLIER": 1.0},            # Rủi ro 1.0x khi xu hướng đã rõ ràng (lagging).
    NOISE_ZONE: {"CAPITAL_RISK_MULTIPLIER": 0.4}               # Rủi ro 0.4x khi thị trường nhiễu, không rõ xu hướng.
}

CAPITAL_MANAGEMENT_CONFIG = {
    "ENABLED": True,                                          # True: Bật tự động điều chỉnh vốn nền tảng.
    "AUTO_COMPOUND_THRESHOLD_PCT": 10.0,                      # Tự động gộp lãi vào vốn khi tài khoản tăng trưởng 10%.
    "AUTO_DELEVERAGE_THRESHOLD_PCT": -10.0,                   # Tự động giảm vốn tính toán khi tài khoản sụt giảm 10%.
    "CAPITAL_ADJUSTMENT_COOLDOWN_HOURS": 48,                  # Thời gian chờ giữa các lần điều chỉnh vốn.
    "DEPOSIT_DETECTION_MIN_USD": 20.0,                        # Ngưỡng USD tối thiểu để phát hiện nạp/rút.
    "DEPOSIT_DETECTION_THRESHOLD_PCT": 0.02,                  # Ngưỡng % tối thiểu để phát hiện nạp/rút.
}


# ==================================================================================================
# III. PHÂN TÍCH TÍN HIỆU & ĐIỂM SỐ (Signal Analysis & Scoring)
# --------------------------------------------------------------------------------------------------
# Cách bot tổng hợp, lọc và đánh giá các tín hiệu kỹ thuật.
# ==================================================================================================

SCORE_SMOOTHING_CONFIG = {
    "METHOD": "EXPONENTIAL_MA",                               # Phương pháp làm mượt điểm: EMA (tốt nhất cho 5m).
    "EMA_SMOOTHING_CONFIG": { "SPAN": 5 }                     # Độ nhạy của EMA, số nhỏ = nhạy hơn, số lớn = mượt hơn.
}

MTF_ANALYSIS_CONFIG = {
    "ENABLED": True,                                          # True: Bật phân tích đa khung thời gian.
    "BONUS_COEFFICIENT": 1.10,                                # Thưởng 10% điểm nếu các khung lớn đồng thuận.
    "PENALTY_COEFFICIENT": 0.96,                              # Phạt 4% điểm nếu 1 khung lớn ngược xu hướng.
    "SEVERE_PENALTY_COEFFICIENT": 0.93,                       # Phạt 7% điểm nếu tất cả khung lớn đều ngược xu hướng.
    "SIDEWAYS_PENALTY_COEFFICIENT": 0.97,                     # Phạt 3% điểm nếu khung lớn đi ngang.
}

EXTREME_ZONE_ADJUSTMENT_CONFIG = {
    "ENABLED": True,                                          # True: Bật nhận diện cơ hội đảo chiều (bắt đáy/đỉnh).
    "MAX_BONUS_COEFF": 1.15,                                  # Mức thưởng điểm tối đa cho tín hiệu đảo chiều.
    "SCORING_WEIGHTS": { "RSI": 0.4, "BB_POS": 0.4, "CANDLE": 0.35, "SR_LEVEL": 0.35 }, # Trọng số của các yếu tố.
    "BASE_IMPACT": { "BONUS_PER_POINT": 0.10 },               # Mức thưởng cho mỗi điểm "cơ hội" được tính.
    "CONFLUENCE_MULTIPLIER": 1.4,                             # Nhân hệ số khi nhiều yếu tố đảo chiều cùng xuất hiện.
    "RULES_BY_TIMEFRAME": {
        "5m": {"OVERBOUGHT": {"RSI_ABOVE": 70, "BB_POS_ABOVE": 0.93}, "OVERSOLD": {"RSI_BELOW": 30, "BB_POS_BELOW": 0.07}},
        "15m": {"OVERBOUGHT": {"RSI_ABOVE": 70, "BB_POS_ABOVE": 0.93}, "OVERSOLD": {"RSI_BELOW": 30, "BB_POS_BELOW": 0.07}},
        "1h": {"OVERBOUGHT": {"RSI_ABOVE": 70, "BB_POS_ABOVE": 0.92}, "OVERSOLD": {"RSI_BELOW": 30, "BB_POS_BELOW": 0.08}}
    },
    "CONFIRMATION_BOOST": {                                   # Các yếu tố xác nhận tín hiệu đảo chiều.
        "ENABLED": True,
        "BEARISH_CANDLES": ["shooting_star", "bearish_engulfing", "gravestone"],
        "BULLISH_CANDLES": ["hammer", "bullish_engulfing", "dragonfly"],
        "RESISTANCE_PROXIMITY_PCT": 0.007, "SUPPORT_PROXIMITY_PCT": 0.007,
    }
}

MOMENTUM_FILTER_CONFIG = {
    "ENABLED": True,                                          # True: Bật bộ lọc động lượng cuối cùng trước khi vào lệnh.
    "RULES_BY_TIMEFRAME": {                                   # Yêu cầu phải có X nến xác nhận động lượng trong Y nến gần nhất.
        "5m": {"WINDOW": 4, "REQUIRED_CANDLES": 2},
        "15m": {"WINDOW": 4, "REQUIRED_CANDLES": 2},
        "1h": {"WINDOW": 3, "REQUIRED_CANDLES": 1}
    }
}


# ==================================================================================================
# IV. QUẢN LÝ LỆNH GIAO DỊCH (Active Trade Management)
# --------------------------------------------------------------------------------------------------
# Cách bot xử lý các lệnh sau khi đã mở: gồng lời, cắt lỗ, chốt lời từng phần.
# ==================================================================================================

ACTIVE_TRADE_MANAGEMENT_CONFIG = {
    "EARLY_CLOSE_ABS_THRESHOLD_L": 1.8,                       # [Tăng kiên nhẫn] Đóng lệnh Long nếu điểm số giảm xuống dưới 1.8.
    "EARLY_CLOSE_ABS_THRESHOLD_S": -1.8,                      # [Tăng kiên nhẫn] Đóng lệnh Short nếu điểm số tăng lên trên -1.8.
    "EARLY_CLOSE_REL_DROP_PCT": 0.65,                         # [Tăng kiên nhẫn] Đóng 1 phần nếu điểm số mất 65% sức mạnh ban đầu.
    "PARTIAL_EARLY_CLOSE_PCT": 0.5,                           # Tỷ lệ đóng một phần khi tín hiệu suy yếu.
    "PROFIT_PROTECTION": {
        "ENABLED": True,                                      # True: Bật tính năng bảo vệ lợi nhuận.
        "MIN_PEAK_PNL_TRIGGER": 80.0,                         # [Tối ưu gồng lời] Kích hoạt khi lợi nhuận đạt 0.8R (80% rủi ro ban đầu).
        "PNL_DROP_TRIGGER_PCT": 50.0,                         # [Tối ưu gồng lời] Can thiệp nếu lợi nhuận sụt 50% từ đỉnh.
        "PARTIAL_CLOSE_PCT": 0.5                              # Tỷ lệ đóng một phần để bảo vệ lợi nhuận.
    },
    "SMART_TSL": { "ENABLED": True, "ATR_REDUCTION_FACTOR": 0.75 }, # Bật Trailing Stop Loss thông minh.
    "DYNAMIC_TP_ATR_TRAIL": {                                 # Bật gồng lời bằng ATR Trailing sau khi đạt TP1.
        "ENABLED": True,
        "ACTIVATED_AFTER_TP1": True,
        "ATR_MULTIPLIER": 2.5,
    }
}

DCA_CONFIG = {
    "ENABLED": False,                                         # [An toàn] TẮT chiến lược DCA (trung bình giá) vì rủi ro cao.
    "MAX_DCA_ENTRIES": 2,
    "STRATEGY": "aggressive",
    "MULTIPLIERS": { "aggressive": 0.8, "conservative": 0.6 },
    "TRIGGER_DROP_PCT_BY_TIMEFRAME": {"5m": -3.0, "15m": -4.0, "1h": -5.0},
    "SCORE_MIN_THRESHOLD_LONG": 5.5, "SCORE_MIN_THRESHOLD_SHORT": -5.5,
    "DCA_COOLDOWN_HOURS": 4,
    "REQUIRE_CONFIRMATION_CANDLE": True,
    "BULLISH_CONFIRMATION_CANDLES": ["hammer", "bullish_engulfing", "dragonfly"],
    "BEARISH_CONFIRMATION_CANDLES": ["shooting_star", "bearish_engulfing", "gravestone"],
}


# ==================================================================================================
# V. BỘ CHIẾN THUẬT GIAO DỊCH (Tactics Lab)
# --------------------------------------------------------------------------------------------------
# Tập hợp các chiến lược giao dịch mà bot có thể sử dụng.
# ==================================================================================================

TACTICS_LAB = {
    # --- CHIẾN THUẬT CHO LỆNH LONG ---
    "Balanced_Trader_L": {
        "OPTIMAL_ZONE":          [LAGGING_ZONE, COINCIDENT_ZONE], # Giao dịch trong vùng xu hướng rõ ràng.
        "TRADE_TYPE":            "LONG",                          # Chỉ vào lệnh MUA.
        "ENTRY_SCORE":           6.3,                             # Yêu cầu điểm tín hiệu tối thiểu là 6.3.
        "USE_MOMENTUM_FILTER":   True,                            # Bật bộ lọc động lượng.
        "USE_EXTREME_ZONE_FILTER": True,                          # Bật bộ lọc cơ hội đảo chiều.
        "RR":                    1.5,                             # Tỷ lệ Rủi ro/Lợi nhuận mục tiêu là 1:1.5.
        "ATR_SL_MULTIPLIER":     2.5,                             # Stop Loss đặt cách giá 2.5 lần chỉ báo ATR.
        "USE_TRAILING_SL":       True,                            # Bật Trailing Stop Loss (TSL).
        "TRAIL_ACTIVATION_RR":   1.2,                             # Kích hoạt TSL khi lợi nhuận đạt 1.2R.
        "TRAIL_DISTANCE_RR":     0.8,                             # Khoảng cách TSL so với giá là 0.8R.
        "ENABLE_PARTIAL_TP":     True,                            # Bật chốt lời một phần tại TP1.
        "TP1_RR_RATIO":          0.5,                             # Vị trí TP1 tại 0.5R.
        "TP1_PROFIT_PCT":        0.6,                             # Chốt 60% khối lượng lệnh tại TP1.
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "Breakout_Hunter_L": {
        "OPTIMAL_ZONE":          [LEADING_ZONE, COINCIDENT_ZONE], # Giao dịch khi có tín hiệu breakout sớm.
        "TRADE_TYPE":            "LONG",
        "ENTRY_SCORE":           7.0,                             # Yêu cầu điểm cao hơn cho tín hiệu breakout.
        "USE_MOMENTUM_FILTER":   True,
        "USE_EXTREME_ZONE_FILTER": False,                         # Tắt bộ lọc đảo chiều, tập trung đi theo breakout.
        "RR":                    1.7,                             # Mục tiêu RR cao hơn cho các cú breakout mạnh.
        "ATR_SL_MULTIPLIER":     2.4,                             # SL chặt hơn một chút.
        "USE_TRAILING_SL":       True,
        "TRAIL_ACTIVATION_RR":   1.3,
        "TRAIL_DISTANCE_RR":     0.9,
        "ENABLE_PARTIAL_TP":     True,
        "TP1_RR_RATIO":          0.6,
        "TP1_PROFIT_PCT":        0.5,                             # Chốt 50% tại TP1.
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "Dip_Hunter_L": {
        "OPTIMAL_ZONE":          [LEADING_ZONE, COINCIDENT_ZONE], # Chiến thuật bắt đáy điều chỉnh.
        "TRADE_TYPE":            "LONG",
        "ENTRY_SCORE":           7.0,                             # Yêu cầu tín hiệu đảo chiều mạnh.
        "USE_MOMENTUM_FILTER":   False,                           # Tắt lọc động lượng vì đang bắt đảo chiều.
        "USE_EXTREME_ZONE_FILTER": True,                          # Bật bộ lọc đảo chiều là cốt lõi.
        "RR":                    1.4,                             # RR mục tiêu thấp hơn, an toàn hơn.
        "ATR_SL_MULTIPLIER":     3.0,                             # SL rộng hơn để tránh bị quét.
        "USE_TRAILING_SL":       False,                           # Thường không dùng TSL cho chiến lược đảo chiều.
        "ENABLE_PARTIAL_TP":     True,
        "TP1_RR_RATIO":          0.5,
        "TP1_PROFIT_PCT":        0.7,                             # Chốt phần lớn ở TP1 để bảo toàn lợi nhuận.
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "Cautious_Observer_L": {
        "OPTIMAL_ZONE":          [NOISE_ZONE],                    # Giao dịch trong vùng thị trường nhiễu.
        "TRADE_TYPE":            "LONG",
        "ENTRY_SCORE":           7.8,                             # Yêu cầu điểm CỰC CAO để vào lệnh trong vùng nhiễu.
        "USE_MOMENTUM_FILTER":   True,
        "USE_EXTREME_ZONE_FILTER": True,
        "RR":                    1.3,                             # Mục tiêu RR ngắn và an toàn.
        "ATR_SL_MULTIPLIER":     1.8,                             # SL rất chặt để thoát nhanh nếu sai.
        "USE_TRAILING_SL":       True,
        "TRAIL_ACTIVATION_RR":   1.0,                             # Dời SL về hòa vốn ngay khi đạt 1R.
        "TRAIL_DISTANCE_RR":     0.6,
        "ENABLE_PARTIAL_TP":     True,
        "TP1_RR_RATIO":          0.5,
        "TP1_PROFIT_PCT":        0.7,
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "AI_Aggressor_L": {
        "OPTIMAL_ZONE":          [COINCIDENT_ZONE],
        "TRADE_TYPE":            "LONG", "ENTRY_SCORE": 6.6, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.2,
        "USE_MOMENTUM_FILTER":   True, "USE_EXTREME_ZONE_FILTER": False, "USE_TRAILING_SL": True,
        "TRAIL_ACTIVATION_RR":   1.1, "TRAIL_DISTANCE_RR": 0.7, "ENABLE_PARTIAL_TP": True,
        "TP1_RR_RATIO":          0.5, "TP1_PROFIT_PCT": 0.6, "WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },

    # --- CHIẾN THUẬT CHO LỆNH SHORT ---
    "Balanced_Seller_S": {
        "OPTIMAL_ZONE":          [LAGGING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -6.3,
        "USE_MOMENTUM_FILTER":   True, "USE_EXTREME_ZONE_FILTER": True, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.5,
        "USE_TRAILING_SL":       True, "TRAIL_ACTIVATION_RR": 1.2, "TRAIL_DISTANCE_RR": 0.8,
        "ENABLE_PARTIAL_TP":     True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.6,
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "Breakdown_Hunter_S": {
        "OPTIMAL_ZONE":          [LEADING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -7.0,
        "USE_MOMENTUM_FILTER":   True, "USE_EXTREME_ZONE_FILTER": False, "RR": 1.7, "ATR_SL_MULTIPLIER": 2.4,
        "USE_TRAILING_SL":       True, "TRAIL_ACTIVATION_RR": 1.3, "TRAIL_DISTANCE_RR": 0.9,
        "ENABLE_PARTIAL_TP":     True, "TP1_RR_RATIO": 0.6, "TP1_PROFIT_PCT": 0.5,
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "Rally_Seller_S": {
        "OPTIMAL_ZONE":          [LEADING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -7.0,
        "USE_MOMENTUM_FILTER":   False, "USE_EXTREME_ZONE_FILTER": True, "RR": 1.4, "ATR_SL_MULTIPLIER": 3.0,
        "USE_TRAILING_SL":       False, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.7,
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "Cautious_Shorter_S": {
        "OPTIMAL_ZONE":          [NOISE_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -7.8,
        "USE_MOMENTUM_FILTER":   True, "USE_EXTREME_ZONE_FILTER": True, "RR": 1.3, "ATR_SL_MULTIPLIER": 1.8,
        "USE_TRAILING_SL":       True, "TRAIL_ACTIVATION_RR": 1.0, "TRAIL_DISTANCE_RR": 0.6,
        "ENABLE_PARTIAL_TP":     True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.7,
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
    "AI_Contrarian_S": {
        "OPTIMAL_ZONE":          [COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -6.6,
        "USE_MOMENTUM_FILTER":   True, "USE_EXTREME_ZONE_FILTER": False, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.2,
        "USE_TRAILING_SL":       True, "TRAIL_ACTIVATION_RR": 1.1, "TRAIL_DISTANCE_RR": 0.7,
        "ENABLE_PARTIAL_TP":     True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.6,
        "WEIGHTS":               {'tech': 1.0, 'context': 0.0, 'ai': 0.0},
    },
}


# ==================================================================================================
# VI. CẤU HÌNH HỆ THỐNG & TIỆN ÍCH (System & Utilities)
# --------------------------------------------------------------------------------------------------
# Các thiết lập phụ trợ như thông báo, ghi log.
# ==================================================================================================

DYNAMIC_ALERT_CONFIG = {
    "ENABLED": True,                                          # True: Bật thông báo động qua Discord.
    "ALERT_COOLDOWN_MINUTES": 240,                            # Thời gian chờ (phút) giữa các thông báo tự động.
    "PNL_CHANGE_THRESHOLD_PCT": 2.5,                          # Gửi thông báo nếu PnL tổng thay đổi quá 2.5%.
    "FORCE_UPDATE_MULTIPLIER": 2.5,                           # Gửi thông báo bắt buộc sau X lần thời gian chờ.
}

DISCORD_CONFIG = {
    "WEBHOOK_URL": os.getenv("DISCORD_EXNESS_WEBHOOK"),       # Lấy link webhook từ file .env.
    "CHUNK_DELAY_SECONDS": 2                                  # Thời gian chờ giữa các tin nhắn dài.
}

LOG_FILE_MAX_BYTES = 5 * 1024 * 1024                          # Kích thước tối đa của file log (5MB).
LOG_FILE_BACKUP_COUNT = 3                                     # Số lượng file log backup được giữ lại.

# ==================================================================================================
# =============================== KẾT THÚC TRUNG TÂM CẤU HÌNH =====================================
# ==================================================================================================

connector = None
state = {}
indicator_results = {}
price_dataframes = {}
score_history = {}  # Biến này sẽ được sử dụng linh hoạt bởi các phương pháp smoothing

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
    
    formatter = logging.Formatter("[%(asctime)s] (ExnessBot) %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    file_handler.setFormatter(formatter)
    error_file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    if logger.hasHandlers(): logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(error_file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)
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
        "daily_realized_pnl": 0.0,
        "last_day_checked": ""
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
    daily_pnl = state.get('daily_realized_pnl', 0.0)
    daily_pnl_icon = "🟢" if daily_pnl >= 0 else "🔴"
    daily_pnl_str = f"| ☀️ PnL Ngày: {daily_pnl_icon} **${daily_pnl:,.2f}**"
    header = f"💰 Vốn BĐ: **${initial_capital:,.2f}** | 🦊 Equity: **${equity:,.2f}** | 📈 PnL Tổng: {pnl_icon} **${pnl_total_usd:,.2f} ({pnl_total_percent:+.2f}%)** {daily_pnl_str}"
    lines = [f"📊 **CẬP NHẬT ĐỘNG EXNESS BOT** - `{now_vn_str}`", header]
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

def apply_score_smoothing(symbol: str, new_score: float) -> float:
    """
    Áp dụng phương pháp làm mượt điểm số được chọn trong cấu hình.
    ĐÃ THÊM LOGIC CHO EMA.
    """
    method = SCORE_SMOOTHING_CONFIG.get("METHOD", "NONE")
    global score_history

    if method == "RATE_LIMITING":
        cfg = SCORE_SMOOTHING_CONFIG.get("RATE_LIMITING_CONFIG", {})
        max_change, factor = cfg.get("MAX_CHANGE", 5.0), cfg.get("FACTOR", 0.3)
        history_key = f"{symbol}_rl"
        
        if history_key not in score_history:
            score_history[history_key] = new_score
            return new_score
        
        old_score = score_history[history_key]
        score_change = new_score - old_score

        if abs(score_change) > max_change:
            logger.info(f"    (Smooth RL) Thay đổi điểm đột ngột cho {symbol}: {old_score:.2f} -> {new_score:.2f} (Δ{score_change:+.2f}). Áp dụng làm mượt...")
            smoothed_score = old_score + (score_change * factor)
        else:
            smoothed_score = new_score
        
        score_history[history_key] = smoothed_score
        return smoothed_score

    elif method == "MOVING_AVERAGE":
        cfg = SCORE_SMOOTHING_CONFIG.get("MA_SMOOTHING_CONFIG", {})
        window = cfg.get("WINDOW", 3)
        history_key = f"{symbol}_ma"
        
        if history_key not in score_history:
            score_history[history_key] = deque([new_score] * window, maxlen=window)
        else:
            score_history[history_key].append(new_score)
        
        ma_score = sum(score_history[history_key]) / len(score_history[history_key])
        return ma_score
        
    # --- LOGIC MỚI CHO EMA ---
    elif method == "EXPONENTIAL_MA":
        cfg = SCORE_SMOOTHING_CONFIG.get("EMA_SMOOTHING_CONFIG", {})
        span = cfg.get("SPAN", 5)
        history_key = f"{symbol}_ema"
        
        # Nếu chưa có lịch sử, EMA đầu tiên bằng chính điểm số mới
        if history_key not in score_history:
            score_history[history_key] = new_score
            return new_score
        
        old_ema = score_history[history_key]
        # Công thức tính EMA chuẩn
        alpha = 2 / (span + 1)
        new_ema = (new_score * alpha) + (old_ema * (1 - alpha))
        
        score_history[history_key] = new_ema
        return new_ema

    else: # "NONE" hoặc bất kỳ giá trị nào khác
        return new_score

def check_correlation_risk(active_trades, new_symbol):
    """Check correlation exposure to avoid over-concentration"""
    if not active_trades:
        return True
    
    # Define high correlation pairs
    correlation_groups = [
        ["BTCUSD", "ETHUSD"],  # Crypto correlation
        # Add more pairs as needed
    ]
    
    for group in correlation_groups:
        if new_symbol in group:
            # Count existing trades in same correlation group
            same_group_trades = sum(1 for trade in active_trades 
                                   if trade['symbol'] in group)
            if same_group_trades >= 2:  # Max 2 trades per correlation group
                logger.warning(f"Correlation risk: Already have {same_group_trades} trades in group with {new_symbol}")
                return False
    
    return True

def is_spread_acceptable(symbol, max_spread_multiplier=2.0):
    """Check if current spread is acceptable for trading"""
    try:
        symbol_info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        
        if not symbol_info or not tick:
            return False
            
        current_spread = tick.ask - tick.bid
        normal_spread = symbol_info.spread * symbol_info.point
        
        # If current spread is more than 2x normal, reject
        if current_spread > normal_spread * max_spread_multiplier:
            logger.warning(f"Spread quá rộng cho {symbol}: {current_spread:.5f} vs normal {normal_spread:.5f}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Lỗi kiểm tra spread {symbol}: {e}")
        return False

def update_scores_for_active_trades():
    active_trades = state.get("active_trades", [])
    if not active_trades: return
    for trade in active_trades:
        indicators = indicator_results.get(trade['symbol'], {}).get(GENERAL_CONFIG['MAIN_TIMEFRAME'])
        if indicators:
            tactic_cfg = TACTICS_LAB.get(trade.get('opened_by_tactic'), {})
            tactic_weights = tactic_cfg.get("WEIGHTS")
            decision = get_advisor_decision(trade['symbol'], GENERAL_CONFIG['MAIN_TIMEFRAME'], indicators, {"WEIGHTS": tactic_weights})
            
            # Áp dụng smoothing cho điểm của các lệnh đang mở
            raw_score = decision.get('raw_tech_score', 0.0)
            smoothed_raw_score = apply_score_smoothing(trade['symbol'], raw_score)
            
            # Apply MTF coefficient
            mtf_coeff = get_mtf_adjustment_coefficient(trade['symbol'], GENERAL_CONFIG['MAIN_TIMEFRAME'], trade['type'])
            
            # Apply EZT coefficient
            opportunity_coeff = 1.0
            if tactic_cfg.get("USE_EXTREME_ZONE_FILTER", False):
                opportunity_coeff = get_extreme_zone_adjustment_coefficient(indicators, GENERAL_CONFIG['MAIN_TIMEFRAME'], trade['type'])
            
            final_score = smoothed_raw_score * mtf_coeff * opportunity_coeff
            
            trade['last_score'] = final_score
            trade['last_zone'] = determine_market_zone(indicators)

def determine_market_zone(indicators):
    scores = {LEADING_ZONE: 0, COINCIDENT_ZONE: 0, LAGGING_ZONE: 0, NOISE_ZONE: 0}
    adx = indicators.get('adx', 20)
    ema_9 = indicators.get('ema_9', 0)
    ema_20 = indicators.get('ema_20', 0)
    ema_50 = indicators.get('ema_50', 0)
    bb_width = indicators.get('bb_width', 0)
    ema_diff_pct = abs((ema_9 - ema_20) / ema_20) * 100 if ema_20 > 0 else 0
    if adx < 22 and ema_diff_pct < 0.08:
        scores[NOISE_ZONE] += 2.5
    is_trending_up = ema_9 > ema_20 and ema_20 > ema_50
    is_trending_down = ema_9 < ema_20 and ema_20 < ema_50
    if is_trending_up or is_trending_down:
        scores[LAGGING_ZONE] += 2.0
        if adx > 25:
            scores[LAGGING_ZONE] += 1.5
    if indicators.get('breakout_signal', "none") != "none":
        scores[COINCIDENT_ZONE] += 3.0
    if indicators.get('macd_cross', "neutral") not in ["neutral", "no_cross"]:
        scores[COINCIDENT_ZONE] += 2.0
    if indicators.get('candle_pattern') in ["bullish_engulfing", "bearish_engulfing"]:
        scores[COINCIDENT_ZONE] += 1.5
    df = price_dataframes.get(indicators.get('symbol'), {}).get(indicators.get('interval'), pd.DataFrame())
    if not df.empty and 'bb_width' in df.columns and not df['bb_width'].isna().all():
        if bb_width < df['bb_width'].quantile(0.2):
            scores[LEADING_ZONE] += 2.5
    if not any(v > 0 for v in scores.values()):
        return NOISE_ZONE
    return max(scores, key=scores.get)

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

def get_extreme_zone_adjustment_coefficient(indicators: Dict, interval: str, trade_type: str) -> float:
    """
    Tính toán hệ số cơ hội đảo chiều.
    Logic đã được sửa lại để hoạt động đối xứng và chính xác cho cả LONG và SHORT.
    """
    cfg = EXTREME_ZONE_ADJUSTMENT_CONFIG
    if not cfg.get("ENABLED", False): return 1.0
    
    weights, rules = cfg.get("SCORING_WEIGHTS", {}), cfg.get("RULES_BY_TIMEFRAME", {}).get(interval)
    if not rules: return 1.0
    
    price, rsi = indicators.get("price", 0), indicators.get("rsi_14", 50)
    bbu, bbm, bbl = indicators.get("bb_upper", 0), indicators.get("bb_middle", 0), indicators.get("bb_lower", 0)
    if not all([price > 0, bbu > bbm, bbm > bbl]): return 1.0
    
    long_opportunity_score, short_opportunity_score = 0.0, 0.0
    confirmation_cfg = cfg.get("CONFIRMATION_BOOST", {})
    
    # --- Tính điểm cơ hội cho LONG (Khi thị trường QUÁ BÁN) ---
    oversold_rule = rules.get("OVERSOLD", {})
    bb_range = bbu - bbl
    if bb_range > 0:
        bb_pos = (price - bbl) / bb_range
        if rsi < oversold_rule.get("RSI_BELOW", 30): long_opportunity_score += weights.get("RSI", 0)
        if bb_pos < oversold_rule.get("BB_POS_BELOW", 0.07): long_opportunity_score += weights.get("BB_POS", 0)
    
    if confirmation_cfg.get("ENABLED"):
        candle, sup_level = indicators.get("candle_pattern"), indicators.get("support_level", 0)
        if candle in confirmation_cfg.get("BULLISH_CANDLES", []): long_opportunity_score += weights.get("CANDLE", 0)
        is_near_support = sup_level > 0 and abs(price - sup_level) / price < confirmation_cfg.get("SUPPORT_PROXIMITY_PCT", 0.007)
        if is_near_support: long_opportunity_score += weights.get("SR_LEVEL", 0)

    # --- Tính điểm cơ hội cho SHORT (Khi thị trường QUÁ MUA) ---
    overbought_rule = rules.get("OVERBOUGHT", {})
    if bb_range > 0:
        bb_pos = (price - bbl) / bb_range
        if rsi > overbought_rule.get("RSI_ABOVE", 70): short_opportunity_score += weights.get("RSI", 0)
        if bb_pos > overbought_rule.get("BB_POS_ABOVE", 0.93): short_opportunity_score += weights.get("BB_POS", 0)
    
    if confirmation_cfg.get("ENABLED"):
        candle, res_level = indicators.get("candle_pattern"), indicators.get("resistance_level", 0)
        if candle in confirmation_cfg.get("BEARISH_CANDLES", []): short_opportunity_score += weights.get("CANDLE", 0)
        is_near_resistance = res_level > 0 and abs(price - res_level) / price < confirmation_cfg.get("RESISTANCE_PROXIMITY_PCT", 0.007)
        if is_near_resistance: short_opportunity_score += weights.get("SR_LEVEL", 0)

    # --- Áp dụng hệ số dựa trên loại giao dịch ---
    base_impact = cfg.get("BASE_IMPACT", {})
    bonus_per_point = base_impact.get("BONUS_PER_POINT", 0.10)
    
    if trade_type == "LONG":
        # Nếu đang xét lệnh LONG, chỉ quan tâm đến điểm cơ hội LONG
        coeff_change = long_opportunity_score * bonus_per_point
    else: # SHORT
        # Nếu đang xét lệnh SHORT, chỉ quan tâm đến điểm cơ hội SHORT
        coeff_change = short_opportunity_score * bonus_per_point
        
    calculated_coeff = 1.0 + coeff_change
    return min(calculated_coeff, cfg["MAX_BONUS_COEFF"]) # Chỉ có bonus, không có penalty trực tiếp

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
        logger.info(f"💰 Thiết lập Vốn Nền tảng ban đầu: ${state['initial_capital']:,.2f}")
        save_state()
        return
    balance_prev_session, pnl_prev_session = state.get("balance_end_of_last_session", 0.0), state.get("realized_pnl_last_session", 0.0)
    if balance_prev_session > 0:
        expected_balance = balance_prev_session + pnl_prev_session
        net_deposit = current_balance - expected_balance
        threshold = max(CAPITAL_MANAGEMENT_CONFIG["DEPOSIT_DETECTION_MIN_USD"], state.get("initial_capital", 1) * CAPITAL_MANAGEMENT_CONFIG["DEPOSIT_DETECTION_THRESHOLD_PCT"])
        if abs(net_deposit) > threshold:
            reason = "Nạp tiền" if net_deposit > 0 else "Rút tiền"
            logger.info(f"💰 Phát hiện {reason} ròng: ${net_deposit:,.2f}. Cập nhật Vốn Nền tảng.")
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
    global state
    today_str = datetime.now(VIETNAM_TZ).strftime('%Y-%m-%d')
    last_day_checked = state.get('last_day_checked', '')
    if today_str != last_day_checked:
        logger.info(f"☀️  Ngày mới ({today_str}). Reset bộ đếm PnL ngày.")
        state['daily_realized_pnl'] = 0.0
        state['last_day_checked'] = today_str
    daily_loss_limit_pct = RISK_RULES_CONFIG.get("DAILY_LOSS_LIMIT_PERCENT", -100.0)
    capital_base = state.get('initial_capital', 1)
    daily_loss_limit_usd = capital_base * (daily_loss_limit_pct / 100.0)
    current_daily_pnl = state.get('daily_realized_pnl', 0.0)
    if current_daily_pnl <= daily_loss_limit_usd:
        logger.warning(f"🛑  ĐÃ CHẠM NGƯỠNG THUA LỖ NGÀY (${current_daily_pnl:,.2f} / ${daily_loss_limit_usd:,.2f}). Ngừng mở lệnh mới hôm nay.")
        return
    active_trades = state.get("active_trades", [])
    if len(active_trades) >= RISK_RULES_CONFIG["MAX_ACTIVE_TRADES"]:
        logger.debug("Đã đạt giới hạn %d lệnh mở. Bỏ qua quét.", RISK_RULES_CONFIG["MAX_ACTIVE_TRADES"])
        return
    account_info = connector.get_account_info()
    if not account_info: return
    current_total_risk_usd = sum(t.get('risk_amount_usd', 0) for t in active_trades)
    risk_limit_pct = RISK_RULES_CONFIG["MAX_TOTAL_RISK_EXPOSURE_PERCENT"]
    risk_limit_usd = account_info['equity'] * (risk_limit_pct / 100)
    if current_total_risk_usd >= risk_limit_usd:
        logger.debug("Đã đạt giới hạn tổng rủi ro (%.2f/%.2f USD). Bỏ qua quét.", current_total_risk_usd, risk_limit_usd)
        return
    max_per_direction = RISK_RULES_CONFIG.get("MAX_TRADES_PER_DIRECTION", 5)
    long_count = sum(1 for t in active_trades if t['type'] == 'LONG')
    short_count = sum(1 for t in active_trades if t['type'] == 'SHORT')
    opportunities, now_vn, cooldown_map = [], datetime.now(VIETNAM_TZ), state.get('cooldown_until', {})
    for symbol in GENERAL_CONFIG["SYMBOLS_TO_SCAN"]:
    # THAY BẰNG CẢ ĐOẠN CODE NÀY:
        trades_on_this_symbol = [t for t in active_trades if t['symbol'] == symbol]
        if trades_on_this_symbol:
            last_trade_time_iso = max(t['entry_time'] for t in trades_on_this_symbol)
            last_trade_time = datetime.fromisoformat(last_trade_time_iso)
            
            minutes_since_last_trade = (now_vn - last_trade_time).total_seconds() / 60
            
            cooldown_minutes = GENERAL_CONFIG.get("MIN_INTERVAL_SAME_SYMBOL_MINUTES", 60)
            
            if minutes_since_last_trade < cooldown_minutes:
                continue
        cooldown_str = cooldown_map.get(symbol, {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if cooldown_str and now_vn < datetime.fromisoformat(cooldown_str): continue
        indicators = indicator_results.get(symbol, {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if not indicators: continue
        
        decision = get_advisor_decision(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], indicators, {"WEIGHTS": {'tech': 1.0, 'context': 0.0, 'ai': 0.0}})
        
        # Áp dụng smoothing LÊN ĐIỂM GỐC
        raw_score = apply_score_smoothing(symbol, decision.get('raw_tech_score', 0.0))
        
        market_zone, trade_type = determine_market_zone(indicators), "LONG" if raw_score > 0 else "SHORT"
        
        for tactic_name, tactic_cfg in TACTICS_LAB.items():
            if tactic_cfg["TRADE_TYPE"] != trade_type: continue
            if market_zone not in tactic_cfg.get("OPTIMAL_ZONE", []): continue
            
            mtf_coeff = get_mtf_adjustment_coefficient(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], trade_type)
            
            opportunity_coeff = 1.0
            if tactic_cfg.get("USE_EXTREME_ZONE_FILTER", False):
                opportunity_coeff = get_extreme_zone_adjustment_coefficient(indicators, GENERAL_CONFIG["MAIN_TIMEFRAME"], trade_type)
            
            final_score = raw_score * mtf_coeff * opportunity_coeff
            
            if cooldown_str and abs(final_score) < GENERAL_CONFIG["OVERRIDE_COOLDOWN_SCORE"]: continue
            opportunities.append({
                "symbol": symbol, "score": final_score, "raw_score": raw_score,
                "tactic_name": tactic_name, "tactic_cfg": tactic_cfg,
                "indicators": indicators, "zone": market_zone,
                "mtf_coeff": mtf_coeff, "opportunity_coeff": opportunity_coeff,
                "reason": decision.get("reason", "N/A") # Thêm reason để logging
            })
    if not opportunities:
        logger.info("=> Không tìm thấy bất kỳ cơ hội nào từ các cặp tiền được quét.")
        return
    min_score_threshold = GENERAL_CONFIG["MIN_RAW_SCORE_THRESHOLD"]
    top_n = GENERAL_CONFIG["TOP_N_OPPORTUNITIES_TO_CHECK"]
    all_sorted_opps = sorted(opportunities, key=lambda x: abs(x['score']), reverse=True)
    top_opps_to_log = all_sorted_opps[:top_n]
    logger.info(f"---[🔎 Phân tích {len(top_opps_to_log)} cơ hội hàng đầu (từ tổng số {len(opportunities)})]---")
    found_trade_to_open = False
    for i, opp in enumerate(top_opps_to_log):
        # --- LOGGING NÂNG CẤP ---
        logger.info(f"  #{i+1}: {opp['symbol']} | Tactic: {opp['tactic_name']}")
        logger.info(f"      => Điểm Gốc (đã làm mượt): {opp['raw_score']:.2f} | Điểm Final: {opp['score']:.2f} (Ngưỡng: {opp['tactic_cfg']['ENTRY_SCORE']})")
        logger.info(f"      => Điều chỉnh: [MTF: x{opp['mtf_coeff']:.2f}] [Cơ hội Đảo chiều: x{opp['opportunity_coeff']:.2f}]")
        
        # Log chi tiết các lý do
        reasons = opp.get('reason', '').split(' | ')
        if reasons and reasons[0] != 'No signals detected':
            logger.info("      => Lý do chính:")
            for reason in reasons[:3]: # Chỉ log 3 lý do hàng đầu cho gọn
                logger.info(f"          - {reason}")
                
        if abs(opp['raw_score']) < min_score_threshold:
            logger.info(f"      => ❌ Không đạt ngưỡng điểm tối thiểu ({min_score_threshold}). Bỏ qua.")
            continue
        trade_type = opp['tactic_cfg']['TRADE_TYPE']
        if trade_type == "LONG" and long_count >= max_per_direction:
            logger.info(f"      => ❌ Đã đạt giới hạn {max_per_direction} lệnh LONG. Bỏ qua.")
            continue
        if trade_type == "SHORT" and short_count >= max_per_direction:
            logger.info(f"      => ❌ Đã đạt giới hạn {max_per_direction} lệnh SHORT. Bỏ qua.")
            continue
        passes_score = (opp['score'] >= opp['tactic_cfg']['ENTRY_SCORE']) if opp['score'] > 0 else (opp['score'] <= opp['tactic_cfg']['ENTRY_SCORE'])
        if not passes_score:
            logger.info("      => ❌ Không đạt ngưỡng điểm. Xem xét cơ hội tiếp theo...")
            continue
        passes_momentum = not opp['tactic_cfg']['USE_MOMENTUM_FILTER'] or is_momentum_confirmed(opp['symbol'], GENERAL_CONFIG["MAIN_TIMEFRAME"], opp['tactic_cfg']['TRADE_TYPE'])
        if not passes_momentum:
            logger.info("      => ❌ Lọc động lượng thất bại. Xem xét cơ hội tiếp theo...")
            continue
        
        base_risk_pct = RISK_RULES_CONFIG["RISK_PER_TRADE_PERCENT"]
        zone_multiplier = ZONE_BASED_POLICIES.get(opp['zone'], {}).get("CAPITAL_RISK_MULTIPLIER", 1.0)
        session_multiplier = 1.0
        if SESSION_RISK_CONFIG["ENABLED"]:
            current_hour = datetime.now(VIETNAM_TZ).hour
            quiet_cfg = SESSION_RISK_CONFIG["QUIET_HOURS"]
            active_cfg = SESSION_RISK_CONFIG["ACTIVE_HOURS"]
            if quiet_cfg["START"] <= current_hour < quiet_cfg["END"]:
                session_multiplier = quiet_cfg["MULTIPLIER"]
                logger.info(f"      => 🌙 Phiên Á yên tĩnh. Giảm rủi ro (x{session_multiplier:.2f}).")
            elif active_cfg["START"] <= current_hour < active_cfg["END"]:
                session_multiplier = active_cfg["MULTIPLIER"]
                logger.info(f"      => 🌞 Phiên Âu/Mỹ sôi động. Tăng rủi ro (x{session_multiplier:.2f}).")
        adj_risk_pct = base_risk_pct * zone_multiplier * session_multiplier
        risk_amount_usd_est = capital_base * (adj_risk_pct / 100)
        passes_risk = (current_total_risk_usd + risk_amount_usd_est) <= risk_limit_usd
        if not passes_risk:
            logger.info("      => ❌ Vượt giới hạn tổng rủi ro. Xem xét cơ hội tiếp theo...")
            continue
        passes_correlation = check_correlation_risk(active_trades, opp['symbol'])
        if not passes_correlation:
            logger.info("      => ❌ Vượt giới hạn correlation risk. Xem xét cơ hội tiếp theo...")
            continue
        logger.info(f"      => ✅ Đạt mọi điều kiện. Tiến hành đặt lệnh...")
        execute_trade(opp, adj_risk_pct)
        found_trade_to_open = True
        break
    if not found_trade_to_open:
        logger.info(f"  => Không có cơ hội nào trong top {len(top_opps_to_log)} đạt ngưỡng vào lệnh.")

def execute_trade(opportunity, adjusted_risk_percent):
    symbol, tactic_cfg, indicators, score, tactic_name, zone = opportunity['symbol'], opportunity['tactic_cfg'], opportunity['indicators'], opportunity['score'], opportunity['tactic_name'], opportunity['zone']
    capital_base = state.get('initial_capital', connector.get_account_info()['equity'])
    order_type = mt5.ORDER_TYPE_BUY if tactic_cfg["TRADE_TYPE"] == "LONG" else mt5.ORDER_TYPE_SELL
    if not is_spread_acceptable(symbol):
        logger.warning(f"Bỏ qua {symbol} do spread quá rộng")
        return
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return logger.error(f"Không thể lấy giá {symbol}")
    entry_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    
    atr_value = indicators.get('atr', 0)
    atr_multiplier = tactic_cfg.get("ATR_SL_MULTIPLIER", 2.0)
    risk_dist = atr_value * atr_multiplier
    
    if risk_dist <= 0: 
        logger.warning(f"Khoảng cách rủi ro (risk_dist) không hợp lệ ({risk_dist:.5f}) cho {symbol}. ATR: {atr_value:.5f}, Multiplier: {atr_multiplier}")
        return
        
    sl_price = entry_price - risk_dist if order_type == mt5.ORDER_TYPE_BUY else entry_price + risk_dist
    tp_price = entry_price + (risk_dist * tactic_cfg.get("RR", 1.5)) if order_type == mt5.ORDER_TYPE_BUY else entry_price - (risk_dist * tactic_cfg.get("RR", 1.5))
    
    # --- DÒNG LOG CẢI TIẾN ĐƯỢC THÊM VÀO ĐÂY ---
    logger.info(f"      => Chuẩn bị lệnh {symbol}: Entry~{format_price(entry_price)}, SL={format_price(sl_price)}, TP={format_price(tp_price)}, ATR={atr_value:.5f}, RiskDist={risk_dist:.5f}")

    risk_amount_usd = capital_base * (adjusted_risk_percent / 100)
    
    lot_size = connector.calculate_lot_size(symbol, risk_amount_usd, sl_price, order_type)
    if lot_size is None or lot_size <= 0: 
        logger.warning(f"Lot size = {lot_size} không hợp lệ cho {symbol}")
        return
    
    result = None
    retry_limit = RISK_RULES_CONFIG.get("OPEN_TRADE_RETRY_LIMIT", 3)
    for attempt in range(retry_limit):
        #comment = f"exness_bot_{tactic_name}"
        comment = "" 
        result = connector.place_order(symbol, order_type, lot_size, sl_price, tp_price, magic_number=GENERAL_CONFIG["MAGIC_NUMBER"], comment=comment)
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
        event_msg = f"[{event_time}] 🚀 Mở lệnh {tactic_cfg['TRADE_TYPE']} {symbol} | Tactic: {tactic_name}"
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
        
        pnl_to_record = total_pnl_for_trade - sum(trade.get('partial_pnl_details', {}).values())
        state['daily_realized_pnl'] = state.get('daily_realized_pnl', 0.0) + pnl_to_record
        state['session_realized_pnl'] = state.get('session_realized_pnl', 0.0) + pnl_to_record
        
        trade.update({'status': f'Closed ({reason})', 'exit_price': last_deal.price if deals else 'N/A', 'exit_time': datetime.now(VIETNAM_TZ).isoformat(), 'pnl_usd': total_pnl_for_trade})
        state['active_trades'] = [t for t in state['active_trades'] if t['trade_id'] != trade['trade_id']]
        state.setdefault('trade_history', []).append(trade)
        cooldown_map = state.setdefault('cooldown_until', {}); cooldown_map.setdefault(trade['symbol'], {})[GENERAL_CONFIG["MAIN_TIMEFRAME"]] = (datetime.now(VIETNAM_TZ) + timedelta(hours=GENERAL_CONFIG["TRADE_COOLDOWN_HOURS"])).isoformat()
        export_trade_to_csv(trade)
        icon = "✅" if total_pnl_for_trade >= 0 else "❌"
        event_msg = f"[{event_time}] {icon} Đóng lệnh {trade['symbol']} ({reason}) | PnL: ${total_pnl_for_trade:,.2f}"
        state.setdefault('session_events', []).append(event_msg)
    else:
        state['daily_realized_pnl'] = state.get('daily_realized_pnl', 0.0) + closed_pnl
        state['session_realized_pnl'] = state.get('session_realized_pnl', 0.0) + closed_pnl
        
        trade['partial_pnl_details'][reason] = trade['partial_pnl_details'].get(reason, 0) + closed_pnl
        trade['lot_size'] = round(trade['lot_size'] - lot_to_close, 2)
        event_msg = f"[{event_time}] 💰 Chốt lời {close_pct*100:.0f}% lệnh {trade['symbol']} ({reason}) | PnL: ${closed_pnl:,.2f}"
        state.setdefault('session_events', []).append(event_msg)
    return True

def manage_open_positions():
    for trade in state.get("active_trades", [])[:]:
        symbol = trade['symbol']
        indicators = indicator_results.get(symbol, {}).get(GENERAL_CONFIG['MAIN_TIMEFRAME'])
        if not indicators: continue

        current_price = indicators.get("price")
        if not current_price: continue

        pnl_usd, pnl_percent = get_current_pnl(trade, current_price)
        trade['peak_pnl_percent'] = max(trade.get('peak_pnl_percent', 0.0), pnl_percent)

        is_long = trade['type'] == "LONG"
        
        # --- Ghi log kiểm tra SL/TP ---
        if (is_long and current_price <= trade['sl_price']) or (not is_long and current_price >= trade['sl_price']):
            logger.info(f"    - 🚦 [QUẢN LÝ LỆNH] {symbol}: Giá chạm Stop Loss tại {format_price(trade['sl_price'])}. Đóng lệnh.")
            if close_trade_on_mt5(trade, "SL"): continue
        
        is_dynamic_tp_active = trade.get('is_atr_trailing_active', False)
        if not is_dynamic_tp_active and trade.get('tp_price', 0) > 0:
            if (is_long and current_price >= trade['tp_price']) or (not is_long and current_price <= trade['tp_price']):
                logger.info(f"    - 🚦 [QUẢN LÝ LỆNH] {symbol}: Giá chạm Take Profit tại {format_price(trade['tp_price'])}. Đóng lệnh.")
                if close_trade_on_mt5(trade, "TP"): continue

        # --- Ghi log cho logic Early Close ---
        tactic_cfg = TACTICS_LAB.get(trade.get('opened_by_tactic'), {})
        last_score, entry_score = trade.get('last_score', 0), trade.get('entry_score', 0)
        base_threshold = ACTIVE_TRADE_MANAGEMENT_CONFIG['EARLY_CLOSE_ABS_THRESHOLD_L'] if is_long else ACTIVE_TRADE_MANAGEMENT_CONFIG['EARLY_CLOSE_ABS_THRESHOLD_S']
        market_regime = indicators.get("market_regime", "SIDEWAYS_VOLATILE")
        regime_multiplier = 0.8 if market_regime == "TRENDING" else 1.0
        threshold = base_threshold * regime_multiplier
        
        # LOG CHO NGƯỠNG TUYỆT ĐỐI
        if (is_long and last_score < threshold) or (not is_long and last_score > threshold):
            logger.info(f"    - 🚦 [QUẢN LÝ LỆNH] {symbol}: Điểm số ({last_score:.2f}) đã vi phạm ngưỡng tuyệt đối ({threshold:.2f}). Đóng toàn bộ lệnh.")
            if close_trade_on_mt5(trade, f"EC_Abs_{last_score:.1f}"): 
                continue

        # LOG CHO NGƯỠNG TƯƠNG ĐỐI
        rel_drop_pct = ACTIVE_TRADE_MANAGEMENT_CONFIG['EARLY_CLOSE_REL_DROP_PCT']
        rel_threshold = abs(entry_score) * (1 - rel_drop_pct)
        if abs(last_score) < rel_threshold and not trade.get('partial_closed_by_score'):
            close_pct_config = ACTIVE_TRADE_MANAGEMENT_CONFIG["PARTIAL_EARLY_CLOSE_PCT"]
            logger.info(f"    - 🚦 [QUẢN LÝ LỆNH] {symbol}: Điểm số ({abs(last_score):.2f}) giảm tương đối quá ngưỡng ({rel_threshold:.2f}). Đóng {close_pct_config*100:.0f}% lệnh.")
            if close_trade_on_mt5(trade, f"EC_Rel_{last_score:.1f}", close_pct_config):
                trade['partial_closed_by_score'] = True

        # --- Ghi log cho các logic quản lý lợi nhuận ---
        initial_risk_dist = abs(trade['entry_price'] - trade['initial_sl'])
        if initial_risk_dist > 0:
            pnl_ratio = (current_price - trade['entry_price']) / initial_risk_dist if is_long else (trade['entry_price'] - current_price) / initial_risk_dist

            if tactic_cfg.get("ENABLE_PARTIAL_TP", False) and not trade.get("tp1_hit", False) and pnl_ratio >= tactic_cfg.get("TP1_RR_RATIO", 0.6):
                logger.info(f"    - 🚦 [QUẢN LÝ LỆNH] {symbol}: Đạt mục tiêu TP1 (RR >= {tactic_cfg.get('TP1_RR_RATIO', 0.6)}). Chốt lời một phần.")
                if close_trade_on_mt5(trade, "TP1", tactic_cfg.get("TP1_PROFIT_PCT", 0.5)):
                    trade['tp1_hit'] = True
                    dtp_cfg = ACTIVE_TRADE_MANAGEMENT_CONFIG.get("DYNAMIC_TP_ATR_TRAIL", {})
                    if dtp_cfg.get("ENABLED", False) and dtp_cfg.get("ACTIVATED_AFTER_TP1", False):
                        trade['is_atr_trailing_active'] = True
                        logger.info(f"        - ATR TRAIL {symbol}: Kích hoạt chế độ gồng lời bằng ATR Trailing Stop.")
                    else:
                        new_sl = trade['entry_price']
                        if connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price']):
                            trade['sl_price'] = new_sl
                            logger.info(f"        - TP1 {symbol}: Dời SL về entry {format_price(new_sl)}")

            if trade.get('is_atr_trailing_active', False):
                dtp_cfg = ACTIVE_TRADE_MANAGEMENT_CONFIG.get("DYNAMIC_TP_ATR_TRAIL", {})
                current_atr = indicators.get('atr', trade.get('atr_at_entry', 0))
                if current_atr > 0:
                    trail_dist = current_atr * dtp_cfg.get("ATR_MULTIPLIER", 2.5)
                    new_sl = current_price - trail_dist if is_long else current_price + trail_dist
                    is_better = (new_sl > trade['sl_price']) if is_long else (new_sl < trade['sl_price'])
                    if is_better:
                        if connector.modify_position(trade['ticket_id'], new_sl, 0):
                            trade['sl_price'] = new_sl
                            if trade.get('tp_price', 0) != 0: trade['tp_price'] = 0
                            logger.info(f"    - ⛓️ [ATR TRAIL] {symbol}: SL được cập nhật lên {format_price(new_sl)}")
            elif tactic_cfg.get("USE_TRAILING_SL", False) and pnl_ratio >= tactic_cfg.get("TRAIL_ACTIVATION_RR", 1.2):
                trail_dist = initial_risk_dist * tactic_cfg.get("TRAIL_DISTANCE_RR", 0.8)
                new_sl = current_price - trail_dist if is_long else current_price + trail_dist
                is_better = (new_sl > trade['sl_price']) if is_long else (new_sl < trade['sl_price'])
                if is_better and abs(new_sl - trade['sl_price']) > (initial_risk_dist * 0.1):
                    if connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price']):
                        trade['sl_price'] = new_sl
                        logger.info(f"    - ⛓️ [TSL] {symbol}: SL được cập nhật lên {format_price(new_sl)}")

        pp_cfg = ACTIVE_TRADE_MANAGEMENT_CONFIG["PROFIT_PROTECTION"]
        if pp_cfg["ENABLED"] and not trade.get('profit_taken', False) and trade['peak_pnl_percent'] >= pp_cfg["MIN_PEAK_PNL_TRIGGER"]:
            if (trade['peak_pnl_percent'] - pnl_percent) >= pp_cfg["PNL_DROP_TRIGGER_PCT"]:
                logger.info(f"    - 🚦 [QUẢN LÝ LỆNH] {symbol}: Lợi nhuận giảm từ đỉnh. Kích hoạt Bảo vệ lợi nhuận.")
                if close_trade_on_mt5(trade, "PP", pp_cfg["PARTIAL_CLOSE_PCT"]):
                    trade['profit_taken'] = True


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
        
        indicators = indicator_results.get(trade['symbol'], {}).get(GENERAL_CONFIG['MAIN_TIMEFRAME'])
        if not indicators: continue
        
        current_price = indicators.get("price")
        if not current_price: continue
            
        last_entry_price = trade['dca_entries'][-1]['price'] if trade.get('dca_entries') else trade['entry_price']
        
        atr_at_entry = trade.get('atr_at_entry', 0)
        if atr_at_entry <= 0: continue
        distance_in_atr = abs(current_price - last_entry_price) / atr_at_entry
        dca_trigger_atr = 1.5
        is_going_against = (trade['type'] == 'LONG' and current_price < last_entry_price) or \
                           (trade['type'] == 'SHORT' and current_price > last_entry_price)

        if not (is_going_against and distance_in_atr >= dca_trigger_atr): continue

        score_threshold = DCA_CONFIG["SCORE_MIN_THRESHOLD_LONG"] if trade['type'] == "LONG" else DCA_CONFIG["SCORE_MIN_THRESHOLD_SHORT"]
        if (trade['type'] == "LONG" and trade['last_score'] < score_threshold) or (trade['type'] == "SHORT" and trade['last_score'] > score_threshold): continue
        
        if DCA_CONFIG.get("REQUIRE_CONFIRMATION_CANDLE", False):
            candle = indicators.get("candle_pattern", "none")
            confirmation_passed = False
            if trade['type'] == 'LONG' and candle in DCA_CONFIG.get("BULLISH_CONFIRMATION_CANDLES", []):
                confirmation_passed = True
            elif trade['type'] == 'SHORT' and candle in DCA_CONFIG.get("BEARISH_CONFIRMATION_CANDLES", []):
                confirmation_passed = True
            
            if not confirmation_passed:
                continue

        strategy = DCA_CONFIG.get("STRATEGY", "aggressive")
        multiplier = DCA_CONFIG.get("MULTIPLIERS", {}).get(strategy, 1.0)
        initial_lot_size = trade.get('initial_lot_size', trade['lot_size'])
        dca_lot_size = initial_lot_size * multiplier
        order_type = mt5.ORDER_TYPE_BUY if trade['type'] == "LONG" else mt5.ORDER_TYPE_SELL
        result = None
        retry_limit = RISK_RULES_CONFIG.get("OPEN_TRADE_RETRY_LIMIT", 3)
        comment = f"exness_bot_dca_{strategy}"
        for attempt in range(retry_limit):
            result = connector.place_order(trade['symbol'], order_type, dca_lot_size, 0, 0, magic_number=GENERAL_CONFIG["MAGIC_NUMBER"], comment=comment)
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
            event_msg = f"[{event_time}] 🧠 DCA ({strategy}) {trade['symbol']} | Lot: {dca_lot_size} @ {format_price(result.price)}"
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
        state.setdefault("trade_history", []).extend(closed_trades)
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
                msg = (f"⚠️ CẢNH BÁO: Phát hiện vị thế lạ/mở côi trên tài khoản.\n"
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
    pnl_summary_line = f"🎯 Win Rate: **{win_rate_str}** | 🚀 PF: **{pf_str}** | 💵 PnL Đóng: **${total_pnl_closed:,.2f}**\n"
    pnl_summary_line += f"👍 AVG Lãi: **{avg_win_str}** | 👎 AVG Lỗ: **{avg_loss_str}**"
    report = [
        f"📑 **BÁO CÁO TỔNG KẾT EXNESS BOT** - {datetime.now(VIETNAM_TZ).strftime('%H:%M %d-%m-%Y')}",
        f"💰 Vốn Nền tảng: **${initial_capital:,.2f}** | 💵 Balance: **${balance:,.2f}**",
        f"🦊 Equity: **${equity:,.2f}** | 📈 PnL Tổng: **${pnl_total_usd:+,.2f} ({pnl_total_percent:+.2f}%)**",
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
            
            manage_open_positions()
            handle_stale_trades()
            handle_dca_opportunities()

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

            interval_minutes = GENERAL_CONFIG["HEAVY_TASK_INTERVAL_MINUTES"]
            current_minute = now_vn.minute
            
            if (current_minute % interval_minutes == 0) and (current_minute != last_heavy_task_minute):
                last_heavy_task_minute = current_minute
                
                logger.info(f"--- [Chu kỳ {interval_minutes}m] Bắt đầu quét và phân tích... ---")
                manage_dynamic_capital()
                load_all_indicators()
                update_scores_for_active_trades()
                find_and_open_new_trades()
                save_state()
            
            if now_ts - last_reconciliation_time > GENERAL_CONFIG["RECONCILIATION_INTERVAL_MINUTES"] * 60:
                reconcile_positions()
                last_reconciliation_time = now_ts
                
            time.sleep(GENERAL_CONFIG["LOOP_SLEEP_SECONDS"])
        except KeyboardInterrupt:
            logger.info("Phát hiện KeyboardInterrupt. Đang dừng bot...")
            raise
        except Exception as e:
            logger.error(f"Lỗi nghiêm trọng trong vòng lặp chính: {e}\n```{traceback.format_exc()}```")
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
                logger.critical(f"Gửi thông báo lỗi nghiêm trọng đến Discord: {e}")
                send_discord_message(f"🚨 LỖI NGHIÊM TRỌNG: {error_message}", is_error=True, force=True)
                state['last_critical_error_alert_time'] = now_dt.isoformat()
                save_state()
            time.sleep(60)

def run_bot():
    global connector, state
    setup_logging()
    logger.info("=== KHỞI ĐỘNG EXNESS BOT V2.7.0 (THE APEX STRATEGIST) ===")
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
        logger.info(f"✅ Kết nối MT5 thành công. Tài khoản #{account_info['login']} | Vốn nền tảng: ${state.get('initial_capital', 0):,.2f}")
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
