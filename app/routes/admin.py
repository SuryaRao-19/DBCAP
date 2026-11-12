"""
Admin / Station Operator Routes
EV Charging Station Management System - DBMS Capstone Project
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.routes.auth_middleware import login_required, role_required, get_current_user_id
from app.services.station_service import (
    get_all_stations, get_station_by_id, create_station, update_station,
    get_all_charging_points, create_charging_point, update_charging_point, get_point_by_id
)
from app.services.booking_service import get_all_bookings
from app.services.session_service import get_all_sessions
from app.services.payment_service import get_all_payments
from app.services.auth_service import get_all_users, toggle_user_status, create_user_by_admin
from app.services.report_service import (
    get_admin_dashboard_metrics, get_monthly_revenue_report,
    get_monthly_energy_report, get_station_utilization_report,
    get_booking_status_distribution, get_system_health,
    get_admin_chart_analytics,
)
from app.services.audit_service import (
    log_audit_event, get_audit_logs, get_system_settings_list, update_system_setting
)
from app.services.contact_service import (
    get_contact_messages, update_contact_status, VALID_ENQUIRY_STATUSES
)
from app.services.station_import_service import (
    import_stations_from_csv, review_station_approval, get_pending_approval_stations
)
from app.services.platform_service import (
    get_data_sources, update_data_source, VALID_DATA_STATUSES
)

admin_bp = Blueprint("admin", __name__)



@admin_bp.before_request
@login_required
@role_required("ADMIN")
def enforce_admin_access():
    pass


@admin_bp.route("/dashboard")
def dashboard():
    metrics = get_admin_dashboard_metrics()
    recent_bookings = get_all_bookings()[:5]
    recent_sessions = get_all_sessions()[:5]
    charts = get_admin_chart_analytics()
    return render_template(
        "admin/dashboard.html",
        metrics=metrics,
        recent_bookings=recent_bookings,
        recent_sessions=recent_sessions,
        charts=charts,
    )


@admin_bp.route("/stations", methods=["GET", "POST"])
def stations():
    if request.method == "POST":
        station_name = request.form.get("station_name")
        address = request.form.get("address")
        city = request.form.get("city")
        state = request.form.get("state", "Delhi NCR")
        postal_code = request.form.get("postal_code")
        opening_time = request.form.get("opening_time", "06:00:00")
        closing_time = request.form.get("closing_time", "23:00:00")
        status = request.form.get("station_status", "ACTIVE")
        operator_name = request.form.get("operator_name", "Tata Power EZ Charge")
        verif_status = request.form.get("verification_status", "DEMO")
        lat_raw = request.form.get("latitude", "").strip()
        lng_raw = request.form.get("longitude", "").strip()
        source_url = request.form.get("source_url", "").strip() or None

        try:
            lat = float(lat_raw) if lat_raw else None
            lng = float(lng_raw) if lng_raw else None
        except ValueError:
            flash("Invalid latitude or longitude format.", "danger")
            return redirect(url_for("admin.stations"))

        if not station_name or not address or not city:
            flash("Station name, address, and city are required.", "danger")
        else:
            sid = create_station(
                station_name, address, city, opening_time, closing_time, status,
                state=state, postal_code=postal_code, latitude=lat, longitude=lng,
                operator_name=operator_name, source_url=source_url,
                verification_status=verif_status, approval_status="APPROVED",
            )
            log_audit_event(
                action="CREATE_STATION",
                entity_name="Stations",
                entity_id=sid,
                user_id=get_current_user_id(),
                details=f"Created station '{station_name}' in {city} (Status: {status})",
                ip_address=request.remote_addr
            )
            flash(f"Charging Station '{station_name}' created successfully.", "success")
        return redirect(url_for("admin.stations"))

    city_filter = request.args.get("city")
    status_filter = request.args.get("status")
    all_stations = get_all_stations(city=city_filter, status=status_filter, only_approved=False)
    pending_stations = get_pending_approval_stations()
    return render_template("admin/stations.html", stations=all_stations, pending_stations=pending_stations)


@admin_bp.route("/stations/<int:station_id>/edit", methods=["POST"])
def edit_station(station_id):
    if not get_station_by_id(station_id, only_approved=False):
        flash("Charging station not found.", "danger")
        return redirect(url_for("admin.stations")), 404

    station_name = request.form.get("station_name")
    address = request.form.get("address")
    city = request.form.get("city")
    opening_time = request.form.get("opening_time")
    closing_time = request.form.get("closing_time")
    status = request.form.get("station_status")

    update_station(station_id, station_name, address, city, opening_time, closing_time, status)
    log_audit_event(
        action="UPDATE_STATION",
        entity_name="Stations",
        entity_id=station_id,
        user_id=get_current_user_id(),
        details=f"Updated station {station_id} status to {status}",
        ip_address=request.remote_addr
    )
    flash("Station updated successfully.", "success")
    return redirect(url_for("admin.stations"))


@admin_bp.route("/stations/import", methods=["POST"])
def import_stations():
    """Import charging stations from CSV file or pasted CSV data into pending review queue."""
    csv_text = request.form.get("csv_text", "").strip()
    uploaded = request.files.get("csv_file")
    if uploaded and uploaded.filename:
        csv_text = uploaded.read().decode("utf-8", errors="ignore")

    approve_now = request.form.get("approve_immediately") == "1"
    result = import_stations_from_csv(csv_text, approve_immediately=approve_now)

    admin_id = get_current_user_id()
    log_audit_event(
        action="IMPORT_STATIONS_CSV",
        entity_name="Stations",
        entity_id=None,
        user_id=admin_id,
        details=f"CSV import: {len(result['imported_ids'])} imported, {len(result['skipped'])} duplicates skipped, {len(result['errors'])} errors",
        ip_address=request.remote_addr,
    )

    if result["imported_ids"]:
        state_msg = "published immediately" if approve_now else "queued for admin approval"
        flash(f"Imported {len(result['imported_ids'])} station(s) ({state_msg}).", "success")
    if result["skipped"]:
        flash(f"Skipped {len(result['skipped'])} duplicate(s): {'; '.join(result['skipped'][:3])}", "warning")
    if result["errors"]:
        flash(f"Validation rejected {len(result['errors'])} row(s): {'; '.join(result['errors'][:3])}", "danger")

    return redirect(url_for("admin.stations"))


@admin_bp.route("/stations/<int:station_id>/review", methods=["POST"])
def review_station(station_id):
    """Approve or reject imported/unverified charging stations."""
    decision = request.form.get("decision", "")
    verif_status = request.form.get("verification_status", "").strip() or None
    success, msg = review_station_approval(station_id, decision, verification_status=verif_status)
    if success:
        log_audit_event(
            action="REVIEW_STATION_APPROVAL",
            entity_name="Stations",
            entity_id=station_id,
            user_id=get_current_user_id(),
            details=msg,
            ip_address=request.remote_addr,
        )
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.stations"))


@admin_bp.route("/points", methods=["GET", "POST"])
def points():
    if request.method == "POST":
        station_id = request.form.get("station_id")
        point_code = request.form.get("point_code")
        connector_type = request.form.get("connector_type")
        max_power_kw = request.form.get("max_power_kw")
        tariff_per_kwh = request.form.get("tariff_per_kwh")
        point_status = request.form.get("point_status", "AVAILABLE")

        try:
            pid = create_charging_point(station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
            log_audit_event(
                action="CREATE_POINT",
                entity_name="ChargingPoints",
                entity_id=pid,
                user_id=get_current_user_id(),
                details=f"Added dispenser '{point_code}' to station {station_id} ({connector_type}, {max_power_kw}kW, tariff {tariff_per_kwh})",
                ip_address=request.remote_addr
            )
            flash(f"Dispenser '{point_code}' added successfully.", "success")
        except Exception as e:
            flash(f"Error adding charging point: {str(e)}", "danger")
        return redirect(url_for("admin.points"))

    all_points = get_all_charging_points()
    stations_list = get_all_stations()
    return render_template("admin/points.html", points=all_points, stations=stations_list)


@admin_bp.route("/points/<int:point_id>/edit", methods=["POST"])
def edit_point(point_id):
    if not get_point_by_id(point_id):
        flash("Charging point not found.", "danger")
        return redirect(url_for("admin.points")), 404

    point_code = request.form.get("point_code")
    connector_type = request.form.get("connector_type")
    max_power_kw = request.form.get("max_power_kw")
    tariff_per_kwh = request.form.get("tariff_per_kwh")
    point_status = request.form.get("point_status")

    try:
        update_charging_point(point_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status)
        log_audit_event(
            action="UPDATE_POINT",
            entity_name="ChargingPoints",
            entity_id=point_id,
            user_id=get_current_user_id(),
            details=f"Updated dispenser {point_id} to status {point_status}, tariff {tariff_per_kwh}",
            ip_address=request.remote_addr
        )
        flash(f"Charging point '{point_code}' updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating point: {str(e)}", "danger")
    return redirect(url_for("admin.points"))


@admin_bp.route("/bookings")
def bookings():
    all_bookings = get_all_bookings()
    return render_template("admin/bookings.html", bookings=all_bookings)


@admin_bp.route("/sessions")
def sessions():
    all_sessions = get_all_sessions()
    return render_template("admin/sessions.html", sessions=all_sessions)


@admin_bp.route("/payments")
def payments():
    all_payments = get_all_payments()
    return render_template("admin/payments.html", payments=all_payments)


@admin_bp.route("/reports")
def reports():
    revenue_data = get_monthly_revenue_report()
    energy_data = get_monthly_energy_report()
    utilization_data = get_station_utilization_report()
    status_distribution = get_booking_status_distribution()
    return render_template(
        "admin/reports.html",
        revenue_data=revenue_data,
        energy_data=energy_data,
        utilization_data=utilization_data,
        status_distribution=status_distribution
    )


@admin_bp.route("/reports/export")
def export_reports():
    import csv
    import io
    from flask import Response
    from datetime import datetime

    report_type = request.args.get("type", "revenue")
    output = io.StringIO()
    writer = csv.writer(output)

    if report_type == "revenue":
        data = get_monthly_revenue_report()
        writer.writerow(["Station ID", "Station Name", "City", "Billing Month", "Successful Transactions", "Total Revenue (INR)"])
        for r in data:
            writer.writerow([r["station_id"], r["station_name"], r["city"], r["revenue_month"], r["successful_transactions"], r["total_revenue"]])
        filename = f"ev_monthly_revenue_{datetime.now().strftime('%Y%m%d')}.csv"
    elif report_type == "energy":
        data = get_monthly_energy_report()
        writer.writerow(["Station ID", "Station Name", "City", "Usage Month", "Completed Sessions", "Total Energy (kWh)", "Avg kWh / Session"])
        for r in data:
            writer.writerow([r["station_id"], r["station_name"], r["city"], r["usage_month"], r["completed_sessions"], r["total_energy_kwh"], r["avg_kwh_per_session"]])
        filename = f"ev_monthly_energy_{datetime.now().strftime('%Y%m%d')}.csv"
    elif report_type == "utilization":
        data = get_station_utilization_report()
        writer.writerow(["Station ID", "Station Name", "City", "Dispenser Count", "Total Sessions", "Total Charge Hours", "Total kWh Dispensed"])
        for r in data:
            writer.writerow([r["station_id"], r["station_name"], r["city"], r["dispenser_count"], r["total_sessions"], r["total_charge_hours"], r["total_kwh_dispensed"]])
        filename = f"ev_station_utilization_{datetime.now().strftime('%Y%m%d')}.csv"
    elif report_type == "status":
        data = get_booking_status_distribution()
        writer.writerow(["Booking Status", "Total Bookings", "Percentage (%)"])
        for r in data:
            writer.writerow([r["booking_status"], r["count"], r["percentage"]])
        filename = f"ev_booking_distribution_{datetime.now().strftime('%Y%m%d')}.csv"
    else:
        flash("Invalid report export type specified.", "danger")
        return redirect(url_for("admin.reports"))

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )



@admin_bp.route("/users")
def users():
    role_filter = request.args.get("role")
    status_filter = request.args.get("status")
    query = request.args.get("q", "").strip().lower()

    user_list = get_all_users(role=role_filter if role_filter else None, status=status_filter if status_filter else None)

    if query:
        user_list = [
            u for u in user_list
            if query in u["full_name"].lower() or query in u["email"].lower() or (u.get("phone") and query in u["phone"])
        ]

    return render_template(
        "admin/users.html",
        users=user_list,
        selected_role=role_filter,
        selected_status=status_filter,
        search_query=query
    )


@admin_bp.route("/users/create", methods=["POST"])
def create_user():
    """Protected administrative route for provisioning OWNER or ADMIN accounts."""
    full_name = request.form.get("full_name", "")
    email = request.form.get("email", "")
    phone = request.form.get("phone", "")
    password = request.form.get("password", "")
    role = request.form.get("role", "OWNER")

    uid, err = create_user_by_admin(full_name, email, phone, password, role=role)
    if err:
        flash(err, "danger")
    else:
        log_audit_event(
            action="CREATE_USER",
            entity_name="Users",
            entity_id=uid,
            user_id=get_current_user_id(),
            details=f"Admin created account '{email.strip().lower()}' with role {role.strip().upper()}",
            ip_address=request.remote_addr
        )
        flash(f"User account '{email.strip().lower()}' ({role.strip().upper()}) created successfully.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
def toggle_status(user_id):
    current_admin_id = get_current_user_id()
    success, res = toggle_user_status(user_id, current_admin_id)
    if success:
        log_audit_event(
            action="TOGGLE_USER_STATUS",
            entity_name="Users",
            entity_id=user_id,
            user_id=current_admin_id,
            details=f"Admin updated user {user_id} account status to {res}",
            ip_address=request.remote_addr
        )
        flash(f"User account status successfully updated to {res}.", "success")
    else:
        flash(res, "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/system-health")
def system_health():
    health_data = get_system_health()
    return render_template("admin/system_health.html", health=health_data)


@admin_bp.route("/audit-logs")
def audit_logs():
    entity_filter = request.args.get("entity")
    logs = get_audit_logs(limit=100, entity_name=entity_filter if entity_filter else None)
    settings = get_system_settings_list()
    return render_template(
        "admin/audit_logs.html",
        logs=logs,
        settings=settings,
        selected_entity=entity_filter
    )


@admin_bp.route("/settings/update", methods=["POST"])
def update_setting_route():
    key = request.form.get("setting_key")
    val = request.form.get("setting_value")
    success, msg = update_system_setting(key, val, user_id=get_current_user_id())
    flash(msg, "success" if success else "danger")
    return redirect(url_for("admin.audit_logs"))


@admin_bp.route("/enquiries")
def enquiries():
    status_filter = request.args.get("status", "").strip().upper()
    if status_filter not in VALID_ENQUIRY_STATUSES:
        status_filter = ""
    messages = get_contact_messages(status=status_filter or None, limit=150)
    return render_template(
        "admin/enquiries.html",
        messages=messages,
        selected_status=status_filter,
        valid_statuses=VALID_ENQUIRY_STATUSES,
    )


@admin_bp.route("/enquiries/<int:message_id>/status", methods=["POST"])
def update_enquiry_status(message_id):
    new_status = request.form.get("submission_status", "")
    admin_id = get_current_user_id()
    success, res = update_contact_status(message_id, new_status)
    if success:
        log_audit_event(
            action="UPDATE_ENQUIRY_STATUS",
            entity_name="ContactMessages",
            entity_id=message_id,
            user_id=admin_id,
            details=f"Admin updated enquiry #{message_id} status to {res}",
            ip_address=request.remote_addr,
        )
        flash(f"Enquiry #{message_id} marked as {res}.", "success")
    else:
        flash(res, "danger")
    return redirect(url_for("admin.enquiries"))


@admin_bp.route("/data-sources")
def admin_data_sources():
    """Admin Data Source Register & Integrity Governance portal."""
    return render_template(
        "admin/data_sources.html",
        sources=get_data_sources(),
        valid_statuses=VALID_DATA_STATUSES,
    )


@admin_bp.route("/data-sources/<int:source_id>/update", methods=["POST"])
def update_data_source_route(source_id):
    new_status = request.form.get("data_status", "")
    notes = request.form.get("notes", "")
    success, msg = update_data_source(source_id, new_status, notes=notes or None)
    if success:
        log_audit_event(
            action="UPDATE_DATA_SOURCE",
            entity_name="DataSources",
            entity_id=source_id,
            user_id=get_current_user_id(),
            details=msg,
            ip_address=request.remote_addr,
        )
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.admin_data_sources"))

