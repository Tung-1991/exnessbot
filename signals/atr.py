# -*- coding: utf-8 -*-
# signals/atr.py
# (ĐÃ SỬA LỖI REGRESSION)

import pandas as pd
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger("ExnessBot")

def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo Average True Range (ATR).
    (ĐÃ HOÀN NGUYÊN VỀ GỐC ĐỂ SỬA LỖI 4700 vs 3600)
    """
    if not all(col in df.columns for col in ['high', 'low', 'close']):
        logger.error("[ATR] DataFrame thiếu cột 'high', 'low', hoặc 'close'.")
        return None
        
    if len(df) < period + 1: # (Hoàn nguyên check an toàn)
        logger.warning(f"[ATR] Không đủ dữ liệu ({len(df)}) để tính ATR({period}).")
        return None

    # Tính toán True Range (TR)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # --- (ĐÂY LÀ DÒNG SỬA LỖI) ---
    # Hoàn nguyên về logic 'alpha' (như file gốc của bạn)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    # --- (HẾT SỬA LỖI) ---
    
    return atr

# ==============================================================================
# (NÂNG CẤP 1) HÀM MỚI: DYNAMIC ATR BUFFER
# (Hàm này vẫn giữ nguyên, nó không gây lỗi)
# ==============================================================================

def get_dynamic_atr_buffer(
    current_atr_value: float,
    df: pd.DataFrame, 
    config: Dict[str, Any], 
    mode: str
) -> float:
    """
    Tính toán hệ số nhân (multiplier) ATR động dựa trên biến động thị trường.
    """
    
    # 1. Lấy hệ số cơ sở (Base Multiplier)
    base_multiplier = 1.0
    if mode == "SL":
        base_multiplier = config.get("sl_atr_multiplier", 0.2)
    elif mode == "BE":
        base_multiplier = config.get("be_atr_buffer", 0.8)
    elif mode == "TSL":
        base_multiplier = config.get("trail_atr_buffer", 0.2)
    else:
        return base_multiplier # Fallback an toàn

    try:
        # 2. Lấy Config cho Logic Động
        ma_period = config.get("DYN_ATR_MA_PERIOD", 50)
        min_cap_ratio = config.get("DYN_ATR_MIN_CAP_RATIO", 0.75)
        max_cap_ratio = config.get("DYN_ATR_MAX_CAP_RATIO", 2.0)
        
        # 3. Tính toán Tỷ lệ Biến động (Volatility Ratio)
        atr_period = config.get("atr_period", 14)
        
        # (SỬA LỖI) Gọi hàm calculate_atr (đã sửa)
        atr_series = calculate_atr(df, atr_period)
        
        if atr_series is None or len(atr_series) < ma_period:
            return base_multiplier # Không đủ dữ liệu, dùng hệ số cố định

        # 3.2. Tính MA(50) của ATR(14)
        long_term_atr_ma = atr_series.rolling(window=ma_period).mean().iloc[-1]
        
        if pd.isna(long_term_atr_ma) or long_term_atr_ma == 0:
            return base_multiplier # Lỗi tính toán, dùng hệ số cố định

        volatility_ratio = current_atr_value / long_term_atr_ma
        
        scaled_multiplier = base_multiplier * volatility_ratio
        
        min_mult = base_multiplier * min_cap_ratio
        max_mult = base_multiplier * max_cap_ratio
        
        final_multiplier = max(min_mult, min(scaled_multiplier, max_mult))

        return final_multiplier

    except Exception as e:
        logger.error(f"[ATR] Lỗi khi tính Dynamic Buffer (Mode: {mode}): {e}. Dùng hệ số cố định.")
        return base_multiplier # Fallback an toàn