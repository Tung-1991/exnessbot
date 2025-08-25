# -*- coding: utf-8 -*-
from typing import Dict, Tuple, List, Callable
import math

# ==============================================================================
# =================== 🔥 FIXED: CÁC HÀM TÍNH ĐIỂM CHO CFD CRYPTO 🔥 ===========
# ==============================================================================

def score_trend(ind: Dict) -> Tuple[float, str]:
    """Trend Analysis - Optimized for crypto volatility"""
    ema_9 = ind.get("ema_9", 0)
    ema_20 = ind.get("ema_20", 0)
    ema_50 = ind.get("ema_50", 0)
    
    if ema_9 > 0 and ema_20 > 0:
        # Nới lỏng ngưỡng cho crypto (từ 0.05% -> 0.02%)
        ema_diff_pct = ((ema_9 - ema_20) / ema_20) * 100
        
        # Thêm xác nhận từ EMA 50
        ema50_confirm = 0.0
        if ema_50 > 0:
            if ema_9 > ema_50 and ema_20 > ema_50: ema50_confirm = 0.3
            elif ema_9 < ema_50 and ema_20 < ema_50: ema50_confirm = -0.3
        
        if abs(ema_diff_pct) < 0.02: return 0.0, ""
        elif ema_diff_pct > 0.05: return 1.0 + ema50_confirm, f"Uptrend ({ema_diff_pct:.2f}%)"
        elif ema_diff_pct > 0.2: return 1.5 + ema50_confirm, f"Strong Uptrend ({ema_diff_pct:.2f}%)"
        elif ema_diff_pct < -0.05: return -1.0 + ema50_confirm, f"Downtrend ({ema_diff_pct:.2f}%)"
        elif ema_diff_pct < -0.2: return -1.5 + ema50_confirm, f"Strong Downtrend ({ema_diff_pct:.2f}%)"
    
    return 0.0, ""

def score_momentum_5m(ind: Dict) -> Tuple[float, str]:
    """Enhanced Momentum với RSI + MACD + ADX"""
    rsi = ind.get("rsi_14", 50)
    macd_hist = ind.get("macd_hist", 0)
    adx = ind.get("adx", 20)
    
    # RSI Score - Thêm nhiều mức
    rsi_score = 0
    if rsi <= 25: rsi_score = 1.8
    elif rsi <= 35: rsi_score = 1.2
    elif rsi <= 45: rsi_score = 0.5
    elif rsi >= 75: rsi_score = -1.8
    elif rsi >= 65: rsi_score = -1.2
    elif rsi >= 55: rsi_score = -0.5
    
    # MACD Score - Tăng trọng số
    macd_score = 0
    if macd_hist > 0: macd_score = 0.6
    elif macd_hist < 0: macd_score = -0.6
    
    # ADX Bonus - Trend strength
    adx_bonus = 0
    if adx > 25: adx_bonus = 0.3 if (rsi_score + macd_score) > 0 else -0.3
    
    total = rsi_score + macd_score + adx_bonus
    
    if total > 0.5: return total, f"Bullish Momentum (RSI:{rsi:.0f}, ADX:{adx:.0f})"
    elif total < -0.5: return total, f"Bearish Momentum (RSI:{rsi:.0f}, ADX:{adx:.0f})"
    
    return 0.0, ""

def score_price_action_5m(ind: Dict) -> Tuple[float, str]:
    """Enhanced Price Action với Pin Bar + Engulfing"""
    high, low, close, open_price = ind.get("high", 0), ind.get("low", 0), ind.get("closed_candle_price", 0), ind.get("open", 0)
    bb_lower, bb_upper, bb_middle = ind.get("bb_lower", 0), ind.get("bb_upper", 0), ind.get("bb_middle", 0)
    prev_high, prev_low, prev_close = ind.get("prev_high", 0), ind.get("prev_low", 0), ind.get("prev_close", 0)
    
    if not all([high, low, close, open_price]): return 0.0, ""

    body = abs(close - open_price)
    upper_wick = high - max(close, open_price)
    lower_wick = min(close, open_price) - low
    full_range = high - low
    
    if full_range == 0: return 0.0, ""
    
    # BB Position Score
    bb_pos_score = 0
    if bb_upper > bb_lower:
        bb_range = bb_upper - bb_lower
        price_pos = (close - bb_lower) / bb_range
        if price_pos < 0.2: bb_pos_score = 1.0  # Near lower band
        elif price_pos > 0.8: bb_pos_score = -1.0  # Near upper band
    
    # Pin Bar Analysis
    if lower_wick > body * 2 and upper_wick < body * 0.7:
        base_score = 1.8
        return base_score + bb_pos_score, "Bullish Pin Bar"
    elif upper_wick > body * 2 and lower_wick < body * 0.7:
        base_score = -1.8
        return base_score + bb_pos_score, "Bearish Pin Bar"
    
    # Engulfing Patterns
    if prev_close > 0 and prev_high > 0:
        # Bullish Engulfing
        if close > open_price and open_price < prev_close and close > prev_high:
            return 2.0 + bb_pos_score, "Bullish Engulfing"
        # Bearish Engulfing
        elif close < open_price and open_price > prev_close and close < prev_low:
            return -2.0 + bb_pos_score, "Bearish Engulfing"
    
    return 0.0, ""

