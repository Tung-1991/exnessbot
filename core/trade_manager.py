# -*- coding: utf-8 -*-
# core/trade_manager.py (v6.0 - Final)
# Nâng cấp Logic Đa Khung, Vào Lệnh 3 Cấp, và Thoát Lệnh Hybrid ATR (Điểm 4).

import time
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import MetaTrader5 as mt5
import uuid

# Import các module cốt lõi v6.0
from core.exness_connector import ExnessConnector
from core.risk_manager import calculate_trade_details # (File Bước 3)
from signals.signal_generator import get_final_signal # (File Bước 2)
from core.storage_manager import load_state, save_state
from signals.atr import calculate_atr

# Lấy logger chính của ứng dụng
logger = logging.getLogger("ExnessBot")

# --- HÀM TIỆN ÍCH (Giữ nguyên) ---
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
    """Lớp điều phối chính v6.0, chứa logic Vào/Thoát lệnh nâng cao."""
    
    def __init__(self, config_module):
        self.config = config_module
        self.connector = ExnessConnector()
        self.state = {}
        self.last_candle_time = None
        self.cooldown_until = datetime.now()
        # Xóa bỏ cache data phức tạp, sẽ tải data mới mỗi lần phân tích
        # để đảm bảo score "biến động" chính xác nhất.
        logger.info("Trade Manager v6.0 (Logic 3 Cấp & Hybrid ATR) đã khởi tạo.")

    def run(self):
        """Bắt đầu vòng lặp hoạt động chính của bot (Giữ nguyên logic)."""
        logger.info("Bot đang khởi động...")
        if not self.connector.connect():
            logger.critical("CRITICAL: Không thể kết nối tới MT5! Bot sẽ thoát.")
            return
            
        self.state = load_state()
        logger.info(f"✅ Bot đã tải lại trạng thái. Hiện đang quản lý {len(self.state.get('active_trades', []))} lệnh.")
        logger.info("✅ Kết nối thành công. Bot bắt đầu hoạt động...")
        
        try:
            while True:
                now = datetime.now()
                
                # 1. Quản lý lệnh đang mở (Chạy mỗi giây)
                # Đây là nơi logic Thoát Lệnh (Điểm 4) và TSL (Điểm 7) hoạt động
                self.manage_open_positions()

                # 2. Quét tín hiệu mới (Chỉ chạy 1 lần khi có nến mới)
                timeframe_minutes = parse_timeframe_to_minutes(self.config['TIMEFRAME'])
                # Đảm bảo chỉ chạy 1 lần duy nhất khi nến mới bắt đầu
                is_new_candle_time = (now.minute % timeframe_minutes == 0) and (now.second < self.config['LOOP_SLEEP_SECONDS'])
                current_candle_timestamp = now.replace(second=0, microsecond=0)
                
                if is_new_candle_time and current_candle_timestamp != self.last_candle_time:
                    self.last_candle_time = current_candle_timestamp
                    logger.info(f"Nến {self.config['TIMEFRAME']} mới. Bắt đầu quét lệnh mới...")
                    self.scan_for_new_trades()

                time.sleep(self.config['LOOP_SLEEP_SECONDS'])

        except KeyboardInterrupt:
            logger.warning("\nPhát hiện Ctrl+C. Bot đang dừng lại một cách an toàn...")
        except Exception as e:
            logger.critical(f"Lỗi không xác định trong vòng lặp chính: {e}", exc_info=True)
        finally:
            logger.info("Đang đóng kết nối và lưu trạng thái cuối cùng...")
            save_state(self.state)
            self.connector.shutdown()
            logger.info("Bot đã dừng hoàn toàn.")

    def get_current_pnl(self, trade: Dict, current_price: float) -> tuple[float, float]:
        """Tính PnL hiện tại của lệnh bằng USD và R-multiple (Giữ nguyên)."""
        if not current_price or trade.get('entry_price', 0) <= 0: return 0.0, 0.0
        
        order_type_str = 'LONG' if trade['type'] == 'LONG' else 'SELL'
        profit_usd = self.connector.calculate_profit(trade['symbol'], order_type_str, trade['lot_size'], trade['entry_price'], current_price) or 0.0
        
        # Sửa lỗi chia cho 0 nếu risk = 0
        initial_risk_usd = trade.get('initial_risk_usd', 0.0)
        if initial_risk_usd <= 0: return profit_usd, 0.0
        
        pnl_r = profit_usd / initial_risk_usd
        return profit_usd, pnl_r

    def manage_open_positions(self):
        """
        Quản lý các lệnh đang mở (Logic Hybrid ATR - Điểm 4 & TSL - Điểm 7).
        Hàm này chạy liên tục để check TSL, TP1, PP, và Score Exit.
        """
        if not self.state.get('active_trades'): return
        
        trade_cfg = self.config.get('ACTIVE_TRADE_MANAGEMENT', {})
        state_changed = False
        
        # Lấy data nến HIỆN TẠI để tính score (cho Điểm 4)
        # Chúng ta cần data mới nhất mỗi lần check
        df_main = self.connector.get_historical_data(self.config['SYMBOL'], self.config['TIMEFRAME'], self.config['CANDLE_FETCH_COUNT'])
        df_trend = self.connector.get_historical_data(self.config['SYMBOL'], self.config['TREND_TIMEFRAME'], self.config['CANDLE_FETCH_COUNT'])

        # Nếu không lấy được data, không thể check score, chỉ check TSL/TP/PP
        can_check_score = (df_main is not None and df_trend is not None)
        current_long_score, current_short_score = 0.0, 0.0
        
        if can_check_score:
            current_long_score, current_short_score, _ = get_final_signal(df_main, df_trend, self.config)

        for trade in self.state.get('active_trades', [])[:]:
            position = next((p for p in self.connector.get_all_open_positions() if p.ticket == trade['ticket_id']), None)
            
            # 1. Kiểm tra xem lệnh có còn trên server không
            if position is None:
                logger.info(f"Lệnh #{trade['ticket_id']} đã đóng (SL/TP server). Đang cập nhật bộ nhớ.")
                self.state['active_trades'].remove(trade)
                self.state.setdefault('trade_history', []).append(trade) # Lưu lịch sử
                state_changed = True
                continue

            is_long = trade['type'] == 'LONG'
            tick = self.connector.mt5.symbol_info_tick(trade['symbol'])
            if not tick: continue
            
            current_price = tick.bid if is_long else tick.ask
            pnl_usd, pnl_r = self.get_current_pnl(trade, current_price)
            trade['peak_pnl_r'] = max(trade.get('peak_pnl_r', 0.0), pnl_r)

            # --- LOGIC THOÁT LỆNH SỐ 1: HYBRID ATR (ĐIỂM 4) ---
            if self.config.get('ENABLE_SCORE_BASED_EXIT', False) and can_check_score:
                current_score = current_long_score if is_long else current_short_score
                exit_threshold = self.config.get('EXIT_SCORE_THRESHOLD', 40.0)
                
                if current_score < exit_threshold:
                    logger.warning(f"[Hybrid ATR] Kích hoạt thoát lệnh! Lệnh #{trade['ticket_id']} ({trade['type']}) có điểm rớt xuống {current_score:.2f} (Ngưỡng: {exit_threshold})")
                    
                    close_percent = self.config.get('EXIT_PARTIAL_CLOSE_PERCENT', 100.0)
                    volume_to_close = round(position.volume * (close_percent / 100.0), 2)
                    
                    if self.connector.close_position(position, volume_to_close=volume_to_close, comment="Score Exit"):
                        if volume_to_close == position.volume:
                            self.state['active_trades'].remove(trade)
                            self.state.setdefault('trade_history', []).append(trade)
                        else:
                            # Cập nhật lại lot size nếu chỉ đóng 1 phần
                            trade['lot_size'] = round(position.volume - volume_to_close, 2)
                            trade['initial_lot_size'] = trade['lot_size'] # Cập nhật để các logic sau (PP, TP1) tính đúng
                        
                        state_changed = True
                    continue # Đã xử lý lệnh này

            # --- LOGIC THOÁT LỆNH SỐ 2, 3, 4 (TP1, PP, TSL - ĐIỂM 7) ---
            # Các logic này được giữ nguyên từ file gốc của bạn, chúng chạy song song
            
            # 2. Logic TP1
            if trade_cfg.get("ENABLE_TP1") and not trade.get("tp1_hit") and pnl_r >= trade_cfg.get("TP1_RR_RATIO", 1.0):
                logger.info(f"[TP1] Lệnh #{trade['ticket_id']} đạt ngưỡng {trade_cfg.get('TP1_RR_RATIO', 1.0)}R.")
                lot_to_close = round(trade['initial_lot_size'] * (trade_cfg.get("TP1_PARTIAL_CLOSE_PERCENT", 50.0) / 100), 2)
                
                if self.connector.close_position(position, volume_to_close=lot_to_close, comment="TP1 Hit"):
                    trade['lot_size'] = round(position.volume - lot_to_close, 2)
                    trade['initial_lot_size'] = trade['lot_size'] # Cập nhật lại
                    trade['tp1_hit'] = True
                    if trade_cfg.get("TP1_MOVE_SL_TO_ENTRY", True):
                        if self.connector.modify_position(trade['ticket_id'], trade['entry_price'], trade['tp_price']):
                            trade['sl_price'] = trade['entry_price']
                            logger.info(f"-> TP1: Đã dời SL của lệnh #{trade['ticket_id']} về điểm vào lệnh.")
                    state_changed = True
                continue

            # 3. Logic Protect Profit (PP)
            if (trade_cfg.get("ENABLE_PROTECT_PROFIT") and
                not trade.get("pp_triggered") and
                not trade.get("tp1_hit") and 
                trade['peak_pnl_r'] >= trade_cfg.get("PP_MIN_PEAK_R_TRIGGER", 1.2) and
                (trade['peak_pnl_r'] - pnl_r) >= trade_cfg.get("PP_DROP_R_TRIGGER", 0.4)):
                
                logger.warning(f"[ProtectProfit] Kích hoạt bảo vệ lợi nhuận cho lệnh #{trade['ticket_id']}!")
                lot_to_close = round(trade['initial_lot_size'] * (trade_cfg.get("PP_PARTIAL_CLOSE_PERCENT", 50.0) / 100), 2)
                
                if self.connector.close_position(position, volume_to_close=lot_to_close, comment="PP Triggered"):
                    trade['lot_size'] = round(position.volume - lot_to_close, 2)
                    trade['initial_lot_size'] = trade['lot_size'] # Cập nhật lại
                    trade['pp_triggered'] = True
                    if trade_cfg.get("PP_MOVE_SL_TO_ENTRY", True):
                        if self.connector.modify_position(trade['ticket_id'], trade['entry_price'], trade['tp_price']):
                            trade['sl_price'] = trade['entry_price']
                            logger.info(f"-> PP: Đã dời SL của lệnh #{trade['ticket_id']} về điểm vào lệnh.")
                    state_changed = True
                continue

            # 4. Logic TSL (Dùng ATR của khung MAIN)
            if trade_cfg.get("ENABLE_TSL") and can_check_score: # Tận dụng df_main đã tải
                current_sl = trade.get('sl_price', 0)
                atr_series = calculate_atr(df_main, self.config['ATR_PERIOD'])
                if atr_series is None: continue
                
                current_atr = atr_series.iloc[-1]
                trail_distance = current_atr * trade_cfg.get('TSL_ATR_MULTIPLIER', 2.5)
                new_potential_sl = 0
                
                if is_long: new_potential_sl = current_price - trail_distance
                else: new_potential_sl = current_price + trail_distance
                    
                should_modify = False
                # Chỉ dời SL khi lợi nhuận (và TSL luôn dời về phía có lợi)
                if is_long and new_potential_sl > max(current_sl, trade['entry_price']):
                    should_modify = True
                elif not is_long and new_potential_sl < min(current_sl, trade['entry_price']):
                    should_modify = True

                if should_modify:
                    if self.connector.modify_position(trade['ticket_id'], new_potential_sl, trade['tp_price']):
                        logger.info(f"✅ [TSL] Đã dời SL cho lệnh #{trade['ticket_id']} -> {new_potential_sl:.4f}")
                        trade['sl_price'] = new_potential_sl
                        state_changed = True

        if state_changed:
            save_state(self.state)

    def scan_for_new_trades(self):
        """
        Quy trình quét và thực thi lệnh mới (Logic Vào Lệnh 3 Cấp).
        Hàm này chỉ chạy 1 lần khi có nến mới.
        """
        
        # 1. Kiểm tra điều kiện chung
        if datetime.now() < self.cooldown_until:
            logger.info(f"Bot đang trong thời gian cooldown. Chờ đến {self.cooldown_until.strftime('%H:%M:%S')}")
            return
        
        if len(self.state.get('active_trades', [])) >= self.config['MAX_ACTIVE_TRADES']:
            logger.info(f"Đã đạt số lệnh tối đa ({self.config['MAX_ACTIVE_TRADES']}). Không tìm lệnh mới.")
            return

        # 2. Lấy dữ liệu Đa Khung Thời Gian (MTF)
        symbol = self.config['SYMBOL']
        df_main = self.connector.get_historical_data(symbol, self.config['TIMEFRAME'], self.config['CANDLE_FETCH_COUNT'])
        df_trend = self.connector.get_historical_data(symbol, self.config['TREND_TIMEFRAME'], self.config['CANDLE_FETCH_COUNT'])
        
        if df_main is None or df_main.empty or df_trend is None or df_trend.empty:
            logger.warning(f"Không thể lấy đủ dữ liệu MTF cho {symbol}. Bỏ qua chu kỳ này.")
            return
        
        # 3. Lấy điểm số (từ Bước 2)
        final_long_score, final_short_score, score_details = get_final_signal(df_main, df_trend, self.config)

        # 4. Triển khai Logic Vào Lệnh 3 Cấp
        entry_levels = self.config.get('ENTRY_SCORE_LEVELS', [90.0, 120.0, 150.0])
        signal = 0
        score_level = 0
        final_score = 0.0

        if self.config.get('ENABLE_LONG_TRADES', True) and final_long_score > final_short_score and final_long_score >= entry_levels[0]:
            signal = 1
            final_score = final_long_score
        elif self.config.get('ENABLE_SHORT_TRADES', True) and final_short_score > final_long_score and final_short_score >= entry_levels[0]:
            signal = -1
            final_score = final_short_score
        
        if signal == 0:
            logger.info(f"Không có tín hiệu (Long: {final_long_score:.1f}, Short: {final_short_score:.1f}). Ngưỡng: {entry_levels[0]}")
            return

        # Xác định Cấp (Level) của tín hiệu
        if final_score >= entry_levels[2]: score_level = 3
        elif final_score >= entry_levels[1]: score_level = 2
        else: score_level = 1
        
        signal_type = "LONG" if signal == 1 else "SHORT"
        logger.info(f"✅ TÌM THẤY TÍN HIỆU {signal_type} [CẤP {score_level}]! (Điểm: {final_score:.2f}). Đang tính toán chi tiết...")
        
        # 5. Gọi Risk Manager 3 Cấp (từ Bước 3)
        account_info = self.connector.get_account_info()
        if not account_info:
            logger.error("Không thể lấy thông tin tài khoản để tính toán rủi ro.")
            return
        
        # Lấy giá vào lệnh (giá đóng cửa của nến tín hiệu)
        entry_price = df_main['close'].iloc[-1]
        
        trade_details = calculate_trade_details(
            df_main, entry_price, signal, account_info['equity'], self.config, score_level
        )

        if trade_details is None:
            logger.warning("❌ Tín hiệu không đủ điều kiện rủi ro (hoặc SL quá gần/xa). Lệnh bị hủy.")
            return
            
        lot_size, sl_price, tp_price = trade_details
        
        # 6. Đặt lệnh
        order_type = mt5.ORDER_TYPE_BUY if signal == 1 else mt5.ORDER_TYPE_SELL
        
        # Tính toán rủi ro USD thực tế (để lưu lại)
        risk_amount_usd = abs(self.connector.calculate_profit(symbol, "LONG" if signal == 1 else "SELL", lot_size, entry_price, sl_price) or 0.0)

        logger.info(f"Thông số lệnh Cấp {score_level}: Lot={lot_size:.2f}, SL={sl_price:.4f}, TP={tp_price:.4f}, Risk=${risk_amount_usd:.2f}")
        logger.info("Đang gửi lệnh đến Exness...")

        result = self.connector.place_order(symbol, order_type, lot_size, sl_price, tp_price, self.config['MAGIC_NUMBER'], f"v6_L{score_level}_{signal_type}")

        if result:
            new_trade = {
                "trade_id": str(uuid.uuid4()),
                "ticket_id": result.order,
                "symbol": symbol,
                "type": signal_type,
                "entry_price": result.price, 
                "lot_size": result.volume,
                "initial_lot_size": result.volume, # Lưu lot gốc để tính partial close
                "sl_price": sl_price,
                "tp_price": tp_price,
                "entry_time": datetime.now().isoformat(),
                "entry_score": final_score,         # <-- Lưu lại điểm vào lệnh
                "score_level": score_level,         # <-- Lưu lại Cấp độ
                "initial_risk_usd": risk_amount_usd,
                "peak_pnl_r": 0.0,
                "tp1_hit": False,
                "pp_triggered": False
            }
            self.state.setdefault('active_trades', []).append(new_trade)
            save_state(self.state)
            logger.info(f"✅ Lệnh #{result.order} đã được ghi vào bộ nhớ.")

            # Kích hoạt Cooldown
            timeframe_minutes = parse_timeframe_to_minutes(self.config['TIMEFRAME'])
            cooldown_minutes = self.config.get('COOLDOWN_CANDLES', 3) * timeframe_minutes
            self.cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
            logger.info(f"Lệnh đã được đặt. Kích hoạt cooldown trong {cooldown_minutes} phút.")