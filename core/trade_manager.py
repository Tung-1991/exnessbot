# -*- coding: utf-8 -*-
# core/trade_manager.py (v3.3 - Hoàn chỉnh)

import time
import re
from datetime import datetime, timedelta
from typing import Dict, Any
import MetaTrader5 as mt5
import uuid

# Import các module cốt lõi và cấu hình
import config
from core.exness_connector import ExnessConnector
from core.risk_manager import calculate_trade_details
from signals.signal_generator import get_final_signal
from core.storage_manager import load_state, save_state
from signals.atr import calculate_atr

# --- HÀM TIỆN ÍCH ---
def parse_timeframe_to_minutes(tf_str: str) -> int:
    """Hàm chuyển đổi chuỗi timeframe (ví dụ: '5m', '1h') sang số phút."""
    tf_str = tf_str.lower()
    match = re.match(r"(\d+)([mhd])", tf_str)
    if not match: raise ValueError(f"Khung thời gian không hợp lệ: {tf_str}")
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm': return value
    elif unit == 'h': return value * 60
    elif unit == 'd': return value * 24 * 60
    return 0

# ---------------------------------------------

class TradeManager:
    """Lớp điều phối chính, chứa vòng lặp và logic vận hành của bot."""
    def __init__(self, config_module):
        self.config = config_module
        self.connector = ExnessConnector()
        self.state = {}
        self.last_candle_time = None
        self.cooldown_until = datetime.now()
        self.latest_data_cache = {}
        self.cache_expiry_time = datetime.now()
        print("Trade Manager v3.3 (Hoàn chỉnh) đã được khởi tạo.")

    def run(self):
        """Bắt đầu vòng lặp hoạt động chính của bot."""
        print("Bot đang khởi động...")
        if not self.connector.connect():
            print("CRITICAL: Không thể kết nối tới MT5! Bot sẽ thoát.")
            return
            
        self.state = load_state()
        print(f"✅ Bot đã tải lại trạng thái. Hiện đang quản lý {len(self.state.get('active_trades', []))} lệnh.")
        print("✅ Kết nối thành công. Bot (Phase 3) bắt đầu hoạt động...")
        
        try:
            while True:
                now = datetime.now()
                self.manage_open_positions()

                timeframe_minutes = parse_timeframe_to_minutes(self.config['TIMEFRAME'])
                is_new_candle_time = (now.minute % timeframe_minutes == 0) and (now.second < self.config['LOOP_SLEEP_SECONDS'])
                current_candle_timestamp = now.replace(second=0, microsecond=0)
                
                if is_new_candle_time and current_candle_timestamp != self.last_candle_time:
                    self.last_candle_time = current_candle_timestamp
                    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] Nến {self.config['TIMEFRAME']} mới. Bắt đầu quét lệnh mới...")
                    self.scan_for_new_trades()

                time.sleep(self.config['LOOP_SLEEP_SECONDS'])

        except KeyboardInterrupt:
            print("\n[INFO] Phát hiện Ctrl+C. Bot đang dừng lại một cách an toàn...")
        except Exception as e:
            print(f"[CRITICAL] Lỗi không xác định trong vòng lặp chính: {e}")
        finally:
            print("[INFO] Đang đóng kết nối và lưu trạng thái cuối cùng...")
            save_state(self.state)
            self.connector.shutdown()
            print("[INFO] Bot đã dừng hoàn toàn.")

    def get_current_pnl(self, trade: Dict, current_price: float) -> tuple[float, float]:
        """Tính PnL hiện tại của lệnh bằng USD và R-multiple."""
        if not current_price or trade.get('entry_price', 0) <= 0: return 0.0, 0.0
        
        order_type_str = 'BUY' if trade['type'] == 'LONG' else 'SELL'
        profit_usd = self.connector.calculate_profit(trade['symbol'], order_type_str, trade['lot_size'], trade['entry_price'], current_price) or 0.0
        
        initial_risk_usd = trade.get('initial_risk_usd', 1)
        pnl_r = (profit_usd / initial_risk_usd) if initial_risk_usd > 0 else 0.0
        return profit_usd, pnl_r

    def update_latest_data(self):
        """Tối ưu: Chỉ lấy dữ liệu mới khi cần thiết."""
        now = datetime.now()
        if now < self.cache_expiry_time and self.latest_data_cache:
            return

        symbols_in_trade = {trade['symbol'] for trade in self.state.get('active_trades', [])}
        if not symbols_in_trade:
            self.latest_data_cache = {}
            return

        new_candle_detected = self.last_candle_time and now.minute != self.last_candle_time.minute
        for symbol in symbols_in_trade:
            tick = self.connector.mt5.symbol_info_tick(symbol)
            if tick:
                self.latest_data_cache.setdefault(symbol, {})['tick'] = tick

            if new_candle_detected:
                 df = self.connector.get_historical_data(symbol, self.config['TIMEFRAME'], 50)
                 if df is not None and not df.empty:
                    atr_series = calculate_atr(df, self.config['INDICATORS_CONFIG']['ATR']['PERIOD'])
                    if atr_series is not None:
                         self.latest_data_cache.setdefault(symbol, {})['atr'] = atr_series.iloc[-1]
        
        self.cache_expiry_time = now + timedelta(seconds=self.config['LOOP_SLEEP_SECONDS'])

    def manage_open_positions(self):
        """Quản lý các lệnh đang mở (TSL, TP1, PP...)."""
        if not self.state.get('active_trades'): return
        
        self.update_latest_data()
        trade_cfg = self.config.get('ACTIVE_TRADE_MANAGEMENT', {})
        state_changed = False

        for trade in self.state.get('active_trades', [])[:]:
            symbol_data = self.latest_data_cache.get(trade['symbol'])
            if not symbol_data or 'tick' not in symbol_data: continue

            position = next((p for p in self.connector.get_all_open_positions() if p.ticket == trade['ticket_id']), None)
            if position is None:
                print(f"[INFO] Lệnh #{trade['ticket_id']} đã đóng (bởi SL/TP server). Đang cập nhật bộ nhớ.")
                self.state['active_trades'].remove(trade)
                self.state.setdefault('trade_history', []).append(trade)
                state_changed = True
                continue

            is_long = trade['type'] == 'LONG'
            current_price = symbol_data['tick'].bid if is_long else symbol_data['tick'].ask
            pnl_usd, pnl_r = self.get_current_pnl(trade, current_price)
            trade['peak_pnl_r'] = max(trade.get('peak_pnl_r', 0.0), pnl_r)

            # --- LOGIC TP1 ---
            if trade_cfg.get("ENABLE_TP1") and not trade.get("tp1_hit") and pnl_r >= trade_cfg.get("TP1_RR_RATIO", 1.0):
                print(f"[TP1] Lệnh #{trade['ticket_id']} đạt ngưỡng. Chốt lời một phần...")
                lot_to_close = round(trade['initial_lot_size'] * (trade_cfg.get("TP1_PARTIAL_CLOSE_PERCENT", 50.0) / 100), 2)
                
                if self.connector.close_position(position, volume_to_close=lot_to_close):
                    trade['lot_size'] = round(trade['lot_size'] - lot_to_close, 2)
                    trade['tp1_hit'] = True
                    if trade_cfg.get("TP1_MOVE_SL_TO_ENTRY", True):
                        if self.connector.modify_position(trade['ticket_id'], trade['entry_price'], trade['tp_price']):
                            trade['sl_price'] = trade['entry_price']
                            print(f"-> Đã dời SL của lệnh #{trade['ticket_id']} về điểm vào lệnh.")
                    state_changed = True
                continue

            # --- LOGIC TSL ---
            if trade_cfg.get("ENABLE_TSL") and symbol_data.get('atr'):
                current_sl = trade.get('sl_price', 0)
                trail_distance = symbol_data['atr'] * trade_cfg.get('TSL_ATR_MULTIPLIER', 2.5)
                new_potential_sl = 0
                
                if is_long: new_potential_sl = current_price - trail_distance
                else: new_potential_sl = current_price + trail_distance
                    
                should_modify = False
                if is_long and new_potential_sl > max(current_sl, trade['entry_price']):
                    should_modify = True
                elif not is_long and new_potential_sl < min(current_sl, trade['entry_price']):
                    should_modify = True

                if should_modify:
                    if self.connector.modify_position(trade['ticket_id'], new_potential_sl, trade['tp_price']):
                        print(f"✅ [TSL] Đã dời SL thành công cho lệnh #{trade['ticket_id']} -> {new_potential_sl:.4f}")
                        trade['sl_price'] = new_potential_sl
                        state_changed = True

        if state_changed:
            save_state(self.state)

    def scan_for_new_trades(self):
        """Quy trình quét và thực thi lệnh mới."""
        if datetime.now() < self.cooldown_until:
            print(f"Bot đang trong thời gian cooldown. Chờ đến {self.cooldown_until.strftime('%H:%M:%S')}")
            return
        
        if len(self.state.get('active_trades', [])) >= self.config['MAX_ACTIVE_TRADES']:
            print(f"Đã đạt số lệnh tối đa ({self.config['MAX_ACTIVE_TRADES']}). Không tìm lệnh mới.")
            return

        symbol = self.config['SYMBOL']
        df = self.connector.get_historical_data(symbol, self.config['TIMEFRAME'], self.config['CANDLE_FETCH_COUNT'])
        if df is None or df.empty:
            print(f"Không thể lấy dữ liệu cho {symbol}. Bỏ qua chu kỳ này.")
            return
        
        signal, score_details = get_final_signal(df, self.config)

        print("--- Bảng điểm Phân tích ---")
        for key, value in score_details.items():
            if value != 0: print(f"  - {key.replace('_', ' ').title():<20}: {value:+.2f}")
        print("---------------------------")
        print(f"  >> TỔNG ĐIỂM CUỐI CÙNG: {score_details.get('final_score', 0.0):.2f}")
        print("---------------------------")

        if signal == 0:
            print("Không có tín hiệu giao dịch nào đạt ngưỡng.")
            return
        
        signal_type = "LONG" if signal == 1 else "SHORT"
        print(f"✅ TÌM THẤY TÍN HIỆU {signal_type}! Đang tính toán chi tiết lệnh...")
        
        account_info = self.connector.get_account_info()
        if not account_info:
            print("Không thể lấy thông tin tài khoản để tính toán rủi ro.")
            return
        
        entry_price = df['close'].iloc[-1]
        trade_details = calculate_trade_details(df, entry_price, signal, account_info['equity'], self.config)

        if trade_details is None:
            print("❌ Tín hiệu không đủ điều kiện rủi ro. Lệnh bị hủy.")
            return
            
        lot_size, sl_price, tp_price = trade_details
        
        order_type = mt5.ORDER_TYPE_BUY if signal == 1 else mt5.ORDER_TYPE_SELL
        risk_amount_usd = abs(self.connector.calculate_profit(symbol, order_type, lot_size, entry_price, sl_price) or 0.0)

        print(f"Thông số lệnh: Lot={lot_size:.2f}, SL={sl_price:.4f}, TP={tp_price:.4f}, Risk=${risk_amount_usd:.2f}")
        print("Đang gửi lệnh đến Exness...")

        result = self.connector.place_order(symbol, order_type, lot_size, sl_price, tp_price, self.config['MAGIC_NUMBER'], f"P3_Bot_{signal_type}")

        if result:
            new_trade = {
                "trade_id": str(uuid.uuid4()), "ticket_id": result.order, "symbol": symbol,
                "type": signal_type, "entry_price": result.price, "lot_size": result.volume,
                "initial_lot_size": result.volume, "sl_price": sl_price, "tp_price": tp_price,
                "entry_time": datetime.now().isoformat(),
                "entry_score": score_details.get('final_score', 0.0),
                "initial_risk_usd": risk_amount_usd, "peak_pnl_r": 0.0,
                "tp1_hit": False, "pp_triggered": False
            }
            self.state.setdefault('active_trades', []).append(new_trade)
            save_state(self.state)
            print(f"✅ Lệnh #{result.order} đã được ghi vào bộ nhớ.")

            timeframe_minutes = parse_timeframe_to_minutes(self.config['TIMEFRAME'])
            cooldown_minutes = self.config['COOLDOWN_CANDLES'] * timeframe_minutes
            self.cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
            print(f"Lệnh đã được đặt. Kích hoạt cooldown trong {cooldown_minutes} phút.")