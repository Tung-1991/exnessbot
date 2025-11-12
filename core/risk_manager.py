# -*- coding: utf-8 -*-
# Tên file: core/risk_manager.py

import logging
import pandas as pd
from typing import Dict, Any, Optional, Callable, Tuple # (THAY ĐỔI) Import Tuple
from core.exness_connector import ExnessConnector
from signals.adx import get_adx_value

logger = logging.getLogger("ExnessBot")

class RiskManager:
    """
    Lớp chuyên xử lý toàn bộ logic tính toán rủi ro và khối lượng giao dịch.
    """
    def __init__(self, 
                 config: Dict[str, Any], 
                 mode: str, 
                 get_capital_callback: Callable[[], float], 
                 connector: Optional[ExnessConnector] = None):
        """
        Khởi tạo RiskManager.
        - get_capital_callback: Là một hàm được truyền từ TradeManager
                                để lấy vốn (live balance hoặc sim capital).
        - connector: Chỉ cần cho 'live' mode để tính lot.
        """
        self.config = config
        self.mode = mode
        self.get_capital_callback = get_capital_callback
        self.connector = connector

        # --- Đọc Config liên quan đến Risk ---
        self.SYMBOL = self.config["SYMBOL"]
        self.CONTRACT_SIZE = self.config["CONTRACT_SIZE"]
        self.RISK_MANAGEMENT_MODE = self.config["RISK_MANAGEMENT_MODE"]
        self.fixed_lot = self.config["fixed_lot"]
        self.RISK_PERCENT_PER_TRADE = self.config["RISK_PERCENT_PER_TRADE"]
        
    def _get_risk_amount(self) -> float:
        """
        Helper: Lấy số tiền rủi ro dựa trên vốn hiện tại.
        Sử dụng callback để lấy vốn.
        """
        capital = self.get_capital_callback()
        return capital * (self.RISK_PERCENT_PER_TRADE / 100.0)

    def _sim_calculate_lot_size(self, risk_amount_usd, entry_price, sl_price):
        """Helper (BACKTEST): Tính Lot size."""
        risk_per_unit = abs(entry_price - sl_price)
        if risk_per_unit == 0: return 0.0, 0.0
        
        lot_size = risk_amount_usd / (risk_per_unit * self.CONTRACT_SIZE)
        lot_size = round(lot_size, 2)
        if lot_size < 0.01: lot_size = 0.01
            
        actual_risk_usd = lot_size * risk_per_unit * self.CONTRACT_SIZE
        return lot_size, actual_risk_usd

    # --- (THAY ĐỔI) Sửa Lỗi 2 (Phần 2) ---
    def calculate_lot_size_for_trade(self, 
                                     signal: str, 
                                     data_h1: pd.DataFrame, 
                                     initial_sl_price: float, 
                                     sim_entry_price: float
                                     ) -> Tuple[Optional[float], float, float]:
        """
        Hàm chính: Tính toán Lot Size dựa trên logic DYNAMIC, FIXED, hoặc PERCENT.
        (THAY ĐỔI) Trả về (lot_size, initial_risk_usd, adjusted_sl_price)
        """
        lot_size = 0.0
        initial_risk_usd = 0.0
        # (THAY ĐỔI) Khởi tạo adjusted_sl_price
        # Điều này quan trọng cho backtest và fixed_lot
        adjusted_sl_price = initial_sl_price 
        
        order_type = 0 if signal == "BUY" else 1

        # --- DYNAMIC RISK ---
        if self.RISK_MANAGEMENT_MODE == "DYNAMIC":
            try:
                trend_adx_h1 = get_adx_value(data_h1, self.config)
            except Exception as e:
                logger.error(f"[RiskManager] Lỗi tính ADX cho DYNAMIC: {e}")
                return None, 0.0, initial_sl_price # (THAY ĐỔI)
            
            if trend_adx_h1 < self.config["ADX_MIN_LEVEL"]:
                # 1. Sideways -> RISK_PERCENT
                risk_amount_usd = self._get_risk_amount()
                if self.mode == "live":
                    # (THAY ĐỔI) Nhận cả 2 giá trị
                    lot_size, adjusted_sl_price = self.connector.calculate_lot_size(
                        self.SYMBOL, risk_amount_usd, initial_sl_price, order_type
                    )
                else:
                    lot_size, initial_risk_usd = self._sim_calculate_lot_size(
                        risk_amount_usd, sim_entry_price, initial_sl_price
                    )
            else:
                # 2. Trending -> FIXED_LOT
                lot_size = self.fixed_lot

        # --- Logic Gốc (FIXED/PERCENT) ---
        else:
            if self.RISK_MANAGEMENT_MODE == "FIXED_LOT":
                lot_size = self.fixed_lot
            else: # "RISK_PERCENT"
                risk_amount_usd = self._get_risk_amount()
                if self.mode == "live":
                    # (THAY ĐỔI) Nhận cả 2 giá trị
                    lot_size, adjusted_sl_price = self.connector.calculate_lot_size(
                        self.SYMBOL, risk_amount_usd, initial_sl_price, order_type
                    )
                else:
                    lot_size, initial_risk_usd = self._sim_calculate_lot_size(
                        risk_amount_usd, sim_entry_price, initial_sl_price
                    )
        
        # --- Xử lý cho Backtest ---
        if self.mode == "backtest":
            # Nếu dùng fixed_lot, ta vẫn cần tính rủi ro ban đầu (1R)
            if initial_risk_usd == 0 and lot_size > 0:
                initial_risk_usd = abs(sim_entry_price - initial_sl_price) * lot_size * self.CONTRACT_SIZE
        
        # Kiểm tra None (trường hợp lỗi API Exness)
        if lot_size is None:
            logger.error(f"[{self.mode.upper()}] Connector trả về None khi tính Lot Size.")
            return None, 0.0, adjusted_sl_price # (THAY ĐỔI)

        return lot_size, initial_risk_usd, adjusted_sl_price # (THAY ĐỔI)
    # --- (HẾT THAY ĐỔI) ---