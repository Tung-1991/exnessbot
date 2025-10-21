# -*- coding: utf-8 -*-
# signals/signal_generator.py (v4.1 - Đã sửa lỗi)

import pandas as pd
from typing import Dict, Any, Tuple

# Import các hàm tính điểm mới từ các file con
from signals.bollinger_bands import get_bb_score
from signals.rsi import get_rsi_score
from signals.macd import get_macd_score
from signals.supertrend import get_supertrend_score

# Import các hàm tính toán gốc cho các bộ lọc
from signals.ema import calculate_emas

# ==============================================================================
# HÀM ÁP DỤNG CÁC BỘ LỌC (Hệ số nhân)
# ==============================================================================

def apply_filters(long_score: float, short_score: float, df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """Áp dụng các bộ lọc EMA và Volume để điều chỉnh điểm số cuối cùng."""
    
    # --- Bộ lọc EMA ---
    ema_cfg = config['FILTER_CONFIG']['EMA_TREND_FILTER']
    if ema_cfg['enabled']:
        # Lấy tham số EMA từ config chung thay vì hardcode
        ema_params = config['INDICATORS_CONFIG']['EMA']
        slow_ema, _ = calculate_emas(df, {'INDICATORS_CONFIG': {'EMA': ema_params}})
        if slow_ema is not None and not slow_ema.empty:
            last_close = df['close'].iloc[-1]
            last_ema = slow_ema.iloc[-1]
            
            if last_close > last_ema: # Xu hướng tăng
                long_score *= ema_cfg['multipliers']['in_trend_multiplier']
                short_score *= ema_cfg['multipliers']['counter_trend_multiplier']
            else: # Xu hướng giảm
                long_score *= ema_cfg['multipliers']['counter_trend_multiplier']
                short_score *= ema_cfg['multipliers']['in_trend_multiplier']

    # --- Bộ lọc Volume ---
    vol_cfg = config['FILTER_CONFIG']['VOLUME_FILTER']
    if vol_cfg['enabled']:
        volume_ma = df['volume'].rolling(window=vol_cfg['params']['ma_period']).mean()
        if not volume_ma.empty and volume_ma.iloc[-1] > 0:
            last_volume = df['volume'].iloc[-1]
            avg_volume = volume_ma.iloc[-1]
            ratio = last_volume / avg_volume

            multiplier = 1.0
            for tier in sorted(vol_cfg['tiered_multipliers'], key=lambda x: x['threshold_ratio']):
                if ratio < tier['threshold_ratio']:
                    multiplier = tier['multiplier']
                    break
            
            long_score *= multiplier
            short_score *= multiplier

    return long_score, short_score

# ==============================================================================
# HÀM TỔNG HỢP TÍN HIỆU CUỐI CÙNG (Hàm chính)
# ==============================================================================

def get_final_signal(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
    """
    Tổng hợp điểm từ tất cả các chỉ báo, áp dụng bộ lọc, và ra quyết định.
    """
    total_long_score = 0.0
    total_short_score = 0.0
    score_details = {}

    # --- BƯỚC 1: TÍNH ĐIỂM THÔ TỪ CÁC CHỈ BÁO TÍN HIỆU ---
    
    # 1. Bollinger Bands
    long_bb, short_bb = get_bb_score(df, config)
    total_long_score += long_bb
    total_short_score += short_bb
    score_details['bb_score'] = f"L:{long_bb:.2f}/S:{short_bb:.2f}"

    # 2. Supertrend
    long_st, short_st = get_supertrend_score(df, config)
    total_long_score += long_st
    total_short_score += short_st
    score_details['st_score'] = f"L:{long_st:.2f}/S:{short_st:.2f}"

    # 3. RSI (ĐÃ THÊM)
    long_rsi, short_rsi = get_rsi_score(df, config)
    total_long_score += long_rsi
    total_short_score += short_rsi
    score_details['rsi_score'] = f"L:{long_rsi:.2f}/S:{short_rsi:.2f}"

    # 4. MACD (ĐÃ THÊM)
    long_macd, short_macd = get_macd_score(df, config)
    total_long_score += long_macd
    total_short_score += short_macd
    score_details['macd_score'] = f"L:{long_macd:.2f}/S:{short_macd:.2f}"

    score_details['raw_long_score'] = total_long_score
    score_details['raw_short_score'] = total_short_score

    # --- BƯỚC 2: ÁP DỤNG CÁC BỘ LỌC XÁC NHẬN ---
    final_long_score, final_short_score = apply_filters(total_long_score, total_short_score, df, config)
    
    score_details['final_long_score'] = final_long_score
    score_details['final_short_score'] = final_short_score

    # --- BƯỚC 3: RA QUYẾT ĐỊNH CUỐI CÙNG ---
    final_signal = 0
    entry_threshold = config['ENTRY_SCORE_THRESHOLD']
    allow_long = config.get('ENABLE_LONG_TRADES', True)
    allow_short = config.get('ENABLE_SHORT_TRADES', True)
    
    if allow_long and final_long_score > final_short_score and final_long_score >= entry_threshold:
        final_signal = 1
        score_details['final_decision'] = f"LONG with score {final_long_score:.2f}"
    elif allow_short and final_short_score > final_long_score and final_short_score >= entry_threshold:
        final_signal = -1
        score_details['final_decision'] = f"SHORT with score {final_short_score:.2f}"
        
    return final_signal, score_details