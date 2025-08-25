# -*- coding: utf-8 -*-
from typing import Dict, Tuple, List, Callable

# ==============================================================================
# =================== CÁC HÀM TÍNH ĐIỂM RIÊNG LẺ (RULES) ===================
# ==============================================================================
# NOTE: Đây là những hàm bạn đã cung cấp, tôi chỉ giữ lại và sắp xếp.
# Bạn cần tự định nghĩa các hàm còn thiếu như score_rsi_div, score_support_resistance...
# Tôi sẽ thêm vào một vài hàm ví dụ để code chạy được.

def score_trend(ind: Dict) -> Tuple[float, str]:
    """Trend cho 5m - chấp nhận weak trend"""
    ema_9 = ind.get("ema_9", 0)
    ema_20 = ind.get("ema_20", 0)
    
    if ema_9 > 0 and ema_20 > 0:
        ema_diff_pct = ((ema_9 - ema_20) / ema_20) * 100
        
        if abs(ema_diff_pct) < 0.05: return 0.0, ""
        elif ema_diff_pct > 0.1: return 0.8, "Trend tăng yếu"
        elif ema_diff_pct > 0.4: return 1.2, "Trend tăng mạnh"
        elif ema_diff_pct < -0.1: return -0.8, "Trend giảm yếu"
        elif ema_diff_pct < -0.4: return -1.2, "Trend giảm mạnh"
    
    return 0.0, ""

def score_momentum_5m(ind: Dict) -> Tuple[float, str]:
    """Momentum ngắn hạn cho 5m"""
    rsi = ind.get("rsi_14", 50)
    macd_hist = ind.get("macd_hist", 0)
    
    rsi_score = 0
    if rsi <= 30: rsi_score = 1.2
    elif rsi <= 40: rsi_score = 0.6
    elif rsi >= 70: rsi_score = -1.2
    elif rsi >= 60: rsi_score = -0.6
    
    macd_score = 0
    if macd_hist > 0: macd_score = 0.4
    elif macd_hist < 0: macd_score = -0.4
    
    total = rsi_score + macd_score
    
    if total > 0.5: return total, f"Momentum tăng (RSI:{rsi:.0f})"
    elif total < -0.5: return total, f"Momentum giảm (RSI:{rsi:.0f})"
    
    return 0.0, ""

def score_price_action_5m(ind: Dict) -> Tuple[float, str]:
    """Price action patterns cho 5m. Ví dụ: Nến Hammer ở đáy BB"""
    high, low, close, open_price = ind.get("high", 0), ind.get("low", 0), ind.get("closed_candle_price", 0), ind.get("open", 0)
    bb_lower, bb_upper = ind.get("bb_lower", 0), ind.get("bb_upper", 0)
    
    if not all([high, low, close, open_price, bb_lower, bb_upper]): return 0.0, ""

    body = abs(close - open_price)
    upper_wick = high - max(close, open_price)
    lower_wick = min(close, open_price) - low
    full_range = high - low
    
    if full_range == 0: return 0.0, ""
    
    # [LOGIC MỚI] Nến Hammer/Shooting Star gần vùng BB
    is_near_bb_low = abs(low - bb_lower) / full_range < 0.2
    is_near_bb_high = abs(high - bb_upper) / full_range < 0.2

    # Bullish Pin Bar (Hammer)
    if lower_wick > body * 2 and upper_wick < body * 0.7:
        score = 1.5
        if is_near_bb_low: score = 2.5 # Tăng điểm mạnh nếu ở đáy BB
        return score, "Bullish Pin Bar"

    # Bearish Pin Bar (Shooting Star)
    elif upper_wick > body * 2 and lower_wick < body * 0.7:
        score = -1.5
        if is_near_bb_high: score = -2.5 # Tăng điểm mạnh nếu ở đỉnh BB
        return score, "Bearish Pin Bar"
    
    return 0.0, ""

def score_mean_reversion_5m(ind: Dict) -> Tuple[float, str]:
    """Mean reversion setup cho 5m"""
    price = ind.get("closed_candle_price", 0)
    bb_middle = ind.get("bb_middle", 0)
    atr = ind.get("atr", 0)
    
    if not all([price, bb_middle, atr > 0]): return 0.0, ""
    
    distance_from_mean = abs(price - bb_middle)
    distance_in_atr = distance_from_mean / atr
    
    if distance_in_atr > 1.8:
        if price < bb_middle: return 1.5, "Mean Reversion BUY"
        else: return -1.5, "Mean Reversion SELL"
    
    return 0.0, ""

