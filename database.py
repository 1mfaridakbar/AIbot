# file: database.py

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
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(pair, timestamp)
            )
        ''')

        # Tabel untuk riwayat perdagangan bot (STRUKTUR DIPERBARUI)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                quote_amount REAL NOT NULL,
                timestamp INTEGER NOT NULL,
                order_id TEXT UNIQUE,
                status TEXT DEFAULT 'open', 
                profit_loss REAL,
                associated_buy_id INTEGER,
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
            # print("Database connection closed.") # Bisa di-uncomment jika perlu debug

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

        if limit:
             # Mengambil data terbaru dengan mengurutkan secara descending, lalu mengurutkannya kembali secara ascending
            query = f"SELECT * FROM (SELECT * FROM ohlcv_data WHERE pair = ? ORDER BY timestamp DESC LIMIT {limit}) ORDER BY timestamp ASC"
            params = [pair]

        cursor.execute(query, params)
        return cursor.fetchall()

    def insert_trade_history(self, pair, trade_type, price, amount, quote_amount, timestamp, order_id=None, status='open', profit_loss=None, associated_buy_id=None, notes=None):
        """Memasukkan riwayat perdagangan bot."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO trade_history (pair, trade_type, price, amount, quote_amount, timestamp, order_id, status, profit_loss, associated_buy_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (pair, trade_type, price, amount, quote_amount, timestamp, order_id, status, profit_loss, associated_buy_id, notes))
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
        
        query += " ORDER BY timestamp DESC"

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

    # --- FUNGSI BARU UNTUK BOT STATEFUL ---
    def get_open_buy_trades(self, pair):
        """Mengambil semua trade 'buy' yang masih berstatus 'open'."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_history WHERE pair = ? AND trade_type = 'buy' AND status = 'open'", (pair,))
        return cursor.fetchall()

    def close_buy_trade(self, buy_trade_id):
        """Mengubah status trade 'buy' yang sudah terjual menjadi 'closed'."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE trade_history SET status = 'closed' WHERE id = ?", (buy_trade_id,))
        conn.commit()
        print(f"Trade ID {buy_trade_id} has been closed in the database.")