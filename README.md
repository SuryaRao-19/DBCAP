# EV Charging Station Management System (EV ChargeNet)

A full-stack EV Charging Network & Station Management web application built with **Python Flask**, **MySQL 8.0+**, **Jinja2**, **Web3Forms**, and **Vercel Serverless** deployment readiness.

---

## Core Features

### Public & Contact Portal
- **Station Discovery & Interactive NCR Map (`/`, `/stations`, `/stations/<id>`, `/api/stations/map`)**: Explore 14 verified Delhi NCR hubs inspired by Tata Power EZ Charge (`New Delhi`, `Gurugram`, `Noida`, `Greater Noida`, `Faridabad`, `Ghaziabad`), filter by city/connector/charging speed, sort *"Near Me"* via browser geolocation, and render pins dynamically on Google Maps JS API or automatic Leaflet.js/OpenStreetMap fallback.
- **Transparency & Verification Pages (`/about`, `/data-sources`)**: Explicit independent academic platform disclosure, Tata Power EZ Charge reference profile & social links, and a live MySQL `DataSources` register distinguishing `VERIFIED`, `DEMO`, `ESTIMATED`, and `UNAVAILABLE` metrics.
- **Web3Forms Contact & Enquiry Portal (`/contact`)**: CSRF-protected enquiry form with client/server validation, honeypot spam filter, DB-backed rate limiting & duplicate submission lock, resilient MySQL backup storage (`ContactMessages`), and Web3Forms backend API forwarding.

### EV Owner Portal (`/owner/*`)
- **Vehicle Fleet Management (`/owner/vehicles`)**: Register, edit, and delete EVs with strict user ownership checks.
- **Slot Reservations (`/owner/bookings`, `/owner/book/<point_id>`)**: Real-time overlap checking (`/api/check-overlap`) backed by DB trigger `trg_booking_before_insert`, plus live estimated charging duration, kWh, and tariff preview.
- **Live Charging Simulation & Razorpay TEST MODE Checkout (`/owner/charging`, `/owner/checkout/<session_id>`, `/owner/session/<id>/download`)**: Atomic row-locked session start (`start_session`), stored procedure completion (`CompleteChargingSession` + `CalculateChargingCost`), dedicated Razorpay Test Mode Standard Checkout with 18% GST invoice breakdown, server-side HMAC-SHA256 signature verification (`/api/payments/razorpay/order`, `/api/payments/razorpay/verify`, `/api/payments/razorpay/sandbox-complete`), idempotent webhook ingestion (`/api/payments/razorpay/webhook` -> `PaymentWebhookEvents`), and strict live-key guardrail (`rzp_live_*` blocked), plus simulated ledger fallback (`DEMO PAYMENT — NO REAL MONEY WILL BE CHARGED`) and printable/downloadable `.txt` receipts.

### Administrator Portal (`/admin/*`)
- **Operations Dashboard, Sidebar & Real-Time Analytics (`/admin/dashboard`, `/admin/reports`)**: Collapsible fixed sidebar navigation (`Operations` + `Administration`), real MySQL-backed Chart.js visualizations (city hub capacity, monthly reservations, connector mix, payment ledger outcomes), utilization metrics, and CSV export.
- **Station Directory, CSV Import & Approval Workflow (`/admin/stations`, `/admin/points`)**: Manage station geospatial metadata, bulk-import CSV station lists with coordinate/PIN/source validation, and review `PENDING_APPROVAL` hubs before public publishing.
- **Data Governance (`/admin/data-sources`)**: Manage `DataSources` verification classifications (`VERIFIED`, `DEMO`, `ESTIMATED`, `UNAVAILABLE`).
- **User Governance & Audit Trail (`/admin/users`, `/admin/audit-logs`)**: Create `ADMIN` or `OWNER` accounts securely (`POST /admin/users/create`), toggle `ACTIVE`/`INACTIVE` access (immediately enforced per request), and update `SystemSettings`.
- **Enquiry Triage (`/admin/enquiries`)**: View Contact Us submissions, track Web3Forms `SENT`/`FAILED`/`PENDING` status, and transition enquiries (`NEW`, `IN_PROGRESS`, `RESOLVED`).
- **Portable System Health (`/admin/system-health`)**: Live MySQL diagnostics using `DATABASE()`.

