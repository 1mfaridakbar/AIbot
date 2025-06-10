import time
import os
import pandas as pd
from datetime import datetime, timedelta

from indodax_api import IndodaxAPI
from database import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

# --- Konfigurasi ---
PAIR_TO_COLLECT = "btcidr"
INTERVAL_SECONDS = 300
COLLECTION_INTERVAL_SECONDS = 60

# --- Inisialisasi Klien ---
API_KEY = os.getenv("INDODAX_API_KEY")
SECRET_KEY = os.getenv("INDODAX_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    print("Error: INDODAX_API_KEY or INDODAX_SECRET_KEY not set in .env. Exiting data collector.")
    exit()

indodax_client = IndodaxAPI(API_KEY, SECRET_KEY)
db_manager = DatabaseManager()

trades_buffer = {}

def aggregate_trades_to_ohlcv(pair, trades, interval_seconds):
    # ... (fungsi ini tetap sama, tidak perlu diubah) ...
    if not trades:
        return []

    df = pd.DataFrame(trades)
    df['date'] = pd.to_datetime(df['date'], unit='s')
    df['price'] = pd.to_numeric(df['price'])
    df['amount'] = pd.to_numeric(df['amount'])

    df = df.set_index('date')

    ohlcv = df['price'].resample(f'{interval_seconds}s').ohlc() # <--- PERUBAHAN DI SINI
    ohlcv['volume'] = df['amount'].resample(f'{interval_seconds}s').sum() # <--- PERUBAHAN DI SINI

    ohlcv = ohlcv.dropna(subset=['volume'])
    
    ohlcv = ohlcv.reset_index()
    
    ohlcv['timestamp'] = ohlcv['date'].apply(lambda x: int(x.timestamp()))
    
    final_ohlcv_data = []
    current_unix_time = int(time.time())
    
    for _, row in ohlcv.iterrows():
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting data collection for {PAIR_TO_COLLECT.upper()}...")
    
    global trades_buffer

    # Dapatkan data trades terbaru dari Indodax
    # Indodax trades API mengembalikan list langsung, bukan dictionary dengan kunci 'trades'
    # Perbaikan: Langsung gunakan respons dari indodax_client.get_trades()
    raw_trades_response = indodax_client.get_trades(PAIR_TO_COLLECT)
    # --- TAMBAHKAN BARIS INI UNTUK DEBUGGING ---
    print(f"  Raw trades response type: {type(raw_trades_response)}")
    print(f"  Raw trades response content (first 200 chars): {str(raw_trades_response)[:200]}")
    # --- AKHIR BARIS DEBUGGING ---
    
    # Periksa apakah respons adalah list dan tidak kosong
    if isinstance(raw_trades_response, list) and raw_trades_response: # <--- PERUBAHAN UTAMA DI SINI
        
        # Inisialisasi buffer untuk pasangan jika belum ada
        if PAIR_TO_COLLECT not in trades_buffer:
            trades_buffer[PAIR_TO_COLLECT] = []

        # Tambahkan trades baru ke buffer
        existing_trade_ids = {trade['tid'] for trade in trades_buffer[PAIR_TO_COLLECT]}
        new_trades_added = 0
        
        # Iterasi langsung melalui raw_trades_response
        for trade in raw_trades_response: # <--- PERUBAHAN UTAMA DI SINI
            # Pastikan 'tid' ada sebelum mencoba mengaksesnya
            if 'tid' in trade and trade['tid'] not in existing_trade_ids:
                trade_ts = int(trade['date'])
                trade_price = float(trade['price'])
                trade_amount = float(trade['amount'])
                
                trades_buffer[PAIR_TO_COLLECT].append({
                    'date': trade_ts,
                    'price': trade_price,
                    'amount': trade_amount,
                    'tid': trade['tid']
                })
                new_trades_added += 1
        
        # Sort buffer by timestamp to ensure correct OHLCV aggregation
        trades_buffer[PAIR_TO_COLLECT].sort(key=lambda x: x['date'])
        print(f"  Added {new_trades_added} new trades to buffer. Buffer size: {len(trades_buffer[PAIR_TO_COLLECT])}")

        # Hapus trades yang sangat lama dari buffer
        buffer_retention_seconds = INTERVAL_SECONDS * 12
        cutoff_time = int(time.time()) - buffer_retention_seconds
        initial_buffer_size = len(trades_buffer[PAIR_TO_COLLECT])
        trades_buffer[PAIR_TO_COLLECT] = [
            trade for trade in trades_buffer[PAIR_TO_COLLECT] if trade['date'] >= cutoff_time
        ]
        removed_trades = initial_buffer_size - len(trades_buffer[PAIR_TO_COLLECT])
        if removed_trades > 0:
            print(f"  Removed {removed_trades} old trades from buffer. New buffer size: {len(trades_buffer[PAIR_TO_COLLECT])}")

        # Agregasi dan simpan data OHLCV
        ohlcv_to_save = aggregate_trades_to_ohlcv(PAIR_TO_COLLECT, trades_buffer[PAIR_TO_COLLECT], INTERVAL_SECONDS)
        
        if ohlcv_to_save:
            print(f"  Aggregated {len(ohlcv_to_save)} new OHLCV candles to save.")
            for candle in ohlcv_to_save:
                db_manager.insert_ohlcv_data(
                    candle['pair'],
                    candle['timestamp'],
                    candle['open'],
                    candle['high'],
                    candle['low'],
                    candle['close'],
                    candle['volume']
                )
        else:
            print("  No new complete OHLCV candles to save yet.")
    else:
        print(f"  No valid trades data received for {PAIR_TO_COLLECT} or response was empty/not a list.") # <--- PERUBAHAN UTAMA DI SINI

# ... (run_data_collector() dan if __name__ == "__main__": tetap sama) ...

def run_data_collector():
    print("Starting data collector. Press Ctrl+C to stop.")
    while True:
        try:
            collect_data()
            time.sleep(COLLECTION_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nData collector stopped by user.")
            break
        except Exception as e:
            print(f"An error occurred in data collector: {e}")
            time.sleep(COLLECTION_INTERVAL_SECONDS) # Tunggu sebelum retry

if __name__ == "__main__":
    run_data_collector()
    