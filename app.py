from flask import Flask, render_template, jsonify, g # Import 'g' from Flask
import os
from indodax_api import IndodaxAPI
from database import DatabaseManager  # Import DatabaseManager
from dotenv import load_dotenv
import time

load_dotenv()

app = Flask(__name__)

# Initialize Indodax API client
API_KEY = os.getenv("INDODAX_API_KEY")
SECRET_KEY = os.getenv("INDODAX_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    print("Warning: INDODAX_API_KEY or INDODAX_SECRET_KEY not set. Dashboard might not work fully.")
    indodax_client = None
else:
    indodax_client = IndodaxAPI(API_KEY, SECRET_KEY)

# --- Removed global db_manager = DatabaseManager() ---
# Database connection will now be managed per-request


# Function to get a database connection for the current request
def get_db():
    if 'db' not in g: # Check if a db connection already exists in the global 'g' object for this request
        g.db = DatabaseManager() # If not, create a new one and store it
    return g.db

# Function to close the database connection at the end of the request
@app.teardown_appcontext
def close_db_connection(exception):
    db = g.pop('db', None) # Get the db object from 'g' and remove it
    if db: # If a db object existed for this request
        db.close_connection() # Close its connection


@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/dashboard_data')
def get_dashboard_data():
    # Get database manager instance for this specific request
    db_manager_current_request = get_db() 

    # Pastikan indodax_client tersedia sebelum mencoba memanggilnya
    if not indodax_client:
        return jsonify({"error": "API keys not configured."}), 500

    # Ambil saldo dari Indodax API
    info = indodax_client.get_info()
    balance = {}
    if info and info['success'] == 1:
        balance = info['return']['balance']
    else:
        print("Failed to get balance info from Indodax.")
        balance = {'idr': 0.0, 'btc': 0.0, 'eth': 0.0}

    # Ambil harga ticker BTC/IDR saat ini (contoh, Anda bisa menambahkan ETH/IDR dll.)
    btcidr_ticker = indodax_client.get_ticker("btcidr")
    current_btc_price = float(btcidr_ticker['ticker']['last']) if btcidr_ticker and 'ticker' in btcidr_ticker else 0

    # Hitung total nilai aset (perkiraan sederhana)
    idr_balance = float(balance.get('idr', 0))
    btc_balance = float(balance.get('btc', 0))
    total_asset_value_idr = idr_balance + (btc_balance * current_btc_price)

    # --- Ambil data dari Database (menggunakan db_manager_current_request) ---
    profit_summary_data = db_manager_current_request.get_profit_summary() # Use the request-specific db_manager
    total_realized_profit_all_pairs = 0.0
    profit_by_pair = {}
    for row in profit_summary_data:
        pair = row['pair']
        profit = row['total_realized_profit']
        profit_by_pair[pair] = f"{profit:,.2f} IDR"
        total_realized_profit_all_pairs += profit
    
    # Ambil 5 riwayat perdagangan terbaru
    recent_trades_raw = db_manager_current_request.get_trade_history(limit=5) # Use the request-specific db_manager
    recent_trades_formatted = []
    for trade in recent_trades_raw:
        trade_time_readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trade['timestamp']))
        recent_trades_formatted.append({
            'type': trade['trade_type'].upper(),
            'pair': trade['pair'].upper(),
            'amount': f"{trade['amount']:.8f}",
            'price': f"{trade['price']:,.0f}",
            'quote_amount': f"{trade['quote_amount']:,.2f}",
            'profit_loss': f"{trade['profit_loss']:,.2f}" if trade['profit_loss'] is not None else "N/A",
            'timestamp': trade_time_readable,
            'status': trade['status'] if trade['status'] else 'N/A'
        })

    # Placeholder for percentage profit. This calculation will need refinement
    # as your bot grows and you track initial capital/investments more accurately.
    initial_capital_placeholder = 10000000.0
    percentage_profit = (total_realized_profit_all_pairs / initial_capital_placeholder) * 100 if initial_capital_placeholder > 0 else 0

    dashboard_data = {
        "current_balance_idr": f"{idr_balance:,.2f} IDR",
        "current_balance_btc": f"{btc_balance:.8f} BTC",
        "current_btc_price": f"{current_btc_price:,.0f} IDR",
        "total_asset_value_idr": f"{total_asset_value_idr:,.2f} IDR",
        "total_profit_idr": f"{total_realized_profit_all_pairs:,.2f} IDR",
        "percentage_profit": f"{percentage_profit:.2f}%",
        "profit_by_pair": profit_by_pair,
        "recent_trades": recent_trades_formatted,
        "other_relevant_data": "..."
    }
    return jsonify(dashboard_data)

# No need for this if get_db and teardown_appcontext are properly implemented
# @app.teardown_appcontext
# def close_db_connection(exception):
#     if hasattr(db_manager, 'conn') and db_manager.conn is not None:
#         db_manager.close_connection()

if __name__ == '__main__':
    app.run(debug=True)