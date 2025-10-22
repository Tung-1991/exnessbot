# -*- coding: utf-8 -*-
# backtest.py (v6.0 - Final - Hỗ trợ MTF & Hybrid ATR)

import pandas as pd
import numpy as np
from typing import Dict, Any, List
import logging

# --- BƯỚC 1: IMPORT CÁC MODULE v6.0 ---
# Import config v6.0 (File Bước 1)
import config 
# Import hàm tính điểm v6.0 (File Bước 2)
from signals.signal_generator import get_final_signal
# Import hàm quản lý vốn v6.0 (File Bước 3)
from core.risk_manager import calculate_trade_details
# Import hàm tính ATR (cho TSL)
from signals.atr import calculate_atr

# Thiết lập logger (để xem log debug của các hàm)
logger = logging.getLogger("ExnessBot")
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# --- BƯỚC 2: CẤU HÌNH BACKTEST ---
INITIAL_CAPITAL = 1000.0

# --- CẤU HÌNH DATA ĐA KHUNG (MTF) ---
# Quan trọng: Đảm bảo 2 file này khớp với config.TIMEFRAME và config.TREND_TIMEFRAME
DATA_FILE_PATH_MAIN = "data/ETHUSD_15m_6M.csv" # Dữ liệu cho config.TIMEFRAME
DATA_FILE_PATH_TREND = "data/ETHUSD_1h_6M.csv"  # Dữ liệu cho config.TREND_TIMEFRAME

CONTRACT_SIZE = 1.0 # Kích thước hợp đồng (1.0 cho 1 ETH)
CANDLE_FETCH_COUNT = config.CANDLE_FETCH_COUNT # Số nến lịch sử cần để tính chỉ báo

# Đặt thành True để xem bảng phân tích điểm số chi tiết của từng tín hiệu.
SHOW_DETAILED_LOG = True

# Lấy config dictionary v6.0 (quan trọng)
config_dict = config.__dict__

def print_score_details(timestamp: Any, details: Dict[str, Any]):
    """
    In ra bảng phân tích điểm số chi tiết v6.0.
    """
    long_scores = details.get("long", {})
    short_scores = details.get("short", {})
    trend_bias = details.get("trend_bias", 0)
    
    long_total = sum(long_scores.values())
    short_total = sum(short_scores.values())
    
    trend_str = "TĂNG (Bias: 1)" if trend_bias == 1 else ("GIẢM (Bias: -1)" if trend_bias == -1 else "NEUTRAL (Bias: 0)")

    # --- Bắt đầu in ---
    print(f"[{timestamp}] --- PHÂN TÍCH TÍN HIỆU (Xu hướng H1: {trend_str}) ---")
    
    # --- PHE LONG ---
    print(f"==> PHE LONG (Tổng: {long_total:.1f})")
    long_str = " | ".join([f"{k}: {v:.1f}" for k, v in long_scores.items() if v > 0])
    print(f"    {long_str if long_str else 'Không có điểm'}")

    # --- PHE SHORT ---
    print(f"\n==> PHE SHORT (Tổng: {short_total:.1f})")
    short_str = " | ".join([f"{k}: {v:.1f}" for k, v in short_scores.items() if v > 0])
    print(f"    {short_str if short_str else 'Không có điểm'}")
    
    print("="*60)

def prepare_data():
    """Tải và đồng bộ hóa hai dataframe MTF."""
    try:
        df_main = pd.read_csv(DATA_FILE_PATH_MAIN, index_col='timestamp', parse_dates=True)
        df_trend = pd.read_csv(DATA_FILE_PATH_TREND, index_col='timestamp', parse_dates=True)
        
        df_main.rename(columns={'tick_volume': 'volume'}, inplace=True, errors='ignore')
        df_trend.rename(columns={'tick_volume': 'volume'}, inplace=True, errors='ignore')
    except FileNotFoundError as e:
        print(f"LỖI: Không tìm thấy file dữ liệu: {e.filename}")
        return None, None
        
    # Đồng bộ hóa: Đảm bảo df_main chỉ chứa các nến mà df_trend cũng có
    # (Ví dụ: nến 15m, 30m, 45m sẽ được giữ lại nếu nến 00m tồn tại)
    df_main = df_main[df_main.index.floor('h').isin(df_trend.index)]
    
    if df_main.empty:
        print("LỖI: Không có dữ liệu sau khi đồng bộ hóa. Kiểm tra lại 2 file data.")
        return None, None
        
    print(f"Đã tải {len(df_main)} nến {config.TIMEFRAME} và {len(df_trend)} nến {config.TREND_TIMEFRAME}.")
    return df_main, df_trend

