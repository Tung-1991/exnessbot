# -*- coding: utf-8 -*-
# Tên file: core/trade_manager.py

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import threading

# --- Import các file "Cốt lõi" ---
from core.exness_connector import ExnessConnector
from core.storage_manager import load_state, save_state
from core.risk_manager import RiskManager 

# --- Import các file "Cảm biến" ---
# (NÂNG CẤP 1) Import hàm mới
from signals.atr import calculate_atr, get_dynamic_atr_buffer 
from signals.swing_point import get_last_swing_points
from signals.signal_generator import get_signal
from signals.adx import get_adx_value
from signals.ema import check_trend_ema
from signals.supertrend import get_supertrend_direction

logger = logging.getLogger("ExnessBot")

# ==============================================================================
# LỚP HỖ TRỢ (Dùng cho Backtest)
# ==============================================================================
class SimTrade:
    """Lớp lưu trữ thông tin lệnh (Trade "trên giấy") cho Backtest."""
    def __init__(self, entry_time, entry_price, signal_type, lot_size, 
                 initial_sl_price, initial_risk_usd):
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.type = signal_type # "BUY" / "SELL"
        self.lot_size = lot_size
        
        self.initial_sl_price = initial_sl_price
        self.current_sl = initial_sl_price 
        self.initial_risk_usd = initial_risk_usd
        self.initial_1R_usd = initial_risk_usd 
        
        self.is_BE_hit = False 
        
        self.close_time = None
        self.close_price = None
        self.close_reason = None
        self.pnl_usd = 0.0

# ==============================================================================
# LỚP TRADE MANAGER (CHÍNH)
# ==============================================================================

