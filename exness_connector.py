import MetaTrader5 as mt5
import os
import pandas as pd
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Lấy logger được cấu hình bởi file chính, nếu không có thì tạo logger cơ bản
logger = logging.getLogger("ExnessBot")
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] - %(message)s")

class ExnessConnector:
    def __init__(self):
        load_dotenv()
        self._is_connected = False
        self._timeframe_mapping = {
            '1m': mt5.TIMEFRAME_M1, '5m': mt5.TIMEFRAME_M5, '15m': mt5.TIMEFRAME_M15,
            '30m': mt5.TIMEFRAME_M30, '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1,
        }
        logger.info("Exness Connector khởi tạo. Sẵn sàng kết nối tới terminal MT5 đang chạy...")

    def connect(self):
        if self._is_connected:
            return True
        logger.info("Đang tìm và kết nối tới terminal MetaTrader 5...")
        try:
            if not mt5.initialize():
                logger.error(f"Lỗi initialize(): {mt5.last_error()}")
                return False
            account_info = mt5.account_info()
            if not account_info:
                logger.error(f"Không thể lấy thông tin tài khoản: {mt5.last_error()}")
                mt5.shutdown()
                return False
            logger.info(f"Đã kết nối thành công tới tài khoản #{account_info.login} trên server {account_info.server}")
            self._is_connected = True
            return True
        except Exception as e:
            logger.critical(f"Lỗi ngoại lệ khi kết nối: {e}", exc_info=True)
            return False

    def shutdown(self):
        if self._is_connected:
            logger.info("Đang đóng kết nối MetaTrader 5...")
            mt5.shutdown()
            self._is_connected = False

    def get_account_info(self):
        if not self._is_connected: return None
        info = mt5.account_info()
        return info._asdict() if info else None

    def get_historical_data(self, symbol, timeframe, count):
        if not self._is_connected: return None
        mt5_timeframe = self._timeframe_mapping.get(timeframe)
        if not mt5_timeframe:
            logger.error(f"Lỗi: Khung thời gian '{timeframe}' không được hỗ trợ.")
            return None
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.rename(columns={'time': 'timestamp', 'tick_volume': 'volume'}, inplace=True)
            df.set_index('timestamp', inplace=True)
            return df[['open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            logger.error(f"Lỗi ngoại lệ khi lấy dữ liệu lịch sử: {e}", exc_info=True)
            return None

    def get_open_positions(self, symbol):
        if not self._is_connected: return []
        positions = mt5.positions_get(symbol=symbol)
        return positions if positions else []

    def place_order(self, symbol, order_type, lot_size, sl_price, tp_price, magic_number=202508):
        if not self._is_connected: return None
        price = mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot_size,
            "type": order_type, "price": price, "sl": sl_price, "tp": tp_price,
            "magic": magic_number, "comment": "ricealert_v1",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh {symbol} đã được đặt thành công. Ticket: {result.order}")
            return result
        logger.error(f"❌ Đặt lệnh {symbol} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None

    def close_position(self, position, comment="ricealert_close"):
        if not self._is_connected: return None
        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": position.symbol, "volume": position.volume,
            "type": order_type, "position": position.ticket, "price": price, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh đóng cho ticket #{position.ticket} đã được gửi thành công.")
            return result
        logger.error(f"❌ Đóng lệnh cho ticket #{position.ticket} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None

    # --- CÁC HÀM MỚI ĐƯỢC THÊM VÀO ---
    def get_all_open_positions(self):
        if not self._is_connected: return []
        positions = mt5.positions_get()
        return positions if positions else []

    def calculate_loss(self, symbol, order_type, volume, entry_price, sl_price):
        if not self._is_connected: return None
        # MT5 tính loss là một số âm, nên ta lấy giá trị tuyệt đối
        loss = mt5.order_calc_loss(order_type, symbol, volume, entry_price, sl_price)
        return abs(loss) if loss is not None else None

    def modify_position(self, ticket_id, sl_price, tp_price):
        if not self._is_connected: return None
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket_id,
            "sl": float(sl_price),
            "tp": float(tp_price),
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Sửa lệnh #{ticket_id} thành công. SL mới: {sl_price}, TP mới: {tp_price}")
            return True
        logger.error(f"Sửa lệnh #{ticket_id} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return False

if __name__ == "__main__":
    connector = ExnessConnector()
    if connector.connect():
        SYMBOL = "BTCUSD"
        LOT_SIZE = 0.01
        logger.info(f"\n--- Thử nghiệm đặt lệnh {LOT_SIZE} lot {SYMBOL} ---")
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick:
            current_price = tick.ask
            sl_demo = current_price - 1000
            tp_demo = current_price + 2000
            buy_result = connector.place_order(SYMBOL, mt5.ORDER_TYPE_BUY, LOT_SIZE, sl_demo, tp_demo)
            if buy_result:
                time.sleep(5)
                positions = connector.get_all_open_positions()
                found_position = next((p for p in positions if p.ticket == buy_result.order), None)
                if found_position:
                    logger.info(f"--- Tìm thấy vị thế (Ticket: {found_position.ticket}). Thử nghiệm sửa lệnh ---")
                    new_sl = sl_demo + 100
                    connector.modify_position(found_position.ticket, new_sl, tp_demo)
                    time.sleep(2)
                    logger.info(f"--- Thử nghiệm đóng lệnh ---")
                    connector.close_position(found_position)
                else:
                    logger.warning("Không tìm thấy vị thế vừa mở để thử nghiệm.")
        else:
            logger.error("Không thể lấy giá tick hiện tại của BTCUSD để thử nghiệm.")
        connector.shutdown()