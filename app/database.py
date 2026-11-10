import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_supabase_client():
    """Create a client for the EpiScanner cloud database."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Supabase configuration is missing. Check the root .env file."
        )

    return create_client(url, key)


def test_database_connection():
    """Check whether the backend can query the cloud database."""
    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id")
        .limit(1)
        .execute()
    )

    return {
        "connected": True,
        "message": "Supabase database connection successful.",
        "rows_checked": len(result.data),
    }

def save_scan_report(report, card_uid="DEMO-USER"):
    """Save an AI report under a profile in Supabase."""
    client = get_supabase_client()

    # Find the profile or create it if it does not exist.
    profile_result = (
        client.table("profiles")
        .upsert(
            {"card_uid": card_uid},
            on_conflict="card_uid",
        )
        .execute()
    )

    if not profile_result.data:
        raise RuntimeError("Could not create or find the scan profile.")

    profile_id = profile_result.data[0]["id"]

    # Extract the scan area when the AI report provides one.
    scan_area = None
    if isinstance(report, dict):
        scan_area = report.get("scan_area")

    # Save the report as JSON in the cloud database.
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
        raise RuntimeError("The scan report was not saved.")

    return {
        "saved": True,
        "scan_id": scan_result.data[0]["id"],
        "profile_id": profile_id,
    }

def register_profile(card_uid, display_name):
    """Create or update a profile associated with an RFID card."""
    card_uid = card_uid.strip()
    display_name = display_name.strip()

    if not card_uid or not display_name:
        raise ValueError("Both card UID and display name are required.")

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
        raise RuntimeError("Could not save the profile.")

    profile = result.data[0]

    return {
        "profile_id": profile["id"],
        "display_name": profile["display_name"],
        "card_uid": profile["card_uid"],
    }

def create_profile(card_uid, display_name):
    """Register a new person with a unique RFID card."""
    card_uid = card_uid.strip()
    display_name = display_name.strip()

    if not card_uid or not display_name:
        raise ValueError("Card UID and person's name are required.")

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
    """Retrieve registered profiles from Supabase."""
    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id, card_uid, display_name, created_at")
        .order("created_at", desc=True)
        .execute()
    )

    return result.data or []

def find_profile(card_uid, display_name):
    """Find an existing profile using its RFID UID and registered name."""
    card_uid = card_uid.strip()
    display_name = display_name.strip()

    if not card_uid or not display_name:
        raise ValueError("Name and RFID card UID are required.")

    client = get_supabase_client()

    result = (
        client.table("profiles")
        .select("id, card_uid, display_name")
        .eq("card_uid", card_uid)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError("No profile found. Check your name and RFID card UID.")

    profile = result.data[0]

    if (profile.get("display_name") or "").strip().casefold() != display_name.casefold():
        raise ValueError("The name does not match this RFID card.")

    return {
        "profile_id": profile["id"],
        "display_name": profile["display_name"],
        "card_uid": profile["card_uid"],
    }