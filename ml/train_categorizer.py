"""
SpendSense AI — Transaction Categorizer Training
==================================================
Run once to train and save the RandomForest classifier.
  python ml/train_categorizer.py

What happens here (step by step):
  1. Load data/transactions.csv
  2. Build TF-IDF + numeric feature matrix (X)
  3. Extract category labels (y)
  4. Split: 80% train / 20% test
  5. Train RandomForestClassifier
  6. Print classification report
  7. Save model + vectorizer to ml/models/

Class Labels (8 categories):
  Dining, Groceries, Bills, Shopping, Travel, Health, Entertainment, Transfer

Why Random Forest?
  - Handles mixed features (text TF-IDF + numerics) well
  - Robust to outliers and noisy labels
  - Returns probability scores (predict_proba) for confidence
  - Fast to train on 2000 rows; fast at inference
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.preprocessing import LabelEncoder

from ml.feature_engineering import fit_vectorizer, build_categorizer_features
from config import TRANSACTIONS_CSV, CATEGORIZER_PATH, VECTORIZER_PATH, MODEL_DIR, CATEGORY_LABELS


def train_categorizer():
    print("=" * 65)
    print("  SpendSense AI — Training Transaction Categorizer")
    print("=" * 65)

    # ── Step 1: Load data ─────────────────────────────────────────────────────
    print(f"\n[Step 1] Loading training data from: {TRANSACTIONS_CSV}")
    if not os.path.exists(TRANSACTIONS_CSV):
        print("ERROR: transactions.csv not found. Run: python data/generate_data.py")
        return

    df = pd.read_csv(TRANSACTIONS_CSV)
    print(f"         Loaded {len(df)} rows × {len(df.columns)} columns")
    print(f"         Category distribution:")
    for cat, count in df["category"].value_counts().items():
        pct = count / len(df) * 100
        print(f"           {cat:<15} {count:>4} rows  ({pct:.1f}%)")

    # ── Step 2: Feature Engineering ───────────────────────────────────────────
    print(f"\n[Step 2] Building TF-IDF + numeric features...")
    vectorizer = fit_vectorizer(df)
    X = build_categorizer_features(df, vectorizer)
    print(f"         Feature matrix shape: {X.shape}")
    print(f"         TF-IDF vocabulary size: {len(vectorizer.vocabulary_)}")

    # ── Step 3: Labels ────────────────────────────────────────────────────────
    print(f"\n[Step 3] Encoding {len(CATEGORY_LABELS)} class labels...")
    y = df["category"].values
    print(f"         Labels: {CATEGORY_LABELS}")

    # ── Step 4: Train / Test Split ────────────────────────────────────────────
    print(f"\n[Step 4] Splitting data: 80% train / 20% test...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"         Train size: {X_train.shape[0]} rows")
    print(f"         Test size:  {X_test.shape[0]} rows")

    # ── Step 5: Train Model ───────────────────────────────────────────────────
    print(f"\n[Step 5] Training RandomForestClassifier...")
    print(f"         n_estimators=200, max_depth=None, min_samples_split=2")
    model = RandomForestClassifier(
        n_estimators=200,     # 200 trees — more trees = more accurate, slower
        max_depth=None,       # trees grow until pure leaves
        min_samples_split=2,
        min_samples_leaf=1,
        max_features="sqrt",  # each tree sees sqrt(n_features) features
        random_state=42,
        n_jobs=-1,            # use all CPU cores
        class_weight="balanced"  # handle any class imbalance
    )
    model.fit(X_train, y_train)
    print(f"         Training complete.")

    # ── Step 6: Evaluate ──────────────────────────────────────────────────────
    print(f"\n[Step 6] Evaluating on test set...")
    y_pred  = model.predict(X_test)
    acc     = accuracy_score(y_test, y_pred)
    print(f"\n         Overall Accuracy: {acc:.4f} ({acc*100:.1f}%)\n")
    print("         Classification Report:")
    print("         " + "-" * 55)
    report = classification_report(y_test, y_pred, target_names=CATEGORY_LABELS,
                                   zero_division=0)
    for line in report.split("\n"):
        print(f"         {line}")

    # Cross-validation score (5-fold)
    print(f"\n         5-Fold Cross Validation...")
    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring="accuracy", n_jobs=-1)
    print(f"         CV Scores: {cv_scores.round(3)}")
    print(f"         CV Mean:   {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # ── Step 7: Save Model + Vectorizer ───────────────────────────────────────
    print(f"\n[Step 7] Saving model artifacts...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model,      CATEGORIZER_PATH)
    joblib.dump(vectorizer, VECTORIZER_PATH)
    print(f"         Categorizer  → {CATEGORIZER_PATH}")
    print(f"         Vectorizer   → {VECTORIZER_PATH}")

    print("\n✅ Categorizer training complete!")
    print("   Next: python ml/train_anomaly.py")


if __name__ == "__main__":
    train_categorizer()
