"""
SpendSense AI — Database Layer
================================
Uses Python's built-in sqlite3 — no external ORM required.
All table creation, user management, and upload/transaction
storage functions live here.

Tables:
  users           — registered accounts (user & admin roles)
  upload_batches  — each CSV upload session + agent outputs
  transactions    — individual transaction rows from uploads
  admin_logs      — audit trail of admin actions
"""

import sqlite3
import os
from datetime import datetime
import json
from config import DB_PATH


# ─────────────────────────────────────────────────────────────────────────────
# Connection Helper
# ─────────────────────────────────────────────────────────────────────────────

def get_connection():
    """Return a new SQLite connection with row_factory for dict-like rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # allows row["column_name"] access
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Database Initialization
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    """
    Create all tables if they do not exist.
    Safe to call on every app start — uses CREATE TABLE IF NOT EXISTS.
    Also seeds the default admin account on first run.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ── Table 1: users ────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'user',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Table 2: upload_batches ───────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_batches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            filename        TEXT    NOT NULL,
            upload_date     TEXT    NOT NULL DEFAULT (datetime('now')),
            total_txns      INTEGER DEFAULT 0,
            anomaly_count   INTEGER DEFAULT 0,
            total_amount    REAL    DEFAULT 0.0,
            insight_text    TEXT    DEFAULT '',
            budget_tips     TEXT    DEFAULT '[]',
            alerts          TEXT    DEFAULT '[]',
            category_totals TEXT    DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Table 3: transactions ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id            INTEGER NOT NULL,
            user_id             INTEGER NOT NULL,
            date                TEXT,
            merchant            TEXT,
            description         TEXT    DEFAULT '',
            amount              REAL    DEFAULT 0.0,
            predicted_category  TEXT    DEFAULT '',
            final_category      TEXT    DEFAULT '',
            confidence          REAL    DEFAULT 0.0,
            is_anomaly          INTEGER DEFAULT 0,
            anomaly_score       REAL    DEFAULT 0.0,
            FOREIGN KEY (batch_id) REFERENCES upload_batches(id) ON DELETE CASCADE
        )
    """)

    # ── Table 4: admin_logs ───────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id    INTEGER,
            action      TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Table 5: system_settings ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # ── Table 6: chat_messages (User-scoped Chat History) ─────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            role        TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Table 7: user_goals (Monthly Budget & Savings Targets) ────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_goals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER UNIQUE NOT NULL,
            monthly_budget  REAL    NOT NULL DEFAULT 50000.0,
            savings_target  REAL    NOT NULL DEFAULT 10000.0,
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── Table 8: user_notes (Financial Cheat Notes & Rules) ───────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            note        TEXT    NOT NULL,
            category    TEXT    DEFAULT 'memo',
            is_done     INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

    # Seed default admin account (only on first run)
    _seed_admin()


def _seed_admin():
    """Create the default admin account if it doesn't already exist."""
    from config import DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD
    from auth import hash_password

    if not get_user_by_username(DEFAULT_ADMIN_USERNAME):
        create_user(
            username=DEFAULT_ADMIN_USERNAME,
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            role="admin"
        )
        print(f"[DB] Default admin created: {DEFAULT_ADMIN_USERNAME}")


# ─────────────────────────────────────────────────────────────────────────────
# User CRUD
# ─────────────────────────────────────────────────────────────────────────────

def create_user(username, email, password_hash, role="user"):
    """Insert a new user. Returns the new user's id, or None on failure."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        return None   # username or email already exists


def get_user_by_username(username):
    """Return a user row dict by username, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    """Return a user row dict by id, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    """Return a user row dict by email, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    """ADMIN: Return all users (without passwords)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id):
    """ADMIN: Delete a user and all their data (CASCADE handles related rows)."""
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def update_user_password(username: str, new_hash: str) -> bool:
    """
    Update a user's password hash by username.
    Returns True on success, False if user not found.
    Used by the forgot-password flow.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = ? WHERE username = ?",
        (new_hash, username)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# Upload Batch CRUD
# ─────────────────────────────────────────────────────────────────────────────

