"""
SpendSense AI — Feature Engineering
=====================================
Converts raw transaction text (merchant + description) into
numeric feature vectors that ML models can process.

Two feature sets are built:
  1. Categorizer features — TF-IDF text + numeric (amount, day, weekend)
  2. Anomaly features     — numeric only (amount stats, z-score, rolling spend)

Why TF-IDF?
  A merchant name like "Zomato" is just a string.
  TF-IDF converts it into a vector of numbers where each dimension
  represents the "importance" of a word relative to all documents.
  "Zomato" will score high in Dining-related rows and near-zero elsewhere.
"""

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse import hstack, csr_matrix
import re


# ─────────────────────────────────────────────────────────────────────────────
# Text Preprocessing
# ─────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Normalize merchant + description text for TF-IDF:
      • Lowercase everything
      • Remove special characters (keep only letters/numbers/spaces)
      • Collapse multiple spaces
    """
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_text_column(df: pd.DataFrame) -> pd.Series:
    """
    Combine merchant and description into one text string per row.
    Example: merchant="Zomato", description="food order"
             → "zomato food order"
    """
    merchant    = df["merchant"].fillna("").apply(clean_text)
    description = df["description"].fillna("").apply(clean_text)
    return merchant + " " + description


# ─────────────────────────────────────────────────────────────────────────────
# Categorizer Feature Builder
# ─────────────────────────────────────────────────────────────────────────────

def fit_vectorizer(df: pd.DataFrame) -> TfidfVectorizer:
    """
    Fit a TF-IDF vectorizer on the training corpus.
    Parameters:
      max_features=500  → keep only the 500 most informative words
      ngram_range=(1,2) → include single words AND two-word pairs
                          e.g. "food" and "food delivery" as separate features
      min_df=2          → ignore words that appear in fewer than 2 rows
    Returns the fitted vectorizer (save this with joblib).
    """
    corpus = build_text_column(df)
    vectorizer = TfidfVectorizer(
        max_features=500,
        ngram_range=(1, 2),
        min_df=2,
        sublinear_tf=True   # apply log normalization to term frequencies
    )
    vectorizer.fit(corpus)
    return vectorizer


def build_categorizer_features(df: pd.DataFrame, vectorizer: TfidfVectorizer):
    """
    Build the full feature matrix for the categorizer.

    Features:
      [0:500] TF-IDF text features (sparse)
      [500]   amount (log-scaled — log1p avoids log(0))
      [501]   day_of_week (0=Monday … 6=Sunday)
      [502]   is_weekend (1 if Saturday or Sunday)
      [503]   amount_bin (0=low, 1=mid, 2=high — relative to dataset)

    Returns: scipy sparse matrix (shape: n_rows × 504)
    """
    # Text features
    corpus        = build_text_column(df)
    text_features = vectorizer.transform(corpus)

    # Parse dates
    dates = pd.to_datetime(df["date"], errors="coerce")

    # Numeric features (must become sparse matrix for hstack)
    amounts       = np.log1p(df["amount"].fillna(0).values).reshape(-1, 1)
    day_of_week   = dates.dt.dayofweek.fillna(0).values.reshape(-1, 1)
    is_weekend    = (dates.dt.dayofweek >= 5).astype(int).values.reshape(-1, 1)
    amount_bin    = pd.cut(
        df["amount"].fillna(0),
        bins=3, labels=[0, 1, 2]
    ).astype(float).values.reshape(-1, 1)

    numeric = np.hstack([amounts, day_of_week, is_weekend, amount_bin])
    numeric_sparse = csr_matrix(numeric)

    return hstack([text_features, numeric_sparse])


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detector Feature Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_anomaly_features(df: pd.DataFrame,
                           category_stats: dict = None) -> np.ndarray:
    """
    Build numeric feature matrix for the Isolation Forest anomaly detector.

    Features:
      [0] log_amount           — log-scaled transaction amount
      [1] amount_zscore        — how many std devs above category mean
      [2] day_of_week          — 0–6
      [3] is_weekend           — 0 or 1
      [4] rolling_7d_fraction  — fraction of 7-day budget spent (if available)

    category_stats is a dict: {category: {"mean": x, "std": y}}
    If not provided, it's computed from df itself (training mode).

    Returns: numpy array (shape: n_rows × 5)
    """
    df = df.copy()
    df["amount"]   = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    dates          = pd.to_datetime(df["date"], errors="coerce")

    df["log_amount"]  = np.log1p(df["amount"])
    df["day_of_week"] = dates.dt.dayofweek.fillna(0)
    df["is_weekend"]  = (dates.dt.dayofweek >= 5).astype(int)

    # Compute category z-score
    cat_col = "category" if "category" in df.columns else "predicted_category"
    if cat_col not in df.columns:
        df["amount_zscore"] = 0.0
    else:
        if category_stats is None:
            category_stats = (
                df.groupby(cat_col)["amount"]
                .agg(["mean", "std"])
                .fillna(0)
                .to_dict("index")
            )
        def zscore(row):
            stats = category_stats.get(row.get(cat_col, ""), {"mean": 0, "std": 1})
            std   = stats.get("std", 1) or 1
            return (row["amount"] - stats.get("mean", 0)) / std
        df["amount_zscore"] = df.apply(zscore, axis=1)

    # Rolling 7-day spend fraction (simplified: amount / 7d rolling sum)
    df_sorted = df.sort_values("date") if "date" in df.columns else df
    df["rolling_7d"] = (
        df_sorted["amount"]
        .rolling(window=7, min_periods=1)
        .sum()
        .values
    )
    df["rolling_fraction"] = df["amount"] / (df["rolling_7d"] + 1)

    feature_cols = [
        "log_amount", "amount_zscore", "day_of_week",
        "is_weekend", "rolling_fraction"
    ]
    return df[feature_cols].fillna(0).values, category_stats
