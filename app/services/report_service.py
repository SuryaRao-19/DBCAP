"""
Reporting and Analytical Query Service
EV Charging Station Management System - Portable & Optimized
"""
import time
from app.db import query_all, query_one


def get_admin_dashboard_metrics():
    """Calculate executive KPI aggregates from real database records."""
    station_stats = query_one(
        "SELECT "
        "COUNT(*) AS total_stations, "
        "COALESCE(SUM(CASE WHEN station_status = 'ACTIVE' THEN 1 ELSE 0 END), 0) AS active_stations "
        "FROM Stations"
    )

    point_stats = query_one(
        "SELECT "
        "COUNT(*) AS total_points, "
        "COALESCE(SUM(CASE WHEN point_status = 'AVAILABLE' THEN 1 ELSE 0 END), 0) AS available_points, "
        "COALESCE(SUM(CASE WHEN point_status = 'OCCUPIED' THEN 1 ELSE 0 END), 0) AS occupied_points, "
        "COALESCE(SUM(CASE WHEN point_status IN ('UNAVAILABLE', 'MAINTENANCE') THEN 1 ELSE 0 END), 0) AS offline_points "
        "FROM ChargingPoints"
    )

    total_users = query_one("SELECT COUNT(*) AS cnt FROM Users WHERE role = 'OWNER'")["cnt"]
    total_vehicles = query_one("SELECT COUNT(*) AS cnt FROM Vehicles")["cnt"]
    total_bookings = query_one("SELECT COUNT(*) AS cnt FROM Bookings")["cnt"]

    session_stats = query_one(
        "SELECT "
        "COUNT(*) AS total_sessions, "
        "COALESCE(SUM(CASE WHEN session_status = 'IN_PROGRESS' THEN 1 ELSE 0 END), 0) AS active_sessions, "
        "COALESCE(SUM(CASE WHEN session_status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS completed_sessions, "
        "COALESCE(SUM(CASE WHEN session_status = 'COMPLETED' THEN energy_kwh ELSE 0 END), 0) AS total_energy_kwh "
        "FROM ChargingSessions"
    )

    revenue_stats = query_one(
        "SELECT COALESCE(SUM(amount), 0) AS total_revenue "
        "FROM Payments WHERE payment_status = 'SUCCESS'"
    )

    return {
        "total_stations": int(station_stats["total_stations"] or 0),
        "active_stations": int(station_stats["active_stations"] or 0),
        "total_points": int(point_stats["total_points"] or 0),
        "available_points": int(point_stats["available_points"] or 0),
        "occupied_points": int(point_stats["occupied_points"] or 0),
        "offline_points": int(point_stats["offline_points"] or 0),
        "total_users": int(total_users or 0),
        "total_vehicles": int(total_vehicles or 0),
        "total_bookings": int(total_bookings or 0),
        "total_sessions": int(session_stats["total_sessions"] or 0),
        "active_sessions": int(session_stats["active_sessions"] or 0),
        "completed_sessions": int(session_stats["completed_sessions"] or 0),
        "total_energy_kwh": float(session_stats["total_energy_kwh"] or 0),
        "total_revenue": float(revenue_stats["total_revenue"] or 0),
    }


def get_owner_dashboard_metrics(user_id):
    """Calculate personal metrics for an EV Owner."""
    veh_count = query_one("SELECT COUNT(*) AS cnt FROM Vehicles WHERE user_id = %s", (user_id,))["cnt"]
    book_count = query_one("SELECT COUNT(*) AS cnt FROM Bookings WHERE user_id = %s", (user_id,))["cnt"]

    sess_stats = query_one(
        "SELECT "
        "COUNT(*) AS total_sessions, "
        "COALESCE(SUM(energy_kwh), 0) AS total_kwh, "
        "COALESCE(SUM(total_cost), 0) AS total_spend "
        "FROM ChargingSessions "
        "WHERE user_id = %s AND session_status = 'COMPLETED'",
        (user_id,)
    )

    return {
        "vehicle_count": veh_count,
        "booking_count": book_count,
        "total_sessions": sess_stats["total_sessions"] or 0,
        "total_kwh": float(sess_stats["total_kwh"] or 0),
        "total_spend": float(sess_stats["total_spend"] or 0)
    }