def score_mean_reversion_5m(ind: Dict) -> Tuple[float, str]:
    """Mean Reversion với Bollinger Bands"""
    price = ind.get("closed_candle_price", 0)
    bb_upper, bb_lower, bb_middle = ind.get("bb_upper", 0), ind.get("bb_lower", 0), ind.get("bb_middle", 0)
    rsi = ind.get("rsi_14", 50)
    atr = ind.get("atr", 0)
    
    if not all([price, bb_middle, atr > 0]): return 0.0, ""
    
    # Distance from BB bands
    if price <= bb_lower:
        score = 2.0
        if rsi < 30: score += 0.5  # RSI confirm
        return score, f"Oversold at BB Lower (RSI:{rsi:.0f})"
    elif price >= bb_upper:
        score = -2.0
        if rsi > 70: score -= 0.5  # RSI confirm
        return score, f"Overbought at BB Upper (RSI:{rsi:.0f})"
    
    # Distance from mean in ATR
    distance_from_mean = abs(price - bb_middle)
    distance_in_atr = distance_from_mean / atr
    
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
    """RSI Divergence Detection"""
    div = ind.get("rsi_divergence", "none")
    rsi = ind.get("rsi_14", 50)
    
    if div == "bullish":
        score = 2.2
        if rsi < 35: score += 0.5  # Strong oversold
        return score, f"Bullish RSI Divergence (RSI:{rsi:.0f})"
    elif div == "bearish":
        score = -2.2
        if rsi > 65: score -= 0.5  # Strong overbought
        return score, f"Bearish RSI Divergence (RSI:{rsi:.0f})"
    
    return 0.0, ""

def score_support_resistance(ind: Dict) -> Tuple[float, str]:
    """Support/Resistance Levels"""
    price = ind.get("closed_candle_price", 0)
    support = ind.get("support_level", 0)
    resistance = ind.get("resistance_level", 0)
    atr = ind.get("atr", 0)
    
    if not all([price, support, resistance, atr > 0]): return 0.0, ""
    
    # Check proximity to levels (within 0.5 ATR)
    if abs(price - support) < atr * 0.5:
        bounce_strength = (price - support) / atr
        if bounce_strength > 0: return 1.5, f"Bounce from Support @{support:.2f}"
    
    if abs(price - resistance) < atr * 0.5:
        rejection_strength = (resistance - price) / atr
        if rejection_strength > 0: return -1.5, f"Rejection from Resistance @{resistance:.2f}"
    
    return 0.0, ""

def score_breakout(ind: Dict) -> Tuple[float, str]:
    """Breakout Detection với Volume Confirmation"""
    signal = ind.get("breakout_signal", "none")
    volume = ind.get("volume", 0)
    vol_ma = ind.get("vol_ma20", 0)
    adx = ind.get("adx", 20)
    
    if signal == "bullish":
        score = 2.0
        if vol_ma > 0 and volume > vol_ma * 1.5: score += 0.8  # Volume confirm
        if adx > 25: score += 0.5  # Trend strength
        return score, f"Bullish Breakout (Vol:{volume/vol_ma:.1f}x)"
    elif signal == "bearish":
        score = -2.0
        if vol_ma > 0 and volume > vol_ma * 1.5: score -= 0.8
        if adx > 25: score -= 0.5
        return score, f"Bearish Breakout (Vol:{volume/vol_ma:.1f}x)"
    
    return 0.0, ""

def score_volume_analysis(ind: Dict) -> Tuple[float, str]:
    """Volume Analysis với CMF"""
    volume = ind.get("volume", 0)
    vol_ma = ind.get("vol_ma20", 0)
    cmf = ind.get("cmf", 0)
    price_change = 0
    
    if ind.get("closed_candle_price", 0) > 0 and ind.get("prev_close", 0) > 0:
        price_change = (ind["closed_candle_price"] - ind["prev_close"]) / ind["prev_close"]
    
    if vol_ma > 0:
        vol_ratio = volume / vol_ma
        
        # High volume + price movement
        if vol_ratio > 1.5:
            if price_change > 0 and cmf > 0.1:
                return 1.2, f"Bullish Volume Surge ({vol_ratio:.1f}x, CMF:{cmf:.2f})"
            elif price_change < 0 and cmf < -0.1:
                return -1.2, f"Bearish Volume Surge ({vol_ratio:.1f}x, CMF:{cmf:.2f})"
    
    # CMF signal alone
    if cmf > 0.2: return 0.8, f"Strong Buying Pressure (CMF:{cmf:.2f})"
    elif cmf < -0.2: return -0.8, f"Strong Selling Pressure (CMF:{cmf:.2f})"
    
    return 0.0, ""

