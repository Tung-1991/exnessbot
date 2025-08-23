# /root/ricealert/trade_advisor.py
import os
import json
from datetime import datetime
from typing import Dict, Tuple, Optional
from signal_logic import check_signal

# ==============================================================================
# =================== ⚙️ TRUNG TÂM CẤU HÌNH & TINH CHỈNH ⚙️ =====================
# ==============================================================================
FULL_CONFIG = {
    "NOTES": "v8.1 - Bidirectional Scoring for CFD",
    "SCORE_RANGE": 8.0,
    "WEIGHTS": { 'tech': 0.7, 'context': 0.05, 'ai': 0.25 }, # Tạm thời tăng trọng số TA, giảm Context và AI
    "DECISION_THRESHOLDS": { "buy": 7.0, "sell": -7.0 }, # Ngưỡng mua/bán ví dụ
    "TRADE_PLAN_RULES": {
        "default_rr_ratio": 1.8, "high_score_rr_ratio": 2.2,
        "critical_score_rr_ratio": 2.8, "default_sl_percent": 0.03
    },
    "CONTEXT_SETTINGS": {
        "NEWS_NORMALIZATION_CAP": 25.0,
        "NEWS_AGGREGATION_METHOD": "HIGHEST_ABS"
    }
}

# ==============================================================================
# =================== 💻 LOGIC CHƯƠNG TRÌNH 💻 ===================
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.join(BASE_DIR, "ricenews/lognew")
AI_DIR = os.path.join(BASE_DIR, "ai_logs")
MARKET_CONTEXT_PATH = os.path.join(BASE_DIR, "ricenews/lognew/market_context.json")

def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return default

def analyze_market_trend(mc: dict) -> str:
    if not mc: return "NEUTRAL"
    up_score, down_score = 0, 0
    fear_greed_value = mc.get('fear_greed', 50)
    if fear_greed_value is None: fear_greed_value = 50
    btc_dominance_value = mc.get('btc_dominance', 50)
    if btc_dominance_value is None: btc_dominance_value = 50
    if fear_greed_value > 68: up_score += 1
    elif fear_greed_value < 35: down_score += 1
    if btc_dominance_value > 55: up_score += 1
    elif btc_dominance_value < 48: down_score += 1
    if up_score > down_score: return "UPTREND"
    if down_score > up_score: return "DOWNTREND"
    return "NEUTRAL"

def get_live_context_and_ai(symbol: str, interval: str, config: dict) -> Tuple[Dict, Dict]:
    market_context = load_json(MARKET_CONTEXT_PATH, {})
    market_trend = analyze_market_trend(market_context)
    today_path = os.path.join(NEWS_DIR, f"{datetime.now().strftime('%Y-%m-%d')}_news_signal.json")
    news_data = load_json(today_path, [])
    tag_clean = symbol.lower().replace("usdt", "").strip()
    relevant_news = [n for n in news_data if n.get("category_tag", "").lower() == tag_clean or n.get("category_tag") in {"MACRO", "GENERAL"}]
    news_factor = 0.0
    aggregation_method = config['CONTEXT_SETTINGS'].get("NEWS_AGGREGATION_METHOD", "HIGHEST_ABS")
    if relevant_news:
        if aggregation_method == "HIGHEST_ABS":
            most_impactful_news = max(relevant_news, key=lambda n: abs(n.get('news_score', 0)))
            news_factor = most_impactful_news.get('news_score', 0.0)
        else:
            news_factor = sum(n.get('news_score', 0.0) for n in relevant_news)
    final_context = market_context.copy()
    final_context["market_trend"] = market_trend
    final_context["news_factor"] = news_factor
    ai_data = load_json(os.path.join(AI_DIR, f"{symbol}_{interval}.json"), {})
    return final_context, ai_data

def generate_combined_trade_plan(base_plan: dict, score: float, config: dict) -> dict:
    return {"entry": 0, "tp": 0, "sl": 0} # Tạm thời vô hiệu hóa, sẽ tính lại trong live_trade

def get_advisor_decision(
    symbol: str, interval: str, indicators: dict, config: dict,
    ai_data_override: Optional[Dict] = None,
    context_override: Optional[Dict] = None,
    weights_override: Optional[Dict] = None,
) -> Dict:
    if context_override is not None and ai_data_override is not None:
        context, ai_data = context_override, ai_data_override
    else:
        # Tạm thời dùng dữ liệu rỗng để bỏ qua AI và Context
        context, ai_data = {}, {}
    
    signal_details = check_signal(indicators)
    raw_tech_score = signal_details.get("raw_tech_score", 0.0)
    score_range = config.get("SCORE_RANGE", 8.0)
    
    # Chuẩn hóa điểm TA về thang -1 đến +1
    tech_scaled = raw_tech_score / score_range
    tech_scaled = min(max(tech_scaled, -1.0), 1.0) # Đảm bảo nằm trong khoảng [-1, 1]

    # Tạm thời đặt các điểm khác bằng 0
    context_scaled = 0.0
    ai_skew = 0.0
    
    weights = weights_override if weights_override is not None else config['WEIGHTS']
    final_rating = (weights['tech'] * tech_scaled) + \
                   (weights['context'] * context_scaled) + \
                   (weights['ai'] * ai_skew)

    # <<< THAY ĐỔI CỐT LÕI: Chuyển sang thang điểm đối xứng -10 đến +10 >>>
    final_score = round(final_rating * 10, 2)
    
    decision_type = "NEUTRAL"
    if final_score >= config['DECISION_THRESHOLDS']['buy']:
        decision_type = "OPPORTUNITY_BUY"
    elif final_score <= config['DECISION_THRESHOLDS']['sell']:
        decision_type = "OPPORTUNITY_SELL"

    return {
        "decision_type": decision_type, "final_score": final_score,
        "tech_score_raw": raw_tech_score, "signal_reason": signal_details.get("reason")
    }