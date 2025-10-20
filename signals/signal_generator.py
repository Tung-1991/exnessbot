# -*- coding: utf-8 -*-
# signals/signal_generator.py

import pandas as pd
from typing import Dict, Any, Tuple

# Import tất cả các hàm tính điểm và bộ lọc từ các module con
# Tuân thủ quy tắc "Import từ thư mục gốc"
from signals.bollinger_bands import get_bb_signal
from signals.rsi import get_rsi_score
from signals.macd import get_macd_score
from signals.supertrend import get_supertrend_score
from signals.ema import get_ema_score
from signals.volume import get_volume_score

def get_final_signal(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
    """
    Tổng hợp điểm từ tất cả các chỉ báo, áp dụng các bộ lọc,
    và đưa ra quyết định giao dịch cuối cùng.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu giá.
        config (Dict[str, Any]): Toàn bộ file cấu hình.

    Returns:
        Tuple[int, Dict[str, float]]: 
            - int: Tín hiệu cuối cùng (+1 Mua, -1 Bán, 0 Đứng yên).
            - Dict: Chi tiết điểm số của từng chỉ báo để hiển thị.
    """
    score_details = {}
    weights = config['SCORING_WEIGHTS']

    # --- BƯỚC 1: THU THẬP ĐIỂM TỪ CÁC CHỈ BÁO CHÍNH ---
    
    # Lưu ý: get_bb_signal trả về +1/-1/0, cần nhân với trọng số
    bb_config = config['INDICATORS_CONFIG']['BB']
    bb_raw_signal = get_bb_signal(
        df, 
        period=bb_config['PERIOD'], 
        std_dev=bb_config['STD_DEV']
    ) # <== ĐÃ SỬA
    score_details['bb_score'] = bb_raw_signal * weights['BB_TRIGGER_SCORE']
    
    # Các hàm khác đã trả về điểm số đã nhân trọng số
    score_details['rsi_score'] = get_rsi_score(df, config)
    score_details['macd_score'] = get_macd_score(df, config)
    score_details['supertrend_score'] = get_supertrend_score(df, config)
    
    # Tính tổng điểm sơ bộ
    preliminary_total_score = sum(score_details.values())
    
    # --- BƯỚC 2: XÁC ĐỊNH HƯỚNG TÍN HIỆU DỰ KIẾN ---
    signal_direction = 0
    if preliminary_total_score > 0:
        signal_direction = 1  # Hướng MUA
    elif preliminary_total_score < 0:
        signal_direction = -1 # Hướng BÁN

    # --- BƯỚC 3: ÁP DỤNG ĐIỂM PHẠT TỪ CÁC "NGƯỜI GÁC CỔNG" ---
    
    # Áp dụng điểm phạt từ EMA (chỉ phạt khi đi ngược xu hướng)
    score_details['ema_penalty'] = get_ema_score(df, config, signal_direction)
    
    # Áp dụng điểm phạt từ Volume (chỉ phạt khi volume yếu)
    score_details['volume_penalty'] = get_volume_score(df, config)
    
    # --- BƯỚC 4: TÍNH TỔNG ĐIỂM CUỐI CÙNG VÀ RA QUYẾT ĐỊNH ---
    
    final_score = preliminary_total_score + score_details['ema_penalty'] + score_details['volume_penalty']
    score_details['final_score'] = final_score
    
    final_signal = 0
    entry_threshold = config['ENTRY_SCORE_THRESHOLD']
    
    if final_score >= entry_threshold:
        final_signal = 1  # QUYẾT ĐỊNH MUA
    elif final_score <= -entry_threshold:
        final_signal = -1 # QUYẾT ĐỊNH BÁN
        
    return final_signal, score_details