"""
SpendSense AI — Central Configuration
=======================================
All settings, paths, and constants live here.
If you need to change a path or key name, change it ONLY in this file.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── Flask ────────────────────────────────────────────────────────────────────
SECRET_KEY   = os.getenv("SECRET_KEY", "dev-secret-key-please-change")
FLASK_DEBUG  = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1")
FLASK_PORT   = int(os.getenv("PORT", os.getenv("FLASK_PORT", 7860 if os.getenv("SPACE_ID") else 5000)))

# ─── JWT ──────────────────────────────────────────────────────────────────────
JWT_EXPIRY_SECONDS = 3600          # tokens expire after 1 hour
JWT_ALGORITHM      = "HS256"

# ─── Database ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "spendsense.db")

# ─── File Uploads ─────────────────────────────────────────────────────────────
UPLOAD_FOLDER    = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {".csv"}
MAX_FILE_SIZE_MB   = 10

# ─── ML Models ────────────────────────────────────────────────────────────────
ML_DIR              = os.path.join(BASE_DIR, "ml")
MODEL_DIR           = os.path.join(ML_DIR, "models")
CATEGORIZER_PATH    = os.path.join(MODEL_DIR, "categorizer.pkl")
VECTORIZER_PATH     = os.path.join(MODEL_DIR, "tfidf_vectorizer.pkl")
ANOMALY_MODEL_PATH  = os.path.join(MODEL_DIR, "anomaly_detector.pkl")

# ─── Training Data ────────────────────────────────────────────────────────────
DATA_DIR          = os.path.join(BASE_DIR, "data")
TRANSACTIONS_CSV  = os.path.join(DATA_DIR, "transactions.csv")
SAMPLE_CSV        = os.path.join(DATA_DIR, "sample_upload.csv")

# ─── LLM / Gemini ─────────────────────────────────────────────────────────────
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL_NAME   = "gemini-3.5-flash-lite"

def get_effective_google_api_key() -> str:
    """
    Returns the active Gemini API key from .env (reloading on call) or database.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    env_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if env_key and env_key != "your_gemini_api_key_here" and len(env_key) > 15:
        return env_key

    try:
        from database import get_system_setting
        db_key = get_system_setting("google_api_key", "").strip()
        if db_key and db_key != "your_gemini_api_key_here" and len(db_key) > 15:
            return db_key
    except Exception:
        pass

    return ""

def is_agents_enabled() -> bool:
    """Returns True if a valid Google Gemini API key is configured."""
    return bool(get_effective_google_api_key())

# Enabled only if key is provided and is not the default placeholder
AGENTS_ENABLED      = bool(GOOGLE_API_KEY) and GOOGLE_API_KEY not in ("your_gemini_api_key_here", "") and len(GOOGLE_API_KEY) > 15

# ─── Class Labels ─────────────────────────────────────────────────────────────
# These are the 8 spending categories the ML categorizer can predict.
# Keep this list in sync with the training data labels.
CATEGORY_LABELS = [
    "Dining",
    "Groceries",
    "Bills",
    "Shopping",
    "Travel",
    "Health",
    "Entertainment",
    "Transfer",
]

# Confidence threshold below which Agent 1 (Categorization Agent) will
# re-evaluate and potentially reassign the ML-predicted label.
LOW_CONFIDENCE_THRESHOLD = 0.60

# Contamination rate for Isolation Forest (expected anomaly fraction)
ANOMALY_CONTAMINATION = 0.05      # 5% of transactions expected to be anomalous

# ─── Admin Defaults ───────────────────────────────────────────────────────────
DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL", "admin@spendsense.com")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")

# ─── Ensure directories exist ────────────────────────────────────────────────
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
