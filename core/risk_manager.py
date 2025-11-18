# -*- coding: utf-8 -*-
# Tên file: core/risk_manager.py

import logging
import pandas as pd
from typing import Dict, Any, Optional, Callable, Tuple
from core.exness_connector import ExnessConnector
from signals.adx import get_adx_value

logger = logging.getLogger("ExnessBot")

class RiskManager:
    """
    Lớp chuyên xử lý toàn bộ logic tính toán rủi ro và khối lượng giao dịch.
    (NÂNG CẤP: ADX Grey Zone & Max Loss SL)
    """
    def __init__(self, 
                 config: Dict[str, Any], 
                 mode: str, 
                 get_capital_callback: Callable[[], float], 
                 connector: Optional[ExnessConnector] = None):
        
        self.config = config
        self.mode = mode
        self.get_capital_callback = get_capital_callback
        self.connector = connector

        self.SYMBOL = self.config["SYMBOL"]
        self.CONTRACT_SIZE = self.config["CONTRACT_SIZE"]
        self.RISK_MANAGEMENT_MODE = self.config["RISK_MANAGEMENT_MODE"]
        self.fixed_lot = self.config["fixed_lot"]
        self.RISK_PERCENT_PER_TRADE = self.config["RISK_PERCENT_PER_TRADE"]
        
    def _get_risk_amount(self) -> float:
        capital = self.get_capital_callback()
        return capital * (self.RISK_PERCENT_PER_TRADE / 100.0)

    def _sim_calculate_lot_size(self, risk_amount_usd, entry_price, sl_price):
        risk_per_unit = abs(entry_price - sl_price)
        if risk_per_unit == 0: return 0.0, 0.0
        
        lot_size = risk_amount_usd / (risk_per_unit * self.CONTRACT_SIZE)
        lot_size = round(lot_size, 2)
        if lot_size < 0.1: lot_size = 0.1
            
        actual_risk_usd = lot_size * risk_per_unit * self.CONTRACT_SIZE
        return lot_size, actual_risk_usd

    def calculate_lot_size_for_trade(self, 
                                     signal: str, 
                                     data_h1: pd.DataFrame, 
                                     initial_sl_price: float, # Đây là SL Kỹ thuật
                                     sim_entry_price: float   # Đây là giá M15 close (Ước tính Entry)
                                     ) -> Tuple[Optional[float], float, float]:
        """
        Hàm chính: Tính toán Lot Size VÀ Điều chỉnh SL (nếu cần).
        (NÂNG CẤP: ADX Grey Zone & Max Loss SL)
        Trả về: (lot_size, initial_risk_usd, adjusted_sl_price)
        """
        
        lot_size = 0.0
        initial_risk_usd = 0.0
        adjusted_sl_price = initial_sl_price # Mặc định SL điều chỉnh = SL kỹ thuật
        
        order_type = 0 if signal == "BUY" else 1

        # --- (NÂNG CẤP) Đọc Config Vùng Xám & Max Loss ---
        USE_ADX_GREY_ZONE = self.config.get("USE_ADX_GREY_ZONE", False)
        ADX_WEAK = self.config.get("ADX_WEAK", 18)
        ADX_STRONG = self.config.get("ADX_STRONG", 23)
        ADX_MIN_LEVEL = self.config.get("ADX_MIN_LEVEL", 20)

        USE_MAX_USD_SL = self.config.get("USE_MAX_USD_SL_FOR_FIXED_LOT", False)
        MAX_USD_LOSS = self.config.get("MAX_USD_LOSS_PER_TRADE", 300.0)

        # --- BƯỚC 1: Xác định chiến lược (FIXED hay PERCENT) ---
        use_fixed_lot_strategy = False

        if self.RISK_MANAGEMENT_MODE == "FIXED_LOT":
            use_fixed_lot_strategy = True
        
        elif self.RISK_MANAGEMENT_MODE == "DYNAMIC":
            try:
                trend_adx_h1 = get_adx_value(data_h1, self.config)
            except Exception as e:
                logger.error(f"[RiskManager] Lỗi tính ADX cho DYNAMIC: {e}")
                return None, 0.0, initial_sl_price
            
            # (THAY ĐỔI) Logic DYNAMIC với Vùng Xám
            if USE_ADX_GREY_ZONE:
                if trend_adx_h1 >= ADX_STRONG:
                    # 1. Trending (Mạnh) -> Dùng FIXED_LOT
                    use_fixed_lot_strategy = True
                # 2. (Else) Sideways (Yếu) hoặc Grey Zone (Thận trọng) -> Dùng RISK_PERCENT
                
            else:
                # Logic Gốc
                if trend_adx_h1 >= ADX_MIN_LEVEL:
                    use_fixed_lot_strategy = True

        # --- BƯỚC 2: Thực thi Tính toán ---

        if use_fixed_lot_strategy:
            # --- A. CHIẾN LƯỢC FIXED LOT ---
            lot_size = self.fixed_lot

            # (NÂNG CẤP) Áp dụng MAX LOSS SL (Nâng cấp 2)
            if USE_MAX_USD_SL and lot_size > 0 and MAX_USD_LOSS > 0:
                try:
                    # 1. Tính SL Tối Đa (Max Loss SL)
                    price_distance_allowed = MAX_USD_LOSS / (lot_size * self.CONTRACT_SIZE)
                    
                    max_loss_sl_price = 0.0
                    if signal == "BUY":
                        max_loss_sl_price = sim_entry_price - price_distance_allowed
                    else: # SELL
                        max_loss_sl_price = sim_entry_price + price_distance_allowed

                    # 2. So sánh với SL Kỹ thuật
                    technical_sl_price = initial_sl_price
                    
                    if signal == "BUY":
                        # Chọn SL "chặt hơn" (giá trị LỚN HƠN)
                        final_sl = max(technical_sl_price, max_loss_sl_price)
                        if final_sl == max_loss_sl_price and max_loss_sl_price > technical_sl_price:
                            logger.warning(f"[RiskManager] Áp dụng Max Loss SL (BUY). SL Kỹ thuật ({technical_sl_price:.5f}) vi phạm rủi ro ${MAX_USD_LOSS}.")
                            adjusted_sl_price = max_loss_sl_price
                    
                    else: # SELL
                        # Chọn SL "chặt hơn" (giá trị NHỎ HƠN)
                        final_sl = min(technical_sl_price, max_loss_sl_price)
                        if final_sl == max_loss_sl_price and max_loss_sl_price < technical_sl_price:
                            logger.warning(f"[RiskManager] Áp dụng Max Loss SL (SELL). SL Kỹ thuật ({technical_sl_price:.5f}) vi phạm rủi ro ${MAX_USD_LOSS}.")
                            adjusted_sl_price = max_loss_sl_price
                    
                except Exception as e:
                    logger.error(f"[RiskManager] Lỗi khi tính Max Loss SL: {e}. Dùng SL kỹ thuật.")
                    adjusted_sl_price = initial_sl_price
            
        else:
            # --- B. CHIẾN LƯỢC RISK PERCENT ---
            risk_amount_usd = self._get_risk_amount()
            if self.mode == "live":
                lot_size, adjusted_sl_price = self.connector.calculate_lot_size(
                    self.SYMBOL, risk_amount_usd, initial_sl_price, order_type
                )
            else:
                lot_size, initial_risk_usd = self._sim_calculate_lot_size(
                    risk_amount_usd, sim_entry_price, initial_sl_price
                )
                adjusted_sl_price = initial_sl_price # Backtest không bị điều chỉnh SL bởi sàn

        
        # --- BƯỚC 3: Xử lý 1R (cho Backtest) ---
        if self.mode == "backtest":
            if initial_risk_usd == 0 and lot_size is not None and lot_size > 0:
                # Phải dùng SL đã điều chỉnh (adjusted_sl_price) để tính 1R
                initial_risk_usd = abs(sim_entry_price - adjusted_sl_price) * lot_size * self.CONTRACT_SIZE
        
        if lot_size is None:
            logger.error(f"[{self.mode.upper()}] Connector trả về None khi tính Lot Size.")
            return None, 0.0, adjusted_sl_price

        return lot_size, initial_risk_usd, adjusted_sl_price