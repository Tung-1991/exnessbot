# -*- coding: utf-8 -*-
# Tên file: backtest.py

import os
import pandas as pd
import logging
from typing import Optional
from datetime import datetime, timedelta # (MỚI) Thêm thư viện datetime

# Import các file "Cốt lõi"
from core.logger_setup import setup_logging
from core.trade_manager import TradeManager 

# Import các file "Bộ não"
from signals.signal_generator import get_signal 

# Import file config
import config

logger = logging.getLogger("ExnessBot") 
# logger = logging.getLogger("ExnessBot") 

def _load_and_sync_data() -> Optional[pd.DataFrame]:
    """
    Tải 2 file CSV và đồng bộ H1 vào M15.
    (SỬA LỖI LOOKAHEAD BIAS)
    """
    try:
        path_h1 = os.path.join(config.DATA_DIR, f"{config.SYMBOL}_{config.trend_timeframe}.csv")
        path_m15 = os.path.join(config.DATA_DIR, f"{config.SYMBOL}_{config.entry_timeframe}.csv")

        df_h1 = pd.read_csv(path_h1, index_col='timestamp', parse_dates=True)
        df_m15 = pd.read_csv(path_m15, index_col='timestamp', parse_dates=True)
        
        # --- (THAY ĐỔI) SỬA LỖI LOOKAHEAD BIAS ---
        # 1. Thêm prefix
        df_h1_prefixed = df_h1.add_prefix('h1_')
        # 2. Dịch chuyển (shift) dữ liệu H1 về quá khứ 1 nến
        #    Điều này đảm bảo tại nến M15 (ví dụ 10:15), 
        #    bot chỉ thấy dữ liệu H1 đã đóng (nến 9:00-10:00),
        #    chứ không thấy dữ liệu H1 'tương lai' (nến 10:00-11:00).
        df_h1_shifted = df_h1_prefixed.shift(1)
        
        # 3. Concat với dữ liệu H1 đã dịch chuyển (shifted)
        df_synced = pd.concat([df_m15, df_h1_shifted], axis=1).ffill()
        # --- (HẾT THAY ĐỔI) ---
        
        # 4. Xóa các hàng M15 đầu tiên (không có dữ liệu H1 tương ứng)
        df_synced = df_synced.dropna(subset=['h1_open'])
        
        if df_synced.empty:
            logger.error("Dữ liệu sau khi đồng bộ bị rỗng.")
            return None
            
        logger.info(f"Đã tải và đồng bộ {len(df_synced)} nến M15 (đã sửa lỗi Lookahead Bias).")
        return df_synced
        
    except FileNotFoundError:
        logger.critical(f"LỖI: Không tìm thấy file data. Vui lòng chạy 'download_data.py' trước.")
        return None
    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi tải dữ liệu: {e}", exc_info=True)
        return None

