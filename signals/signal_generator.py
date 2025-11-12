# -*- coding: utf-8 -*-
# Tên file: signals/signal_generator.py

import pandas as pd
import logging
from typing import Optional, Dict, Any

# Import tất cả 7 file "cảm biến"
from signals.supertrend import get_supertrend_direction
from signals.ema import check_trend_ema, check_entry_ema_breakout, _calculate_ema
from signals.adx import get_adx_value
from signals.candle import get_candle_confirmation
from signals.multi_candle import get_pullback_confirmation
from signals.volume import get_volume_confirmation
# (File atr.py và swing_point.py sẽ được dùng bởi core/trade_manager.py)

logger = logging.getLogger("ExnessBot")

def get_signal(
    df_h1: pd.DataFrame, 
    df_m15: pd.DataFrame,
    config: Dict[str, Any]
) -> Optional[str]:
    """
    Hàm "Bộ não" tổng hợp.
    Thực thi logic 3 bước trong codeplan.txt.

    Args:
        df_h1 (pd.DataFrame): DataFrame dữ liệu H1.
        df_m15 (pd.DataFrame): DataFrame dữ liệu M15.
        config (Dict[str, Any]): Đối tượng config.

    Returns:
        Optional[str]: "BUY", "SELL", hoặc None.
    """
    
    # Đọc config
    ALLOW_LONG_TRADES = config["ALLOW_LONG_TRADES"]
    ALLOW_SHORT_TRADES = config["ALLOW_SHORT_TRADES"]
    
    USE_TREND_FILTER = config["USE_TREND_FILTER"]
    USE_SUPERTREND_FILTER = config["USE_SUPERTREND_FILTER"]
    USE_EMA_TREND_FILTER = config["USE_EMA_TREND_FILTER"]
    USE_ADX_FILTER = config["USE_ADX_FILTER"]
    ADX_MIN_LEVEL = config["ADX_MIN_LEVEL"]
    
    ENTRY_LOGIC_MODE = config["ENTRY_LOGIC_MODE"]
    
    USE_CANDLE_FILTER = config["USE_CANDLE_FILTER"]
    USE_VOLUME_FILTER = config["USE_VOLUME_FILTER"]
    
    try:
        # --- BƯỚC 1: LỌC XU HƯỚNG (H1) ---
        final_trend = "SIDEWAYS"
        
        # (NÂNG CẤP 2: Luôn tính ADX vì cần dùng cho logic DYNAMIC)
        trend_adx_h1 = get_adx_value(df_h1, config) # float (ví dụ 25.5)
        
        if not USE_TREND_FILTER:
            # Nếu tắt lọc, bot được phép trade cả hai hướng
            final_trend = "ANY"
        else:
            # 1.1. Tính các cảm biến H1
            trend_ema_h1 = check_trend_ema(df_h1, config) # "UP" / "DOWN"
            trend_st_h1 = get_supertrend_direction(df_h1, config) # "UP" / "DOWN"
            # (ADX đã tính ở trên)

            # 1.2. Tổng hợp kết quả H1
            is_long_biased = True  # Mặc định cho phép Long
            is_short_biased = True # Mặc định cho phép Short

            # Check bộ lọc EMA
            if USE_EMA_TREND_FILTER and trend_ema_h1 == "DOWN":
                is_long_biased = False
            if USE_EMA_TREND_FILTER and trend_ema_h1 == "UP":
                is_short_biased = False
                
            # Check bộ lọc Supertrend
            if USE_SUPERTREND_FILTER and trend_st_h1 == "DOWN":
                is_long_biased = False
            if USE_SUPERTREND_FILTER and trend_st_h1 == "UP":
                is_short_biased = False

            # 1.3. Áp dụng bộ lọc ADX
            if USE_ADX_FILTER and trend_adx_h1 < ADX_MIN_LEVEL:
                # ADX yếu -> Thị trường Sideways -> KHÓA cả hai chiều
                is_long_biased = False
                is_short_biased = False
                
            # 1.4. Quyết định Trend cuối cùng
            if is_long_biased and not is_short_biased:
                final_trend = "UP"
            elif is_short_biased and not is_long_biased:
                final_trend = "DOWN"
            else:
                # (Cả hai cùng True (ví dụ EMA và ST ngược nhau)
                # hoặc cả hai cùng False (do ADX))
                final_trend = "SIDEWAYS"

        # --- BƯỚC 2: LỌC ENTRY (M15) ---
        entry_signal = None # "BUY" or "SELL"
        
        # --- NÂNG CẤP 2: LOGIC DYNAMIC ENTRY ---
        if ENTRY_LOGIC_MODE == "DYNAMIC":
            if trend_adx_h1 < ADX_MIN_LEVEL:
                # ADX Thấp (Sideways) -> Dùng Logic "PULLBACK"
                ema_21_m15 = _calculate_ema(df_m15, config["ENTRY_EMA_PERIOD"])
                if ema_21_m15 is not None:
                    entry_signal = get_pullback_confirmation(df_m15, ema_21_m15, config)
            else:
                # ADX Cao (Trending) -> Dùng Logic "BREAKOUT"
                breakout_signal = check_entry_ema_breakout(df_m15, config)
                if breakout_signal:
                    candle_ok = True if not USE_CANDLE_FILTER else get_candle_confirmation(df_m15, config)
                    volume_ok = True if not USE_VOLUME_FILTER else get_volume_confirmation(df_m15, config)
                    if candle_ok and volume_ok:
                        entry_signal = breakout_signal
        
        # --- Logic Gốc (Nếu không dùng DYNAMIC) ---
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
        
        # Check Lệnh Long
        if (final_trend == "UP" or final_trend == "ANY") and \
           entry_signal == "BUY" and ALLOW_LONG_TRADES:
            
            # (Thêm log để biết mode nào đã kích hoạt)
            entry_mode = "DYNAMIC_PULLBACK" if (ENTRY_LOGIC_MODE == "DYNAMIC" and trend_adx_h1 < ADX_MIN_LEVEL) else \
                         "DYNAMIC_BREAKOUT" if (ENTRY_LOGIC_MODE == "DYNAMIC" and trend_adx_h1 >= ADX_MIN_LEVEL) else \
                         ENTRY_LOGIC_MODE
            logger.info(f"TÍN HIỆU BUY MỚI: Trend H1={final_trend}, Entry M15={entry_mode}")
            return "BUY"

        # Check Lệnh Short
        if (final_trend == "DOWN" or final_trend == "ANY") and \
           entry_signal == "SELL" and ALLOW_SHORT_TRADES:
            
            entry_mode = "DYNAMIC_PULLBACK" if (ENTRY_LOGIC_MODE == "DYNAMIC" and trend_adx_h1 < ADX_MIN_LEVEL) else \
                         "DYNAMIC_BREAKOUT" if (ENTRY_LOGIC_MODE == "DYNAMIC" and trend_adx_h1 >= ADX_MIN_LEVEL) else \
                         ENTRY_LOGIC_MODE
            logger.info(f"TÍN HIỆU SELL MỚI: Trend H1={final_trend}, Entry M15={entry_mode}")
            return "SELL"
            
        return None # Không có tín hiệu

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng trong Signal Generator: {e}", exc_info=True)
        return None