# -*- coding: utf-8 -*-
# Tên file: signals/signal_generator.py (Bản Final V7.0)
# Mục đích: Chỉ tổng hợp điểm từ 8 indicator độc lập (Logic Cộng dồn).
#          ĐÃ LOẠI BỎ HOÀN TOÀN LOGIC 'trend_bias'.

import pandas as pd
from typing import Dict, Any, Tuple
import logging

# --- BƯỚC 1: IMPORT TẤT CẢ 8 HÀM TÍNH ĐIỂM (v7.0) ---

# 6 Indicators Khung M15 (df_main)
from signals.bollinger_bands import get_bb_score
from signals.rsi import get_rsi_score
from signals.macd import get_macd_score
from signals.adx import get_adx_score
from signals.candle_patterns import get_candle_pattern_score
from signals.volume import get_volume_score

# 2 Indicators Khung H1 (df_trend)
from signals.supertrend import get_supertrend_score
# (Hàm get_ema_score sẽ được tạo ở file ema.py tiếp theo)
from signals.ema import get_ema_score 

logger = logging.getLogger("ExnessBot")

# ==============================================================================
# HÀM HỖ TRỢ (HELPERS)
# ==============================================================================

def _apply_max_score(score: float, max_score: float) -> float:
    """
    Hàm nội bộ: Áp dụng trần điểm (Weighting).
    Hàm này rất quan trọng để "chuẩn hóa" trọng số của mỗi indicator.
    """
    return min(score, max_score)

# ==============================================================================
# HÀM TỔNG HỢP TÍN HIỆU CUỐI CÙNG (HÀM CHÍNH v7.0)
# ==============================================================================

def get_final_signal(
    df_main: pd.DataFrame, 
    df_trend: pd.DataFrame, 
    config: Dict[str, Any]
) -> Tuple[float, float, Dict[str, Any]]:
    """
    Tổng hợp điểm từ TẤT CẢ 8 chỉ báo độc lập.
    Tuân thủ logic CỘNG DỒN (additive) và không có 'trend_bias'.
    
    Returns:
        Tuple[float, float, Dict[str, Any]]: 
        (final_long_score, final_short_score, score_details)
    """
    
    # --- KHỞI TẠO ---
    final_long_score, final_short_score = 0.0, 0.0
    
    # Đọc cấu hình từ config.py
    cfg_main = config.get('ENTRY_SIGNALS_CONFIG', {})
    cfg_trend = config.get('TREND_FILTERS_CONFIG', {})
    
    score_details = {
        "long": {},
        "short": {},
        "trend_bias": "REMOVED" # Ghi chú rõ ràng logic cũ đã bị loại bỏ
    }

    try:
        # --- BƯỚC A: TÍNH ĐIỂM TÍN HIỆU KHUNG M15 (df_main) ---
        
        # 1. Bollinger Bands (v7.0)
        if cfg_main.get('BOLLINGER_BANDS', {}).get('enabled', False):
            max_s = cfg_main['BOLLINGER_BANDS'].get('MAX_SCORE', 30)
            # GỌI HÀM MÀ KHÔNG CÓ 'trend_bias'
            bb_long, bb_short = get_bb_score(df_main, config) 
            score_details['long']['BB'] = _apply_max_score(bb_long, max_s)
            score_details['short']['BB'] = _apply_max_score(bb_short, max_s)

        # 2. RSI (v7.0)
        if cfg_main.get('RSI', {}).get('enabled', False):
            max_s = cfg_main['RSI'].get('MAX_SCORE', 30)
            # GỌI HÀM MÀ KHÔNG CÓ 'trend_bias'
            rsi_long, rsi_short = get_rsi_score(df_main, config)
            score_details['long']['RSI'] = _apply_max_score(rsi_long, max_s)
            score_details['short']['RSI'] = _apply_max_score(rsi_short, max_s)

        # 3. MACD (v7.0)
        if cfg_main.get('MACD', {}).get('enabled', False):
            max_s = cfg_main['MACD'].get('MAX_SCORE', 25)
            macd_long, macd_short = get_macd_score(df_main, config)
            score_details['long']['MACD'] = _apply_max_score(macd_long, max_s)
            score_details['short']['MACD'] = _apply_max_score(macd_short, max_s)

        # 4. ADX (v7.0)
        if cfg_main.get('ADX', {}).get('enabled', False):
            max_s = cfg_main['ADX'].get('MAX_SCORE', 10)
            adx_long, adx_short = get_adx_score(df_main, config)
            score_details['long']['ADX'] = _apply_max_score(adx_long, max_s)
            score_details['short']['ADX'] = _apply_max_score(adx_short, max_s)

        # 5. Candle Patterns (v7.0)
        if cfg_main.get('CANDLE_PATTERNS', {}).get('enabled', False):
            max_s = cfg_main['CANDLE_PATTERNS'].get('MAX_SCORE', 20)
            candle_long, candle_short = get_candle_pattern_score(df_main, config)
            score_details['long']['Candle'] = _apply_max_score(candle_long, max_s)
            score_details['short']['Candle'] = _apply_max_score(candle_short, max_s)
            
        # 6. Volume (v7.0)
        if cfg_main.get('VOLUME', {}).get('enabled', False):
            max_s = cfg_main['VOLUME'].get('MAX_SCORE', 5)
            vol_long, vol_short = get_volume_score(df_main, config)
            score_details['long']['Volume'] = _apply_max_score(vol_long, max_s)
            score_details['short']['Volume'] = _apply_max_score(vol_short, max_s)

        # --- BƯỚC B: TÍNH ĐIỂM TÍN HIỆU KHUNG H1 (df_trend) ---
        # (Đây là 2 indicator cuối cùng, HĐLĐ như 6 cái trên)

        # 7. Supertrend (H1)
        if cfg_trend.get('SUPERTREND', {}).get('enabled', False):
            max_s = cfg_trend['SUPERTREND'].get('MAX_SCORE', 15) # Sẽ thêm MAX_SCORE này vào config sau
            st_long, st_short = get_supertrend_score(df_trend, config)
            score_details['long']['ST_H1'] = _apply_max_score(st_long, max_s)
            score_details['short']['ST_H1'] = _apply_max_score(st_short, max_s)
        
        # 8. EMA (H1)
        if cfg_trend.get('EMA', {}).get('enabled', False):
            max_s = cfg_trend['EMA'].get('MAX_SCORE', 15) # Sẽ thêm MAX_SCORE này vào config sau
            ema_long, ema_short = get_ema_score(df_trend, config)
            score_details['long']['EMA_H1'] = _apply_max_score(ema_long, max_s)
            score_details['short']['EMA_H1'] = _apply_max_score(ema_short, max_s)

        # --- BƯỚC C: TÍNH TỔNG ĐIỂM CUỐI CÙNG (Logic Cộng dồn) ---
        
        for score in score_details['long'].values():
            final_long_score += score
            
        for score in score_details['short'].values():
            final_short_score += score

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng trong get_final_signal (v7.0): {e}", exc_info=True)
        return 0.0, 0.0, {} # Trả về 0 nếu có lỗi

    # Trả về điểm số thô
    return final_long_score, final_short_score, score_details