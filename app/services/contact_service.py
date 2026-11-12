"""
Contact & Web3Forms Enquiry Service
EV Charging Station Management System
"""
import os
import re
import requests
from flask import current_app
from app.db import query_all, query_one, execute

WEB3FORMS_ENDPOINT = "https://api.web3forms.com/submit"

CONTACT_CATEGORIES = (
    "General enquiry",
    "Charging station support",
    "Booking issue",
    "Payment issue",
    "Business partnership",
    "Technical support",
)

VALID_ENQUIRY_STATUSES = ("NEW", "IN_PROGRESS", "RESOLVED")

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_HEADER_INJECTION_RE = re.compile(r"[\r\n\x00]")


def _sanitize_header_text(value):
    """Strip CR/LF/NUL characters so user input can never inject email headers."""
    return _HEADER_INJECTION_RE.sub(" ", (value or "")).strip()


def validate_contact_payload(full_name, email, phone, subject, category, message, honeypot=""):
    """Validate contact form fields server-side. Returns (cleaned_dict, error_message)."""
    if (honeypot or "").strip():
        return None, "Spam check triggered. Submission rejected."

    clean_name = _sanitize_header_text(full_name)
    clean_email = _sanitize_header_text(email).lower()
    clean_phone = _sanitize_header_text(phone)
    clean_subject = _sanitize_header_text(subject)
    clean_category = (category or "").strip()
    clean_message = (message or "").replace("\x00", "").strip()

    if len(clean_name) < 2 or len(clean_name) > 120:
        return None, "Full name must be between 2 and 120 characters."
    if not clean_email or len(clean_email) > 150 or not _EMAIL_RE.match(clean_email):
        return None, "Please enter a valid email address."
    if clean_phone and len(clean_phone) > 25:
        return None, "Phone number must not exceed 25 characters."
    if len(clean_subject) < 3 or len(clean_subject) > 200:
        return None, "Subject must be between 3 and 200 characters."
    if clean_category not in CONTACT_CATEGORIES:
        return None, "Please select a valid enquiry category."
    if len(clean_message) < 10 or len(clean_message) > 2000:
        return None, "Message must be between 10 and 2000 characters."

    return {
        "full_name": clean_name,
        "email": clean_email,
        "phone": clean_phone or None,
        "subject": clean_subject,
        "category": clean_category,
        "message": clean_message,
    }, None


def _check_rate_limit_and_duplicate(email, subject, message, ip_address):
    """
    Serverless-safe DB-backed rate limiting and duplicate submission prevention.
    Returns error string if blocked, else None.
    """
    dup = query_one(
        "SELECT id FROM ContactMessages "
        "WHERE email = %s AND subject = %s AND message = %s "
        "  AND created_at >= (NOW() - INTERVAL 5 MINUTE) "
        "LIMIT 1",
        (email, subject, message)
    )
    if dup:
        return "Duplicate enquiry detected. Your previous submission was already received."

    ip_count_row = query_one(
        "SELECT COUNT(*) AS cnt FROM ContactMessages "
        "WHERE (ip_address = %s OR email = %s) "
        "  AND created_at >= (NOW() - INTERVAL 10 MINUTE)",
        (ip_address or "unknown", email)
    )
    if ip_count_row and int(ip_count_row["cnt"]) >= 5:
        return "Too many enquiries submitted recently. Please wait a few minutes before trying again."

    return None


