import os
import json
from datetime import datetime
from typing import Dict, Tuple, Optional
from signal_logic import check_signal

# ==============================================================================
# =================== ⚙️ TRUNG TÂM CẤU HÌNH & TINH CHỈNH ⚙️ =====================
# ==============================================================================
FULL_CONFIG = {
    "NOTES": "v9.2 - Pure Signal Provider for Advanced Trading Engine",
    "SCORE_RANGE": 8.0,
    "WEIGHTS": {
        'tech': 1.0,
        'context': 0.0,
        'ai': 0.0
    },
}

# ==============================================================================
# =================== 💻 LOGIC CHƯƠNG TRÌNH 💻 ===================
# ==============================================================================

def get_advisor_decision(
    symbol: str, interval: str, indicators: dict, config: dict
) -> Dict:
    
    signal_details = check_signal(indicators)
    tech_score = signal_details.get("raw_tech_score", 0.0)
    
    context_score = 0.0
    ai_score = 0.0

    weights = config.get('WEIGHTS', {'tech': 1.0, 'context': 0.0, 'ai': 0.0})
    final_score = (weights['tech'] * tech_score) + \
                  (weights['context'] * context_score) + \
                  (weights['ai'] * ai_score)
    
    final_score = round(final_score, 2)

    return {
        "final_score": final_score,
        "signal_reason": signal_details.get("reason"),
        "tag": signal_details.get("tag"),
        "level": signal_details.get("level"),
        "debug_info": {
            "weights_used": weights,
            "tech_component": round(weights['tech'] * tech_score, 2),
        }
    }