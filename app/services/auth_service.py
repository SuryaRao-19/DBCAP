"""
Authentication & User Management Service
EV Charging Station Management System - Production Hardened
"""
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import query_all, query_one, execute

VALID_ROLES = ("OWNER", "ADMIN")


def authenticate_user(email, password):
    """Verify user credentials with secure password hashing."""
    if not email or not password:
        return None, "Email and password are required."

    user = query_one(
        "SELECT user_id, full_name, email, phone, password_hash, role, account_status "
        "FROM Users WHERE email = %s",
        (email.strip().lower(),)
    )
    if not user:
        return None, "No account found with this email address."

    if user["account_status"] != "ACTIVE":
        return None, "This account is inactive. Please contact your system administrator."

    stored_hash = user["password_hash"]
    is_valid = False
    try:
        is_valid = check_password_hash(stored_hash, password)
    except Exception:
        is_valid = False

    if not is_valid:
        return None, "Invalid email or password."

    return user, None


def register_user(full_name, email, phone, password, role="OWNER", allow_admin=False):
    """
    Register a new user account with secure password hashing.
    Public registration is strictly restricted to the OWNER role unless
    allow_admin=True is explicitly supplied by an authenticated admin action.
    """
    if not full_name or not full_name.strip():
        return None, "Full name is required."
    if not email or not email.strip():
        return None, "Email address is required."

    normalized_role = (role or "OWNER").strip().upper()
    if normalized_role not in VALID_ROLES:
        return None, "Invalid account role specified."
    if normalized_role == "ADMIN" and not allow_admin:
        return None, "Administrator accounts cannot be created via public registration."

    email = email.strip().lower()
    existing = query_one("SELECT user_id FROM Users WHERE email = %s", (email,))
    if existing:
        return None, "An account with this email address already exists."

    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters long."

    hashed = generate_password_hash(password)
    user_id = execute(
        "INSERT INTO Users (full_name, email, phone, password_hash, role, account_status) "
        "VALUES (%s, %s, %s, %s, %s, 'ACTIVE')",
        (full_name.strip(), email, phone.strip() if phone else None, hashed, normalized_role)
    )
    return user_id, None


def create_user_by_admin(full_name, email, phone, password, role="OWNER"):
    """Protected administrative user/admin creation helper."""
    return register_user(
        full_name=full_name,
        email=email,
        phone=phone,
        password=password,
        role=role,
        allow_admin=True,
    )


def get_user_profile(user_id):
    """Retrieve user details by primary key."""
    return query_one(
        "SELECT user_id, full_name, email, phone, role, account_status, created_at "
        "FROM Users WHERE user_id = %s",
        (user_id,)
    )


def update_user_profile(user_id, full_name, phone, current_password=None, new_password=None):
    """Update user personal information and optionally change password."""
    user = query_one(
        "SELECT user_id, password_hash FROM Users WHERE user_id = %s",
        (user_id,)
    )
    if not user:
        return False, "User account not found."

    if new_password:
        if not current_password:
            return False, "Current password is required to set a new password."
        if not check_password_hash(user["password_hash"], current_password):
            return False, "Incorrect current password."
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters."

        new_hash = generate_password_hash(new_password)
        execute(
            "UPDATE Users SET full_name = %s, phone = %s, password_hash = %s WHERE user_id = %s",
            (full_name.strip(), phone.strip() if phone else None, new_hash, user_id)
        )
    else:
        execute(
            "UPDATE Users SET full_name = %s, phone = %s WHERE user_id = %s",
            (full_name.strip(), phone.strip() if phone else None, user_id)
        )

    return True, None


def get_all_users(role=None, status=None):
    """Admin view: Retrieve all users with vehicle, booking, and session counts."""
    sql = (
        "SELECT u.user_id, u.full_name, u.email, u.phone, u.role, u.account_status, u.created_at, "
        "       COUNT(DISTINCT v.vehicle_id) AS vehicle_count, "
        "       COUNT(DISTINCT b.booking_id) AS booking_count, "
        "       COUNT(DISTINCT cs.session_id) AS session_count "
        "FROM Users u "
        "LEFT JOIN Vehicles v ON v.user_id = u.user_id "
        "LEFT JOIN Bookings b ON b.user_id = u.user_id "
        "LEFT JOIN ChargingSessions cs ON cs.user_id = u.user_id "
        "WHERE 1=1 "
    )
    params = []
    if role:
        sql += " AND u.role = %s"
        params.append(role)
    if status:
        sql += " AND u.account_status = %s"
        params.append(status)

    sql += " GROUP BY u.user_id ORDER BY u.created_at DESC"
    return query_all(sql, params)


def toggle_user_status(user_id, admin_user_id):
    """Deactivate or activate a user account (protecting primary admin)."""
    if int(user_id) == int(admin_user_id):
        return False, "You cannot deactivate your own active administrator account."

    user = query_one("SELECT account_status FROM Users WHERE user_id = %s", (user_id,))
    if not user:
        return False, "User not found."

    new_status = "INACTIVE" if user["account_status"] == "ACTIVE" else "ACTIVE"
    execute("UPDATE Users SET account_status = %s WHERE user_id = %s", (new_status, user_id))
    return True, new_status
