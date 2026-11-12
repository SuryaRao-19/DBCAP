"""
Stations and Charging Points Service
EV Charging Station Management System - Optimized Geospatial & NCR Queries
"""
from app.db import query_all, query_one, execute


def get_all_stations(city=None, status=None, only_approved=True):
    """
    Retrieve stations with optional city, operational status, and approval filtering.
    Uses aggregated joins to avoid N+1 queries and surfaces geospatial/operator metadata.
    """
    sql = (
        "SELECT s.station_id, s.station_name, s.address, s.city, s.state, s.postal_code, "
        "       s.latitude, s.longitude, s.google_place_id, s.maps_url, "
        "       s.operator_name, s.connector_types, s.charger_capacity_kw, s.contact_info, "
        "       s.opening_time, s.closing_time, s.station_status, "
        "       s.verification_status, s.approval_status, s.source_url, s.last_verified_at, s.created_at, "
        "       COUNT(cp.point_id) AS total_points, "
        "       COALESCE(SUM(CASE WHEN cp.point_status = 'AVAILABLE' THEN 1 ELSE 0 END), 0) AS available_points, "
        "       COALESCE(SUM(CASE WHEN cp.point_status = 'OCCUPIED' THEN 1 ELSE 0 END), 0) AS occupied_points, "
        "       COALESCE(MAX(cp.max_power_kw), 0) AS peak_power_kw, "
        "       (SELECT GROUP_CONCAT(sf.facility_name ORDER BY sf.facility_name SEPARATOR ', ') "
        "        FROM StationFacilities sf WHERE sf.station_id = s.station_id) AS facilities_csv "
        "FROM Stations s "
        "LEFT JOIN ChargingPoints cp ON cp.station_id = s.station_id "
        "WHERE 1=1"
    )
    params = []
    if only_approved:
        sql += " AND s.approval_status = 'APPROVED'"
    if city:
        sql += " AND s.city = %s"
        params.append(city)
    if status:
        sql += " AND s.station_status = %s"
        params.append(status)

    sql += (
        " GROUP BY s.station_id, s.station_name, s.address, s.city, s.state, s.postal_code, "
        "          s.latitude, s.longitude, s.google_place_id, s.maps_url, "
        "          s.operator_name, s.connector_types, s.charger_capacity_kw, s.contact_info, "
        "          s.opening_time, s.closing_time, s.station_status, "
        "          s.verification_status, s.approval_status, s.source_url, s.last_verified_at, s.created_at "
        " ORDER BY s.city, s.station_name"
    )
    stations = query_all(sql, params)

    for s in stations:
        if s.get("opening_time") is not None:
            s["opening_time"] = str(s["opening_time"])
        if s.get("closing_time") is not None:
            s["closing_time"] = str(s["closing_time"])
        s["latitude"] = float(s["latitude"]) if s.get("latitude") is not None else None
        s["longitude"] = float(s["longitude"]) if s.get("longitude") is not None else None
        s["total_points"] = int(s["total_points"] or 0)
        s["available_points"] = int(s["available_points"] or 0)
        s["occupied_points"] = int(s["occupied_points"] or 0)
        s["peak_power_kw"] = float(s["peak_power_kw"] or 0)
        s["facilities_list"] = [f.strip() for f in (s.get("facilities_csv") or "").split(",") if f.strip()]

    return stations


def get_station_by_id(station_id, only_approved=True):
    """Retrieve single station with its charging points and facilities."""
    sql = (
        "SELECT station_id, station_name, address, city, state, postal_code, "
        "       latitude, longitude, google_place_id, maps_url, "
        "       operator_name, connector_types, charger_capacity_kw, contact_info, "
        "       opening_time, closing_time, station_status, "
        "       verification_status, approval_status, source_url, last_verified_at, created_at "
        "FROM Stations WHERE station_id = %s"
    )
    if only_approved:
        sql += " AND approval_status = 'APPROVED'"
    station = query_one(sql, (station_id,))
    if station:
        if station.get("opening_time") is not None:
            station["opening_time"] = str(station["opening_time"])
        if station.get("closing_time") is not None:
            station["closing_time"] = str(station["closing_time"])
        station["latitude"] = float(station["latitude"]) if station.get("latitude") is not None else None
        station["longitude"] = float(station["longitude"]) if station.get("longitude") is not None else None

        station["points"] = query_all(
            "SELECT point_id, station_id, point_code, connector_type, max_power_kw, "
            "       tariff_per_kwh, point_status, created_at "
            "FROM ChargingPoints WHERE station_id = %s ORDER BY point_code",
            (station_id,)
        )
        facs = query_all(
            "SELECT facility_name FROM StationFacilities WHERE station_id = %s ORDER BY facility_name",
            (station_id,)
        )
        station["facilities_list"] = [f["facility_name"] for f in facs]
    return station


