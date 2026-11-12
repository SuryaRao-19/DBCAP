"""
Vehicle Management Service
EV Charging Station Management System - DBMS Capstone Project
"""
from app.db import query_all, query_one, execute


def get_vehicles_by_user(user_id):
    """Retrieve all vehicles owned by a specific EV owner."""
    return query_all(
        "SELECT * FROM Vehicles WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )


def get_vehicle_by_id(vehicle_id, user_id=None):
    """Retrieve single vehicle, enforcing user ownership if user_id is passed."""
    sql = "SELECT * FROM Vehicles WHERE vehicle_id = %s"
    params = [vehicle_id]
    if user_id:
        sql += " AND user_id = %s"
        params.append(user_id)
    return query_one(sql, params)


def add_vehicle(user_id, registration_no, make, model, battery_capacity_kwh):
    """Register a new vehicle under the authenticated owner."""
    reg = registration_no.strip().upper()
    existing = query_one("SELECT vehicle_id FROM Vehicles WHERE registration_no = %s", (reg,))
    if existing:
        return None, f"Vehicle registration number '{reg}' is already registered."

    capacity = float(battery_capacity_kwh)
    if capacity <= 0:
        return None, "Battery capacity must be greater than 0 kWh."

    vid = execute(
        "INSERT INTO Vehicles (user_id, registration_no, make, model, battery_capacity_kwh) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, reg, make.strip(), model.strip(), capacity)
    )
    return vid, None


def delete_vehicle(vehicle_id, user_id):
    """Delete a vehicle owned by the authenticated owner."""
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    if not vehicle:
        return False, "Vehicle not found or you do not have permission to delete it."

    # Check for active bookings or ongoing sessions
    active = query_one(
        "SELECT booking_id FROM Bookings "
        "WHERE vehicle_id = %s AND booking_status IN ('PENDING', 'CONFIRMED')",
        (vehicle_id,)
    )
    if active:
        return False, "Cannot delete vehicle with active or upcoming bookings."

    execute("DELETE FROM Vehicles WHERE vehicle_id = %s AND user_id = %s", (vehicle_id, user_id))
    return True, None


def update_vehicle(vehicle_id, user_id, registration_no, make, model, battery_capacity_kwh):
    """Update vehicle details, ensuring ownership and unique registration number."""
    vehicle = get_vehicle_by_id(vehicle_id, user_id)
    if not vehicle:
        return False, "Vehicle not found or you do not have permission to edit it."

    reg = registration_no.strip().upper()
    existing = query_one(
        "SELECT vehicle_id FROM Vehicles WHERE registration_no = %s AND vehicle_id != %s",
        (reg, vehicle_id)
    )
    if existing:
        return False, f"Registration number '{reg}' is already taken by another vehicle."

    try:
        capacity = float(battery_capacity_kwh)
        if capacity <= 0:
            return False, "Battery capacity must be greater than 0 kWh."
    except (ValueError, TypeError):
        return False, "Invalid battery capacity value."

    execute(
        "UPDATE Vehicles SET registration_no = %s, make = %s, model = %s, battery_capacity_kwh = %s "
        "WHERE vehicle_id = %s AND user_id = %s",
        (reg, make.strip(), model.strip(), capacity, vehicle_id, user_id)
    )
    return True, None