def submit_contact_enquiry(full_name, email, phone, subject, category, message, honeypot="", ip_address=None):
    """
    Validate, rate-limit, persist to MySQL ContactMessages, and forward via Web3Forms API.
    Returns (contact_id, email_delivered_bool, user_feedback_message, is_validation_error).
    If email delivery fails after DB persistence, the DB row is preserved with
    email_delivery_status = 'FAILED'.
    """
    cleaned, val_err = validate_contact_payload(
        full_name, email, phone, subject, category, message, honeypot=honeypot
    )
    if val_err:
        return None, False, val_err, True

    limit_err = _check_rate_limit_and_duplicate(
        cleaned["email"], cleaned["subject"], cleaned["message"], ip_address
    )
    if limit_err:
        return None, False, limit_err, True

    # 1. Persist enquiry safely in MySQL first
    contact_id = execute(
        "INSERT INTO ContactMessages "
        "(full_name, email, phone, subject, category, message, submission_status, email_delivery_status, ip_address) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'NEW', 'PENDING', %s)",
        (
            cleaned["full_name"],
            cleaned["email"],
            cleaned["phone"],
            cleaned["subject"],
            cleaned["category"],
            cleaned["message"],
            (ip_address or "")[:45] or None,
        )
    )

    # 2. Deliver via Web3Forms backend proxy
    access_key = (
        (current_app.config.get("WEB3FORMS_ACCESS_KEY") if current_app else None)
        or os.getenv("WEB3FORMS_ACCESS_KEY", "")
    ).strip()

    if not access_key or access_key == "your_web3forms_access_key_here":
        execute(
            "UPDATE ContactMessages SET email_delivery_status = 'FAILED', email_error = %s WHERE id = %s",
            ("WEB3FORMS_ACCESS_KEY is not configured.", contact_id)
        )
        return (
            contact_id,
            False,
            f"Your enquiry (#{contact_id}) was saved, but email notification could not be sent because the mail service is not configured.",
            False,
        )

    payload = {
        "access_key": access_key,
        "from_name": "EV ChargeNet Contact Portal",
        "subject": f"[EV ChargeNet | {cleaned['category']}] {cleaned['subject']}",
        "replyto": cleaned["email"],
        "name": cleaned["full_name"],
        "email": cleaned["email"],
        "phone": cleaned["phone"] or "Not provided",
        "category": cleaned["category"],
        "enquiry_id": str(contact_id),
        "message": (
            f"Enquiry ID: #{contact_id}\n"
            f"Category: {cleaned['category']}\n"
            f"Sender: {cleaned['full_name']} <{cleaned['email']}>\n"
            f"Phone: {cleaned['phone'] or 'Not provided'}\n\n"
            f"{cleaned['message']}"
        ),
    }

    try:
        resp = requests.post(
            WEB3FORMS_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10,
        )
        data = {}
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code == 200 and data.get("success") is True:
            execute(
                "UPDATE ContactMessages SET email_delivery_status = 'SENT', email_error = NULL WHERE id = %s",
                (contact_id,)
            )
            return (
                contact_id,
                True,
                f"Thank you! Your enquiry (#{contact_id}) has been received and forwarded to our support team.",
                False,
            )

        err_detail = data.get("message") or f"HTTP {resp.status_code}"
        execute(
            "UPDATE ContactMessages SET email_delivery_status = 'FAILED', email_error = %s WHERE id = %s",
            (str(err_detail)[:250], contact_id)
        )
        return (
            contact_id,
            False,
            f"Your enquiry (#{contact_id}) was saved in our system, but email delivery failed ({err_detail}). Our team will still review it.",
            False,
        )
    except requests.RequestException as exc:
        execute(
            "UPDATE ContactMessages SET email_delivery_status = 'FAILED', email_error = %s WHERE id = %s",
            (str(exc)[:250], contact_id)
        )
        return (
            contact_id,
            False,
            f"Your enquiry (#{contact_id}) was saved in our system, but email delivery timed out or failed. Our team will still review it.",
            False,
        )


def get_contact_messages(status=None, limit=100):
    """Admin view: Retrieve customer enquiries ordered newest first."""
    sql = (
        "SELECT id, full_name, email, phone, subject, category, message, "
        "       submission_status, email_delivery_status, email_error, ip_address, created_at, updated_at "
        "FROM ContactMessages WHERE 1=1"
    )
    params = []
    if status and status in VALID_ENQUIRY_STATUSES:
        sql += " AND submission_status = %s"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(int(limit))
    return query_all(sql, params)


def update_contact_status(message_id, new_status):
    """Update enquiry workflow status (NEW, IN_PROGRESS, RESOLVED)."""
    normalized = (new_status or "").strip().upper()
    if normalized not in VALID_ENQUIRY_STATUSES:
        return False, f"Invalid enquiry status '{new_status}'."

    row = query_one("SELECT id, submission_status FROM ContactMessages WHERE id = %s", (message_id,))
    if not row:
        return False, "Enquiry not found."

    execute(
        "UPDATE ContactMessages SET submission_status = %s WHERE id = %s",
        (normalized, message_id)
    )
    return True, normalized