class TradeManager:
    
    def __init__(self, config: Dict[str, Any], mode="live", initial_capital=10000.0):
        """
        Khởi tạo Trade Manager.
        (NÂNG CẤP: Gộp 1, 2, 3)
        """
        self.config = config
        self.mode = mode
        logger.info(f"TradeManager đã khởi tạo ở chế độ: [{self.mode.upper()}]")

        self.lock = threading.Lock()

        # --- Đọc Config (Chỉ đọc các config liên quan đến TradeManager) ---
        self.SYMBOL = self.config["SYMBOL"]
        self.max_trade = self.config["max_trade"]
        
        # SL/TSL Config (Gốc - Dùng làm fallback)
        self.atr_period = self.config.get("atr_period", 14)
        self.swing_period = self.config.get("swing_period", 5)
        self.sl_atr_multiplier = self.config.get("sl_atr_multiplier", 0.2)
        self.tsl_trigger_R = self.config.get("tsl_trigger_R", 1.0)
        self.isMoveToBE_Enabled = self.config.get("isMoveToBE_Enabled", True)
        self.be_atr_buffer = self.config.get("be_atr_buffer", 0.8)
        self.trail_atr_buffer = self.config.get("trail_atr_buffer", 0.2)
        
        self.MAGIC_NUMBER = 12345 
        
        # --- (THÊM) Đọc Config Nâng cấp ---
        self.USE_DYNAMIC_ATR_BUFFER = self.config.get("USE_DYNAMIC_ATR_BUFFER", False)
        self.USE_ADX_GREY_ZONE = self.config.get("USE_ADX_GREY_ZONE", False)
        self.ADX_WEAK = self.config.get("ADX_WEAK", 18)
        self.ADX_STRONG = self.config.get("ADX_STRONG", 23)
        self.ADX_MIN_LEVEL = self.config.get("ADX_MIN_LEVEL", 20)
        # --- (HẾT THÊM) ---

        # Cấu hình theo Mode
        if self.mode == "live":
            self.connector = ExnessConnector()
            if not self.connector.connect():
                logger.critical("LỖI NGHIÊM TRỌNG: Không thể kết nối MT5 ở chế độ LIVE.")
                raise ConnectionError("Không thể khởi tạo TradeManager ở chế độ LIVE.")
            
            self.state = load_state()
            self.managed_trades = self.state.get("active_trades", [])
            self.last_trade_close_time_str = self.state.get("last_trade_close_time", None)
            logger.info(f"[LIVE] Đang quản lý {len(self.managed_trades)} lệnh (tải từ JSON).")
            
        else: # "backtest"
            self.connector = None
            self.open_trades_sim: List[SimTrade] = []
            self.closed_trades_sim: List[SimTrade] = []
            self.sim_capital = initial_capital
            self.equity_curve = [self.sim_capital]
            self.last_trade_close_time_str = None
            logger.info(f"[BACKTEST] Khởi tạo với vốn $ {initial_capital:,.2f}")

        self.risk_manager = RiskManager(
            self.config,
            self.mode,
            self._get_current_capital, 
            self.connector              
        )

    # ==========================================================
    # HÀM MỚI: ĐỐI CHIẾU TRẠNG THÁI (LUỒNG NHANH)
    # ==========================================================
    def reconcile_live_trades(self):
        """(Hàm cho Luồng 2 - Nhanh 5s)"""
        if self.mode != "live":
            return

        with self.lock:
            try:
                positions_on_exness = self.connector.get_all_open_positions()
                
                if len(self.managed_trades) > 0 and len(positions_on_exness) == 0:
                    if not self.connector.connect():
                        logger.warning("[LIVE][RECONCILE] CẢNH BÁO: Mất kết nối. Bỏ qua đợt đối chiếu này.")
                        return
                
                exness_positions_map = {
                    p.ticket: p for p in positions_on_exness 
                    if p.magic == self.MAGIC_NUMBER
                }
                
                managed_trades_copy = list(self.managed_trades)
                state_changed = False
                
                for trade in managed_trades_copy:
                    if trade["ticket"] not in exness_positions_map:
                        logger.warning(f"[LIVE][RECONCILE] Lệnh {trade['ticket']} không còn trên sàn. Xóa khỏi quản lý.")
                        self.managed_trades.remove(trade)
                        state_changed = True
                        self.last_trade_close_time_str = datetime.now().isoformat()

                if state_changed:
                    self._save_state()
            
            except Exception as e:
                logger.error(f"[LIVE] Lỗi khi reconcile lệnh: {e}")

    # ==========================================================
    # LUỒNG LOGIC CHÍNH
    # ==========================================================

    def check_and_open_new_trade(self, data_h1: pd.DataFrame, data_m15: pd.DataFrame):
        """(Hàm cho Luồng 1 - Signal)"""
        
        # --- KIỂM TRA COOLDOWN ---
        if self.last_trade_close_time_str:
            try:
                last_close_time = datetime.fromisoformat(self.last_trade_close_time_str)
                cooldown_minutes = self.config.get("COOLDOWN_MINUTES", 60) 
                cooldown_delta = timedelta(minutes=cooldown_minutes)
                
                current_time = None
                if self.mode == "live":
                    current_time = datetime.now()
                else: 
                    current_time = data_m15.index[-1].to_pydatetime() 
                
                if current_time < (last_close_time + cooldown_delta):
                    return
                else:
                    logger.info("Thời gian Cooldown đã kết thúc. Bắt đầu tìm tín hiệu trở lại.")
                    self.last_trade_close_time_str = None
                    if self.mode == "live": self._save_state()

            except Exception as e:
                logger.error(f"Lỗi khi xử lý Cooldown: {e}")
                self.last_trade_close_time_str = None
        
        if self._get_open_trade_count() >= self.max_trade:
            return

        signal = get_signal(data_h1, data_m15, self.config) 

        if signal:
            try:
                self.open_trade(signal, data_h1, data_m15)
            except Exception as e:
                logger.error(f"[{self.mode.upper()}] Lỗi khi thực thi open_trade ({signal}): {e}", exc_info=True)

    
    def open_trade(self, signal: str, data_h1: pd.DataFrame, data_m15: pd.DataFrame):
        """(Hàm nội bộ) Thực thi logic mở lệnh."""
        
        with self.lock:
            if self._get_open_trade_count() >= self.max_trade:
                logger.warning(f"[{self.mode.upper()}] Bỏ qua tín hiệu {signal} do race condition, đã đủ lệnh.")
                return
            
            logger.info(f"[{self.mode.upper()}] Nhận tín hiệu {signal}. Bắt đầu tính SL & Lot...")

            try:
                current_atr = calculate_atr(data_m15, self.atr_period).iloc[-1]
                last_high, last_low = get_last_swing_points(data_m15, self.config)
                
                if pd.isna(current_atr) or last_high is None or last_low is None:
                    logger.error("Thiếu dữ liệu (ATR/Swing) để tính SL. Bỏ qua lệnh.")
                    return
            except Exception as e:
                logger.error(f"Lỗi lấy dữ liệu (ATR/Swing): {e}")
                return

            # --- (NÂNG CẤP 1) Lấy Hệ số SL Động ---
            sl_atr_mult = self.sl_atr_multiplier # Mặc định
            if self.USE_DYNAMIC_ATR_BUFFER:
                try:
                    sl_atr_mult = get_dynamic_atr_buffer(current_atr, data_m15, self.config, "SL")
                except Exception as e:
                    logger.error(f"Lỗi get_dynamic_atr_buffer (SL): {e}. Dùng hệ số cố định.")
                    sl_atr_mult = self.sl_atr_multiplier
            # --- (HẾT NÂNG CẤP 1) ---

            # Tính SL ban đầu (Kỹ thuật)
            initial_sl_price = 0.0
            if signal == "BUY":
                initial_sl_price = last_low - (sl_atr_mult * current_atr)
            else: # SELL
                initial_sl_price = last_high + (sl_atr_mult * current_atr)

            sim_entry_price = data_m15['close'].iloc[-1] 
            
            # (NÂNG CẤP 2) Gọi RiskManager (Đã bao gồm logic Max Loss SL)
            lot_size, initial_risk_usd, adjusted_sl_price = self.risk_manager.calculate_lot_size_for_trade(
                signal, data_h1, initial_sl_price, sim_entry_price
            )
            
            if lot_size is None or lot_size <= 0:
                logger.error(f"[{self.mode.upper()}] Tính toán Lot size thất bại hoặc bằng 0. Bỏ qua lệnh.")
                return

            if self.mode == "live":
                order_type = 0 if signal == "BUY" else 1
                result = self.connector.place_order(
                    symbol=self.SYMBOL, order_type=order_type, lot_size=lot_size,
                    sl_price=adjusted_sl_price, tp_price=0.0, # (NÂNG CẤP 2) Dùng SL đã điều chỉnh
                    magic_number=self.MAGIC_NUMBER, comment="finalplan_bot_v3"
                )
                
                if result and result.retcode == 10009: # DONE
                    live_1R_usd = abs(self.connector.calculate_profit(
                        self.SYMBOL, "LONG" if signal=="BUY" else "SELL", 
                        lot_size, result.price, adjusted_sl_price 
                    ))
                    
                    new_trade_state = {
                        "ticket": result.order, "symbol": self.SYMBOL, "type": signal,
                        "entry_price": result.price, 
                        "initial_sl": adjusted_sl_price, # (NÂNG CẤP 2) Lưu SL thực tế
                        "current_sl": adjusted_sl_price, # (NÂNG CẤP 2) Lưu SL thực tế
                        "lot_size": lot_size,
                        "magic": self.MAGIC_NUMBER, "initial_1R_usd": live_1R_usd,
                        "is_BE_hit": False
                    }
                    self.managed_trades.append(new_trade_state)
                    self._save_state()
                    logger.info(f"+++ [LIVE] MỞ LỆNH {signal} thành công. Ticket: {result.order}")
                else:
                    logger.error(f"--- [LIVE] MỞ LỆNH {signal} thất bại. Retcode: {result.retcode if result else 'N/A'}")

            else: # "backtest"
                # (NÂNG CẤP 2) Backtest dùng SL đã điều chỉnh (từ RiskManager)
                trade = SimTrade(data_m15.index[-1], sim_entry_price, signal,
                                 lot_size, adjusted_sl_price, initial_risk_usd)
                self.open_trades_sim.append(trade)
                logger.info(f"+++ [BACKTEST] MỞ LỆNH {signal} @ {sim_entry_price:.5f}")
            
    def update_all_trades(self, data_h1: pd.DataFrame, data_m15: pd.DataFrame):
        """(Hàm cho Luồng 1 - Signal) Quản lý TSL."""
        try:
            current_atr = calculate_atr(data_m15, self.atr_period).iloc[-1]
            last_high, last_low = get_last_swing_points(data_m15, self.config)
            trend_adx_h1 = get_adx_value(data_h1, self.config) 
            
            if pd.isna(current_atr) or last_high is None or last_low is None or pd.isna(trend_adx_h1):
                logger.warning("Thiếu dữ liệu (ATR/Swing/ADX) cho TSL. Bỏ qua.")
                return
        except Exception as e:
            logger.error(f"Lỗi lấy dữ liệu TSL: {e}")
            return
            
        if self.mode == "live":
            # (THAY ĐỔI) Truyền data_m15 cho Nâng cấp 1
            self._live_update_tsl(data_h1, data_m15, current_atr, last_high, last_low, trend_adx_h1)
        else:
            current_candle = data_m15.iloc[-1]
            # (THAY ĐỔI) Truyền data_m15 cho Nâng cấp 1
            self._backtest_update_tsl(data_h1, data_m15, current_atr, last_high, last_low, trend_adx_h1, current_candle)

    # ==========================================================
    # CÁC HÀM RIÊNG CỦA MODE "LIVE"
    # ==========================================================

    def _live_update_tsl(self, data_h1: pd.DataFrame, data_m15: pd.DataFrame, current_atr, last_high, last_low, trend_adx_h1):
        """Logic TSL 3 chế độ cho chế độ LIVE."""
        
        with self.lock:
            # 1. ĐỐI CHIẾU TRƯỚC
            try:
                positions_on_exness = self.connector.get_all_open_positions()
                
                if len(self.managed_trades) > 0 and len(positions_on_exness) == 0:
                    if not self.connector.connect():
                        logger.warning("[LIVE][TSL] Mất kết nối khi update TSL. Bỏ qua vòng này.")
                        return

                exness_positions_map = {
                    p.ticket: p for p in positions_on_exness 
                    if p.magic == self.MAGIC_NUMBER
                }
                
                managed_trades_copy = list(self.managed_trades)
                state_changed = False
                
                for trade in managed_trades_copy:
                    if trade["ticket"] not in exness_positions_map:
                        self.managed_trades.remove(trade)
                        state_changed = True
                        self.last_trade_close_time_str = datetime.now().isoformat()

                if state_changed: self._save_state()
            
            except Exception as e:
                logger.error(f"[LIVE] Lỗi đối chiếu TSL: {e}")
                return 

            # --- (NÂNG CẤP 3) Xác định Trạng thái ADX ---
            adx_state = "STRONG" # Mặc định
            if self.USE_ADX_GREY_ZONE:
                if trend_adx_h1 < self.ADX_WEAK: adx_state = "WEAK"
                elif trend_adx_h1 < self.ADX_STRONG: adx_state = "GREY"
            else: # Dùng logic gốc
                if trend_adx_h1 < self.ADX_MIN_LEVEL: adx_state = "WEAK"
            # --- (HẾT NÂNG CẤP 3) ---

            # 2. XỬ LÝ TSL & EMERGENCY EXIT
            managed_trades_copy = list(self.managed_trades) 
            
            for trade in managed_trades_copy:
                current_position = exness_positions_map.get(trade["ticket"])
                if not current_position: continue 

                # --- EMERGENCY EXIT ---
                if self.config["USE_EMERGENCY_EXIT"]:
                    try:
                        trend_ema_h1 = check_trend_ema(data_h1, self.config)
                        trend_st_h1 = get_supertrend_direction(data_h1, self.config)
                        
                        is_trend_broken = False
                        if trade["type"] == "BUY" and (trend_ema_h1 == "DOWN" or trend_st_h1 == "DOWN"):
                            is_trend_broken = True
                        elif trade["type"] == "SELL" and (trend_ema_h1 == "UP" or trend_st_h1 == "UP"):
                            is_trend_broken = True
                            
                        # (NÂNG CẤP 3) Chỉ thoát khi ADX mạnh
                        is_reversal_confirmed = (adx_state == "STRONG")
                        
                        if is_trend_broken and is_reversal_confirmed:
                            logger.warning(f"[LIVE][EMERGENCY EXIT] Đóng lệnh {trade['ticket']}")
                            if self.connector.close_position(current_position, comment="emergency_exit_h1"):
                                self.last_trade_close_time_str = datetime.now().isoformat()
                            self.managed_trades.remove(trade)
                            self._save_state()
                            continue 
                            
                    except Exception as e:
                        logger.error(f"[LIVE] Lỗi Emergency Exit: {e}")
                        
                # --- Bước 1: BE ---
                if not trade["is_BE_hit"] and self.isMoveToBE_Enabled:
                    live_profit_usd = current_position.profit
                    target_profit_usd = trade["initial_1R_usd"] * self.tsl_trigger_R
                    
                    if live_profit_usd >= target_profit_usd:
                        
                        # (NÂNG CẤP 1) Lấy Hệ số BE Động
                        be_atr_buf = self.be_atr_buffer
                        if self.USE_DYNAMIC_ATR_BUFFER:
                            try:
                                be_atr_buf = get_dynamic_atr_buffer(current_atr, data_m15, self.config, "BE")
                            except Exception as e:
                                logger.error(f"Lỗi get_dynamic_atr_buffer (BE): {e}. Dùng hệ số cố định.")
                        
                        new_sl = 0.0
                        if trade["type"] == "BUY":
                            new_sl = trade["entry_price"] + (be_atr_buf * current_atr)
                        else: # SELL
                            new_sl = trade["entry_price"] - (be_atr_buf * current_atr)

                        if (trade["type"] == "BUY" and new_sl > trade["current_sl"]) or \
                           (trade["type"] == "SELL" and new_sl < trade["current_sl"]):
                            
                            if self.connector.modify_position(trade["ticket"], new_sl, 0.0):
                                logger.info(f"[LIVE] TSL (BE): Dời SL lệnh {trade['ticket']} về {new_sl:.5f}")
                                trade["current_sl"] = new_sl
                                trade["is_BE_hit"] = True
                                self._save_state()

                # --- Bước 2: Trailing (Logic 3 chế độ) ---
                if trade["is_BE_hit"] or not self.isMoveToBE_Enabled:
                    
                    # (NÂNG CẤP 1) Lấy Hệ số TSL Động
                    trail_atr_buf = self.trail_atr_buffer
                    if self.USE_DYNAMIC_ATR_BUFFER:
                        try:
                            trail_atr_buf = get_dynamic_atr_buffer(current_atr, data_m15, self.config, "TSL")
                        except Exception as e:
                            logger.error(f"Lỗi get_dynamic_atr_buffer (TSL): {e}. Dùng hệ số cố định.")

                    new_sl = 0.0
                    
                    # (NÂNG CẤP 3) Dùng adx_state
                    is_trending = (adx_state == "STRONG")
                    tsl_mode = self.config.get("TSL_LOGIC_MODE", "STATIC")

                    if trade["type"] == "BUY":
                        if tsl_mode == "DYNAMIC":
                            if not is_trending: # Sideways hoặc Grey Zone -> Chốt ngắn (Bám ĐỈNH)
                                new_sl = last_high - (trail_atr_buf * current_atr)
                            else: # Trending -> Gồng lãi (Bám ĐÁY)
                                new_sl = last_low - (trail_atr_buf * current_atr)
                        elif tsl_mode == "AGGRESSIVE":
                            new_sl = last_high - (trail_atr_buf * current_atr)
                        else: # STATIC
                            new_sl = last_low - (trail_atr_buf * current_atr)
                    
                    else: # SELL
                        if tsl_mode == "DYNAMIC":
                            if not is_trending: # Sideways hoặc Grey Zone -> Chốt ngắn (Bám ĐÁY)
                                new_sl = last_low + (trail_atr_buf * current_atr)
                            else: # Trending -> Gồng lãi (Bám ĐỈNH)
                                new_sl = last_high + (trail_atr_buf * current_atr)
                        elif tsl_mode == "AGGRESSIVE":
                            new_sl = last_low + (trail_atr_buf * current_atr)
                        else: # STATIC
                            new_sl = last_high + (trail_atr_buf * current_atr)
                    
                    if (trade["type"] == "BUY" and new_sl > trade["current_sl"]) or \
                       (trade["type"] == "SELL" and new_sl < trade["current_sl"]):
                        
                        if self.connector.modify_position(trade["ticket"], new_sl, 0.0):
                            logger.info(f"[LIVE] TSL (SWING): Dời SL lệnh {trade['ticket']} về {new_sl:.5f}")
                            trade["current_sl"] = new_sl
                            self._save_state()

    def _save_state(self):
        """Helper (LIVE): Lưu trạng thái vào JSON."""
        if self.mode == "live":
            self.state["active_trades"] = self.managed_trades
            self.state["last_trade_close_time"] = self.last_trade_close_time_str
            save_state(self.state)

    # ==========================================================
    # CÁC HÀM RIÊNG CỦA MODE "BACKTEST"
    # ==========================================================

    def _backtest_update_tsl(self, data_h1: pd.DataFrame, data_m15: pd.DataFrame, current_atr, last_high, last_low, trend_adx_h1, current_candle):
        """Logic TSL 3 chế độ cho BACKTEST."""
        
        # --- (NÂNG CẤP 3) Xác định Trạng thái ADX ---
        adx_state = "STRONG" # Mặc định
        if self.USE_ADX_GREY_ZONE:
            if trend_adx_h1 < self.ADX_WEAK: adx_state = "WEAK"
            elif trend_adx_h1 < self.ADX_STRONG: adx_state = "GREY"
        else: # Dùng logic gốc
            if trend_adx_h1 < self.ADX_MIN_LEVEL: adx_state = "WEAK"
        # --- (HẾT NÂNG CẤP 3) ---
        
        for i in range(len(self.open_trades_sim) - 1, -1, -1):
            trade = self.open_trades_sim[i]
            
            # --- EMERGENCY EXIT ---
            if self.config["USE_EMERGENCY_EXIT"]:
                try:
                    trend_ema_h1 = check_trend_ema(data_h1, self.config)
                    trend_st_h1 = get_supertrend_direction(data_h1, self.config)
                    
                    is_trend_broken = False
                    if trade.type == "BUY" and (trend_ema_h1 == "DOWN" or trend_st_h1 == "DOWN"):
                        is_trend_broken = True
                    elif trade.type == "SELL" and (trend_ema_h1 == "UP" or trend_st_h1 == "UP"):
                        is_trend_broken = True
                        
                    # (NÂNG CẤP 3) Chỉ thoát khi ADX mạnh
                    is_reversal_confirmed = (adx_state == "STRONG")
                    
                    if is_trend_broken and is_reversal_confirmed:
                        logger.warning(f"[BACKTEST][EMERGENCY EXIT] Đóng lệnh {trade.type}")
                        self._sim_close_trade(trade, current_candle.name, current_candle.close, "Emergency Exit")
                        continue 
                        
                except Exception as e:
                    logger.error(f"[BACKTEST] Lỗi Emergency Exit: {e}")

            # 1. Check SL Hit
            is_sl_hit = False
            if trade.type == "BUY" and current_candle.low <= trade.current_sl:
                is_sl_hit = True
            elif trade.type == "SELL" and current_candle.high >= trade.current_sl:
                is_sl_hit = True
            
            if is_sl_hit:
                self._sim_close_trade(trade, current_candle.name, trade.current_sl, "SL/TSL Hit")
                continue 

            # 2. Cập nhật TSL
            # --- Bước 1: BE ---
            if not trade.is_BE_hit and self.isMoveToBE_Enabled:
                current_profit = 0.0
                if trade.type == "BUY":
                    current_profit = (current_candle.high - trade.entry_price) * trade.lot_size * self.config["CONTRACT_SIZE"]
                else: # SELL
                    current_profit = (trade.entry_price - current_candle.low) * trade.lot_size * self.config["CONTRACT_SIZE"]
                
                target_profit_usd = trade.initial_1R_usd * self.tsl_trigger_R
                
                if current_profit >= target_profit_usd:
                    
                    # (NÂNG CẤP 1) Lấy Hệ số BE Động
                    be_atr_buf = self.be_atr_buffer
                    if self.USE_DYNAMIC_ATR_BUFFER:
                        try:
                            be_atr_buf = get_dynamic_atr_buffer(current_atr, data_m15, self.config, "BE")
                        except Exception as e:
                            logger.error(f"Lỗi get_dynamic_atr_buffer (BE): {e}. Dùng hệ số cố định.")

                    new_sl = 0.0
                    if trade.type == "BUY":
                        new_sl = trade.entry_price + (be_atr_buf * current_atr)
                    else: # SELL
                        new_sl = trade.entry_price - (be_atr_buf * current_atr)
                        
                    if (trade.type == "BUY" and new_sl > trade.current_sl) or \
                       (trade.type == "SELL" and new_sl < trade.current_sl):
                        trade.current_sl = new_sl
                        trade.is_BE_hit = True

            # --- Bước 2: Trailing (Logic 3 chế độ) ---
            if trade.is_BE_hit or not self.isMoveToBE_Enabled:
                
                # (NÂNG CẤP 1) Lấy Hệ số TSL Động
                trail_atr_buf = self.trail_atr_buffer
                if self.USE_DYNAMIC_ATR_BUFFER:
                    try:
                        trail_atr_buf = get_dynamic_atr_buffer(current_atr, data_m15, self.config, "TSL")
                    except Exception as e:
                        logger.error(f"Lỗi get_dynamic_atr_buffer (TSL): {e}. Dùng hệ số cố định.")
                
                new_sl = 0.0
                
                # (NÂNG CẤP 3) Dùng adx_state
                is_trending = (adx_state == "STRONG")
                tsl_mode = self.config.get("TSL_LOGIC_MODE", "STATIC")

                if trade.type == "BUY":
                    if tsl_mode == "DYNAMIC":
                        if not is_trending: # Sideways hoặc Grey Zone -> Chốt ngắn (Bám ĐỈNH)
                            new_sl = last_high - (trail_atr_buf * current_atr)
                        else: # Trending -> Gồng lãi (Bám ĐÁY)
                            new_sl = last_low - (trail_atr_buf * current_atr)
                    elif tsl_mode == "AGGRESSIVE":
                        new_sl = last_high - (trail_atr_buf * current_atr)
                    else: # STATIC
                        new_sl = last_low - (trail_atr_buf * current_atr)
                
                else: # SELL
                    if tsl_mode == "DYNAMIC":
                        if not is_trending: # Sideways hoặc Grey Zone -> Chốt ngắn (Bám ĐÁY)
                            new_sl = last_low + (trail_atr_buf * current_atr)
                        else: # Trending -> Gồng lãi (Bám ĐỈNH)
                            new_sl = last_high + (trail_atr_buf * current_atr)
                    elif tsl_mode == "AGGRESSIVE":
                        new_sl = last_low + (trail_atr_buf * current_atr)
                    else: # STATIC
                        new_sl = last_high + (trail_atr_buf * current_atr)

                if (trade.type == "BUY" and new_sl > trade.current_sl) or \
                   (trade.type == "SELL" and new_sl < trade.current_sl):
                    trade.current_sl = new_sl

    def _sim_close_trade(self, trade: SimTrade, close_time, close_price, reason: str):
        """Helper (BACKTEST): Đóng lệnh."""
        pnl_per_unit = (close_price - trade.entry_price) if trade.type == "BUY" else (trade.entry_price - close_price)
        trade.pnl_usd = pnl_per_unit * trade.lot_size * self.config["CONTRACT_SIZE"]
        
        trade.close_time = close_time
        trade.close_price = close_price
        trade.close_reason = reason
        
        self.closed_trades_sim.append(trade)
        if trade in self.open_trades_sim:
            self.open_trades_sim.remove(trade)
        
        self.sim_capital += trade.pnl_usd
        self.equity_curve.append(self.sim_capital)
        
        self.last_trade_close_time_str = trade.close_time.isoformat()

        logger.info(f"--- [BACKTEST] ĐÓNG LỆNH {trade.type} ({reason}). PnL: ${trade.pnl_usd:,.2f}")
        
    def get_backtest_results_df(self) -> pd.DataFrame:
        """Helper (BACKTEST): Xuất kết quả."""
        if self.mode != "backtest": return pd.DataFrame()
        trades_data = [vars(trade) for trade in self.closed_trades_sim]
        if not trades_data: return pd.DataFrame()
        return pd.DataFrame(trades_data)
    
    def _get_open_trade_count(self) -> int:
        """Helper: Đếm số lệnh đang mở."""
        if self.mode == "live":
            with self.lock:
                return len(self.managed_trades)
        else:
            return len(self.open_trades_sim)

    def _get_current_capital(self) -> float:
        """
        Helper: Trả về vốn hiện tại (live hoặc sim).
        Hàm này được truyền cho RiskManager.
        """
        if self.mode == "live":
            try:
                info = self.connector.get_account_info()
                balance = info.get('balance', self.config["BACKTEST_INITIAL_CAPITAL"])
                return balance
            except Exception as e:
                logger.warning(f"[TradeManager] Không thể lấy balance live, dùng vốn default: {e}")
                return self.config.get("BACKTEST_INITIAL_CAPITAL", 10000.0)
        else: 
            return self.sim_capital