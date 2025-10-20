# -*- coding: utf-8 -*-
# exness_connector.py
# Version: 2.0.0 - The Guardian
# Date: 2025-08-27
"""
CHANGELOG (v2.0.0):
- REFACTOR (calculate_lot_size): Tái cấu trúc hoàn toàn hàm tính toán lot size để có độ tin cậy và an toàn tối đa.
    - FEATURE (Proactive SL Adjustment): Tích hợp cơ chế tự động điều chỉnh Stop Loss nếu nó được đặt quá gần giá,
      tránh các lỗi từ chối lệnh không cần thiết (ý tưởng của người dùng).
    - ENHANCEMENT (Calculation Focus): Loại bỏ phương pháp tính toán thủ công (fallback) có rủi ro sai lệch với các cặp tiền
      phức tạp. Giờ đây, hàm sẽ tập trung 100% vào việc lấy kết quả chính xác từ hàm `mt5.order_calc_profit`.
    - FEATURE (Emergency Fallback): Nếu việc tính toán mức lỗ thất bại hoàn toàn, bot sẽ sử dụng lot size tối thiểu
      và ghi một log ở mức CRITICAL để người dùng được cảnh báo ngay lập tức về việc quy tắc rủi ro đã bị bỏ qua.
- FEATURE (Helper Utilities): Thêm các hàm hỗ trợ `validate_order_before_placement` và `get_market_status` để tăng cường
  khả năng kiểm tra và gỡ lỗi (ý tưởng của người dùng).
"""
from __future__ import annotations

import MetaTrader5 as mt5
import pandas as pd
import logging
from typing import Optional, Dict, List, Tuple

# Lấy logger được cấu hình bởi file chính, nếu không có thì tạo logger cơ bản
logger = logging.getLogger("ExnessBot")
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] - %(message)s")

