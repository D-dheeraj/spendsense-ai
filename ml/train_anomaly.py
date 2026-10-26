"""
SpendSense AI — Anomaly Detector Training
==========================================
Run once to train and save the Isolation Forest anomaly detector.
  python ml/train_anomaly.py

What happens here (step by step):
  1. Load data/transactions.csv
  2. Build numeric feature matrix for anomaly detection
  3. Train IsolationForest
  4. Evaluate: check how well it identifies known anomalies (is_anomaly=1)
  5. Save model + category_stats to ml/models/

Why Isolation Forest?
  - Unsupervised: doesn't need labeled anomaly data to learn
  - Works by isolating points — anomalies are isolated faster than normal points
  - Produces a decision score: more negative = more anomalous
  - Low memory and fast inference — suitable for real-time transaction checking
  - contamination parameter tells it what fraction of data to treat as anomalous
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

from ml.feature_engineering import build_anomaly_features
from config import (TRANSACTIONS_CSV, ANOMALY_MODEL_PATH,
                    MODEL_DIR, ANOMALY_CONTAMINATION)


def train_anomaly_detector():
    print("=" * 65)
    print("  SpendSense AI — Training Anomaly Detector")
    print("=" * 65)

    # ── Step 1: Load data ─────────────────────────────────────────────────────
    print(f"\n[Step 1] Loading training data from: {TRANSACTIONS_CSV}")
    if not os.path.exists(TRANSACTIONS_CSV):
        print("ERROR: transactions.csv not found. Run: python data/generate_data.py")
        return

    df = pd.read_csv(TRANSACTIONS_CSV)
    print(f"         Loaded {len(df)} rows")
    print(f"         Known anomalies in data: {df['is_anomaly'].sum()} "
          f"({df['is_anomaly'].mean()*100:.1f}%)")

    # ── Step 2: Build Anomaly Features ───────────────────────────────────────
    print(f"\n[Step 2] Building anomaly detection features...")
    print(f"         Features: log_amount, amount_zscore, day_of_week, "
          f"is_weekend, rolling_fraction")
    X, category_stats = build_anomaly_features(df)
    print(f"         Feature matrix shape: {X.shape}")

    # True labels for evaluation
    y_true = df["is_anomaly"].values

    # ── Step 3: Train IsolationForest ─────────────────────────────────────────
    print(f"\n[Step 3] Training IsolationForest...")
    print(f"         n_estimators=200, contamination={ANOMALY_CONTAMINATION}")
    model = IsolationForest(
        n_estimators=200,
        contamination=ANOMALY_CONTAMINATION,   # expected fraction of anomalies
        max_samples="auto",
        random_state=42,
        n_jobs=-1
    )
    model.fit(X)
    print(f"         Training complete.")

    # ── Step 4: Evaluate ──────────────────────────────────────────────────────
    print(f"\n[Step 4] Evaluating anomaly detection...")
    raw_predictions = model.predict(X)          # -1 = anomaly, 1 = normal
    scores          = model.decision_function(X) # lower = more anomalous

    # Convert -1/1 to 1/0 (matching is_anomaly column)
    y_pred = (raw_predictions == -1).astype(int)

    total_flagged = y_pred.sum()
    print(f"         Transactions flagged as anomalies: {total_flagged} "
          f"({total_flagged/len(df)*100:.1f}%)")

    # Evaluate against ground-truth labels
    print(f"\n         Classification Report (vs ground-truth is_anomaly):")
    print("         " + "-" * 45)
    report = classification_report(y_true, y_pred,
                                   target_names=["Normal", "Anomaly"],
                                   zero_division=0)
    for line in report.split("\n"):
        print(f"         {line}")

    # AUC score using raw anomaly scores
    try:
        auc = roc_auc_score(y_true, -scores)  # negate: lower score = more anomalous
        print(f"         ROC-AUC Score: {auc:.4f}")
    except Exception:
        print(f"         ROC-AUC: (could not compute)")

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    print(f"\n         Confusion Matrix:")
    print(f"                         Predicted Normal  Predicted Anomaly")
    print(f"         Actual Normal:  {cm[0][0]:>16}  {cm[0][1]:>17}")
    print(f"         Actual Anomaly: {cm[1][0]:>16}  {cm[1][1]:>17}")

    # ── Step 5: Save Model ────────────────────────────────────────────────────
    print(f"\n[Step 5] Saving model artifacts...")
    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(model, ANOMALY_MODEL_PATH)
    # Also save category stats for z-score computation at inference time
    stats_path = os.path.join(MODEL_DIR, "category_stats.pkl")
    joblib.dump(category_stats, stats_path)

    print(f"         Anomaly Detector → {ANOMALY_MODEL_PATH}")
    print(f"         Category Stats   → {stats_path}")

    print("\n✅ Anomaly detector training complete!")
    print("   Next: python ml/predict.py  (or start the app: python app.py)")


if __name__ == "__main__":
    train_anomaly_detector()
