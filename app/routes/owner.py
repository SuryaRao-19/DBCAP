"""
EV Owner Routes
EV Charging Station Management System - Production Hardened
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from app.routes.auth_middleware import login_required, role_required, get_current_user_id
from app.services.vehicle_service import get_vehicles_by_user, add_vehicle, delete_vehicle, update_vehicle
from app.services.station_service import get_all_stations, get_point_by_id, get_all_charging_points
from app.services.booking_service import create_booking, get_user_bookings, cancel_booking
from app.services.session_service import (
    start_session, complete_session, get_active_session_for_user,
    get_user_sessions, get_session_receipt
)
from app.services.payment_service import record_payment
from app.services.report_service import get_owner_dashboard_metrics


owner_bp = Blueprint("owner", __name__)


@owner_bp.before_request
@login_required
@role_required("OWNER")
def enforce_owner_access():
    pass


@owner_bp.route("/dashboard")
def dashboard():
    user_id = get_current_user_id()
    metrics = get_owner_dashboard_metrics(user_id)
    vehicles = get_vehicles_by_user(user_id)
    recent_bookings = get_user_bookings(user_id)[:3]
    active_session = get_active_session_for_user(user_id)
    return render_template(
        "owner/dashboard.html",
        metrics=metrics,
        vehicles=vehicles,
        recent_bookings=recent_bookings,
        active_session=active_session
    )


@owner_bp.route("/vehicles", methods=["GET", "POST"])
def vehicles():
    user_id = get_current_user_id()
    if request.method == "POST":
        registration_no = request.form.get("registration_no", "")
        make = request.form.get("make", "")
        model = request.form.get("model", "")
        battery_capacity = request.form.get("battery_capacity_kwh")

        try:
            vid, err = add_vehicle(user_id, registration_no, make, model, battery_capacity)
        except (TypeError, ValueError):
            vid, err = None, "Invalid battery capacity value."

        if err:
            flash(err, "danger")
        else:
            flash(f"Vehicle '{registration_no.strip().upper()}' registered successfully.", "success")
        return redirect(url_for("owner.vehicles"))

    my_vehicles = get_vehicles_by_user(user_id)
    return render_template("owner/vehicles.html", vehicles=my_vehicles)


@owner_bp.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
def remove_vehicle(vehicle_id):
    user_id = get_current_user_id()
    success, err = delete_vehicle(vehicle_id, user_id)
    if success:
        flash("Vehicle removed successfully.", "success")
    else:
        flash(err, "danger")
    return redirect(url_for("owner.vehicles"))


@owner_bp.route("/vehicles/<int:vehicle_id>/edit", methods=["POST"])
def edit_vehicle(vehicle_id):
    user_id = get_current_user_id()
    registration_no = request.form.get("registration_no", "")
    make = request.form.get("make", "")
    model = request.form.get("model", "")
    battery_capacity = request.form.get("battery_capacity_kwh")

    success, err = update_vehicle(vehicle_id, user_id, registration_no, make, model, battery_capacity)
    if success:
        flash(f"Vehicle '{registration_no.strip().upper()}' updated successfully.", "success")
    else:
        flash(err, "danger")
    return redirect(url_for("owner.vehicles"))


@owner_bp.route("/stations")
def stations():
    city = request.args.get("city")
    active_stations = get_all_stations(city=city, status="ACTIVE")
    all_points = get_all_charging_points()
    return render_template("owner/stations.html", stations=active_stations, points=all_points, selected_city=city)


@owner_bp.route("/book/<int:point_id>", methods=["GET", "POST"])
def book_slot(point_id):
    user_id = get_current_user_id()
    point = get_point_by_id(point_id)
    if not point:
        flash("Charging point not found.", "danger")
        return redirect(url_for("owner.stations"))

    user_vehicles = get_vehicles_by_user(user_id)
    if not user_vehicles:
        flash("Please register a vehicle before making a booking.", "warning")
        return redirect(url_for("owner.vehicles"))

    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id")
        start_at = request.form.get("start_at")
        end_at = request.form.get("end_at")

        booking_id, err = create_booking(user_id, vehicle_id, point_id, start_at, end_at)
        if err:
            flash(err, "danger")
            return render_template("owner/book_slot.html", point=point, vehicles=user_vehicles)

        flash("Reservation confirmed successfully! Your charging slot is booked.", "success")
        return redirect(url_for("owner.bookings"))

    return render_template("owner/book_slot.html", point=point, vehicles=user_vehicles)


@owner_bp.route("/bookings")
def bookings():
    user_id = get_current_user_id()
    my_bookings = get_user_bookings(user_id)
    return render_template("owner/bookings.html", bookings=my_bookings)


@owner_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
def cancel_my_booking(booking_id):
    user_id = get_current_user_id()
    success, err = cancel_booking(booking_id, user_id=user_id)
    if success:
        flash("Reservation cancelled successfully.", "info")
    else:
        flash(err, "danger")
    return redirect(url_for("owner.bookings"))


@owner_bp.route("/charging", methods=["GET", "POST"])
def charging():
    user_id = get_current_user_id()
    active_session = get_active_session_for_user(user_id)
    user_vehicles = get_vehicles_by_user(user_id)
    available_points = [p for p in get_all_charging_points() if p["point_status"] == "AVAILABLE"]
    my_bookings = [b for b in get_user_bookings(user_id) if b["booking_status"] == "CONFIRMED"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "start":
            vehicle_id = request.form.get("vehicle_id")
            point_id = request.form.get("point_id")
            booking_id = request.form.get("booking_id") or None

            session_id, err = start_session(user_id, vehicle_id, point_id, booking_id)
            if err:
                if "permission denied" in err.lower():
                    abort(403)
                flash(err, "danger")
            else:
                flash("Charging session initiated! Energy dispensing simulator active.", "success")
            return redirect(url_for("owner.charging"))

        elif action == "stop":
            session_id = request.form.get("session_id")
            energy_kwh = request.form.get("energy_kwh", "0")

            completed, err = complete_session(session_id, energy_kwh, user_id=user_id)
            if err:
                if "permission denied" in err.lower():
                    abort(403)
                flash(err, "danger")
                return redirect(url_for("owner.charging"))
            flash(f"Charging session completed! Energy: {completed['energy_kwh']} kWh | Total: ₹{completed['total_cost']} — Proceed to TEST MODE checkout.", "success")
            return redirect(url_for("owner.checkout", session_id=completed["session_id"]))

        elif action == "pay":
            session_id = request.form.get("session_id")
            payment_method = request.form.get("payment_method", "UPI")
            sim_outcome = (request.form.get("simulated_outcome") or "SUCCESS").strip().upper()
            if sim_outcome not in ("SUCCESS", "FAILED", "PENDING"):
                sim_outcome = "SUCCESS"

            payment_id, err = record_payment(
                session_id,
                payment_method=payment_method,
                payment_status=sim_outcome,
                user_id=user_id,
                simulation_note=f"DEMO PAYMENT ({sim_outcome}) — NO REAL MONEY WILL BE CHARGED",
            )
            if err:
                if "permission denied" in err.lower():
                    abort(403)
                flash(err, "danger")
                return redirect(url_for("owner.history"))
            if sim_outcome == "SUCCESS":
                flash("DEMO PAYMENT SUCCESSFUL — No real money was charged. Receipt generated in ledger.", "success")
            elif sim_outcome == "FAILED":
                flash("DEMO PAYMENT SIMULATED FAILURE — Record logged cleanly. You may retry payment anytime.", "warning")
            else:
                flash("DEMO PAYMENT PENDING — Awaiting simulated settlement confirmation in ledger.", "info")
            return redirect(url_for("owner.history"))

    return render_template(
        "owner/charging.html",
        active_session=active_session,
        vehicles=user_vehicles,
        available_points=available_points,
        bookings=my_bookings
    )


@owner_bp.route("/history")
def history():
    user_id = get_current_user_id()
    my_sessions = get_user_sessions(user_id)
    return render_template("owner/history.html", sessions=my_sessions)


@owner_bp.route("/session/<int:session_id>")
def session_receipt(session_id):
    user_id = get_current_user_id()
    receipt = get_session_receipt(session_id, user_id=user_id)
    if not receipt:
        flash("Charging session receipt not found or access denied.", "danger")
        return redirect(url_for("owner.history"))
    return render_template("owner/receipt.html", receipt=receipt)


@owner_bp.route("/checkout/<int:session_id>")
def checkout(session_id):
    """Render Razorpay TEST MODE payment checkout summary & verification view."""
    from app.services.razorpay_service import get_checkout_context, has_live_test_credentials, get_razorpay_credentials

    user_id = get_current_user_id()
    ctx, err = get_checkout_context(session_id, user_id)
    if err:
        if "permission denied" in err.lower():
            abort(403)
        flash(err, "danger")
        return redirect(url_for("owner.history"))

    creds = get_razorpay_credentials()
    return render_template(
        "owner/checkout.html",
        checkout=ctx,
        razorpay_key_id=creds["key_id"] if has_live_test_credentials(creds) else "",
        razorpay_live_test_ready=has_live_test_credentials(creds),
    )


@owner_bp.route("/session/<int:session_id>/download")
def download_receipt(session_id):
    """Download a text summary of a demo payment receipt."""
    from flask import Response
    user_id = get_current_user_id()
    receipt = get_session_receipt(session_id, user_id=user_id)
    if not receipt:
        flash("Charging session receipt not found or access denied.", "danger")
        return redirect(url_for("owner.history"))

    lines = [
        "EV CHARGENET — DEMO PAYMENT RECEIPT (NO REAL MONEY CHARGED)",
        "==============================================================",
        f"Invoice Number      : INV-{receipt['session_id']}",
        f"Session ID          : #{receipt['session_id']}",
        f"Booking Reference   : {('#' + str(receipt['booking_id'])) if receipt.get('booking_id') else 'Walk-in Direct Session'}",
        f"Driver              : {receipt['customer_name']} ({receipt['customer_email']})",
        f"Vehicle             : {receipt['make']} {receipt['model']} ({receipt['registration_no']})",
        f"Station             : {receipt['station_name']} — {receipt['station_address']}, {receipt['station_city']}",
        f"Dispenser           : {receipt['point_code']} ({receipt['connector_type']}, {receipt['max_power_kw']} kW)",
        f"Energy Delivered    : {receipt['energy_kwh']:.3f} kWh",
        f"Tariff              : INR {receipt['tariff_per_kwh']:.2f} / kWh",
        f"Total Amount        : INR {receipt['total_cost']:.2f} (DEMO LEDGER)",
        f"Payment Method      : {receipt.get('payment_method') or 'N/A'}",
        f"Payment Status      : {receipt.get('payment_status') or 'PENDING'}",
        f"Transaction Ref     : {receipt.get('transaction_reference') or 'N/A'}",
        f"Paid Timestamp      : {receipt.get('paid_at') or 'N/A'}",
        "==============================================================",
        "Academic Demonstration Disclaimer: Strictly simulated ledger transaction.",
    ]
    return Response(
        "\n".join(lines),
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=ev_demo_receipt_{session_id}.txt"},
    )
