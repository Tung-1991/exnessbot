# -*- coding: utf-8 -*-
# Tên file: signals/adx.py

import pandas as pd
import logging
from typing import Optional, Dict, Any
import pandas_ta as ta  # (MỚI) Import thư viện pandas-ta

logger = logging.getLogger("ExnessBot")

def get_adx_value(
    df_h1: pd.DataFrame,
    config: Dict[str, Any]
) -> float:
    """
    Tính toán giá trị ADX(14) cho nến cuối cùng.
    (ĐÃ SỬA: Sử dụng thư viện pandas_ta cho độ chính xác cao)
    
    Args:
        df_h1 (pd.DataFrame): DataFrame dữ liệu H1 (phải có 'high', 'low', 'close').
        config (Dict[str, Any]): Đối tượng config.

    Returns:
        float: Giá trị ADX cuối cùng (ví dụ: 25.5). Trả về 0.0 nếu lỗi.
    """
    
    # Lấy chu kỳ
    # (Lưu ý: Trong config, DI_PERIOD và ADX_PERIOD đều là 14.
    # Thư viện pandas_ta dùng 1 tham số 'length' cho cả hai,
    # nên ta chỉ cần lấy 1 giá trị là đủ)
    period = config.get("ADX_PERIOD", 14) 
    
    try:
        # Cần đủ dữ liệu (thư viện sẽ tự xử lý, nhưng check cơ bản)
        if len(df_h1) < period:
            logger.warning(f"Không đủ dữ liệu H1 ({len(df_h1)}) để tính ADX({period}).")
            return 0.0

        # 1. Tính toán ADX bằng pandas_ta
        # Ta sử dụng cú pháp "extension" của pandas_ta (df.ta.adx)
        # Nó sẽ tự động tính toán và trả về một DataFrame chứa các cột:
        # ADX_14, DMP_14, DMN_14 (nếu period=14)
        
        # Thêm .copy() để tránh lỗi SettingWithCopyWarning
        df = df_h1.copy()
        adx_results = df.ta.adx(length=period)
        
        if adx_results is None or adx_results.empty:
            logger.error("Lỗi khi tính ADX: pandas_ta trả về None/Empty.")
            return 0.0

        # 2. Lấy cột ADX (tên cột sẽ là 'ADX_period')
        adx_col_name = f"ADX_{period}"
        if adx_col_name not in adx_results.columns:
            logger.error(f"Lỗi khi tính ADX: Không tìm thấy cột '{adx_col_name}'.")
            return 0.0
            
        # 3. Lấy giá trị cuối cùng
        last_adx_value = adx_results[adx_col_name].iloc[-1]

        if pd.isna(last_adx_value):
            # (Thường xảy ra ở các nến đầu tiên, thư viện trả về NaN)
            return 0.0

        return last_adx_value

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi tính ADX (pandas_ta): {e}", exc_info=True)
        return 0.0 # Trả về 0.0 (an toàn)