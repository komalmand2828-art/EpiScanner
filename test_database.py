from app.database import register_profile

if __name__ == "__main__":
    result = register_profile(
        card_uid="DEMO-CARD-001",
        display_name="Test Person",
    )

    print("Profile saved successfully!")
    print("Name:", result["display_name"])
    print("Card UID:", result["card_uid"])
    print("Internal profile ID:", result["profile_id"])