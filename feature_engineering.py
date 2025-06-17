# file: feature_engineering.py

import pandas as pd
import pandas_ta as ta
from database import DatabaseManager
import config

def generate_features():
    """
    Mengambil data OHLCV dari database, menghitung fitur-fitur teknikal,
    dan menyimpannya ke tabel feature_data.
    """
    print("--- Starting Feature Engineering Process ---")

    db = DatabaseManager()
    pair = config.PAIR_TO_TRADE

    # 1. Ambil SEMUA data OHLCV yang ada dari database
    print(f"Fetching all OHLCV data for {pair}...")
    all_data_rows = db.get_ohlcv_data(pair)
    
    if len(all_data_rows) < 50: # Butuh data yang cukup untuk menghitung indikator
        print("Not enough historical data to generate features. Run data_collector.py for a while.")
        db.close_connection()
        return

    # 2. Ubah ke Pandas DataFrame
    df = pd.DataFrame([dict(row) for row in all_data_rows])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.set_index('timestamp')
    print(f"Loaded {len(df)} data points.")

    # 3. Hitung semua indikator teknikal yang kita inginkan menggunakan pandas_ta
    print("Calculating technical indicators...")
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.bbands(append=True)
    df.ta.atr(append=True)
    df.ta.adx(append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    
    # Ganti nama kolom agar sesuai dengan skema database
    df.rename(columns={
        'RSI_14': 'rsi_14',
        'MACD_12_26_9': 'macd_12_26_9',
        'MACDh_12_26_9': 'macdh_12_26_9',
        'MACDs_12_26_9': 'macds_12_26_9',
        'BBL_20_2.0': 'bb_lower_20_2',
        'BBM_20_2.0': 'bb_middle_20_2',
        'BBU_20_2.0': 'bb_upper_20_2',
        'ATRr_14': 'atr_14',
        'ADX_14': 'adx_14',
        'EMA_20': 'ema_20',
        'EMA_50': 'ema_50'
    }, inplace=True)

    # 4. Hapus baris yang memiliki nilai NaN (biasanya di awal data karena butuh periode untuk menghitung)
    df.dropna(inplace=True)
    print(f"Data points after dropping NaN: {len(df)}")

    # 5. Persiapkan data untuk dimasukkan ke database
    df.reset_index(inplace=True) # Kembalikan timestamp dari index ke kolom
    df['timestamp'] = df['timestamp'].astype('int64') // 10**9 # Ubah ke unix timestamp integer

    data_to_insert = []
    for _, row in df.iterrows():
        data_to_insert.append((
            pair,
            row['timestamp'],
            row['open'],
            row['high'],
            row['low'],
            row['close'],
            row['volume'],
            row.get('rsi_14'),
            row.get('macd_12_26_9'),
            row.get('macdh_12_26_9'),
            row.get('macds_12_26_9'),
            row.get('bb_lower_20_2'),
            row.get('bb_middle_20_2'),
            row.get('bb_upper_20_2'),
            row.get('atr_14'),
            row.get('adx_14'),
            row.get('ema_20'),
            row.get('ema_50')
        ))

    # 6. Bersihkan data lama dan masukkan data baru yang sudah diperkaya
    if data_to_insert:
        print(f"Preparing to insert {len(data_to_insert)} rows of feature data...")
        db.clear_feature_data(pair) # Hapus data lama
        if db.insert_feature_data_batch(data_to_insert): # Masukkan data baru
            print("Successfully inserted feature data into the database.")
        else:
            print("Failed to insert feature data.")
    else:
        print("No feature data to insert.")

    db.close_connection()
    print("--- Feature Engineering Process Finished ---")


if __name__ == "__main__":
    generate_features()