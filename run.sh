#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  SpendSense AI — One-Command Launcher
#  Run: bash run.sh
# ═══════════════════════════════════════════════════════════

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       SpendSense AI — Launcher           ║"
echo "  ║  Multi-Agent Personal Finance Advisor    ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── Step 1: Check Python ──────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ Python3 not found. Please install Python 3.9+ first."
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# ── Step 2: Install dependencies ─────────────────────────────────────────────
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt -q
echo "✅ Dependencies installed."

# ── Step 3: Create .env if missing ───────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Created .env from template."
    echo "   Add your GOOGLE_API_KEY to .env to enable AI agents."
    echo "   The app works without it (ML-only mode)."
fi

# ── Step 4: Generate training data (if missing) ───────────────────────────────
if [ ! -f "data/transactions.csv" ]; then
    echo ""
    echo "🔢 Generating synthetic training data..."
    python3 data/generate_data.py
fi

# ── Step 5: Train ML models (if not trained) ──────────────────────────────────
if [ ! -f "ml/models/categorizer.pkl" ]; then
    echo ""
    echo "🤖 Training ML Categorizer (Random Forest)..."
    python3 ml/train_categorizer.py
fi

if [ ! -f "ml/models/anomaly_detector.pkl" ]; then
    echo ""
    echo "🔍 Training Anomaly Detector (Isolation Forest)..."
    python3 ml/train_anomaly.py
fi

# ── Step 6: Launch Flask ───────────────────────────────────────────────────────
echo ""
echo "🚀 Starting SpendSense AI server..."
echo "   Open http://localhost:5000 in your browser"
echo "   Admin login: admin / Admin@123"
echo "   Press Ctrl+C to stop"
echo ""
python3 app.py
