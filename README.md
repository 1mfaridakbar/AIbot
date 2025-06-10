# Crypto Trading Bot Otomatis

Proyek ini bertujuan untuk mengembangkan aplikasi crypto trading bot otomatis yang andal menggunakan Python dan terintegrasi dengan Indodax API.

## Fitur Utama

-   **Dashboard:** Menampilkan saldo, keuntungan, dan metrik performa.
-   **AI untuk Rekomendasi & Analisis Pasar:** Menggunakan AI untuk analisis tren dan prediksi harga.
-   **Rekomendasi Trading:** Menampilkan aset kripto yang direkomendasikan berdasarkan analisis AI.
-   **Auto Trading:** Eksekusi perdagangan otomatis berdasarkan strategi yang telah ditentukan.

## Instalasi

1.  **Clone Repository:**
    ```bash
    git clone [https://github.com/nama_pengguna_anda/crypto_trading_bot.git](https://github.com/nama_pengguna_anda/crypto_trading_bot.git)
    cd crypto_trading_bot
    ```
    (Ganti `nama_pengguna_anda/crypto_trading_bot.git` dengan URL repo Anda setelah menginisialisasi Git.)

2.  **Buat Virtual Environment:**
    ```bash
    python3 -m venv venv
    ```

3.  **Aktifkan Virtual Environment:**
    * **macOS/Linux:**
        ```bash
        source venv/bin/activate
        ```
    * **Windows:**
        ```bash
        venv\Scripts\activate
        ```

4.  **Install Dependensi:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Konfigurasi Kunci API:**
    Buat file `.env` di root direktori proyek dan tambahkan kunci API Indodax Anda:
    ```
    INDODAX_API_KEY=YOUR_INDODAX_API_KEY
    INDODAX_SECRET_KEY=YOUR_INDODAX_SECRET_KEY
    ```

## Cara Menjalankan

### Menjalankan Dashboard Web

```bash
python app.py