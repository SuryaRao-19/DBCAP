# Security Architecture & Hardening Guide

## Overview
The EV Charging Station Management System (**EV ChargeNet**) enforces defense-in-depth across authentication, authorization, database transactions, session cookies, CSRF protection, and third-party API proxying.

---

## 1. Authentication & Role-Based Access Control (RBAC)

- **Public Registration Lockdown**: `/register` strictly enforces `role="OWNER"` (`allow_admin=False` in `app/services/auth_service.py`). The registration template contains no role selector, and any POST payload attempting to pass a non-`OWNER` role is rejected with `HTTP 403`.
- **Protected Admin Provisioning**: New administrator accounts can only be created via the Admin Portal (`POST /admin/users/create`) by an authenticated `ADMIN` user, recorded in `AuditLogs`.
- **Per-Request Account Status Enforcement**: `app/routes/auth_middleware.py` (`_verify_active_session_user`) checks `Users.account_status == 'ACTIVE'` on every authenticated request. Deactivated users lose access immediately (HTML routes redirect after clearing the session; `/api/*` routes return `401`).
- **Password Hashing**: Passwords are hashed using Werkzeug `scrypt` (`generate_password_hash` / `check_password_hash`). Legacy hardcoded `DEMO_HASH_` password bypasses have been removed.

---

## 2. Insecure Direct Object Reference (IDOR) Prevention

Every state-changing and data-reading endpoint verifies ownership against `session["user_id"]`:

- **Bookings**: Cancelling a booking enforces `WHERE booking_id = %s AND user_id = %s`.
- **Vehicles**: Editing or deleting a vehicle verifies `user_id` ownership in `app/services/vehicle_service.py`.
- **Charging Sessions (`start_session` & `complete_session`)**:
  - Verifies vehicle ownership and locks both the target `ChargingPoints` row and user's active sessions with `SELECT ... FOR UPDATE`.
  - When a `booking_id` is linked, verifies `Bookings.user_id == current_user_id`, `Bookings.point_id == selected_point_id`, and `Bookings.booking_status IN ('PENDING', 'CONFIRMED')`.
- **Payments (`record_payment`)**:
  - Verifies `ChargingSessions.user_id == current_user_id` before allowing payment settlement (returns `403` across users, `404` for unknown session IDs).
  - Enforces `session_status == 'COMPLETED'` and uses server-computed `ChargingSessions.total_cost` rather than trusting client-supplied amounts.
- **Receipts**: `get_session_receipt` scopes queries by `user_id` for EV owners.

> **Payment Feature Classification**: Payment settlement in this system is a **Simulated Financial Ledger**. It records billing settlements (`UPI`, `CARD`, `WALLET`, `CASH`) in the MySQL `Payments` table with server-computed costs and transaction references. It is **not** connected to a live merchant payment gateway (Razorpay/Stripe); real card processing would require adding a signed payment-gateway checkout and webhook verification layer.

---

## 3. CSRF Protection

- Global `CSRFProtect` (`Flask-WTF`) is initialized in `app/__init__.py`.
- All state-changing HTML forms include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- `app/templates/base.html` exposes `<meta name="csrf-token" content="{{ csrf_token() }}">`, and `app/static/js/main.js` provides `getCsrfToken()` for AJAX requests.
- Missing or invalid CSRF tokens return `400` cleanly via `@app.errorhandler(CSRFError)` (JSON for `/api/*`, flash + `400` redirect/error handling for web routes).

---

## 4. Session Cookies & Secret Management

Configured in `app/__init__.py`:
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = "Lax"`
- `SESSION_COOKIE_SECURE = True` when `FLASK_ENV=production` or running on Vercel (`VERCEL=1`)
- `PERMANENT_SESSION_LIFETIME = timedelta(hours=2)`
- Session cleared before setting authenticated claims (`session.clear()`) on login and cleared cleanly on `/logout`.

### Production Fail-Fast Secrets
In production (`FLASK_ENV=production` or `VERCEL` environment):
- `SECRET_KEY` **must** be set via environment variables (min 32 random bytes recommended; `python -c "import secrets; print(secrets.token_hex(32))"`). The app raises `RuntimeError` if missing or set to a placeholder.
- Demo credentials were removed from `login.html`, `run.py`, and JavaScript.
- `.env` is excluded via `.gitignore` and `.vercelignore`.

