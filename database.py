import sqlite3
import os
import time

DATABASE_FILE = 'trading_data.db' # Nama file database Anda

class DatabaseManager:
    def __init__(self, db_file=DATABASE_FILE):
        self.db_file = db_file
        self.conn = None # Koneksi database
        self._initialize_db()

    def _get_connection(self):
        """Mendapatkan koneksi ke database. Membuat koneksi jika belum ada."""
        if self.conn is None:
            # Check if directory exists, create if not (for more complex paths)
            # db_dir = os.path.dirname(self.db_file)
            # if db_dir and not os.path.exists(db_dir):
            #     os.makedirs(db_dir)
            self.conn = sqlite3.connect(self.db_file)
            self.conn.row_factory = sqlite3.Row # Mengizinkan akses kolom seperti dictionary
        return self.conn

    def _initialize_db(self):
        """Membuat tabel jika belum ada."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Tabel untuk data OHLCV (Open, High, Low, Close, Volume)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                timestamp INTEGER NOT NULL, -- Unix timestamp
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(pair, timestamp) -- Memastikan tidak ada duplikasi data per pasangan dan waktu
            )
        ''')

        # Tabel untuk riwayat perdagangan bot
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                trade_type TEXT NOT NULL, -- 'buy' or 'sell'
                price REAL NOT NULL,
                amount REAL NOT NULL, -- Jumlah kripto yang diperdagangkan
                quote_amount REAL NOT NULL, -- Jumlah IDR yang terlibat (misal: IDR yang dibayar/diterima)
                timestamp INTEGER NOT NULL, -- Unix timestamp saat order dieksekusi/tercatat
                order_id TEXT UNIQUE, -- ID order dari Indodax (jika ada)
                status TEXT, -- 'filled', 'pending', 'cancelled'
                profit_loss REAL, -- Keuntungan/kerugian untuk perdagangan ini (akan dihitung nanti saat sell)
                notes TEXT
            )
        ''')
        
        # Tabel untuk melacak keuntungan/kerugian per pair (agregat)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_summary (
                pair TEXT PRIMARY KEY,
                total_realized_profit REAL DEFAULT 0.0,
                last_updated INTEGER NOT NULL
            )
        ''')

        conn.commit()
        print(f"Database initialized: {self.db_file}")

    def close_connection(self):
        """Menutup koneksi database."""
        if self.conn:
            self.conn.close()
            self.conn = None
            print("Database connection closed.")

    def insert_ohlcv_data(self, pair, timestamp, open_price, high_price, low_price, close_price, volume):
        """Memasukkan data OHLCV ke database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO ohlcv_data (pair, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (pair, timestamp, open_price, high_price, low_price, close_price, volume))
            conn.commit()
            # print(f"Inserted OHLCV for {pair} at {timestamp}") # Uncomment for debugging
            return True
        except sqlite3.Error as e:
            print(f"Error inserting OHLCV data: {e}")
            return False

    def get_ohlcv_data(self, pair, limit=None, start_timestamp=None, end_timestamp=None):
        """Mengambil data OHLCV dari database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM ohlcv_data WHERE pair = ? ORDER BY timestamp ASC"
        params = [pair]

        if start_timestamp and end_timestamp:
            query = "SELECT * FROM ohlcv_data WHERE pair = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC"
            params = [pair, start_timestamp, end_timestamp]
        elif start_timestamp:
            query = "SELECT * FROM ohlcv_data WHERE pair = ? AND timestamp >= ? ORDER BY timestamp ASC"
            params = [pair, start_timestamp]
        elif end_timestamp:
            query = "SELECT * FROM ohlcv_data WHERE pair = ? AND timestamp <= ? ORDER BY timestamp ASC"
            params = [pair, end_timestamp]

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        return cursor.fetchall()

    def insert_trade_history(self, pair, trade_type, price, amount, quote_amount, timestamp, order_id=None, status=None, profit_loss=None, notes=None):
        """Memasukkan riwayat perdagangan bot."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO trade_history (pair, trade_type, price, amount, quote_amount, timestamp, order_id, status, profit_loss, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (pair, trade_type, price, amount, quote_amount, timestamp, order_id, status, profit_loss, notes))
            conn.commit()
            print(f"Trade recorded: {trade_type.upper()} {amount} {pair.split('idr')[0].upper()} at {price}")
            return True
        except sqlite3.Error as e:
            print(f"Error inserting trade history: {e}")
            return False
            
    def get_trade_history(self, pair=None, trade_type=None, limit=None):
        """Mengambil riwayat perdagangan bot."""
        conn = self._get_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM trade_history"
        conditions = []
        params = []

        if pair:
            conditions.append("pair = ?")
            params.append(pair)
        if trade_type:
            conditions.append("trade_type = ?")
            params.append(trade_type)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp DESC" # Order by latest first

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        return cursor.fetchall()
        
    def update_profit_summary(self, pair, realized_profit):
        """Memperbarui atau memasukkan ringkasan keuntungan untuk pasangan tertentu."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO profit_summary (pair, total_realized_profit, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(pair) DO UPDATE SET
                    total_realized_profit = total_realized_profit + ?,
                    last_updated = ?
            ''', (pair, realized_profit, int(time.time()), realized_profit, int(time.time())))
            conn.commit()
            print(f"Profit summary updated for {pair}: Added {realized_profit:.2f}")
            return True
        except sqlite3.Error as e:
            print(f"Error updating profit summary: {e}")
            return False

    def get_profit_summary(self):
        """Mengambil semua ringkasan keuntungan."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profit_summary")
        return cursor.fetchall()

