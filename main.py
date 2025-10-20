# main.py
import config
from core.trade_manager import TradeManager
from dotenv import load_dotenv
import os
import logging  # <-- Thêm vào
from core.logger_setup import setup_logging  # <-- Thêm vào

def main():
    """
    Hàm chính để khởi chạy bot.
    """
    # Tải các biến môi trường từ file .env
    load_dotenv()
    
    # Thiết lập hệ thống logging ngay từ đầu
    setup_logging()  # <-- Thêm vào
    logger = logging.getLogger("ExnessBot") # <-- Thêm vào
    logger.info("===================================")
    logger.info("Khởi chạy Exness Bot...")
    
    # Tạo một thực thể của TradeManager với file cấu hình
    bot = TradeManager(config.__dict__)
    
    # Bắt đầu chạy bot
    bot.run()

if __name__ == "__main__":
    main()