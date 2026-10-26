"""
SpendSense AI — Flask Application Entry Point
===============================================
Start the server with: python app.py

What this file does:
  1. Creates the Flask app instance
  2. Registers all route blueprints (auth, user, admin)
  3. Adds CORS headers (allows the frontend to call the API)
  4. Initializes the SQLite database (creates tables + default admin)
  5. Serves the frontend (index.html) on the root route
  6. Starts the development server on port 5000
"""

import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import SECRET_KEY, FLASK_DEBUG, FLASK_PORT
from database import init_db
from routes.auth_routes  import auth_bp
from routes.user_routes  import user_bp
from routes.admin_routes import admin_bp


# ─────────────────────────────────────────────────────────────────────────────
# App Creation
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)
app.config["SECRET_KEY"] = SECRET_KEY

# Enable CORS for all API routes (allows browser JS to call the API)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Auto-initialize SQLite database (creates tables & admin account for Gunicorn / WSGI)
try:
    init_db()
except Exception as _e:
    print(f"[Startup] DB init notice: {_e}")


# ─────────────────────────────────────────────────────────────────────────────
# Register Blueprints
# ─────────────────────────────────────────────────────────────────────────────

app.register_blueprint(auth_bp)   # /api/auth/*
app.register_blueprint(user_bp)   # /api/user/*
app.register_blueprint(admin_bp)  # /api/admin/*


# ─────────────────────────────────────────────────────────────────────────────
# Frontend Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main SPA (Single Page Application)."""
    return send_from_directory("templates", "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


@app.route("/api/sample-csv")
def sample_csv():
    """Serve sample transaction CSV for quick one-click demo."""
    return send_from_directory("data", "sample_upload.csv", mimetype="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    """Simple health check endpoint."""
    from ml.predict import models_are_trained
    from config import AGENTS_ENABLED
    return jsonify({
        "status":         "ok",
        "models_trained": models_are_trained(),
        "agents_enabled": AGENTS_ENABLED
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found."}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed."}), 405


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error. Please try again."}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("  SpendSense AI — Starting Server")
    print("=" * 65)

    # Initialize database (creates tables + admin user on first run)
    print("[Startup] Initializing database...")
    init_db()
    print("[Startup] Database ready.")

    # Show ML model status
    from ml.predict import models_are_trained
    from config import AGENTS_ENABLED
    if models_are_trained():
        print("[Startup] ✅ ML models found and ready.")
    else:
        print("[Startup] ⚠️  ML models not found. Train them first:")
        print("             python ml/train_categorizer.py")
        print("             python ml/train_anomaly.py")

    if AGENTS_ENABLED:
        print("[Startup] ✅ Gemini agents enabled.")
    else:
        print("[Startup] ⚠️  No GOOGLE_API_KEY found — running in ML-only mode.")
        print("             Add your key to .env to enable AI insights.")

    print(f"\n[Startup] 🚀 Server running at http://localhost:{FLASK_PORT}")
    print("           Press Ctrl+C to stop.\n")

    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=FLASK_DEBUG
    )