---

## Security & Architecture Highlights
- **Role-Based Access Control (RBAC)**: Public registration (`/register`) exclusively creates `OWNER` accounts (`allow_admin=False`); only authenticated `ADMIN` accounts can provision new administrators.
- **IDOR & Transaction Protection**: All booking, session, payment, receipt, and vehicle mutations verify resource ownership and use parameterized SQL + InnoDB row locking (`SELECT ... FOR UPDATE`).
- **CSRF & Hardened Sessions**: Global `Flask-WTF` `CSRFProtect`, `HttpOnly`, `SameSite=Lax`, and production `Secure` cookies, plus environment-driven secrets (`SECRET_KEY`, `DATABASE_URL`, `WEB3FORMS_ACCESS_KEY`) with production fail-fast checks.
- **Connection Pooling**: `DBUtils.PooledDB` (`app/db.py`) with `ping=1`, TLS/SSL support, and serverless connection limits.

> **Note on Payment Handling**: Checkout & session billing in `Payments` operate exclusively in **Razorpay Test Mode / Simulated Financial Ledger** for academic demonstration (zero live merchant charges; `rzp_live_*` keys are blocked).

---

## Project Structure

```text
DBCAP/
├── api/
│   └── index.py                  # Vercel Python WSGI entrypoint
├── app/
│   ├── __init__.py               # Flask app factory, CSRF, hardened sessions, blueprints
│   ├── db.py                     # PooledDB connection manager, DATABASE_URL & SSL parser
│   ├── routes/                   # public, auth, owner, admin, api, auth_middleware
│   ├── services/                 # auth, station, booking, session, payment, report, audit, contact
│   ├── static/                   # CSS & JS assets (main.js CSRF helper)
│   └── templates/                # Jinja2 HTML views (public, auth, owner, admin)
├── database/
│   ├── 01_schema.sql             # Core 3NF InnoDB tables + ContactMessages
│   ├── 02_constraints_indexes.sql
│   ├── 03_routines_triggers.sql  # CalculateChargingCost, CompleteChargingSession, triggers
│   ├── 04_demo_data.sql          # Optional staging/demo dataset
│   └── migrations/               # Non-destructive ordered SQL migrations (001–005)
├── docs/
│   ├── SECURITY.md
│   ├── DATABASE_SETUP.md
│   ├── DATA_VERIFICATION_REPORT.md
│   ├── WEB3FORMS_SETUP.md
│   ├── VERCEL_DEPLOYMENT.md
│   ├── PRODUCTION_CHECKLIST.md
│   └── deployment.md
├── tests/                        # Automated pytest verification suite
├── .env.example                  # Placeholder environment variable template
├── init_db.py                    # Cross-platform pure-Python DB initializer & migrator
├── requirements.txt
├── run.py                        # Local development runner
└── vercel.json                   # Vercel serverless configuration
```

---

## Local Quickstart

1. **Create environment & install dependencies**
   ```bash
   python -m venv .venv
   # Windows PowerShell: .\.venv\Scripts\Activate.ps1
   # Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configure environment variables**
   Copy `.env.example` to `.env` and fill in your local MySQL credentials, `SECRET_KEY`, and `WEB3FORMS_ACCESS_KEY`.
3. **Initialize or migrate MySQL 8.0+ database**
   ```bash
   # Non-destructive migration (preserves existing data):
   python init_db.py --mode migrate

   # Fresh database creation (with optional demo data):
   python init_db.py --mode full --seed-demo
   ```
4. **Run the test suite**
   ```bash
   python -m pytest -v
   ```
5. **Start the local server**
   ```bash
   python run.py
   ```

---

## Documentation
- **Security Hardening**: [`docs/SECURITY.md`](docs/SECURITY.md)
- **Managed MySQL & Migrations**: [`docs/DATABASE_SETUP.md`](docs/DATABASE_SETUP.md)
- **Web3Forms Setup**: [`docs/WEB3FORMS_SETUP.md`](docs/WEB3FORMS_SETUP.md)
- **Vercel Deployment Walkthrough**: [`docs/VERCEL_DEPLOYMENT.md`](docs/VERCEL_DEPLOYMENT.md)
- **Pre-Launch Checklist**: [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md)
