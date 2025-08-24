# -*- coding: utf-8 -*-
import os
import sys
import json
import uuid
import time
import logging
import math
import pytz
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# --- THIẾT LẬP ĐƯỜNG DẪN VÀ IMPORT ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(PROJECT_ROOT))
dotenv_path = os.path.join(os.path.dirname(PROJECT_ROOT), '.env')
load_dotenv(dotenv_path=dotenv_path)

from exness_connector import ExnessConnector
from indicator import calculate_indicators
from signal_logic import check_signal
from trade_advisor import get_advisor_decision
import MetaTrader5 as mt5

# ==============================================================================
# ======================== ⚙️ TRUNG TÂM CẤU HÌNH ⚙️ =========================
# ==============================================================================
# --- CẤU HÌNH CHUNG ---
GENERAL_CONFIG = {
    "SYMBOLS_TO_SCAN": ["ETHUSD"],
    "TIMEFRAME": "5m",
    "LOOP_SLEEP_SECONDS": 1,
    "HEAVY_TASK_INTERVAL_MINUTES": 5,
    "RECONCILIATION_INTERVAL_MINUTES": 5,
    "CANDLE_FETCH_COUNT": 300,
    "TOP_N_OPPORTUNITIES_TO_CHECK": 3,
}
# --- QUẢN LÝ VỐN & RỦI RO ---
RISK_MANAGEMENT_CONFIG = {
    "RISK_PER_TRADE_PERCENT": 1.0,
    "MAX_ACTIVE_TRADES": 5,
    "MIN_ORDER_VALUE_USD": 10.0,
}
# --- CHIẾN LƯỢC GIAO DỊCH (TACTICS & ZONES) ---
ZONE_BASED_POLICIES = {
    "LEADING": {"NOTES": "Dò mìn cơ hội tiềm năng.", "CAPITAL_RISK_MULTIPLIER": 0.8},
    "COINCIDENT": {"NOTES": "Vùng tốt nhất, quyết đoán vào lệnh.", "CAPITAL_RISK_MULTIPLIER": 1.2},
    "LAGGING": {"NOTES": "An toàn, đi theo trend đã rõ.", "CAPITAL_RISK_MULTIPLIER": 1.0},
    "NOISE": {"NOTES": "Nguy hiểm, giảm rủi ro.", "CAPITAL_RISK_MULTIPLIER": 0.5}
}
TACTICS_LAB = {
    # --- 5 TACTICS LONG ---
    "Balanced_Trader_L": {"OPTIMAL_ZONE": ["LAGGING", "COINCIDENT"], "ENTRY_SCORE": 6.3, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.6},
    "Breakout_Hunter_L": {"OPTIMAL_ZONE": ["LEADING", "COINCIDENT"], "ENTRY_SCORE": 7.0, "RR": 1.7, "ATR_SL_MULTIPLIER": 2.4},
    "Dip_Hunter_L": {"OPTIMAL_ZONE": ["LEADING", "COINCIDENT"], "ENTRY_SCORE": 6.8, "RR": 1.4, "ATR_SL_MULTIPLIER": 3.2},
    "AI_Aggressor_L": {"OPTIMAL_ZONE": ["COINCIDENT"], "ENTRY_SCORE": 6.6, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.2},
    "Cautious_Observer_L": {"OPTIMAL_ZONE": "NOISE", "ENTRY_SCORE": 8.0, "RR": 1.4, "ATR_SL_MULTIPLIER": 1.8},
    # --- 5 TACTICS SHORT (Đối xứng) ---
    "Balanced_Seller_S": {"OPTIMAL_ZONE": ["LAGGING", "COINCIDENT"], "ENTRY_SCORE": -6.3, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.6},
    "Breakdown_Hunter_S": {"OPTIMAL_ZONE": ["LEADING", "COINCIDENT"], "ENTRY_SCORE": -7.0, "RR": 1.7, "ATR_SL_MULTIPLIER": 2.4},
    "Rally_Seller_S": {"OPTIMAL_ZONE": ["LEADING", "COINCIDENT"], "ENTRY_SCORE": -6.8, "RR": 1.4, "ATR_SL_MULTIPLIER": 3.2},
    "AI_Contrarian_S": {"OPTIMAL_ZONE": ["COINCIDENT"], "ENTRY_SCORE": -6.6, "RR": 1.5, "ATR_SL_MULTIPLIER": 2.2},
    "Cautious_Shorted_S": {"OPTIMAL_ZONE": "NOISE", "ENTRY_SCORE": -8.0, "RR": 1.4, "ATR_SL_MULTIPLIER": 1.8},
}
# --- QUẢN LÝ LỆNH ĐANG MỞ ---
ACTIVE_TRADE_MANAGEMENT_CONFIG = {
    "EARLY_CLOSE_SCORE_THRESHOLD_LONG": 4.0,
    "EARLY_CLOSE_SCORE_THRESHOLD_SHORT": -4.0,
    "ENABLE_TRAILING_STOP": True,
    "TRAIL_ACTIVATION_RR": 1.2,
    "TRAIL_DISTANCE_RR": 0.8,
}
# --- DCA CONFIG ---
DCA_CONFIG = {
    "ENABLED": True,
    "MAX_DCA_ENTRIES": 2,
    "TRIGGER_DROP_PERCENT": -3.0, # Phần trăm giá đi ngược để kích hoạt DCA
    "SCORE_THRESHOLD_LONG": 6.5,
    "SCORE_THRESHOLD_SHORT": -6.5,
    "CAPITAL_MULTIPLIER": 1.5, # Lần DCA sau sẽ vào vốn gấp 1.5 lần lệnh trước
}
# --- DISCORD & LOGGING ---
DISCORD_CONFIG = {
    "WEBHOOK_URL": os.getenv("DISCORD_LIVE_WEBHOOK"),
    "REPORT_SCHEDULE_HOURS": [8, 20], # Gửi báo cáo vào 8h và 20h
    "ERROR_COOLDOWN_MINUTES": 30
}
# ==============================================================================
# ======================== BIẾN TOÀN CỤC & HẰNG SỐ =========================
# ==============================================================================
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOG_DIR = os.path.join(DATA_DIR, "logs")
STATE_FILE = os.path.join(DATA_DIR, "exness_state.json")
os.makedirs(LOG_DIR, exist_ok=True)
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
logger = None
connector = None
# ==============================================================================
# =========================== HÀM TIỆN ÍCH ============================
# ==============================================================================
def setup_logging():
    global logger
    log_filename = os.path.join(LOG_DIR, f"bot_log_{datetime.now().strftime('%Y-%m-%d')}.log")
    error_filename = os.path.join(LOG_DIR, f"error_log_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    # Lấy logger và quan trọng nhất là XÓA TẤT CẢ HANDLER CŨ
    logger = logging.getLogger("ExnessBot")
    logger.setLevel(logging.INFO)

    # === DÒNG SỬA LỖI QUAN TRỌNG NHẤT ===
    logger.propagate = False
    # ====================================

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(fmt="[%(asctime)s] [%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    # Handler để lưu log INFO và cao hơn vào file bot_log
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Handler để chỉ lưu log ERROR và cao hơn vào file error_log
    error_handler = logging.FileHandler(error_filename, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # Handler để hiển thị log trên màn hình terminal
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(stream_handler)

def load_state():
    if not os.path.exists(STATE_FILE): return {"active_trades": [], "trade_history": [], "bot_settings": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.error("Lỗi đọc file state.json hoặc file không tồn tại. Bắt đầu với state mới.")
        return {"active_trades": [], "trade_history": [], "bot_settings": {}}

def save_state(state):
    temp_path = STATE_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f: json.dump(state, f, indent=4)
    os.replace(temp_path, STATE_FILE)

# (Các hàm gửi Discord và xây dựng báo cáo sẽ được thêm vào đây sau)
# ==============================================================================
# =========================== LOGIC CỐT LÕI ============================
# ==============================================================================
def calculate_lot_size(equity, risk_percent, symbol, order_type, entry_price, sl_price):
    if entry_price == sl_price: return 0.0
    risk_amount_usd = equity * (risk_percent / 100)
    loss_for_one_lot = connector.calculate_loss(symbol, order_type, 1.0, entry_price, sl_price)
    if not loss_for_one_lot or abs(loss_for_one_lot) < 0.01:
        logger.error(f"Không thể tính toán PnL cho {symbol}, có thể do thông tin symbol không có.")
        return 0.0
    
    lot_size = risk_amount_usd / abs(loss_for_one_lot)
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info: return 0.0
    
    volume_step = symbol_info.volume_step
    lot_size_rounded = math.floor(lot_size / volume_step) * volume_step
    
    if lot_size_rounded < symbol_info.volume_min: return 0.0
    return round(lot_size_rounded, 2)

def determine_market_zone(indicators: dict) -> str:
    # Logic đơn giản hóa, có thể mở rộng sau
    adx = indicators.get('adx', 20)
    bb_width = indicators.get('bb_width', 0.05)
    if adx < 20 and bb_width < 0.03: return "NOISE"
    if adx > 25: return "LAGGING"
    return "COINCIDENT"

# Dán đoạn code này để thay thế cho hàm find_and_open_new_trade cũ

def find_and_open_new_trade(state: Dict):
    if len(state.get("active_trades", [])) >= RISK_MANAGEMENT_CONFIG["MAX_ACTIVE_TRADES"]:
        return

    potential_opportunities = []
    for symbol in GENERAL_CONFIG["SYMBOLS_TO_SCAN"]:
        if any(t['symbol'] == symbol for t in state.get("active_trades", [])): continue
        
        dataframe = connector.get_historical_data(symbol, GENERAL_CONFIG["TIMEFRAME"], GENERAL_CONFIG["CANDLE_FETCH_COUNT"])
        if dataframe is None or dataframe.empty:
            logger.warning(f"Không có dữ liệu nến cho {symbol}, bỏ qua quét.")
            continue
        
        indicators = calculate_indicators(dataframe, symbol, GENERAL_CONFIG["TIMEFRAME"])
        signal = check_signal(indicators)
        decision = get_advisor_decision(signal)
        
        final_score = decision.get('final_score', 0.0)
        if final_score == 0: continue # Bỏ qua các tín hiệu trung lập

        trade_type = "LONG" if final_score > 0 else "SHORT"
        
        # (Phần logic Zone sẽ được thêm sau, hiện tại quét tất cả Tactic)
        for tactic_name, tactic_cfg in TACTICS_LAB.items():
            is_long_tactic = tactic_name.endswith("_L")
            is_short_tactic = tactic_name.endswith("_S")
            
            if (trade_type == "LONG" and not is_long_tactic) or (trade_type == "SHORT" and not is_short_tactic): continue
            
            potential_opportunities.append({
                "symbol": symbol, "score": final_score, "tactic_name": tactic_name, 
                "tactic_cfg": tactic_cfg, "indicators": indicators, "decision": decision
            })
    
    if not potential_opportunities:
        logger.info("Không tìm thấy cơ hội giao dịch tiềm năng nào trong chu kỳ này.")
        return

    # --- BẮT ĐẦU LOGIC LOG MỚI ---
    sorted_opportunities = sorted(potential_opportunities, key=lambda x: abs(x['score']), reverse=True)
    top_opportunities = sorted_opportunities[:GENERAL_CONFIG["TOP_N_OPPORTUNITIES_TO_CHECK"]]
    
    logger.info(f"---[🏆 Xem xét {len(top_opportunities)} cơ hội hàng đầu (tối đa {GENERAL_CONFIG['TOP_N_OPPORTUNITIES_TO_CHECK']})] ---")
    
    executable_opportunity = None
    
    for i, opportunity in enumerate(top_opportunities):
        symbol = opportunity['symbol']
        tactic_name = opportunity['tactic_name']
        tactic_cfg = opportunity['tactic_cfg']
        final_score = opportunity['score']
        entry_threshold = tactic_cfg.get("ENTRY_SCORE", 99)
        
        # (Ghi chú: Phần `(MTF x...)` chúng ta sẽ thêm vào sau khi tích hợp logic Phân tích Đa khung thời gian)
        log_line = f"  #{i+1}: {symbol}-{GENERAL_CONFIG['TIMEFRAME']} | Tactic: {tactic_name} | Điểm: {final_score:.2f} (Ngưỡng: {entry_threshold})"
        
        passes_threshold = (final_score >= entry_threshold) if final_score > 0 else (final_score <= entry_threshold)
        
        if passes_threshold:
            log_line += "\n      => ✅ Đạt ngưỡng! Chọn cơ hội này."
            logger.info(log_line)
            executable_opportunity = opportunity
            break # Dừng lại ngay khi tìm thấy cơ hội tốt nhất đạt ngưỡng
        else:
            log_line += "\n      => 📉 Không đạt ngưỡng. Xem xét cơ hội tiếp theo..."
            logger.info(log_line)

    if not executable_opportunity:
        logger.info("=> Không có cơ hội nào trong top đạt ngưỡng vào lệnh. Chờ chu kỳ sau.")
        return
    # --- KẾT THÚC LOGIC LOG MỚI ---

    # --- Bắt đầu quy trình vào lệnh cho cơ hội đã chọn ---
    symbol = executable_opportunity['symbol']
    tactic_cfg = executable_opportunity['tactic_cfg']
    indicators = executable_opportunity['indicators']
    score = executable_opportunity['score']
    tactic_name = executable_opportunity['tactic_name']

    logger.info(f"*** THỰC THI CƠ HỘI TỐT NHẤT: {symbol} | Tactic: {tactic_name} | Điểm: {score:.2f} ***")

    account_info = connector.get_account_info()
    if not account_info:
        logger.error("Không thể lấy thông tin tài khoản để vào lệnh.")
        return

    equity = account_info['equity']
    order_type = mt5.ORDER_TYPE_BUY if score > 0 else mt5.ORDER_TYPE_SELL
    
    tick = mt5.symbol_info_tick(symbol)
    if not tick: 
        logger.error(f"Không thể lấy giá tick cho {symbol}.")
        return
    entry_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

    risk_dist_atr = indicators.get('atr', 0) * tactic_cfg.get("ATR_SL_MULTIPLIER", 2.0)
    if risk_dist_atr == 0:
        logger.warning(f"ATR bằng 0 cho {symbol}, không thể tính SL. Bỏ qua cơ hội.")
        return

    sl_price = entry_price - risk_dist_atr if order_type == mt5.ORDER_TYPE_BUY else entry_price + risk_dist_atr
    tp_price = entry_price + (risk_dist_atr * tactic_cfg.get("RR", 1.5)) if order_type == mt5.ORDER_TYPE_BUY else entry_price - (risk_dist_atr * tactic_cfg.get("RR", 1.5))
    
    lot_size = calculate_lot_size(equity, RISK_MANAGEMENT_CONFIG["RISK_PER_TRADE_PERCENT"], symbol, order_type, entry_price, sl_price)
    
    if lot_size > 0:
        logger.info(f"-> Chuẩn bị gửi lệnh: {'BUY' if order_type == 0 else 'SELL'} {lot_size} lot {symbol} @ {entry_price:.4f} | SL: {sl_price:.4f} | TP: {tp_price:.4f}")
        result = connector.place_order(symbol, order_type, lot_size, sl_price, tp_price)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh được đặt thành công. Ticket: {result.order}")
            new_trade = {
                "trade_id": str(uuid.uuid4()), "ticket_id": result.order, "symbol": symbol,
                "type": "LONG" if order_type == mt5.ORDER_TYPE_BUY else "SHORT",
                "entry_price": result.price, "lot_size": result.volume,
                "sl_price": result.sl, "tp_price": result.tp,
                "opened_by_tactic": tactic_name, "entry_time": datetime.now(timezone.utc).isoformat(),
                "entry_score": score, "last_score": score, "trailing_stop_activated": False
            }
            state.setdefault("active_trades", []).append(new_trade)
            save_state(state)
        else:
            logger.error(f"❌ Đặt lệnh thất bại. Retcode: {result.retcode if result else 'N/A'}. Lý do: {result.comment if result else 'Không rõ'}")
    else:
        logger.warning("Lot size tính toán ra bằng 0. Không vào lệnh.")


def manage_open_positions(state: Dict):
    active_trades = state.get("active_trades", [])
    if not active_trades: return
    
    for trade in active_trades[:]: # Lặp trên một bản copy để có thể xóa
        symbol = trade['symbol']
        tick = mt5.symbol_info_tick(symbol)
        if not tick: continue
        
        trade_type = trade['type']
        current_price = tick.bid if trade_type == "LONG" else tick.ask # Giá để đóng lệnh
        
        # --- LOGIC TRAILING STOP ---
        if ACTIVE_TRADE_MANAGEMENT_CONFIG["ENABLE_TRAILING_STOP"] and not trade.get('trailing_stop_activated'):
            initial_risk_dist = abs(trade['entry_price'] - trade['sl_price'])
            if initial_risk_dist == 0: continue
            
            pnl_ratio = 0
            if trade_type == "LONG":
                pnl_ratio = (current_price - trade['entry_price']) / initial_risk_dist
            else: # SHORT
                pnl_ratio = (trade['entry_price'] - current_price) / initial_risk_dist
            
            if pnl_ratio >= ACTIVE_TRADE_MANAGEMENT_CONFIG["TRAIL_ACTIVATION_RR"]:
                trade['trailing_stop_activated'] = True
                logger.info(f"Trailing Stop được kích hoạt cho lệnh {symbol} ticket #{trade['ticket_id']}")
        
        if trade.get('trailing_stop_activated'):
            initial_risk_dist = abs(trade['entry_price'] - trade['sl_price'])
            trail_dist = initial_risk_dist * ACTIVE_TRADE_MANAGEMENT_CONFIG["TRAIL_DISTANCE_RR"]
            new_sl = 0
            
            if trade_type == "LONG" and current_price - trail_dist > trade['sl_price']:
                new_sl = current_price - trail_dist
            elif trade_type == "SHORT" and current_price + trail_dist < trade['sl_price']:
                new_sl = current_price + trail_dist
            
            if new_sl != 0:
                logger.info(f"Cập nhật Trailing Stop cho {symbol} #{trade['ticket_id']}: SL mới {new_sl:.4f}")
                result = connector.modify_position(trade['ticket_id'], new_sl, trade['tp_price'])
                if result:
                    trade['sl_price'] = new_sl # Cập nhật lại state
                    save_state(state)

def reconcile_positions(state: Dict):
    logger.info("Bắt đầu đối soát vị thế giữa bot và MT5...")
    bot_tickets = {t['ticket_id'] for t in state.get("active_trades", [])}
    mt5_positions = connector.get_all_open_positions()
    mt5_tickets = {p.ticket for p in mt5_positions}
    
    # Tìm lệnh bot nghĩ là đang mở nhưng thực tế đã đóng
    closed_manually_tickets = bot_tickets - mt5_tickets
    if closed_manually_tickets:
        for ticket in closed_manually_tickets:
            logger.warning(f"Đối soát: Vị thế ticket #{ticket} đã bị đóng thủ công trên MT5. Đang cập nhật trạng thái...")
        
        original_trades = state["active_trades"]
        state["active_trades"] = [t for t in original_trades if t['ticket_id'] not in closed_manually_tickets]
        
        closed_trades = [t for t in original_trades if t['ticket_id'] in closed_manually_tickets]
        for t in closed_trades:
            t['status'] = 'Closed (Reconciled)'
            t['exit_time'] = datetime.now(timezone.utc).isoformat()
            state.setdefault("trade_history", []).append(t)
        
        save_state(state)
        logger.info(f"Đã dọn dẹp {len(closed_manually_tickets)} vị thế không đồng bộ.")
    else:
        logger.info("Tất cả vị thế đều đồng bộ.")

# ==============================================================================
# ======================== VÒNG LẶP CHÍNH CỦA BOT =========================
# ==============================================================================
def run_bot():
    global connector
    setup_logging()
    logger.info("--- KHỞI ĐỘNG EXNESS TRADE BOT V1.0 ---")
    
    connector = ExnessConnector()
    if not connector.connect():
        logger.critical("!!! BOT DỪNG DO KHÔNG THỂ KẾT NỐI TỚI MT5 !!!")
        return
        
    state = load_state()
    last_heavy_task_time = 0
    last_reconciliation_time = 0
    
    try:
        while True:
            now = time.time()
            
            # TÁC VỤ NHANH: Luôn chạy để quản lý lệnh
            manage_open_positions(state)

            # TÁC VỤ NẶNG: Chạy định kỳ
            if now - last_heavy_task_time > GENERAL_CONFIG["HEAVY_TASK_INTERVAL_MINUTES"] * 60:
                logger.info(f"--- Bắt đầu chu kỳ tác vụ nặng ({GENERAL_CONFIG['HEAVY_TASK_INTERVAL_MINUTES']} phút) ---")
                last_heavy_task_time = now
                
                # Đối soát vị thế
                if now - last_reconciliation_time > GENERAL_CONFIG["RECONCILIATION_INTERVAL_MINUTES"] * 60:
                    reconcile_positions(state)
                    last_reconciliation_time = now
                
                # Tìm cơ hội mới
                find_and_open_new_trade(state)
                
                # (Gửi báo cáo Discord định kỳ sẽ được thêm vào đây)
                logger.info("--- Kết thúc chu kỳ tác vụ nặng ---")

            time.sleep(GENERAL_CONFIG["LOOP_SLEEP_SECONDS"])
            
    except KeyboardInterrupt:
        logger.info("Đã nhận tín hiệu dừng bot...")
    except Exception as e:
        logger.critical(f"LỖI TOÀN CỤC NGOÀI DỰ KIẾN: {e}", exc_info=True)
    finally:
        connector.shutdown()
        save_state(state)
        logger.info("--- BOT ĐÃ DỪNG HOẠT ĐỘNG ---")

if __name__ == "__main__":
    run_bot()