"""
SpendSense AI — Authentication Routes
========================================
Endpoints:
  POST /api/auth/register  — create a new user account
  POST /api/auth/login     — login and receive JWT token
  GET  /api/auth/me        — get current user info (requires auth)
"""

from flask import Blueprint, request, jsonify
from auth import hash_password, check_password, create_token, require_auth
from database import create_user, get_user_by_username, get_user_by_email

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user account.

    Request body (JSON):
      { "username": "dheeraj", "email": "d@example.com", "password": "mypass" }

    Response (success):
      { "message": "Account created successfully." }

    Response (error):
      { "error": "Username already taken." }
    """
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip().lower()
    email    = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    # ── Validation ────────────────────────────────────────────────────────────
    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required."}), 400

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    if "@" not in email:
        return jsonify({"error": "Please enter a valid email address."}), 400

    # ── Check uniqueness ──────────────────────────────────────────────────────
    if get_user_by_username(username):
        return jsonify({"error": "Username is already taken."}), 409

    if get_user_by_email(email):
        return jsonify({"error": "An account with this email already exists."}), 409

    # ── Create user ───────────────────────────────────────────────────────────
    password_hash = hash_password(password)
    user_id = create_user(username=username, email=email,
                          password_hash=password_hash, role="user")

    if not user_id:
        return jsonify({"error": "Registration failed. Please try again."}), 500

    return jsonify({"message": "Account created successfully. Please log in."}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Login with username + password. Returns a JWT token.

    Request body (JSON):
      { "username": "dheeraj", "password": "mypass" }

    Response (success):
      {
        "token": "<JWT>",
        "user": { "id": 1, "username": "dheeraj", "role": "user" }
      }
    """
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    user = get_user_by_username(username)

    if not user or not check_password(password, user["password"]):
        return jsonify({"error": "Invalid username or password."}), 401

    token = create_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"]
    )

    return jsonify({
        "token": token,
        "user": {
            "id":       user["id"],
            "username": user["username"],
            "email":    user["email"],
            "role":     user["role"]
        }
    }), 200


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me(current_user):
    """
    Return the currently authenticated user's info.
    Used by the frontend on page load to verify token validity.
    """
    from database import get_user_by_id
    user = get_user_by_id(current_user["user_id"])
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({
        "id":       user["id"],
        "username": user["username"],
        "email":    user["email"],
        "role":     user["role"],
        "created_at": user["created_at"]
    }), 200


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """
    Reset a user's password without email verification (local/demo mode).

    Request body (JSON):
      {
        "username":     "dheeraj",
        "new_password": "newpass123",
        "confirm_password": "newpass123"
      }

    Response (success):
      { "message": "Password reset successfully." }

    Security note:
      In production, this would require an email OTP or token.
      For this demo/college project, we verify the username exists
      and apply the new password directly — suitable for local demo use.
    """
    data = request.get_json(silent=True) or {}

    username         = str(data.get("username", "")).strip().lower()
    new_password     = str(data.get("new_password", "")).strip()
    confirm_password = str(data.get("confirm_password", "")).strip()

    # ── Validation ────────────────────────────────────────────────────────────
    if not username or not new_password or not confirm_password:
        return jsonify({"error": "Username, new password, and confirmation are required."}), 400

    if new_password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400

    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    # ── Verify user exists ────────────────────────────────────────────────────
    user = get_user_by_username(username)
    if not user:
        # Don't reveal whether username exists (security best practice)
        return jsonify({"error": "If that username exists, the password has been reset."}), 200

    # ── Update password ───────────────────────────────────────────────────────
    from database import update_user_password
    new_hash = hash_password(new_password)
    success  = update_user_password(username, new_hash)

    if not success:
        return jsonify({"error": "Password reset failed. Please try again."}), 500

    return jsonify({"message": "Password reset successfully. Please log in with your new password."}), 200