def get_monthly_revenue_report():
    """Phase 3 Report 3: Monthly revenue by station."""
    return query_all(
        "SELECT s.station_id, s.station_name, s.city, "
        "       DATE_FORMAT(p.paid_at, '%%Y-%%m') AS revenue_month, "
        "       COUNT(p.payment_id) AS successful_transactions, "
        "       SUM(p.amount) AS total_revenue "
        "FROM Payments p "
        "JOIN ChargingSessions cs ON cs.session_id = p.session_id "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE p.payment_status = 'SUCCESS' "
        "GROUP BY s.station_id, s.station_name, s.city, DATE_FORMAT(p.paid_at, '%%Y-%%m') "
        "ORDER BY revenue_month DESC, total_revenue DESC"
    )


def get_monthly_energy_report():
    """Phase 3 Report 4: Monthly energy dispensed by station."""
    return query_all(
        "SELECT s.station_id, s.station_name, s.city, "
        "       DATE_FORMAT(cs.start_at, '%%Y-%%m') AS usage_month, "
        "       COUNT(cs.session_id) AS completed_sessions, "
        "       ROUND(SUM(cs.energy_kwh), 2) AS total_energy_kwh, "
        "       ROUND(AVG(cs.energy_kwh), 2) AS avg_kwh_per_session "
        "FROM ChargingSessions cs "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "WHERE cs.session_status = 'COMPLETED' "
        "GROUP BY s.station_id, s.station_name, s.city, DATE_FORMAT(cs.start_at, '%%Y-%%m') "
        "ORDER BY usage_month DESC, total_energy_kwh DESC"
    )


def get_station_utilization_report():
    """Phase 3 Report 8: Station utilization metrics."""
    return query_all(
        "SELECT s.station_id, s.station_name, s.city, "
        "       COUNT(DISTINCT cp.point_id) AS dispenser_count, "
        "       COUNT(cs.session_id) AS total_sessions, "
        "       COALESCE(ROUND(SUM(TIMESTAMPDIFF(MINUTE, cs.start_at, cs.end_at)) / 60.0, 2), 0) AS total_charge_hours, "
        "       ROUND(COALESCE(SUM(cs.energy_kwh), 0), 2) AS total_kwh_dispensed "
        "FROM Stations s "
        "JOIN ChargingPoints cp ON cp.station_id = s.station_id "
        "LEFT JOIN ChargingSessions cs ON cs.point_id = cp.point_id AND cs.session_status = 'COMPLETED' "
        "GROUP BY s.station_id, s.station_name, s.city "
        "ORDER BY total_charge_hours DESC"
    )


def get_booking_status_distribution():
    """Phase 3 Report 5: Bookings grouped by status."""
    total = query_one("SELECT COUNT(*) AS cnt FROM Bookings")["cnt"]
    rows = query_all(
        "SELECT booking_status, COUNT(*) AS count "
        "FROM Bookings GROUP BY booking_status ORDER BY count DESC"
    )
    for r in rows:
        r["percentage"] = round((r["count"] * 100.0 / total), 1) if total > 0 else 0
    return rows


