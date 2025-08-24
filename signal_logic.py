# SỬA các hàm hiện có để phù hợp 5m:

def score_trend(ind: Dict) -> Tuple[float, str]:
    """Trend cho 5m - chấp nhận weak trend"""
    t = ind.get("trend")
    ema_9 = ind.get("ema_9", 0)
    ema_20 = ind.get("ema_20", 0)
    
    # Thay vì chỉ dựa vào trend category
    # Xem xét độ lệch EMA
    if ema_9 > 0 and ema_20 > 0:
        ema_diff_pct = ((ema_9 - ema_20) / ema_20) * 100
        
        if abs(ema_diff_pct) < 0.1:  # Sideways
            return 0.0, ""
        elif ema_diff_pct > 0.2:  # Weak uptrend cũng được điểm
            return 0.8, "Trend tăng yếu"
        elif ema_diff_pct > 0.5:
            return 1.2, "Trend tăng mạnh"
        elif ema_diff_pct < -0.2:
            return -0.8, "Trend giảm yếu"
        elif ema_diff_pct < -0.5:
            return -1.2, "Trend giảm mạnh"
    
    return 0.0, ""

def score_momentum_5m(ind: Dict) -> Tuple[float, str]:
    """Momentum ngắn hạn cho 5m - THÊM MỚI"""
    rsi = ind.get("rsi_14", 50)
    macd_hist = ind.get("macd_hist", 0)
    
    # RSI momentum
    rsi_score = 0
    if 30 < rsi < 40:
        rsi_score = 0.5  # Động lượng yếu nhưng có tiềm năng
    elif 40 < rsi < 60:
        rsi_score = 0  # Neutral
    elif 60 < rsi < 70:
        rsi_score = -0.5
    elif rsi <= 30:
        rsi_score = 1.0  # Oversold momentum
    elif rsi >= 70:
        rsi_score = -1.0  # Overbought momentum
    
    # MACD histogram momentum  
    macd_score = 0
    if macd_hist > 0:
        macd_score = 0.3
    elif macd_hist < 0:
        macd_score = -0.3
    
    total = rsi_score + macd_score
    
    if total > 0.5:
        return total, f"Momentum tăng (RSI:{rsi:.0f})"
    elif total < -0.5:
        return total, f"Momentum giảm (RSI:{rsi:.0f})"
    
    return 0.0, ""

def score_price_action_5m(ind: Dict) -> Tuple[float, str]:
    """Price action patterns cho 5m - THÊM MỚI"""
    high = ind.get("high", 0)
    low = ind.get("low", 0)
    close = ind.get("closed_candle_price", 0)
    open_price = ind.get("open", 0)
    
    if not all([high, low, close, open_price]):
        return 0.0, ""
    
    # Tính các yếu tố price action
    body = abs(close - open_price)
    upper_wick = high - max(close, open_price)
    lower_wick = min(close, open_price) - low
    full_range = high - low
    
    if full_range == 0:
        return 0.0, ""
    
    # Pin bar patterns
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        return 1.5, "Bullish pin bar"
    elif upper_wick > body * 2 and lower_wick < body * 0.5:
        return -1.5, "Bearish pin bar"
    
    # Engulfing với volume
    volume = ind.get("volume", 0)
    vol_ma = ind.get("vol_ma20", 1)
    if volume > vol_ma * 1.5:  # Volume confirmation
        if close > open_price and body > full_range * 0.7:
            return 1.0, "Bullish momentum candle"
        elif close < open_price and body > full_range * 0.7:
            return -1.0, "Bearish momentum candle"
    
    return 0.0, ""

def score_mean_reversion_5m(ind: Dict) -> Tuple[float, str]:
    """Mean reversion setup cho 5m - THÊM MỚI"""
    price = ind.get("closed_candle_price", 0)
    bb_middle = ind.get("bb_middle", 0)
    atr = ind.get("atr", 0)
    
    if not all([price, bb_middle, atr]):
        return 0.0, ""
    
    # Khoảng cách từ giá đến BB middle (mean)
    distance_from_mean = abs(price - bb_middle)
    distance_in_atr = distance_from_mean / atr if atr > 0 else 0
    
    # Setup mean reversion khi giá xa mean
    if distance_in_atr > 2:  # Giá quá xa mean
        if price < bb_middle:
            return 1.5, "Mean reversion BUY setup"
        else:
            return -1.5, "Mean reversion SELL setup"
    
    return 0.0, ""

# CẬP NHẬT RULE_WEIGHTS - ƯU TIÊN COMBO CHO 5M:
RULE_WEIGHTS = {
    # COMBO CHÍNH CHO 5M (cao nhất)
    "score_price_action_5m": 2.5,      # Price action là VÀNG
    "score_momentum_5m": 2.0,          # Momentum ngắn hạn
    "score_mean_reversion_5m": 2.0,    # Mean reversion setups
    
    # Vẫn quan trọng (đã có trong hệ thống)
    "score_rsi_div": 2.0,              # Divergence vẫn tốt
    "score_support_resistance": 2.0,   # SR levels quan trọng
    "score_breakout": 1.5,             # Breakout (nếu có)
    "score_candle_pattern": 1.5,       # Patterns
    "score_doji": 1.5,                 # Doji patterns
    "score_volume": 1.5,               # Volume spikes
    
    # Giảm xuống cho 5m
    "score_trend": 0.8,                # Trend yếu hơn
    "score_macd": 0.5,                 # MACD chậm
    "score_bb": 0.5,                   # BB đã có trong EZ filter
    "score_cmf": 0.5,                  
    "score_atr_vol": 0.3,              
    "score_ema200": 0.2,               # Gần như vô dụng
    "score_rsi_multi": 0.5,            
    "score_adx": 0.3,                  # ADX quá chậm
}

# Thêm các hàm mới vào RULE_FUNCS:
RULE_FUNCS: List[Callable[[Dict], Tuple[float, str]]] = [
    # Ưu tiên combo 5m
    score_price_action_5m,
    score_momentum_5m,
    score_mean_reversion_5m,
    
    # Các rules hiện có
    score_trend,  # Đã sửa cho 5m
    score_rsi_div,
    score_support_resistance,
    score_breakout,
    score_candle_pattern,
    score_doji,
    score_volume,
    
    # Ít quan trọng
    score_macd,
    score_bb,
    score_cmf,
    score_atr_vol,
    score_ema200,
    score_rsi_multi,
    score_adx,
]