import MetaTrader5 as mt5

# --- HÀM KIỂM TRA KẾT NỐI ---

def test_mt5_connection():
    """
    Hàm này chỉ làm một việc: cố gắng kết nối với MetaTrader 5
    và in ra kết quả.
    """
    print("Đang cố gắng kết nối với MetaTrader 5...")

    # Cố gắng khởi tạo kết nối
    # Cần đảm bảo phần mềm MT5 đang chạy và đã đăng nhập
    if not mt5.initialize():
        # Nếu thất bại, in ra mã lỗi và thoát
        print("KẾT NỐI THẤT BẠI!")
        print(f"Lý do: initialize() failed, error code = {mt5.last_error()}")
        return

    # Nếu thành công, in ra thông báo và một vài thông tin cơ bản
    print("--------------------------------------------------")
    print("✅ KẾT NỐI THÀNH CÔNG!")
    print(f"Phiên bản MetaTrader 5 terminal: {mt5.version()}")
    
    # Lấy thông tin tài khoản để chắc chắn rằng đã kết nối đúng
    account_info = mt5.account_info()
    if account_info:
        print(f"Đã kết nối tới tài khoản: {account_info.login}")
        print(f"Máy chủ (Server): {account_info.server}")
        print(f"Số dư (Balance): {account_info.balance} {account_info.currency}")
    
    # Luôn luôn đóng kết nối khi không dùng nữa
    mt5.shutdown()
    print("Đã đóng kết nối an toàn.")
    print("--------------------------------------------------")


# --- CHẠY CHƯƠG TRÌNH ---
if __name__ == "__main__":
    test_mt5_connection()