# -*- coding: utf-8 -*-
# signal_logic.py (Upgraded with Tanh Normalization)
# Version: 2.0.0
# Date: 2025-08-26
"""
CHANGELOG (v2.0.0):
- REFACTOR (Scoring System): Thay thế hoàn toàn hệ thống tính điểm tuyến tính (AMPLIFICATION_FACTOR) bằng hàm Hyperbolic Tangent (math.tanh).
  - Mục đích: Tạo ra một điểm số ổn định hơn, giảm thiểu sự biến động cực đoan giữa các cây nến.
  - Lợi ích: Điểm số sẽ phản ứng mượt mà hơn, nhạy cảm với các tín hiệu yếu nhưng không bị "thổi phồng" quá mức ở các vùng tín hiệu mạnh, giúp các cơ chế quản lý lệnh (như cắt lỗ sớm) hoạt động đáng tin cậy hơn.
- FEATURE (Tanh Sensitivity): Thêm hằng số TANH_SENSITIVITY để dễ dàng tinh chỉnh "độ nhạy" của đường cong chuẩn hóa điểm số trong tương lai.
"""

from typing import Dict, Tuple, List, Callable
import math

# ==============================================================================
# ======================== CÁC HÀM TÍNH ĐIỂM TÍN HIỆU ==========================
# ==============================================================================
# Các hàm tính điểm cho từng tín hiệu riêng lẻ không thay đổi.
# Chúng vẫn là nền tảng để tạo ra tổng điểm thô có trọng số.

def score_trend(ind: Dict) -> Tuple[float, str]:
    ema_9 = ind.get("ema_9", 0)
    ema_20 = ind.get("ema_20", 0)
    ema_50 = ind.get("ema_50", 0)
    if ema_9 > 0 and ema_20 > 0:
        ema_diff_pct = ((ema_9 - ema_20) / ema_20) * 100
        ema50_confirm = 0.0
        if ema_50 > 0:
            if ema_9 > ema_50 and ema_20 > ema_50: ema50_confirm = 0.3
            elif ema_9 < ema_50 and ema_20 < ema_50: ema50_confirm = -0.3
        if abs(ema_diff_pct) < 0.02: return 0.0, ""
        elif ema_diff_pct > 0.2: return 1.5 + ema50_confirm, f"Strong Uptrend ({ema_diff_pct:.2f}%)"
        elif ema_diff_pct > 0.05: return 1.0 + ema50_confirm, f"Uptrend ({ema_diff_pct:.2f}%)"
        elif ema_diff_pct < -0.2: return -1.5 + ema50_confirm, f"Strong Downtrend ({ema_diff_pct:.2f}%)"
        elif ema_diff_pct < -0.05: return -1.0 + ema50_confirm, f"Downtrend ({ema_diff_pct:.2f}%)"
    return 0.0, ""

def score_momentum_5m(ind: Dict) -> Tuple[float, str]:
    rsi = ind.get("rsi_14", 50)
    macd_hist = ind.get("macd_hist", 0)
    adx = ind.get("adx", 20)
    rsi_score = 0
    if rsi <= 25: rsi_score = 1.8
    elif rsi <= 35: rsi_score = 1.2
    elif rsi <= 45: rsi_score = 0.5
    elif rsi >= 75: rsi_score = -1.8
    elif rsi >= 65: rsi_score = -1.2
    elif rsi >= 55: rsi_score = -0.5
    macd_score = 0
    if macd_hist > 0: macd_score = 0.6
    elif macd_hist < 0: macd_score = -0.6
    adx_bonus = 0
    if adx > 25: adx_bonus = 0.3 if (rsi_score + macd_score) > 0 else -0.3
    total = rsi_score + macd_score + adx_bonus
    if total > 0.5: return total, f"Bullish Momentum (RSI:{rsi:.0f}, ADX:{adx:.0f})"
    elif total < -0.5: return total, f"Bearish Momentum (RSI:{rsi:.0f}, ADX:{adx:.0f})"
    return 0.0, ""

