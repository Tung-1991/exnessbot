import MetaTrader5 as mt5
import pandas as pd
import time
import os
from dotenv import load_dotenv

def initialize_connection():
    load_dotenv()
    if not mt5.initialize():
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return False
    return True

def place_order(symbol, lot, order_type, sl_points, tp_points):
    price = mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
    if price is None:
        print("Không lấy được giá tick.")
        return None

    if order_type == mt5.ORDER_TYPE_BUY:
        sl = price - sl_points * mt5.symbol_info(symbol).point
        tp = price + tp_points * mt5.symbol_info(symbol).point
    else: # SELL
        sl = price + sl_points * mt5.symbol_info(symbol).point
        tp = price - tp_points * mt5.symbol_info(symbol).point

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": 234000,
        "comment": "ricealert_order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Đặt lệnh thất bại, retcode={result.retcode if result else 'N/A'}")
        return None

    print(f"✅ Đã gửi yêu cầu đặt lệnh {symbol} thành công! Ticket: {result.order}")
    
    # Vòng lặp xác nhận an toàn (rất quan trọng)
    for i in range(5):
        positions = mt5.positions_get(ticket=result.order)
        if positions:
            print(f"✅ Lệnh {result.order} đã được xác nhận trên server!")
            return positions[0]
        time.sleep(1)
        
    print(f"⚠️ Không thể xác nhận lệnh {result.order} sau 5s. Cần kiểm tra thủ công!")
    return None

# --- CHƯƠNG TRÌNH CHÍNH ĐỂ KIỂM THỬ ---
if __name__ == "__main__":
    if initialize_connection():
        SYMBOL = os.getenv("EXNESS_SYMBOL")
        LOT_SIZE = float(os.getenv("TRADE_LOT_SIZE"))
        SL_POINTS = int(os.getenv("RISK_SL_POINTS"))
        TP_POINTS = int(os.getenv("RISK_TP_POINTS"))

        print(f"\n--- Chuẩn bị đặt lệnh MUA {LOT_SIZE} lot {SYMBOL} ---")
        buy_position = place_order(SYMBOL, LOT_SIZE, mt5.ORDER_TYPE_BUY, SL_POINTS, TP_POINTS)
        if buy_position:
            print("Thông tin vị thế MUA:", buy_position)
            time.sleep(5) # Đợi 5 giây
            # Đóng lệnh vừa mở để test
            close_request = {"action": mt5.TRADE_ACTION_DEAL, "position": buy_position.ticket, "volume": LOT_SIZE, "type": mt5.ORDER_TYPE_SELL, "price": mt5.symbol_info_tick(SYMBOL).bid}
            mt5.order_send(close_request)
            print(f"Đã đóng vị thế MUA {buy_position.ticket}")

        mt5.shutdown()
        print("\nĐã đóng kết nối an toàn.")