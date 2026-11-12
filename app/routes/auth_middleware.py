"""
Authentication and Role-Based Authorization Decorators
EV Charging Station Management System - Production Hardened
"""
from functools import wraps
from flask import session, redirect, url_for, flash, abort, request, jsonify
from app.db import query_one


def _verify_active_session_user():
    """
    Verify that the session user exists and remains ACTIVE in the database.
    Synchronizes session['role'] with the authoritative DB role.
    Returns (user_dict, error_response_or_None).
    """
    user_id = session.get("user_id")
    if not user_id:
        if request.path.startswith("/api/"):
            return None, (jsonify({"error": "Unauthorized. Please log in."}), 401)
        flash("Please log in to continue.", "warning")
        return None, redirect(url_for("auth.login", next=request.url))

    user = query_one(
        "SELECT user_id, role, account_status FROM Users WHERE user_id = %s",
        (user_id,)
    )
    if not user or user["account_status"] != "ACTIVE":
        session.clear()
        if request.path.startswith("/api/"):
            return None, (jsonify({"error": "Session invalidated: account is inactive or unavailable."}), 401)
        flash("Your session has ended because this account is inactive.", "danger")
        return None, redirect(url_for("auth.login"))

    session["role"] = user["role"]
    return user, None


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _, err_resp = _verify_active_session_user()
        if err_resp is not None:
            return err_resp
        return f(*args, **kwargs)
    return decorated_function


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user, err_resp = _verify_active_session_user()
            if err_resp is not None:
                return err_resp
            if user["role"] != role:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Forbidden. Insufficient role permissions."}), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_current_user_id():
    """Extract authenticated user_id from session securely (never from client params)."""
    return session.get("user_id")
