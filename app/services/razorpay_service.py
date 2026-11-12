"""
Razorpay Standard Checkout & Webhook Integration Service (TEST MODE ONLY)
Tata Power EZ Charge — EV Network Management Demo
"""
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
import requests
from flask import current_app
from app.db import query_one, transaction
from app.services.audit_service import log_audit_event

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
RAZORPAY_PAYMENT_URL_TMPL = "https://api.razorpay.com/v1/payments/{payment_id}"
VALID_CHECKOUT_METHODS = ("UPI", "CARD", "CREDIT_CARD", "DEBIT_CARD", "NET_BANKING", "WALLET")


def get_razorpay_credentials():
    """Retrieve Razorpay configuration safely from Flask config / environment."""
    if current_app:
        key_id = (current_app.config.get("RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID", "")).strip()
        key_secret = (current_app.config.get("RAZORPAY_KEY_SECRET") or os.getenv("RAZORPAY_KEY_SECRET", "")).strip()
        webhook_secret = (current_app.config.get("RAZORPAY_WEBHOOK_SECRET") or os.getenv("RAZORPAY_WEBHOOK_SECRET", "")).strip()
        app_secret = str(current_app.config.get("SECRET_KEY") or "test-fallback-key")
    else:
        key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
        key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
        webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
        app_secret = os.getenv("SECRET_KEY", "test-fallback-key")

    return {
        "key_id": key_id,
        "key_secret": key_secret,
        "webhook_secret": webhook_secret,
        "app_secret": app_secret,
    }


def is_live_razorpay_key(key_id):
    """Guardrail: prevent accidental use of live Razorpay keys in TEST MODE ONLY app."""
    return bool(key_id and key_id.startswith("rzp_live_") and os.getenv("ALLOW_LIVE_RAZORPAY", "") != "1")


def has_live_test_credentials(creds=None):
    """True when valid Razorpay Test API keys (rzp_test_*) are supplied."""
    creds = creds or get_razorpay_credentials()
    return bool(creds["key_id"].startswith("rzp_test_") and creds["key_secret"])


def _signing_secret_for_order(order_id, creds):
    """Return key_secret for real rzp_test orders or derived sandbox HMAC secret for local test orders."""
    if str(order_id or "").startswith("order_sim_"):
        return hashlib.sha256(f"rzp_sim::{creds['app_secret']}".encode("utf-8")).hexdigest()
    return creds["key_secret"] or hashlib.sha256(f"rzp_sim::{creds['app_secret']}".encode("utf-8")).hexdigest()


def compute_tax_breakdown(total_cost):
    """Split GST-inclusive session total (18% GST) accurately in INR without altering ledger sum."""
    total = round(Decimal(str(total_cost or 0)), 2)
    if total <= 0:
        return {"base_amount": Decimal("0.00"), "tax_amount": Decimal("0.00"), "total_amount": Decimal("0.00"), "amount_paise": 0}
    base = round(total / Decimal("1.18"), 2)
    tax = round(total - base, 2)
    return {
        "base_amount": base,
        "tax_amount": tax,
        "total_amount": total,
        "amount_paise": int(round(float(total) * 100)),
    }


def get_checkout_context(session_id, user_id):
    """Fetch complete session, station, dispenser, booking, and tax breakdown scoped to user_id."""
    row = query_one(
        "SELECT cs.session_id, cs.booking_id, cs.user_id, cs.point_id, cs.start_at, cs.end_at, "
        "       cs.energy_kwh, cs.tariff_per_kwh, cs.total_cost, cs.session_status, "
        "       cp.point_code, cp.connector_type, cp.max_power_kw, "
        "       s.station_id, s.station_name, s.address, s.city, s.state, s.postal_code, s.operator_name, "
        "       v.registration_no, v.make, v.model, "
        "       u.full_name AS customer_name, u.email AS customer_email, u.phone AS customer_phone "
        "FROM ChargingSessions cs "
        "JOIN ChargingPoints cp ON cp.point_id = cs.point_id "
        "JOIN Stations s ON s.station_id = cp.station_id "
        "JOIN Vehicles v ON v.vehicle_id = cs.vehicle_id "
        "JOIN Users u ON u.user_id = cs.user_id "
        "WHERE cs.session_id = %s",
        (session_id,),
    )
    if not row:
        return None, "Charging session not found."
    if int(row["user_id"]) != int(user_id):
        return None, "Permission denied: Session does not belong to your account."

    latest_pay = query_one(
        "SELECT payment_id, transaction_reference, razorpay_order_id, razorpay_payment_id, "
        "       amount, base_amount, tax_amount, payment_method, gateway_provider, payment_status, paid_at "
        "FROM Payments WHERE session_id = %s "
        "ORDER BY (payment_status = 'SUCCESS') DESC, payment_id DESC LIMIT 1",
        (session_id,),
    )
    row["breakdown"] = compute_tax_breakdown(row["total_cost"])
    row["payment"] = latest_pay
    return row, None


