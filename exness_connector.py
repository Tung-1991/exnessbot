# exness_connector.py

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
                logger.warning(f"Không có dữ liệu lịch sử cho {symbol} trên khung {timeframe}.")
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.rename(columns={'time': 'timestamp', 'tick_volume': 'volume'}, inplace=True)
            df.set_index('timestamp', inplace=True)
            return df[['open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            logger.error(f"Lỗi ngoại lệ khi lấy dữ liệu lịch sử cho {symbol}: {e}", exc_info=True)
            return None

    def get_all_open_positions(self):
        if not self._is_connected: return []
        positions = mt5.positions_get()
        return positions if positions else []

    def place_order(self, symbol, order_type, lot_size, sl_price, tp_price, magic_number=202508):
        if not self._is_connected: return None
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Không thể lấy giá tick cho {symbol} để đặt lệnh.")
            return None
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot_size,
            "type": order_type, "price": price, "sl": sl_price, "tp": tp_price,
            "magic": magic_number, "comment": "exness_bot_v2",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh {symbol} đã được đặt thành công. Ticket: {result.order}")
            return result
        logger.error(f"❌ Đặt lệnh {symbol} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None

    def close_position(self, position, volume_to_close=None, comment="exness_bot_close"):
        if not self._is_connected: return None
        tick = mt5.symbol_info_tick(position.symbol)
        if not tick:
            logger.error(f"Không thể lấy giá tick cho {position.symbol} để đóng lệnh.")
            return None
        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask
        volume = volume_to_close if volume_to_close is not None and volume_to_close > 0 else position.volume
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": position.symbol, "volume": volume,
            "type": order_type, "position": position.ticket, "price": price, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh đóng {volume} lot cho ticket #{position.ticket} đã được gửi thành công.")
            return result
        logger.error(f"❌ Đóng lệnh cho ticket #{position.ticket} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None

    def modify_position(self, ticket_id, sl_price, tp_price):
        if not self._is_connected: return None
        request = {
            "action": mt5.TRADE_ACTION_SLTP, "position": ticket_id,
            "sl": float(sl_price), "tp": float(tp_price),
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Sửa lệnh #{ticket_id} thành công. SL mới: {sl_price:.5f}, TP mới: {tp_price:.5f}")
            return True
        logger.error(f"Sửa lệnh #{ticket_id} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return False

    def calculate_profit(self, symbol, order_type, volume, entry_price, current_price):
        if not self._is_connected: return None
        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type == "LONG" else mt5.ORDER_TYPE_SELL
        profit = mt5.order_calc_profit(mt5_order_type, symbol, volume, entry_price, current_price)
        return profit if profit is not None else None

    def calculate_lot_size(self, symbol, risk_amount_usd, sl_price):
        """Tính toán lot size chính xác dựa trên số tiền rủi ro và khoảng cách stop loss."""
        if not self._is_connected: return None
        try:
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                logger.error(f"Không thể lấy thông tin symbol {symbol}")
                return None

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                logger.error(f"Không thể lấy giá tick của {symbol}")
                return None
            
            # Sử dụng giá ASK cho lệnh BUY, giá BID cho lệnh SELL để tính toán
            entry_price = tick.ask 
            order_type = mt5.ORDER_TYPE_BUY
            if sl_price > entry_price: # Nếu SL > giá vào lệnh, đây là lệnh SELL
                 entry_price = tick.bid
                 order_type = mt5.ORDER_TYPE_SELL

            if abs(entry_price - sl_price) == 0:
                logger.error(f"Giá vào lệnh và giá SL bằng nhau cho {symbol}")
                return None

            # Tính toán mức lỗ cho 1.0 lot dựa trên hàm của MT5 (chính xác nhất)
            loss_per_lot = mt5.order_calc_loss(order_type, symbol, 1.0, entry_price, sl_price)
            if loss_per_lot is None or loss_per_lot <= 0:
                logger.error(f"Không thể tính toán mức lỗ cho 1 lot của {symbol}.")
                return None

            # Tính lot size thô
            lot_size = risk_amount_usd / abs(loss_per_lot)

            # Làm tròn và kiểm tra các giới hạn của sàn
            min_vol, max_vol, vol_step = symbol_info.volume_min, symbol_info.volume_max, symbol_info.volume_step
            
            lot_size = round(lot_size / vol_step) * vol_step # Làm tròn theo bước khối lượng
            lot_size = round(lot_size, 2) # Làm tròn tới 2 chữ số thập phân

            if lot_size < min_vol:
                logger.warning(f"Lot size tính toán ({lot_size}) < mức tối thiểu ({min_vol}). Sử dụng mức tối thiểu.")
                return min_vol
            if lot_size > max_vol:
                logger.warning(f"Lot size tính toán ({lot_size}) > mức tối đa ({max_vol}). Sử dụng mức tối đa.")
                return max_vol
            
            logger.debug(f"Tính toán lot size cho {symbol}: {lot_size} (Rủi ro: ${risk_amount_usd})")
            return lot_size
        except Exception as e:
            logger.error(f"Lỗi ngoại lệ khi tính lot size cho {symbol}: {e}", exc_info=True)
            return None


if __name__ == "__main__":
    connector = ExnessConnector()
    if connector.connect():
        SYMBOL = "BTCUSD"
        
        # --- Thử nghiệm tính toán Lot Size ---
        logger.info(f"\n--- Thử nghiệm tính toán Lot Size cho {SYMBOL} ---")
        risk_demo = 20  # Muốn rủi ro $20
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick:
            current_price = tick.ask
            sl_price_demo = current_price - 1000 # SL cách 1000 giá
            calculated_lot = connector.calculate_lot_size(SYMBOL, risk_demo, sl_price_demo)
            if calculated_lot:
                logger.info(f"Để rủi ro ${risk_demo} với SL tại {sl_price_demo:.2f}, cần vào lệnh {calculated_lot} lot.")

                # --- Thử nghiệm đặt lệnh với lot size đã tính ---
                logger.info(f"\n--- Thử nghiệm đặt lệnh {calculated_lot} lot {SYMBOL} ---")
                tp_price_demo = current_price + 2000
                buy_result = connector.place_order(SYMBOL, mt5.ORDER_TYPE_BUY, calculated_lot, sl_price_demo, tp_price_demo)
                if buy_result:
                    time.sleep(5)
                    positions = connector.get_all_open_positions()
                    found_position = next((p for p in positions if p.ticket == buy_result.order), None)
                    if found_position:
                        logger.info(f"--- Tìm thấy vị thế (Ticket: {found_position.ticket}). Thử nghiệm đóng lệnh ---")
                        connector.close_position(found_position)
        else:
            logger.error("Không thể lấy giá tick hiện tại để thử nghiệm.")
        
        connector.shutdown()