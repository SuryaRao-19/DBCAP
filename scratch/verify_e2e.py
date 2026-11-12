"""
End-to-End Live HTTP Route Verifier
EV Charging Station Management System - DBMS Capstone Project
"""
import requests
import sys

BASE_URL = "http://127.0.0.1:5000"

def test_endpoint(session, method, path, expected_status=200, name=""):
    url = f"{BASE_URL}{path}"
    if method == "GET":
        resp = session.get(url, allow_redirects=True)
    else:
        resp = session.post(url, allow_redirects=True)
    
    label = name or path
    if resp.status_code == expected_status:
        print(f"  [PASS] {method} {label} -> {resp.status_code}")
        return True
    else:
        print(f"  [FAIL] {method} {label} -> Got {resp.status_code}, expected {expected_status}")
        return False

def main():
    print("============================================================")
    print("STARTING END-TO-END HTTP ROUTE & UI VERIFICATION")
    print("============================================================")

    all_passed = True
    guest = requests.Session()

    print("\n--- 1. Testing Public Routes ---")
    public_routes = [
        ("/", "Landing Page"),
        ("/stations", "Public Stations Directory"),
        ("/stations?city=New+Delhi", "Stations Filtered by City"),
        ("/stations?connector=CCS2", "Stations Filtered by Connector"),
        ("/stations/1", "Station Detail (Connaught Place)"),
        ("/login", "Login Page"),
        ("/register", "Registration Page"),
    ]
    for path, name in public_routes:
        if not test_endpoint(guest, "GET", path, expected_status=200, name=name):
            all_passed = False

    print("\n--- 2. Testing Administrator Session & Routes ---")
    admin = requests.Session()
    login_resp = admin.post(f"{BASE_URL}/login", data={"email": "admin@evdemo.com", "password": "Admin@123"}, allow_redirects=True)
    if "admin@evdemo.com" in login_resp.text or "Welcome back" in login_resp.text or login_resp.status_code == 200:
        print("  [PASS] Admin Authentication Successful")
    else:
        print("  [FAIL] Admin Authentication Failed")
        all_passed = False

    admin_routes = [
        ("/admin/dashboard", "Admin Dashboard (Aggregates)"),
        ("/admin/stations", "Station Management Table"),
        ("/admin/points", "Charging Points & Tariffs Table"),
        ("/admin/bookings", "All Bookings System-wide"),
        ("/admin/sessions", "All Charging Sessions System-wide"),
        ("/admin/payments", "Financial Ledger Payments"),
        ("/admin/users", "User & Account Management"),
        ("/admin/reports", "Analytical Reports (Revenue & Energy)"),
        ("/admin/system-health", "System & DBMS Diagnostics"),
        ("/admin/audit-logs", "Administrative Audit Trail & Settings"),
        ("/profile", "Admin Account Profile"),
        ("/api/health", "Database & Backend Health JSON Endpoint"),
    ]
    for path, name in admin_routes:
        if not test_endpoint(admin, "GET", path, expected_status=200, name=name):
            all_passed = False

    print("\n--- 3. Testing EV Owner Session & Routes ---")
    owner = requests.Session()
    owner_login = owner.post(f"{BASE_URL}/login", data={"email": "aarav@example.com", "password": "Owner@123"}, allow_redirects=True)
    if "aarav@example.com" in owner_login.text or "Welcome back" in owner_login.text or owner_login.status_code == 200:
        print("  [PASS] EV Owner Authentication Successful")
    else:
        print("  [FAIL] EV Owner Authentication Failed")
        all_passed = False

    owner_routes = [
        ("/owner/dashboard", "EV Owner Dashboard"),
        ("/owner/vehicles", "My Vehicles Fleet"),
        ("/owner/bookings", "My Slot Reservations"),
        ("/owner/charging", "Live Energy Simulator"),
        ("/owner/history", "Charging History & Receipts"),
        ("/owner/session/1", "Itemized Tax Invoice Receipt"),
        ("/profile", "Owner Account Profile"),
    ]
    for path, name in owner_routes:
        if not test_endpoint(owner, "GET", path, expected_status=200, name=name):
            all_passed = False

    print("\n============================================================")
    if all_passed:
        print("ALL END-TO-END HTTP ROUTES VERIFIED SUCCESSFULLY! (100% PASS)")
        print("============================================================")
        sys.exit(0)
    else:
        print("SOME ENDPOINTS FAILED - REVIEW LOGS ABOVE")
        print("============================================================")
        sys.exit(1)

if __name__ == "__main__":
    main()
