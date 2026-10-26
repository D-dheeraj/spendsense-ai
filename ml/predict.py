"""
SpendSense AI — ML Inference (Predict)
========================================
This module loads the saved models and runs predictions on new data.
Called by agents/orchestrator.py during the upload pipeline.

Two main functions:
  categorize_transactions(df) → adds predicted_category + confidence columns
  detect_anomalies(df)        → adds is_anomaly + anomaly_score columns

Models are loaded once (lazy-loaded on first call) and cached in memory
for subsequent requests to avoid repeated disk reads.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import joblib

from ml.feature_engineering import build_categorizer_features, build_anomaly_features
from config import (CATEGORIZER_PATH, VECTORIZER_PATH,
                    ANOMALY_MODEL_PATH, MODEL_DIR, LOW_CONFIDENCE_THRESHOLD)


# ─────────────────────────────────────────────────────────────────────────────
# Model Cache (lazy-loaded — loaded once on first prediction call)
# ─────────────────────────────────────────────────────────────────────────────

_categorizer    = None
_vectorizer     = None
_anomaly_model  = None
_category_stats = None


def _load_categorizer():
    global _categorizer, _vectorizer
    if _categorizer is None:
        if not os.path.exists(CATEGORIZER_PATH):
            raise FileNotFoundError(
                f"Categorizer not found at {CATEGORIZER_PATH}. "
                "Run: python ml/train_categorizer.py"
            )
        _categorizer = joblib.load(CATEGORIZER_PATH)
        _vectorizer  = joblib.load(VECTORIZER_PATH)
    return _categorizer, _vectorizer


def _load_anomaly_model():
    global _anomaly_model, _category_stats
    if _anomaly_model is None:
        if not os.path.exists(ANOMALY_MODEL_PATH):
            raise FileNotFoundError(
                f"Anomaly model not found at {ANOMALY_MODEL_PATH}. "
                "Run: python ml/train_anomaly.py"
            )
        _anomaly_model  = joblib.load(ANOMALY_MODEL_PATH)
        stats_path      = os.path.join(MODEL_DIR, "category_stats.pkl")
        _category_stats = joblib.load(stats_path) if os.path.exists(stats_path) else None
    return _anomaly_model, _category_stats


def models_are_trained() -> bool:
    """Check whether both model files exist on disk."""
    return (
        os.path.exists(CATEGORIZER_PATH) and
        os.path.exists(ANOMALY_MODEL_PATH)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Categorization
# ─────────────────────────────────────────────────────────────────────────────

def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the trained RandomForest categorizer on a DataFrame of transactions.

    Input columns required: merchant, description, amount, date
    Adds columns:
      predicted_category — the model's best guess (e.g. "Dining")
      confidence         — probability of the predicted class (0.0–1.0)
      low_confidence     — True if confidence < LOW_CONFIDENCE_THRESHOLD

    Low-confidence predictions are later reviewed by Agent 1
    (Categorization Agent) which may reassign the label.
    """
    model, vectorizer = _load_categorizer()

    df = df.copy()
    df["merchant"]    = df.get("merchant", pd.Series([""] * len(df))).fillna("")
    df["description"] = df.get("description", pd.Series([""] * len(df))).fillna("")
    df["amount"]      = pd.to_numeric(df.get("amount", pd.Series([0] * len(df))), errors="coerce").fillna(0)

    # Build feature matrix
    X = build_categorizer_features(df, vectorizer)

    # Predict class and probabilities
    predicted_labels = model.predict(X)
    probabilities    = model.predict_proba(X)     # shape: (n_rows, n_classes)
    confidence_scores = probabilities.max(axis=1)

    df["predicted_category"] = predicted_labels
    df["confidence"]         = confidence_scores.round(4)
    df["low_confidence"]     = df["confidence"] < LOW_CONFIDENCE_THRESHOLD

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the trained IsolationForest anomaly detector on a DataFrame.

    Input columns required: amount, date, (optionally: predicted_category)
    Adds columns:
      is_anomaly    — 1 if flagged as anomaly, 0 if normal
      anomaly_score — raw model score (more negative = more suspicious)

    The anomaly_score is used by Agent 4 (Alert Agent) to prioritize
    which anomalies to include in the alert feed.
    """
    model, cat_stats = _load_anomaly_model()

    df = df.copy()
    df["amount"] = pd.to_numeric(df.get("amount", pd.Series([0] * len(df))), errors="coerce").fillna(0)

    # Build numeric feature matrix
    X, _ = build_anomaly_features(df, category_stats=cat_stats)

    # Predict: -1 = anomaly, 1 = normal
    raw_preds     = model.predict(X)
    scores        = model.decision_function(X)

    df["is_anomaly"]    = (raw_preds == -1).astype(int)
    df["anomaly_score"] = scores.round(4)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Combined Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_ml_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run both ML models sequentially on the input DataFrame.
    Returns a DataFrame with all prediction columns added.
    """
    df = categorize_transactions(df)
    df = detect_anomalies(df)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Quick Test (run directly to verify models work)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import SAMPLE_CSV
    print("Testing ML pipeline on sample_upload.csv...")
    if not os.path.exists(SAMPLE_CSV):
        print(f"Sample file not found: {SAMPLE_CSV}")
        print("Run: python data/generate_data.py")
    else:
        df = pd.read_csv(SAMPLE_CSV)
        result = run_ml_pipeline(df)
        print("\nSample predictions:")
        print(result[["merchant", "amount", "predicted_category",
                       "confidence", "is_anomaly", "anomaly_score"]].head(10).to_string())
        print(f"\nTotal anomalies flagged: {result['is_anomaly'].sum()} / {len(result)}")