def create_razorpay_order(session_id, user_id, payment_method="UPI"):
    """
    Validate session ownership, compute server-side amount, create Razorpay TEST order
    (or signed local test sandbox order if API keys are unconfigured), and persist PENDING row.
    """
    creds = get_razorpay_credentials()
    if is_live_razorpay_key(creds["key_id"]):
        return None, "Security block: Live Razorpay credentials are disabled. Only TEST MODE (rzp_test_*) is permitted."

    method = (payment_method or "UPI").strip().upper().replace(" ", "_")
    if method not in VALID_CHECKOUT_METHODS:
        method = "UPI"

    try:
        with transaction() as cur:
            cur.execute(
                "SELECT session_id, booking_id, user_id, total_cost, session_status "
                "FROM ChargingSessions WHERE session_id = %s FOR UPDATE",
                (session_id,),
            )
            sess = cur.fetchone()
            if not sess:
                return None, "Charging session not found."
            if int(sess["user_id"]) != int(user_id):
                return None, "Permission denied: Session does not belong to your account."
            if sess["session_status"] != "COMPLETED":
                return None, "Only completed charging sessions can be paid."

            cur.execute(
                "SELECT payment_id, transaction_reference FROM Payments "
                "WHERE session_id = %s AND payment_status = 'SUCCESS' FOR UPDATE",
                (session_id,),
            )
            settled = cur.fetchone()
            if settled:
                return None, f"Session is already settled under transaction {settled['transaction_reference']}."

            breakdown = compute_tax_breakdown(sess["total_cost"])
            if breakdown["amount_paise"] < 100:
                return None, "Minimum ₹1.00 bill amount is required for Razorpay test checkout."

            sandbox_mode = not has_live_test_credentials(creds)
            tx_ref = f"RZPTST-{uuid.uuid4().hex[:8].upper()}"

            if not sandbox_mode:
                resp = requests.post(
                    RAZORPAY_ORDERS_URL,
                    auth=(creds["key_id"], creds["key_secret"]),
                    json={
                        "amount": breakdown["amount_paise"],
                        "currency": "INR",
                        "receipt": f"ev_sess_{session_id}_{uuid.uuid4().hex[:6]}",
                        "payment_capture": 1,
                        "notes": {
                            "session_id": str(session_id),
                            "user_id": str(user_id),
                            "mode": "ACADEMIC_TEST_MODE",
                        },
                    },
                    timeout=10,
                )
                if resp.status_code not in (200, 201):
                    return None, f"Razorpay order creation failed (HTTP {resp.status_code})."
                rzp_order = resp.json()
                order_id = rzp_order["id"]
            else:
                order_id = f"order_sim_{uuid.uuid4().hex[:14]}"

            cur.execute(
                "INSERT INTO Payments "
                "(session_id, booking_id, transaction_reference, razorpay_order_id, amount, base_amount, tax_amount, "
                " currency, payment_method, gateway_provider, payment_status, is_simulated, simulation_note) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'INR', %s, 'RAZORPAY_TEST', 'PENDING', 1, %s)",
                (
                    session_id,
                    sess.get("booking_id"),
                    tx_ref,
                    order_id,
                    breakdown["total_amount"],
                    breakdown["base_amount"],
                    breakdown["tax_amount"],
                    method,
                    "RAZORPAY TEST MODE CHECKOUT — NO REAL MONEY CHARGED",
                ),
            )
            payment_row_id = cur.lastrowid

        return {
            "order_id": order_id,
            "payment_row_id": payment_row_id,
            "transaction_reference": tx_ref,
            "amount_paise": breakdown["amount_paise"],
            "amount_inr": float(breakdown["total_amount"]),
            "base_amount": float(breakdown["base_amount"]),
            "tax_amount": float(breakdown["tax_amount"]),
            "currency": "INR",
            "key_id": creds["key_id"] if not sandbox_mode else "rzp_test_sandbox_demo",
            "sandbox_mode": sandbox_mode,
        }, None
    except requests.RequestException as exc:
        return None, f"Razorpay API network failure: {str(exc)}"
    except Exception as exc:
        return None, f"Unable to create Razorpay test order: {str(exc)}"