def score_price_action_5m(ind: Dict) -> Tuple[float, str]:
    high, low, close, open_price = ind.get("high", 0), ind.get("low", 0), ind.get("closed_candle_price", 0), ind.get("open", 0)
    bb_lower, bb_upper = ind.get("bb_lower", 0), ind.get("bb_upper", 0)
    prev_high, prev_low, prev_close = ind.get("prev_high", 0), ind.get("prev_low", 0), ind.get("prev_close", 0)
    if not all([high, low, close, open_price]): return 0.0, ""
    body = abs(close - open_price)
    full_range = high - low
    if full_range == 0: return 0.0, ""
    bb_pos_score = 0
    if bb_upper > bb_lower:
        bb_range = bb_upper - bb_lower
        price_pos = (close - bb_lower) / bb_range
        if price_pos < 0.2: bb_pos_score = 1.0
        elif price_pos > 0.8: bb_pos_score = -1.0
    if prev_close > 0 and prev_high > 0:
        if close > open_price and open_price < prev_close and close > prev_high:
            return 2.0 + bb_pos_score, "Bullish Engulfing"
        elif close < open_price and open_price > prev_close and close < prev_low:
            return -2.0 + bb_pos_score, "Bearish Engulfing"
    upper_wick = high - max(close, open_price)
    lower_wick = min(close, open_price) - low
    if lower_wick > body * 2 and upper_wick < body * 0.7:
        return 1.8 + bb_pos_score, "Bullish Pin Bar"
    elif upper_wick > body * 2 and lower_wick < body * 0.7:
        return -1.8 + bb_pos_score, "Bearish Pin Bar"
    return 0.0, ""

def score_mean_reversion_5m(ind: Dict) -> Tuple[float, str]:
    price = ind.get("closed_candle_price", 0)
    bb_upper, bb_lower, bb_middle = ind.get("bb_upper", 0), ind.get("bb_lower", 0), ind.get("bb_middle", 0)
    rsi = ind.get("rsi_14", 50)
    atr = ind.get("atr", 0)
    if not all([price, bb_middle, atr > 0]): return 0.0, ""
    if price <= bb_lower:
        score = 2.0
        if rsi < 30: score += 0.5
        return score, f"Oversold at BB Lower (RSI:{rsi:.0f})"
    elif price >= bb_upper:
        score = -2.0
        if rsi > 70: score -= 0.5
        return score, f"Overbought at BB Upper (RSI:{rsi:.0f})"
    distance_in_atr = abs(price - bb_middle) / atr
    if distance_in_atr > 1.5:
        if price < bb_middle:
            score = 1.2
            if rsi < 40: score += 0.3
            return score, "Mean Reversion BUY"
        else:
            score = -1.2
            if rsi > 60: score -= 0.3
            return score, "Mean Reversion SELL"
    return 0.0, ""

def score_rsi_divergence(ind: Dict) -> Tuple[float, str]:
    div = ind.get("rsi_divergence", "none")
    rsi = ind.get("rsi_14", 50)
    if div == "bullish":
        score = 2.2
        if rsi < 35: score += 0.5
        return score, f"Bullish RSI Divergence (RSI:{rsi:.0f})"
    elif div == "bearish":
        score = -2.2
        if rsi > 65: score -= 0.5
        return score, f"Bearish RSI Divergence (RSI:{rsi:.0f})"
    return 0.0, ""

def score_support_resistance(ind: Dict) -> Tuple[float, str]:
    price = ind.get("closed_candle_price", 0)
    support = ind.get("support_level", 0)
    resistance = ind.get("resistance_level", 0)
    atr = ind.get("atr", 0)
    if not all([price, support, resistance, atr > 0]): return 0.0, ""
    if abs(price - support) < atr * 0.5 and price > support:
        return 1.5, f"Bounce from Support @{support:.2f}"
    if abs(price - resistance) < atr * 0.5 and price < resistance:
        return -1.5, f"Rejection from Resistance @{resistance:.2f}"
    return 0.0, ""

def score_breakout(ind: Dict) -> Tuple[float, str]:
    signal = ind.get("breakout_signal", "none")
    volume = ind.get("volume", 0)
    vol_ma = ind.get("vol_ma20", 0)
    adx = ind.get("adx", 20)
    if signal == "bullish":
        score = 2.0
        if vol_ma > 0 and volume > vol_ma * 1.5: score += 0.8
        if adx > 25: score += 0.5
        return score, f"Bullish Breakout (Vol:{volume/vol_ma:.1f}x)"
    elif signal == "bearish":
        score = -2.0
        if vol_ma > 0 and volume > vol_ma * 1.5: score -= 0.8
        if adx > 25: score -= 0.5
        return score, f"Bearish Breakout (Vol:{volume/vol_ma:.1f}x)"
    return 0.0, ""

