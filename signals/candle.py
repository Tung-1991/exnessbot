# -*- coding: utf-8 -*-
# Tên file: signals/candle.py

import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger("ExnessBot")

def get_candle_confirmation(
    df_m15: pd.DataFrame,
    config: Dict[str, Any]
) -> bool:
    """
    Kiểm tra xác nhận Nến (Logic GĐ 3 - finalplan.txt).
    Kiểm tra xem nến M15 cuối cùng (nến breakout) có phải là nến mạnh không.

    Args:
        df_m15 (pd.DataFrame): DataFrame dữ liệu M15.
        config (Dict[str, Any]): Đối tượng config.

    Trả về:
        bool: True nếu là nến mạnh, False nếu không.
    """
    
    min_body_percent = config["min_body_percent"]
    
    try:
        if df_m15.empty:
            return False

        # Lấy nến cuối cùng (nến breakout)
        last_candle = df_m15.iloc[-1]

        open_price = last_candle['open']
        high_price = last_candle['high']
        low_price = last_candle['low']
        close_price = last_candle['close']

        # 1. Tính toán Range Nến (High - Low)
        candle_range = high_price - low_price

        # Xử lý lỗi (ví dụ: nến doji, range = 0)
        if candle_range == 0:
            return False

        # 2. Tính toán Body Nến (Giá trị tuyệt đối)
        candle_body = abs(close_price - open_price)

        # 3. Tính toán % Body
        body_percent = (candle_body / candle_range) * 100.0

        # 4. So sánh với ngưỡng
        if body_percent >= min_body_percent:
            # logger.debug(f"XÁC NHẬN NẾN: Body {body_percent:.2f}% >= {min_body_percent}%")
            return True

    except Exception as e:
        logger.error(f"Lỗi khi check Candle Confirmation: {e}", exc_info=True)
        pass

    # Mặc định là False
    return False