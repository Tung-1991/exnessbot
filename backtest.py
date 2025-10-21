# -*- coding: utf-8 -*-
# backtest.py (v6.0 - Phòng Thí Nghiệm "Bộ Luật V2.3")

import pandas as pd
import numpy as np
from typing import Dict, Any, List
import config

# Import các hàm tính toán và logic tín hiệu mới nhất
from signals.signal_generator import get_final_signal
from core.risk_manager import calculate_trade_details

# --- CẤU HÌNH BACKTEST ---
INITIAL_CAPITAL = 1000.0
DATA_FILE_PATH = "data/ETHUSD_15m_6M.csv" # Đường dẫn tới file dữ liệu
CONTRACT_SIZE = 1.0 # Kích thước hợp đồng (ví dụ: 1.0 cho 1 ETH)
CANDLE_FETCH_COUNT = config.CANDLE_FETCH_COUNT # Số nến lịch sử cần để tính chỉ báo

# --- CẤU HÌNH HIỂN THỊ LOG ---
# Đặt thành True để xem bảng phân tích chi tiết của từng tín hiệu.
# Đặt thành False để chỉ xem báo cáo tổng kết cuối cùng (chạy nhanh hơn).
SHOW_DETAILED_LOG = True

# Lấy config dictionary (quan trọng)
config_dict = config.__dict__

def print_score_details(timestamp: Any, details: Dict[str, Any]):
    """
    In ra bảng phân tích điểm số chi tiết và dễ hiểu.
    """
    raw_long = details.get("raw", {}).get("long", {})
    raw_short = details.get("raw", {}).get("short", {})
    adj_long = details.get("adj", {}).get("long", {})
    adj_short = details.get("adj", {}).get("short", {})
    
    raw_long_total = details.get("raw", {}).get("long_total", 0.0)
    raw_short_total = details.get("raw", {}).get("short_total", 0.0)
    adj_long_total = details.get("adj", {}).get("long_total", 0.0)
    adj_short_total = details.get("adj", {}).get("short_total", 0.0)
    
    final_long = details.get("final", {}).get("long", 0.0)
    final_short = details.get("final", {}).get("short", 0.0)
    
    signal = details.get("final", {}).get("signal", 0)

    # --- Bắt đầu in ---
    print(f"[{timestamp}] --- PHÂN TÍCH TÍN HIỆU ---")
    
    # --- PHE LONG ---
    print("==> PHE LONG")
    raw_str_long = " | ".join([f"{k}: {v:.1f}" for k, v in raw_long.items()])
    adj_str_long = " | ".join([f"{k}: {v:+.1f}" for k, v in adj_long.items()])
    print(f"    [Khởi Tạo] {raw_str_long} => Tổng: {raw_long_total:.1f}")
    print(f"    [Xác Nhận] {adj_str_long} => Tổng: {adj_long_total:+.1f}")
    print("    " + "-"*50)
    print(f"    >> ĐIỂM LONG CUỐI CÙNG: {final_long:.1f}")
    print()

    # --- PHE SHORT ---
    print("==> PHE SHORT")
    raw_str_short = " | ".join([f"{k}: {v:.1f}" for k, v in raw_short.items()])
    adj_str_short = " | ".join([f"{k}: {v:+.1f}" for k, v in adj_short.items()])
    print(f"    [Khởi Tạo] {raw_str_short} => Tổng: {raw_short_total:.1f}")
    print(f"    [Xác Nhận] {adj_str_short} => Tổng: {adj_short_total:+.1f}")
    print("    " + "-"*50)
    print(f"    >> ĐIỂM SHORT CUỐI CÙNG: {final_short:.1f}")
    print()

    # --- QUYẾT ĐỊNH ---
    decision = "BỎ QUA"
    if signal == 1:
        decision = "QUYẾT ĐỊNH: VÀO LỆNH LONG"
    elif signal == -1:
        decision = "QUYẾT ĐỊNH: VÀO LỆNH SHORT"
        
    threshold = config_dict.get('ENTRY_SCORE_THRESHOLD', 70.0)
    print(f"{decision} (Điểm cao nhất: {max(final_long, final_short):.1f}, Ngưỡng: {threshold})")
    print("="*60)


