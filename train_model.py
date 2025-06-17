# file: train_model.py

import pandas as pd
from database import DatabaseManager
import config
import joblib # Untuk menyimpan model AI kita

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

def train_model():
    """
    Fungsi lengkap untuk mengambil data, membuat target, melatih model,
    mengevaluasi, dan menyimpannya.
    """
    print("--- Starting Model Training Process ---")
    
    db = DatabaseManager()
    pair = config.PAIR_TO_TRADE

    # 1. Ambil Data Fitur dari Database
    # -----------------------------------
    print("Loading feature data from database...")
    feature_data_rows = db.get_feature_data(pair)
    db.close_connection()

    if len(feature_data_rows) < 100:
        print(f"WARNING: Only {len(feature_data_rows)} data points available. Model performance will be poor.")
        print("Please collect more data before training a serious model.")
        if len(feature_data_rows) < 10:
             print("Not enough data to even attempt training. Exiting.")
             return

    df = pd.DataFrame([dict(row) for row in feature_data_rows])
    df.drop(columns=['id', 'pair'], inplace=True) # Hapus kolom yang tidak relevan untuk training
    
    # 2. Membuat "Target" (Apa yang ingin kita prediksi)
    # ----------------------------------------------------
    # Target kita sederhana: kita akan memberi label '1' (artinya 'Beli') jika
    # dalam 5 candle ke depan, harga 'high' pernah naik setidaknya 1.5% dari harga 'close' saat ini.
    # Jika tidak, kita beri label '0' (artinya 'Jangan Beli').
    print("Creating target variable...")
    
    future_candles = 5
    profit_target_percentage = 1.5
    
    df['target'] = 0 # Default target adalah 0
    for i in range(len(df)):
        current_price = df.loc[i, 'close']
        # Look into the future from the current candle
        future_window = df.iloc[i + 1 : i + 1 + future_candles]
        if not future_window.empty:
            max_future_high = future_window['high'].max()
            if max_future_high >= current_price * (1 + profit_target_percentage / 100):
                df.loc[i, 'target'] = 1 # Jika target profit tercapai, beri label 1
    
    # 3. Persiapan Data untuk Training
    # ---------------------------------
    print("Preparing data for training...")
    
    # Hapus baris yang mungkin punya nilai NaN setelah proses di atas
    df.dropna(inplace=True) 
    
    # Pisahkan antara Fitur (X) dan Target (y)
    features = [col for col in df.columns if col not in ['timestamp', 'target']]
    X = df[features]
    y = df['target']
    
    if len(X) < 10:
        print("Not enough valid data rows after creating targets. Exiting.")
        return

    # Bagi data menjadi data latih (80%) dan data tes (20%)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    print(f"Training data size: {len(X_train)} rows")
    print(f"Testing data size: {len(X_test)} rows")
    
    # 4. Melatih Model AI
    # ---------------------
    print("Training the RandomForestClassifier model...")
    # RandomForest adalah model yang kuat dan bagus untuk pemula
    model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    model.fit(X_train, y_train)

    # 5. Mengevaluasi Kinerja Model
    # --------------------------------
    print("\n--- Model Evaluation ---")
    y_pred = model.predict(X_test)
    
    accuracy = accuracy_score(y_test, y_pred)
    print(f"Model Accuracy: {accuracy:.2%}")
    print("\nClassification Report:")
    # Laporan ini memberikan detail performa untuk setiap kelas (0 dan 1)
    print(classification_report(y_test, y_pred))

    # 6. Menyimpan Model yang Sudah Dilatih
    # -------------------------------------
    print("Saving the trained model to 'trading_model.pkl'...")
    joblib.dump(model, 'trading_model.pkl')
    print("Model saved successfully.")
    print("\n--- Model Training Process Finished ---")


if __name__ == "__main__":
    train_model()