def verify_payment_signature(order_id, payment_id, signature, secret_override=None):
    """Verify Razorpay Checkout signature HMAC-SHA256(order_id|payment_id, secret)."""
    if not order_id or not payment_id or not signature:
        return False
    creds = get_razorpay_credentials()
    secret = secret_override or _signing_secret_for_order(order_id, creds)
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def generate_sandbox_payment_proof(order_id):
    """Server-issued simulated test payment ID + valid HMAC signature for sandbox test checkout only."""
    if not str(order_id or "").startswith("order_sim_"):
        return None, None
    creds = get_razorpay_credentials()
    payment_id = f"pay_sim_{uuid.uuid4().hex[:14]}"
    secret = _signing_secret_for_order(order_id, creds)
    sig = hmac.new(secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256).hexdigest()
    return payment_id, sig


def verify_and_settle_razorpay_payment(
    session_id,
    user_id,
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature,
    payment_method="UPI",
):
    """
    Cryptographically verify Razorpay payment signature (and API payment status when live test keys exist),
    enforce session & order ownership, and finalize database settlement atomically.
    """
    creds = get_razorpay_credentials()
    if is_live_razorpay_key(creds["key_id"]):
        return None, "Live Razorpay mode is prohibited in this environment."

    if not verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        log_audit_event(
            action="RAZORPAY_SIGNATURE_FAILED",
            entity_name="Payments",
            entity_id=session_id,
            user_id=user_id,
            details=f"Invalid Razorpay signature for order {razorpay_order_id}",
        )
        return None, "Payment verification failed: Invalid Razorpay signature."

    method = (payment_method or "UPI").strip().upper().replace(" ", "_")
    if method not in VALID_CHECKOUT_METHODS:
        method = "UPI"

    try:
        with transaction() as cur:
            cur.execute(
                "SELECT session_id, booking_id, user_id, total_cost, session_status "
                "FROM ChargingSessions WHERE session_id = %s FOR UPDATE",
                (session_id,),
            )
            sess = cur.fetchone()
            if not sess:
                return None, "Charging session not found."
            if int(sess["user_id"]) != int(user_id):
                return None, "Permission denied: Session does not belong to your account."

            cur.execute(
                "SELECT payment_id, transaction_reference, payment_status, amount "
                "FROM Payments WHERE session_id = %s AND razorpay_order_id = %s FOR UPDATE",
                (session_id, razorpay_order_id),
            )
            order_row = cur.fetchone()
            if not order_row:
                return None, "Matching Razorpay order for this session was not found."

            if order_row["payment_status"] == "SUCCESS":
                return order_row, None

            # Reject if session already paid under another order
            cur.execute(
                "SELECT transaction_reference FROM Payments WHERE session_id = %s AND payment_status = 'SUCCESS' FOR UPDATE",
                (session_id,),
            )
            already = cur.fetchone()
            if already:
                return None, f"Session already paid under transaction {already['transaction_reference']}."

            # Double-verify payment state against Razorpay API if real test order
            if not str(razorpay_order_id).startswith("order_sim_") and has_live_test_credentials(creds):
                r = requests.get(
                    RAZORPAY_PAYMENT_URL_TMPL.format(payment_id=razorpay_payment_id),
                    auth=(creds["key_id"], creds["key_secret"]),
                    timeout=10,
                )
                if r.status_code != 200:
                    return None, "Unable to verify Razorpay payment status with gateway."
                pdata = r.json()
                expected_paise = int(round(float(sess["total_cost"]) * 100))
                if pdata.get("order_id") != razorpay_order_id or int(pdata.get("amount", 0)) != expected_paise:
                    return None, "Gateway order or amount mismatch."
                if pdata.get("status") not in ("captured", "authorized"):
                    return None, f"Payment status '{pdata.get('status')}' is not captured."

            now_dt = datetime.now()
            cur.execute(
                "UPDATE Payments "
                "SET payment_status = 'SUCCESS', razorpay_payment_id = %s, razorpay_signature = %s, "
                "    payment_method = %s, paid_at = %s, "
                "    simulation_note = 'RAZORPAY TEST MODE VERIFIED — NO REAL MONEY CHARGED' "
                "WHERE payment_id = %s",
                (razorpay_payment_id, razorpay_signature, method, now_dt, order_row["payment_id"]),
            )
            order_row["payment_status"] = "SUCCESS"
            order_row["razorpay_payment_id"] = razorpay_payment_id

        log_audit_event(
            action="RAZORPAY_TEST_PAYMENT_VERIFIED",
            entity_name="Payments",
            entity_id=order_row["payment_id"],
            user_id=user_id,
            details=f"Verified Razorpay test payment {razorpay_payment_id} for order {razorpay_order_id}",
        )
        return order_row, None
    except Exception as exc:
        return None, f"Failed to verify payment settlement: {str(exc)}"


