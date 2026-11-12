"""
Public Portal Routes, Brand Reference, Map Discovery & Web3Forms Contact
EV Charging Station Management System
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.routes.auth_middleware import login_required, get_current_user_id
from app.services.station_service import get_all_stations, get_station_by_id, get_all_charging_points
from app.services.report_service import get_admin_dashboard_metrics
from app.services.auth_service import get_user_profile, update_user_profile
from app.services.contact_service import CONTACT_CATEGORIES, submit_contact_enquiry
from app.services.platform_service import VERIFIED_ANNOUNCEMENTS, OFFICIAL_EZCHARGE_STATS, get_data_sources

public_bp = Blueprint("public", __name__)

NCR_CITIES = ("New Delhi", "Gurugram", "Noida", "Greater Noida", "Faridabad", "Ghaziabad")


def _matches_speed_bucket(dispensers, speed_filter):
    if not speed_filter:
        return True
    speeds = [float(p.get("max_power_kw") or 0) for p in dispensers]
    if not speeds:
        return False
    peak = max(speeds)
    if speed_filter == "FAST":
        return peak >= 50.0
    if speed_filter == "RAPID":
        return 22.0 <= peak < 50.0
    if speed_filter == "AC":
        return any(s < 22.0 for s in speeds)
    return True


@public_bp.route("/")
def landing():
    """Public landing page with verified reference identity, NCR stations, and map preview."""
    metrics = get_admin_dashboard_metrics()
    stations = get_all_stations(status="ACTIVE", only_approved=True)
    cities = sorted(list(set(s["city"] for s in stations if s.get("city"))))

    return render_template(
        "landing.html",
        metrics=metrics,
        featured_stations=stations[:6],
        all_stations=stations,
        cities=cities,
        ncr_cities=NCR_CITIES,
        announcements=VERIFIED_ANNOUNCEMENTS,
        official_stats=OFFICIAL_EZCHARGE_STATS,
        contact_categories=CONTACT_CATEGORIES,
        city_count=len(cities),
        station_count=len(stations),
    )


@public_bp.route("/about")
def about():
    """About Us page detailing verified Tata Power EZ Charge case study & data transparency."""
    data_sources = get_data_sources()
    stations = get_all_stations(status="ACTIVE", only_approved=True)
    city_counts = {}
    for s in stations:
        city_counts[s["city"]] = city_counts.get(s["city"], 0) + 1

    return render_template(
        "about.html",
        data_sources=data_sources,
        announcements=VERIFIED_ANNOUNCEMENTS,
        official_stats=OFFICIAL_EZCHARGE_STATS,
        city_counts=city_counts,
        total_verified=sum(1 for s in stations if s.get("verification_status") == "VERIFIED"),
    )


@public_bp.route("/data-sources")
def data_sources():
    """Public Data Source Register documenting VERIFIED vs DEMO vs ESTIMATED vs UNAVAILABLE facts."""
    return render_template("data_sources.html", sources=get_data_sources())


@public_bp.route("/stations")
def browse_stations():
    """Public interactive map and charging station directory with NCR city, connector, and speed filters."""
    city_filter = request.args.get("city", "").strip()
    connector_filter = request.args.get("connector", "").strip()
    speed_filter = request.args.get("speed", "").strip().upper()
    query = request.args.get("q", "").strip().lower()

    all_active_stations = get_all_stations(status="ACTIVE", only_approved=True)
    available_cities = sorted(list(set(s["city"] for s in all_active_stations if s.get("city"))))

    stations_for_city = (
        [s for s in all_active_stations if s["city"].lower() == city_filter.lower()]
        if city_filter
        else all_active_stations
    )
    all_points = get_all_charging_points(only_approved=True)
    available_connectors = sorted(list(set(p["connector_type"] for p in all_points if p.get("connector_type"))))

    points_by_station = {}
    for p in all_points:
        points_by_station.setdefault(p["station_id"], []).append(p)

    filtered_stations = []
    for s in stations_for_city:
        st_points = points_by_station.get(s["station_id"], [])

        if connector_filter:
            has_conn = any(p["connector_type"] == connector_filter for p in st_points) or (
                connector_filter.lower() in (s.get("connector_types") or "").lower()
            )
            if not has_conn:
                continue

        if speed_filter and not _matches_speed_bucket(st_points, speed_filter):
            continue

        if query:
            searchable = " ".join([
                s.get("station_name") or "",
                s.get("city") or "",
                s.get("state") or "",
                s.get("postal_code") or "",
                s.get("address") or "",
                s.get("operator_name") or "",
            ]).lower()
            if query not in searchable:
                continue

        s["dispensers"] = st_points
        filtered_stations.append(s)

    return render_template(
        "public_stations.html",
        stations=filtered_stations,
        cities=available_cities,
        ncr_cities=NCR_CITIES,
        connectors=available_connectors,
        selected_city=city_filter,
        selected_connector=connector_filter,
        selected_speed=speed_filter,
        search_query=query,
    )


@public_bp.route("/stations/<int:station_id>")
def station_detail(station_id):
    """Detailed view of a charging station with geospatial coordinates, facilities, and dispensers."""
    station = get_station_by_id(station_id, only_approved=True)
    if not station:
        flash("Charging station not found.", "danger")
        return redirect(url_for("public.browse_stations"))

    return render_template("station_detail.html", station=station)


@public_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile view and credential management for both EV Owners and Administrators."""
    user_id = get_current_user_id()
    user_data = get_user_profile(user_id)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_new_password = request.form.get("confirm_new_password", "").strip()

        if not full_name:
            flash("Full name cannot be empty.", "danger")
            return render_template("profile.html", user=user_data)

        if new_password:
            if new_password != confirm_new_password:
                flash("New passwords do not match.", "danger")
                return render_template("profile.html", user=user_data)
            if len(new_password) < 6:
                flash("New password must be at least 6 characters.", "danger")
                return render_template("profile.html", user=user_data)

        success, err = update_user_profile(
            user_id,
            full_name=full_name,
            phone=phone,
            current_password=current_password if new_password else None,
            new_password=new_password if new_password else None,
        )

        if success:
            session["full_name"] = full_name
            flash("Profile updated successfully!", "success")
            user_data = get_user_profile(user_id)
        else:
            flash(err, "danger")

    return render_template("profile.html", user=user_data)


