# file: config.py

# --- PENGATURAN UMUM ---
PAIR_TO_TRADE = "btcidr" 
TRADE_AMOUNT_IDR = 50000 

# --- PENGATURAN MANAJEMEN RISIKO (BARU) ---
# Tentukan persentase dalam angka. Misal: 5.0 untuk 5%
TAKE_PROFIT_PERCENTAGE = 5.0  # Jual jika profit mencapai 5% dari harga beli
STOP_LOSS_PERCENTAGE = 2.0   # Jual jika rugi mencapai 2% dari harga beli

# --- PENGATURAN STRATEGI (MA Crossover) ---
SHORT_MA_WINDOW = 10 
LONG_MA_WINDOW = 30  

# --- PENGATURAN PENGUMPULAN DATA ---
OHLCV_INTERVAL_SECONDS = 300 
DATA_COLLECTION_INTERVAL_SECONDS = 60 

# --- PENGATURAN BOT ---
BOT_RUN_INTERVAL_SECONDS = 30