def run_backtest():
    print("--- Bắt đầu chạy Backtest (v6.0 - Phòng Thí Nghiệm) ---")
    if SHOW_DETAILED_LOG:
        print("Chế độ log chi tiết: BẬT")
    else:
        print("Chế độ log chi tiết: TẮT")
        
    # 1. Tải và chuẩn bị dữ liệu
    try:
        df = pd.read_csv(DATA_FILE_PATH, index_col='timestamp', parse_dates=True)
        df.rename(columns={'tick_volume': 'volume'}, inplace=True, errors='ignore')
    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file dữ liệu tại: {DATA_FILE_PATH}")
        return
    print(f"Đã tải {len(df)} nến gốc.")

    # 2. Thiết lập "luật chơi"
    balance = INITIAL_CAPITAL
    equity_curve = [INITIAL_CAPITAL]
    active_trades: List[Dict[str, Any]] = []
    trade_history: List[Dict[str, Any]] = []
    cooldown_until_index = 0

    print(f"Bắt đầu giả lập trên {len(df)} nến...")

    # 3. Vòng lặp Giả lập
    for i in range(CANDLE_FETCH_COUNT, len(df)):
        
        historical_df_slice = df.iloc[i - CANDLE_FETCH_COUNT : i]
        current_candle = df.iloc[i]
        
        # --- A. QUẢN LÝ LỆNH MỞ (TP1, PP, TSL...) ---
        trade_management_config = config_dict.get('ACTIVE_TRADE_MANAGEMENT', {})
        for trade in active_trades[:]:
            pnl = 0.0
            is_long = trade['type'] == 'LONG'
            
            current_price = current_candle['open']
            price_change = (current_price - trade['entry_price']) if is_long else (trade['entry_price'] - current_price)
            pnl_usd = price_change * trade['lot_size'] * CONTRACT_SIZE
            pnl_r = pnl_usd / trade['initial_risk_usd'] if trade['initial_risk_usd'] > 0 else 0.0
            
            trade['peak_pnl_r'] = max(trade.get('peak_pnl_r', 0.0), pnl_r)

            if trade_management_config.get("ENABLE_TP1") and not trade.get("tp1_hit") and pnl_r >= trade_management_config.get("TP1_RR_RATIO", 1.0):
                trade['tp1_hit'] = True
                if trade_management_config.get("TP1_MOVE_SL_TO_ENTRY", True):
                    trade['sl_price'] = trade['entry_price']

            if (trade_management_config.get("ENABLE_PROTECT_PROFIT") and
                not trade.get("pp_triggered") and not trade.get("tp1_hit") and
                trade['peak_pnl_r'] >= trade_management_config.get("PP_MIN_PEAK_R_TRIGGER", 1.2) and
                (trade['peak_pnl_r'] - pnl_r) >= trade_management_config.get("PP_DROP_R_TRIGGER", 0.4)):
                trade['pp_triggered'] = True
                if trade_management_config.get("PP_MOVE_SL_TO_ENTRY", True):
                    trade['sl_price'] = trade['entry_price']
            
            if trade_management_config.get("ENABLE_TSL"):
                atr_series = historical_df_slice['high'] - historical_df_slice['low']
                current_atr = atr_series.mean() 
                trail_distance = current_atr * trade_management_config.get('TSL_ATR_MULTIPLIER', 2.5)
                
                if is_long:
                    new_potential_sl = current_price - trail_distance
                    if new_potential_sl > trade['sl_price']:
                        trade['sl_price'] = new_potential_sl
                else: # SHORT
                    new_potential_sl = current_price + trail_distance
                    if new_potential_sl < trade['sl_price']:
                        trade['sl_price'] = new_potential_sl
            
            trade_closed = False
            close_price = 0.0

            if is_long:
                if current_candle['low'] <= trade['sl_price']:
                    trade_closed = True; close_price = trade['sl_price']
                elif current_candle['high'] >= trade['tp_price']:
                    trade_closed = True; close_price = trade['tp_price']
            else: # SHORT
                if current_candle['high'] >= trade['sl_price']:
                    trade_closed = True; close_price = trade['sl_price']
                elif current_candle['low'] <= trade['tp_price']:
                    trade_closed = True; close_price = trade['tp_price']

            if trade_closed:
                price_change = (close_price - trade['entry_price']) if is_long else (trade['entry_price'] - close_price)
                pnl = price_change * trade['lot_size'] * CONTRACT_SIZE
                balance += pnl
                equity_curve.append(balance)
                
                trade['close_time'] = current_candle.name
                trade['pnl'] = pnl
                trade_history.append(trade)
                active_trades.remove(trade)
                cooldown_until_index = i + config_dict.get('COOLDOWN_CANDLES', 0)

        # --- B. TÌM TÍN HIỆU MỚI ---
        can_open_trade = (i >= cooldown_until_index) and (len(active_trades) < config.MAX_ACTIVE_TRADES)
        
        if can_open_trade:
            signal, score_details = get_final_signal(historical_df_slice, config_dict)
            
            # Chỉ in log nếu có một trong hai phe có điểm thô > 0 để tránh làm loãng
            if SHOW_DETAILED_LOG and (score_details.get("raw", {}).get("long_total", 0) > 0 or score_details.get("raw", {}).get("short_total", 0) > 0):
                print_score_details(current_candle.name, score_details)

            if signal != 0:
                entry_price = current_candle['open']
                trade_details = calculate_trade_details(
                    historical_df_slice, entry_price, signal, balance, config_dict
                )
                
                if trade_details:
                    lot_size, sl_price, tp_price = trade_details
                    initial_risk = abs(entry_price - sl_price) * lot_size * CONTRACT_SIZE
                    
                    if lot_size > 0 and balance > initial_risk:
                        new_trade = {
                            "entry_time": current_candle.name,
                            "entry_price": entry_price,
                            "type": "LONG" if signal == 1 else "SHORT",
                            "lot_size": lot_size,
                            "sl_price": sl_price,
                            "tp_price": tp_price,
                            "initial_risk_usd": initial_risk,
                            "score": score_details.get("final", {}).get("decision_score", 0.0),
                            "tp1_hit": False,
                            "pp_triggered": False,
                            "peak_pnl_r": 0.0
                        }
                        active_trades.append(new_trade)
                        print(f"[{current_candle.name}] >>> LỆNH {new_trade['type']} ĐƯỢC THỰC THI VỚI ĐIỂM {new_trade['score']:.1f} <<<")

    # 4. Đóng tất cả các lệnh còn lại vào cuối kỳ
    if active_trades:
        last_price = df.iloc[-1]['close']
        for trade in active_trades:
            price_change = (last_price - trade['entry_price']) if trade['type'] == 'LONG' else (trade['entry_price'] - last_price)
            pnl = price_change * trade['lot_size'] * CONTRACT_SIZE
            balance += pnl
            equity_curve.append(balance)
            trade['close_time'] = df.index[-1]
            trade['pnl'] = pnl
            trade_history.append(trade)

    # 5. In Báo Cáo Kết Quả Nâng Cao
    print("\n--- KẾT QUẢ BACKTEST (v6.0) ---")
    print(f"Dữ liệu: {DATA_FILE_PATH} | Khung thời gian: {config.TIMEFRAME}")
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


if __name__ == "__main__":
    run_backtest()