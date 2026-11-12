"""
Booking Management Service
EV Charging Station Management System - DBMS Capstone Project
"""
from datetime import datetime
from app.db import query_all, query_one, execute, transaction


def create_booking(user_id, vehicle_id, point_id, start_at, end_at):
    """
    Create a new time slot reservation for a charging point.
    Uses atomic database transaction with row-level locking (SELECT ... FOR UPDATE)
    to serialize concurrent reservation attempts on the same charging dispenser.
    Database trigger trg_booking_before_insert acts as an additional defense-in-depth barrier.
    """
    # 1. Parse and validate timestamps
    if isinstance(start_at, str):
        start_dt = datetime.fromisoformat(start_at.replace("T", " "))
    else:
        start_dt = start_at

    if isinstance(end_at, str):
        end_dt = datetime.fromisoformat(end_at.replace("T", " "))
    else:
        end_dt = end_at

    if end_dt <= start_dt:
        return None, "Booking end time must be strictly after start time."

    # 2. Verify Vehicle belongs to authenticated User
    veh = query_one(
        "SELECT vehicle_id FROM Vehicles WHERE vehicle_id = %s AND user_id = %s",
        (vehicle_id, user_id)
    )
    if not veh:
        return None, "Selected vehicle does not belong to your account."

    # 3. Concurrency-safe atomic transaction with row locking
    try:
        with transaction() as cur:
            # Acquire exclusive lock on the charging point row
            cur.execute(
                "SELECT cp.point_id, cp.point_status, s.station_status "
                "FROM ChargingPoints cp "
                "JOIN Stations s ON s.station_id = cp.station_id "
                "WHERE cp.point_id = %s FOR UPDATE",
                (point_id,)
            )
            point = cur.fetchone()
            if not point:
                return None, "Charging point not found."
            if point["station_status"] != "ACTIVE" or point["point_status"] != "AVAILABLE":
                return None, "Charging point or station is currently unavailable."

            # Check for overlapping confirmed reservations under lock
            cur.execute(
                "SELECT booking_id FROM Bookings "
                "WHERE point_id = %s "
                "  AND booking_status IN ('PENDING', 'CONFIRMED') "
                "  AND %s < end_at AND %s > start_at "
                "FOR UPDATE",
                (point_id, start_dt, end_dt)
            )
            overlap = cur.fetchone()
            if overlap:
                return None, "This charging point already has a confirmed reservation during this time window."

            # Insert booking atomically
            cur.execute(
                "INSERT INTO Bookings (user_id, vehicle_id, point_id, start_at, end_at, booking_status) "
                "VALUES (%s, %s, %s, %s, %s, 'CONFIRMED')",
                (user_id, vehicle_id, point_id, start_dt, end_dt)
            )
            booking_id = cur.lastrowid
            return booking_id, None

    except Exception as e:
        err_msg = str(e)
        if "Overlapping booking" in err_msg:
            return None, "Overlapping booking already exists for this dispenser."
        if "Booking end must be after start" in err_msg:
            return None, "End time must be after start time."
        if "Charging point or station is unavailable" in err_msg:
            return None, "Point or station is unavailable."
        return None, f"Database constraint violation: {err_msg}"



def get_user_bookings(user_id):
    """Retrieve all reservations for a specific EV owner."""
    return query_all(
        "SELECT b.*, v.registration_no, v.make, v.model, "
        "       cp.point_code, cp.connector_type, cp.tariff_per_kwh, "
        "       s.station_name, s.city, s.address "
        "FROM Bookings b "
        "JOIN Vehicles v ON v.vehicle_id = b.vehicle_id "
        "JOIN ChargingPoints cp ON cp.point_id = b.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE b.user_id = %s "
        "ORDER BY b.start_at DESC",
        (user_id,)
    )


def get_all_bookings():
    """Admin view: Retrieve all bookings system-wide."""
    return query_all(
        "SELECT b.*, u.full_name AS user_name, u.email AS user_email, "
        "       v.registration_no, v.make, v.model, "
        "       cp.point_code, cp.connector_type, "
        "       s.station_name, s.city "
        "FROM Bookings b "
        "JOIN Users u ON u.user_id = b.user_id "
        "JOIN Vehicles v ON v.vehicle_id = b.vehicle_id "
        "JOIN ChargingPoints cp ON cp.point_id = b.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "ORDER BY b.start_at DESC"
    )


def cancel_booking(booking_id, user_id=None):
    """Cancel a booking if eligible."""
    sql = "SELECT * FROM Bookings WHERE booking_id = %s"
    params = [booking_id]
    if user_id:
        sql += " AND user_id = %s"
        params.append(user_id)

    booking = query_one(sql, params)
    if not booking:
        return False, "Booking not found or permission denied."

    if booking["booking_status"] in ("COMPLETED", "CANCELLED"):
        return False, f"Cannot cancel a booking that is already {booking['booking_status']}."

    execute(
        "UPDATE Bookings SET booking_status = 'CANCELLED' WHERE booking_id = %s",
        (booking_id,)
    )
    return True, None
