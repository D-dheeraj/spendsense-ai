---
title: SpendSense AI
emoji: 💳
colorFrom: amber
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# SpendSense AI
### Multi-Agent Personal Finance & Expense Advisor
**Self-Trained ML + Multi-Agent LLM System**

> Prepared by: **Dheeraj** | MCA, BIT Mesra

---

## What Is This?

SpendSense AI is a **full-stack personal finance advisor** that combines:
- A **self-trained Machine Learning layer** (Random Forest + Isolation Forest)
- A **multi-agent LLM layer** (4 Gemini-powered agents)
- An **authenticated web dashboard** (Flask + HTML/CSS/JS)

Upload your bank statement CSV → get automated spending categories, anomaly alerts, AI-written insights, and budget tips.

---

## Architecture

```
CSV Upload
    │
    ▼
┌─────────────────────────────────────┐
│  ML Layer (Self-Trained)            │
│  • Categorizer (Random Forest)      │ → predicted_category, confidence
│  • Anomaly Detector (Isolation Forest)│ → is_anomaly, anomaly_score
└────────────────────┬────────────────┘
                     │
                     ▼
┌─────────────────────────────────────┐
│  Agent Layer (Gemini 1.5 Flash)     │
│  • Agent 1: Categorization Agent   │ → refines ML labels
│  • Agent 2: Insight Agent          │ → monthly narrative
│  • Agent 3: Budget Advisor Agent   │ → 5 saving tips
│  • Agent 4: Alert Agent            │ → anomaly alerts
└────────────────────┬────────────────┘
                     │
                     ▼
┌─────────────────────────────────────┐
│  Web App (Flask + SQLite)           │
│  • JWT Auth (User + Admin roles)   │
│  • Dashboard: charts, tables, text │
└─────────────────────────────────────┘
```

---

## Quick Start

```bash
# Option A: One command
bash run.sh

# Option B: Manual steps
pip install -r requirements.txt
cp .env.example .env          # add your GOOGLE_API_KEY
python data/generate_data.py  # creates training data
python ml/train_categorizer.py
python ml/train_anomaly.py
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Default Credentials

| Role  | Username | Password   |
|-------|----------|------------|
| Admin | admin    | Admin@123  |
| User  | Register via the app |

---

## CSV Upload Format

| Column       | Required | Example          |
|--------------|----------|------------------|
| `date`       | ✅       | 2024-03-15       |
| `merchant`   | ✅       | Zomato           |
| `amount`     | ✅       | 450.00           |
| `description`| Optional | food delivery    |

Use `data/sample_upload.csv` for a ready-to-use demo file.

---

## Class Labels

**8 Spending Categories** (Categorizer output):
`Dining` · `Groceries` · `Bills` · `Shopping` · `Travel` · `Health` · `Entertainment` · `Transfer`

**Anomaly Labels** (Anomaly Detector output):
`0` = Normal · `1` = Anomaly

---

## Folder Structure

```
Spendsense/
├── app.py              ← Flask entry point
├── config.py           ← All settings
├── database.py         ← SQLite layer
├── auth.py             ← JWT auth
├── requirements.txt
├── run.sh              ← One-command launcher
├── checkpoint.json     ← Build progress tracker
│
├── data/
│   ├── generate_data.py
│   ├── transactions.csv
│   └── sample_upload.csv
│
├── ml/
│   ├── feature_engineering.py
│   ├── train_categorizer.py
│   ├── train_anomaly.py
│   ├── predict.py
│   └── models/         ← Saved .pkl files
│
├── agents/
│   ├── prompts.py
│   ├── agent_runner.py
│   └── orchestrator.py
│
├── routes/
│   ├── auth_routes.py
│   ├── user_routes.py
│   └── admin_routes.py
│
├── templates/
│   └── index.html
│
└── static/
    ├── css/style.css
    └── js/
        ├── app.js
        ├── dashboard.js
        └── charts.js
```

---

## Tech Stack

| Layer       | Technology                          |
|-------------|-------------------------------------|
| Language    | Python 3.9+                         |
| ML          | scikit-learn, pandas, numpy, joblib |
| LLM/Agents  | google-generativeai (Gemini 1.5 Flash)|
| Backend     | Flask, Flask-CORS                   |
| Auth        | PyJWT, bcrypt                       |
| Database    | SQLite (built-in)                   |
| Frontend    | HTML5, Vanilla CSS, Vanilla JS      |
| Charts      | Chart.js (CDN)                      |

---

## Resuming the Build

If you stopped mid-build, check `checkpoint.json`:
```bash
cat checkpoint.json
```
Then tell the AI: **"Continue SpendSense from checkpoint"**

---

## API Reference

| Method | Endpoint                 | Auth  | Description        |
|--------|--------------------------|-------|--------------------|
| POST   | /api/auth/register       | None  | Create account     |
| POST   | /api/auth/login          | None  | Login → JWT        |
| POST   | /api/user/upload         | User  | Upload CSV         |
| GET    | /api/user/dashboard      | User  | Dashboard data     |
| GET    | /api/user/transactions   | User  | Transaction list   |
| GET    | /api/user/summary        | User  | Chart data         |
| GET    | /api/admin/users         | Admin | List all users     |
| DELETE | /api/admin/users/\<id\>  | Admin | Delete user        |
| GET    | /api/admin/stats         | Admin | Platform stats     |
| POST   | /api/admin/retrain       | Admin | Retrain ML models  |

---

*SpendSense AI — MCA Project, BIT Mesra*