def run_backtest():
    print("--- Bắt đầu chạy Backtest (v6.0 - MTF & Hybrid ATR) ---")
    
    # 1. Tải và chuẩn bị dữ liệu MTF
    df_main, df_trend = prepare_data()
    if df_main is None:
        return

    # 2. Thiết lập "luật chơi"
    balance = INITIAL_CAPITAL
    equity_curve = [INITIAL_CAPITAL]
    active_trades: List[Dict[str, Any]] = []
    trade_history: List[Dict[str, Any]] = []
    cooldown_until_index = 0

    print(f"Bắt đầu giả lập trên {len(df_main)} nến (đã đồng bộ)...")

    # 3. Vòng lặp Giả lập
    for i in range(CANDLE_FETCH_COUNT, len(df_main)):
        
        # --- LẤY DATA SLICE (MTF) ---
        # Data chính (15m)
        historical_df_main = df_main.iloc[i - CANDLE_FETCH_COUNT : i]
        current_candle_main = df_main.iloc[i]
        
        # Data xu hướng (1h)
        # Tìm nến 1h tương ứng với nến 15m hiện tại
        current_trend_time = current_candle_main.name.floor('h')
        trend_index_loc = df_trend.index.get_loc(current_trend_time)
        historical_df_trend = df_trend.iloc[trend_index_loc - CANDLE_FETCH_COUNT : trend_index_loc]

        if historical_df_trend.empty:
            continue # Bỏ qua nếu không có đủ data xu hướng

        # --- A. QUẢN LÝ LỆNH MỞ (Hybrid ATR - Điểm 4 & TSL - Điểm 7) ---
        trade_management_config = config_dict.get('ACTIVE_TRADE_MANAGEMENT', {})
        
        # Tính toán score MỚI NHẤT cho logic thoát lệnh (Điểm 4)
        current_long_score, current_short_score, _ = get_final_signal(
            historical_df_main, historical_df_trend, config_dict
        )
        
        for trade in active_trades[:]:
            pnl = 0.0
            is_long = trade['type'] == 'LONG'
            
            # Giá hiện tại (giả định khớp ở giá Mở cửa của nến tiếp theo)
            current_price = current_candle_main['open']
            
            # Tính PnL (R:R)
            price_change = (current_price - trade['entry_price']) if is_long else (trade['entry_price'] - current_price)
            pnl_usd = price_change * trade['lot_size'] * CONTRACT_SIZE
            pnl_r = pnl_usd / trade['initial_risk_usd'] if trade['initial_risk_usd'] > 0 else 0.0
            trade['peak_pnl_r'] = max(trade.get('peak_pnl_r', 0.0), pnl_r)

            # --- Check 5 ĐIỀU KIỆN THOÁT LỆNH (Song song) ---
            trade_closed = False
            close_price = 0.0
            close_reason = "Unknown"

            # 1. Thoát lệnh theo SL/TP (ATR 3 Cấp)
            if is_long:
                if current_candle_main['low'] <= trade['sl_price']:
                    trade_closed = True; close_price = trade['sl_price']; close_reason = "Stop Loss"
                elif current_candle_main['high'] >= trade['tp_price']:
                    trade_closed = True; close_price = trade['tp_price']; close_reason = "Take Profit"
            else: # SHORT
                if current_candle_main['high'] >= trade['sl_price']:
                    trade_closed = True; close_price = trade['sl_price']; close_reason = "Stop Loss"
                elif current_candle_main['low'] <= trade['tp_price']:
                    trade_closed = True; close_price = trade['tp_price']; close_reason = "Take Profit"

            # 2. Thoát lệnh theo TSL (Điểm 7)
            if not trade_closed and trade_management_config.get("ENABLE_TSL"):
                atr_series = calculate_atr(historical_df_main, config.ATR_PERIOD)
                current_atr = atr_series.iloc[-1] 
                trail_distance = current_atr * trade_management_config.get('TSL_ATR_MULTIPLIER', 2.5)
                
                if is_long:
                    new_potential_sl = current_price - trail_distance
                    if new_potential_sl > trade['sl_price']: trade['sl_price'] = new_potential_sl
                else:
                    new_potential_sl = current_price + trail_distance
                    if new_potential_sl < trade['sl_price']: trade['sl_price'] = new_potential_sl
                # (Logic TSL đã được tích hợp vào check SL/TP ở trên)
            
            # 3 & 4. Thoát lệnh theo TP1 & PP (Điểm 7)
            if not trade_closed and trade_management_config.get("ENABLE_TP1") and not trade.get("tp1_hit") and pnl_r >= trade_management_config.get("TP1_RR_RATIO", 1.0):
                trade['tp1_hit'] = True
                if trade_management_config.get("TP1_MOVE_SL_TO_ENTRY", True):
                    trade['sl_price'] = trade['entry_price'] # Dời SL về entry
                # (Logic chốt 50% bị bỏ qua trong backtest này để đơn giản hóa,
                #  nó chỉ mô phỏng việc dời SL)

            if (not trade_closed and trade_management_config.get("ENABLE_PROTECT_PROFIT") and
                not trade.get("pp_triggered") and not trade.get("tp1_hit") and
                trade['peak_pnl_r'] >= trade_management_config.get("PP_MIN_PEAK_R_TRIGGER", 1.2) and
                (trade['peak_pnl_r'] - pnl_r) >= trade_management_config.get("PP_DROP_R_TRIGGER", 0.4)):
                trade['pp_triggered'] = True
                if trade_management_config.get("PP_MOVE_SL_TO_ENTRY", True):
                    trade['sl_price'] = trade['entry_price'] # Dời SL về entry

            # 5. Thoát lệnh theo SCORE (Hybrid ATR - Điểm 4)
            if not trade_closed and config_dict.get('ENABLE_SCORE_BASED_EXIT', False):
                current_score = current_long_score if is_long else current_short_score
                exit_threshold = config_dict.get('EXIT_SCORE_THRESHOLD', 40.0)
                
                if current_score < exit_threshold:
                    trade_closed = True
                    close_price = current_candle_main['open'] # Thoát ngay lập tức
                    close_reason = f"Score Exit ({current_score:.1f} < {exit_threshold})"

            # --- Xử lý Đóng Lệnh ---
            if trade_closed:
                price_change = (close_price - trade['entry_price']) if is_long else (trade['entry_price'] - close_price)
                pnl = price_change * trade['lot_size'] * CONTRACT_SIZE
                balance += pnl
                equity_curve.append(balance)
                
                trade['close_time'] = current_candle_main.name
                trade['pnl'] = pnl
                trade['close_reason'] = close_reason
                trade_history.append(trade)
                active_trades.remove(trade)
                cooldown_until_index = i + config_dict.get('COOLDOWN_CANDLES', 0)

        # --- B. TÌM TÍN HIỆU MỚI (Logic 3 Cấp) ---
        can_open_trade = (i >= cooldown_until_index) and (len(active_trades) < config.MAX_ACTIVE_TRADES)
        
        if can_open_trade:
            # (Chúng ta đã tính score ở trên, dùng lại)
            final_long_score = current_long_score
            final_short_score = current_short_score
            
            if SHOW_DETAILED_LOG and (final_long_score > 0 or final_short_score > 0):
                # (Tải lại data slice LẦN CUỐI cùng với nến hiện tại để in log cho đúng)
                df_main_with_current = df_main.iloc[i - CANDLE_FETCH_COUNT : i+1]
                df_trend_with_current = df_trend.iloc[trend_index_loc - CANDLE_FETCH_COUNT : trend_index_loc+1]
                _, _, score_details_log = get_final_signal(df_main_with_current, df_trend_with_current, config_dict)
                print_score_details(current_candle_main.name, score_details_log)

            # --- Logic Vào Lệnh 3 Cấp (Điểm 9) ---
            entry_levels = config_dict.get('ENTRY_SCORE_LEVELS', [90.0, 120.0, 150.0])
            signal = 0
            score_level = 0
            final_score = 0.0

            if config.ENABLE_LONG_TRADES and final_long_score > final_short_score and final_long_score >= entry_levels[0]:
                signal = 1; final_score = final_long_score
            elif config.ENABLE_SHORT_TRADES and final_short_score > final_long_score and final_short_score >= entry_levels[0]:
                signal = -1; final_score = final_short_score
            
            if signal != 0:
                # Xác định Cấp (Level)
                if final_score >= entry_levels[2]: score_level = 3
                elif final_score >= entry_levels[1]: score_level = 2
                else: score_level = 1
                
                entry_price = current_candle_main['open'] # Vào lệnh ở nến tiếp theo
                
                # Gọi Risk Manager v6.0 (Bước 3) với đúng level
                trade_details = calculate_trade_details(
                    historical_df_main, entry_price, signal, balance, config_dict, score_level
                )
                
                if trade_details:
                    lot_size, sl_price, tp_price = trade_details
                    initial_risk = abs(entry_price - sl_price) * lot_size * CONTRACT_SIZE
                    
                    if lot_size > 0 and balance > initial_risk:
                        new_trade = {
                            "entry_time": current_candle_main.name,
                            "entry_price": entry_price,
                            "type": "LONG" if signal == 1 else "SHORT",
                            "lot_size": lot_size,
                            "sl_price": sl_price,
                            "tp_price": tp_price,
                            "initial_risk_usd": initial_risk,
                            "score": final_score,
                            "score_level": score_level,
                            "tp1_hit": False,
                            "pp_triggered": False,
                            "peak_pnl_r": 0.0
                        }
                        active_trades.append(new_trade)
                        print(f"[{current_candle_main.name}] >>> LỆNH {new_trade['type']} [CẤP {score_level}] ĐƯỢC THỰC THI (Điểm {final_score:.1f}) <<<")

    # 4. Đóng tất cả các lệnh còn lại vào cuối kỳ
    if active_trades:
        last_price = df_main.iloc[-1]['close']
        for trade in active_trades:
            price_change = (last_price - trade['entry_price']) if trade['type'] == 'LONG' else (trade['entry_price'] - last_price)
            pnl = price_change * trade['lot_size'] * CONTRACT_SIZE
            balance += pnl
            equity_curve.append(balance)
            trade['close_time'] = df_main.index[-1]
            trade['pnl'] = pnl
            trade['close_reason'] = "End of Backtest"
            trade_history.append(trade)

    # 5. In Báo Cáo Kết Quả Nâng Cao (Giữ nguyên)
    print("\n--- KẾT QUẢ BACKTEST (v6.0 - MTF & Hybrid ATR) ---")
    print(f"Data Chính: {DATA_FILE_PATH_MAIN} ({config.TIMEFRAME})")
    print(f"Data Xu Hướng: {DATA_FILE_PATH_TREND} ({config.TREND_TIMEFRAME})")
    print("--------------------------------------------------")
    
    total_pnl = balance - INITIAL_CAPITAL
    total_return_pct = (total_pnl / INITIAL_CAPITAL) * 100
    print(f"Vốn ban đầu:      ${INITIAL_CAPITAL:,.2f}")
    print(f"Số dư cuối kỳ:     ${balance:,.2f}")
    print(f"Tổng Lợi nhuận/Lỗ: ${total_pnl:,.2f} ({total_return_pct:,.2f}%)")

    if not trade_history:
        print("\nKhông có lệnh nào được thực hiện.")
        return

    total_trades = len(trade_history)
    wins = [t for t in trade_history if t['pnl'] > 0]
    losses = [t for t in trade_history if t['pnl'] <= 0]
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    
    print(f"\nTổng số lệnh:       {total_trades}")
    print(f"Số lệnh thắng:      {len(wins)}")
    print(f"Số lệnh thua:       {len(losses)}")
    print(f"Tỷ lệ thắng:         {win_rate:,.2f}%")
    
    total_gross_profit = sum(t['pnl'] for t in wins)
    total_gross_loss = abs(sum(t['pnl'] for t in losses))
    profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else float('inf')
    avg_win = total_gross_profit / len(wins) if wins else 0
    avg_loss = total_gross_loss / len(losses) if losses else 0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')
    
    print(f"\nLợi nhuận gộp:      ${total_gross_profit:,.2f}")
    print(f"Lỗ gộp:             ${total_gross_loss:,.2f}")
    print(f"Profit Factor:      {profit_factor:,.2f}")
    print(f"Trung bình Thắng:   ${avg_win:,.2f}")
    print(f"Trung bình Thua:    ${avg_loss:,.2f}")
    print(f"Tỷ lệ R:R (TB):      {rr_ratio:,.2f}:1")
    
    equity_series = pd.Series(equity_curve)
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    max_drawdown_pct = abs(drawdown.min() * 100)
    
    print(f"\nSụt giảm vốn tối đa: {max_drawdown_pct:,.2f}%")

    long_trades = [t for t in trade_history if t['type'] == 'LONG']
    short_trades = [t for t in trade_history if t['type'] == 'SHORT']
    print(f"\nSố lệnh Long:       {len(long_trades)} (Thắng: {len([t for t in long_trades if t['pnl'] > 0])})")
    print(f"Số lệnh Short:      {len(short_trades)} (Thắng: {len([t for t in short_trades if t['pnl'] > 0])})")
    
    # Phân tích lý do đóng lệnh
    print("\n--- Phân tích Lý do Đóng lệnh ---")
    reasons = pd.Series([t['close_reason'] for t in trade_history]).value_counts()
    for reason, count in reasons.items():
        print(f"  {reason:<25}: {count} lệnh")


if __name__ == "__main__":
    run_backtest()