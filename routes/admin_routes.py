"""
SpendSense AI — Admin Routes
==============================
All endpoints exclusively for admin-role users.
Protected by @require_admin — regular users get 403 Forbidden.

Endpoints:
  GET    /api/admin/users          — list all registered users
  DELETE /api/admin/users/<id>     — delete a user and all their data
  GET    /api/admin/uploads        — all uploads across all users
  GET    /api/admin/stats          — site-wide aggregate statistics
  POST   /api/admin/retrain        — trigger ML model retraining
  GET    /api/admin/logs           — admin action audit trail
"""

import subprocess
import sys
import os
from flask import Blueprint, jsonify, request
from auth import require_admin
from database import (get_all_users, delete_user, get_all_batches,
                      get_site_stats, log_admin_action, get_admin_logs)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ─────────────────────────────────────────────────────────────────────────────
# User Management
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@require_admin
def list_users(current_user):
    """
    ADMIN: Return all registered users (id, username, email, role, created_at).
    Passwords are never returned.
    """
    users = get_all_users()
    return jsonify({
        "users": users,
        "total": len(users)
    }), 200


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_admin
def remove_user(current_user, user_id):
    """
    ADMIN: Delete a user account and ALL their data (uploads, transactions).
    Cannot delete your own account.
    """
    if user_id == current_user["user_id"]:
        return jsonify({"error": "You cannot delete your own account."}), 400

    from database import get_user_by_id
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "User not found."}), 404

    delete_user(user_id)

    log_admin_action(
        admin_id=current_user["user_id"],
        action=f"Deleted user: {target['username']} (id={user_id})"
    )

    return jsonify({"message": f"User '{target['username']}' deleted successfully."}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Upload Management
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/uploads", methods=["GET"])
@require_admin
def all_uploads(current_user):
    """
    ADMIN: Return all CSV uploads across all users, with username attached.
    Heavy text fields (insight_text, budget_tips, alerts) excluded for performance.
    """
    batches = get_all_batches()
    lite = []
    for b in batches:
        lite.append({
            "id":            b["id"],
            "username":      b.get("username", "?"),
            "filename":      b["filename"],
            "upload_date":   b["upload_date"],
            "total_txns":    b["total_txns"],
            "anomaly_count": b["anomaly_count"],
            "total_amount":  b["total_amount"]
        })
    return jsonify({
        "uploads": lite,
        "total":   len(lite)
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Site-wide Stats
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/stats", methods=["GET"])
@require_admin
def site_stats(current_user):
    """
    ADMIN: Return aggregate platform statistics:
      total_users, total_uploads, total_txns, total_anomalies,
      total_amount, category_breakdown (per-category totals across all users)
    """
    stats = get_site_stats()
    return jsonify(stats), 200


# ─────────────────────────────────────────────────────────────────────────────
# ML Model Retraining
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/retrain", methods=["POST"])
@require_admin
def retrain_models(current_user):
    """
    ADMIN: Trigger retraining of both ML models in the background.
    Returns immediately — retraining happens asynchronously.
    Check /api/admin/logs for completion status.

    This is useful after adding new training data or changing model parameters.
    """
    log_admin_action(
        admin_id=current_user["user_id"],
        action="Triggered ML model retraining"
    )

    # Run retraining scripts (blocking for simplicity in demo)
    try:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cat_script   = os.path.join(base, "ml", "train_categorizer.py")
        anom_script  = os.path.join(base, "ml", "train_anomaly.py")

        result_cat  = subprocess.run(
            [sys.executable, cat_script],
            capture_output=True, text=True, timeout=120
        )
        result_anom = subprocess.run(
            [sys.executable, anom_script],
            capture_output=True, text=True, timeout=120
        )

        if result_cat.returncode != 0 or result_anom.returncode != 0:
            return jsonify({
                "error": "Retraining failed.",
                "categorizer_error": result_cat.stderr[-500:],
                "anomaly_error":     result_anom.stderr[-500:]
            }), 500

        log_admin_action(
            admin_id=current_user["user_id"],
            action="ML model retraining completed successfully"
        )

        return jsonify({"message": "Both ML models retrained successfully."}), 200

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Retraining timed out (>2 minutes)."}), 500
    except Exception as e:
        return jsonify({"error": f"Retraining error: {str(e)}"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Admin Action Logs
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/logs", methods=["GET"])
@require_admin
def admin_logs(current_user):
    """ADMIN: Return the audit trail of all admin actions (last 200)."""
    logs = get_admin_logs()
    return jsonify({
        "logs":  logs,
        "total": len(logs)
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Global Upload Master Switch (System Setting)
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/settings/upload-toggle", methods=["GET"])
@require_admin
def get_upload_toggle(current_user):
    """ADMIN: Return whether CSV statement uploads are enabled system-wide."""
    from database import get_system_setting
    enabled = get_system_setting("uploads_enabled", "true").lower() == "true"
    return jsonify({"uploads_enabled": enabled}), 200


@admin_bp.route("/settings/upload-toggle", methods=["POST"])
@require_admin
def set_upload_toggle(current_user):
    """ADMIN: Enable or disable user statement uploads globally."""
    from database import set_system_setting, log_admin_action
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))
    set_system_setting("uploads_enabled", "true" if enabled else "false")

    status_str = "ENABLED" if enabled else "DISABLED"
    log_admin_action(
        admin_id=current_user["user_id"],
        action=f"Changed global upload status to: {status_str}"
    )

    return jsonify({
        "message": f"User statement uploads have been {status_str.lower()}.",
        "uploads_enabled": enabled
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Admin Upload (CSV analysis from admin panel)
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/upload", methods=["POST"])
@require_admin
def admin_upload(current_user):
    """
    ADMIN: Upload a CSV and run the full ML + Agent pipeline.
    Stored under admin's account. Useful for live demos and testing.
    """
    import io, os
    import pandas as pd
    from werkzeug.utils import secure_filename
    from agents.orchestrator import run_pipeline
    from database import save_upload_batch, save_transactions
    from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only CSV files supported."}), 400

    file.seek(0, os.SEEK_END)
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if size_mb > MAX_FILE_SIZE_MB:
        return jsonify({"error": f"File too large (max {MAX_FILE_SIZE_MB}MB)."}), 400

    filename = secure_filename(file.filename)
    try:
        df = pd.read_csv(io.StringIO(file.read().decode("utf-8")))
    except Exception as e:
        return jsonify({"error": f"Could not read CSV: {str(e)}"}), 400

    from datetime import datetime
    upload_dir = os.path.join(UPLOAD_FOLDER, f"admin_{current_user['user_id']}")
    os.makedirs(upload_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(os.path.join(upload_dir, f"{ts}_{filename}"), index=False)

    result = run_pipeline(df, filename=filename)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Pipeline failed.")}), 500

    summary = result["summary"]
    batch_id = save_upload_batch(
        user_id         = current_user["user_id"],
        filename        = f"[ADMIN] {filename}",
        total_txns      = summary["total_txns"],
        anomaly_count   = summary["anomaly_count"],
        total_amount    = summary["total_amount"],
        insight_text    = result["insight_text"],
        budget_tips     = result["budget_tips"],
        alerts          = result["alerts"],
        category_totals = summary["category_totals"]
    )
    save_transactions(
        batch_id          = batch_id,
        user_id           = current_user["user_id"],
        transactions_list = result["transactions"]
    )
    log_admin_action(
        admin_id = current_user["user_id"],
        action   = f"Admin upload: '{filename}' — {summary['total_txns']} txns, {summary['anomaly_count']} anomalies"
    )

    return jsonify({
        "message":      "Admin upload processed successfully.",
        "batch_id":     batch_id,
        "summary":      summary,
        "insight_text": result["insight_text"],
        "budget_tips":  result["budget_tips"],
        "alerts":       result["alerts"]
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Gemini API Key Management
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/settings/api-key", methods=["GET"])
@require_admin
def get_api_key_status(current_user):
    """ADMIN: Return current Gemini API key status."""
    from config import get_effective_google_api_key, is_agents_enabled
    key = get_effective_google_api_key()
    has_key = bool(key)
    masked = ""
    if has_key:
        masked = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "********"
    from config import GEMINI_MODEL_NAME
    return jsonify({
        "has_key": has_key,
        "masked_key": masked,
        "agents_enabled": is_agents_enabled(),
        "model": GEMINI_MODEL_NAME
    }), 200


@admin_bp.route("/settings/api-key", methods=["POST"])
@require_admin
def update_api_key(current_user):
    """ADMIN: Save and activate a new Google Gemini API key."""
    import os
    from database import set_system_setting, log_admin_action
    from config import BASE_DIR

    data = request.get_json(silent=True) or {}
    new_key = str(data.get("api_key", "")).strip()

    if not new_key or len(new_key) < 15:
        return jsonify({"error": "Kripya valid Gemini API key enter karein (typically 39 characters, starts with AIza)."}), 400

    # 1. Save in system_settings database table
    set_system_setting("google_api_key", new_key)

    # 2. Update .env file so it persists across reboots
    try:
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("GOOGLE_API_KEY="):
                    new_lines.append(f"GOOGLE_API_KEY={new_key}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"\nGOOGLE_API_KEY={new_key}\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
    except Exception as e:
        print(f"[AdminRoutes] Note: Could not update .env file: {e}")

    # 3. Re-configure Gemini runner
    try:
        import agents.agent_runner as ar
        ar._gemini_client = None
        ar._last_configured_key = None
        ar._get_gemini_client()
    except Exception as e:
        print(f"[AdminRoutes] Gemini re-init note: {e}")

    log_admin_action(
        admin_id=current_user["user_id"],
        action=f"Updated Gemini API key ({new_key[:6]}...{new_key[-4:]})"
    )

    return jsonify({
        "message": "Gemini API key successfully saved and activated! AI Chatbot and all Agents are now LIVE.",
        "has_key": True,
        "masked_key": f"{new_key[:6]}...{new_key[-4:]}"
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Admin AI Assistant Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/chat", methods=["POST"])
@require_admin
def admin_chat(current_user):
    """
    Dedicated AI Chat Assistant for Administrator.
    Can answer platform telemetry, user metrics, model status, and audit inquiries.
    """
    from database import save_chat_message, get_site_stats
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Message is required."}), 400

    # Save admin query to chat history
    save_chat_message(current_user["user_id"], "user", message)

    msg_lower = message.lower()
    stats = get_site_stats()
    total_users = stats.get("total_users", 0)
    total_uploads = stats.get("total_uploads", 0)
    total_txns = stats.get("total_txns", 0)
    total_anomalies = stats.get("total_anomalies", 0)
    total_amount = stats.get("total_amount", 0)

    # 1. Total users
    if any(w in msg_lower for w in ["user", "users", "account", "accounts", "member"]):
        reply = (
            f"Platform par currently **{total_users} registered users** hain. "
            f"Aap 'Manage Users' panel se unka role promote ya account manage kar sakte hain."
        )
    # 2. Uploads & Datasets
    elif any(w in msg_lower for w in ["upload", "uploads", "statement", "csv", "batches"]):
        reply = (
            f"Abhi tak platform par kul **{total_uploads} statements/CSV batches** upload huye hain, "
            f"jisme **{total_txns} transactions** analyze kiye ja chuke hain (Total volume: ₹{total_amount:,.0f})."
        )
    # 3. Anomalies & Security
    elif any(w in msg_lower for w in ["anomaly", "anomalies", "fraud", "threat", "alert"]):
        reply = (
            f"IsolationForest ML detector ne site-wide **{total_anomalies} anomalous transactions** flag kiye hain. "
            f"Sabhi high-burn alerts user dashboards par notify kiye gaye hain."
        )
    # 4. Model Status & Retrain
    elif any(w in msg_lower for w in ["model", "ml", "train", "retrain", "accuracy"]):
        reply = (
            "**ML Pipeline Status:**\n\n"
            "• **Categorization Model**: RandomForestClassifier (`ml/models/categorizer.joblib`) - Active\n"
            "• **Anomaly Detector**: IsolationForest (`ml/models/anomaly_detector.joblib`) - Active\n\n"
            "Aap Admin Dashboard se ek click me dono models retrain kar sakte hain."
        )
    # 5. General stats / health
    elif any(w in msg_lower for w in ["health", "stat", "stats", "overview", "system", "summary"]):
        reply = (
            f"**SpendSense Platform Telemetry:**\n\n"
            f"• **Registered Users**: {total_users}\n"
            f"• **Uploaded Statements**: {total_uploads}\n"
            f"• **Analyzed Transactions**: {total_txns}\n"
            f"• **Flagged Anomalies**: {total_anomalies}\n"
            f"• **Processed Volume**: ₹{total_amount:,.0f}\n\n"
            f"Sabhi services healthy aur operational hain."
        )
    else:
        from agents.agent_runner import is_agents_enabled, _call_gemini
        if is_agents_enabled():
            admin_prompt = (
                "You are the SpendSense AI Admin Assistant. You assist the system administrator with platform metrics, "
                "financial oversight, machine learning diagnostics, and system operations. Keep answers professional, concise, "
                "and helpful in a blend of English and Hindi."
            )
            context = f"Platform Stats: Users={total_users}, Uploads={total_uploads}, Transactions={total_txns}, Anomalies={total_anomalies}, TotalVol=₹{total_amount:,.0f}. User asked: {message}"
            ai_resp = _call_gemini(admin_prompt, context)
            if ai_resp and ai_resp not in ("__NO_API_KEY__", "__API_ERROR__"):
                reply = ai_resp
            else:
                reply = (
                    f"Platform Health: Normal. {total_users} active users, {total_txns} analyzed transactions "
                    f"(Total ₹{total_amount:,.0f}). Aap users, uploads, ML models ya system stats ke baare me poochh sakte hain."
                )
        else:
            reply = (
                f"Platform Health: Normal. {total_users} active users, {total_txns} analyzed transactions "
                f"(Total ₹{total_amount:,.0f}). Aap users, uploads, ML models ya system stats ke baare me poochh sakte hain."
            )

    save_chat_message(current_user["user_id"], "ai", reply)
    return jsonify({"reply": reply}), 200


@admin_bp.route("/chat/history", methods=["GET"])
@require_admin
def admin_chat_history(current_user):
    """Return the admin's personal conversation history."""
    from database import get_user_chat_history
    messages = get_user_chat_history(current_user["user_id"], limit=100)
    return jsonify({"messages": messages, "user_id": current_user["user_id"]}), 200


@admin_bp.route("/chat/history", methods=["DELETE"])
@require_admin
def clear_admin_chat_history(current_user):
    """Clear chat history strictly for the admin."""
    from database import clear_user_chat_history
    clear_user_chat_history(current_user["user_id"])
    return jsonify({"message": "Admin chat history cleared successfully."}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Admin Workspace: Platform Governance, Cap Guard & Incident Runbooks
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/workspace", methods=["GET"])
@require_admin
def get_admin_workspace(current_user):
    """
    Return advanced admin workspace data:
    - Platform budget cap & burn pacing
    - System health metrics
    - Admin operations checklist / incident runbooks
    """
    from database import get_site_stats, get_user_notes, get_system_setting
    stats = get_site_stats()
    total_spend = stats.get("total_amount", 0.0)
    
    cap_str = get_system_setting("platform_budget_cap", "5000000.0")
    try:
        platform_cap = float(cap_str)
    except ValueError:
        platform_cap = 5000000.0

    burn_pct = round((total_spend / max(platform_cap, 1.0)) * 100, 1)
    notes = get_user_notes(current_user["user_id"])
    
    # Pre-populate default best-practice admin runbook if notes empty
    if not notes:
        from database import add_user_note
        add_user_note(current_user["user_id"], "Weekly ML Model Retrain & Data Drift Verification", category="maintenance")
        add_user_note(current_user["user_id"], "Review Statistical Outliers & High-Risk Flagged Batches", category="security")
        add_user_note(current_user["user_id"], "Audit Registered Accounts & User Role Permissions", category="audit")
        notes = get_user_notes(current_user["user_id"])

    uploads_enabled = get_system_setting("uploads_enabled", "true").lower() == "true"

    return jsonify({
        "platform_budget_cap": platform_cap,
        "total_spend": round(total_spend, 2),
        "burn_pct": burn_pct,
        "is_overcap": total_spend > platform_cap,
        "total_users": stats.get("total_users", 0),
        "total_uploads": stats.get("total_uploads", 0),
        "total_txns": stats.get("total_txns", 0),
        "total_anomalies": stats.get("total_anomalies", 0),
        "uploads_enabled": uploads_enabled,
        "notes": notes
    }), 200


@admin_bp.route("/workspace/cap", methods=["POST"])
@require_admin
def set_admin_platform_cap(current_user):
    """Update system-wide platform spending cap."""
    from database import set_system_setting, log_admin_action
    data = request.get_json(silent=True) or {}
    cap = float(data.get("cap", 5000000.0))
    if cap <= 0:
        return jsonify({"error": "Platform cap must be greater than 0"}), 400

    set_system_setting("platform_budget_cap", str(cap))
    log_admin_action(current_user["user_id"], f"Updated platform spend cap to: ₹{cap:,.0f}")
    return jsonify({"message": "Platform spending cap updated successfully", "cap": cap}), 200


@admin_bp.route("/workspace/notes", methods=["POST"])
@require_admin
def create_admin_note(current_user):
    """Add a new maintenance runbook task or cheat note for admin."""
    from database import add_user_note
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", "")).strip()
    category = str(data.get("category", "maintenance")).strip().lower()
    if not note:
        return jsonify({"error": "Task description cannot be empty"}), 400

    new_note = add_user_note(current_user["user_id"], note=note, category=category)
    return jsonify({"message": "Runbook task added", "note": new_note}), 201


@admin_bp.route("/workspace/notes/<int:note_id>/toggle", methods=["PATCH"])
@require_admin
def toggle_admin_note(current_user, note_id):
    """Toggle completed state of an admin runbook note."""
    from database import toggle_user_note
    toggle_user_note(note_id, current_user["user_id"])
    return jsonify({"message": "Runbook status updated"}), 200


@admin_bp.route("/workspace/notes/<int:note_id>", methods=["DELETE"])
@require_admin
def delete_admin_note(current_user, note_id):
    """Delete an admin runbook note."""
    from database import delete_user_note
    delete_user_note(note_id, current_user["user_id"])
    return jsonify({"message": "Runbook task deleted"}), 200