def verify_webhook_signature(raw_body, signature_header, secret_override=None):
    """Verify Razorpay webhook HMAC-SHA256 signature against exact raw request body."""
    if not raw_body or not signature_header:
        return False
    creds = get_razorpay_credentials()
    secret = secret_override or creds["webhook_secret"]
    if not secret:
        return False
    body_bytes = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip())


def process_razorpay_webhook(raw_body, signature_header, event_id_header=None, secret_override=None):
    """
    Process Razorpay webhook events (payment.captured, payment.failed, order.paid) safely:
    - Enforces HMAC-SHA256 signature verification
    - Deduplicates repeated deliveries via PaymentWebhookEvents.event_id
    - Updates matching order payment state inside an InnoDB transaction
    """
    if not verify_webhook_signature(raw_body, signature_header, secret_override=secret_override):
        return 401, {"success": False, "error": "Invalid or missing Razorpay webhook signature."}

    try:
        payload = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body)
    except Exception:
        return 400, {"success": False, "error": "Malformed JSON webhook payload."}

    event_type = (payload.get("event") or "").strip()
    if event_type not in ("payment.captured", "payment.failed", "order.paid"):
        return 200, {"success": True, "status": "IGNORED_UNHANDLED_EVENT", "event": event_type}

    p_entity = (payload.get("payload") or {}).get("payment", {}).get("entity", {}) or {}
    o_entity = (payload.get("payload") or {}).get("order", {}).get("entity", {}) or {}
    order_id = p_entity.get("order_id") or o_entity.get("id")
    payment_id = p_entity.get("id")
    event_id = (
        (event_id_header or "").strip()
        or f"{event_type}:{order_id or 'none'}:{payment_id or hashlib.sha256(str(payload).encode()).hexdigest()[:12]}"
    )

    try:
        with transaction() as cur:
            cur.execute(
                "SELECT webhook_id FROM PaymentWebhookEvents WHERE event_id = %s FOR UPDATE",
                (event_id,),
            )
            if cur.fetchone():
                return 200, {"success": True, "status": "DUPLICATE_IGNORED", "event_id": event_id}

            target_status = "FAILED" if event_type == "payment.failed" else "SUCCESS"
            if order_id:
                cur.execute(
                    "SELECT payment_id, payment_status, session_id FROM Payments "
                    "WHERE razorpay_order_id = %s FOR UPDATE",
                    (order_id,),
                )
                pay_row = cur.fetchone()
                if pay_row:
                    # Never downgrade an already captured SUCCESS record on out-of-order failure webhook
                    if not (pay_row["payment_status"] == "SUCCESS" and target_status == "FAILED"):
                        cur.execute(
                            "UPDATE Payments SET payment_status = %s, razorpay_payment_id = COALESCE(%s, razorpay_payment_id), "
                            "paid_at = CASE WHEN %s = 'SUCCESS' THEN COALESCE(paid_at, NOW()) ELSE paid_at END "
                            "WHERE payment_id = %s",
                            (target_status, payment_id, target_status, pay_row["payment_id"]),
                        )

            summary = json.dumps({"order_id": order_id, "payment_id": payment_id, "target": target_status})[:500]
            cur.execute(
                "INSERT INTO PaymentWebhookEvents "
                "(event_id, event_type, razorpay_order_id, razorpay_payment_id, signature_verified, processing_status, payload_summary) "
                "VALUES (%s, %s, %s, %s, 1, 'PROCESSED', %s)",
                (event_id, event_type, order_id, payment_id, summary),
            )

        log_audit_event(
            action=f"RAZORPAY_WEBHOOK_{event_type.upper().replace('.', '_')}",
            entity_name="PaymentWebhookEvents",
            entity_id=None,
            user_id=None,
            details=f"Processed event {event_id} for order {order_id}",
        )
        return 200, {"success": True, "status": "PROCESSED", "event_id": event_id}
    except Exception as exc:
        return 500, {"success": False, "error": f"Webhook processing failure: {str(exc)}"}
