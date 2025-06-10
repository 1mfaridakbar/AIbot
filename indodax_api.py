import requests
import hashlib
import hmac
import time
import json
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

class IndodaxAPI:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key.encode('utf-8')
        self.public_api_url = "https://indodax.com/api/"
        self.private_api_url = "https://indodax.com/tapi/"

    def _private_request(self, method, params=None):
        if params is None:
            params = {}
        
        # Add nonce
        params['nonce'] = int(time.time() * 1000) 
        params['method'] = method

        post_data = self._urlencode(params)
        
        signature = hmac.new(self.secret_key, post_data.encode('utf-8'), hashlib.sha512).hexdigest()

        headers = {
            'Key': self.api_key,
            'Sign': signature,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            response = requests.post(self.private_api_url, headers=headers, data=post_data)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error during API request: {e}")
            return None

    def _public_request(self, endpoint):
        try:
            response = requests.get(f"{self.public_api_url}{endpoint}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error during public API request: {e}")
            return None

    def _urlencode(self, params):
        return '&'.join([f"{key}={value}" for key, value in params.items()])

    # --- Public API Endpoints ---
    def get_ticker(self, pair):
        return self._public_request(f"ticker/{pair}") # e.g., "btcidr"

    def get_trades(self, pair):
        return self._public_request(f"trades/{pair}") # e.g., "btcidr"

    # --- Private API Endpoints ---
    def get_info(self):
        return self._private_request("getInfo")

    def trade(self, pair, type, price=None, amount=None):
        # type can be 'buy' or 'sell'
        # For market orders, you might only need amount (IDR for buy, Crypto for sell)
        # For limit orders, you need both price and amount
        
        params = {
            'pair': pair,
            'type': type
        }
        if price:
            params['price'] = price
        if amount:
            params['amount'] = amount

        return self._private_request("trade", params)

    def get_order(self, pair, order_id):
        params = {
            'pair': pair,
            'order_id': order_id
        }
        return self._private_request("getOrder", params)

    def cancel_order(self, pair, order_id, type):
        # type can be 'buy' or 'sell'
        params = {
            'pair': pair,
            'order_id': order_id,
            'type': type
        }
        return self._private_request("cancelOrder", params)

# Example Usage (Save your API_KEY and SECRET_KEY in a .env file)
if __name__ == "__main__":
    API_KEY = os.getenv("INDODAX_API_KEY")
    SECRET_KEY = os.getenv("INDODAX_SECRET_KEY")

    if not API_KEY or not SECRET_KEY:
        print("Please set INDODAX_API_KEY and INDODAX_SECRET_KEY in your .env file.")
    else:
        indodax = IndodaxAPI(API_KEY, SECRET_KEY)

        # Get balance info
        info = indodax.get_info()
        if info and info['success'] == 1:
            print("Balance Info:", json.dumps(info['return']['balance'], indent=2))
        else:
            print("Failed to get balance info:", info)

        # Get BTC/IDR ticker (public)
        btcidr_ticker = indodax.get_ticker("btcidr")
        if btcidr_ticker:
            print("BTC/IDR Ticker:", json.dumps(btcidr_ticker, indent=2))
        else:
            print("Failed to get BTC/IDR ticker.")