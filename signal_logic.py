from typing import Dict, List, Tuple, Callable

try:
    from trade_advisor import FULL_CONFIG
    SCORE_RANGE: float = float(FULL_CONFIG.get("SCORE_RANGE", 8.0))
except Exception:
    SCORE_RANGE = 8.0

CLAMP_MAX_SCORE, CLAMP_MIN_SCORE = 8.0, -8.0

RULE_WEIGHTS = {
    "score_rsi_div": 2.0,
    "score_breakout": 2.0,
    "score_trend": 1.5,
    "score_macd": 1.5,
    "score_doji": 1.5,
    "score_bb": 1.5,
    "score_support_resistance": 1.5,
    "score_cmf": 1.0,
    "score_volume": 1.0,
    "score_candle_pattern": 1.0,
    "score_atr_vol": 1.0,
    "score_ema200": 0.5,
    "score_rsi_multi": 0.5,
    "score_adx": 0.5,
}

def score_trend(ind: Dict) -> Tuple[float, str]:
    t = ind.get("trend")
    if t == "uptrend": return 1.0, "Trend Tăng"
    if t == "downtrend": return -1.0, "Trend Giảm"
    return 0.0, ""

def score_ema200(ind: Dict) -> Tuple[float, str]:
    p, ema = ind.get("closed_candle_price"), ind.get("ema_200")
    if not ema or not p: return 0.0, ""
    return (1.0, "Giá > EMA200") if p > ema else (-1.0, "Giá < EMA200")

def score_rsi_multi(ind: Dict) -> Tuple[float, str]:
    r1h, r4h = ind.get("rsi_1h"), ind.get("rsi_4h")
    if r1h is None or r4h is None: return 0.0, ""
    if r1h > 60 and r4h > 55: return 1.0, "RSI đa khung mạnh"
    if r1h < 40 and r4h < 45: return -1.0, "RSI đa khung yếu"
    return 0.0, ""

def score_macd(ind: Dict) -> Tuple[float, str]:
    cross = ind.get("macd_cross")
    if cross == "bullish": return 1.0, "MACD cắt lên"
    if cross == "bearish": return -1.0, "MACD cắt xuống"
    return 0.0, ""

def score_rsi_div(ind: Dict) -> Tuple[float, str]:
    div = ind.get("rsi_divergence")
    if div == "bullish": return 1.0, "Phân kỳ RSI tăng"
    if div == "bearish": return -1.0, "Phân kỳ RSI giảm"
    return 0.0, ""

def score_cmf(ind: Dict) -> Tuple[float, str]:
    cmf = ind.get("cmf")
    if cmf is None: return 0.0, ""
    if cmf > 0.05: return 1.0, "Dòng tiền CMF dương"
    if cmf < -0.05: return -1.0, "Dòng tiền CMF âm"
    return 0.0, ""

# 🟢 Đã sửa: Hàm này giờ đây trả về điểm có hướng dựa trên trend
def score_adx(ind: Dict) -> Tuple[float, str]:
    adx, trend = ind.get("adx"), ind.get("trend")
    if adx is not None and adx > 25:
        if trend == "uptrend":
            return 1.0, f"ADX > 25 (Trend Tăng Mạnh)"
        elif trend == "downtrend":
            return -1.0, f"ADX > 25 (Trend Giảm Mạnh)"
    return 0.0, ""

# 🟢 Đã sửa: Hàm này giờ đây trả về điểm có hướng dựa trên thân nến
def score_volume(ind: Dict) -> Tuple[float, str]:
    v, vma = ind.get("volume"), ind.get("vol_ma20")
    if not vma: return 0.0, ""
    if v > 1.8 * vma:
        closed_price, open_price = ind.get("closed_candle_price"), ind.get("open")
        if closed_price > open_price:
            return 1.0, "Volume đột biến (Tăng)"
        elif closed_price < open_price:
            return -1.0, "Volume đột biến (Giảm)"
    return 0.0, ""

def score_bb(ind: Dict) -> Tuple[float, str]:
    p, up, lo = ind.get("closed_candle_price"), ind.get("bb_upper"), ind.get("bb_lower")
    if not all([p, up, lo]): return 0.0, ""
    if p < lo: return 1.0, "Giá dưới BB dưới (Mua)"
    if p > up: return -1.0, "Giá trên BB trên (Bán)"
    return 0.0, ""

