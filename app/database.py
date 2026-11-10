import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_supabase_client():
    """Connect to Supabase."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError("Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    return create_client(url, key)


def test_database_connection():
    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id")
        .limit(1)
        .execute()
    )

    return {
        "connected": True,
        "message": "Supabase connection successful.",
        "rows_checked": len(result.data or []),
    }


def save_scan_report(report, card_uid="DEMO-USER"):
    """Save an AI report against an RFID profile."""
    client = get_supabase_client()

    profile_result = (
        client.table("profiles")
        .upsert(
            {"card_uid": card_uid.strip()},
            on_conflict="card_uid",
        )
        .execute()
    )

    if not profile_result.data:
        raise RuntimeError("Could not find or create profile.")

    profile_id = profile_result.data[0]["id"]

    scan_area = report.get("scan_area") if isinstance(report, dict) else None

    scan_result = (
        client.table("scans")
        .insert({
            "profile_id": profile_id,
            "scan_area": scan_area,
            "report": report,
        })
        .execute()
    )

    if not scan_result.data:
        raise RuntimeError("Scan report was not saved.")

    return {
        "saved": True,
        "scan_id": scan_result.data[0]["id"],
        "profile_id": profile_id,
    }


def register_profile(card_uid, display_name):
    """Create or update an RFID profile."""
    card_uid = card_uid.strip()
    display_name = display_name.strip()

    if not card_uid or not display_name:
        raise ValueError("Card UID and name are required.")

    client = get_supabase_client()

    result = (
        client.table("profiles")
        .upsert(
            {
                "card_uid": card_uid,
                "display_name": display_name,
            },
            on_conflict="card_uid",
        )
        .execute()
    )

    if not result.data:
        raise RuntimeError("Could not save profile.")

    profile = result.data[0]

    return {
        "profile_id": profile["id"],
        "display_name": profile["display_name"],
        "card_uid": profile["card_uid"],
    }


def create_profile(card_uid, display_name):
    """Register a new patient."""
    card_uid = card_uid.strip()
    display_name = display_name.strip()

    if not card_uid or not display_name:
        raise ValueError("Card UID and name are required.")

    client = get_supabase_client()

    existing = (
        client.table("profiles")
        .select("id")
        .eq("card_uid", card_uid)
        .limit(1)
        .execute()
    )

    if existing.data:
        raise ValueError("This RFID card is already registered.")

    result = (
        client.table("profiles")
        .insert({
            "card_uid": card_uid,
            "display_name": display_name,
        })
        .execute()
    )

    if not result.data:
        raise RuntimeError("Profile registration failed.")

    profile = result.data[0]

    return {
        "profile_id": profile["id"],
        "display_name": profile["display_name"],
        "card_uid": profile["card_uid"],
    }


def list_profiles():
    """Get all registered patients."""
    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id, card_uid, display_name, created_at")
        .order("created_at", desc=True)
        .execute()
    )

    return result.data or []


def find_profile(card_uid, display_name):
    """Find a profile using RFID UID and name."""
    card_uid = card_uid.strip()
    display_name = display_name.strip()

    if not card_uid or not display_name:
        raise ValueError("Name and RFID UID are required.")

    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id, card_uid, display_name")
        .eq("card_uid", card_uid)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError("No profile found.")

    profile = result.data[0]

    if (profile.get("display_name") or "").strip().casefold() != display_name.casefold():
        raise ValueError("Name does not match this RFID card.")

    return {
        "profile_id": profile["id"],
        "display_name": profile["display_name"],
        "card_uid": profile["card_uid"],
    }


def find_profile_by_card_uid(card_uid):
    """Find a patient using RFID UID only."""
    card_uid = card_uid.strip()

    if not card_uid:
        raise ValueError("RFID card UID is required.")

    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id, card_uid, display_name")
        .eq("card_uid", card_uid)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    profile = result.data[0]

    return {
        "profile_id": profile["id"],
        "display_name": profile["display_name"],
        "card_uid": profile["card_uid"],
    }


def get_scan_history(card_uid):
    """Get all previous scans for one RFID patient."""
    profile = find_profile_by_card_uid(card_uid)

    if not profile:
        raise ValueError("Patient not found. Register the RFID card first.")

    client = get_supabase_client()

    result = (
        client.table("scans")
        .select("id, profile_id, scanned_at, scan_area, report")
        .eq("profile_id", profile["profile_id"])
        .order("scanned_at", desc=True)
        .limit(100)
        .execute()
    )

    return {
        "patient": profile,
        "total_scans": len(result.data or []),
        "scans": result.data or [],
    }