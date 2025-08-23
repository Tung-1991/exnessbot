# livetrade/live_trade_exness.py
# -*- coding: utf-8 -*-
import os
import sys
import time
import logging
import math
from datetime import datetime
from dotenv import load_dotenv
import MetaTrader5 as mt5

# --- THIẾT LẬP ĐƯỜNG DẪN ĐỂ IMPORT CHÍNH XÁC ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(dotenv_path=dotenv_path)

# Import các module từ thư mục gốc
from exness_connector import ExnessConnector
from indicator import calculate_indicators
from trade_advisor import get_advisor_decision, FULL_CONFIG as ADVISOR_CONFIG
from signal_logic import check_signal

# ==============================================================================
# ======================== ⚙️ TRUNG TÂM CẤU HÌNH ⚙️ =========================
# ==============================================================================
BOT_CONFIG = {
    "SYMBOL": "BTCUSD", "TIMEFRAME": "5m", "CANDLE_FETCH_COUNT": 300,
    "RISK_PER_TRADE_PERCENT": 1.0, "ENTRY_SCORE_THRESHOLD": 7.0,
    "ATR_SL_MULTIPLIER": 2.0, "RR_RATIO": 2.0, "MAX_OPEN_POSITIONS": 1
}

# ==============================================================================
# ======================== 🤖 LOGIC CHÍNH CỦA BOT 🤖 ========================
# ==============================================================================
def setup_logging():
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_filename = os.path.join(LOG_DIR, f"exness_bot_log_{datetime.now().strftime('%Y-%m-%d')}.log")
    logger = logging.getLogger("ExnessBot")
    logger.setLevel(logging.INFO)
    if logger.hasHandlers(): logger.handlers.clear()
    formatter = logging.Formatter(fmt="[%(asctime)s] [%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(log_filename, encoding='utf-8'); file_handler.setFormatter(formatter); logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler(); stream_handler.setFormatter(formatter); logger.addHandler(stream_handler)
    return logger

def calculate_lot_size(account_equity, risk_percent, symbol, entry_price, sl_price, order_type):
    if entry_price == sl_price: return 0.0
    risk_amount_usd = account_equity * (risk_percent / 100)
    loss_for_one_lot = mt5.order_calc_loss(order_type, symbol, 1.0, entry_price, sl_price)
    if not loss_for_one_lot or abs(loss_for_one_lot) < 0.01: return 0.0
    lot_size = risk_amount_usd / abs(loss_for_one_lot)
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info: return 0.0
    volume_step = symbol_info.volume_step
    lot_size_rounded = math.floor(lot_size / volume_step) * volume_step
    return round(lot_size_rounded, 2)

def run_bot():
    logger = setup_logging()
    logger.info("--- Khoi dong RiceAlert Exness Bot ---")

    SYMBOL = BOT_CONFIG['SYMBOL']
    TIMEFRAME = BOT_CONFIG['TIMEFRAME']
    
    # SỬA LỖI: Khởi tạo connector không cần tham số
    connector = ExnessConnector()
    if not connector.connect():
        logger.critical("!!! Bot dung do khong the ket noi toi MT5. !!!"); return

    logger.info(f"Cau hinh: Symbol=[{SYMBOL}], Timeframe=[{TIMEFRAME}], Risk/Trade=[{BOT_CONFIG['RISK_PER_TRADE_PERCENT']}%]")
    
    last_processed_candle_time = datetime.min
    
    try:
        while True:
            # SỬA LỖI: Gọi hàm get_open_positions từ connector instance
            active_positions = connector.get_open_positions(symbol=SYMBOL)
            
            # Quản lý lệnh tick-by-tick sẽ được thêm ở bước sau
            
            current_candles = connector.get_historical_data(SYMBOL, TIMEFRAME, 2)
            if current_candles is None or len(current_candles) < 2:
                time.sleep(5); continue

            latest_candle_time = current_candles.index[-1]
            if latest_candle_time > last_processed_candle_time:
                logger.info(f"Phat hien nen {TIMEFRAME} moi: {latest_candle_time}")
                last_processed_candle_time = latest_candle_time

                if len(active_positions) < BOT_CONFIG['MAX_OPEN_POSITIONS']:
                    historical_data = connector.get_historical_data(SYMBOL, TIMEFRAME, BOT_CONFIG['CANDLE_FETCH_COUNT'])
                    if historical_data is not None:
                        indicators = calculate_indicators(historical_data, SYMBOL, TIMEFRAME)
                        decision = get_advisor_decision(SYMBOL, TIMEFRAME, indicators, ADVISOR_CONFIG)
                        
                        final_score = decision.get('final_score', 0.0)
                        logger.info(f"-> Phan tich xong: Diem cuoi cung={final_score:.2f} | Quyet dinh={decision.get('decision_type')}")

                        if abs(final_score) >= BOT_CONFIG['ENTRY_SCORE_THRESHOLD']:
                            logger.info(f"*** Tin hieu dat nguong! Bat dau quy trinh vao lenh... ***")
                            account_info = connector.get_account_info()
                            entry_price = indicators.get('price')
                            atr = indicators.get('atr')
                            
                            if account_info and entry_price and atr:
                                equity = account_info.get('equity')
                                risk_distance = atr * BOT_CONFIG['ATR_SL_MULTIPLIER']
                                order_type = mt5.ORDER_TYPE_BUY if final_score > 0 else mt5.ORDER_TYPE_SELL
                                sl_price = entry_price - risk_distance if order_type == mt5.ORDER_TYPE_BUY else entry_price + risk_distance
                                tp_price = entry_price + (risk_distance * BOT_CONFIG['RR_RATIO']) if order_type == mt5.ORDER_TYPE_BUY else entry_price - (risk_distance * BOT_CONFIG['RR_RATIO'])
                                lot_size = calculate_lot_size(account_equity=equity, risk_percent=BOT_CONFIG['RISK_PER_TRADE_PERCENT'], symbol=SYMBOL, entry_price=entry_price, sl_price=sl_price, order_type=order_type)
                                
                                if lot_size > 0:
                                    logger.info(f"-> GUI LENH: Type={'BUY' if order_type == 0 else 'SELL'}, Lot={lot_size}, SL={sl_price:,.2f}, TP={tp_price:,.2f}")
                                    connector.place_order(SYMBOL, order_type, lot_size, sl_price, tp_price)

            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Da nhan tin hieu dung bot...")
    finally:
        connector.shutdown()
        logger.info("--- Bot da dung hoat dong ---")

if __name__ == "__main__":
    run_bot()