def save_upload_batch(user_id, filename, total_txns, anomaly_count,
                      total_amount, insight_text, budget_tips, alerts,
                      category_totals):
    """
    Save one complete pipeline run (one CSV upload) to the database.
    budget_tips and alerts are Python lists — serialized to JSON strings.
    category_totals is a Python dict — serialized to JSON string.
    Returns the new batch_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO upload_batches
            (user_id, filename, total_txns, anomaly_count, total_amount,
             insight_text, budget_tips, alerts, category_totals)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, filename, total_txns, anomaly_count, total_amount,
        insight_text,
        json.dumps(budget_tips),
        json.dumps(alerts),
        json.dumps(category_totals)
    ))
    conn.commit()
    batch_id = cursor.lastrowid
    conn.close()
    return batch_id


def get_user_batches(user_id):
    """Return all upload batches for a user, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM upload_batches WHERE user_id = ? ORDER BY upload_date DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    batches = []
    for r in rows:
        b = dict(r)
        b["budget_tips"]     = json.loads(b["budget_tips"])
        b["alerts"]          = json.loads(b["alerts"])
        b["category_totals"] = json.loads(b["category_totals"])
        batches.append(b)
    return batches


def get_latest_batch(user_id):
    """Return the most recent upload batch for a user."""
    batches = get_user_batches(user_id)
    return batches[0] if batches else None


def get_all_batches():
    """ADMIN: Return all upload batches across all users."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT ub.*, u.username
        FROM upload_batches ub
        JOIN users u ON ub.user_id = u.id
        ORDER BY ub.upload_date DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        b = dict(r)
        b["budget_tips"]     = json.loads(b["budget_tips"])
        b["alerts"]          = json.loads(b["alerts"])
        b["category_totals"] = json.loads(b["category_totals"])
        result.append(b)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Transaction CRUD
# ─────────────────────────────────────────────────────────────────────────────

def save_transactions(batch_id, user_id, transactions_list):
    """
    Bulk-insert a list of transaction dicts into the transactions table.
    Each dict must have: date, merchant, description, amount,
    predicted_category, final_category, confidence, is_anomaly, anomaly_score
    """
    conn = get_connection()
    conn.executemany("""
        INSERT INTO transactions
            (batch_id, user_id, date, merchant, description, amount,
             predicted_category, final_category, confidence,
             is_anomaly, anomaly_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            batch_id, user_id,
            t.get("date", ""), t.get("merchant", ""), t.get("description", ""),
            float(t.get("amount", 0)),
            t.get("predicted_category", ""), t.get("final_category", ""),
            float(t.get("confidence", 0)),
            int(t.get("is_anomaly", 0)), float(t.get("anomaly_score", 0))
        )
        for t in transactions_list
    ])
    conn.commit()
    conn.close()


def get_user_transactions(user_id, page=1, per_page=20, category=None,
                          anomaly_only=False):
    """
    Return paginated transactions for a user.
    Supports optional filtering by category and anomaly flag.
    Returns: {"transactions": [...], "total": int, "page": int, "pages": int}
    """
    offset = (page - 1) * per_page
    filters = ["user_id = ?"]
    params  = [user_id]

    if category:
        filters.append("final_category = ?")
        params.append(category)
    if anomaly_only:
        filters.append("is_anomaly = 1")

    where = " AND ".join(filters)

    conn = get_connection()
    total = conn.execute(
        f"SELECT COUNT(*) FROM transactions WHERE {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM transactions WHERE {where} ORDER BY date DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    conn.close()

    return {
        "transactions": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": (total + per_page - 1) // per_page
    }


def get_all_user_transactions(user_id):
    """Return all transactions for a user ordered by date ASC."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY date ASC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Admin Logs
# ─────────────────────────────────────────────────────────────────────────────

def set_system_setting(key: str, value: str):
    """Save or update a system configuration key-value pair."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO system_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def get_system_setting(key: str, default: str = "true") -> str:
    """Retrieve a system configuration value by key."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def log_admin_action(admin_id, action):
    """Record an admin action for the audit trail."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO admin_logs (admin_id, action) VALUES (?, ?)",
        (admin_id, action)
    )
    conn.commit()
    conn.close()


