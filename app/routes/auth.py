"""
Authentication Routes
EV Charging Station Management System - Production Hardened
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.services.auth_service import authenticate_user, register_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        if session.get("role") == "ADMIN":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("owner.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        user, err = authenticate_user(email, password)
        if err:
            flash(err, "danger")
            return render_template("login.html", email=email)

        # Regenerate session cleanly after authentication
        session.clear()
        session.permanent = True
        session["user_id"] = user["user_id"]
        session["full_name"] = user["full_name"]
        session["email"] = user["email"]
        session["role"] = user["role"]

        flash(f"Welcome back, {user['full_name']}!", "success")
        if user["role"] == "ADMIN":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("owner.dashboard"))

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Reject any client attempt to submit an unauthorized role (e.g., ADMIN)
        submitted_role = request.form.get("role", "").strip().upper()
        if submitted_role and submitted_role != "OWNER":
            flash("Public registration is restricted to EV Owner accounts.", "danger")
            return render_template("register.html", full_name=full_name, email=email, phone=phone), 403

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", full_name=full_name, email=email, phone=phone)

        uid, err = register_user(full_name, email, phone, password, role="OWNER", allow_admin=False)
        if err:
            flash(err, "danger")
            return render_template("register.html", full_name=full_name, email=email, phone=phone)

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out securely.", "info")
    return redirect(url_for("auth.login"))
