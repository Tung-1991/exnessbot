# -*- coding: utf-8 -*-
# Tên file: signals/swing_point.py

import pandas as pd
import numpy as np
import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("ExnessBot")

def get_last_swing_points(
    df: pd.DataFrame,
    config: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float]]:
    """
    Tìm giá Swing High và Swing Low GẦN NHẤT (mới nhất).
    
    Logic (theo finalplan.txt):
    - swing_period = 5 nghĩa là 1 nến trung tâm, 2 nến trái, 2 nến phải.
    - Swing Low: Nến có Low thấp nhất trong 5 nến.
    - Swing High: Nến có High cao nhất trong 5 nến.

    Args:
        df (pd.DataFrame): DataFrame dữ liệu.
        config (Dict[str, Any]): Đối tượng config.

    Returns:
        Tuple[Optional[float], Optional[float]]: 
        (last_swing_high_price, last_swing_low_price)
    """
    
    swing_period = config["swing_period"]
    
    last_swing_high_price: Optional[float] = None
    last_swing_low_price: Optional[float] = None

    try:
        if len(df) < swing_period:
            # Không đủ nến để tìm
            return None, None

        # (n) là số nến ở mỗi bên của nến trung tâm
        # swing_period = 5 -> n = 2 (2 trái, 1 giữa, 2 phải)
        n = (swing_period - 1) // 2
        
        # Chỉ check các nến có đủ 'n' nến ở 2 bên
        # Lùi từ nến gần nhất có thể check (index -1-n)
        
        # Chuyển sang numpy array để xử lý nhanh hơn
        highs_arr = df['high'].values
        lows_arr = df['low'].values
        
        # Lặp ngược từ nến gần nhất có thể check (cách đây n nến)
        # về nến xa nhất có thể check (nến thứ n)
        for i in range(len(df) - 1 - n, n - 1, -1):
            
            # --- Check Swing High ---
            if last_swing_high_price is None: # Nếu chưa tìm thấy
                # Lấy cửa sổ (window) gồm 'swing_period' nến
                window = highs_arr[i-n : i+n+1]
                
                # Nếu nến 'i' là cao nhất trong cửa sổ
                if highs_arr[i] == np.max(window):
                    # (Check thêm để đảm bảo nó là đỉnh duy nhất)
                    if np.sum(window == highs_arr[i]) == 1: 
                        last_swing_high_price = highs_arr[i]

            # --- Check Swing Low ---
            if last_swing_low_price is None: # Nếu chưa tìm thấy
                window = lows_arr[i-n : i+n+1]
                
                # Nếu nến 'i' là thấp nhất trong cửa sổ
                if lows_arr[i] == np.min(window):
                    # (Check thêm để đảm bảo nó là đáy duy nhất)
                    if np.sum(window == lows_arr[i]) == 1:
                        last_swing_low_price = lows_arr[i]

            # Tối ưu: Nếu đã tìm thấy cả 2 thì thoát sớm
            if last_swing_high_price is not None and last_swing_low_price is not None:
                break
                
        return last_swing_high_price, last_swing_low_price

    except Exception as e:
        logger.error(f"Lỗi khi tìm Last Swing Points: {e}", exc_info=True)
        return None, None