def get_admin_logs():
    """Return all admin log entries, newest first."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT al.*, u.username as admin_name
        FROM admin_logs al
        LEFT JOIN users u ON al.admin_id = u.id
        ORDER BY al.timestamp DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Site-wide Stats (Admin)
# ─────────────────────────────────────────────────────────────────────────────

def get_site_stats():
    """ADMIN: Return aggregate statistics across the entire platform."""
    conn = get_connection()
    stats = {}
    stats["total_users"]    = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'user'"
    ).fetchone()[0]
    stats["total_uploads"]  = conn.execute(
        "SELECT COUNT(*) FROM upload_batches"
    ).fetchone()[0]
    stats["total_txns"]     = conn.execute(
        "SELECT COUNT(*) FROM transactions"
    ).fetchone()[0]
    stats["total_anomalies"]= conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE is_anomaly = 1"
    ).fetchone()[0]
    stats["total_amount"]   = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions"
    ).fetchone()[0]

    # Category breakdown across all users
    rows = conn.execute("""
        SELECT final_category, COUNT(*) as count, SUM(amount) as total
        FROM transactions
        WHERE final_category != ''
        GROUP BY final_category
        ORDER BY total DESC
    """).fetchall()
    stats["category_breakdown"] = [dict(r) for r in rows]

    conn.close()
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# User Chat History Management
# ─────────────────────────────────────────────────────────────────────────────

def save_chat_message(user_id: int, role: str, message: str) -> int:
    """Save a user or AI chat message for the specified user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_messages (user_id, role, message)
        VALUES (?, ?, ?)
    """, (user_id, role, str(message)))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def get_user_chat_history(user_id: int, limit: int = 100) -> list:
    """Retrieve chat history for a specific user in chronological order."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, role, message, created_at
        FROM chat_messages
        WHERE user_id = ?
        ORDER BY id ASC
        LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_user_chat_history(user_id: int):
    """Delete all chat history for a specific user."""
    conn = get_connection()
    conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Workspace: Budget Goals & Financial Cheat Notes
# ─────────────────────────────────────────────────────────────────────────────

def get_user_goal(user_id: int) -> dict:
    """Retrieve the monthly budget and savings goal for a user."""
    conn = get_connection()
    row = conn.execute("""
        SELECT monthly_budget, savings_target, updated_at
        FROM user_goals
        WHERE user_id = ?
    """, (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    # Default values if not yet configured
    return {
        "monthly_budget": 50000.0,
        "savings_target": 10000.0,
        "updated_at": ""
    }


def set_user_goal(user_id: int, monthly_budget: float, savings_target: float = 10000.0) -> dict:
    """Save or update the user's monthly budget goal."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO user_goals (user_id, monthly_budget, savings_target, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            monthly_budget = excluded.monthly_budget,
            savings_target = excluded.savings_target,
            updated_at     = datetime('now')
    """, (user_id, float(monthly_budget), float(savings_target)))
    conn.commit()
    conn.close()
    return get_user_goal(user_id)


def get_user_notes(user_id: int) -> list:
    """Retrieve all cheat notes and reminders for a user."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, note, category, is_done, created_at
        FROM user_notes
        WHERE user_id = ?
        ORDER BY is_done ASC, id DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_user_note(user_id: int, note: str, category: str = "memo") -> dict:
    """Add a new cheat note or reminder."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_notes (user_id, note, category, is_done)
        VALUES (?, ?, ?, 0)
    """, (user_id, str(note).strip(), category))
    note_id = cursor.lastrowid
    conn.commit()
    row = conn.execute("SELECT id, note, category, is_done, created_at FROM user_notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def toggle_user_note(note_id: int, user_id: int) -> bool:
    """Toggle completed/pending status of a note."""
    conn = get_connection()
    conn.execute("""
        UPDATE user_notes
        SET is_done = CASE WHEN is_done = 1 THEN 0 ELSE 1 END
        WHERE id = ? AND user_id = ?
    """, (note_id, user_id))
    conn.commit()
    conn.close()
    return True


def delete_user_note(note_id: int, user_id: int) -> bool:
    """Delete a user note."""
    conn = get_connection()
    conn.execute("DELETE FROM user_notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    conn.close()
    return True
