# -*- coding: utf-8 -*-
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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv
import traceback

# --- CẤU HÌNH ĐƯỜNG DẪN & IMPORT (Từ Bản 2 - Tốt hơn) ---
try:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(PROJECT_ROOT) == 'livetrade':
        PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)
    sys.path.append(PROJECT_ROOT)
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

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
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# --- BIẾN TOÀN CỤC & LOGGER ---
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
logger = logging.getLogger("ExnessBot")

# ==============================================================================
# ==================== ⚙️ TRUNG TÂM CẤU HÌNH (MERGED) ⚙️ ====================
# ==============================================================================

GENERAL_CONFIG = {
    "SYMBOLS_TO_SCAN": [s.strip() for s in os.getenv("SYMBOLS_TO_SCAN", "BTCUSD,XAUUSD").split(',')],
    "MAIN_TIMEFRAME": "5m",
    "MTF_TIMEFRAMES": ["5m", "15m", "1h"],
    "LOOP_SLEEP_SECONDS": 2,
    "HEAVY_TASK_INTERVAL_MINUTES": 5,
    "RECONCILIATION_INTERVAL_MINUTES": 15,
    "CANDLE_FETCH_COUNT": 300,
    "TOP_N_OPPORTUNITIES_TO_CHECK": 5,
    "TRADE_COOLDOWN_HOURS": 1.0,
    "OVERRIDE_COOLDOWN_SCORE": 7.5,
    "MAGIC_NUMBER": 202508,
    # <<< MERGED: Khôi phục cấu hình Momentum Filter chi tiết từ Bản 1
    "MOMENTUM_FILTER_CONFIG": {
        "ENABLED": True,
        "RULES_BY_TIMEFRAME": {
            "5m": {"WINDOW": 5, "REQUIRED_CANDLES": 3},
            "15m": {"WINDOW": 5, "REQUIRED_CANDLES": 2},
            "1h": {"WINDOW": 4, "REQUIRED_CANDLES": 1}
        }
    },
    "DAILY_SUMMARY_TIMES": ["08:10", "20:10"],
}

# <<< MERGED: Giữ lại cơ chế Quản lý Vốn Động từ Bản 2
CAPITAL_MANAGEMENT_CONFIG = {
    "ENABLED": True,
    "AUTO_COMPOUND_THRESHOLD_PCT": 10.0,
    "AUTO_DELEVERAGE_THRESHOLD_PCT": -10.0,
    "CAPITAL_ADJUSTMENT_COOLDOWN_HOURS": 48
}

# <<< MERGED: Giữ lại MTF Analysis nâng cao từ Bản 2
MTF_ANALYSIS_CONFIG = {
    "ENABLED": True,
    "BONUS_COEFFICIENT": 1.05,
    "PENALTY_COEFFICIENT": 0.95,
    "SEVERE_PENALTY_COEFFICIENT": 0.85, # Giữ lại hệ số phạt nặng
    "SIDEWAYS_PENALTY_COEFFICIENT": 0.97,
}

# <<< MERGED: Khôi phục cơ chế Extreme Zone từ Bản 1
EXTREME_ZONE_ADJUSTMENT_CONFIG = {
    "ENABLED": True,
    "MAX_BONUS_COEFF": 1.10,
    "MIN_PENALTY_COEFF": 0.90,
    "SCORING_WEIGHTS": { "RSI": 0.4, "BB_POS": 0.4, "CANDLE": 0.35, "SR_LEVEL": 0.35 },
    "BASE_IMPACT": { "BONUS_PER_POINT": 0.07, "PENALTY_PER_POINT": -0.08 },
    "CONFLUENCE_MULTIPLIER": 1.6,
    "RULES_BY_TIMEFRAME": {
        "5m": {"OVERBOUGHT": {"RSI_ABOVE": 75, "BB_POS_ABOVE": 0.98}, "OVERSOLD": {"RSI_BELOW": 25, "BB_POS_BELOW": 0.05}},
        "15m": {"OVERBOUGHT": {"RSI_ABOVE": 73, "BB_POS_ABOVE": 0.95}, "OVERSOLD": {"RSI_BELOW": 27, "BB_POS_BELOW": 0.08}},
        "1h": {"OVERBOUGHT": {"RSI_ABOVE": 72, "BB_POS_ABOVE": 0.95}, "OVERSOLD": {"RSI_BELOW": 30, "BB_POS_BELOW": 0.10}}
    },
}

ACTIVE_TRADE_MANAGEMENT_CONFIG = {
    "EARLY_CLOSE_ABS_THRESHOLD_L": 4.5, "EARLY_CLOSE_ABS_THRESHOLD_S": -4.5, "EARLY_CLOSE_REL_DROP_PCT": 0.30, "PARTIAL_EARLY_CLOSE_PCT": 0.5,
    "PROFIT_PROTECTION": {"ENABLED": True, "MIN_PEAK_PNL_TRIGGER": 2.5, "PNL_DROP_TRIGGER_PCT": 1.0, "PARTIAL_CLOSE_PCT": 0.5}
}

RISK_RULES_CONFIG = {
    "RISK_PER_TRADE_PERCENT": 1.0, "MAX_ACTIVE_TRADES": 5,
    "STALE_TRADE_RULES": {"5m": {"HOURS": 8, "PROGRESS_THRESHOLD_PCT": 1.0}, "STAY_OF_EXECUTION_SCORE_L": 6.0, "STAY_OF_EXECUTION_SCORE_S": -6.0}
}

