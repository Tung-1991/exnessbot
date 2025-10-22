# -*- coding: utf-8 -*-
# signals/signal_generator.py (v6.0 - Final)
# File này đã được viết lại hoàn toàn để tuân thủ logic 3 Cấp và Đa Khung Thời Gian.

import pandas as pd
from typing import Dict, Any, Tuple
import logging

# --- BƯỚC 1: IMPORT TẤT CẢ CÁC HÀM TÍNH ĐIỂM v6.0 ---
from signals.bollinger_bands import get_bb_score
from signals.rsi import get_rsi_score
from signals.macd import get_macd_score
from signals.adx import get_adx_score
from signals.candle_patterns import get_candle_pattern_score
from signals.volume import get_volume_score

# --- BƯỚC 2: IMPORT CÁC HÀM LỌC XU HƯỚNG v6.0 ---
from signals.supertrend import get_supertrend_score
from signals.ema import calculate_ema # Dùng lại hàm tính EMA gốc

logger = logging.getLogger("ExnessBot")

# ==============================================================================
# HÀM HỖ TRỢ (HELPERS)
# ==============================================================================

def _get_ema_trend_score(df_trend: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Hàm nội bộ: Tính điểm xu hướng (Trend Score) từ EMA 200 trên khung df_trend.
    """
    long_score, short_score = 0.0, 0.0
    try:
        cfg = config['TREND_FILTERS_CONFIG']['EMA']
        if not cfg.get('enabled', False):
            return 0.0, 0.0

        period = cfg['params']['period']
        emas = calculate_emas(df_trend, slow_period=period, fast_period=50) # Fast EMA không dùng
        
        if emas is None or pd.isna(emas[0].iloc[-1]):
            return 0.0, 0.0
            
        slow_ema = emas[0]
        last_close = df_trend['close'].iloc[-1]
        
        if last_close > slow_ema.iloc[-1]:
            long_score = 1.0 # Báo hiệu xu hướng TĂNG
        elif last_close < slow_ema.iloc[-1]:
            short_score = 1.0 # Báo hiệu xu hướng GIẢM

    except Exception as e:
        # logger.debug(f"Lỗi khi tính EMA Trend: {e}")
        pass
    return long_score, short_score

def _get_trend_bias(df_trend: pd.DataFrame, config: Dict[str, Any]) -> int:
    """
    Hàm nội bộ: Xác định xu hướng chung (trend_bias) từ khung thời gian TREND.
    Trả về: 1 (Tăng), -1 (Giảm), 0 (Không rõ ràng).
    """
    try:
        filter_type = config['TREND_FILTERS_CONFIG'].get('USE_TREND_FILTER', 'BOTH').upper()
        
        st_long, st_short = 0.0, 0.0
        ema_long, ema_short = 0.0, 0.0

        if filter_type in ['SUPERTREND', 'BOTH']:
            st_long, st_short = get_supertrend_score(df_trend, config)
        
        if filter_type in ['EMA', 'BOTH']:
            ema_long, ema_short = _get_ema_trend_score(df_trend, config)

        # Quyết định dựa trên bộ lọc
        if filter_type == 'BOTH':
            # Yêu cầu cả hai cùng đồng thuận
            if st_long > 0 and ema_long > 0: return 1
            if st_short > 0 and ema_short > 0: return -1
            return 0 # Không đồng thuận
        
        elif filter_type == 'SUPERTREND':
            if st_long > 0: return 1
            if st_short > 0: return -1
            return 0
            
        elif filter_type == 'EMA':
            if ema_long > 0: return 1
            if ema_short > 0: return -1
            return 0
            
    except Exception as e:
        # logger.debug(f"Lỗi khi lấy Trend Bias: {e}")
        pass
        
    return 0 # Mặc định là không có xu hướng

def _apply_max_score(score: float, max_score: float) -> float:
    """Hàm nội bộ: Áp dụng trần điểm (Điểm 3)"""
    return min(score, max_score)

# ==============================================================================
# HÀM TỔNG HỢP TÍN HIỆU CUỐI CÙNG (HÀM CHÍNH v6.0)
# ==============================================================================

def get_final_signal(
    df_main: pd.DataFrame, 
    df_trend: pd.DataFrame, 
    config: Dict[str, Any]
) -> Tuple[float, float, Dict[str, Any]]:
    """
    Tổng hợp điểm từ tất cả các chỉ báo v6.0.
    Tuân thủ logic cộng điểm độc lập và trần điểm (Điểm 1, 2, 3).
    
    Hàm này KHÔNG còn trả về signal (1/-1), chỉ trả về điểm số thô.
    
    Returns:
        Tuple[float, float, Dict[str, Any]]: 
        (final_long_score, final_short_score, score_details)
    """
    
    # --- KHỞI TẠO ---
    final_long_score, final_short_score = 0.0, 0.0
    cfg = config['ENTRY_SIGNALS_CONFIG']
    
    score_details = {
        "long": {},
        "short": {},
        "trend_bias": 0
    }

    try:
        # --- BƯỚC A: XÁC ĐỊNH XU HƯỚNG CHUNG (từ df_trend) ---
        trend_bias = _get_trend_bias(df_trend, config)
        score_details["trend_bias"] = trend_bias
        
        # --- BƯỚC B: TÍNH ĐIỂM TÍN HIỆU (từ df_main) ---
        
        # 1. Bollinger Bands (v6.0)
        if cfg['BOLLINGER_BANDS']['enabled']:
            max_s = cfg['BOLLINGER_BANDS']['MAX_SCORE']
            bb_long, bb_short = get_bb_score(df_main, config, trend_bias)
            score_details['long']['BB'] = _apply_max_score(bb_long, max_s)
            score_details['short']['BB'] = _apply_max_score(bb_short, max_s)

        # 2. RSI (v6.0)
        if cfg['RSI']['enabled']:
            max_s = cfg['RSI']['MAX_SCORE']
            rsi_long, rsi_short = get_rsi_score(df_main, config, trend_bias)
            score_details['long']['RSI'] = _apply_max_score(rsi_long, max_s)
            score_details['short']['RSI'] = _apply_max_score(rsi_short, max_s)

        # 3. MACD (v6.0)
        if cfg['MACD']['enabled']:
            max_s = cfg['MACD']['MAX_SCORE']
            macd_long, macd_short = get_macd_score(df_main, config)
            score_details['long']['MACD'] = _apply_max_score(macd_long, max_s)
            score_details['short']['MACD'] = _apply_max_score(macd_short, max_s)

        # 4. ADX (v6.0)
        if cfg['ADX']['enabled']:
            max_s = cfg['ADX']['MAX_SCORE']
            adx_long, adx_short = get_adx_score(df_main, config)
            score_details['long']['ADX'] = _apply_max_score(adx_long, max_s)
            score_details['short']['ADX'] = _apply_max_score(adx_short, max_s)

        # 5. Candle Patterns (v6.0)
        if cfg['CANDLE_PATTERNS']['enabled']:
            max_s = cfg['CANDLE_PATTERNS']['MAX_SCORE']
            candle_long, candle_short = get_candle_pattern_score(df_main, config)
            score_details['long']['Candle'] = _apply_max_score(candle_long, max_s)
            score_details['short']['Candle'] = _apply_max_score(candle_short, max_s)
            
        # 6. Volume (v6.0)
        if cfg['VOLUME']['enabled']:
            max_s = cfg['VOLUME']['MAX_SCORE']
            # Volume xác nhận cho cả 2 phe
            vol_long, vol_short = get_volume_score(df_main, config)
            score_details['long']['Volume'] = _apply_max_score(vol_long, max_s)
            score_details['short']['Volume'] = _apply_max_score(vol_short, max_s)

        # --- BƯỚC C: TÍNH TỔNG ĐIỂM CUỐI CÙNG (Logic Điểm 1) ---
        # Chỉ cộng điểm, không trừ điểm
        
        for score in score_details['long'].values():
            final_long_score += score
            
        for score in score_details['short'].values():
            final_short_score += score

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng trong get_final_signal: {e}", exc_info=True)
        return 0.0, 0.0, {} # Trả về 0 nếu có lỗi

    # Trả về điểm số thô
    return final_long_score, final_short_score, score_details