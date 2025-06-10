# file: bot_logic.py

import time
import os
import pandas as pd
import pandas_ta as ta # -> Import library baru untuk indikator teknikal
from datetime import datetime
from indodax_api import IndodaxAPI
from database import DatabaseManager
from dotenv import load_dotenv
import config 

load_dotenv()

class TradingBot:
    def __init__(self, api_key, secret_key, 
                 pair=config.PAIR_TO_TRADE, 
                 trade_amount_idr=config.TRADE_AMOUNT_IDR):
        self.indodax = IndodaxAPI(api_key, secret_key)
        self.db_manager = DatabaseManager()
        self.pair = pair
        self.trade_amount_idr = trade_amount_idr
        self.ohlcv_interval_seconds = config.OHLCV_INTERVAL_SECONDS
        self.last_trade_type = None
        self.open_positions = {}

        self.short_ma_window = config.SHORT_MA_WINDOW
        self.long_ma_window = config.LONG_MA_WINDOW
        
        self._load_open_positions_from_db()
        
    def _load_open_positions_from_db(self):
        print("Loading open positions from database...")
        self.open_positions[self.pair] = []
        open_trades = self.db_manager.get_open_buy_trades(self.pair)
        
        for trade in open_trades:
            self.open_positions[self.pair].append({
                'buy_id': trade['id'],
                'buy_price': trade['price'],
                'buy_amount_crypto': trade['amount'],
                'buy_timestamp': trade['timestamp'],
                'buy_order_id': trade['order_id'],
                'buy_quote_amount_idr': trade['quote_amount']
            })
        print(f"Found {len(self.open_positions.get(self.pair, []))} open position(s) for {self.pair.upper()}.")

    def _get_current_prices(self):
        ticker = self.indodax.get_ticker(self.pair)
        if ticker and ticker.get('ticker'):
            return float(ticker['ticker']['last']), float(ticker['ticker']['buy']), float(ticker['ticker']['sell'])
        return None, None, None

    def _get_balance(self, asset_code):
        info = self.indodax.get_info()
        if info and info['success'] == 1:
            return float(info['return']['balance'].get(asset_code, 0))
        return 0

    def get_ohlcv_from_db(self):
        needed_candles = self.long_ma_window + 20 # Butuh lebih banyak data untuk RSI
        ohlcv_rows = self.db_manager.get_ohlcv_data(self.pair, limit=needed_candles)
        
        if not ohlcv_rows:
            return pd.DataFrame()
        
        data_for_df = [dict(row) for row in ohlcv_rows]
        df = pd.DataFrame(data_for_df)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.set_index('timestamp').sort_index()
        return df[['open', 'high', 'low', 'close', 'volume']]

    # --- FUNGSI DIPERBARUI UNTUK MENGHITUNG SEMUA INDIKATOR ---
    def _calculate_indicators(self, df):
        """Menghitung semua indikator teknikal yang dibutuhkan (SMA dan RSI)."""
        if df.empty or len(df) < self.long_ma_window:
            return None, None, None

        # Hitung SMA
        df['SMA_Short'] = df['close'].rolling(window=self.short_ma_window).mean()
        df['SMA_Long'] = df['close'].rolling(window=self.long_ma_window).mean()
        
        # Hitung RSI (dengan panjang standar 14)
        df.ta.rsi(length=14, append=True) # Ini akan menambah kolom 'RSI_14'
        
        # Ambil nilai terakhir dari setiap indikator
        sma_short = df['SMA_Short'].iloc[-1]
        sma_long = df['SMA_Long'].iloc[-1]
        rsi = df['RSI_14'].iloc[-1]
        
        return sma_short, sma_long, rsi

    def _check_risk_management(self):
        if not self.open_positions.get(self.pair):
            return None

        current_price, _, _ = self._get_current_prices()
        if current_price is None:
            return None
        
        position = self.open_positions[self.pair][0]
        buy_price = position['buy_price']

        take_profit_price = buy_price * (1 + config.TAKE_PROFIT_PERCENTAGE / 100)
        stop_loss_price = buy_price * (1 - config.STOP_LOSS_PERCENTAGE / 100)
        
        print(f"  [Risk Check] Buy Price: {buy_price:,.0f} | Current: {current_price:,.0f} | TP Target: {take_profit_price:,.0f} | SL Target: {stop_loss_price:,.0f}")

        if current_price >= take_profit_price:
            return "Take-Profit"
        
        if current_price <= stop_loss_price:
            return "Stop-Loss"
            
        return None

    # --- LOGIKA KEPUTUSAN DIPERBARUI DENGAN RSI ---
    def make_trading_decision(self):
        """Membuat keputusan trading berdasarkan MA Crossover yang dikonfirmasi oleh RSI."""
        ohlcv_df = self.get_ohlcv_from_db()
        
        if ohlcv_df.empty or len(ohlcv_df) < self.long_ma_window + 2:
            print("Not enough OHLCV data from DB to make a decision. Waiting...")
            return "HOLD"
            
        # Hitung semua indikator
        sma_short, sma_long, rsi = self._calculate_indicators(ohlcv_df)

        if sma_short is None or sma_long is None or pd.isna(rsi):
            print("Not enough data to calculate indicators. Holding.")
            return "HOLD"
        
        # Ambil SMA periode sebelumnya untuk deteksi crossover
        prev_sma_short = ohlcv_df['SMA_Short'].iloc[-2]
        prev_sma_long = ohlcv_df['SMA_Long'].iloc[-2]

        current_close_price = ohlcv_df['close'].iloc[-1]
        print(f"  [Strategy Check] Price: {current_close_price:,.0f} | SMA{self.short_ma_window}: {sma_short:,.0f} | SMA{self.long_ma_window}: {sma_long:,.0f} | RSI: {rsi:.2f}")

        # Kondisi Golden Cross + Konfirmasi RSI (tidak jenuh beli)
        is_golden_cross = sma_short > sma_long and prev_sma_short <= prev_sma_long
        if is_golden_cross and rsi < 70: # RSI < 70 adalah konfirmasi
            if not self.open_positions.get(self.pair):
                print(f">>> Golden Cross confirmed by RSI ({rsi:.2f} < 70): BUY Signal")
                return "BUY"
            else:
                return "HOLD"
        
        # Kondisi Death Cross + Konfirmasi RSI (tidak jenuh jual)
        is_death_cross = sma_short < sma_long and prev_sma_short >= prev_sma_long
        if is_death_cross and rsi > 30: # RSI > 30 adalah konfirmasi
            if self.open_positions.get(self.pair):
                print(f">>> Death Cross confirmed by RSI ({rsi:.2f} > 30): SELL Signal")
                return "SELL"
            else:
                return "HOLD"
        
        return "HOLD"

    def execute_trade(self, action, reason=""):
        current_price, _, _ = self._get_current_prices()
        if current_price is None: return

        trade_note = f"Bot auto-trade based on: {reason}"

        if action == "BUY":
            idr_balance = self._get_balance("idr")
            if idr_balance >= self.trade_amount_idr:
                print(f"Attempting to BUY {self.trade_amount_idr:,.0f} IDR worth of {self.pair.upper()}...")
                buy_order_result = self.indodax.trade(pair=self.pair, type="buy", amount=self.trade_amount_idr)
                if buy_order_result and buy_order_result['success'] == 1:
                    self.db_manager.insert_trade_history(
                        pair=self.pair, trade_type="buy", price=current_price,
                        amount=buy_order_result['return'].get('receive_amount', 0), 
                        quote_amount=self.trade_amount_idr,
                        timestamp=int(time.time()), order_id=buy_order_result['return'].get('order_id'),
                        status="open", notes=trade_note
                    )
                    print(f"BUY order successful! Reloading open positions from DB...")
                    self.last_trade_type = "BUY"
                    self._load_open_positions_from_db()
                else:
                    print(f"Failed to place BUY order: {buy_order_result.get('error', 'Unknown error')}")
        
        elif action == "SELL":
            if self.open_positions.get(self.pair):
                position_to_sell = self.open_positions[self.pair][0]
                amount_to_sell_crypto = position_to_sell['buy_amount_crypto']
                sell_order_result = self.indodax.trade(pair=self.pair, type="sell", amount=amount_to_sell_crypto)
                if sell_order_result and sell_order_result['success'] == 1:
                    received_idr = amount_to_sell_crypto * current_price
                    profit_loss = received_idr - position_to_sell['buy_quote_amount_idr']
                    self.db_manager.insert_trade_history(
                        pair=self.pair, trade_type="sell", price=current_price,
                        amount=amount_to_sell_crypto, quote_amount=received_idr,
                        timestamp=int(time.time()), order_id=sell_order_result['return'].get('order_id'),
                        status="closed", profit_loss=profit_loss,
                        associated_buy_id=position_to_sell['buy_id'], notes=trade_note
                    )
                    self.db_manager.close_buy_trade(position_to_sell['buy_id'])
                    self.db_manager.update_profit_summary(self.pair, profit_loss)
                    print(f"SELL order successful! Profit/Loss: {profit_loss:,.2f} IDR. Reloading positions...")
                    self.last_trade_type = "SELL"
                    self._load_open_positions_from_db()
                else:
                    print(f"Failed to place SELL order: {sell_order_result.get('error', 'Unknown error')}")

    def run_bot(self, interval_seconds=60):
        print(f"Starting bot for {self.pair.upper()} with {interval_seconds} second interval...")
        while True:
            try:
                print("-" * 60)
                sell_reason = self._check_risk_management()
                if sell_reason:
                    print(f">>> {sell_reason} Triggered! Executing SELL...")
                    self.execute_trade("SELL", reason=sell_reason)
                else:
                    strategy_decision = self.make_trading_decision()
                    if strategy_decision != "HOLD":
                        self.execute_trade(strategy_decision, reason=f"Strategy Signal ({strategy_decision})")
                    else:
                        print("Holding position based on strategy.")
            except Exception as e:
                print(f"An error occurred during bot run: {e}")
                import traceback
                traceback.print_exc()
            time.sleep(interval_seconds)

if __name__ == "__main__":
    API_KEY = os.getenv("INDODAX_API_KEY")
    SECRET_KEY = os.getenv("INDODAX_SECRET_KEY")

    if not API_KEY or not SECRET_KEY:
        print("Please set INDODAX_API_KEY and INDODAX_SECRET_KEY in your .env file.")
    else:
        trading_bot = TradingBot(API_KEY, SECRET_KEY)
        trading_bot.run_bot(interval_seconds=config.BOT_RUN_INTERVAL_SECONDS)