# <<< MERGED: Khôi phục cấu hình DCA chi tiết từ Bản 1
DCA_CONFIG = {
    "ENABLED": True, "MAX_DCA_ENTRIES": 2,
    "TRIGGER_DROP_PCT_BY_TIMEFRAME": {"5m": -3.0, "15m": -4.0, "1h": -5.0},
    "SCORE_MIN_THRESHOLD_LONG": 6.5, "SCORE_MIN_THRESHOLD_SHORT": -6.5,
    "CAPITAL_MULTIPLIER": 1.5, "DCA_COOLDOWN_HOURS": 4
}

# <<< MERGED: Khôi phục cấu hình Discord đầy đủ từ Bản 1
DISCORD_CONFIG = {
    "WEBHOOK_URL": os.getenv("DISCORD_EXNESS_WEBHOOK"),
    "CHUNK_DELAY_SECONDS": 2
}

LEADING_ZONE, COINCIDENT_ZONE, LAGGING_ZONE, NOISE_ZONE = "LEADING", "COINCIDENT", "LAGGING", "NOISE"
ZONE_BASED_POLICIES = {
    LEADING_ZONE: {"CAPITAL_RISK_MULTIPLIER": 0.8}, COINCIDENT_ZONE: {"CAPITAL_RISK_MULTIPLIER": 1.2},
    LAGGING_ZONE: {"CAPITAL_RISK_MULTIPLIER": 1.0}, NOISE_ZONE: {"CAPITAL_RISK_MULTIPLIER": 0.5}
}

