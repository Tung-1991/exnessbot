from signal_logic import check_signal

def get_advisor_decision(symbol: str, interval: str, indicators: dict, config: dict) -> dict:
    signal_details = check_signal(indicators)
    tech_score = signal_details.get("raw_tech_score", 0.0)
    
    volatility_adj = 1.0
    atr_pct = indicators.get("atr_percent", 0)
    if atr_pct > 5.0:
        volatility_adj = 0.9
    elif atr_pct > 3.0:
        volatility_adj = 0.95
    elif atr_pct < 1.0:
        volatility_adj = 1.05
    
    symbol_adj = 1.0
    if "BTC" in symbol:
        symbol_adj = 1.0
    elif "ETH" in symbol:
        symbol_adj = 1.02
    else:
        symbol_adj = 0.98
    
    weights = config.get('WEIGHTS', {'tech': 1.0, 'context': 0.0, 'ai': 0.0})
    
    adjusted_tech_score = tech_score * volatility_adj * symbol_adj
    
    final_score = (weights['tech'] * adjusted_tech_score) + \
                  (weights['context'] * 0.0) + \
                  (weights['ai'] * 0.0)
    
    final_score = round(final_score, 2)
    final_score = max(-10.0, min(10.0, final_score))
    
    return {
        "final_score": final_score,
        "signal_reason": signal_details.get("reason"),
        "tag": signal_details.get("tag"),
        "level": signal_details.get("level"),
        "debug_info": {
            "weights_used": weights,
            "tech_score_raw": tech_score,
            "volatility_adjustment": volatility_adj,
            "symbol_adjustment": symbol_adj,
            "active_signals": signal_details.get("debug_info", {}).get("active_signals", 0)
        }
    }