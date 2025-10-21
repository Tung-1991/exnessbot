# -*- coding: utf-8 -*-
# signals/ema.py (v5.0 - Logic Bậc Thang 5 Cấp)

import pandas as pd
from typing import Optional, Dict, Any, Tuple

# Import hàm tính ATR để đo khoảng cách
from signals.atr import calculate_atr

def calculate_emas(df: pd.DataFrame, slow_period: int, fast_period: int) -> Optional[Tuple[pd.Series, pd.Series]]:
    """
    Tính toán các đường EMA. Hàm được sửa lại để nhận tham số trực tiếp.
    """
    if 'close' not in df.columns:
        return None
    
    slow_ema = df['close'].ewm(span=slow_period, adjust=False).mean()
    fast_ema = df['close'].ewm(span=fast_period, adjust=False).mean()
    
    return slow_ema, fast_ema

def get_ema_adjustment_score(df: pd.DataFrame, config: Dict[str, Any]) -> float:
    """
    Tính điểm thưởng/phạt dựa trên vị trí của giá so với đường EMA 200.
    Sử dụng cơ chế bậc thang 5 cấp dựa trên khoảng cách ATR.
    """
    try:
        cfg = config['ADJUSTMENT_SCORE_CONFIG']['EMA_TREND_FILTER']
        atr_cfg = config['INDICATORS_CONFIG']['ATR']
    except KeyError:
        return 0.0

    if not cfg.get('enabled', False) or len(df) < cfg['params']['period']:
        return 0.0

    # Tính toán EMA
    emas = calculate_emas(df, slow_period=cfg['params']['period'], fast_period=50) # Fast EMA tạm thời không dùng
    if emas is None:
        return 0.0
    slow_ema, _ = emas
    
    # Tính toán ATR
    atr_series = calculate_atr(df, period=atr_cfg['PERIOD'])
    if atr_series is None or pd.isna(atr_series.iloc[-1]) or atr_series.iloc[-1] == 0:
        return 0.0

    last_close = df['close'].iloc[-1]
    last_slow_ema = slow_ema.iloc[-1]
    last_atr = atr_series.iloc[-1]

    # Tính khoảng cách từ giá đến EMA bằng đơn vị ATR
    # Dương: giá trên EMA (thuận xu hướng LONG)
    # Âm: giá dưới EMA (ngược xu hướng LONG)
    distance_in_atr = (last_close - last_slow_ema) / last_atr

    score = 0.0
    
    # Sắp xếp các bậc thang để duyệt từ điều kiện chặt nhất
    # Cho phe LONG: duyệt từ threshold_atr cao nhất xuống thấp nhất
    # Cho phe SHORT: duyệt từ threshold_atr thấp nhất lên cao nhất
    long_tiers = sorted(cfg.get('score_tiers', []), key=lambda x: x['threshold_atr'], reverse=True)

    # Logic chấm điểm sẽ được xử lý trong signal_generator để phân biệt LONG/SHORT
    # Hàm này chỉ trả về một "chỉ số môi trường" chung.
    # signal_generator sẽ quyết định điểm này là thưởng hay phạt.
    # Ví dụ: distance_in_atr = 1.5 (rất thuận LONG).
    # -> Phe LONG sẽ được +15, phe SHORT sẽ bị -15.
    
    # Để đơn giản hóa, hàm này sẽ trả về điểm trực tiếp cho cả 2 phe
    # Logic này sẽ được signal_generator sử dụng
    
    long_score = 0
    short_score = 0

    # --- Điểm cho phe LONG ---
    for tier in long_tiers:
        if distance_in_atr >= tier['threshold_atr']:
            long_score = tier['score']
            break
            
    # --- Điểm cho phe SHORT (logic ngược lại) ---
    for tier in long_tiers:
        # Nếu distance_in_atr là -1.5 (rất thuận SHORT), nó sẽ khớp với tier có score -15 cho LONG
        # Nhưng với phe SHORT, đây là điểm cộng
        if -distance_in_atr >= tier['threshold_atr']:
             short_score = tier['score']
             break

    # Hàm này sẽ được gọi bởi signal_generator, nên nó sẽ trả về điểm cho cả 2 phe
    # Tuy nhiên, để cấu trúc rõ ràng, chúng ta sẽ để signal_generator xử lý việc đảo dấu.
    # Hàm này chỉ trả về 1 điểm duy nhất dựa trên trạng thái của thị trường.
    final_score = 0
    for tier in long_tiers:
        # Giả định threshold_atr trong config là cho phe LONG
        if distance_in_atr >= tier['threshold_atr']:
            final_score = tier['score']
            break
            
    return final_score # Trả về điểm thô (+15, -10, 0...)