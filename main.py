# -*- coding: utf-8 -*-
# main.py

# Import các module cần thiết
import config
from core.trade_manager import TradeManager
from dotenv import load_dotenv
import os

def main():
    """
    Hàm chính để khởi chạy bot.
    """
    # Tải các biến môi trường từ file .env
    load_dotenv()
    
    # Tạo một thực thể của TradeManager với file cấu hình
    bot = TradeManager(config.__dict__)
    
    # Bắt đầu chạy bot
    bot.run()

if __name__ == "__main__":
    main()