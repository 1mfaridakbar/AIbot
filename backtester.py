# file: backtester.py

import pandas as pd
import pandas_ta as ta
from database import DatabaseManager
import config

# --- KELAS UNTUK MENGELOLA SIMULASI ---
class TradeSimulator:
    def __init__(self, initial_balance_idr):
        self.balance_idr = initial_balance_idr
        self.balance_crypto = 0.0
        self.open_position = None
        self.trades = []
        self.equity_history = []

    def buy(self, price, timestamp):
        if self.balance_idr > 0:
            amount_to_buy_crypto = self.balance_idr / price
            self.balance_crypto = amount_to_buy_crypto
            self.open_position = {'price': price, 'amount': amount_to_buy_crypto}
            self.balance_idr = 0
            self.trades.append({'type': 'BUY', 'price': price, 'timestamp': timestamp, 'profit': 0})
            print(f"{timestamp} - EXECUTED BUY @ {price:,.0f}")

    def sell(self, price, timestamp):
        if self.open_position:
            profit = (price - self.open_position['price']) * self.open_position['amount']
            self.balance_idr = self.balance_crypto * price
            self.balance_crypto = 0
            self.open_position = None
            self.trades.append({'type': 'SELL', 'price': price, 'timestamp': timestamp, 'profit': profit})
            print(f"{timestamp} - EXECUTED SELL @ {price:,.0f} | Profit: {profit:,.2f}")

    def update_equity(self, current_price):
        """Mencatat nilai total aset di setiap langkah."""
        total_equity = self.balance_idr
        if self.open_position:
            total_equity += self.balance_crypto * current_price
        self.equity_history.append(total_equity)


# --- FUNGSI UTAMA UNTUK MENJALANKAN BACKTEST ---
def run_backtest():
    print("--- Starting Backtest ---")
    db = DatabaseManager()
    
    # 1. Muat SEMUA data historis dari database
    # Ganti limit=1000 dengan jumlah data yang lebih besar jika Anda punya
    all_data_rows = db.get_ohlcv_data(config.PAIR_TO_TRADE, limit=1000) 
    if len(all_data_rows) < config.LONG_MA_WINDOW + 2:
        print("Not enough historical data to run backtest.")
        return

    df = pd.DataFrame([dict(row) for row in all_data_rows])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.set_index('timestamp')

    # 2. Hitung semua indikator sekaligus
    df.ta.sma(length=config.SHORT_MA_WINDOW, append=True)
    df.ta.sma(length=config.LONG_MA_WINDOW, append=True)
    df.ta.rsi(length=14, append=True)
    df.dropna(inplace=True) # Hapus baris yang tidak punya nilai indikator (awal data)
    
    # Ganti nama kolom agar sesuai dengan kode bot_logic
    df.rename(columns={
        f'SMA_{config.SHORT_MA_WINDOW}': 'SMA_Short',
        f'SMA_{config.LONG_MA_WINDOW}': 'SMA_Long',
        'RSI_14': 'RSI'
    }, inplace=True)
    
    # 3. Inisialisasi simulator
    simulator = TradeSimulator(initial_balance_idr=10_000_000) # Modal awal 10 Juta IDR
    
    # 4. Loop melalui setiap candle di data historis
    for i in range(1, len(df)): # Mulai dari 1 untuk bisa membandingkan dengan 'i-1'
        current_row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        # Simulasikan pengecekan setiap candle
        simulator.update_equity(current_row['close'])

        # --- Logika Keputusan (diadaptasi dari bot_logic.py) ---
        
        # Cek Take-Profit / Stop-Loss dulu (jika ada posisi terbuka)
        if simulator.open_position:
            buy_price = simulator.open_position['price']
            take_profit_price = buy_price * (1 + config.TAKE_PROFIT_PERCENTAGE / 100)
            stop_loss_price = buy_price * (1 - config.STOP_LOSS_PERCENTAGE / 100)
            
            if current_row['close'] >= take_profit_price:
                simulator.sell(current_row['close'], current_row.name)
                continue
            if current_row['close'] <= stop_loss_price:
                simulator.sell(current_row['close'], current_row.name)
                continue

        # Jika tidak ada trigger SL/TP, cek strategi utama
        is_golden_cross = prev_row['SMA_Short'] <= prev_row['SMA_Long'] and current_row['SMA_Short'] > current_row['SMA_Long']
        is_death_cross = prev_row['SMA_Short'] >= prev_row['SMA_Long'] and current_row['SMA_Short'] < current_row['SMA_Long']
        
        # Kondisi Beli
        if is_golden_cross and current_row['RSI'] < 70 and not simulator.open_position:
            simulator.buy(current_row['close'], current_row.name)
        
        # Kondisi Jual
        elif is_death_cross and current_row['RSI'] > 30 and simulator.open_position:
            simulator.sell(current_row['close'], current_row.name)

    # 5. Cetak Laporan Performa
    print("\n--- Backtest Finished: Performance Report ---")
    
    if not simulator.trades:
        print("No trades were executed.")
        return
        
    final_balance = simulator.equity_history[-1]
    total_profit = final_balance - 10_000_000
    
    sell_trades = [t for t in simulator.trades if t['type'] == 'SELL']
    wins = [t for t in sell_trades if t['profit'] > 0]
    losses = [t for t in sell_trades if t['profit'] <= 0]
    
    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0
    total_profit_from_wins = sum(t['profit'] for t in wins)
    total_loss_from_losses = abs(sum(t['profit'] for t in losses))
    profit_factor = total_profit_from_wins / total_loss_from_losses if total_loss_from_losses > 0 else float('inf')
    
    # Hitung Max Drawdown
    equity_series = pd.Series(simulator.equity_history)
    rolling_max = equity_series.cummax()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = abs(drawdown.min() * 100)

    print(f"Period Tested: {df.index.min()} to {df.index.max()}")
    print(f"Initial Balance: {10_000_000:,.2f} IDR")
    print(f"Final Balance:   {final_balance:,.2f} IDR")
    print(f"Total Profit/Loss: {total_profit:,.2f} IDR ({total_profit/10_000_000:.2%})")
    print("-" * 20)
    print(f"Total Trades: {len(sell_trades)}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Max Drawdown: {max_drawdown:.2f}%")

if __name__ == "__main__":
    run_backtest()