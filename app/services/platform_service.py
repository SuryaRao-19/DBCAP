"""
Platform Identity, Verified Operator Reference, Social Links & Data Sources Service
EV Charging Station Management System
"""
from app.db import query_all, query_one, execute

VALID_DATA_STATUSES = ("VERIFIED", "DEMO", "ESTIMATED", "UNAVAILABLE")

# Verified Tata Power EZ Charge public scale disclosures (sourced from tatapower.com/ezcharge)
OFFICIAL_EZCHARGE_STATS = [
    {
        "value": "5,500+",
        "label": "Public & Captive Charging Points",
        "source_label": "Tata Power EZ Charge Portal",
        "source_url": "https://www.tatapower.com/ezcharge/",
        "verified_date": "2026-04-08",
    },
    {
        "value": "620+",
        "label": "Cities & Towns Covered (700+ target reach)",
        "source_label": "Tata Power EZ Charge Portal",
        "source_url": "https://www.tatapower.com/ezcharge/",
        "verified_date": "2026-04-08",
    },
    {
        "value": "1.2 Lakh+",
        "label": "Residential Home Chargers Deployed",
        "source_label": "Tata Power EZ Charge Portal",
        "source_url": "https://www.tatapower.com/ezcharge/",
        "verified_date": "2026-04-08",
    },
    {
        "value": "1,200+",
        "label": "Commercial E-Bus Charging Points",
        "source_label": "Tata Power EZ Charge Portal",
        "source_url": "https://www.tatapower.com/ezcharge/",
        "verified_date": "2026-04-08",
    },
]

# Official Tata Power EZ Charge & corporate milestones (sourced from tatapower.com / tatamotors.com)
VERIFIED_ANNOUNCEMENTS = [
    {
        "title": "700+ Cities Pan-India EV Charging Footprint",
        "date": "Verified Official Network Metric",
        "summary": "Tata Power EZ Charge reports presence across 700+ cities and towns with home, public AC/DC, highway, and e-bus charging points.",
        "source_name": "Tata Power EZ Charge Portal",
        "source_url": "https://www.tatapower.com/ezcharge/",
        "status": "VERIFIED",
    },
    {
        "title": "Metro Commercial EV Fast-Charging Corridor Expansion",
        "date": "September 2024 Release",
        "summary": "Tata Power Renewable Energy & Tata Motors announced dedicated commercial EV fast-charging hubs across Delhi, Mumbai, Bengaluru, Chennai, and Kolkata.",
        "source_name": "Tata Motors / Tata Power Announcement",
        "source_url": "https://www.tatapower.com/ezcharge/",
        "status": "VERIFIED",
    },
    {
        "title": "Academic Case Study & Demo Portal Boundary",
        "date": "Platform Notice",
        "summary": "EV ChargeNet showcases real Delhi NCR station addresses and Tata Power public facts, while reservations, kWh metering, and billing run in sandboxed MySQL Demo Mode.",
        "source_name": "EV ChargeNet Integrity Policy",
        "source_url": None,
        "status": "DEMO",
    },
]


def get_platform_operator():
    """Retrieve verified reference operator profile from MySQL."""
    try:
        op = query_one(
            "SELECT operator_id, operator_name, parent_company, official_website, "
            "       play_store_url, linktree_url, support_phone, support_email, "
            "       network_scale_summary, cities_coverage_summary, mission_text, vision_text, "
            "       services_summary, is_independent_case_study, verification_status, "
            "       source_url, last_verified_at "
            "FROM NetworkOperators ORDER BY operator_id LIMIT 1"
        )
        return op
    except Exception:
        return None


def get_verified_social_links():
    """Retrieve verified corporate social media links."""
    try:
        return query_all(
            "SELECT social_id, platform, display_label, handle, url, verification_status, source_url, last_verified_at "
            "FROM SocialLinks ORDER BY FIELD(platform, 'WEBSITE', 'LINKEDIN', 'X_TWITTER', 'INSTAGRAM', 'YOUTUBE', 'FACEBOOK')"
        )
    except Exception:
        return []


def get_data_sources():
    """Retrieve the complete Data Source Register ordered by status and item."""
    try:
        return query_all(
            "SELECT source_id, data_item, source_name, source_url, verification_date, "
            "       data_status, notes, last_updated "
            "FROM DataSources ORDER BY FIELD(data_status, 'VERIFIED', 'ESTIMATED', 'DEMO', 'UNAVAILABLE'), source_id"
        )
    except Exception:
        return []


def update_data_source(source_id, data_status, notes=None):
    """Admin action: update verification status and notes on a DataSources record."""
    normalized = (data_status or "").strip().upper()
    if normalized not in VALID_DATA_STATUSES:
        return False, f"Invalid status '{data_status}'. Must be one of {', '.join(VALID_DATA_STATUSES)}."

    row = query_one("SELECT source_id FROM DataSources WHERE source_id = %s", (source_id,))
    if not row:
        return False, "Data source entry not found."

    execute(
        "UPDATE DataSources SET data_status = %s, notes = COALESCE(%s, notes), verification_date = CURDATE() WHERE source_id = %s",
        (normalized, notes.strip() if notes else None, source_id),
    )
    return True, f"Data source #{source_id} updated to {normalized}."

