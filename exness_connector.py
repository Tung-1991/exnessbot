import MetaTrader5 as mt5
import os
import pandas as pd
import time
from datetime import datetime
from dotenv import load_dotenv

class ExnessConnector:
    def __init__(self):
        load_dotenv()
        self._is_connected = False
        self._timeframe_mapping = {
            '1m': mt5.TIMEFRAME_M1, '5m': mt5.TIMEFRAME_M5, '15m': mt5.TIMEFRAME_M15,
            '30m': mt5.TIMEFRAME_M30, '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1,
        }
        print("Exness Connector khởi tạo. Sẵn sàng kết nối tới terminal MT5 đang chạy...")

    def connect(self):
        if self._is_connected:
            return True
        print("Đang tìm và kết nối tới terminal MetaTrader 5...")
        try:
            if not mt5.initialize():
                print(f"Lỗi initialize(): {mt5.last_error()}")
                return False
            account_info = mt5.account_info()
            if not account_info:
                print(f"Không thể lấy thông tin tài khoản: {mt5.last_error()}")
                mt5.shutdown()
                return False
            print(f"Đã kết nối thành công tới tài khoản #{account_info.login} trên server {account_info.server}")
            self._is_connected = True
            return True
        except Exception as e:
            print(f"Lỗi ngoại lệ khi kết nối: {e}")
            return False

    def shutdown(self):
        if self._is_connected:
            print("Đang đóng kết nối MetaTrader 5...")
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
            print(f"Lỗi: Khung thời gian '{timeframe}' không được hỗ trợ.")
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
            print(f"Lỗi ngoại lệ khi lấy dữ liệu lịch sử: {e}")
            return None

    def get_open_positions(self, symbol):
        if not self._is_connected: return []
        positions = mt5.positions_get(symbol=symbol)
        return positions if positions else []

    def place_order(self, symbol, order_type, lot_size, sl_price, tp_price, magic_number=202508):
        if not self._is_connected: return None
        
        price = mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "magic": magic_number,
            "comment": "ricealert_v1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Lệnh {symbol} đã được đặt thành công. Ticket: {result.order}")
            return result
        
        print(f"❌ Đặt lệnh {symbol} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None

    def close_position(self, position, comment="ricealert_close"):
        if not self._is_connected: return None

        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Lệnh đóng cho ticket #{position.ticket} đã được gửi thành công.")
            return result
        
        print(f"❌ Đóng lệnh cho ticket #{position.ticket} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None


if __name__ == "__main__":
    connector = ExnessConnector()
    if connector.connect():
        SYMBOL = "BTCUSD"
        LOT_SIZE = 0.01

        print(f"\n--- Thử nghiệm đặt lệnh {LOT_SIZE} lot {SYMBOL} ---")
        
        # Lấy giá hiện tại để tính SL/TP demo
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick:
            current_price = tick.ask
            sl_demo = current_price - 1000  # SL cách 1000 điểm giá
            tp_demo = current_price + 2000  # TP cách 2000 điểm giá
            
            # 1. Đặt lệnh MUA
            buy_result = connector.place_order(SYMBOL, mt5.ORDER_TYPE_BUY, LOT_SIZE, sl_demo, tp_demo)
            
            if buy_result:
                time.sleep(5) # Đợi 5 giây để lệnh được xử lý
                
                # 2. Tìm và đóng chính lệnh vừa mở
                positions = mt5.positions_get(symbol=SYMBOL)
                if positions:
                    found_position = None
                    for pos in positions:
                        if pos.magic == 202508: # Tìm đúng lệnh của bot qua magic number
                            found_position = pos
                            break
                    
                    if found_position:
                        print(f"\n--- Tìm thấy vị thế (Ticket: {found_position.ticket}). Thử nghiệm đóng lệnh ---")
                        connector.close_position(found_position)
                    else:
                        print("Không tìm thấy vị thế vừa mở để đóng.")
                else:
                    print("Không có vị thế nào đang mở.")
        else:
            print("Không thể lấy giá tick hiện tại của BTCUSD để thử nghiệm.")

        connector.shutdown()