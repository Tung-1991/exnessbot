# -*- coding: utf-8 -*-
# trade_advisor.py
# Version: 1.1.0 - Bugfix
# Date: 2025-08-26
"""
CHANGELOG (v1.1.0):
- FIX (Key Mismatch): Sửa lỗi thiếu key 'raw_tech_score' trong kết quả trả về, 
  đây là nguyên nhân gây ra điểm số luôn bằng 0 trong main_bot v2.7.0.
- FIX (Typo): Sửa lỗi chính tả từ 'signal_reason' thành 'reason' để đồng bộ với main_bot.
"""

from signal_logic import check_signal

def get_advisor_decision(symbol: str, interval: str, indicators: dict, config: dict) -> dict:
    """
    Hàm tổng hợp cuối cùng để đưa ra quyết định giao dịch.
    Nó lấy tín hiệu thô, áp dụng các điều chỉnh theo ngữ cảnh và trả về điểm số cuối cùng.
    """
    # 1. Lấy phân tích tín hiệu kỹ thuật từ signal_logic
    signal_details = check_signal(indicators)
    tech_score = signal_details.get("raw_tech_score", 0.0)
    
    # 2. Điều chỉnh điểm số dựa trên sự biến động của thị trường
    volatility_adj = 1.0
    atr_pct = indicators.get("atr_percent", 0)
    if atr_pct > 5.0:
        volatility_adj = 0.9  # Giảm nhẹ điểm nếu biến động quá cao
    elif atr_pct > 3.0:
        volatility_adj = 0.95
    elif atr_pct < 1.0:
        volatility_adj = 1.05 # Tăng nhẹ điểm nếu thị trường đang yên tĩnh (sắp có biến động)
    
    # 3. Điều chỉnh điểm số dựa trên cặp tiền (tùy chọn)
    symbol_adj = 1.0
    if "BTC" in symbol:
        symbol_adj = 1.0
    elif "ETH" in symbol:
        symbol_adj = 1.02
    else:
        symbol_adj = 0.98
    
    # 4. Lấy trọng số từ cấu hình tactic
    weights = config.get('WEIGHTS', {'tech': 1.0, 'context': 0.0, 'ai': 0.0})
    
    # 5. Tính điểm kỹ thuật đã được điều chỉnh
    adjusted_tech_score = tech_score * volatility_adj * symbol_adj
    
    # 6. Tính điểm cuối cùng dựa trên các trọng số (hiện tại chỉ dùng tech_score)
    final_score = (weights['tech'] * adjusted_tech_score) + \
                  (weights['context'] * 0.0) + \
                  (weights['ai'] * 0.0)
    
    # Làm tròn và giới hạn điểm số trong khoảng [-10, 10]
    final_score = round(final_score, 2)
    final_score = max(-10.0, min(10.0, final_score))
    
    # 7. Trả về kết quả đầy đủ cho chương trình chính
    # --- PHẦN SỬA LỖI ---
    # a. Thêm "raw_tech_score" để báo cáo về cho chương trình chính.
    # b. Sửa "signal_reason" thành "reason" để log hiển thị đúng.
    return {
        "final_score": final_score,
        "raw_tech_score": tech_score, # <--- LỖI ĐÃ SỬA
        "reason": signal_details.get("reason"), # <--- LỖI ĐÃ SỬA
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
