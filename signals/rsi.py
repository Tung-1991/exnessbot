# -*- coding: utf-8 -*-
# signals/rsi.py (v4.0 - Phase 4)

import pandas as pd
from typing import Optional, Dict, Any, Tuple

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """
    Tính toán chỉ báo Relative Strength Index (RSI).
    Hàm này không thay đổi vì logic tính toán RSI là không đổi.
    """
    if 'close' not in df.columns:
        return None

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_rsi_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên các cấp độ RSI trong config.
    Hàm này đã được viết lại hoàn toàn.
    """
    cfg = config['SCORING_CONFIG']['RSI']
    if not cfg['enabled']:
        return 0.0, 0.0

    rsi_series = calculate_rsi(df, period=cfg['params']['period'])
    if rsi_series is None or rsi_series.empty:
        return 0.0, 0.0

    last_rsi = rsi_series.iloc[-1]
    long_score, short_score = 0.0, 0.0
    
    # --- Tính điểm cho phe MUA (LONG) ---
    # Logic: RSI càng thấp (càng quá bán), điểm càng cao.
    # Giả định 'score_levels' được sắp xếp từ yếu đến mạnh
    if 'extreme' in cfg['score_levels'] and last_rsi < cfg['score_levels']['extreme']['threshold'][0]:
        long_score = cfg['score_levels']['extreme']['score']
    
    if 'deep' in cfg['score_levels'] and last_rsi < cfg['score_levels']['deep']['threshold'][0]:
        long_score = cfg['score_levels']['deep']['score'] # Ghi đè điểm cao hơn nếu thỏa mãn điều kiện sâu hơn

    # --- Tính điểm cho phe BÁN (SHORT) ---
    # Logic: RSI càng cao (càng quá mua), điểm càng cao.
    if 'extreme' in cfg['score_levels'] and last_rsi > cfg['score_levels']['extreme']['threshold'][1]:
        short_score = cfg['score_levels']['extreme']['score']
        
    if 'deep' in cfg['score_levels'] and last_rsi > cfg['score_levels']['deep']['threshold'][1]:
        short_score = cfg['score_levels']['deep']['score']

    # Chuẩn hóa điểm theo trọng số (weight).
    # Ví dụ: Nếu điểm thô là 15, weight là 10. Điểm cuối = 10 * (15 / 10) = 15.
    # Tuy nhiên, để đơn giản, chúng ta sẽ để signal_generator xử lý việc nhân weight.
    # Hàm này chỉ trả về điểm thô theo thang điểm của nó.
    # signal_generator sẽ chuẩn hóa theo thang điểm 100.
    
    # Để đơn giản hóa, hàm này sẽ trả về điểm thô, và signal_generator sẽ nhân với weight
    # Chúng ta cần chuẩn hóa thang điểm. Giả sử điểm tối đa có thể đạt là 15 (từ deep).
    max_possible_score = max(level['score'] for level in cfg['score_levels'].values())
    
    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0

    return final_long_score, final_short_score