"""
SpendSense AI — User Routes
==============================
All endpoints that a regular (non-admin) logged-in user can access.
All routes are protected by @require_auth.

Endpoints:
  POST /api/user/upload         — upload CSV, runs background pipeline with job status
  GET  /api/user/upload/status  — poll live agent execution status
  GET  /api/user/dashboard      — latest batch results + animated KPIs + health score
  GET  /api/user/transactions   — paginated + filterable transaction list
  GET  /api/user/summary        — category totals + monthly trend + ML spend forecast
  GET  /api/user/health-score   — 0-100 financial health gauge & pillar breakdown
  POST /api/user/chat           — Chat with Data assistant powered by pandas + Gemini
  GET  /api/user/batches        — list all past uploads
"""

import os
import io
import uuid
import threading
import pandas as pd
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from auth import require_auth
from database import (save_upload_batch, save_transactions,
                      get_user_batches, get_latest_batch,
                      get_user_transactions, get_all_user_transactions)
from agents.orchestrator import run_pipeline
from agents.agent_runner import run_chat_agent
from analytics import (calculate_kpis, calculate_health_score,
                       calculate_forecast, prepare_chat_summary,
                       calculate_spending_diagnostics)
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

user_bp = Blueprint("user", __name__, url_prefix="/api/user")

# In-memory tracking of upload background jobs for live progress
upload_jobs = {}


def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# Background Upload Processor
# ─────────────────────────────────────────────────────────────────────────────

def _process_upload_task(job_id: str, user_id: int, df: pd.DataFrame, filename: str):
    """Worker running in a background thread to update live agent progress."""
    try:
        def on_progress(step: int, name: str, pct: int):
            if job_id in upload_jobs:
                upload_jobs[job_id]["step"] = step
                upload_jobs[job_id]["step_name"] = name
                upload_jobs[job_id]["progress"] = pct

        result = run_pipeline(df, filename=filename, progress_callback=on_progress)
        if not result.get("success"):
            upload_jobs[job_id]["status"] = "failed"
            upload_jobs[job_id]["error"]  = result.get("error", "Pipeline failed.")
            return

        summary = result["summary"]
        batch_id = save_upload_batch(
            user_id        = user_id,
            filename       = filename,
            total_txns     = summary["total_txns"],
            anomaly_count  = summary["anomaly_count"],
            total_amount   = summary["total_amount"],
            insight_text   = result["insight_text"],
            budget_tips    = result["budget_tips"],
            alerts         = result["alerts"],
            category_totals= summary["category_totals"]
        )

        save_transactions(
            batch_id          = batch_id,
            user_id           = user_id,
            transactions_list = result["transactions"]
        )

        upload_jobs[job_id]["status"]       = "completed"
        upload_jobs[job_id]["step"]         = 5
        upload_jobs[job_id]["progress"]     = 100
        upload_jobs[job_id]["step_name"]    = "Analysis completed successfully!"
        upload_jobs[job_id]["batch_id"]     = batch_id
        upload_jobs[job_id]["summary"]      = summary
        upload_jobs[job_id]["insight_text"] = result["insight_text"]
        upload_jobs[job_id]["budget_tips"]  = result["budget_tips"]
        upload_jobs[job_id]["alerts"]       = result["alerts"]

    except Exception as e:
        print(f"[UploadJob] Error processing job {job_id}: {e}")
        if job_id in upload_jobs:
            upload_jobs[job_id]["status"] = "failed"
            upload_jobs[job_id]["error"]  = str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Upload Endpoints (Async with Stepper Polling)
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/upload", methods=["POST"])
@require_auth
def upload(current_user):
    """
    Accepts CSV upload, launches background processing pipeline,
    and returns a job_id for live status polling.
    """
    from database import get_system_setting
    if get_system_setting("uploads_enabled", "true").lower() == "false":
        return jsonify({"error": "Statement uploads are temporarily paused by the administrator for platform maintenance."}), 403

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Please select a CSV file."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files are supported."}), 400

    file.seek(0, os.SEEK_END)
    file_size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if file_size_mb > MAX_FILE_SIZE_MB:
        return jsonify({"error": f"File too large. Maximum {MAX_FILE_SIZE_MB} MB."}), 400

    filename = secure_filename(file.filename)

    try:
        df = pd.read_csv(io.StringIO(file.read().decode("utf-8")))
    except Exception as e:
        return jsonify({"error": f"Could not read CSV file: {str(e)}"}), 400

    # Save to disk
    user_upload_dir = os.path.join(UPLOAD_FOLDER, str(current_user["user_id"]))
    os.makedirs(user_upload_dir, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_name = f"{timestamp}_{filename}"
    df.to_csv(os.path.join(user_upload_dir, saved_name), index=False)

    # Spawn background task
    job_id = str(uuid.uuid4())
    upload_jobs[job_id] = {
        "status":    "processing",
        "step":      1,
        "step_name": "Validating CSV structure...",
        "progress":  10,
        "error":     None
    }

    thread = threading.Thread(
        target=_process_upload_task,
        args=(job_id, current_user["user_id"], df, filename)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        "message": "Upload accepted. Pipeline processing in background.",
        "job_id":  job_id,
        "status":  "processing"
    }), 202