def run_backtest():
    """
    Hàm chính để chạy vòng lặp Backtest "trên giấy".
    """
    logger.info("--- BẮT ĐẦU CHẠY BACKTEST (Chế độ 'trên giấy') ---")
    
    # 1. Tải và đồng bộ dữ liệu
    df_synced = _load_and_sync_data()
    if df_synced is None:
        return

    # 2. Khởi tạo các mô-đun
    
    # Khởi tạo TradeManager ở chế độ "backtest"
    # Truyền config vào
    try:
        trade_manager = TradeManager(
            config=config, # Truyền config
            mode="backtest", 
            initial_capital=config.BACKTEST_INITIAL_CAPITAL
        )
    except Exception as e:
        logger.critical(f"Lỗi khi khởi tạo TradeManager (Backtest): {e}")
        return

    # 3. Vòng lặp chính (Mô phỏng 24/7)
    min_data_h1 = config.NUM_H1_BARS
    min_data_m15 = config.NUM_M15_BARS
    
    logger.info("Bắt đầu lặp qua từng nến M15...")
    
    # Lấy giá trị Cooldown từ config (nếu không có thì mặc định 60)
    cooldown_minutes = config.COOLDOWN_MINUTES if hasattr(config, "COOLDOWN_MINUTES") else 60
    cooldown_delta = timedelta(minutes=cooldown_minutes)
    
    # Lặp từ nến thứ X trở đi
    for i in range(max(min_data_h1, min_data_m15), len(df_synced)):
        
        # 3.1. Lấy dữ liệu lịch sử
        current_m15_data = df_synced.iloc[i - min_data_m15 : i + 1]
        
        h1_subset = df_synced.iloc[: i + 1][['h1_open', 'h1_high', 'h1_low', 'h1_close', 'h1_volume']]
        h1_unique = h1_subset.drop_duplicates(keep='last')
        current_h1_data = h1_unique.iloc[-min_data_h1:]
        current_h1_data.columns = ['open', 'high', 'low', 'close', 'volume']
        
        current_time = current_m15_data.index[-1] # Đây là Timestamp
        current_time_py = current_time.to_pydatetime() # Chuyển sang datetime

        # 3.2. CẬP NHẬT TRƯỚC (Chế độ Backtest)
        try:
            # (Hàm này có thể đóng lệnh và kích hoạt Cooldown)
            trade_manager.update_all_trades(current_h1_data, current_m15_data)
        except Exception as e:
            logger.error(f"[{current_time}] Lỗi khi update_all_trades (Backtest): {e}", exc_info=False)


        # --- [LOGIC MỚI] KIỂM TRA COOLDOWN CHO BACKTEST ---
        is_in_cooldown = False
        if trade_manager.last_trade_close_time_str:
            try:
                last_close_time = datetime.fromisoformat(trade_manager.last_trade_close_time_str)
                
                # Nếu chưa hết cooldown -> bỏ qua tìm tín hiệu
                if current_time_py < (last_close_time + cooldown_delta):
                    is_in_cooldown = True
                else:
                    # Hết cooldown, reset
                    trade_manager.last_trade_close_time_str = None
                    # (Không cần save state vì đây là backtest)
            except Exception as e:
                logger.error(f"Lỗi xử lý Cooldown (Backtest): {e}")
                trade_manager.last_trade_close_time_str = None # Reset nếu lỗi
        
        # Nếu đang cooldown, bỏ qua bước 3.3 và 3.4
        if is_in_cooldown:
            continue
        # --- [HẾT LOGIC MỚI] ---
        

        # 3.3. TÌM TÍN HIỆU
        
        # (Kiểm tra max_trade trước khi tìm tín hiệu để tiết kiệm tài nguyên)
        if trade_manager._get_open_trade_count() >= trade_manager.max_trade:
            signal = None
        else:
            try:
                # Truyền config vào
                signal = get_signal(current_h1_data, current_m15_data, config) # "BUY", "SELL", None
            except Exception as e:
                logger.error(f"[{current_time}] Lỗi khi get_signal: {e}", exc_info=False)
                signal = None
            
        # 3.4. HÀNH ĐỘNG (Chế độ Backtest)
        if signal:
            try:
                # (Hàm open_trade đã có check max_trade bên trong 
                # để xử lý race condition, nhưng check ở 3.3 vẫn tốt hơn)
                trade_manager.open_trade(signal, current_h1_data, current_m15_data)
            except Exception as e:
                logger.error(f"[{current_time}] Lỗi khi open_trade ({signal}) (Backtest): {e}", exc_info=False)

    logger.info("--- HOÀN TẤT VÒNG LẶP BACKTEST ---")
    
    # 4. Xuất kết quả
    try:
        results_df = trade_manager.get_backtest_results_df()
        if results_df.empty:
            logger.warning("Backtest hoàn tất. Không có lệnh nào được thực hiện.")
            return

        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(config.OUTPUT_DIR, config.RESULTS_CSV_FILE)
        
        results_df.to_csv(output_path, index=False)
        logger.info(f"Đã lưu kết quả Backtest ( {len(results_df)} lệnh) vào: {output_path}")

    except Exception as e:
        logger.error(f"Lỗi khi xuất kết quả backtest: {e}", exc_info=True)


if __name__ == "__main__":
    setup_logging()
    run_backtest()