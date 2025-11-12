# -*- coding: utf-8 -*-
# Tên file: signals/supertrend.py

import pandas as pd
import logging
from typing import Dict, Any
# Import hàm ATR từ file chúng ta đã có
from signals.atr import calculate_atr 

logger = logging.getLogger("ExnessBot")

def get_supertrend_direction(
    df_h1: pd.DataFrame,
    config: Dict[str, Any]
) -> str:
    """
    Tính toán Supertrend và trả về hướng của nến cuối cùng.
    
    Args:
        df_h1 (pd.DataFrame): DataFrame dữ liệu H1.
        config (Dict[str, Any]): Đối tượng config.

    Returns:
        str: "UP" (nếu Supertrend đang màu xanh), 
             "DOWN" (nếu Supertrend đang màu đỏ).
    """
    
    atr_period = config["ST_ATR_PERIOD"]
    multiplier = config["ST_MULTIPLIER"]
    
    try:
        # 1. Tính ATR
        atr = calculate_atr(df_h1, atr_period)
        if atr is None:
            logger.warning("Không thể tính ATR cho Supertrend.")
            return "DOWN" # Mặc định an toàn

        # 2. Tính toán Upper/Lower Band cơ bản
        hl2 = (df_h1['high'] + df_h1['low']) / 2
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)

        # 3. Tính toán Supertrend cuối cùng
        # Khởi tạo cột final_band và direction
        final_band = pd.Series(0.0, index=df_h1.index)
        direction = pd.Series(True, index=df_h1.index) # True = UP, False = DOWN

        for i in range(1, len(df_h1)):
            # --- Logic Supertrend ---
            
            # Nếu giá đóng cửa nến trước > band trên nến trước
            if df_h1['close'].iloc[i-1] > final_band.iloc[i-1]:
                # Trend đang LÊN
                direction.iloc[i] = True
                # Nếu lower_band hiện tại > final_band trước -> nâng band lên
                final_band.iloc[i] = max(lower_band.iloc[i], final_band.iloc[i-1])
            else:
                # Trend đang XUỐNG
                direction.iloc[i] = False
                # Nếu upper_band hiện tại < final_band trước -> hạ band xuống
                final_band.iloc[i] = min(upper_band.iloc[i], final_band.iloc[i-1])

        # 4. Lấy kết quả của nến cuối cùng
        last_direction_is_up = direction.iloc[-1]

        if last_direction_is_up:
            return "UP"
        else:
            return "DOWN"

    except Exception as e:
        logger.error(f"Lỗi khi tính Supertrend: {e}", exc_info=True)
        return "DOWN" # Mặc định an toàn