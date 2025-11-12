# -*- coding: utf-8 -*-
# Tên file: signals/ema.py

import pandas as pd
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ExnessBot")

def _calculate_ema(df: pd.DataFrame, period: int) -> Optional[pd.Series]:
    """Hàm helper nội bộ (private) để tính EMA."""
    if len(df) < period:
        return None
    try:
        # Dùng ewm (Exponential Moving Average)
        return df['close'].ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.error(f"Lỗi tính EMA period {period}: {e}")
        return None

# ==============================================================================
# HÀM 1: Check Trend (Giai đoạn 1)
# ==============================================================================

def check_trend_ema(
    df_h1: pd.DataFrame,
    config: Dict[str, Any]
) -> str:
    """
    Check GĐ 1: Giá H1 so với EMA 50.
    Trả về: "UP" (Giá > EMA), "DOWN" (Giá < EMA). 
    """
    trend_ema_period = config["TREND_EMA_PERIOD"]
    ema_series = _calculate_ema(df_h1, trend_ema_period)
    
    # Nếu không tính được, mặc định là DOWN (an toàn)
    if ema_series is None or len(ema_series) < 1:
        return "DOWN"

    last_close = df_h1['close'].iloc[-1]
    last_ema = ema_series.iloc[-1]

    if last_close > last_ema:
        return "UP"
    else:
        return "DOWN"

# ==============================================================================
# HÀM 2: Check Entry (Giai đoạn 2 - Breakout)
# ==============================================================================

def check_entry_ema_breakout(
    df_m15: pd.DataFrame,
    config: Dict[str, Any]
) -> Optional[str]:
    """
    Check GĐ 2 (Breakout): Giá M15 CẮT (cross) EMA 21.
    Trả về: "BUY", "SELL", hoặc None.
    """
    entry_ema_period = config["ENTRY_EMA_PERIOD"]
    ema_series = _calculate_ema(df_m15, entry_ema_period)

    # Cần ít nhất 2 nến để check "cắt"
    if ema_series is None or len(ema_series) < 2:
        return None 

    # Lấy 2 nến cuối cùng (nến hiện tại và nến trước đó)
    close_prev = df_m15['close'].iloc[-2] # Nến trước
    close_last = df_m15['close'].iloc[-1] # Nến hiện tại (nến breakout)
    
    ema_prev = ema_series.iloc[-2]
    ema_last = ema_series.iloc[-1]

    # Check Tín hiệu Long: (Nến trước < EMA) VÀ (Nến hiện tại > EMA)
    if (close_prev < ema_prev) and (close_last > ema_last):
        return "BUY"

    # Check Tín hiệu Short: (Nến trước > EMA) VÀ (Nến hiện tại < EMA)
    if (close_prev > ema_prev) and (close_last < ema_last):
        return "SELL"
        
    # Không có tín hiệu cắt
    return None