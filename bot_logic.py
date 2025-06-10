import time
import os
import pandas as pd
from datetime import datetime, timedelta # Tambahkan import timedelta
from indodax_api import IndodaxAPI
from database import DatabaseManager # Import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

class TradingBot:
    def __init__(self, api_key, secret_key, pair="btcidr", trade_amount_idr=100000, ohlcv_interval_seconds=300):
        self.indodax = IndodaxAPI(api_key, secret_key)
        self.db_manager = DatabaseManager()
        self.pair = pair
        self.trade_amount_idr = trade_amount_idr
        self.ohlcv_interval_seconds = ohlcv_interval_seconds
        self.last_trade_type = None
        self.open_positions = {}

        self.short_ma_window = 10
        self.long_ma_window = 30
        
    def _get_current_prices(self):
        ticker = self.indodax.get_ticker(self.pair)
        if ticker and ticker['ticker']:
            return float(ticker['ticker']['last']), float(ticker['ticker']['buy']), float(ticker['ticker']['sell'])
        return None, None, None

    def _get_balance(self, asset_code):
        info = self.indodax.get_info()
        if info and info['success'] == 1:
            return float(info['return']['balance'].get(asset_code, 0))
        return 0

    def get_ohlcv_from_db(self, limit=None):
        """
        Mengambil data OHLCV nyata dari database.
        Memastikan nama kolom yang benar untuk Pandas DataFrame.
        """
        needed_candles = self.long_ma_window + 5
        ohlcv_rows = self.db_manager.get_ohlcv_data(self.pair, limit=needed_candles)
        
        if not ohlcv_rows:
            return pd.DataFrame() # Return empty DataFrame if no data
        
        # --- PERUBAHAN UTAMA DI SINI ---
        # Konversi sqlite3.Row objek menjadi dictionary yang eksplisit
        # Ini akan memastikan Pandas membuat DataFrame dengan nama kolom yang benar
        data_for_df = []
        for row in ohlcv_rows:
            data_for_df.append({
                'id': row['id'],
                'pair': row['pair'],
                'timestamp': row['timestamp'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            })

        df = pd.DataFrame(data_for_df)
        # --- AKHIR PERUBAHAN UTAMA ---

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.set_index('timestamp').sort_index()
        
        return df[['open', 'high', 'low', 'close', 'volume']]

    # ... (sisa kode class TradingBot sama) ...

    def calculate_moving_averages(self, df):
        """Menghitung Simple Moving Averages dari DataFrame OHLCV."""
        # ... (fungsi ini sama) ...
        if df.empty or len(df) < max(self.short_ma_window, self.long_ma_window):
            return None, None # Not enough data
        
        df['SMA_Short'] = df['close'].rolling(window=self.short_ma_window).mean()
        df['SMA_Long'] = df['close'].rolling(window=self.long_ma_window).mean()
        
        # Return latest SMA values
        return df['SMA_Short'].iloc[-1], df['SMA_Long'].iloc[-1]
    
    def make_trading_decision(self):
        """Membuat keputusan trading berdasarkan MA Crossover."""
        ohlcv_df = self.get_ohlcv_from_db()
        
        # Periksa apakah ada cukup data untuk menghitung MA
        # Pastikan ada setidaknya (long_ma_window + 1) baris untuk menghitung MA dan prev_MA
        if ohlcv_df.empty or len(ohlcv_df) < self.long_ma_window + 1: # Diubah dari +5 ke +1 karena sudah ada filter di bawah
            print("Not enough OHLCV data from DB to make a decision. Waiting for more data...")
            return "HOLD"
            
        # Panggil calculate_moving_averages setelah memastikan DataFrame tidak kosong
        sma_short, sma_long = self.calculate_moving_averages(ohlcv_df)

        if sma_short is None or sma_long is None:
            print("Not enough data to calculate moving averages (SMAs are None). Holding.")
            return "HOLD"

        current_close_price = ohlcv_df['close'].iloc[-1]
        
        print(f"Current Close Price: {current_close_price:,.0f}, SMA Short ({self.short_ma_window}): {sma_short:,.0f}, SMA Long ({self.long_ma_window}): {sma_long:,.0f}")

        # Dapatkan nilai SMA dari periode sebelumnya untuk mendeteksi crossover
        # Pastikan ada cukup data untuk iloc[-2] (yaitu setidaknya 2 baris setelah perhitungan MA)
        if len(ohlcv_df) >= self.long_ma_window + 2: # Harus ada 2 candlestick setelah MA bisa dihitung
            # Pastikan kolom SMA sudah ada di DataFrame sebelum mencoba mengaksesnya
            if 'SMA_Short' not in ohlcv_df.columns or 'SMA_Long' not in ohlcv_df.columns:
                # Jika belum, hitung ulang untuk mendapatkan kolom SMA
                temp_df_with_sma = ohlcv_df.copy()
                temp_df_with_sma['SMA_Short'] = temp_df_with_sma['close'].rolling(window=self.short_ma_window).mean()
                temp_df_with_sma['SMA_Long'] = temp_df_with_sma['close'].rolling(window=self.long_ma_window).mean()
                prev_sma_short = temp_df_with_sma['SMA_Short'].iloc[-2]
                prev_sma_long = temp_df_with_sma['SMA_Long'].iloc[-2]
            else:
                prev_sma_short = ohlcv_df['SMA_Short'].iloc[-2]
                prev_sma_long = ohlcv_df['SMA_Long'].iloc[-2]
        else:
            prev_sma_short = sma_short # Jika tidak ada data sebelumnya yang cukup, anggap sama (tidak ada crossover yang jelas)
            prev_sma_long = sma_long

        # ... (sisa fungsi make_trading_decision() sama) ...
        # MA Crossover Strategy
        # Beli jika SMA pendek melintasi SMA panjang dari bawah ke atas (Golden Cross)
        if sma_short > sma_long and prev_sma_short <= prev_sma_long and self.last_trade_type != "BUY":
            # Periksa apakah ada posisi terbuka untuk pasangan ini
            if self.pair not in self.open_positions or len(self.open_positions[self.pair]) == 0:
                print("SMA Short crossed above SMA Long: BUY Signal (Golden Cross)")
                return "BUY"
            else:
                print("BUY Signal detected, but already holding an open position. Holding.")
                return "HOLD"
        
        # Jual jika SMA pendek melintasi SMA panjang dari atas ke bawah (Death Cross)
        elif sma_short < sma_long and prev_sma_short >= prev_sma_long and self.last_trade_type != "SELL":
            # Hanya jual jika ada posisi terbuka
            if self.pair in self.open_positions and len(self.open_positions[self.pair]) > 0:
                print("SMA Short crossed below SMA Long: SELL Signal (Death Cross)")
                return "SELL"
            else:
                print("SELL Signal detected, but no open position to sell. Holding.")
                return "HOLD"
        else:
            return "HOLD"

    def execute_trade(self, action):
        """Mengeksekusi perdagangan dan mencatatnya ke database."""
        current_price, buy_price, sell_price = self._get_current_prices()
        if current_price is None:
            print("Could not get current price for trade execution. Holding.")
            return

        if action == "BUY":
            idr_balance = self._get_balance("idr")
            if idr_balance >= self.trade_amount_idr:
                print(f"Attempting to BUY {self.trade_amount_idr} IDR worth of {self.pair.upper()} at approx. {current_price:,.0f} IDR...")
                
                # Gunakan limit order atau market order sesuai preferensi Anda.
                # Untuk simplicity, tetap gunakan amount untuk market buy Indodax (jumlah IDR)
                buy_order_result = self.indodax.trade(pair=self.pair, type="buy", amount=self.trade_amount_idr)
                
                if buy_order_result and buy_order_result['success'] == 1:
                    order_id = buy_order_result['return'].get('order_id')
                    received_amount = buy_order_result['return'].get('receive_amount', 0) # Amount of crypto received (approx)
                    
                    # Catat pembelian ke database
                    self.db_manager.insert_trade_history(
                        pair=self.pair,
                        trade_type="buy",
                        price=current_price, # Gunakan harga pasar saat ini atau harga eksekusi jika API memberikan
                        amount=received_amount, # Ini akan menjadi jumlah kripto yang benar-benar Anda dapatkan
                        quote_amount=self.trade_amount_idr, # Jumlah IDR yang digunakan
                        timestamp=int(time.time()),
                        order_id=order_id,
                        status="filled", # Asumsi filled untuk market order
                        notes="Bot auto-buy"
                    )
                    print(f"BUY order placed! ID: {order_id}. Received: {received_amount} {self.pair.split('idr')[0].upper()}")
                    self.last_trade_type = "BUY"
                    
                    # Tambahkan ke posisi terbuka
                    if self.pair not in self.open_positions:
                        self.open_positions[self.pair] = []
                    self.open_positions[self.pair].append({
                        'buy_price': current_price,
                        'buy_amount_crypto': received_amount,
                        'buy_timestamp': int(time.time()),
                        'buy_order_id': order_id,
                        'buy_quote_amount_idr': self.trade_amount_idr
                    })
                else:
                    print(f"Failed to place BUY order: {buy_order_result.get('error', 'Unknown error')}")
            else:
                print(f"Insufficient IDR balance ({idr_balance:,.2f}) to buy {self.trade_amount_idr:,.2f} IDR worth of {self.pair.upper()}. Holding.")
        
        elif action == "SELL":
            asset_code = self.pair.replace('idr', '')
            crypto_balance = self._get_balance(asset_code)
            
            if self.pair in self.open_positions and self.open_positions[self.pair]:
                # Ambil posisi buy tertua atau yang paling relevan (sesuai strategi Anda)
                # Untuk kesederhanaan, kita jual seluruh posisi yang ada
                position_to_sell = self.open_positions[self.pair].pop(0) # Ambil posisi buy pertama
                
                # Pastikan jumlah kripto yang kita jual sesuai dengan yang kita beli
                amount_to_sell_crypto = position_to_sell['buy_amount_crypto']
                
                if crypto_balance >= amount_to_sell_crypto and amount_to_sell_crypto > 0:
                    print(f"Attempting to SELL {amount_to_sell_crypto:.8f} {asset_code.upper()} at approx. {current_price:,.0f} IDR...")
                    
                    sell_order_result = self.indodax.trade(pair=self.pair, type="sell", amount=amount_to_sell_crypto) # Amount is crypto amount
                    
                    if sell_order_result and sell_order_result['success'] == 1:
                        order_id = sell_order_result['return'].get('order_id')
                        # Indodax sell API mungkin tidak langsung memberikan 'receive_amount' di market sell
                        # Kita asumsikan received_idr adalah amount_to_sell_crypto * current_price
                        received_idr = amount_to_sell_crypto * current_price # Estimasi IDR yang diterima
                        
                        # Hitung profit/loss
                        profit_loss = received_idr - position_to_sell['buy_quote_amount_idr']
                        
                        # Catat penjualan ke database
                        self.db_manager.insert_trade_history(
                            pair=self.pair,
                            trade_type="sell",
                            price=current_price, # Gunakan harga pasar saat ini atau harga eksekusi
                            amount=amount_to_sell_crypto,
                            quote_amount=received_idr,
                            timestamp=int(time.time()),
                            order_id=order_id,
                            status="filled",
                            profit_loss=profit_loss,
                            notes="Bot auto-sell"
                        )
                        # Perbarui ringkasan keuntungan
                        self.db_manager.update_profit_summary(self.pair, profit_loss)

                        print(f"SELL order placed! ID: {order_id}. Profit/Loss: {profit_loss:,.2f} IDR")
                        self.last_trade_type = "SELL"
                    else:
                        print(f"Failed to place SELL order: {sell_order_result.get('error', 'Unknown error')}")
                        # Jika jual gagal, kembalikan posisi ke open_positions
                        self.open_positions[self.pair].insert(0, position_to_sell) 
                else:
                    print(f"Insufficient {asset_code.upper()} balance ({crypto_balance:.8f}) or invalid amount to sell ({amount_to_sell_crypto:.8f}). Holding.")
                    self.open_positions[self.pair].insert(0, position_to_sell) # Kembalikan posisi jika tidak cukup
            else:
                print("No open positions to sell. Holding.")
        else:
            print("Holding...")


    def run_bot(self, interval_seconds=60):
        print(f"Starting bot for {self.pair.upper()} with {interval_seconds} second interval...")
        while True:
            try:
                decision = self.make_trading_decision()
                self.execute_trade(decision)
            except Exception as e:
                print(f"An error occurred during bot run: {e}")
                import traceback
                traceback.print_exc() # Print full traceback for debugging
            time.sleep(interval_seconds)

if __name__ == "__main__":
    API_KEY = os.getenv("INDODAX_API_KEY")
    SECRET_KEY = os.getenv("INDODAX_SECRET_KEY")

    if not API_KEY or not SECRET_KEY:
        print("Please set INDODAX_API_KEY and INDODAX_SECRET_KEY in your .env file.")
    else:
        # BE CAREFUL WITH REAL FUNDS!
        # This bot is for demonstration purposes. Use paper trading/simulations first.
        # The trade_amount_idr is a fixed value here, you might want to make it dynamic.
        trading_bot = TradingBot(API_KEY, SECRET_KEY, pair="btcidr", trade_amount_idr=50000, ohlcv_interval_seconds=300)
        
        # To run the bot continuously:
        trading_bot.run_bot(interval_seconds=30) # Jalankan setiap 30 detik untuk pengujian cepat
        # Ingat: sesuaikan interval_seconds ini dengan seberapa sering Anda ingin bot membuat keputusan.
        # Interval yang lebih besar lebih stabil, lebih kecil lebih reaktif (tapi lebih banyak API call).

        # For a single test run without continuous loop (comment out run_bot above if using this):
        # print("Running a single bot cycle...")
        # decision = trading_bot.make_trading_decision()
        # trading_bot.execute_trade(decision)
        # print("Single bot cycle finished.")