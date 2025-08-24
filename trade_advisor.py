from typing import Dict

ADVISOR_CONFIG = {
    "WEIGHTS": {
        'tech': 1.0, 
        'context': 0.0,
        'ai': 0.0
    },
    "DECISION_THRESHOLDS": {
        "buy": 7.0,
        "sell": -7.0
    },
    "MAX_RAW_SCORES": {
        "tech": 8.0,
        "context": 25.0,
        "ai": 1.0
    }
}

def get_advisor_decision(signal_result: Dict) -> Dict:
    raw_tech_score = signal_result.get("raw_tech_score", 0.0)
    reason = signal_result.get("reason", "Không có tín hiệu.")
    raw_context_score = 0.0
    raw_ai_score = 0.0
    max_scores = ADVISOR_CONFIG["MAX_RAW_SCORES"]
    tech_scaled = raw_tech_score / max_scores['tech'] if max_scores['tech'] != 0 else 0.0
    context_scaled = raw_context_score / max_scores['context'] if max_scores['context'] != 0 else 0.0
    ai_scaled = raw_ai_score / max_scores['ai'] if max_scores['ai'] != 0 else 0.0
    weights = ADVISOR_CONFIG["WEIGHTS"]
    final_rating = (weights['tech'] * tech_scaled) + \
                   (weights['context'] * context_scaled) + \
                   (weights['ai'] * ai_scaled)
    final_score = round(max(-1.0, min(final_rating, 1.0)) * 10, 2)
    decision_type = "NEUTRAL"
    thresholds = ADVISOR_CONFIG["DECISION_THRESHOLDS"]
    if final_score >= thresholds['buy']:
        decision_type = "BUY"
    elif final_score <= thresholds['sell']:
        decision_type = "SELL"
    return {
        "decision_type": decision_type,
        "final_score": final_score,
        "signal_reason": reason
    }