def score_volume_analysis(ind: Dict) -> Tuple[float, str]:
    volume = ind.get("volume", 0)
    vol_ma = ind.get("vol_ma20", 0)
    cmf = ind.get("cmf", 0)
    price_change = 0
    if ind.get("closed_candle_price", 0) > 0 and ind.get("prev_close", 0) > 0:
        price_change = (ind["closed_candle_price"] - ind["prev_close"]) / ind["prev_close"]
    if vol_ma > 0:
        vol_ratio = volume / vol_ma
        if vol_ratio > 1.5:
            if price_change > 0 and cmf > 0.1:
                return 1.2, f"Bullish Volume Surge ({vol_ratio:.1f}x, CMF:{cmf:.2f})"
            elif price_change < 0 and cmf < -0.1:
                return -1.2, f"Bearish Volume Surge ({vol_ratio:.1f}x, CMF:{cmf:.2f})"
    if cmf > 0.2: return 0.8, f"Strong Buying Pressure (CMF:{cmf:.2f})"
    elif cmf < -0.2: return -0.8, f"Strong Selling Pressure (CMF:{cmf:.2f})"
    return 0.0, ""

def score_macd_signal(ind: Dict) -> Tuple[float, str]:
    cross = ind.get("macd_cross", "neutral")
    hist = ind.get("macd_hist", 0)
    if cross == "bullish":
        score = 1.8
        if hist > 0: score += 0.4
        return score, f"MACD Bullish Cross (Hist:{hist:.4f})"
    elif cross == "bearish":
        score = -1.8
        if hist < 0: score -= 0.4
        return score, f"MACD Bearish Cross (Hist:{hist:.4f})"
    if abs(hist) > 0:
        if hist > 0: return 0.5, f"MACD Positive Momentum"
        else: return -0.5, f"MACD Negative Momentum"
    return 0.0, ""

def score_volatility_setup(ind: Dict) -> Tuple[float, str]:
    atr_pct = ind.get("atr_percent", 0)
    if atr_pct > 0:
        if atr_pct < 1.0:
            return 0.5, f"Low Volatility Setup (ATR:{atr_pct:.2f}%)"
        elif atr_pct > 3.0:
            return -0.3, f"High Volatility Warning (ATR:{atr_pct:.2f}%)"
    return 0.0, ""

# ==============================================================================
# ====================== CẤU HÌNH TRỌNG SỐ & QUY TẮC ===========================
# ==============================================================================

TRENDING_WEIGHTS = {
    "score_breakout": 3.0, "score_trend": 2.8, "score_momentum_5m": 2.5,
    "score_price_action_5m": 1.8, "score_macd_signal": 1.6, "score_volume_analysis": 1.5,
    "score_support_resistance": 0.5, "score_rsi_divergence": 0.5, "score_mean_reversion_5m": 0.2,
    "score_volatility_setup": 0.8,
}
SIDEWAYS_VOLATILE_WEIGHTS = {
    "score_mean_reversion_5m": 2.8, "score_rsi_divergence": 2.6, "score_support_resistance": 2.5,
    "score_price_action_5m": 2.2, "score_breakout": 1.5, "score_momentum_5m": 1.0,
    "score_macd_signal": 1.0, "score_trend": 0.5, "score_volume_analysis": 0.8,
    "score_volatility_setup": 0.5,
}
SIDEWAYS_QUIET_WEIGHTS = {
    "score_mean_reversion_5m": 3.0, "score_rsi_divergence": 2.8, "score_support_resistance": 2.5,
    "score_price_action_5m": 2.0, "score_breakout": 1.8, "score_volatility_setup": 1.5,
    "score_momentum_5m": 0.8, "score_macd_signal": 0.8, "score_trend": 0.2,
    "score_volume_analysis": 0.5,
}

RULE_FUNCS: List[Callable[[Dict], Tuple[float, str]]] = [
    score_breakout, score_price_action_5m, score_rsi_divergence, score_mean_reversion_5m,
    score_momentum_5m, score_macd_signal, score_support_resistance, score_trend,
    score_volume_analysis, score_volatility_setup,
]

