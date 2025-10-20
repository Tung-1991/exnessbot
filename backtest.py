# -*- coding: utf-8 -*-
# backtest.py (v4 - Fix lỗi Supertrend/ATR, Dùng Logic % Mới)

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
import config  # Import "bộ não" config của chúng ta

# Import các hàm tính toán chỉ báo GỐC
# (Vì ta tính 1 lần duy nhất, nên gọi hàm gốc là đúng)
from signals.bollinger_bands import calculate_bollinger_bands, get_bb_signal
from signals.rsi import calculate_rsi, get_rsi_score
from signals.macd import calculate_macd, get_macd_score
from signals.supertrend import calculate_supertrend, get_supertrend_score
from signals.ema import calculate_emas, get_ema_score
from signals.volume import get_volume_score # Hàm này đặc biệt, tính và chấm điểm luôn
from signals.atr import calculate_atr

# Import hàm quản lý rủi ro GỐC (đã sửa logic %)
from core.risk_manager import calculate_trade_details

# --- CẤU HÌNH BACKTEST ---
INITIAL_CAPITAL = 1000.0
DATA_FILE_PATH = "data/ETHUSD_15m_6M.csv" # File dữ liệu 6 tháng
CONTRACT_SIZE = 1.0 # (FIXED) 1 Lot = 1 ETH
CANDLE_FETCH_COUNT = config.CANDLE_FETCH_COUNT # = 300

# Lấy config dictionary (quan trọng)
config_dict = config.__dict__

def precalculate_indicators(df, cfg):
    """
    Tính toán TẤT CẢ các chỉ báo trên toàn bộ DataFrame một lần duy nhất.
    """
    print("Đang tính toán các chỉ báo cho 6 tháng...")
    
    # Lấy configs
    bb_cfg = cfg['INDICATORS_CONFIG']['BB']
    rsi_cfg = cfg['INDICATORS_CONFIG']['RSI']
    macd_cfg = cfg['INDICATORS_CONFIG']['MACD']
    st_cfg = cfg['INDICATORS_CONFIG']['SUPERTREND']
    ema_cfg = cfg['INDICATORS_CONFIG']['EMA']
    vol_cfg = cfg['INDICATORS_CONFIG']['VOLUME']
    atr_cfg = cfg['INDICATORS_CONFIG']['ATR'] # Thêm ATR config

    # Tính BB
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(df, bb_cfg['PERIOD'], bb_cfg['STD_DEV'])
    
    # Tính RSI
    df['rsi'] = calculate_rsi(df, rsi_cfg['PERIOD'])
    
    # Tính MACD
    df['macd_line'], df['signal_line'] = calculate_macd(df, macd_cfg['FAST_EMA'], macd_cfg['SLOW_EMA'], macd_cfg['SIGNAL_SMA'])
    
    # Tính Supertrend
    df['supertrend'] = calculate_supertrend(df, st_cfg['ATR_PERIOD'], st_cfg['MULTIPLIER'])
    
    # Tính EMAs
    df['slow_ema'], df['fast_ema'] = calculate_emas(df, cfg) # Hàm này cần cả dict config
    
    # Tính Volume MA (cho hàm get_volume_score)
    df['volume_ma'] = df['volume'].rolling(window=vol_cfg['MA_PERIOD']).mean()
    
    # Tính ATR (cho risk_manager)
    df['atr'] = calculate_atr(df, atr_cfg['PERIOD'])
    
    print("✅ Tính toán chỉ báo hoàn tất.")
    # Xóa các hàng đầu tiên có NaN (quan trọng!)
    # Tìm index đầu tiên mà TẤT CẢ các cột chỉ báo cần thiết không còn NaN
    required_cols = ['bb_upper', 'rsi', 'macd_line', 'signal_line', 'supertrend', 'slow_ema', 'volume_ma', 'atr']
    first_valid_index = df[required_cols].first_valid_index()
    if first_valid_index is not None:
        df = df.loc[first_valid_index:]
        print(f"Đã xóa các hàng NaN, còn lại {len(df)} nến.")
    else:
        print("LỖI: Không tìm thấy dữ liệu hợp lệ sau khi tính chỉ báo.")
        return pd.DataFrame() # Trả về DataFrame rỗng nếu lỗi

    return df