@user_bp.route("/upload/status/<job_id>", methods=["GET"])
@require_auth
def upload_status(current_user, job_id):
    """Poll live agent progress for an ongoing upload."""
    job = upload_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Upload job not found."}), 404
    return jsonify(job), 200


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Endpoint (with animated KPIs & Health Score)
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard(current_user):
    """
    Return latest batch data along with:
      - kpis: animated KPI metrics + month-over-month change
      - health_score: 0-100 financial health gauge
    """
    batch = get_latest_batch(current_user["user_id"])

    if not batch:
        return jsonify({
            "has_data":   False,
            "message":    "No uploads yet. Upload a CSV to get started."
        }), 200

    kpis        = calculate_kpis(current_user["user_id"])
    health      = calculate_health_score(current_user["user_id"])
    diagnostics = calculate_spending_diagnostics(current_user["user_id"])

    return jsonify({
        "has_data":        True,
        "batch_id":        batch["id"],
        "filename":        batch["filename"],
        "upload_date":     batch["upload_date"],
        "total_txns":      batch["total_txns"],
        "anomaly_count":   batch["anomaly_count"],
        "total_amount":    batch["total_amount"],
        "insight_text":    batch["insight_text"],
        "budget_tips":     batch["budget_tips"],
        "alerts":          batch["alerts"],
        "category_totals": batch["category_totals"],
        "kpis":            kpis,
        "health_score":    health,
        "diagnostics":     diagnostics
    }), 200


@user_bp.route("/diagnostics", methods=["GET"])
@require_auth
def diagnostics_route(current_user):
    """Return 50/30/20 budget matrix, weekend surge radar, and micro-spend bleed."""
    data = calculate_spending_diagnostics(current_user["user_id"])
    return jsonify(data), 200


