# -*- coding: utf-8 -*-
# core/storage_manager.py

import json
import os
from typing import Dict, Any

# Xác định đường dẫn tới file trạng thái
# Giả định file này nằm trong thư mục core/, thư mục data/ nằm cùng cấp với core/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
STATE_FILE_PATH = os.path.join(PROJECT_ROOT, "data", "trades_state.json")

def load_state() -> Dict[str, Any]:
    """
    Tải trạng thái của bot từ file JSON.
    Nếu file không tồn tại hoặc bị lỗi, trả về một trạng thái mặc định.
    """
    default_state = {
        "active_trades": [],   # Danh sách các lệnh đang được bot quản lý
        "trade_history": [],   # Lịch sử các lệnh đã đóng
        "account_stats": {},   # Các thông số thống kê về tài khoản
        "last_trade_close_time": None # (MỚI) Thêm để theo dõi Cooldown
    }
    
    if not os.path.exists(STATE_FILE_PATH):
        print("[INFO] Không tìm thấy file trạng thái, sẽ tạo file mới.")
        return default_state
        
    try:
        with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
            # Đảm bảo các key cơ bản luôn tồn tại
            for key, value in default_state.items():
                state.setdefault(key, value)
            print("[INFO] Đã tải trạng thái từ file trades_state.json thành công.")
            return state
    except (json.JSONDecodeError, FileNotFoundError):
        print("[WARNING] File trạng thái bị lỗi hoặc không đọc được. Bắt đầu với trạng thái mới.")
        return default_state

def save_state(state_data: Dict[str, Any]):
    """
    Lưu trạng thái hiện tại của bot vào file JSON.
    """
    try:
        # Tạo thư mục data nếu chưa có
        os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)
        
        with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=4, ensure_ascii=False)
        # print("[DEBUG] Đã lưu trạng thái bot thành công.") # Có thể bật để gỡ lỗi
    except Exception as e:
        print(f"[ERROR] Lỗi nghiêm trọng khi lưu trạng thái: {e}")