def get_final_signal_backtest(df_slice: pd.DataFrame, config: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
    """
    Hàm tính điểm tổng hợp CHO BACKTEST.
    Nó KHÔNG tính lại chỉ báo, mà lấy giá trị đã tính sẵn từ df_slice.
    """
    score_details = {}
    weights = config['SCORING_WEIGHTS']
    penalties = config['PENALTY_WEIGHTS']
    indicators_cfg = config['INDICATORS_CONFIG']

    # --- LẤY GIÁ TRỊ ĐÃ TÍNH SẴN TỪ NẾN CUỐI CÙNG CỦA SLICE ---
    last_candle = df_slice.iloc[-1]
    
    # 1. Bollinger Bands Score
    bb_raw_signal = 0
    if last_candle['close'] > last_candle['bb_upper']:
        bb_raw_signal = -1
    elif last_candle['close'] < last_candle['bb_lower']:
        bb_raw_signal = 1
    score_details['bb_score'] = bb_raw_signal * weights['BB_TRIGGER_SCORE']

    # 2. RSI Score
    rsi_score = 0
    rsi_cfg = indicators_cfg['RSI']
    if last_candle['rsi'] < rsi_cfg['OVERSOLD']:
        rsi_score = weights['RSI_EXTREME_SCORE']
    elif last_candle['rsi'] > rsi_cfg['OVERBOUGHT']:
        rsi_score = -weights['RSI_EXTREME_SCORE']
    score_details['rsi_score'] = rsi_score

    # 3. MACD Score (Cần 2 nến cuối)
    macd_score = 0
    if len(df_slice) >= 2:
        prev_candle = df_slice.iloc[-2]
        # Bullish Crossover
        if prev_candle['macd_line'] < prev_candle['signal_line'] and last_candle['macd_line'] > last_candle['signal_line']:
            macd_score = weights['MACD_CROSS_SCORE']
        # Bearish Crossover
        elif prev_candle['macd_line'] > prev_candle['signal_line'] and last_candle['macd_line'] < last_candle['signal_line']:
            macd_score = -weights['MACD_CROSS_SCORE']
    score_details['macd_score'] = macd_score

    # 4. Supertrend Score
    st_score = 0
    if last_candle['close'] > last_candle['supertrend']:
        st_score = weights['SUPERTREND_ALIGN_SCORE']
    elif last_candle['close'] < last_candle['supertrend']:
        st_score = -weights['SUPERTREND_ALIGN_SCORE']
    score_details['supertrend_score'] = st_score

    # --- TÍNH TỔNG SƠ BỘ VÀ XÁC ĐỊNH HƯỚNG ---
    preliminary_total_score = sum(v for k, v in score_details.items() if '_penalty' not in k) # Chỉ cộng điểm gốc
    
    signal_direction = 0
    if preliminary_total_score > 0:
        signal_direction = 1
    elif preliminary_total_score < 0:
        signal_direction = -1

    # --- ÁP DỤNG ĐIỂM PHẠT ---
    
    # 5. EMA Penalty
    ema_penalty = 0
    is_long_term_uptrend = last_candle['close'] > last_candle['slow_ema']
    if signal_direction == 1 and not is_long_term_uptrend:
        ema_penalty = -penalties['COUNTER_EMA_TREND_PENALTY']
    elif signal_direction == -1 and is_long_term_uptrend:
        ema_penalty = -penalties['COUNTER_EMA_TREND_PENALTY']
    score_details['ema_penalty'] = ema_penalty

    # 6. Volume Penalty (Dùng hàm gốc vì nó phức tạp hơn chút)
    # Hàm get_volume_score cần df có cột 'volume' và 'volume_ma'
    score_details['volume_penalty'] = get_volume_score(df_slice, config) # Truyền slice đủ 300 nến

    # --- TÍNH TỔNG CUỐI CÙNG VÀ RA QUYẾT ĐỊNH ---
    final_score = sum(score_details.values())
    score_details['final_score'] = final_score
    
    final_signal = 0
    entry_threshold = config['ENTRY_SCORE_THRESHOLD']
    allow_long = config.get('ENABLE_LONG_TRADES', True)
    allow_short = config.get('ENABLE_SHORT_TRADES', True)
    
    if final_score >= entry_threshold and allow_long:
        final_signal = 1
    elif final_score <= -entry_threshold and allow_short:
        final_signal = -1
        
    return final_signal, score_details


def run_backtest():
    print("--- Bắt đầu chạy Backtest (v4 - Fix Supertrend/ATR, Logic % Mới) ---")
    
    # 1. Tải và chuẩn bị dữ liệu
    try:
        df = pd.read_csv(DATA_FILE_PATH, index_col='timestamp', parse_dates=True)
        # Đổi tên cột nếu cần (tùy file CSV)
        df.rename(columns={'tick_volume': 'volume'}, inplace=True, errors='ignore')
    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file dữ liệu tại: {DATA_FILE_PATH}")
        return
    except Exception as e:
        print(f"LỖI khi đọc file CSV: {e}")
        return

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']):
        print(f"LỖI: File CSV thiếu cột OHLCV. Các cột hiện có: {df.columns.tolist()}")
        return
        
    print(f"Đã tải {len(df)} nến gốc.")
    
    # 2. TÍNH TOÁN TRƯỚC TOÀN BỘ CHỈ BÁO
    df_with_indicators = precalculate_indicators(df.copy(), config_dict) # Dùng copy để giữ df gốc
    
    if df_with_indicators.empty:
        return # Lỗi đã được in ra trong hàm precalculate
        
    print(f"Bắt đầu giả lập trên {len(df_with_indicators)} nến.")

    # 3. Thiết lập "luật chơi"
    balance = INITIAL_CAPITAL
    active_trades = []
    trade_history = []
    cooldown_until_index = 0

    # 4. Vòng lặp Giả lập
    # Lặp qua DataFrame đã có sẵn chỉ báo
    for i in range(CANDLE_FETCH_COUNT, len(df_with_indicators)): # Bắt đầu đủ sâu để slice 300 nến đầu tiên có ý nghĩa
        
        # Slice dữ liệu lịch sử (ĐÃ CÓ CHỈ BÁO) cho hàm tính điểm
        historical_df_slice = df_with_indicators.iloc[i - CANDLE_FETCH_COUNT : i]
        
        # Nến hiện tại (để check SL/TP và lấy giá vào lệnh)
        current_candle = df_with_indicators.iloc[i]
        
        # --- A. QUẢN LÝ LỆNH MỞ (Check SL/TP v1 - Chưa có TSL, PP, TP1) ---
        for trade_index in range(len(active_trades) - 1, -1, -1):
            trade = active_trades[trade_index]
            trade_closed = False
            pnl = 0.0
            risk_per_lot_unit = trade['lot_size'] * CONTRACT_SIZE # = lot_size * 1
            
            if trade['type'] == 'LONG':
                if current_candle['low'] <= trade['sl_price']:
                    trade_closed = True
                    pnl = (trade['sl_price'] - trade['entry_price']) * risk_per_lot_unit
                elif current_candle['high'] >= trade['tp_price']:
                    trade_closed = True
                    pnl = (trade['tp_price'] - trade['entry_price']) * risk_per_lot_unit
            elif trade['type'] == 'SHORT':
                if current_candle['high'] >= trade['sl_price']:
                    trade_closed = True
                    pnl = (trade['entry_price'] - trade['sl_price']) * risk_per_lot_unit
                elif current_candle['low'] <= trade['tp_price']:
                    trade_closed = True
                    pnl = (trade['entry_price'] - trade['tp_price']) * risk_per_lot_unit

            if trade_closed:
                balance += pnl
                trade['close_time'] = current_candle.name # Timestamp của nến đóng lệnh
                trade['pnl'] = pnl
                trade_history.append(trade)
                active_trades.pop(trade_index)
                cooldown_until_index = i + config_dict.get('COOLDOWN_CANDLES', 0)

        # --- B. TÌM TÍN HIỆU MỚI ---
        can_open_trade = (i >= cooldown_until_index) and (len(active_trades) < config.MAX_ACTIVE_TRADES)
        
        if can_open_trade:
            # 1. Gọi "bộ não" backtest (dùng giá trị đã tính sẵn)
            signal, score_details = get_final_signal_backtest(historical_df_slice, config_dict)
            
            if signal != 0:
                # 2. Gọi "quản lý rủi ro" GỐC (đã fix logic %)
                entry_price = current_candle['open'] # Giả định vào lệnh tại giá Mở Cửa
                
                # Hàm này cần slice có cột 'atr' đã tính sẵn
                trade_details = calculate_trade_details(
                    historical_df_slice, # Phải có cột 'atr'
                    entry_price, 
                    signal, 
                    balance, 
                    config_dict
                )
                
                # 3. Mở lệnh "ảo"
                if trade_details: # Hàm trả về (lot_size, sl_price, tp_price)
                    lot_size, sl_price, tp_price = trade_details
                    
                    # Kiểm tra lại lot size > 0 (quan trọng)
                    if lot_size <= 0: continue 
                    
                    new_trade = {
                        "entry_time": current_candle.name, # Timestamp của nến vào lệnh
                        "entry_price": entry_price,
                        "type": "LONG" if signal == 1 else "SHORT",
                        "lot_size": lot_size,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "score": score_details.get('final_score', 0.0)
                    }
                    active_trades.append(new_trade)

    # 4. Đóng tất cả các lệnh còn lại vào cuối kỳ
    last_candle = df_with_indicators.iloc[-1]
    last_price = last_candle['close']
    for trade in active_trades:
        risk_per_lot_unit = trade['lot_size'] * CONTRACT_SIZE
        pnl = 0.0
        if trade['type'] == 'LONG':
            pnl = (last_price - trade['entry_price']) * risk_per_lot_unit
        else:
            pnl = (trade['entry_price'] - last_price) * risk_per_lot_unit
        balance += pnl
        trade['close_time'] = last_candle.name
        trade['pnl'] = pnl
        trade_history.append(trade)

    # 5. In Báo Cáo Kết Quả
    print("\n--- KẾT QUẢ BACKTEST (v4 - Đã sửa lỗi) ---")
    print(f"Dữ liệu: {DATA_FILE_PATH}")
    print(f"Khung thời gian: {config.TIMEFRAME} | Kích thước HĐ: {CONTRACT_SIZE} ETH / 1 Lot")
    print("---------------------------------")
    print(f"Vốn ban đầu:    ${INITIAL_CAPITAL:,.2f}")
    print(f"Số dư cuối kỳ:   ${balance:,.2f}")
    
    total_pnl = balance - INITIAL_CAPITAL
    print(f"Tổng Lợi nhuận/Lỗ: ${total_pnl:,.2f} ({total_pnl/INITIAL_CAPITAL*100:,.2f}%)")
    
    if len(trade_history) == 0:
        print("Không có lệnh nào được thực hiện.")
        return

    total_trades = len(trade_history)
    wins = [t for t in trade_history if t['pnl'] > 0]
    losses = [t for t in trade_history if t['pnl'] <= 0]
    
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    
    print(f"Tổng số lệnh:   {total_trades}")
    print(f"Số lệnh thắng:  {len(wins)}")
    print(f"Số lệnh thua:   {len(losses)}")
    print(f"Tỷ lệ thắng:     {win_rate:,.2f}%")
    
    avg_win = sum(t['pnl'] for t in wins) / len(wins) if len(wins) > 0 else 0
    avg_loss = abs(sum(t['pnl'] for t in losses) / len(losses)) if len(losses) > 0 else 0
    print(f"Trung bình Thắng: ${avg_win:,.2f}")
    print(f"Trung bình Thua:  ${avg_loss:,.2f}")
    
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    print(f"Tỷ lệ R:R (TB):  {rr_ratio:,.2f}:1") # Tính R:R trung bình
    
    # Tính toán Max Drawdown
    equity_curve = pd.Series([INITIAL_CAPITAL] + np.cumsum([t['pnl'] for t in trade_history]).tolist())
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    max_drawdown = drawdown.min() * 100
    
    print(f"Sụt giảm tối đa: {max_drawdown:,.2f}%")

if __name__ == "__main__":
    run_backtest()