# ─────────────────────────────────────────────────────────────────────────────
# Summary Endpoint (with Linear Regression Spend Forecast)
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/summary", methods=["GET"])
@require_auth
def summary(current_user):
    """
    Return category totals, authentic monthly trend data, and next-month forecast.
    """
    batches = get_user_batches(current_user["user_id"])
    if not batches:
        return jsonify({"has_data": False}), 200

    txns = get_all_user_transactions(current_user["user_id"])
    df   = pd.DataFrame(txns) if txns else pd.DataFrame()

    all_categories = {}
    monthly        = {}

    if not df.empty:
        all_categories = df.groupby("final_category")["amount"].sum().round(2).to_dict()
        df["dt"] = pd.to_datetime(df["date"], errors="coerce")
        valid = df.dropna(subset=["dt"]).copy()
        if not valid.empty:
            valid["m"] = valid["dt"].dt.to_period("M").astype(str)
            monthly = valid.groupby("m")["amount"].sum().round(2).sort_index().to_dict()

    if not monthly:
        for b in batches:
            m_key = b["upload_date"][:7]
            monthly[m_key] = monthly.get(m_key, 0) + b.get("total_amount", 0)

    forecast = calculate_forecast(current_user["user_id"])

    return jsonify({
        "has_data":        True,
        "category_totals": all_categories,
        "monthly_totals":  monthly,
        "forecast":        forecast,
        "total_uploads":   len(batches)
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Financial Health Score Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/health-score", methods=["GET"])
@require_auth
def health_score_route(current_user):
    """Return the detailed 0-100 financial health score and component breakdown."""
    health = calculate_health_score(current_user["user_id"])
    return jsonify(health), 200


# ─────────────────────────────────────────────────────────────────────────────
# Chat with Data Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/chat", methods=["POST"])
@require_auth
def chat(current_user):
    """
    AI financial assistant responding directly to user inquiries.
    Uses pandas to aggregate transaction metrics, avoiding token waste.
    Saves conversation messages strictly scoped to current_user.
    """
    from database import save_chat_message

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Message is required."}), 400

    # 1. Save user query to their own history
    save_chat_message(current_user["user_id"], "user", message)

    # 2. Generate answer
    summary_data = prepare_chat_summary(current_user["user_id"], message)
    reply = run_chat_agent(message, summary_data)

    # 3. Save AI reply to user's history
    save_chat_message(current_user["user_id"], "ai", reply)

    return jsonify({
        "reply": reply,
        "specific_match": summary_data.get("specific_merchant_match")
    }), 200


@user_bp.route("/chat/history", methods=["GET"])
@require_auth
def chat_history(current_user):
    """Return the current user's personal conversation history."""
    from database import get_user_chat_history
    messages = get_user_chat_history(current_user["user_id"], limit=100)
    return jsonify({
        "messages": messages,
        "user_id": current_user["user_id"]
    }), 200


@user_bp.route("/chat/history", methods=["DELETE"])
@require_auth
def clear_chat_history_route(current_user):
    """Clear chat history strictly for the authenticated user."""
    from database import clear_user_chat_history
    clear_user_chat_history(current_user["user_id"])
    return jsonify({"message": "Chat history cleared successfully."}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Transactions Endpoint (Paginated + Filterable)
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/transactions", methods=["GET"])
@require_auth
def transactions(current_user):
    """
    Return a paginated, filterable list of the user's transactions.
    """
    page         = int(request.args.get("page", 1))
    per_page     = min(int(request.args.get("per_page", 20)), 100)
    category     = request.args.get("category", None)
    anomaly_only = request.args.get("anomaly_only", "false").lower() == "true"

    result = get_user_transactions(
        user_id      = current_user["user_id"],
        page         = page,
        per_page     = per_page,
        category     = category,
        anomaly_only = anomaly_only
    )

    return jsonify(result), 200


# ─────────────────────────────────────────────────────────────────────────────
# Batches List Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/batches", methods=["GET"])
@require_auth
def batches(current_user):
    """Return all past upload batches for the current user."""
    user_batches = get_user_batches(current_user["user_id"])
    lite = []
    for b in user_batches:
        lite.append({
            "id":           b["id"],
            "filename":     b["filename"],
            "upload_date":  b["upload_date"],
            "total_txns":   b["total_txns"],
            "anomaly_count":b["anomaly_count"],
            "total_amount": b["total_amount"]
        })
    return jsonify({"batches": lite}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Financial Workspace: Goals & Smart Cheat Notes
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/workspace", methods=["GET"])
@require_auth
def get_workspace_data(current_user):
    """
    Return user's budget target, current spend, daily allowance pace,
    and personal financial cheat notes.
    """
    import calendar
    from datetime import date
    from database import get_user_goal, get_user_notes, get_all_user_transactions

    user_id = current_user["user_id"]
    goal = get_user_goal(user_id)
    notes = get_user_notes(user_id)

    # Calculate current month's outflow
    txns = get_all_user_transactions(user_id)
    today = date.today()
    curr_ym = today.strftime("%Y-%m")

    curr_month_spend = 0.0
    for t in txns:
        d_str = str(t.get("date", ""))
        if d_str.startswith(curr_ym):
            curr_month_spend += float(t.get("amount", 0) or 0)

    # If no transactions in current calendar month, fall back to total recent batch spend
    if curr_month_spend == 0.0 and txns:
        curr_month_spend = sum(float(t.get("amount", 0) or 0) for t in txns[-30:])

    monthly_budget = float(goal.get("monthly_budget", 50000.0))
    remaining = max(0.0, monthly_budget - curr_month_spend)
    pct_used = round((curr_month_spend / max(monthly_budget, 1.0)) * 100, 1)

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = max(1, days_in_month - today.day + 1)
    daily_allowance = round(remaining / days_left, 0)

    return jsonify({
        "monthly_budget": monthly_budget,
        "current_spend": round(curr_month_spend, 2),
        "remaining": round(remaining, 2),
        "pct_used": pct_used,
        "days_left": days_left,
        "daily_allowance": daily_allowance,
        "is_overbudget": curr_month_spend > monthly_budget,
        "notes": notes
    }), 200


@user_bp.route("/workspace/goal", methods=["POST"])
@require_auth
def update_goal(current_user):
    """Update user's monthly budget goal."""
    from database import set_user_goal
    data = request.get_json(silent=True) or {}
    budget = float(data.get("monthly_budget", 50000.0))
    if budget <= 0:
        return jsonify({"error": "Budget must be greater than 0"}), 400
    goal = set_user_goal(current_user["user_id"], monthly_budget=budget)
    return jsonify({"message": "Budget goal updated successfully", "goal": goal}), 200


@user_bp.route("/workspace/notes", methods=["POST"])
@require_auth
def create_note(current_user):
    """Add a new cheat note or reminder."""
    from database import add_user_note
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", "")).strip()
    if not note:
        return jsonify({"error": "Note cannot be empty"}), 400
    new_note = add_user_note(current_user["user_id"], note=note)
    return jsonify({"message": "Note added", "note": new_note}), 201


@user_bp.route("/workspace/notes/<int:note_id>/toggle", methods=["PATCH"])
@require_auth
def toggle_note_route(current_user, note_id):
    """Toggle completed state of a note."""
    from database import toggle_user_note
    toggle_user_note(note_id, current_user["user_id"])
    return jsonify({"message": "Note status updated"}), 200


@user_bp.route("/workspace/notes/<int:note_id>", methods=["DELETE"])
@require_auth
def delete_note_route(current_user, note_id):
    """Delete a user note."""
    from database import delete_user_note
    delete_user_note(note_id, current_user["user_id"])
    return jsonify({"message": "Note deleted"}), 200
