# file: notifier.py

import requests
import config

def send_notification(message):
    """Mengirim pesan notifikasi ke Telegram."""
    if not config.ENABLE_NOTIFICATIONS:
        return

    bot_token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not bot_token or not chat_id or bot_token == "GANTI_DENGAN_TOKEN_ANDA":
        print("Peringatan: Token/Chat ID Telegram belum diatur. Notifikasi dilewati.")
        return

    # URL untuk mengirim pesan melalui API Telegram
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Data yang akan dikirim
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown' # Mengizinkan format tebal, miring, dll.
    }

    try:
        response = requests.post(url, data=payload, timeout=5)
        if response.status_code != 200:
            print(f"Error mengirim notifikasi Telegram: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error koneksi saat mengirim notifikasi: {e}")

# Contoh penggunaan (bisa dihapus nanti)
if __name__ == "__main__":
    send_notification("✅ *Tes Notifikasi*:\nBot trading Anda berhasil terhubung!")