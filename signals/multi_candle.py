# -*- coding: utf-8 -*-
# Tên file: signals/multi_candle.py

import pandas as pd
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ExnessBot")

def get_pullback_confirmation(
    df_m15: pd.DataFrame, 
    ema_series_m15: pd.Series,
    config: Dict[str, Any]
) -> Optional[str]:
    """
    Check GĐ 2+3 (Pullback): Tìm nến đảo chiều tại EMA 21.
    
    Args:
        df_m15 (pd.DataFrame): DataFrame dữ liệu M15.
        ema_series_m15 (pd.Series): Dãy EMA 21 (đã được tính).
        config (Dict[str, Any]): Đối tượng config.

    Returns:
        Optional[str]: "BUY", "SELL", hoặc None.
    """
    
    pattern_name = config["PULLBACK_CANDLE_PATTERN"]
    
    try:
        # Cần ít nhất 2 nến (cặp nến) và 2 giá trị EMA
        if len(df_m15) < 2 or len(ema_series_m15) < 2:
            return None

        # Lấy 2 nến cuối cùng
        # (Nến [-2] là nến BỊ nhấn chìm)
        # (Nến [-1] là nến nhấn chìm - nến tín hiệu)
        prev_candle = df_m15.iloc[-2]
        last_candle = df_m15.iloc[-1]

        # Lấy giá trị EMA tại nến tín hiệu
        last_ema = ema_series_m15.iloc[-1]

        # Trích xuất O-H-L-C
        p_open, p_high, p_low, p_close = prev_candle[['open', 'high', 'low', 'close']]
        l_open, l_high, l_low, l_close = last_candle[['open', 'high', 'low', 'close']]


        if pattern_name == "ENGULFING":
            # --- 1. Check Bullish Engulfing (Tín hiệu BUY) ---
            # (Nến trước là Nến Giảm)
            is_prev_bearish = p_close < p_open
            # (Nến sau là Nến Tăng)
            is_last_bullish = l_close > l_open
            # (Body nến sau bao trọn body nến trước)
            is_engulfing_buy = (l_open < p_close) and (l_close > p_open)
            
            # (Logic GĐ 2: Giá hồi về EMA)
            # (Đáy của cặp nến phải chạm/vượt xuống EMA 21)
            is_at_ema_buy = min(p_low, l_low) <= last_ema
            
            if (is_prev_bearish and is_last_bullish and 
                is_engulfing_buy and is_at_ema_buy):
                # logger.debug("XÁC NHẬN PULLBACK: Bullish Engulfing tại EMA 21.")
                return "BUY"

            # --- 2. Check Bearish Engulfing (Tín hiệu SELL) ---
            # (Nến trước là Nến Tăng)
            is_prev_bullish = p_close > p_open
            # (Nến sau là Nến Giảm)
            is_last_bearish = l_close < l_open
            # (Body nến sau bao trọn body nến trước)
            is_engulfing_sell = (l_open > p_close) and (l_close < p_open)
            
            # (Logic GĐ 2: Giá hồi về EMA)
            # (Đỉnh của cặp nến phải chạm/vượt lên EMA 21)
            is_at_ema_sell = max(p_high, l_high) >= last_ema
            
            if (is_prev_bullish and is_last_bearish and 
                is_engulfing_sell and is_at_ema_sell):
                # logger.debug("XÁC NHẬN PULLBACK: Bearish Engulfing tại EMA 21.")
                return "SELL"

    except Exception as e:
        logger.error(f"Lỗi khi check Pullback Confirmation: {e}", exc_info=True)
        pass

    # Mặc định là không có tín hiệu
    return None