"""
SpendSense AI — Pipeline Orchestrator
=======================================
The single function run_pipeline() connects everything:
  1. Validates the uploaded DataFrame
  2. Runs ML Layer (categorizer + anomaly detector)
  3. Runs all 4 LLM Agents on ML output
  4. Returns a single structured result dict ready for the dashboard

This is the only file that the backend (routes/user_routes.py) calls.
It isolates all pipeline complexity behind one clean function.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime

from ml.predict import run_ml_pipeline, models_are_trained
from agents.agent_runner import (
    run_categorization_agent,
    run_insight_agent,
    run_budget_advisor_agent,
    run_alert_agent
)
from config import CATEGORY_LABELS


# ─────────────────────────────────────────────────────────────────────────────
# Required Columns in Uploaded CSV
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {"date", "merchant", "amount"}
OPTIONAL_COLUMNS = {"description"}


def validate_dataframe(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Check that the uploaded CSV has all required columns.
    Returns (True, "") on success or (False, error_message) on failure.
    """
    missing = REQUIRED_COLUMNS - set(df.columns.str.lower())
    if missing:
        return False, f"Missing required columns: {', '.join(missing)}. " \
                      f"Required: date, merchant, amount"
    if len(df) == 0:
        return False, "The uploaded file is empty."
    if len(df) > 10000:
        return False, "File too large. Maximum 10,000 transactions per upload."
    return True, ""


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize column names to lowercase and ensure optional columns exist.
    """
    df.columns = df.columns.str.lower().str.strip()
    if "description" not in df.columns:
        df["description"] = ""
    df["merchant"]    = df["merchant"].fillna("Unknown").str.strip()
    df["description"] = df["description"].fillna("").str.strip()
    df["amount"]      = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["date"]        = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["amount"] > 0].reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(df: pd.DataFrame, filename: str = "upload.csv", progress_callback = None) -> dict:
    """
    Full ML + Agent pipeline for one uploaded CSV file.
    Accepts progress_callback(step, name, pct) for live stepper updates.
    """
    print(f"\n[Pipeline] Starting pipeline for: {filename}")

    def _notify(step, name, pct):
        if callable(progress_callback):
            try:
                progress_callback(step, name, pct)
            except Exception as e:
                print(f"[Pipeline] Progress error: {e}")

    # ── Step 1: Validate ──────────────────────────────────────────────────────
    _notify(1, "Validating CSV structure...", 10)
    valid, error = validate_dataframe(df)
    if not valid:
        return {"success": False, "error": error}

    df = normalize_columns(df)
    print(f"[Pipeline] Loaded {len(df)} valid transactions")

    # Assign temporary IDs for agent tracking
    df["transaction_id"] = [f"TXN{i+1:05d}" for i in range(len(df))]

    # ── Step 2–3: ML Layer ────────────────────────────────────────────────────
    if not models_are_trained():
        return {
            "success": False,
            "error": "ML models are not trained yet. "
                     "Run: python ml/train_categorizer.py && python ml/train_anomaly.py"
        }

    _notify(1, "Categorizing transactions (Random Forest + Agent 1)...", 25)
    print("[Pipeline] Running ML models...")
    df = run_ml_pipeline(df)
    print(f"[Pipeline] Categories predicted. Anomalies: {df['is_anomaly'].sum()}")

    # ── Step 4: Agent 1 — Categorization Refinement ───────────────────────────
    txns_for_agent = df[[
        "transaction_id", "merchant", "description",
        "predicted_category", "confidence"
    ]].to_dict("records")

    cat_corrections = run_categorization_agent(txns_for_agent)
    correction_map  = {c["transaction_id"]: c["final_category"]
                       for c in cat_corrections}

    df["final_category"] = df["transaction_id"].map(correction_map).fillna(
        df["predicted_category"]
    )

    # ── Step 5: Compute Summary Statistics ────────────────────────────────────
    _notify(2, "Detecting anomalies & evaluating risk (Isolation Forest)...", 50)
    category_totals = (
        df.groupby("final_category")["amount"]
        .sum()
        .round(2)
        .to_dict()
    )
    top_merchants = (
        df.groupby("merchant")["amount"]
        .sum()
        .nlargest(3)
        .index.tolist()
    )
    total_amount  = round(df["amount"].sum(), 2)
    anomaly_count = int(df["is_anomaly"].sum())

    try:
        dates  = pd.to_datetime(df["date"], errors="coerce").dropna()
        month  = dates.dt.to_period("M").value_counts().index[0].strftime("%B %Y")
    except Exception:
        month = datetime.now().strftime("%B %Y")

    summary = {
        "total_txns":      len(df),
        "total_amount":    total_amount,
        "anomaly_count":   anomaly_count,
        "category_totals": category_totals,
        "top_merchants":   top_merchants,
        "month":           month
    }

    # ── Step 6–8: Agents 2, 3 & 4 (Concurrent Parallel Execution) ─────────────
    _notify(3, "Synthesizing AI insights, budget tips & alerts in parallel...", 70)
    print("[Pipeline] Running Agents 2, 3 & 4 concurrently via ThreadPoolExecutor...")
    top_cat = max(category_totals, key=category_totals.get) if category_totals else ""
    advisor_payload = {
        "category_totals": category_totals,
        "total_amount":    total_amount,
        "anomaly_count":   anomaly_count,
        "top_category":    top_cat
    }
    anomaly_rows = df[df["is_anomaly"] == 1][[
        "merchant", "amount", "date", "anomaly_score"
    ]].to_dict("records")

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_insight = executor.submit(run_insight_agent, summary)
        future_budget  = executor.submit(run_budget_advisor_agent, advisor_payload)
        future_alert   = executor.submit(run_alert_agent, anomaly_rows)

        insight_text = future_insight.result()
        _notify(4, "Personalized budget tips & alerts finalized...", 90)
        budget_tips  = future_budget.result()
        alerts       = future_alert.result()

    # ── Step 9: Build final transaction list ──────────────────────────────────
    _notify(5, "Finalizing dashboard updates...", 98)
    transactions_out = df[[
        "transaction_id", "date", "merchant", "description",
        "amount", "predicted_category", "final_category",
        "confidence", "is_anomaly", "anomaly_score"
    ]].to_dict("records")

    for t in transactions_out:
        t["amount"]        = float(t["amount"])
        t["confidence"]    = float(t["confidence"])
        t["anomaly_score"] = float(t["anomaly_score"])
        t["is_anomaly"]    = int(t["is_anomaly"])

    print(f"[Pipeline] ✅ Pipeline complete. Transactions: {len(transactions_out)}, Anomalies: {anomaly_count}")
    _notify(5, "Complete!", 100)

    return {
        "success":      True,
        "transactions": transactions_out,
        "summary":      summary,
        "insight_text": insight_text,
        "budget_tips":  budget_tips,
        "alerts":       alerts
    }
