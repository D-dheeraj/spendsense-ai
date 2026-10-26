"""
SpendSense AI — Financial Analytics Engine
============================================
Handles:
  1. KPI metrics & Month-over-Month calculations
  2. Financial Health Score (0-100 rule-based engine)
  3. Spend Forecasting via Linear Regression
  4. Pandas data aggregation for Chat with Data
"""

import pandas as pd
import numpy as np
from datetime import datetime
from database import get_all_user_transactions, get_user_batches


# ─────────────────────────────────────────────────────────────────────────────
# 1. KPI Calculations (Animated Cards)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_kpis(user_id: int) -> dict:
    """
    Calculate high-level KPI metrics for the dashboard cards:
      - Total Spend
      - Total Transactions
      - Top Category (name + amount + share %)
      - Anomalies (count + share %)
      - Month-over-Month change % (+/- with direction)
    """
    txns = get_all_user_transactions(user_id)
    if not txns:
        return {
            "has_data": False,
            "total_spend": 0,
            "total_txns": 0,
            "top_category": {"name": "—", "amount": 0, "pct": 0},
            "anomalies": {"count": 0, "pct": 0},
            "monthly_change": {
                "has_comparison": False,
                "pct": 0.0,
                "direction": "flat",
                "label": "First upload"
            }
        }

    df = pd.DataFrame(txns)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["is_anomaly"] = pd.to_numeric(df["is_anomaly"], errors="coerce").fillna(0).astype(int)

    total_spend = float(df["amount"].sum())
    total_txns  = len(df)

    # Top Category
    cat_spend = df.groupby("final_category")["amount"].sum()
    if not cat_spend.empty:
        top_cat_name = str(cat_spend.idxmax())
        top_cat_amt  = float(cat_spend.max())
        top_cat_pct  = round((top_cat_amt / total_spend * 100), 1) if total_spend > 0 else 0
    else:
        top_cat_name = "—"
        top_cat_amt  = 0.0
        top_cat_pct  = 0.0

    # Anomalies
    anomaly_count = int(df["is_anomaly"].sum())
    anomaly_pct   = round((anomaly_count / total_txns * 100), 1) if total_txns > 0 else 0

    # Month-over-Month calculation
    monthly_change = {
        "has_comparison": False,
        "pct": 0.0,
        "direction": "flat",
        "label": "First month"
    }

    try:
        df["dt"] = pd.to_datetime(df["date"], errors="coerce")
        valid_dates = df.dropna(subset=["dt"])
        if not valid_dates.empty:
            valid_dates["month_period"] = valid_dates["dt"].dt.to_period("M")
            monthly_totals = valid_dates.groupby("month_period")["amount"].sum().sort_index()

            if len(monthly_totals) >= 2:
                curr_month = float(monthly_totals.iloc[-1])
                prev_month = float(monthly_totals.iloc[-2])
                if prev_month > 0:
                    diff_pct = round(((curr_month - prev_month) / prev_month) * 100, 1)
                    direction = "up" if diff_pct > 0 else ("down" if diff_pct < 0 else "flat")
                    sign = "+" if diff_pct > 0 else ""
                    monthly_change = {
                        "has_comparison": True,
                        "pct": abs(diff_pct),
                        "signed_pct": f"{sign}{diff_pct}%",
                        "direction": direction,
                        "current_month": curr_month,
                        "prev_month": prev_month,
                        "label": f"{sign}{diff_pct}% vs last month"
                    }
    except Exception as e:
        print(f"[Analytics] MoM calculation error: {e}")

    # Fallback: if single month in dates, check if multiple upload batches exist
    if not monthly_change["has_comparison"]:
        batches = get_user_batches(user_id)
        if len(batches) >= 2:
            curr_amt = float(batches[0].get("total_amount", 0))
            prev_amt = float(batches[1].get("total_amount", 0))
            if prev_amt > 0:
                diff_pct = round(((curr_amt - prev_amt) / prev_amt) * 100, 1)
                direction = "up" if diff_pct > 0 else ("down" if diff_pct < 0 else "flat")
                sign = "+" if diff_pct > 0 else ""
                monthly_change = {
                    "has_comparison": True,
                    "pct": abs(diff_pct),
                    "signed_pct": f"{sign}{diff_pct}%",
                    "direction": direction,
                    "label": f"{sign}{diff_pct}% vs previous batch"
                }

    return {
        "has_data": True,
        "total_spend": round(total_spend, 2),
        "total_txns": total_txns,
        "top_category": {
            "name": top_cat_name,
            "amount": round(top_cat_amt, 2),
            "pct": top_cat_pct
        },
        "anomalies": {
            "count": anomaly_count,
            "pct": anomaly_pct
        },
        "monthly_change": monthly_change
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Financial Health Score (0–100 Gauge)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_health_score(user_id: int) -> dict:
    """
    Computes a 0–100 Financial Health Score based on 4 weighted pillars:
      1. Discretionary share (30 pts): Dining + Shopping + Entertainment % of total.
      2. Spending stability (25 pts): Standard deviation / Mean of periods.
      3. Anomaly ratio (25 pts): Anomalies / Total transactions.
      4. Trend (20 pts): Month-over-month growth rate.
    """
    txns = get_all_user_transactions(user_id)
    if not txns:
        return {
            "has_data": False,
            "score": 0,
            "label": "No Data",
            "color": "#6b7280",
            "explanation": "Upload your transaction statements to generate a financial health score."
        }

    df = pd.DataFrame(txns)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["is_anomaly"] = pd.to_numeric(df["is_anomaly"], errors="coerce").fillna(0).astype(int)

    total_spend = float(df["amount"].sum())
    total_txns  = len(df)
    if total_spend <= 0 or total_txns == 0:
        return {
            "has_data": False,
            "score": 50,
            "label": "Fair",
            "color": "#f59e0b",
            "explanation": "Insufficient transaction volume to calculate health score."
        }

    # ── Pillar 1: Discretionary Share (Weight 30) ──────────────────────────────
    discretionary_cats = {"Dining", "Shopping", "Entertainment"}
    disc_mask  = df["final_category"].isin(discretionary_cats)
    disc_spend = float(df[disc_mask]["amount"].sum())
    disc_ratio = disc_spend / total_spend  # 0.0 to 1.0

    # <= 20% gives full 30 pts, >= 60% gives minimum 5 pts
    if disc_ratio <= 0.20:
        score_disc = 30.0
    elif disc_ratio >= 0.60:
        score_disc = 5.0
    else:
        score_disc = 30.0 - ((disc_ratio - 0.20) / 0.40) * 25.0
    score_disc = max(5.0, min(30.0, score_disc))

    # ── Pillar 2: Spending Stability (Weight 25) ──────────────────────────────
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    valid_dates = df.dropna(subset=["dt"]).copy()
    if not valid_dates.empty and valid_dates["dt"].dt.to_period("M").nunique() > 1:
        # Multiple months -> calculate CV of monthly spends
        monthly = valid_dates.groupby(valid_dates["dt"].dt.to_period("M"))["amount"].sum()
        mean_s  = monthly.mean()
        std_s   = monthly.std()
        cv = (std_s / mean_s) if mean_s > 0 else 0.0
    elif not valid_dates.empty:
        # Single month -> calculate CV of weekly or daily active spend
        daily = valid_dates.groupby(valid_dates["dt"].dt.date)["amount"].sum()
        mean_s = daily.mean()
        std_s  = daily.std()
        cv = (std_s / mean_s) if mean_s > 0 else 0.0
    else:
        cv = 0.35

    # cv <= 0.20 -> 25 pts, cv >= 0.80 -> 5 pts
    if cv <= 0.20:
        score_stability = 25.0
    elif cv >= 0.80:
        score_stability = 5.0
    else:
        score_stability = 25.0 - ((cv - 0.20) / 0.60) * 20.0
    score_stability = max(5.0, min(25.0, score_stability))

    # ── Pillar 3: Anomaly Ratio (Weight 25) ───────────────────────────────────
    anomaly_count = int(df["is_anomaly"].sum())
    anomaly_ratio = anomaly_count / total_txns

    # ratio == 0 -> 25 pts, ratio >= 0.15 -> 0 pts
    if anomaly_ratio == 0:
        score_anomaly = 25.0
    elif anomaly_ratio >= 0.15:
        score_anomaly = 0.0
    else:
        score_anomaly = 25.0 * (1.0 - (anomaly_ratio / 0.15))
    score_anomaly = max(0.0, min(25.0, score_anomaly))

    # ── Pillar 4: Trend / MoM (Weight 20) ──────────────────────────────────────
    kpi = calculate_kpis(user_id)
    mom = kpi.get("monthly_change", {})
    if mom.get("has_comparison"):
        pct = mom["pct"] if mom["direction"] == "up" else -mom["pct"]
        # If spend decreased (pct <= 0) -> 20 pts. If spend increased by >= 30% -> 5 pts
        if pct <= 0:
            score_trend = 20.0
        elif pct >= 30:
            score_trend = 5.0
        else:
            score_trend = 20.0 - (pct / 30.0) * 15.0
    else:
        # Default baseline score for initial upload
        score_trend = 16.0
    score_trend = max(5.0, min(20.0, score_trend))

    # ── Final Score & Classification ──────────────────────────────────────────
    total_score = int(round(score_disc + score_stability + score_anomaly + score_trend))
    total_score = max(0, min(100, total_score))

    if total_score >= 85:
        label = "Excellent"
        color = "#10b981"  # Emerald
    elif total_score >= 65:
        label = "Good"
        color = "#3b82f6"  # Blue
    elif total_score >= 45:
        label = "Fair"
        color = "#f59e0b"  # Amber
    else:
        label = "Poor"
        color = "#ef4444"  # Red

    # 1-line explanation
    disc_pct_str = f"{disc_ratio * 100:.0f}%"
    if anomaly_count > 0:
        anomaly_note = f", but {anomaly_count} flagged anomalies lowered the score"
    else:
        anomaly_note = " with zero detected anomalies"

    explanation = (
        f"{label} score ({total_score}/100): Discretionary spend is at {disc_pct_str}"
        f"{anomaly_note}."
    )

    return {
        "has_data": True,
        "score": total_score,
        "label": label,
        "color": color,
        "explanation": explanation,
        "breakdown": {
            "discretionary_score": round(score_disc, 1),
            "discretionary_max": 30,
            "discretionary_pct": round(disc_ratio * 100, 1),
            "stability_score": round(score_stability, 1),
            "stability_max": 25,
            "anomaly_score": round(score_anomaly, 1),
            "anomaly_max": 25,
            "anomaly_count": anomaly_count,
            "trend_score": round(score_trend, 1),
            "trend_max": 20
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Spend Forecasting (Linear Regression)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_forecast(user_id: int) -> dict:
    """
    Predict next month's total spend using Linear Regression on monthly totals.
    Rule: Requires at least 3 months of data. If less, returns has_enough_data=False.
    """
    txns = get_all_user_transactions(user_id)
    if not txns:
        return {
            "has_enough_data": False,
            "message": "Upload transactions to enable spend forecasting."
        }

    df = pd.DataFrame(txns)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["dt"])

    if df.empty:
        return {
            "has_enough_data": False,
            "message": "No valid transaction dates found."
        }

    df["month"] = df["dt"].dt.to_period("M")
    monthly = df.groupby("month")["amount"].sum().sort_index()

    # Rule: Need at least 3 months
    if len(monthly) < 3:
        return {
            "has_enough_data": False,
            "available_months": len(monthly),
            "message": f"Requires at least 3 months of data for trend forecasting ({len(monthly)} month(s) available)."
        }

    from sklearn.linear_model import LinearRegression

    X = np.arange(len(monthly)).reshape(-1, 1)
    y = monthly.values

    model = LinearRegression()
    model.fit(X, y)

    # Next month prediction
    next_idx = np.array([[len(monthly)]])
    pred_amt = float(model.predict(next_idx)[0])
    pred_amt = max(0.0, round(pred_amt, 2))

    # Next month name string
    last_period = monthly.index[-1]
    next_period = last_period + 1
    next_month_str = str(next_period)

    # Historical monthly points dict
    history = {str(m): round(float(amt), 2) for m, amt in monthly.items()}

    # Trend direction based on slope
    slope = float(model.coef_[0])
    trend_desc = "upward" if slope > 500 else ("downward" if slope < -500 else "stable")

    return {
        "has_enough_data": True,
        "available_months": len(monthly),
        "history": history,
        "next_month": next_month_str,
        "predicted_amount": pred_amt,
        "trend_direction": trend_desc,
        "slope": round(slope, 2),
        "message": f"Predicted spend for {next_month_str} is ₹{pred_amt:,.0f} ({trend_desc} trend)."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Chat Aggregator (Pandas Data Prep)
# ─────────────────────────────────────────────────────────────────────────────

def prepare_chat_summary(user_id: int, user_query: str) -> dict:
    """
    Computes an aggregated summary of the user's spending data for the AI Chat:
      - Does NOT send all raw transaction rows.
      - Calculates category totals, top merchants, monthly trends, anomalies.
      - Filters specifically for any merchant or category mentioned in the query.
      - Falls back to platform data if user hasn't uploaded personal statement yet.
    """
    txns = get_all_user_transactions(user_id)
    if not txns:
        from database import get_connection
        conn = get_connection()
        rows = conn.execute("SELECT * FROM transactions ORDER BY date ASC").fetchall()
        conn.close()
        txns = [dict(r) for r in rows]

    if not txns:
        return {
            "has_data": False,
            "message": "No transaction records found in the system. Please upload a statement first."
        }

    df = pd.DataFrame(txns)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["is_anomaly"] = pd.to_numeric(df["is_anomaly"], errors="coerce").fillna(0).astype(int)
    df["merchant_clean"] = df["merchant"].fillna("Unknown").str.strip()

    total_spend = float(df["amount"].sum())
    total_txns  = len(df)
    anomalies   = df[df["is_anomaly"] == 1]

    # Category totals
    cat_totals = df.groupby("final_category")["amount"].sum().round(2).to_dict()

    # Top 8 merchants
    top_merchants = (
        df.groupby("merchant_clean")["amount"]
        .agg(["sum", "count"])
        .sort_values(by="sum", ascending=False)
        .head(8)
        .reset_index()
        .to_dict(orient="records")
    )

    # Query specific match: Check if user asked about a specific merchant (e.g. Zomato, Amazon, etc.)
    specific_merchant_match = None
    query_lower = user_query.lower()

    # Search in merchants
    unique_merchants = df["merchant_clean"].dropna().unique()
    matched_merchant = None
    for m in unique_merchants:
        if m.lower() in query_lower:
            matched_merchant = m
            break

    if matched_merchant:
        m_df = df[df["merchant_clean"].str.lower() == matched_merchant.lower()]
        specific_merchant_match = {
            "merchant": matched_merchant,
            "total_spend": round(float(m_df["amount"].sum()), 2),
            "txn_count": len(m_df),
            "avg_spend": round(float(m_df["amount"].mean()), 2),
            "categories": m_df["final_category"].unique().tolist(),
            "first_date": str(m_df["date"].min()),
            "last_date": str(m_df["date"].max())
        }

    # Anomalies brief
    anomaly_samples = (
        anomalies[["date", "merchant", "amount", "final_category"]]
        .head(5)
        .to_dict(orient="records")
    )

    return {
        "has_data": True,
        "total_spend": round(total_spend, 2),
        "total_txns": total_txns,
        "anomaly_count": len(anomalies),
        "category_totals": cat_totals,
        "top_merchants": top_merchants,
        "specific_merchant_match": specific_merchant_match,
        "anomaly_samples": anomaly_samples
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Smart Spending Diagnostics (50/30/20 Matrix & Behavioral Spend Radar)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_spending_diagnostics(user_id: int) -> dict:
    """
    Computes deep behavioral finance diagnostics:
      1. 50/30/20 Budget Rule Allocation (Needs vs Wants vs Savings/Other)
      2. Weekend vs Weekday Impulse Surge Radar
      3. Micro-Expense Bleed ('Chai/Coffee & Delivery' small transaction detector)
      4. Merchant Monopoly Index (Top 3 merchants concentration)
    """
    txns = get_all_user_transactions(user_id)
    if not txns:
        return {
            "has_data": False,
            "rule_50_30_20": {
                "needs_amt": 0, "needs_pct": 0, "needs_target": 50,
                "wants_amt": 0, "wants_pct": 0, "wants_target": 30,
                "other_amt": 0, "other_pct": 0, "other_target": 20,
                "status": "No data yet",
                "delta_label": "Upload statement to evaluate 50/30/20 balance"
            },
            "weekend_radar": {
                "weekend_amt": 0, "weekend_pct": 0,
                "weekday_amt": 0, "weekday_pct": 0,
                "surge_multiplier": 1.0,
                "tag": "Balanced",
                "insight": "No data available."
            },
            "micro_bleed": {
                "count": 0, "total_amt": 0, "pct_of_spend": 0,
                "insight": "No micro-spends detected yet."
            },
            "merchant_monopoly": {
                "top3_share": 0,
                "top_merchants": [],
                "insight": "No merchant concentration data."
            }
        }

    df = pd.DataFrame(txns)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df = df[df["amount"] > 0]
    total_spend = float(df["amount"].sum())

    if total_spend <= 0:
        return {"has_data": False}

    # 1. 50/30/20 Rule Breakdown
    NEEDS_CATS = {"Bills", "Groceries", "Health"}
    WANTS_CATS = {"Dining", "Shopping", "Entertainment", "Travel"}

    needs_amt = float(df[df["final_category"].isin(NEEDS_CATS)]["amount"].sum())
    wants_amt = float(df[df["final_category"].isin(WANTS_CATS)]["amount"].sum())
    other_amt = float(df[~df["final_category"].isin(NEEDS_CATS | WANTS_CATS)]["amount"].sum())

    needs_pct = round((needs_amt / total_spend) * 100, 1)
    wants_pct = round((wants_amt / total_spend) * 100, 1)
    other_pct = round(max(0, 100.0 - needs_pct - wants_pct), 1)

    if wants_pct > 40:
        wants_status = f"⚠️ Wants are {wants_pct - 30:.0f}% above target"
        delta_label = f"₹{max(0, wants_amt - (total_spend * 0.30)):,.0f} excess discretionary spend"
    elif needs_pct > 65:
        wants_status = f"⚠️ Needs consuming {needs_pct:.0f}% of budget"
        delta_label = "Essential bills & groceries dominating outflow"
    else:
        wants_status = "✅ Healthy 50/30/20 Balance"
        delta_label = "Spending is aligned with ideal financial benchmarks"

    # 2. Weekend vs Weekday Impulse Radar
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    valid_dt = df.dropna(subset=["dt"]).copy()
    if not valid_dt.empty:
        # Friday (4), Saturday (5), Sunday (6) as weekend/leisure
        valid_dt["is_weekend"] = valid_dt["dt"].dt.dayofweek >= 4
        weekend_amt = float(valid_dt[valid_dt["is_weekend"]]["amount"].sum())
        weekday_amt = float(valid_dt[~valid_dt["is_weekend"]]["amount"].sum())
        weekend_days = valid_dt[valid_dt["is_weekend"]]["dt"].dt.date.nunique() or 1
        weekday_days = valid_dt[~valid_dt["is_weekend"]]["dt"].dt.date.nunique() or 1

        weekend_daily = weekend_amt / weekend_days
        weekday_daily = weekday_amt / weekday_days
        surge_mult = round(weekend_daily / max(weekday_daily, 1.0), 1)

        denom = max(weekend_amt + weekday_amt, 1.0)
        weekend_pct = round((weekend_amt / denom) * 100, 1)
        weekday_pct = round(100.0 - weekend_pct, 1)

        if surge_mult >= 1.8:
            tag = "⚡ High Weekend Surge"
            radar_insight = f"Spend velocity is {surge_mult}x higher on weekends (Fri–Sun) vs weekdays."
        elif surge_mult >= 1.2:
            tag = "🟡 Moderate Weekend Lift"
            radar_insight = f"Weekends see {surge_mult}x daily burn rate compared to workdays."
        else:
            tag = "🟢 Balanced Daily Burn"
            radar_insight = "Even daily distribution between weekdays and weekends."
    else:
        weekend_amt, weekday_amt = 0, 0
        weekend_pct, weekday_pct = 0, 0
        surge_mult = 1.0
        tag = "Balanced"
        radar_insight = "Date metadata insufficient for day analysis."

    # 3. Micro-Expense Bleed (≤ ₹500 transactions)
    micro_df = df[df["amount"] <= 500]
    micro_count = len(micro_df)
    micro_total = float(micro_df["amount"].sum())
    micro_pct = round((micro_total / total_spend) * 100, 1)
    if micro_count > 0:
        micro_insight = f"{micro_count} micro-orders (≤ ₹500) quietly totaled ₹{micro_total:,.0f} ({micro_pct}% of total spend)."
    else:
        micro_insight = "No micro-spends (≤ ₹500) detected."

    # 4. Merchant Monopoly (Top 3 Concentration)
    merchant_grp = df.groupby("merchant")["amount"].sum().sort_values(ascending=False)
    top3_merchants = merchant_grp.head(3)
    top3_total = float(top3_merchants.sum())
    top3_share = round((top3_total / total_spend) * 100, 1)

    top_m_list = [
        {"merchant": str(m), "amount": round(float(a), 2), "share": round((float(a) / total_spend) * 100, 1)}
        for m, a in top3_merchants.items()
    ]

    monopoly_insight = f"Top 3 merchants capture {top3_share}% of your total outflow."

    return {
        "has_data": True,
        "rule_50_30_20": {
            "needs_amt": round(needs_amt, 2),
            "needs_pct": needs_pct,
            "needs_target": 50,
            "wants_amt": round(wants_amt, 2),
            "wants_pct": wants_pct,
            "wants_target": 30,
            "other_amt": round(other_amt, 2),
            "other_pct": other_pct,
            "other_target": 20,
            "status": wants_status,
            "delta_label": delta_label
        },
        "weekend_radar": {
            "weekend_amt": round(weekend_amt, 2),
            "weekend_pct": weekend_pct,
            "weekday_amt": round(weekday_amt, 2),
            "weekday_pct": weekday_pct,
            "surge_multiplier": surge_mult,
            "tag": tag,
            "insight": radar_insight
        },
        "micro_bleed": {
            "count": micro_count,
            "total_amt": round(micro_total, 2),
            "pct_of_spend": micro_pct,
            "insight": micro_insight
        },
        "merchant_monopoly": {
            "top3_share": top3_share,
            "top_merchants": top_m_list,
            "insight": monopoly_insight
        }
    }