def create_station(
    station_name,
    address,
    city,
    opening_time="06:00:00",
    closing_time="23:00:00",
    status="ACTIVE",
    state="Delhi NCR",
    postal_code=None,
    latitude=None,
    longitude=None,
    operator_name="Tata Power EZ Charge",
    connector_types=None,
    charger_capacity_kw=None,
    maps_url=None,
    source_url=None,
    verification_status="DEMO",
    approval_status="APPROVED",
):
    """Create a new charging station with optional geospatial & verification fields."""
    if latitude is not None and longitude is not None and not maps_url:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={float(latitude):.6f},{float(longitude):.6f}"

    return execute(
        "INSERT INTO Stations ("
        "  station_name, address, city, state, postal_code, latitude, longitude, maps_url, "
        "  operator_name, connector_types, charger_capacity_kw, opening_time, closing_time, "
        "  station_status, verification_status, approval_status, source_url, last_verified_at"
        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
        (
            station_name.strip(),
            address.strip(),
            city.strip(),
            (state or "Delhi NCR").strip(),
            postal_code.strip() if postal_code else None,
            latitude,
            longitude,
            maps_url,
            (operator_name or "Tata Power EZ Charge").strip(),
            connector_types,
            charger_capacity_kw,
            opening_time,
            closing_time,
            status,
            verification_status,
            approval_status,
            source_url,
        )
    )


def update_station(
    station_id,
    station_name,
    address,
    city,
    opening_time,
    closing_time,
    status,
    state=None,
    postal_code=None,
    latitude=None,
    longitude=None,
    operator_name=None,
    verification_status=None,
):
    """Update station details, location metadata, and operational status."""
    fields = [
        "station_name = %s",
        "address = %s",
        "city = %s",
        "opening_time = %s",
        "closing_time = %s",
        "station_status = %s",
    ]
    params = [
        station_name.strip(),
        address.strip(),
        city.strip(),
        opening_time,
        closing_time,
        status,
    ]
    if state is not None:
        fields.append("state = %s")
        params.append(state.strip())
    if postal_code is not None:
        fields.append("postal_code = %s")
        params.append(postal_code.strip() or None)
    if latitude is not None and longitude is not None:
        fields.append("latitude = %s")
        fields.append("longitude = %s")
        fields.append("maps_url = %s")
        params.extend([latitude, longitude, f"https://www.google.com/maps/search/?api=1&query={float(latitude):.6f},{float(longitude):.6f}"])
    if operator_name is not None:
        fields.append("operator_name = %s")
        params.append(operator_name.strip())
    if verification_status is not None:
        fields.append("verification_status = %s")
        params.append(verification_status)

    params.append(station_id)
    execute(f"UPDATE Stations SET {', '.join(fields)} WHERE station_id = %s", params)


def get_all_charging_points(station_id=None, only_approved=True):
    """Retrieve all charging dispensers with their parent station info."""
    sql = (
        "SELECT cp.point_id, cp.station_id, cp.point_code, cp.connector_type, "
        "       cp.max_power_kw, cp.tariff_per_kwh, cp.point_status, cp.created_at, "
        "       s.station_name, s.city, s.state, s.station_status, s.operator_name, "
        "       s.latitude, s.longitude, s.approval_status "
        "FROM ChargingPoints cp "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE 1=1"
    )
    params = []
    if only_approved:
        sql += " AND s.approval_status = 'APPROVED'"
    if station_id is not None:
        sql += " AND cp.station_id = %s"
        params.append(station_id)
    sql += " ORDER BY s.station_name, cp.point_code"
    return query_all(sql, params)


def create_charging_point(station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status="AVAILABLE"):
    """Add a new dispenser to a station."""
    return execute(
        "INSERT INTO ChargingPoints (station_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (station_id, point_code.strip().upper(), connector_type, float(max_power_kw), float(tariff_per_kwh), point_status)
    )


def update_charging_point(point_id, point_code, connector_type, max_power_kw, tariff_per_kwh, point_status):
    """Update a dispenser's parameters and live status."""
    execute(
        "UPDATE ChargingPoints SET point_code = %s, connector_type = %s, max_power_kw = %s, "
        "tariff_per_kwh = %s, point_status = %s WHERE point_id = %s",
        (point_code.strip().upper(), connector_type, float(max_power_kw), float(tariff_per_kwh), point_status, point_id)
    )


def get_point_by_id(point_id):
    """Get details of a single charging point with station info."""
    return query_one(
        "SELECT cp.*, s.station_name, s.address, s.city, s.state, s.postal_code, "
        "       s.operator_name, s.latitude, s.longitude, s.maps_url, s.verification_status "
        "FROM ChargingPoints cp JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE cp.point_id = %s",
        (point_id,)
    )
