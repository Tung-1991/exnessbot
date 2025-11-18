# -*- coding: utf-8 -*-
# Tên file: signals/signal_generator.py

import pandas as pd
import logging
from typing import Optional, Dict, Any

from signals.supertrend import get_supertrend_direction
from signals.ema import check_trend_ema, check_entry_ema_breakout, _calculate_ema
from signals.adx import get_adx_value
from signals.candle import get_candle_confirmation
from signals.multi_candle import get_pullback_confirmation
from signals.volume import get_volume_confirmation

logger = logging.getLogger("ExnessBot")

def get_signal(
    df_h1: pd.DataFrame, 
    df_m15: pd.DataFrame,
    config: Dict[str, Any]
) -> Optional[str]:
    """
    Hàm "Bộ não" tổng hợp.
    Thực thi logic 3 bước trong codeplan.txt.
    (NÂNG CẤP: ADX GREY ZONE)
    """
    
    # --- Đọc Config Cơ bản ---
    ALLOW_LONG_TRADES = config["ALLOW_LONG_TRADES"]
    ALLOW_SHORT_TRADES = config["ALLOW_SHORT_TRADES"]
    
    USE_TREND_FILTER = config["USE_TREND_FILTER"]
    USE_SUPERTREND_FILTER = config["USE_SUPERTREND_FILTER"]
    USE_EMA_TREND_FILTER = config["USE_EMA_TREND_FILTER"]
    
    ENTRY_LOGIC_MODE = config["ENTRY_LOGIC_MODE"]
    
    USE_CANDLE_FILTER = config["USE_CANDLE_FILTER"]
    USE_VOLUME_FILTER = config["USE_VOLUME_FILTER"]

    # --- Đọc Config ADX (Gốc & Nâng cấp) ---
    USE_ADX_FILTER = config["USE_ADX_FILTER"]
    ADX_MIN_LEVEL = config.get("ADX_MIN_LEVEL", 20)
    
    # (NÂNG CẤP) Đọc tham số Vùng Xám (với giá trị mặc định an toàn)
    USE_ADX_GREY_ZONE = config.get("USE_ADX_GREY_ZONE", False)
    ADX_WEAK = config.get("ADX_WEAK", 18)
    ADX_STRONG = config.get("ADX_STRONG", 23)

    try:
        # --- BƯỚC 1: LỌC XU HƯỚNG (H1) ---
        final_trend = "SIDEWAYS"
        
        trend_adx_h1 = get_adx_value(df_h1, config) 
        
        if not USE_TREND_FILTER:
            final_trend = "ANY"
        else:
            trend_ema_h1 = check_trend_ema(df_h1, config)
            trend_st_h1 = get_supertrend_direction(df_h1, config)

            is_long_biased = True
            is_short_biased = True

            if USE_EMA_TREND_FILTER and trend_ema_h1 == "DOWN":
                is_long_biased = False
            if USE_EMA_TREND_FILTER and trend_ema_h1 == "UP":
                is_short_biased = False
                
            if USE_SUPERTREND_FILTER and trend_st_h1 == "DOWN":
                is_long_biased = False
            if USE_SUPERTREND_FILTER and trend_st_h1 == "UP":
                is_short_biased = False

            # --- (THAY ĐỔI) 1.3. Áp dụng bộ lọc ADX (Logic Vùng Xám) ---
            if USE_ADX_FILTER:
                if USE_ADX_GREY_ZONE:
                    # Logic Vùng Xám MỚI
                    if trend_adx_h1 < ADX_WEAK:
                        # Dưới vùng xám (Yếu) -> Sideways -> KHÓA
                        is_long_biased = False
                        is_short_biased = False
                    elif trend_adx_h1 >= ADX_WEAK and trend_adx_h1 < ADX_STRONG:
                        # Trong vùng xám (Thận trọng) -> KHÓA
                        is_long_biased = False
                        is_short_biased = False
                    # else: (Trên ADX_STRONG) -> Trending -> Giữ nguyên bias
                
                else:
                    # Logic Gốc (Ngưỡng Cứng)
                    if trend_adx_h1 < ADX_MIN_LEVEL:
                        is_long_biased = False
                        is_short_biased = False
            # --- (HẾT THAY ĐỔI 1.3) ---
                
            if is_long_biased and not is_short_biased:
                final_trend = "UP"
            elif is_short_biased and not is_long_biased:
                final_trend = "DOWN"
            else:
                final_trend = "SIDEWAYS"

        # --- BƯỚC 2: LỌC ENTRY (M15) ---
        entry_signal = None 
        
        # --- (THAY ĐỔI) Logic DYNAMIC ENTRY (Logic Vùng Xám) ---
        if ENTRY_LOGIC_MODE == "DYNAMIC":
            if USE_ADX_GREY_ZONE:
                # Logic Vùng Xám MỚI
                if trend_adx_h1 < ADX_WEAK:
                    # 1. Dưới vùng xám (WEAK) -> Sideways -> Dùng PULLBACK
                    ema_21_m15 = _calculate_ema(df_m15, config["ENTRY_EMA_PERIOD"])
                    if ema_21_m15 is not None:
                        entry_signal = get_pullback_confirmation(df_m15, ema_21_m15, config)
                
                elif trend_adx_h1 >= ADX_STRONG:
                    # 2. Trên vùng xám (STRONG) -> Trending -> Dùng BREAKOUT
                    breakout_signal = check_entry_ema_breakout(df_m15, config)
                    if breakout_signal:
                        candle_ok = True if not USE_CANDLE_FILTER else get_candle_confirmation(df_m15, config)
                        volume_ok = True if not USE_VOLUME_FILTER else get_volume_confirmation(df_m15, config)
                        if candle_ok and volume_ok:
                            entry_signal = breakout_signal
                
                # 3. (Else: Trong Vùng Xám) -> Thận trọng -> entry_signal = None (Mặc định)

            else:
                # Logic Gốc (Ngưỡng Cứng)
                if trend_adx_h1 < ADX_MIN_LEVEL:
                    ema_21_m15 = _calculate_ema(df_m15, config["ENTRY_EMA_PERIOD"])
                    if ema_21_m15 is not None:
                        entry_signal = get_pullback_confirmation(df_m15, ema_21_m15, config)
                else:
                    breakout_signal = check_entry_ema_breakout(df_m15, config)
                    if breakout_signal:
                        candle_ok = True if not USE_CANDLE_FILTER else get_candle_confirmation(df_m15, config)
                        volume_ok = True if not USE_VOLUME_FILTER else get_volume_confirmation(df_m15, config)
                        if candle_ok and volume_ok:
                            entry_signal = breakout_signal
        
        # --- (HẾT THAY ĐỔI DYNAMIC) ---

        elif ENTRY_LOGIC_MODE == "BREAKOUT":
            breakout_signal = check_entry_ema_breakout(df_m15, config)
            if breakout_signal:
                candle_ok = True if not USE_CANDLE_FILTER else get_candle_confirmation(df_m15, config)
                volume_ok = True if not USE_VOLUME_FILTER else get_volume_confirmation(df_m15, config)
                if candle_ok and volume_ok:
                    entry_signal = breakout_signal

        elif ENTRY_LOGIC_MODE == "PULLBACK":
            ema_21_m15 = _calculate_ema(df_m15, config["ENTRY_EMA_PERIOD"])
            if ema_21_m15 is not None:
                entry_signal = get_pullback_confirmation(df_m15, ema_21_m15, config)

        # --- BƯỚC 3: QUYẾT ĐỊNH CUỐI CÙNG ---
        
        if (final_trend == "UP" or final_trend == "ANY") and \
           entry_signal == "BUY" and ALLOW_LONG_TRADES:
            
            # (THAY ĐỔI) Cập nhật logic log
            entry_mode = ENTRY_LOGIC_MODE
            if ENTRY_LOGIC_MODE == "DYNAMIC":
                if USE_ADX_GREY_ZONE:
                    if trend_adx_h1 < ADX_WEAK: entry_mode = "DYN_PULLBACK"
                    elif trend_adx_h1 >= ADX_STRONG: entry_mode = "DYN_BREAKOUT"
                else:
                    if trend_adx_h1 < ADX_MIN_LEVEL: entry_mode = "DYN_PULLBACK"
                    else: entry_mode = "DYN_BREAKOUT"
            
            logger.info(f"TÍN HIỆU BUY MỚI: Trend H1={final_trend}, Entry M15={entry_mode}")
            return "BUY"

        if (final_trend == "DOWN" or final_trend == "ANY") and \
           entry_signal == "SELL" and ALLOW_SHORT_TRADES:
            
            # (THAY ĐỔI) Cập nhật logic log
            entry_mode = ENTRY_LOGIC_MODE
            if ENTRY_LOGIC_MODE == "DYNAMIC":
                if USE_ADX_GREY_ZONE:
                    if trend_adx_h1 < ADX_WEAK: entry_mode = "DYN_PULLBACK"
                    elif trend_adx_h1 >= ADX_STRONG: entry_mode = "DYN_BREAKOUT"
                else:
                    if trend_adx_h1 < ADX_MIN_LEVEL: entry_mode = "DYN_PULLBACK"
                    else: entry_mode = "DYN_BREAKOUT"
            
            logger.info(f"TÍN HIỆU SELL MỚI: Trend H1={final_trend}, Entry M15={entry_mode}")
            return "SELL"
            
        return None 

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng trong Signal Generator: {e}", exc_info=True)
        return None