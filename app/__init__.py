"""
Flask Application Factory
EV Charging Station Management System - Production Hardened
"""
import os
import secrets
from datetime import timedelta
from flask import Flask, render_template, request, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv

load_dotenv()

csrf = CSRFProtect()


def _is_production(app=None):
    """Determine if running in production mode (Vercel or FLASK_ENV=production)."""
    if app and app.config.get("TESTING"):
        return False
    flask_env = os.getenv("FLASK_ENV", "development").strip().lower()
    vercel = os.getenv("VERCEL", "").strip()
    return flask_env == "production" or vercel == "1"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    is_testing = bool(test_config and test_config.get("TESTING"))
    is_prod = False if is_testing else _is_production()

    secret_key = (
        (test_config.get("SECRET_KEY") if test_config else None)
        or os.getenv("SECRET_KEY", "").strip()
    )
    if not secret_key:
        if is_prod:
            raise RuntimeError("SECRET_KEY environment variable is required in production.")
        # Ephemeral per-process fallback for local dev/test only (never a static hardcoded secret)
        secret_key = secrets.token_hex(32)

    # Configuration
    app.config.from_mapping(
        SECRET_KEY=secret_key,
        MYSQL_HOST=os.getenv("MYSQL_HOST", "127.0.0.1"),
        MYSQL_PORT=int(os.getenv("MYSQL_PORT", 3306)),
        MYSQL_USER=os.getenv("MYSQL_USER", "root"),
        MYSQL_PASSWORD=os.getenv("MYSQL_PASSWORD", ""),
        MYSQL_DATABASE=os.getenv("MYSQL_DATABASE", "ev_charging_db"),
        DATABASE_URL=os.getenv("DATABASE_URL", "").strip(),
        MYSQL_SSL_CA=os.getenv("MYSQL_SSL_CA", "").strip(),
        SUPABASE_URL=os.getenv("SUPABASE_URL", "").strip(),
        SUPABASE_PUBLISHABLE_KEY=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        WEB3FORMS_ACCESS_KEY=os.getenv("WEB3FORMS_ACCESS_KEY", "").strip(),
        RAZORPAY_KEY_ID=os.getenv("RAZORPAY_KEY_ID", "").strip(),
        RAZORPAY_KEY_SECRET=os.getenv("RAZORPAY_KEY_SECRET", "").strip(),
        RAZORPAY_WEBHOOK_SECRET=os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip(),
        GOOGLE_MAPS_API_KEY=os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_prod,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=3600,
    )

    if test_config:
        app.config.update(test_config)

    if is_prod:
        has_db_url = bool(app.config.get("DATABASE_URL"))
        has_mysql_creds = all([
            app.config.get("MYSQL_HOST"),
            app.config.get("MYSQL_USER"),
            app.config.get("MYSQL_PASSWORD"),
            app.config.get("MYSQL_DATABASE"),
        ])
        if not (has_db_url or has_mysql_creds):
            raise RuntimeError("Production database configuration (DATABASE_URL or MYSQL_*) is missing.")

    csrf.init_app(app)

    # Register Blueprints
    from app.routes.public import public_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.owner import owner_bp
    from app.routes.api import api_bp
    from app.services.platform_service import get_platform_operator, get_verified_social_links

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(owner_bp, url_prefix="/owner")
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.context_processor
    def inject_platform_identity():
        return {
            "platform_operator": get_platform_operator(),
            "social_links": get_verified_social_links(),
            "google_maps_api_key": app.config.get("GOOGLE_MAPS_API_KEY", ""),
        }

    # Global Error Handlers
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"success": False, "error": "CSRF validation failed. Please refresh and try again."}), 400
        return render_template("error.html", code=400, message="Security check failed (invalid or missing CSRF token). Please go back, refresh the page, and try again."), 400

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Requested resource not found."}), 404
        return render_template("error.html", code=404, message="Requested page not found."), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Access Denied."}), 403
        return render_template("error.html", code=403, message="Access Denied: You do not have permission to access this resource."), 403

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "An internal server error occurred."}), 500
        return render_template("error.html", code=500, message="An internal database or server error occurred."), 500

    return app
