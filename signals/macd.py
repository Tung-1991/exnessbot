# -*- coding: utf-8 -*-
# signals/macd.py (v4.0 - Phase 4)

import pandas as pd
from typing import Optional, Dict, Any, Tuple

def calculate_macd(df: pd.DataFrame, fast_ema: int = 12, slow_ema: int = 26, signal_sma: int = 9) -> Optional[Tuple[pd.Series, pd.Series]]:
    """
    Tính toán đường MACD và đường Signal.
    Hàm này không thay đổi.
    """
    if 'close' not in df.columns:
        return None

    ema_fast = df['close'].ewm(span=fast_ema, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_ema, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_sma, adjust=False).mean()
    
    return macd_line, signal_line

def get_macd_score(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[float, float]:
    """
    Tính điểm thô cho LONG và SHORT dựa trên tín hiệu giao cắt của MACD.
    Hàm này đã được viết lại hoàn toàn.
    """
    cfg = config['SCORING_CONFIG']['MACD']
    if not cfg['enabled']:
        return 0.0, 0.0

    lines = calculate_macd(
        df,
        fast_ema=cfg['params']['fast_ema'],
        slow_ema=cfg['params']['slow_ema'],
        signal_sma=cfg['params']['signal_sma']
    )
    
    if lines is None or len(df) < 2:
        return 0.0, 0.0

    macd_line, signal_line = lines
    long_score, short_score = 0.0, 0.0
    
    # Lấy dữ liệu của 2 cây nến gần nhất để xác định sự giao cắt
    prev_macd = macd_line.iloc[-2]
    prev_signal = signal_line.iloc[-2]
    last_macd = macd_line.iloc[-1]
    last_signal = signal_line.iloc[-1]
    
    # --- Logic tính điểm ---
    score_on_crossover = cfg['score_levels'].get('crossover', 0)

    # Tín hiệu MUA (Bullish Crossover): MACD cắt lên trên đường Signal
    if prev_macd < prev_signal and last_macd > last_signal:
        long_score = score_on_crossover
        
    # Tín hiệu BÁN (Bearish Crossover): MACD cắt xuống dưới đường Signal
    elif prev_macd > prev_signal and last_macd < last_signal:
        short_score = score_on_crossover
        
    # Chuẩn hóa điểm theo trọng số
    # Giả định điểm tối đa có thể có là giá trị 'crossover'
    max_possible_score = score_on_crossover
    
    final_long_score = (long_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0
    final_short_score = (short_score / max_possible_score) * cfg['weight'] if max_possible_score > 0 else 0

    return final_long_score, final_short_score