def score_macd_signal(ind: Dict) -> Tuple[float, str]:
    """MACD Cross và Histogram"""
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
    
    # Histogram momentum
    if abs(hist) > 0:
        if hist > 0: return 0.5, f"MACD Positive Momentum"
        else: return -0.5, f"MACD Negative Momentum"
    
    return 0.0, ""

def score_volatility_setup(ind: Dict) -> Tuple[float, str]:
    """Volatility-based Opportunities"""
    bb_width = ind.get("bb_width", 0)
    atr_pct = ind.get("atr_percent", 0)
    
    # Bollinger Squeeze
    if bb_width > 0:
        # Need historical data for proper squeeze detection
        # For now, use ATR percentage as proxy
        if atr_pct < 1.0:  # Low volatility
            return 0.5, f"Low Volatility Setup (ATR:{atr_pct:.2f}%)"
        elif atr_pct > 3.0:  # High volatility
            return -0.3, f"High Volatility Warning (ATR:{atr_pct:.2f}%)"
    
    return 0.0, ""

# ==============================================================================
# =================== ⚡ OPTIMIZED WEIGHTS FOR CFD CRYPTO ⚡ ===================
# ==============================================================================

RULE_WEIGHTS = {
    "score_breakout": 2.8,           # Highest - Crypto loves breakouts
    "score_price_action_5m": 2.5,    # Pin bars & engulfing crucial
    "score_rsi_divergence": 2.3,     # Divergences work well in crypto
    "score_mean_reversion_5m": 2.0,  # BB bands reversal
    "score_momentum_5m": 1.8,        # RSI + MACD momentum
    "score_macd_signal": 1.6,        # MACD crosses
    "score_support_resistance": 1.5, # S/R levels
    "score_trend": 1.3,              # EMA trend
    "score_volume_analysis": 1.2,    # Volume confirmation
    "score_volatility_setup": 0.8,   # Volatility filter
}

RULE_FUNCS: List[Callable[[Dict], Tuple[float, str]]] = [
    score_breakout,
    score_price_action_5m,
    score_rsi_divergence,
    score_mean_reversion_5m,
    score_momentum_5m,
    score_macd_signal,
    score_support_resistance,
    score_trend,
    score_volume_analysis,
    score_volatility_setup,
]

# ==============================================================================
# =================== 🎯 SMART NORMALIZATION SYSTEM 🎯 ========================
# ==============================================================================

def check_signal(indicators: Dict) -> Dict:
    total_weighted_score = 0.0
    reasons = []
    active_signals = 0
    max_possible_score = 0.0
    
    for rule_func in RULE_FUNCS:
        score, reason = rule_func(indicators)
        if score != 0.0 and reason:
            weight = RULE_WEIGHTS.get(rule_func.__name__, 1.0)
            weighted_score = score * weight
            total_weighted_score += weighted_score
            reasons.append(f"{reason} ({weighted_score:+.2f})")
            active_signals += 1
            max_possible_score += abs(2.5 * weight)
    
    if active_signals == 0:
        normalized_score = 0.0
    else:
        if max_possible_score > 0:
            raw_ratio = total_weighted_score / max_possible_score
        else:
            raw_ratio = total_weighted_score / 12.0
        
        confluence_factor = 1.0
        if active_signals >= 5:
            confluence_factor = 1.25
        elif active_signals >= 3:
            confluence_factor = 1.15
        elif active_signals >= 2:
            confluence_factor = 1.05
            
        normalized_score = raw_ratio * 10.0 * confluence_factor
        normalized_score = max(-10.0, min(10.0, normalized_score))
    
    abs_score = abs(normalized_score)
    if abs_score >= 6.0: tag = "Strong Buy" if normalized_score > 0 else "Strong Sell"
    elif abs_score >= 4.0: tag = "Buy" if normalized_score > 0 else "Sell"
    elif abs_score >= 2.0: tag = "Weak Buy" if normalized_score > 0 else "Weak Sell"
    else: tag = "Neutral"
    
    final_reason = " | ".join(reasons) if reasons else "No signals detected"
    
    return {
        "raw_tech_score": round(normalized_score, 2),
        "reason": final_reason,
        "tag": tag,
        "level": min(5, int(abs_score / 2)),
        "debug_info": {
            "total_weighted": round(total_weighted_score, 2),
            "active_signals": active_signals,
            "max_possible": round(max_possible_score, 2),
            "confluence_factor": confluence_factor
        }
    }