"""
SpendSense AI — Synthetic Transaction Data Generator
======================================================
Run this script ONCE to create the training dataset.
  python data/generate_data.py

Produces:
  data/transactions.csv   — ~2000 rows (used to train ML models)
  data/sample_upload.csv  — 50 rows  (ready-to-use demo upload file)

Each row contains:
  transaction_id, date, merchant, description, amount,
  category (ground-truth label), is_anomaly (0 or 1)

Design:
  For each of the 8 categories we define:
    - A pool of realistic merchant names
    - Typical amount range (min, max)
    - Description phrases
  Anomalies are injected by multiplying a random normal transaction's
  amount by 5–10x and flipping its is_anomaly flag to 1.
"""

import pandas as pd
import numpy as np
import random
import os
from datetime import datetime, timedelta

# Ensure reproducibility
random.seed(42)
np.random.seed(42)

# ─────────────────────────────────────────────────────────────────────────────
# Category Rules
# Each entry defines realistic data for that spending category.
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_RULES = {
    "Dining": {
        "merchants": [
            "Zomato", "Swiggy", "McDonald's", "Domino's Pizza",
            "Cafe Coffee Day", "Subway", "Pizza Hut", "KFC",
            "Burger King", "Barbeque Nation", "Haldiram's",
            "Starbucks", "Chai Point", "Faasos", "Box8"
        ],
        "amount_range": (80, 1500),
        "descriptions": [
            "food order", "restaurant bill", "delivery charge",
            "online food delivery", "dine-in payment", "takeaway order",
            "dinner bill", "lunch payment", "breakfast order"
        ],
        "weight": 0.20   # 20% of all transactions
    },
    "Groceries": {
        "merchants": [
            "BigBasket", "DMart", "Reliance Fresh", "Nature's Basket",
            "Blinkit", "Grofers", "More Supermarket", "Spencers",
            "Star Bazaar", "Nilgiris", "Hypercity", "Zepto"
        ],
        "amount_range": (200, 5000),
        "descriptions": [
            "grocery purchase", "supermarket shopping", "weekly groceries",
            "vegetables and fruits", "dairy products", "household items",
            "monthly grocery", "online grocery order", "fresh produce"
        ],
        "weight": 0.18
    },
    "Bills": {
        "merchants": [
            "Airtel", "Jio", "BSNL", "BESCOM", "MSEDCL",
            "Tata Power", "Indane Gas", "Mahanagar Gas", "LIC Premium",
            "HDFC Insurance", "Amazon Prime", "Netflix Bill",
            "Vodafone", "Society Maintenance", "Water Tax Office"
        ],
        "amount_range": (100, 8000),
        "descriptions": [
            "mobile recharge", "electricity bill payment",
            "internet bill", "gas bill", "insurance premium",
            "society maintenance", "water bill", "broadband payment",
            "DTH recharge", "utility payment", "subscription renewal"
        ],
        "weight": 0.15
    },
    "Shopping": {
        "merchants": [
            "Amazon", "Flipkart", "Myntra", "Ajio", "Nykaa",
            "Meesho", "Snapdeal", "Lifestyle", "Westside",
            "H&M", "Zara", "Decathlon", "Croma", "Reliance Digital",
            "Apple Store"
        ],
        "amount_range": (300, 25000),
        "descriptions": [
            "online shopping", "apparel purchase", "electronics order",
            "home decor", "fashion purchase", "gadget buy",
            "clothing", "accessories", "sports equipment"
        ],
        "weight": 0.17
    },
    "Travel": {
        "merchants": [
            "MakeMyTrip", "IRCTC", "Uber", "Ola", "RedBus",
            "Rapido", "IndiGo Airlines", "Air India", "SpiceJet",
            "Yatra", "GoIbibo", "OYO Rooms", "Zostel",
            "Meru Cabs", "BlaBlacar"
        ],
        "amount_range": (50, 30000),
        "descriptions": [
            "cab ride", "train ticket", "flight booking",
            "bus ticket", "hotel booking", "airport transfer",
            "intercity travel", "auto rickshaw", "outstation trip"
        ],
        "weight": 0.12
    },
    "Health": {
        "merchants": [
            "Apollo Pharmacy", "MedPlus", "Netmeds", "1mg",
            "Cult.fit", "Healthians", "Lybrate", "PharmEasy",
            "Fortis Hospital", "Apollo Hospital", "Max Hospital",
            "Thyrocare", "Dr. Lal PathLabs", "Practo"
        ],
        "amount_range": (100, 15000),
        "descriptions": [
            "medicine purchase", "health checkup", "gym membership",
            "doctor consultation", "lab test", "pharmacy",
            "medical report", "fitness subscription", "health insurance claim"
        ],
        "weight": 0.08
    },
    "Entertainment": {
        "merchants": [
            "Netflix", "Amazon Prime Video", "Hotstar", "Sony LIV",
            "Zee5", "PVR Cinemas", "INOX", "BookMyShow",
            "Spotify", "YouTube Premium", "Apple Music",
            "Steam", "PlayStation Store", "Xbox Live"
        ],
        "amount_range": (50, 5000),
        "descriptions": [
            "OTT subscription", "movie ticket", "streaming service",
            "music subscription", "gaming purchase", "event ticket",
            "concert booking", "digital content", "app subscription"
        ],
        "weight": 0.07
    },
    "Transfer": {
        "merchants": [
            "PhonePe", "Google Pay", "Paytm", "NEFT Transfer",
            "IMPS Payment", "RTGS Transfer", "UPI Payment",
            "Bank Transfer", "Self Transfer", "CRED Payment"
        ],
        "amount_range": (500, 50000),
        "descriptions": [
            "money transfer", "UPI payment", "bank transfer",
            "wallet top-up", "self transfer", "rent payment",
            "family transfer", "credit card payment", "loan repayment"
        ],
        "weight": 0.03
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# Generator Functions
# ─────────────────────────────────────────────────────────────────────────────

def random_date(start_date, end_date):
    """Return a random date string between start and end."""
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return (start_date + timedelta(days=random_days)).strftime("%Y-%m-%d")


def generate_one_transaction(txn_id, category, start_date, end_date):
    """Generate a single realistic transaction for a given category."""
    rules = CATEGORY_RULES[category]
    amount_min, amount_max = rules["amount_range"]

    # Use log-normal distribution for more realistic amount clustering
    mean_amount = (amount_min + amount_max) / 2
    amount = round(np.random.lognormal(
        mean=np.log(mean_amount),
        sigma=0.4
    ), 2)
    # Clip to the category's range
    amount = float(np.clip(amount, amount_min, amount_max))

    return {
        "transaction_id":  f"TXN{txn_id:05d}",
        "date":            random_date(start_date, end_date),
        "merchant":        random.choice(rules["merchants"]),
        "description":     random.choice(rules["descriptions"]),
        "amount":          amount,
        "category":        category,
        "is_anomaly":      0
    }


def inject_anomalies(df, anomaly_fraction=0.05):
    """
    Randomly select ~5% of transactions and multiply their amounts
    by a factor of 5–10x to simulate unusual spending.
    Set is_anomaly = 1 for those rows.
    """
    n_anomalies = int(len(df) * anomaly_fraction)
    anomaly_indices = random.sample(range(len(df)), n_anomalies)
    for idx in anomaly_indices:
        multiplier = random.uniform(5, 10)
        df.at[idx, "amount"]     = round(df.at[idx, "amount"] * multiplier, 2)
        df.at[idx, "is_anomaly"] = 1
    return df


def generate_dataset(n_total=2000):
    """
    Generate n_total transactions distributed across all 8 categories
    according to each category's weight. Returns a pandas DataFrame.
    """
    categories = list(CATEGORY_RULES.keys())
    weights     = [CATEGORY_RULES[c]["weight"] for c in categories]

    # Determine how many rows per category (weights must sum to ~1.0)
    counts = {
        cat: int(n_total * wt)
        for cat, wt in zip(categories, weights)
    }
    # Adjust for rounding
    total_assigned = sum(counts.values())
    counts[categories[0]] += n_total - total_assigned

    start_date = datetime(2024, 1, 1)
    end_date   = datetime(2024, 12, 31)

    rows = []
    txn_id = 1
    for cat, count in counts.items():
        for _ in range(count):
            rows.append(generate_one_transaction(txn_id, cat, start_date, end_date))
            txn_id += 1

    df = pd.DataFrame(rows)
    df = inject_anomalies(df)
    df = df.sample(frac=1).reset_index(drop=True)   # shuffle
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir   = script_dir   # already in data/

    print("=" * 60)
    print("SpendSense AI — Synthetic Data Generator")
    print("=" * 60)

    # ── Generate full training dataset (2000 rows) ────────────────────────────
    print("\n[1/2] Generating 2000-row training dataset...")
    df_full = generate_dataset(n_total=2000)
    full_path = os.path.join(data_dir, "transactions.csv")
    df_full.to_csv(full_path, index=False)
    print(f"      Saved: {full_path}")
    print(f"      Shape: {df_full.shape}")
    print(f"      Categories: {df_full['category'].value_counts().to_dict()}")
    print(f"      Anomalies:  {df_full['is_anomaly'].sum()} rows")

    # ── Generate sample demo upload (50 rows, no anomaly col) ─────────────────
    print("\n[2/2] Generating 50-row sample upload file...")
    df_sample = df_full.head(60).copy()
    # Remove ground-truth cols — user upload won't have them
    df_sample = df_sample.drop(columns=["transaction_id", "category", "is_anomaly"])
    sample_path = os.path.join(data_dir, "sample_upload.csv")
    df_sample.to_csv(sample_path, index=False)
    print(f"      Saved: {sample_path}")
    print(f"      Columns: {list(df_sample.columns)}")

    print("\n✅ Data generation complete!")
    print("   Next: python ml/train_categorizer.py")
