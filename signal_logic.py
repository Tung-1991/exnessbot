from typing import Dict, List, Tuple, Callable

SCORE_RANGE = 8.0
CLAMP_MAX_SCORE, CLAMP_MIN_SCORE = 8.0, -8.0
RULE_WEIGHTS = {
    "score_rsi_div": 2.5, "score_breakout": 2.5, "score_macd_cross": 2.0,
    "score_bb_reversal": 1.5, "score_reversal_pattern": 1.5, "score_fib_reversal": 1.5,
    "score_volume_spike": 1.0, "score_sr_proximity": 1.0, "score_trend_confirm": 1.0,
    "score_money_flow": 0.5, "score_volatility_penalty": -1.5,
}
def score_trend_confirm(ind: Dict) -> Tuple[float, str]:
    t, adx = ind.get("trend"), ind.get("adx", 0)
    if t == "uptrend" and adx > 23: return 1.0, "Trend Tăng Mạnh"
    if t == "downtrend" and adx > 23: return -1.0, "Trend Giảm Mạnh"
    return 0.0, ""
def score_macd_cross(ind: Dict) -> Tuple[float, str]:
    cross = ind.get("macd_cross")
    if cross == "bullish": return 1.0, "MACD Cắt Lên"
    if cross == "bearish": return -1.0, "MACD Cắt Xuống"
    return 0.0, ""
def score_rsi_div(ind: Dict) -> Tuple[float, str]:
    div = ind.get("rsi_divergence")
    if div == "bullish": return 1.0, "Phân kỳ RSI Tăng"
    if div == "bearish": return -1.0, "Phân kỳ RSI Giảm"
    return 0.0, ""
def score_money_flow(ind: Dict) -> Tuple[float, str]:
    cmf = ind.get("cmf", 0.0)
    if cmf > 0.05: return 1.0, "Dòng tiền Dương"
    if cmf < -0.05: return -1.0, "Dòng tiền Âm"
    return 0.0, ""
def score_volume_spike(ind: Dict) -> Tuple[float, str]:
    v, vma = ind.get("volume"), ind.get("vol_ma20")
    if vma and v > 2.0 * vma: return 1.0, "Volume Đột biến"
    return 0.0, ""
def score_bb_reversal(ind: Dict) -> Tuple[float, str]:
    p, up, lo = ind.get("price"), ind.get("bb_upper"), ind.get("bb_lower")
    if not all([p, up, lo]): return 0.0, ""
    if p > up: return -1.0, "Giá Vượt BB Trên (Đảo chiều)"
    if p < lo: return 1.0, "Giá Dưới BB Dưới (Đảo chiều)"
    return 0.0, ""
def score_reversal_pattern(ind: Dict) -> Tuple[float, str]:
    pat, t = ind.get("candle_pattern"), ind.get("trend")
    if pat == "bullish_engulfing" and t == "downtrend": return 1.0, "Nến Bullish Engulfing"
    if pat == "bearish_engulfing" and t == "uptrend": return -1.0, "Nến Bearish Engulfing"
    return 0.0, ""
def score_breakout(ind: Dict) -> Tuple[float, str]:
    bo = ind.get("breakout_signal")
    if bo == "bullish": return 1.0, "Tín hiệu Breakout Tăng"
    if bo == "bearish": return -1.0, "Tín hiệu Breakout Giảm"
    return 0.0, ""
def score_volatility_penalty(ind: Dict) -> Tuple[float, str]:
    atrp = ind.get("atr_percent", 2.0)
    if atrp > 4.0: return 1.0, "Biến động Cao"
    return 0.0, ""
def score_sr_proximity(ind: Dict) -> Tuple[float, str]:
    p, sup, res = ind.get("price"), ind.get("support_level"), ind.get("resistance_level")
    if not all([p, sup, res]): return 0.0, ""
    if abs(p - sup) / p < 0.005: return 1.0, "Gần Hỗ trợ"
    if abs(p - res) / p < 0.005: return -1.0, "Gần Kháng cự"
    return 0.0, ""
def score_fib_reversal(ind: Dict) -> Tuple[float, str]:
    p, fib = ind.get("price", 0), ind.get("fib_0_618", 0)
    trend = ind.get("trend")
    if not all([p, fib]): return 0.0, ""
    proximity_percent = abs(p - fib) / p
    if trend == "uptrend" and proximity_percent < 0.005: return -1.0, "Gần Fibo cản (Short)"
    if trend == "downtrend" and proximity_percent < 0.005: return 1.0, "Gần Fibo hỗ trợ (Long)"
    return 0.0, ""
RULE_FUNCS: List[Callable[[Dict], Tuple[float, str]]] = [
    score_trend_confirm, score_macd_cross, score_rsi_div, score_money_flow,
    score_volume_spike, score_bb_reversal, score_reversal_pattern, score_breakout,
    score_volatility_penalty, score_sr_proximity, score_fib_reversal,
]
def check_signal(indicators: dict) -> Dict:
    if not indicators or not indicators.get("price"):
        return {"raw_tech_score": 0.0, "reason": "Thiếu dữ liệu."}
    total_score, reasons = 0.0, []
    for func in RULE_FUNCS:
        direction, reason_text = func(indicators)
        if direction != 0:
            func_name = func.__name__
            weight = RULE_WEIGHTS.get(func_name, 0.0)
            rule_score = direction * weight
            total_score += rule_score
            reasons.append(f"{reason_text}({rule_score:+.1f})")
    final_score = max(CLAMP_MIN_SCORE, min(total_score, CLAMP_MAX_SCORE))
    final_reason = f"Điểm: {final_score:.2f} | " + " ".join(reasons) if reasons else "Không có tín hiệu."
    return {"raw_tech_score": final_score, "reason": final_reason}