@public_bp.route("/contact", methods=["GET", "POST"])
def contact():
    """Public Contact Us & Support Enquiry portal (Web3Forms proxy + MySQL backup + official social references)."""
    form_data = {}
    uid = get_current_user_id()
    if request.method == "GET" and uid:
        profile_data = get_user_profile(uid)
        if profile_data:
            form_data = {
                "full_name": profile_data.get("full_name", ""),
                "email": profile_data.get("email", ""),
                "phone": profile_data.get("phone") or "",
            }

    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        subject = request.form.get("subject", "")
        category = request.form.get("category", "")
        message = request.form.get("message", "")
        honeypot = request.form.get("botcheck", "")

        form_data = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "subject": subject,
            "category": category,
            "message": message,
        }

        ip_addr = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
        contact_id, delivered, feedback_msg, is_val_err = submit_contact_enquiry(
            full_name=full_name,
            email=email,
            phone=phone,
            subject=subject,
            category=category,
            message=message,
            honeypot=honeypot,
            ip_address=ip_addr,
        )

        if is_val_err:
            flash(feedback_msg, "danger")
            return render_template(
                "contact.html",
                categories=CONTACT_CATEGORIES,
                form_data=form_data,
            ), 400

        if not delivered:
            flash(feedback_msg, "danger")
            return render_template(
                "contact.html",
                categories=CONTACT_CATEGORIES,
                form_data=form_data,
                saved_contact_id=contact_id,
            ), 502

        flash(feedback_msg, "success")
        return redirect(url_for("public.contact"))

    return render_template(
        "contact.html",
        categories=CONTACT_CATEGORIES,
        form_data=form_data,
    )