# --- CẤU HÌNH HỆ THỐNG TÍNH ĐIỂM MỚI ---
# Hệ số này điều chỉnh độ "dốc" của hàm tanh.
# Giá trị nhỏ hơn -> đường cong thoải hơn, điểm số khó đạt tới +/- 10.
# Giá trị lớn hơn -> đường cong dốc hơn, điểm số dễ đạt tới +/- 10 hơn.
TANH_SENSITIVITY = 0.15

CONFLUENCE_BONUS = {
    "ENABLED": True,
    "LEVELS": { 5: 1.15, 4: 1.12, 3: 1.08, 2: 1.03 }
}

# ==============================================================================
# ====================== HÀM TỔNG HỢP TÍN HIỆU (NÂNG CẤP) ======================
# ==============================================================================

def check_signal(indicators: Dict) -> Dict:
    """
    Phân tích các chỉ báo, tính toán điểm số thô có trọng số, và sau đó
    chuẩn hóa nó một cách ổn định bằng hàm math.tanh để ra điểm cuối cùng.
    """
    market_regime = indicators.get("market_regime", "SIDEWAYS_VOLATILE")
    
    if market_regime == "TRENDING":
        active_weights = TRENDING_WEIGHTS
    elif market_regime == "SIDEWAYS_QUIET":
        active_weights = SIDEWAYS_QUIET_WEIGHTS
    else:
        active_weights = SIDEWAYS_VOLATILE_WEIGHTS

    total_weighted_score = 0.0
    reasons = []
    active_signals = 0
    
    for rule_func in RULE_FUNCS:
        score, reason = rule_func(indicators)
        if score != 0.0 and reason:
            weight = active_weights.get(rule_func.__name__, 1.0)
            weighted_score = score * weight
            total_weighted_score += weighted_score
            # Thêm cả tên hàm để dễ debug
            reasons.append(f"{reason} [{rule_func.__name__}] ({weighted_score:+.2f})")
            active_signals += 1

    # --- LOGIC CHUẨN HÓA ĐIỂM SỐ MỚI SỬ DỤNG TANH ---
    if active_signals == 0:
        normalized_score = 0.0
    else:
        # 1. Đưa tổng điểm có trọng số vào hàm tanh.
        #    math.tanh sẽ "nén" mọi giá trị vào khoảng [-1, 1].
        # 2. Nhân với 10 để có thang điểm cuối cùng là [-10, 10].
        normalized_score = math.tanh(total_weighted_score * TANH_SENSITIVITY) * 10.0

        # 3. (Tùy chọn) Áp dụng bonus khi có nhiều tín hiệu đồng thuận.
        confluence_factor = 1.0
        if CONFLUENCE_BONUS["ENABLED"]:
            for num_signals, factor in sorted(CONFLUENCE_BONUS["LEVELS"].items(), reverse=True):
                if active_signals >= num_signals:
                    confluence_factor = factor
                    break
        normalized_score *= confluence_factor
        
        # 4. Đảm bảo điểm số không bao giờ vượt ra ngoài thang điểm.
        normalized_score = max(-10.0, min(10.0, normalized_score))

    # --- Logic phân loại và trả về kết quả (không đổi) ---
    abs_score = abs(normalized_score)
    if abs_score >= 7.5: tag = "Very Strong Buy" if normalized_score > 0 else "Very Strong Sell"
    elif abs_score >= 6.0: tag = "Strong Buy" if normalized_score > 0 else "Strong Sell"
    elif abs_score >= 4.0: tag = "Buy" if normalized_score > 0 else "Sell"
    elif abs_score >= 2.0: tag = "Weak Buy" if normalized_score > 0 else "Weak Sell"
    else: tag = "Neutral"

    final_reason = " | ".join(sorted(reasons)) if reasons else "No signals detected"

    return {
        "raw_tech_score": round(normalized_score, 2),
        "reason": final_reason,
        "tag": tag,
        "level": min(5, int(abs_score / 2)),
        "debug_info": {
            "total_weighted_score": round(total_weighted_score, 2),
            "active_signals": active_signals,
            "market_regime": market_regime,
            "tanh_sensitivity": TANH_SENSITIVITY,
            "confluence_factor": confluence_factor if 'confluence_factor' in locals() else 1.0
        }
    }
