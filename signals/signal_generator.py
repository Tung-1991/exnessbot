# -*- coding: utf-8 -*-
# signals/signal_generator.py (v5.0 - Bộ Luật V2.3)

import pandas as pd
from typing import Dict, Any, Tuple

# --- BƯỚC 1: IMPORT TẤT CẢ CÁC HÀM TÍNH ĐIỂM ---

# Import các hàm tính "Điểm Khởi Tạo"
from signals.bollinger_bands import get_bb_score
from signals.rsi import get_rsi_score
from signals.macd import get_macd_score

# Import các hàm tính "Điểm Điều Chỉnh"
from signals.ema import get_ema_adjustment_score
from signals.supertrend import get_supertrend_adjustment_score
from signals.volume import get_volume_adjustment_score

# ==============================================================================
# HÀM TỔNG HỢP TÍN HIỆU CUỐI CÙNG (HÀM CHÍNH)
# ==============================================================================

def get_final_signal(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """
    Tổng hợp điểm từ tất cả các chỉ báo theo "Bộ Luật V2.3",
    áp dụng thưởng/phạt, và ra quyết định giao dịch cuối cùng.
    """
    # --- KHỞI TẠO CÁC BIẾN ---
    raw_long_score, raw_short_score = 0.0, 0.0
    adj_long_score, adj_short_score = 0.0, 0.0
    
    # Dictionary để lưu điểm chi tiết cho việc log và backtest
    score_details = {
        "raw": {"long": {}, "short": {}},
        "adj": {"long": {}, "short": {}},
        "final": {}
    }

    # --- BƯỚC 2: TÍNH ĐIỂM KHỞI TẠO (RAW SCORE) ---
    
    # 2.1 Bollinger Bands
    bb_long, bb_short = get_bb_score(df, config)
    raw_long_score += bb_long
    raw_short_score += bb_short
    score_details["raw"]["long"]["BB"] = bb_long
    score_details["raw"]["short"]["BB"] = bb_short

    # 2.2 RSI
    rsi_long, rsi_short = get_rsi_score(df, config)
    raw_long_score += rsi_long
    raw_short_score += rsi_short
    score_details["raw"]["long"]["RSI"] = rsi_long
    score_details["raw"]["short"]["RSI"] = rsi_short

    # 2.3 MACD
    macd_long, macd_short = get_macd_score(df, config)
    raw_long_score += macd_long
    raw_short_score += macd_short
    score_details["raw"]["long"]["MACD"] = macd_long
    score_details["raw"]["short"]["MACD"] = macd_short

    score_details["raw"]["long_total"] = raw_long_score
    score_details["raw"]["short_total"] = raw_short_score

    # --- BƯỚC 3: TÍNH ĐIỂM ĐIỀU CHỈNH (ADJUSTMENT SCORE) ---

    # 3.1 EMA Trend Filter
    ema_score = get_ema_adjustment_score(df, config)
    # Nếu ema_score > 0 (thuận xu hướng tăng) -> thưởng LONG, phạt SHORT
    # Nếu ema_score < 0 (thuận xu hướng giảm) -> phạt LONG, thưởng SHORT
    adj_long_score += ema_score
    adj_short_score -= ema_score # Logic đảo ngược
    score_details["adj"]["long"]["EMA"] = ema_score
    score_details["adj"]["short"]["EMA"] = -ema_score

    # 3.2 Supertrend Filter
    st_score = get_supertrend_adjustment_score(df, config)
    # Logic tương tự EMA
    adj_long_score += st_score
    adj_short_score -= st_score
    score_details["adj"]["long"]["Supertrend"] = st_score
    score_details["adj"]["short"]["Supertrend"] = -st_score

    # 3.3 Volume Filter
    vol_score = get_volume_adjustment_score(df, config)
    # Volume xác nhận cho cả hai phe
    # Nếu vol_score > 0 (volume mạnh) -> thưởng cho cả hai
    # Nếu vol_score < 0 (volume yếu) -> phạt cả hai
    adj_long_score += vol_score
    adj_short_score += vol_score
    score_details["adj"]["long"]["Volume"] = vol_score
    score_details["adj"]["short"]["Volume"] = vol_score
    
    score_details["adj"]["long_total"] = adj_long_score
    score_details["adj"]["short_total"] = adj_short_score

    # --- BƯỚC 4: TÍNH ĐIỂM CUỐI CÙNG VÀ RA QUYẾT ĐỊNH ---
    final_long_score = raw_long_score + adj_long_score
    final_short_score = raw_short_score + adj_short_score
    
    score_details["final"]["long"] = final_long_score
    score_details["final"]["short"] = final_short_score

    final_signal = 0
    final_score = 0
    
    try:
        entry_threshold = config['ENTRY_SCORE_THRESHOLD']
        allow_long = config.get('ENABLE_LONG_TRADES', True)
        allow_short = config.get('ENABLE_SHORT_TRADES', True)
    except KeyError:
        return 0, {}

    # So sánh và quyết định
    if allow_long and final_long_score > final_short_score and final_long_score >= entry_threshold:
        final_signal = 1 # Tín hiệu MUA
        final_score = final_long_score
    elif allow_short and final_short_score > final_long_score and final_short_score >= entry_threshold:
        final_signal = -1 # Tín hiệu BÁN
        final_score = final_short_score
        
    score_details["final"]["decision_score"] = final_score
    score_details["final"]["signal"] = final_signal

    return final_signal, score_details