# --- Contoh Penggunaan (untuk pengujian) ---
if __name__ == "__main__":
    # Inisialisasi DatabaseManager di awal
    db_manager = DatabaseManager()

    # Hapus database jika ada untuk pengujian bersih, HANYA SEKALI DI AWAL
    if os.path.exists(DATABASE_FILE):
        try:
            # Pastikan koneksi ditutup sebelum menghapus
            # (Jika ada koneksi dari inisialisasi awal, tutup dulu)
            db_manager.close_connection() 
            os.remove(DATABASE_FILE)
            print(f"Existing database {DATABASE_FILE} removed for a clean test.")
            # Setelah menghapus, inisialisasi ulang DatabaseManager untuk mendapatkan koneksi baru
            db_manager = DatabaseManager() 
        except PermissionError:
            print(f"Warning: Could not remove existing database {DATABASE_FILE}. It might be in use by another process. Skipping deletion.")
            # Jika tidak bisa dihapus, kita tetap akan menggunakan database yang ada.
            # Untuk pengujian bersih, Anda perlu menutup semua program dan menghapus manual.
        except Exception as e:
            print(f"An unexpected error occurred while trying to remove the database: {e}")
            # Jika ada error lain, kita tetap inisialisasi ulang untuk memastikan koneksi ada.
            db_manager = DatabaseManager() 

    # --- Bagian pengujian lainnya tetap sama ---
    # (Kode di bawah ini adalah kelanjutan dari yang sudah Anda miliki)

    print("\n--- Testing OHLCV Data Insertion ---")
    current_time = int(time.time())
    db_manager.insert_ohlcv_data("btcidr", current_time, 70000000, 70500000, 69800000, 70200000, 1.5)
    db_manager.insert_ohlcv_data("btcidr", current_time + 60, 70200000, 70300000, 70000000, 70100000, 1.2)
    db_manager.insert_ohlcv_data("ethidr", current_time, 40000000, 40200000, 39800000, 40100000, 5.0)

    ohlcv_data = db_manager.get_ohlcv_data("btcidr")
    print("\nOHLCV Data for BTCDIDR:")
    for row in ohlcv_data:
        print(f"  ID:{row['id']}, Pair:{row['pair']}, Time:{row['timestamp']}, Close:{row['close']}, Vol:{row['volume']}")

    print("\n--- Testing Trade History Insertion ---")
    db_manager.insert_trade_history("btcidr", "buy", 70000000, 0.001, 70000, int(time.time()), "ORDER_BTC_BUY_1", "filled", notes="Initial buy")
    db_manager.insert_trade_history("btcidr", "sell", 71000000, 0.001, 71000, int(time.time()) + 300, "ORDER_BTC_SELL_1", "filled", profit_loss=1000, notes="Profit trade")
    db_manager.insert_trade_history("ethidr", "buy", 40000000, 0.005, 200000, int(time.time()) + 100, "ORDER_ETH_BUY_1", "filled", notes="Initial ETH buy")

    trade_history = db_manager.get_trade_history()
    print("\nAll Trade History (latest 3):")
    for row in trade_history:
        print(f"  ID:{row['id']}, Pair:{row['pair']}, Type:{row['trade_type']}, Price:{row['price']}, Amount:{row['amount']}, Profit:{row['profit_loss']}")

    print("\n--- Testing Profit Summary Update ---")
    db_manager.update_profit_summary("btcidr", 1000)
    db_manager.update_profit_summary("ethidr", 500)
    db_manager.update_profit_summary("btcidr", 200) # Add more profit to BTCDIDR

    profit_summary = db_manager.get_profit_summary()
    print("\nProfit Summary:")
    for row in profit_summary:
        print(f"  Pair:{row['pair']}, Total Profit:{row['total_realized_profit']}")


    # Pastikan koneksi ditutup di akhir script
    db_manager.close_connection()
    db_manager = DatabaseManager()

    # Hapus database jika ada untuk pengujian bersih
    if os.path.exists(DATABASE_FILE):
        try:
            db_manager.close_connection() # Pastikan koneksi ditutup sebelum menghapus
            os.remove(DATABASE_FILE)
            print(f"Existing database {DATABASE_FILE} removed for a clean test.")
            db_manager = DatabaseManager() # Re-initialize after deletion
        except PermissionError:
            print(f"Warning: Could not remove existing database {DATABASE_FILE}. It might be in use by another process. Skipping deletion.")
            # Jika tidak bisa dihapus, kita tetap akan menggunakan database yang ada,
            # yang mungkin sudah berisi data. Untuk pengujian bersih, Anda perlu
            # menutup semua program dan menghapus manual.
        except Exception as e:
            print(f"An unexpected error occurred while trying to remove the database: {e}")
            db_manager = DatabaseManager() # Re-initialize even if error occurs
    
    # Bagian pengujian lainnya tetap sama
    print("\n--- Testing OHLCV Data Insertion ---")
    current_time = int(time.time())
    db_manager.insert_ohlcv_data("btcidr", current_time, 70000000, 70500000, 69800000, 70200000, 1.5)
    db_manager.insert_ohlcv_data("btcidr", current_time + 60, 70200000, 70300000, 70000000, 70100000, 1.2)
    db_manager.insert_ohlcv_data("ethidr", current_time, 40000000, 40200000, 39800000, 40100000, 5.0)

    ohlcv_data = db_manager.get_ohlcv_data("btcidr")
    print("\nOHLCV Data for BTCDIDR:")
    for row in ohlcv_data:
        print(f"  ID:{row['id']}, Pair:{row['pair']}, Time:{row['timestamp']}, Close:{row['close']}, Vol:{row['volume']}")

    print("\n--- Testing Trade History Insertion ---")
    db_manager.insert_trade_history("btcidr", "buy", 70000000, 0.001, 70000, int(time.time()), "ORDER_BTC_BUY_1", "filled", notes="Initial buy")
    db_manager.insert_trade_history("btcidr", "sell", 71000000, 0.001, 71000, int(time.time()) + 300, "ORDER_BTC_SELL_1", "filled", profit_loss=1000, notes="Profit trade")
    db_manager.insert_trade_history("ethidr", "buy", 40000000, 0.005, 200000, int(time.time()) + 100, "ORDER_ETH_BUY_1", "filled", notes="Initial ETH buy")

    trade_history = db_manager.get_trade_history()
    print("\nAll Trade History (latest 3):")
    for row in trade_history:
        print(f"  ID:{row['id']}, Pair:{row['pair']}, Type:{row['trade_type']}, Price:{row['price']}, Amount:{row['amount']}, Profit:{row['profit_loss']}")

    print("\n--- Testing Profit Summary Update ---")
    db_manager.update_profit_summary("btcidr", 1000)
    db_manager.update_profit_summary("ethidr", 500)
    db_manager.update_profit_summary("btcidr", 200) # Add more profit to BTCDIDR

    profit_summary = db_manager.get_profit_summary()
    print("\nProfit Summary:")
    for row in profit_summary:
        print(f"  Pair:{row['pair']}, Total Profit:{row['total_realized_profit']}")


    db_manager.close_connection() # Pastikan ini selalu terpanggil di akhir
    db_manager = DatabaseManager()

    # Hapus database jika ada untuk pengujian bersih
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
        print(f"Existing database {DATABASE_FILE} removed for a clean test.")
        db_manager = DatabaseManager() # Re-initialize after deletion

    print("\n--- Testing OHLCV Data Insertion ---")
    current_time = int(time.time())
    db_manager.insert_ohlcv_data("btcidr", current_time, 70000000, 70500000, 69800000, 70200000, 1.5)
    db_manager.insert_ohlcv_data("btcidr", current_time + 60, 70200000, 70300000, 70000000, 70100000, 1.2)
    db_manager.insert_ohlcv_data("ethidr", current_time, 40000000, 40200000, 39800000, 40100000, 5.0)

    ohlcv_data = db_manager.get_ohlcv_data("btcidr")
    print("\nOHLCV Data for BTCDIDR:")
    for row in ohlcv_data:
        print(f"  ID:{row['id']}, Pair:{row['pair']}, Time:{row['timestamp']}, Close:{row['close']}, Vol:{row['volume']}")

    print("\n--- Testing Trade History Insertion ---")
    db_manager.insert_trade_history("btcidr", "buy", 70000000, 0.001, 70000, int(time.time()), "ORDER_BTC_BUY_1", "filled", notes="Initial buy")
    db_manager.insert_trade_history("btcidr", "sell", 71000000, 0.001, 71000, int(time.time()) + 300, "ORDER_BTC_SELL_1", "filled", profit_loss=1000, notes="Profit trade")
    db_manager.insert_trade_history("ethidr", "buy", 40000000, 0.005, 200000, int(time.time()) + 100, "ORDER_ETH_BUY_1", "filled", notes="Initial ETH buy")

    trade_history = db_manager.get_trade_history()
    print("\nAll Trade History (latest 3):")
    for row in trade_history:
        print(f"  ID:{row['id']}, Pair:{row['pair']}, Type:{row['trade_type']}, Price:{row['price']}, Amount:{row['amount']}, Profit:{row['profit_loss']}")

    print("\n--- Testing Profit Summary Update ---")
    db_manager.update_profit_summary("btcidr", 1000)
    db_manager.update_profit_summary("ethidr", 500)
    db_manager.update_profit_summary("btcidr", 200) # Add more profit to BTCDIDR

    profit_summary = db_manager.get_profit_summary()
    print("\nProfit Summary:")
    for row in profit_summary:
        print(f"  Pair:{row['pair']}, Total Profit:{row['total_realized_profit']}")


    db_manager.close_connection()