class ExnessConnector:
    """
    Lớp quản lý kết nối và tương tác với terminal MetaTrader 5.
    """
    def __init__(self):
        self._is_connected: bool = False
        self._timeframe_mapping: Dict[str, int] = {
            '1m': mt5.TIMEFRAME_M1, '5m': mt5.TIMEFRAME_M5, '15m': mt5.TIMEFRAME_M15,
            '30m': mt5.TIMEFRAME_M30, '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1,
        }
        logger.info("Exness Connector v2.0.0 (The Guardian) khởi tạo. Sẵn sàng kết nối...")

    def connect(self) -> bool:
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

    def get_account_info(self) -> Optional[Dict]:
        if not self._is_connected: return None
        info = mt5.account_info()
        return info._asdict() if info else None

    def get_historical_data(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
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

    def get_all_open_positions(self) -> List:
        if not self._is_connected: return []
        positions = mt5.positions_get()
        return positions if positions else []

    def place_order(self, symbol: str, order_type: int, lot_size: float, sl_price: float, tp_price: float, magic_number: int, comment: str) -> Optional[mt5.TradeResult]:
        if not self._is_connected: return None
        
        # Kiểm tra lệnh lần cuối trước khi gửi
        is_valid, reason = self.validate_order_before_placement(symbol, order_type, lot_size, sl_price, tp_price)
        if not is_valid:
            logger.error(f"Lệnh không hợp lệ cho {symbol}: {reason}. Hủy đặt lệnh.")
            market_data = self.get_market_status(symbol)
            logger.error(f"Dữ liệu thị trường tại thời điểm lỗi: {market_data}")
            return None

        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot_size,
            "type": order_type, "price": price, "sl": sl_price, "tp": tp_price,
            "magic": magic_number, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh {symbol} đã được đặt thành công. Ticket: {result.order}, Comment: '{comment}'")
            return result
        logger.error(f"❌ Đặt lệnh {symbol} thất bại. Retcode: {result.retcode if result else 'N/A'}, Comment: '{result.comment if result else 'N/A'}' Error: {mt5.last_error()}")
        return None

    def close_position(self, position, volume_to_close: Optional[float] = None, comment: str = "exness_bot_close") -> Optional[mt5.TradeResult]:
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
            "type": order_type, "position": position.ticket, "price": price, "comment": "",
            #"type": order_type, "position": position.ticket, "price": price, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Lệnh đóng {volume:.2f} lot cho ticket #{position.ticket} đã được gửi thành công.")
            return result
        logger.error(f"❌ Đóng lệnh cho ticket #{position.ticket} thất bại. Retcode: {result.retcode if result else 'N/A'}, Error: {mt5.last_error()}")
        return None

    def modify_position(self, ticket_id: int, sl_price: float, tp_price: float) -> bool:
        if not self._is_connected: return False
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

    def calculate_profit(self, symbol: str, order_type_str: str, volume: float, entry_price: float, current_price: float) -> Optional[float]:
        if not self._is_connected: return None
        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type_str == "LONG" else mt5.ORDER_TYPE_SELL
        profit = mt5.order_calc_profit(mt5_order_type, symbol, volume, entry_price, current_price)
        return profit

    def calculate_lot_size(self, symbol: str, risk_amount_usd: float, sl_price: float, order_type: int) -> Optional[float]:
        """
        Tính toán lot size chính xác với xử lý lỗi toàn diện và cơ chế dự phòng.
        """
        if not self._is_connected:
            logger.error(f"MT5 chưa kết nối - không thể tính lot size cho {symbol}")
            return None
        
        try:
            # BƯỚC 1: Lấy thông tin symbol và validate
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                logger.error(f"Không lấy được thông tin symbol {symbol}")
                return None

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                logger.error(f"Không lấy được tick data của {symbol}")
                return None
            
            # BƯỚC 2: Xác định giá vào lệnh và các tham số cơ bản
            entry_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
            min_vol, max_vol, vol_step = symbol_info.volume_min, symbol_info.volume_max, symbol_info.volume_step

            # BƯỚC 3: Validate và tự động điều chỉnh khoảng cách SL
            # Yêu cầu SL phải cách giá ít nhất 2 lần spread để đảm bảo lệnh hợp lệ
            min_distance = symbol_info.spread * symbol_info.point * 2.0
            if abs(entry_price - sl_price) < min_distance:
                logger.warning(f"SL quá gần cho {symbol}. Khoảng cách hiện tại: {abs(entry_price - sl_price):.5f} < Yêu cầu: {min_distance:.5f}")
                # Thêm một khoảng đệm an toàn 20%
                buffer = min_distance * 1.2
                sl_price = entry_price - buffer if order_type == mt5.ORDER_TYPE_BUY else entry_price + buffer
                logger.info(f"Tự động điều chỉnh SL cho {symbol} về mức an toàn: {sl_price:.5f}")

            # BƯỚC 4: Tính mức lỗ, ưu tiên hàm của MT5
            loss_per_lot = mt5.order_calc_profit(order_type, symbol, 1.0, entry_price, sl_price)

            # BƯỚC 5: Validate kết quả tính mức lỗ và fallback khẩn cấp
            if loss_per_lot is None or loss_per_lot >= 0:
                logger.critical(f"TÍNH TOÁN LỖ THẤT BẠI cho {symbol} ngay cả sau khi điều chỉnh SL. Giá trị loss_per_lot: {loss_per_lot}")
                logger.critical(f"Bỏ qua quy tắc rủi ro! Sử dụng lot size tối thiểu ({min_vol}) làm giải pháp khẩn cấp.")
                return min_vol

            # BƯỚC 6: Tính toán và làm tròn lot size
            lot_size = risk_amount_usd / abs(loss_per_lot)

            if vol_step > 0:
                lot_size = round(lot_size / vol_step) * vol_step
            lot_size = round(lot_size, 2)

            # BƯỚC 7: Áp dụng giới hạn min/max của sàn
            if lot_size < min_vol:
                logger.warning(f"Lot size tính toán ({lot_size:.2f}) < mức tối thiểu ({min_vol}). Sử dụng mức tối thiểu.")
                return min_vol
            if lot_size > max_vol:
                logger.warning(f"Lot size tính toán ({lot_size:.2f}) > mức tối đa ({max_vol}). Sử dụng mức tối đa.")
                return max_vol
            
            logger.debug(f"Tính toán lot size thành công cho {symbol}: {lot_size:.2f} (Rủi ro: ${risk_amount_usd:.2f})")
            return lot_size

        except Exception as e:
            logger.error(f"Lỗi ngoại lệ nghiêm trọng trong calculate_lot_size cho {symbol}: {e}", exc_info=True)
            try:
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info:
                    logger.critical(f"FALLBACK NGOẠI LỆ: Sử dụng lot size tối thiểu cho {symbol} do lỗi không xác định.")
                    return symbol_info.volume_min
            except:
                pass
            return None

    def validate_order_before_placement(self, symbol: str, order_type: int, lot_size: float, 
                                          sl_price: float, tp_price: float) -> Tuple[bool, str]:
        """
        Kiểm tra các tham số của lệnh một cách toàn diện trước khi gửi lên server MT5.
        """
        try:
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return False, f"Symbol không hợp lệ: {symbol}"
                
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return False, f"Không có tick data cho {symbol}"
                
            # Kiểm tra lot size
            if lot_size < symbol_info.volume_min:
                return False, f"Lot size {lot_size} < tối thiểu {symbol_info.volume_min}"
            if lot_size > symbol_info.volume_max:
                return False, f"Lot size {lot_size} > tối đa {symbol_info.volume_max}"
            if symbol_info.volume_step > 0 and round(lot_size / symbol_info.volume_step) * symbol_info.volume_step != lot_size:
                 return False, f"Lot size {lot_size} không đúng bước nhảy {symbol_info.volume_step}"

            # Kiểm tra giá và khoảng cách SL/TP
            entry_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
            # stops_level là khoảng cách tối thiểu tính bằng point mà sàn yêu cầu
            min_distance_points = getattr(symbol_info, 'trade_stops_level', 0)
            min_distance_price = min_distance_points * symbol_info.point

            if sl_price > 0:
                if order_type == mt5.ORDER_TYPE_BUY and entry_price - sl_price < min_distance_price:
                    return False, f"SL quá gần. Khoảng cách {entry_price - sl_price:.5f} < yêu cầu {min_distance_price:.5f}"
                if order_type == mt5.ORDER_TYPE_SELL and sl_price - entry_price < min_distance_price:
                    return False, f"SL quá gần. Khoảng cách {sl_price - entry_price:.5f} < yêu cầu {min_distance_price:.5f}"

            if tp_price > 0:
                if order_type == mt5.ORDER_TYPE_BUY and tp_price - entry_price < min_distance_price:
                    return False, f"TP quá gần. Khoảng cách {tp_price - entry_price:.5f} < yêu cầu {min_distance_price:.5f}"
                if order_type == mt5.ORDER_TYPE_SELL and entry_price - tp_price < min_distance_price:
                    return False, f"TP quá gần. Khoảng cách {entry_price - tp_price:.5f} < yêu cầu {min_distance_price:.5f}"
            
            return True, "Hợp lệ"
            
        except Exception as e:
            return False, f"Lỗi ngoại lệ khi validation: {e}"

    def get_market_status(self, symbol: str) -> dict:
        """
        Lấy thông tin chi tiết về thị trường của một symbol để gỡ lỗi.
        """
        try:
            symbol_info = mt5.symbol_info(symbol)
            tick = mt5.symbol_info_tick(symbol)
            
            if not symbol_info or not tick:
                return {"status": "error", "message": "Không lấy được dữ liệu thị trường"}
                
            return {
                "status": "ok",
                "symbol": symbol,
                "bid": tick.bid,
                "ask": tick.ask,
                "spread_points": symbol_info.spread,
                "spread_price": symbol_info.spread * symbol_info.point,
                "stops_level_points": getattr(symbol_info, 'trade_stops_level', 'N/A'),
                "min_lot": symbol_info.volume_min,
                "max_lot": symbol_info.volume_max,
                "lot_step": symbol_info.volume_step,
                "point": symbol_info.point,
                "contract_size": getattr(symbol_info, 'trade_contract_size', 'N/A'),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}