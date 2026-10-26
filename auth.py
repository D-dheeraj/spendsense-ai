"""
SpendSense AI — Authentication Layer
======================================
Handles:
  • Password hashing with bcrypt
  • JWT token creation and verification
  • Route protection decorators for User and Admin roles

Flow:
  1. User registers → password is hashed and stored
  2. User logs in → JWT token returned to browser
  3. Browser sends token in Authorization header on every request
  4. @require_auth / @require_admin decorators verify the token
"""

import jwt
import bcrypt
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta, timezone
from config import SECRET_KEY, JWT_EXPIRY_SECONDS, JWT_ALGORITHM


# ─────────────────────────────────────────────────────────────────────────────
# Password Hashing
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(plain_text: str) -> str:
    """
    Hash a plain-text password using bcrypt.
    Returns a string (bcrypt hash) safe to store in the database.
    bcrypt automatically salts — never store plain passwords.
    """
    return bcrypt.hashpw(
        plain_text.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def check_password(plain_text: str, hashed: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.
    Returns True if they match, False otherwise.
    """
    return bcrypt.checkpw(
        plain_text.encode("utf-8"),
        hashed.encode("utf-8")
    )


# ─────────────────────────────────────────────────────────────────────────────
# JWT Token Management
# ─────────────────────────────────────────────────────────────────────────────

def create_token(user_id: int, username: str, role: str) -> str:
    """
    Create a signed JWT token containing:
      user_id  — numeric database ID
      username — display name
      role     — 'user' or 'admin'
      exp      — expiry timestamp (1 hour from now)

    The token is a signed string the client stores in localStorage.
    The server verifies the signature on every protected request.
    """
    payload = {
        "user_id":  user_id,
        "username": username,
        "role":     role,
        "exp":      datetime.now(timezone.utc) + timedelta(seconds=JWT_EXPIRY_SECONDS),
        "iat":      datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Returns the payload dict on success.
    Raises jwt.ExpiredSignatureError if expired.
    Raises jwt.InvalidTokenError if tampered or malformed.
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


def _extract_token_from_request() -> "str | None":
    """
    Extract the JWT token from the Authorization header.
    Expected format:  Authorization: Bearer <token>
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Route Protection Decorators
# ─────────────────────────────────────────────────────────────────────────────

def require_auth(f):
    """
    Decorator: protects a route — any logged-in user (user OR admin) can access.
    On success, injects `current_user` dict into the wrapped function's kwargs.

    Usage:
        @app.route('/protected')
        @require_auth
        def protected_route(current_user):
            return f"Hello {current_user['username']}"
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_request()
        if not token:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        try:
            payload = decode_token(token)
            kwargs["current_user"] = payload
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired. Please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token. Please log in again."}), 401
    return decorated


def require_admin(f):
    """
    Decorator: protects a route — ONLY users with role='admin' can access.
    Returns 403 Forbidden for regular users even if they are logged in.

    Usage:
        @app.route('/admin/users')
        @require_admin
        def admin_users(current_user):
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_request()
        if not token:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        try:
            payload = decode_token(token)
            if payload.get("role") != "admin":
                return jsonify({"error": "Admin access required."}), 403
            kwargs["current_user"] = payload
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired. Please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token. Please log in again."}), 401
    return decorated