# <<< MERGED: Khôi phục lại toàn bộ 10 chiến thuật từ Bản 1
TACTICS_LAB = {
    "Balanced_Trader_L": {"OPTIMAL_ZONE": [LAGGING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "LONG", "ENTRY_SCORE": 6.3, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.5, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.2, "TRAIL_DISTANCE_RR": 0.8, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.6, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": True},
    "Breakout_Hunter_L": {"OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "LONG", "ENTRY_SCORE": 7.0, "RR": 1.7, "ATR_SL_MULTIPLIER": 2.4, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.3, "TRAIL_DISTANCE_RR": 0.9, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.6, "TP1_PROFIT_PCT": 0.5, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": False},
    "Dip_Hunter_L": {"OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "LONG", "ENTRY_SCORE": 6.8, "RR": 1.4, "ATR_SL_MULTIPLIER": 3.2, "USE_TRAILING_SL": False, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.7, "USE_MOMENTUM_FILTER": False, "USE_EXTREME_ZONE_FILTER": True},
    "AI_Aggressor_L": {"OPTIMAL_ZONE": [COINCIDENT_ZONE], "TRADE_TYPE": "LONG", "ENTRY_SCORE": 6.6, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.2, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.1, "TRAIL_DISTANCE_RR": 0.7, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.6, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": False},
    "Cautious_Observer_L": {"OPTIMAL_ZONE": [NOISE_ZONE], "TRADE_TYPE": "LONG", "ENTRY_SCORE": 7.5, "RR": 1.3, "ATR_SL_MULTIPLIER": 1.8, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.0, "TRAIL_DISTANCE_RR": 0.6, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.7, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": True},
    "Balanced_Seller_S": {"OPTIMAL_ZONE": [LAGGING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -6.3, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.5, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.2, "TRAIL_DISTANCE_RR": 0.8, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.6, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": True},
    "Breakdown_Hunter_S": {"OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -7.0, "RR": 1.7, "ATR_SL_MULTIPLIER": 2.4, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.3, "TRAIL_DISTANCE_RR": 0.9, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.6, "TP1_PROFIT_PCT": 0.5, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": False},
    "Rally_Seller_S": {"OPTIMAL_ZONE": [LEADING_ZONE, COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -6.8, "RR": 1.4, "ATR_SL_MULTIPLIER": 3.2, "USE_TRAILING_SL": False, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.7, "USE_MOMENTUM_FILTER": False, "USE_EXTREME_ZONE_FILTER": True},
    "AI_Contrarian_S": {"OPTIMAL_ZONE": [COINCIDENT_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -6.6, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.2, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.1, "TRAIL_DISTANCE_RR": 0.7, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.6, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": False},
    "Cautious_Shorter_S": {"OPTIMAL_ZONE": [NOISE_ZONE], "TRADE_TYPE": "SHORT", "ENTRY_SCORE": -7.5, "RR": 1.3, "ATR_SL_MULTIPLIER": 1.8, "USE_TRAILING_SL": True, "TRAIL_ACTIVATION_RR": 1.0, "TRAIL_DISTANCE_RR": 0.6, "ENABLE_PARTIAL_TP": True, "TP1_RR_RATIO": 0.5, "TP1_PROFIT_PCT": 0.7, "USE_MOMENTUM_FILTER": True, "USE_EXTREME_ZONE_FILTER": True},
}

# ==============================================================================
# ==================== BIẾN TOÀN CỤC & HÀM TIỆN ÍCH ====================
# ==============================================================================

connector = None
state = {}
indicator_results = {}
price_dataframes = {}
_last_discord_send_time = None # <<< MERGED: Khôi phục biến cho Discord Cooldown

def setup_logging():
    # Giữ nguyên hàm setup_logging tốt của Bản 2
    global logger
    log_filename = os.path.join(LOG_DIR, f"exness_bot_{datetime.now().strftime('%Y-%m-%d')}.log")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.hasHandlers(): logger.handlers.clear()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

def acquire_lock(timeout=10):
    # Giữ nguyên hàm acquire_lock tốt của Bản 2
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
    # Giữ nguyên hàm load_state tốt của Bản 2
    global state
    if not os.path.exists(STATE_FILE):
        state = {"active_trades": [], "trade_history": [], "initial_capital": 0.0}
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        state = {"active_trades": [], "trade_history": [], "initial_capital": 0.0}

def save_state():
    temp_path = STATE_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)
    os.replace(temp_path, STATE_FILE)

def format_price(price):
    if price is None: return "N/A"
    return f"{price:,.5f}" if price < 10 else f"{price:,.2f}"

# <<< MERGED: Khôi phục hàm gửi Discord đầy đủ tính năng của Bản 1
def can_send_discord_now(force=False):
    global _last_discord_send_time
    if force:
        return True
    now = datetime.now()
    if _last_discord_send_time is None or (now - _last_discord_send_time).total_seconds() > 120:
        _last_discord_send_time = now
        return True
    return False

def send_discord_message(content, force=False):
    if not can_send_discord_now(force):
        return
    webhook_url = DISCORD_CONFIG.get("WEBHOOK_URL")
    if not webhook_url:
        return
    max_len = 1900
    chunks = []
    lines = content.split('\n')
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_len:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += ("\n" + line) if current_chunk else line
    if current_chunk:
        chunks.append(current_chunk)
    for i, chunk in enumerate(chunks):
        content_to_send = f"*(Phần {i+1}/{len(chunks)})*\n{chunk}" if len(chunks) > 1 else chunk
        try:
            requests.post(webhook_url, json={"content": content_to_send}, timeout=15).raise_for_status()
            if i < len(chunks) - 1:
                time.sleep(DISCORD_CONFIG["CHUNK_DELAY_SECONDS"])
        except requests.exceptions.RequestException as e:
            logger.error(f"Lỗi gửi Discord: {e}")
            break

def export_trade_to_csv(trade):
    try:
        df = pd.DataFrame([trade])
        df.to_csv(TRADE_HISTORY_CSV, mode='a', header=not os.path.exists(TRADE_HISTORY_CSV), index=False)
    except Exception as e:
        logger.error(f"Lỗi xuất CSV: {e}")

def get_current_pnl(trade, current_price):
    # Giữ lại hàm PnL chính xác hơn của Bản 2
    if not current_price or trade['entry_price'] <= 0: return 0.0, 0.0
    try:
        profit = connector.calculate_profit(trade['symbol'], mt5.ORDER_TYPE_BUY if trade['type'] == "LONG" else mt5.ORDER_TYPE_SELL, trade['lot_size'], trade['entry_price'], current_price)
        pnl_usd = profit if profit is not None else 0.0
        
        capital_at_risk = trade.get('risk_amount_usd', 1)
        # Ước tính PnL % dựa trên số vốn rủi ro ban đầu
        pnl_percent = (pnl_usd / capital_at_risk) * 100 if capital_at_risk > 0 else 0.0
        return pnl_usd, pnl_percent
    except Exception:
        return 0.0, 0.0
        
def calculate_lot_size(equity, risk_percent, symbol, order_type, entry_price, sl_price):
    # Giữ lại hàm tính lot sạch hơn của Bản 2
    if entry_price == sl_price or equity <= 0: return 0.0
    risk_amount = equity * (risk_percent / 100)
    loss = connector.calculate_loss(symbol, order_type, 1.0, entry_price, sl_price)
    if not loss or abs(loss) < 0.01: return 0.0
    lot = risk_amount / abs(loss)
    info = mt5.symbol_info(symbol)
    if not info: return 0.0
    lot = math.floor(lot / info.volume_step) * info.volume_step
    return round(lot, 2) if lot >= info.volume_min else 0.0

# ==============================================================================
# ==================== LOGIC PHÂN TÍCH & QUẢN LÝ VỐN ====================
# ==============================================================================

def load_all_indicators():
    for symbol in GENERAL_CONFIG["SYMBOLS_TO_SCAN"]:
        indicator_results[symbol], price_dataframes[symbol] = {}, {}
        for timeframe in GENERAL_CONFIG["MTF_TIMEFRAMES"]:
            df = connector.get_historical_data(symbol, timeframe, GENERAL_CONFIG["CANDLE_FETCH_COUNT"])
            if df is not None and not df.empty:
                indicator_results[symbol][timeframe] = calculate_indicators(df, symbol, timeframe)
                price_dataframes[symbol][timeframe] = df

def update_scores_for_active_trades():
    for trade in state.get("active_trades", []):
        indicators = indicator_results.get(trade['symbol'], {}).get(GENERAL_CONFIG['MAIN_TIMEFRAME'])
        if indicators:
            decision = get_advisor_decision(trade['symbol'], GENERAL_CONFIG['MAIN_TIMEFRAME'], indicators, {"WEIGHTS": {'tech': 1.0}})
            raw_score = decision.get('final_score', 0.0)
            
            mtf_coeff = get_mtf_adjustment_coefficient(trade['symbol'], GENERAL_CONFIG['MAIN_TIMEFRAME'], trade['type'])
            
            tactic_cfg = TACTICS_LAB.get(trade.get('opened_by_tactic'), {})
            ez_coeff = 1.0
            if tactic_cfg.get("USE_EXTREME_ZONE_FILTER", False):
                ez_coeff = get_extreme_zone_adjustment_coefficient(indicators, GENERAL_CONFIG['MAIN_TIMEFRAME'])

            trade['last_score'] = raw_score * mtf_coeff * ez_coeff
            trade['last_zone'] = determine_market_zone(indicators)

def determine_market_zone(indicators):
    # <<< MERGED: Sử dụng logic quantile của Bản 2, kết hợp với hệ thống chấm điểm của Bản 1
    scores = {LEADING_ZONE: 0, COINCIDENT_ZONE: 0, LAGGING_ZONE: 0, NOISE_ZONE: 0}
    adx, bb_width, trend = indicators.get('adx', 20), indicators.get('bb_width', 0), indicators.get('trend', "sideways")
    if adx < 20: scores[NOISE_ZONE] += 3
    if adx > 25 and trend != "sideways": scores[LAGGING_ZONE] += 2.5
    
    df = price_dataframes.get(indicators['symbol'], {}).get(indicators['interval'], pd.DataFrame())
    if not df.empty and 'bb_width' in df.columns and not df['bb_width'].isna().all():
        if bb_width < df['bb_width'].quantile(0.15): scores[LEADING_ZONE] += 2.5 # Logic quantile thông minh từ Bản 2

    if indicators.get('breakout_signal', "none") != "none": scores[COINCIDENT_ZONE] += 3
    if indicators.get('macd_cross', "neutral") not in ["neutral", "no_cross"]: scores[COINCIDENT_ZONE] += 2
    
    return max(scores, key=scores.get) if any(v > 0 for v in scores.values()) else NOISE_ZONE

def get_mtf_adjustment_coefficient(symbol, target_interval, trade_type):
    # Giữ lại logic MTF nâng cao của Bản 2
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

# <<< MERGED: Khôi phục hàm Extreme Zone từ Bản 1
def get_extreme_zone_adjustment_coefficient(indicators, interval):
    cfg = EXTREME_ZONE_ADJUSTMENT_CONFIG
    if not cfg.get("ENABLED", False): return 1.0
    
    weights = cfg.get("SCORING_WEIGHTS", {})
    base_impact = cfg.get("BASE_IMPACT", {})
    confluence_multiplier = cfg.get("CONFLUENCE_MULTIPLIER", 1.5)
    rules = cfg.get("RULES_BY_TIMEFRAME", {}).get(interval)
    if not rules: return 1.0

    price, bbu, bbm, bbl, rsi = indicators.get("price", 0), indicators.get("bb_upper", 0), indicators.get("bb_middle", 0), indicators.get("bb_lower", 0), indicators.get("rsi_14", 50)
    if not all([price > 0, bbu > bbm, bbm > bbl]): return 1.0

    bonus_score, penalty_score = 0.0, 0.0
    
    # Check for oversold bonus
    oversold_rule = rules.get("OVERSOLD", {})
    bb_range = bbu - bbl
    if bb_range > 0:
      bb_pos = (price - bbl) / bb_range
      if rsi < oversold_rule.get("RSI_BELOW", 1): bonus_score += weights.get("RSI", 0.4)
      if bb_pos < oversold_rule.get("BB_POS_BELOW", 0.05): bonus_score += weights.get("BB_POS", 0.4)
    
    # Check for overbought penalty
    overbought_rule = rules.get("OVERBOUGHT", {})
    if bb_range > 0:
      bb_pos = (price - bbl) / bb_range
      if rsi > overbought_rule.get("RSI_ABOVE", 99): penalty_score += weights.get("RSI", 0.4)
      if bb_pos > overbought_rule.get("BB_POS_ABOVE", 0.98): penalty_score += weights.get("BB_POS", 0.4)

    if bonus_score >= (weights.get("RSI", 0.4) + weights.get("BB_POS", 0.4)): bonus_score *= confluence_multiplier
    if penalty_score >= (weights.get("RSI", 0.4) + weights.get("BB_POS", 0.4)): penalty_score *= confluence_multiplier

    bonus_impact = base_impact.get("BONUS_PER_POINT", 0.05)
    penalty_impact = base_impact.get("PENALTY_PER_POINT", -0.07)
    
    coeff_change = (bonus_score * bonus_impact) + (penalty_score * penalty_impact)
    calculated_coeff = 1.0 + coeff_change
    
    min_coeff = cfg.get("MIN_PENALTY_COEFF", 0.90)
    max_coeff = cfg.get("MAX_BONUS_COEFF", 1.05)
    
    return max(min_coeff, min(calculated_coeff, max_coeff))

# <<< MERGED: Khôi phục hàm Momentum Filter tinh vi từ Bản 1
def is_momentum_confirmed(symbol, interval, direction="LONG"):
    config = GENERAL_CONFIG.get("MOMENTUM_FILTER_CONFIG", {})
    if not config.get("ENABLED", False): return True
    
    rules = config.get("RULES_BY_TIMEFRAME", {}).get(interval, {"WINDOW": 3, "REQUIRED_CANDLES": 2})
    window = rules.get("WINDOW", 3)
    required_candles = rules.get("REQUIRED_CANDLES", 2)
    
    try:
        df = price_dataframes.get(symbol, {}).get(interval)
        if df is None or len(df) < window: return True
        
        recent_candles = df.iloc[-window:]
        good_candles_count = 0
        
        for _, candle in recent_candles.iterrows():
            candle_range = candle['high'] - candle['low']
            if candle_range == 0: continue
            
            is_green = candle['close'] > candle['open']
            closing_position_ratio = (candle['close'] - candle['low']) / candle_range
            
            if direction == "LONG":
                if is_green or closing_position_ratio > 0.6:
                    good_candles_count += 1
            else: # SHORT
                if not is_green or closing_position_ratio < 0.4:
                    good_candles_count += 1
        
        return good_candles_count >= required_candles
    except Exception as e:
        logger.error(f"Lỗi is_momentum_confirmed: {e}")
        return True

# <<< MERGED: Giữ lại hàm Quản lý Vốn Động hoàn toàn mới từ Bản 2
def manage_dynamic_capital():
    if not CAPITAL_MANAGEMENT_CONFIG["ENABLED"]: return
    now_dt, account_info = datetime.now(VIETNAM_TZ), connector.get_account_info()
    if not account_info: return
    current_equity = account_info['equity']
    initial_capital = state.get('initial_capital', 0.0)
    if initial_capital <= 0:
        state['initial_capital'] = current_equity; state['last_capital_adjustment_time'] = now_dt.isoformat()
        return logger.info(f"🌱 Thiết lập Vốn Nền tảng: ${state['initial_capital']:,.2f}")
    
    last_adj_str = state.get('last_capital_adjustment_time')
    cooldown = CAPITAL_MANAGEMENT_CONFIG["CAPITAL_ADJUSTMENT_COOLDOWN_HOURS"]
    if last_adj_str and (now_dt - datetime.fromisoformat(last_adj_str)).total_seconds() / 3600 < cooldown: return
    
    growth_pct = (current_equity / initial_capital - 1) * 100
    if growth_pct >= CAPITAL_MANAGEMENT_CONFIG["AUTO_COMPOUND_THRESHOLD_PCT"] or growth_pct <= CAPITAL_MANAGEMENT_CONFIG["AUTO_DELEVERAGE_THRESHOLD_PCT"]:
        logger.info(f"💰 Hiệu suất ({growth_pct:+.2f}%) đạt ngưỡng. Cập nhật Vốn Nền tảng.")
        state["initial_capital"] = current_equity; state['last_capital_adjustment_time'] = now_dt.isoformat()
        logger.info(f"    Vốn Nền tảng MỚI: ${state['initial_capital']:,.2f}")

# ==============================================================================
# ==================== QUẢN LÝ GIAO DỊCH (MERGED LOGIC) ====================
# ==============================================================================

def find_and_open_new_trades():
    if len(state.get("active_trades", [])) >= RISK_RULES_CONFIG["MAX_ACTIVE_TRADES"]: return
    opportunities, now_vn = [], datetime.now(VIETNAM_TZ)
    cooldown_map = state.get('cooldown_until', {})
    
    for symbol in GENERAL_CONFIG["SYMBOLS_TO_SCAN"]:
        if any(t['symbol'] == symbol for t in state.get("active_trades", [])): continue
        cooldown_str = cooldown_map.get(symbol, {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if cooldown_str and now_vn < datetime.fromisoformat(cooldown_str): continue
        
        indicators = indicator_results.get(symbol, {}).get(GENERAL_CONFIG["MAIN_TIMEFRAME"])
        if not indicators: continue
            
        decision = get_advisor_decision(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], indicators, {"WEIGHTS": {'tech': 1.0}})
        raw_score = decision.get('final_score', 0.0)
        if abs(raw_score) < 4.0: continue

        market_zone, trade_type = determine_market_zone(indicators), "LONG" if raw_score > 0 else "SHORT"
        
        for tactic_name, tactic_cfg in TACTICS_LAB.items():
            if tactic_cfg["TRADE_TYPE"] != trade_type: continue
            if market_zone not in tactic_cfg.get("OPTIMAL_ZONE", []): continue
            
            mtf_coeff = get_mtf_adjustment_coefficient(symbol, GENERAL_CONFIG["MAIN_TIMEFRAME"], trade_type)
            
            # <<< MERGED: Áp dụng lại logic Extreme Zone
            ez_coeff = 1.0
            if tactic_cfg.get("USE_EXTREME_ZONE_FILTER", False):
                ez_coeff = get_extreme_zone_adjustment_coefficient(indicators, GENERAL_CONFIG["MAIN_TIMEFRAME"])
            
            final_score = raw_score * mtf_coeff * ez_coeff
            
            if cooldown_str and abs(final_score) < GENERAL_CONFIG["OVERRIDE_COOLDOWN_SCORE"]: continue
            
            opportunities.append({"symbol": symbol, "score": final_score, "raw_score": raw_score, "tactic_name": tactic_name, "tactic_cfg": tactic_cfg, "indicators": indicators, "zone": market_zone, "mtf_coeff": mtf_coeff, "ez_coeff": ez_coeff})
            
    if not opportunities: return
    
    sorted_opps = sorted(opportunities, key=lambda x: abs(x['score']), reverse=True)[:GENERAL_CONFIG["TOP_N_OPPORTUNITIES_TO_CHECK"]]
    
    for opp in sorted_opps:
        score, entry_thresh = opp['score'], opp['tactic_cfg']['ENTRY_SCORE']
        passes = (score >= entry_thresh) if score > 0 else (score <= entry_thresh)
        if not passes: continue
        
        # <<< MERGED: Sử dụng lại is_momentum_confirmed của Bản 1
        if opp['tactic_cfg']['USE_MOMENTUM_FILTER'] and not is_momentum_confirmed(opp['symbol'], GENERAL_CONFIG["MAIN_TIMEFRAME"], opp['tactic_cfg']['TRADE_TYPE']):
            logger.info(f"    => ⚠️ {opp['symbol']} không vượt qua bộ lọc động lượng tinh vi.")
            continue
            
        logger.info(f"✅ Tín hiệu đạt ngưỡng: {opp['symbol']} | {opp['tactic_name']} | Điểm: {score:.2f} (Gốc:{opp['raw_score']:.2f}) [MTF:x{opp['mtf_coeff']:.2f}] [EZ:x{opp['ez_coeff']:.2f}]")
        execute_trade(opp)
        return

def execute_trade(opportunity):
    # Sử dụng logic thực thi lệnh của Bản 2 vì nó gọn gàng hơn
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
    lot_size = calculate_lot_size(capital_base, adjusted_risk_pct, symbol, order_type, entry_price, sl_price)
    if lot_size <= 0: return logger.warning(f"Lot size = 0 cho {symbol}")
        
    risk_amount_usd = capital_base * (adjusted_risk_pct/100)
    result = connector.place_order(symbol, order_type, lot_size, sl_price, tp_price, magic_number=GENERAL_CONFIG["MAGIC_NUMBER"])
    
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        new_trade = {"trade_id": str(uuid.uuid4()), "ticket_id": result.order, "symbol": symbol, "type": tactic_cfg["TRADE_TYPE"], "entry_price": result.price, "lot_size": result.volume, "sl_price": sl_price, "tp_price": tp_price, "initial_sl": sl_price, "risk_amount_usd": risk_amount_usd, "opened_by_tactic": tactic_name, "entry_time": datetime.now(VIETNAM_TZ).isoformat(), "entry_score": score, "last_score": score, "entry_zone": zone, "last_zone": zone, "peak_pnl_percent": 0.0, "dca_entries": [], "partial_pnl_details": {}}
        state.setdefault("active_trades", []).append(new_trade)
        
        msg = f"🔥 MỞ LỆNH {symbol}\n"
        msg += f"Loại: **{tactic_cfg['TRADE_TYPE']}** | Tactic: **{tactic_name}**\n"
        msg += f"Entry: {format_price(result.price)} | SL: {format_price(sl_price)} | TP: {format_price(tp_price)}\n"
        msg += f"Lot: {lot_size} | Risk: ${risk_amount_usd:.2f} ({adjusted_risk_pct:.1f}%)\n"
        msg += f"Điểm: {score:.2f} | Zone: {zone}"
        send_discord_message(msg, force=True)
    else: 
        logger.error(f"Đặt lệnh thất bại. Retcode: {result.retcode if result else 'N/A'}")

def close_trade_on_mt5(trade, reason, close_pct=1.0):
    # Sử dụng hàm đóng lệnh của Bản 2 vì nó xử lý lot tối thiểu tốt hơn
    position = next((p for p in connector.get_all_open_positions() if p.ticket == trade['ticket_id']), None)
    if not position:
        logger.warning(f"Không tìm thấy vị thế #{trade['ticket_id']} để đóng ({reason})")
        return False
    
    lot_to_close = round(position.volume * close_pct, 2)
    info = mt5.symbol_info(trade['symbol'])
    if info and lot_to_close < info.volume_min:
        if close_pct < 1.0:
            logger.warning(f"Lot đóng một phần ({lot_to_close}) quá nhỏ. Sẽ đóng toàn bộ.")
            lot_to_close = position.volume
        else:
            return False
            
    result = connector.close_position(position, volume_to_close=lot_to_close, comment=f"exness_{reason}")
    if not result: return False
    
    tick = mt5.symbol_info_tick(trade['symbol'])
    exit_price = tick.bid if trade['type'] == "LONG" else tick.ask
    
    pnl_usd, pnl_percent = get_current_pnl(trade, exit_price)
    closed_pnl = pnl_usd * (lot_to_close / trade['lot_size']) if trade['lot_size'] > 0 else pnl_usd

    if lot_to_close >= trade['lot_size'] * 0.99: # Đóng toàn bộ
        trade.update({'status': f'Closed ({reason})', 'exit_price': exit_price, 'exit_time': datetime.now(VIETNAM_TZ).isoformat(), 'pnl_usd': closed_pnl, 'pnl_percent': pnl_percent})
        state['active_trades'] = [t for t in state['active_trades'] if t['trade_id'] != trade['trade_id']]
        state.setdefault('trade_history', []).append(trade)
        cooldown_map = state.setdefault('cooldown_until', {}); cooldown_map.setdefault(trade['symbol'], {})[GENERAL_CONFIG["MAIN_TIMEFRAME"]] = (datetime.now(VIETNAM_TZ) + timedelta(hours=GENERAL_CONFIG["TRADE_COOLDOWN_HOURS"])).isoformat()
        export_trade_to_csv(trade)
        icon = "✅" if closed_pnl >= 0 else "❌"
        send_discord_message(f"{icon} ĐÓNG LỆNH {trade['symbol']} ({reason}) | PnL: **${closed_pnl:.2f}**", force=True)
    else: # Đóng một phần
        trade['partial_pnl_details'][reason] = trade['partial_pnl_details'].get(reason, 0) + closed_pnl
        trade['lot_size'] = round(trade['lot_size'] - lot_to_close, 2)
        send_discord_message(f"💰 CHỐT LỜI {close_pct*100:.0f}% LỆNH {trade['symbol']} ({reason}) | PnL: **${closed_pnl:.2f}**", force=True)
    return True

def manage_open_positions():
    # Sử dụng logic quản lý lệnh mở của Bản 2 vì nó có buffer cho TSL và dời SL về entry khi TP1
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
                trail_dist = initial_risk_dist * tactic_cfg.get("TRAIL_DISTANCE_RR", 0.8)
                new_sl = current_price - trail_dist if trade['type'] == 'LONG' else current_price + trail_dist
                is_better = (new_sl > trade['sl_price']) if trade['type'] == 'LONG' else (new_sl < trade['sl_price'])
                if is_better and abs(new_sl - trade['sl_price']) > (initial_risk_dist * 0.1): # Anti-spam buffer
                    if connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price']):
                        trade['sl_price'] = new_sl
                        logger.info(f"TSL {symbol}: SL được cập nhật lên {format_price(new_sl)}")

            if tactic_cfg.get("ENABLE_PARTIAL_TP", False) and not trade.get("tp1_hit", False) and pnl_ratio >= tactic_cfg.get("TP1_RR_RATIO", 0.6):
                if close_trade_on_mt5(trade, "TP1", tactic_cfg.get("TP1_PROFIT_PCT", 0.5)):
                    trade['tp1_hit'] = True
                    new_sl = trade['entry_price'] # Dời SL về entry
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
    # Sử dụng logic của Bản 2
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
    # <<< MERGED: Khôi phục logic DCA chi tiết của Bản 1
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
        if (trade['type'] == 'LONG' and price_drop_pct > dca_trigger) or (trade['type'] == 'SHORT' and price_drop_pct < -dca_trigger):
            continue

        score_threshold = DCA_CONFIG["SCORE_MIN_THRESHOLD_LONG"] if trade['type'] == "LONG" else DCA_CONFIG["SCORE_MIN_THRESHOLD_SHORT"]
        if (trade['type'] == "LONG" and trade['last_score'] < score_threshold) or (trade['type'] == "SHORT" and trade['last_score'] > score_threshold):
            continue
            
        dca_lot_size = trade['lot_size'] * DCA_CONFIG["CAPITAL_MULTIPLIER"]
        order_type = mt5.ORDER_TYPE_BUY if trade['type'] == "LONG" else mt5.ORDER_TYPE_SELL
        
        # DCA không đặt SL/TP, sẽ gộp vào lệnh gốc
        result = connector.place_order(trade['symbol'], order_type, dca_lot_size, 0, 0, magic_number=GENERAL_CONFIG["MAGIC_NUMBER"])
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            trade['dca_entries'].append({"price": result.price, "lot_size": result.volume, "timestamp": now.isoformat()})
            
            # Tính lại giá trung bình và tổng lot
            all_entries = [{'price': trade['entry_price'], 'lot_size': trade.get('initial_lot_size', trade['lot_size'])}] + trade['dca_entries']
            total_lots = sum(e['lot_size'] for e in all_entries)
            avg_price = sum(e['price'] * e['lot_size'] for e in all_entries) / total_lots if total_lots > 0 else trade['entry_price']
            
            trade.update({'entry_price': avg_price, 'lot_size': total_lots, 'last_dca_time': now.isoformat()})
            send_discord_message(f"🎯 DCA {trade['symbol']}: Lot mới {dca_lot_size} @ {format_price(result.price)} | Giá TB mới: {format_price(avg_price)}", force=True)

def reconcile_positions():
    # Sử dụng logic của Bản 2
    logger.info("Đối soát vị thế...")
    bot_tickets = {t['ticket_id'] for t in state.get("active_trades", [])}
    mt5_tickets = {p.ticket for p in connector.get_all_open_positions() if p.magic == GENERAL_CONFIG["MAGIC_NUMBER"]}
    closed_manually = bot_tickets - mt5_tickets
    if closed_manually:
        for ticket in closed_manually: logger.warning(f"Vị thế #{ticket} đã đóng thủ công")
        closed_trades = [t for t in state["active_trades"] if t['ticket_id'] in closed_manually]
        for t in closed_trades: t.update({'status': 'Closed (Manual)', 'exit_time': datetime.now(VIETNAM_TZ).isoformat()}); state.setdefault("trade_history", []).append(t)
        state["active_trades"] = [t for t in state["active_trades"] if t['ticket_id'] not in closed_manually]

# ... Các hàm build_daily_summary, should_send_daily_report giữ nguyên của Bản 2 ...
def build_daily_summary():
    account_info = connector.get_account_info()
    if not account_info: return ""
    equity, balance = account_info['equity'], account_info['balance']
    initial_capital = state.get('initial_capital', balance)
    if initial_capital <= 0: initial_capital = balance
    pnl_total_usd = equity - initial_capital
    pnl_total_percent = (pnl_total_usd / initial_capital) * 100 if initial_capital > 0 else 0
    report = [f"📊 **BÁO CÁO TỔNG KẾT EXNESS BOT** - {datetime.now(VIETNAM_TZ).strftime('%H:%M %d-%m-%Y')}", f"💰 Vốn Nền tảng: **${initial_capital:,.2f}** | 💵 Balance: **${balance:,.2f}**", f"📊 Equity: **${equity:,.2f}** | 📈 PnL Tổng: **${pnl_total_usd:+,.2f} ({pnl_total_percent:+.2f}%)**", ""]
    active_trades = state.get('active_trades', [])
    if active_trades:
        report.append(f"--- **Vị thế đang mở ({len(active_trades)})** ---")
        for trade in active_trades:
            tick = mt5.symbol_info_tick(trade['symbol'])
            if tick:
                current_price = tick.bid if trade['type'] == "LONG" else tick.ask
                pnl_usd, pnl_percent = get_current_pnl(trade, current_price)
                icon = "🟢" if pnl_usd >= 0 else "🔴"
                holding_hours = (datetime.now(VIETNAM_TZ) - datetime.fromisoformat(trade['entry_time'])).total_seconds() / 3600
                report.append(f"  {icon} **{trade['symbol']}** ({trade['type']}) | PnL: **${pnl_usd:+.2f}** | Giữ: {holding_hours:.1f}h")
    else: report.append("Không có vị thế nào đang mở")
    return '\n'.join(report)

def should_send_daily_report():
    now_vn = datetime.now(VIETNAM_TZ)
    last_sent_str = state.get('last_summary_sent_time')
    if last_sent_str:
        last_sent = datetime.fromisoformat(last_sent_str).astimezone(VIETNAM_TZ)
    else: last_sent = None
    for time_str in GENERAL_CONFIG["DAILY_SUMMARY_TIMES"]:
        h, m = map(int, time_str.split(':'))
        scheduled = now_vn.replace(hour=h, minute=m, second=0, microsecond=0)
        if now_vn >= scheduled and (not last_sent or last_sent < scheduled): return True
    return False

# ==============================================================================
# ==================== VÒNG LẶP CHÍNH (TỪ BẢN 2) ====================
# ==============================================================================

def run_bot():
    global connector, state
    setup_logging()
    logger.info("=== KHỞI ĐỘNG EXNESS BOT V-HYBRID (MERGED) ===")
    connector = ExnessConnector()
    if not connector.connect(): return logger.critical("Không thể kết nối MT5!")
    if not acquire_lock(): return logger.info("Bot đang chạy ở phiên khác. Thoát.")
    
    try:
        load_state()
        if state.get('initial_capital', 0) <= 0:
            account_info = connector.get_account_info()
            if account_info:
                state['initial_capital'] = account_info['balance']
                save_state()

        last_heavy_task, last_reconciliation = 0, 0
        logger.info("Bot sẵn sàng. Bắt đầu vòng lặp chính...")
        
        while True:
            try:
                now = time.time()
                manage_open_positions()
                
                if now - last_heavy_task > GENERAL_CONFIG["HEAVY_TASK_INTERVAL_MINUTES"] * 60:
                    logger.info(f"--- Chạy tác vụ nặng ---")
                    last_heavy_task = now
                    load_all_indicators()
                    update_scores_for_active_trades()
                    manage_dynamic_capital() # <<< MERGED: Chạy Quản lý Vốn Động
                    find_and_open_new_trades()
                    handle_stale_trades()
                    handle_dca_opportunities()
                    save_state()
                    
                if now - last_reconciliation > GENERAL_CONFIG["RECONCILIATION_INTERVAL_MINUTES"] * 60:
                    reconcile_positions()
                    last_reconciliation = now
                    
                if should_send_daily_report():
                    send_discord_message(build_daily_summary(), force=True)
                    state['last_summary_sent_time'] = datetime.now(VIETNAM_TZ).isoformat()
                    save_state()
                    
                time.sleep(GENERAL_CONFIG["LOOP_SLEEP_SECONDS"])
            except KeyboardInterrupt: raise
            except Exception as e: 
                logger.error(f"Lỗi trong vòng lặp: {e}", exc_info=True)
                time.sleep(10)
    except KeyboardInterrupt: 
        logger.info("Nhận tín hiệu dừng...")
    except Exception as e: 
        logger.critical(f"LỖI NGHIÊM TRỌNG: {e}", exc_info=True)
    finally:
        save_state()
        release_lock()
        if connector: connector.shutdown()
        logger.info("=== BOT ĐÃ DỪNG ===")

if __name__ == "__main__":
    run_bot()