# [THÊM VÍ DỤ] Các hàm còn thiếu để code không lỗi
def score_rsi_div(ind: Dict) -> Tuple[float, str]:
    div = ind.get("rsi_divergence", "none")
    if div == "bullish": return 1.8, "Phân kỳ RSI tăng"
    if div == "bearish": return -1.8, "Phân kỳ RSI giảm"
    return 0.0, ""

def score_support_resistance(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_breakout(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_candle_pattern(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_doji(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_volume(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_macd(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_bb(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_cmf(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_atr_vol(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_ema200(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_rsi_multi(ind: Dict) -> Tuple[float, str]: return 0.0, ""
def score_adx(ind: Dict) -> Tuple[float, str]: return 0.0, ""

# ==============================================================================
# =================== CẤU HÌNH TRỌNG SỐ & QUY TẮC ============================
# ==============================================================================

RULE_WEIGHTS = {
    "score_price_action_5m": 2.5,
    "score_mean_reversion_5m": 2.2,
    "score_rsi_div": 2.0,
    "score_momentum_5m": 1.8,
    "score_trend": 1.0,
    # Các trọng số khác giữ nguyên hoặc bạn tự điều chỉnh
}

RULE_FUNCS: List[Callable[[Dict], Tuple[float, str]]] = [
    score_price_action_5m,
    score_mean_reversion_5m,
    score_rsi_div,
    score_momentum_5m,
    score_trend,
    # Thêm các hàm khác vào đây nếu bạn đã định nghĩa chúng
]

# ==============================================================================
# =================== HÀM TỔNG HỢP & CHUẨN HÓA ĐIỂM ==========================
# ==============================================================================

def check_signal(indicators: Dict) -> Dict:
    """
    [SỬA LẠI HOÀN TOÀN]
    Hàm này chạy qua tất cả các quy tắc, tính tổng điểm có trọng số,
    sau đó chuẩn hóa về thang điểm -10 đến +10.
    """
    total_unweighted_score = 0.0
    total_weighted_score = 0.0
    reasons = []

    # [LOGIC CỐT LÕI] Vòng lặp qua tất cả các hàm quy tắc để cộng dồn điểm
    for rule_func in RULE_FUNCS:
        score, reason = rule_func(indicators)
        
        if score != 0.0 and reason:
            weight = RULE_WEIGHTS.get(rule_func.__name__, 1.0) # Lấy trọng số theo tên hàm
            weighted_score = score * weight
            
            total_unweighted_score += score
            total_weighted_score += weighted_score
            reasons.append(f"{reason} ({weighted_score:+.2f})")

    # [CHUẨN HÓA ĐIỂM] Chuyển điểm tổng về thang điểm chung (-10 đến +10)
    # Đây là một tham số quan trọng để bạn tinh chỉnh. Nó đại diện cho mức điểm tổng "tối đa" mà bạn kỳ vọng.
    # Nếu điểm tổng đạt đến mức này, điểm chuẩn hóa sẽ là 10 (hoặc -10).
    MAX_EXPECTED_SCORE = 15.0 
    FINAL_SCORE_RANGE = 10.0

    if total_weighted_score == 0:
        normalized_score = 0.0
    else:
        normalized_score = (total_weighted_score / MAX_EXPECTED_SCORE) * FINAL_SCORE_RANGE

    # Giới hạn điểm trong khoảng [-10, 10] để tránh các giá trị quá lớn
    normalized_score = max(-FINAL_SCORE_RANGE, min(FINAL_SCORE_RANGE, normalized_score))

    # Xây dựng kết quả trả về
    final_reason = " | ".join(reasons) if reasons else "Không có tín hiệu"
    
    tag = "Neutral"
    if normalized_score >= 4.0: tag = "Strong Buy"
    elif normalized_score >= 2.0: tag = "Buy"
    elif normalized_score <= -4.0: tag = "Strong Sell"
    elif normalized_score <= -2.0: tag = "Sell"

    return {
        "raw_tech_score": round(normalized_score, 2), # Đây là điểm đã được chuẩn hóa
        "reason": final_reason,
        "tag": tag,
        "level": int(abs(normalized_score)),
        "debug_info": {
            "unnormalized_score": round(total_weighted_score, 2),
            "reasons_list": reasons
        }
    }