def score_doji(ind: Dict) -> Tuple[float, str]:
    t, d = ind.get("trend"), (ind.get("doji_type") or "").lower()
    if t == "uptrend" and d in {"gravestone", "shooting_star"}: return -1.0, f"Doji đỉnh ({d})"
    if t == "downtrend" and d in {"dragonfly", "hammer"}: return 1.0, f"Doji đáy ({d})"
    return 0.0, ""

def score_breakout(ind: Dict) -> Tuple[float, str]:
    bo = ind.get("breakout_signal")
    if bo == "bullish": return 1.0, "Tín hiệu Breakout tăng"
    if bo == "bearish": return -1.0, "Tín hiệu Breakout giảm"
    return 0.0, ""

def score_atr_vol(ind: Dict) -> Tuple[float, str]:
    atrp = ind.get("atr_percent", 2.0)
    if atrp > 5.0: return -1.0, "Biến động ATR% cao (Rủi ro)"
    return 0.0, ""

def score_support_resistance(ind: Dict) -> Tuple[float, str]:
    p, sup, res = ind.get("closed_candle_price"), ind.get("support_level"), ind.get("resistance_level")
    if not all([p, sup, res]): return 0.0, ""
    if abs(p - sup) / p < 0.015: return 1.0, "Giá gần Hỗ trợ"
    if abs(p - res) / p < 0.015: return -1.0, "Giá gần Kháng cự"
    return 0.0, ""

def score_candle_pattern(ind: Dict) -> Tuple[float, str]:
    pat, t = ind.get("candle_pattern"), ind.get("trend")
    if pat == "bullish_engulfing" and t != "uptrend": return 1.0, "Nến Bullish Engulfing"
    if pat == "bearish_engulfing" and t != "downtrend": return -1.0, "Nến Bearish Engulfing"
    return 0.0, ""

RULE_FUNCS: List[Callable[[Dict], Tuple[float, str]]] = [
    score_trend, score_ema200, score_rsi_multi, score_macd, score_rsi_div,
    score_cmf, score_adx, score_volume, score_bb, score_doji, score_breakout,
    score_atr_vol, score_support_resistance, score_candle_pattern,
]

LEVEL_THRESHOLDS = {
    "CRITICAL": 0.625 * SCORE_RANGE,
    "WARNING": 0.375 * SCORE_RANGE,
    "ALERT": 0.125 * SCORE_RANGE,
}

def _map_level_tag(score: float, rsi: float) -> Tuple[str, str]:
    level, tag = "HOLD", "neutral"
    abs_score = abs(score)

    if abs_score >= LEVEL_THRESHOLDS["CRITICAL"]: level = "CRITICAL"
    elif abs_score >= LEVEL_THRESHOLDS["WARNING"]: level = "WARNING"
    elif abs_score >= LEVEL_THRESHOLDS["ALERT"]: level = "ALERT"
    else: level = "WATCHLIST"
    
    if score > LEVEL_THRESHOLDS["ALERT"]:
        tag = "weak_buy"
        if level == "WARNING": tag = "can_buy"
        if level == "CRITICAL": tag = "strong_buy"
        if level in ["CRITICAL", "WARNING"] and rsi > 70: tag = "buy_overheat"
    elif score < -LEVEL_THRESHOLDS["ALERT"]:
        tag = "weak_sell"
        if level == "WARNING": tag = "can_sell"
        if level == "CRITICAL": tag = "strong_sell"
        if level in ["CRITICAL", "WARNING"] and rsi < 30: tag = "sell_oversold"
        
    return level, tag

def check_signal(indicators: dict) -> Dict:
    if not indicators or not indicators.get("price"):
        return {"level": "HOLD", "tag": "no_data", "reason": "Thiếu dữ liệu đầu vào.", "raw_tech_score": 0.0}

    total_score = 0.0
    reasons = []

    for func in RULE_FUNCS:
        direction, reason_text = func(indicators)
        if direction != 0:
            func_name = func.__name__
            weight = RULE_WEIGHTS.get(func_name, 0.0)
            
            # 🟢 Đã sửa: Bỏ logic cũ, giờ đây direction sẽ quyết định hướng điểm số
            rule_score = direction * weight
            total_score += rule_score
            reasons.append(f"{reason_text} ({rule_score:+.1f})")
    
    final_score = max(CLAMP_MIN_SCORE, min(total_score, CLAMP_MAX_SCORE))
    
    level, tag = _map_level_tag(final_score, indicators.get("rsi_14", 50.0))
    final_reason = f"Tổng điểm: {final_score:.1f} | " + " ".join(reasons) if reasons else "Không có tín hiệu rõ ràng."

    return {
        "level": level,
        "tag": tag,
        "reason": final_reason,
        "raw_tech_score": final_score
    }