# -*- coding: utf-8 -*-
# core/logger_setup.py

import logging
import os
# Đổi từ RotatingFileHandler sang TimedRotatingFileHandler
from logging.handlers import TimedRotatingFileHandler 

def setup_logging():
    """
    Thiết lập hệ thống ghi log chuyên nghiệp cho toàn bộ bot.
    - Hiển thị log INFO trở lên ra màn hình.
    - Ghi log DEBUG trở lên vào file (TỰ ĐỘNG XOAY VÒNG HÀNG NGÀY).
    - Ghi log ERROR trở lên vào file (TỰ ĐỘNG XOAY VÒNG HÀNG NGÀY).
    """
    
    # Xác định thư mục log
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
    LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Lấy logger chính của ứng dụng
    logger = logging.getLogger("ExnessBot")
    logger.setLevel(logging.DEBUG) # Bắt tất cả các log từ cấp độ DEBUG trở lên
    
    # Dọn dẹp các handler cũ để tránh ghi log lặp lại
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # --- Handler 1: Hiển thị ra màn hình (Console) ---
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO) # Chỉ hiển thị INFO và cao hơn
    stream_formatter = logging.Formatter('%(message)s') # Format đơn giản cho màn hình
    stream_handler.setFormatter(stream_formatter)
    
    # --- Handler 2: Ghi vào file info.log (Xoay vòng hàng ngày) ---
    info_log_path = os.path.join(LOG_DIR, "info.log")
    
    # SỬ DỤNG HANDLER MỚI:
    # when='D' (daily): Xoay vòng mỗi ngày
    # interval=1: Mỗi 1 ngày
    # backupCount=30: Giữ lại 30 file log cũ (30 ngày)
    info_handler = TimedRotatingFileHandler(
        info_log_path, 
        when='D', 
        interval=1, 
        backupCount=30, 
        encoding='utf-8'
    )
    info_handler.setLevel(logging.DEBUG) # Ghi lại tất cả mọi thứ vào file
    file_formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] - %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    info_handler.setFormatter(file_formatter)
    
    # --- Handler 3: Ghi vào file error.log (Xoay vòng hàng ngày) ---
    error_log_path = os.path.join(LOG_DIR, "error.log")
    
    # Áp dụng logic tương tự cho file error
    error_handler = TimedRotatingFileHandler(
        error_log_path, 
        when='D', 
        interval=1, 
        backupCount=30, 
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR) # Chỉ ghi ERROR và CRITICAL
    error_handler.setFormatter(file_formatter)
    
    # Thêm các handler vào logger
    logger.addHandler(stream_handler)
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    
    # Ngăn không cho log lan truyền lên root logger
    logger.propagate = False
    
    print("Hệ thống logging (xoay vòng hàng ngày) đã được thiết lập.")