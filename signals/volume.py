# -*- coding: utf-8 -*-
# Tên file: signals/volume.py

import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger("ExnessBot")

def get_volume_confirmation(
    df_m15: pd.DataFrame,
    config: Dict[str, Any]
) -> bool:
    """
    Kiểm tra xác nhận Volume (Logic StdDev - finalplan.txt).
    Kiểm tra xem Volume của nến breakout (nến cuối cùng)
    có vượt trội so với trung bình (cộng độ lệch chuẩn) hay không.

    Args:
        df_m15 (pd.DataFrame): DataFrame dữ liệu M15.
        config (Dict[str, Any]): Đối tượng config.

    Trả về:
        bool: True nếu volume mạnh, False nếu không.
    """
    
    volume_ma_period = config["volume_ma_period"]
    volume_sd_multiplier = config["volume_sd_multiplier"]
    
    try:
        # Cần ít nhất (chu kỳ + 1 nến breakout) để tính toán
        if len(df_m15) < volume_ma_period + 1:
            # logger.debug("Không đủ dữ liệu M15 để tính Volume VMA/StdDev.")
            return False

        # Lấy volume của nến breakout (nến cuối cùng)
        breakout_volume = df_m15['volume'].iloc[-1]

        # Lấy (volume_ma_period) nến TRƯỚC nến breakout để làm cơ sở
        # Ví dụ: nếu period=20, sẽ lấy 20 nến (từ -21 đến -2)
        previous_volumes = df_m15['volume'].iloc[-(volume_ma_period + 1) : -1]

        if len(previous_volumes) < volume_ma_period:
             # (Check an toàn lần nữa)
            return False

        # Tính toán VMA (Volume Moving Average) và StdDev
        vma = previous_volumes.mean()
        std_dev = previous_volumes.std()

        # Xử lý lỗi (ví dụ: data đầu vào bị lỗi, hoặc std_dev=NaN)
        if pd.isna(vma) or pd.isna(std_dev) or vma == 0:
            # logger.warning("VMA hoặc StdDev Volume không hợp lệ (NaN/0).")
            return False

        # --- Logic Cốt lõi (finalplan.txt) ---
        volume_threshold = vma + (std_dev * volume_sd_multiplier)

        if breakout_volume > volume_threshold:
            # logger.debug(f"XÁC NHẬN VOLUME: {breakout_volume:.2f} > {volume_threshold:.2f}")
            return True

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi check Volume (StdDev logic): {e}", exc_info=True)
        pass

    # Mặc định là False
    return False