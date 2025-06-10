# file: data_collector.py

import time
import os
import pandas as pd
from datetime import datetime
from indodax_api import IndodaxAPI
from database import DatabaseManager
from dotenv import load_dotenv
import config # Mengimpor file konfigurasi

load_dotenv()

# --- Konfigurasi diambil dari config.py ---

# Inisialisasi Klien
API_KEY = os.getenv("INDODAX_API_KEY")
SECRET_KEY = os.getenv("INDODAX_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    print("Error: INDODAX_API_KEY or INDODAX_SECRET_KEY not set. Exiting data collector.")
    exit()

indodax_client = IndodaxAPI(API_KEY, SECRET_KEY)
db_manager = DatabaseManager()

trades_buffer = {}

def aggregate_trades_to_ohlcv(pair, trades, interval_seconds):
    if not trades:
        return []

    df = pd.DataFrame(trades)
    df['date'] = pd.to_datetime(df['date'], unit='s')
    df['price'] = pd.to_numeric(df['price'])
    df['amount'] = pd.to_numeric(df['amount'])
    df = df.set_index('date')

    resample_rule = f'{interval_seconds}s'
    ohlcv = df['price'].resample(resample_rule).ohlc()
    ohlcv['volume'] = df['amount'].resample(resample_rule).sum()
    ohlcv = ohlcv.dropna(subset=['open']) # Hanya candle yang valid (ada transaksi)
    
    ohlcv = ohlcv.reset_index()
    ohlcv['timestamp'] = ohlcv['date'].apply(lambda x: int(x.timestamp()))
    
    final_ohlcv_data = []
    current_unix_time = int(time.time())
    
    for _, row in ohlcv.iterrows():
        # Hanya simpan candle yang sudah "selesai" (tidak sedang berjalan)
        if row['timestamp'] + interval_seconds <= current_unix_time:
            final_ohlcv_data.append({
                'pair': pair,
                'timestamp': row['timestamp'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            })
    return final_ohlcv_data


def collect_data():
    pair = config.PAIR_TO_TRADE
    interval = config.OHLCV_INTERVAL_SECONDS
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collecting data for {pair.upper()}...")
    
    global trades_buffer
    raw_trades_response = indodax_client.get_trades(pair)
    
    if isinstance(raw_trades_response, list) and raw_trades_response:
        if pair not in trades_buffer:
            trades_buffer[pair] = []

        existing_trade_ids = {trade['tid'] for trade in trades_buffer[pair]}
        new_trades_added = 0
        
        for trade in raw_trades_response:
            if 'tid' in trade and trade['tid'] not in existing_trade_ids:
                trades_buffer[pair].append({
                    'date': int(trade['date']),
                    'price': float(trade['price']),
                    'amount': float(trade['amount']),
                    'tid': trade['tid']
                })
                new_trades_added += 1
        
        trades_buffer[pair].sort(key=lambda x: x['date'])
        
        # Hapus buffer yang lebih tua dari (jumlah candle yang dibutuhkan * interval)
        buffer_retention_seconds = interval * (config.LONG_MA_WINDOW + 20) 
        cutoff_time = int(time.time()) - buffer_retention_seconds
        trades_buffer[pair] = [t for t in trades_buffer[pair] if t['date'] >= cutoff_time]
        
        print(f"  Added {new_trades_added} new trades. Buffer size: {len(trades_buffer[pair])}")
        
        ohlcv_to_save = aggregate_trades_to_ohlcv(pair, trades_buffer[pair], interval)
        
        if ohlcv_to_save:
            saved_count = 0
            for candle in ohlcv_to_save:
                if db_manager.insert_ohlcv_data(
                    candle['pair'], candle['timestamp'], candle['open'],
                    candle['high'], candle['low'], candle['close'], candle['volume']
                ):
                    saved_count +=1
            if saved_count > 0:
                 print(f"  Saved {saved_count} new OHLCV candles to database.")
        else:
            print("  No new complete OHLCV candles to save yet.")
    else:
        print(f"  No valid trades data received for {pair} or response was empty.")

def run_data_collector():
    print("Starting data collector. Press Ctrl+C to stop.")
    while True:
        try:
            collect_data()
            time.sleep(config.DATA_COLLECTION_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nData collector stopped by user.")
            break
        except Exception as e:
            print(f"An error occurred in data collector: {e}")
            time.sleep(config.DATA_COLLECTION_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_data_collector()