def get_system_health():
    """Database and system diagnostics using portable DATABASE() metadata."""
    start = time.time()
    db_info = query_one("SELECT VERSION() AS version, DATABASE() AS db_name, @@hostname AS host")
    latency_ms = round((time.time() - start) * 1000, 2)

    candidate_tables = [
        "Users",
        "Vehicles",
        "Stations",
        "ChargingPoints",
        "Bookings",
        "ChargingSessions",
        "Payments",
        "PaymentWebhookEvents",
        "AuditLogs",
        "SystemSettings",
        "ContactMessages",
        "NetworkOperators",
        "SocialLinks",
        "DataSources",
        "StationFacilities",
    ]
    existing_rows = query_all(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
    )
    existing_set = {r["TABLE_NAME"].lower() for r in existing_rows}

    table_stats = []
    total_records = 0
    for tbl in candidate_tables:
        if tbl.lower() in existing_set:
            cnt = query_one(f"SELECT COUNT(*) AS c FROM `{tbl}`")["c"]
            total_records += cnt
            table_stats.append({"name": tbl, "rows": cnt})

    routines = query_all(
        "SELECT ROUTINE_NAME, ROUTINE_TYPE, DTD_IDENTIFIER "
        "FROM INFORMATION_SCHEMA.ROUTINES "
        "WHERE ROUTINE_SCHEMA = DATABASE() "
        "ORDER BY ROUTINE_NAME"
    )

    triggers = query_all(
        "SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE, ACTION_TIMING "
        "FROM INFORMATION_SCHEMA.TRIGGERS "
        "WHERE TRIGGER_SCHEMA = DATABASE() "
        "ORDER BY TRIGGER_NAME"
    )

    indexes = query_all(
        "SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns "
        "FROM INFORMATION_SCHEMA.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND INDEX_NAME NOT IN ('PRIMARY') "
        "GROUP BY TABLE_NAME, INDEX_NAME "
        "ORDER BY TABLE_NAME, INDEX_NAME"
    )

    threads = query_one("SHOW STATUS LIKE 'Threads_connected'")

    return {
        "status": "HEALTHY",
        "mysql_version": db_info.get("version", "Unknown"),
        "database_name": db_info.get("db_name", "Unknown"),
        "host": db_info.get("host", "localhost"),
        "latency_ms": latency_ms,
        "threads_connected": threads.get("Value", 1) if threads else 1,
        "tables": table_stats,
        "total_records": total_records,
        "routines": routines,
        "triggers": triggers,
        "indexes": indexes,
    }


def get_admin_chart_analytics():
    """Real MySQL database chart series for Admin Dashboard visualizations."""
    stations_by_city = query_all(
        "SELECT city, COUNT(*) AS count "
        "FROM Stations WHERE approval_status = 'APPROVED' "
        "GROUP BY city ORDER BY count DESC, city ASC"
    )
    chargers_by_type = query_all(
        "SELECT connector_type, COUNT(*) AS count, ROUND(SUM(max_power_kw), 1) AS total_kw "
        "FROM ChargingPoints GROUP BY connector_type ORDER BY count DESC"
    )
    monthly_bookings = query_all(
        "SELECT DATE_FORMAT(start_at, '%%Y-%%m') AS month, COUNT(*) AS count "
        "FROM Bookings GROUP BY DATE_FORMAT(start_at, '%%Y-%%m') "
        "ORDER BY month ASC LIMIT 12"
    )
    payment_status_counts = query_all(
        "SELECT payment_status, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total_amount "
        "FROM Payments GROUP BY payment_status ORDER BY count DESC"
    )
    return {
        "stations_by_city": [{"city": r["city"], "count": int(r["count"])} for r in stations_by_city],
        "chargers_by_type": [
            {"connector_type": r["connector_type"], "count": int(r["count"]), "total_kw": float(r["total_kw"] or 0)}
            for r in chargers_by_type
        ],
        "monthly_bookings": [{"month": r["month"], "count": int(r["count"])} for r in monthly_bookings],
        "payment_status_counts": [
            {"payment_status": r["payment_status"], "count": int(r["count"]), "total_amount": float(r["total_amount"] or 0)}
            for r in payment_status_counts
        ],
        "booking_statuses": [
            {"booking_status": r["booking_status"], "count": int(r["count"])}
            for r in get_booking_status_distribution()
        ],
    }
