from pathlib import Path
import io

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai_service import analyse_image
from app.database import (
    save_scan_report,
    create_profile,
    list_profiles,
    find_profile,
    find_profile_by_card_uid,
    get_scan_history,
)    
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

MAX_IMAGE_MB = 8
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_LANGUAGES = {"en", "hi", "pa"}

class ProfileRegistration(BaseModel):
    card_uid: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)

class ProfileLookup(BaseModel):
    card_uid: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)    

app = FastAPI(
    title="EpiScanner API",
    description=(
        "Experimental AI-assisted skin, scalp and hair image assessment. "
        "Not a medical diagnostic system."
    ),
    version="0.2.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


@app.get("/", include_in_schema=False)
async def home():
    index_file = STATIC_DIR / "index.html"

    if not index_file.is_file():
        raise HTTPException(
            status_code=500,
            detail="Dashboard file static/index.html was not found.",
        )

    return FileResponse(index_file)


@app.get("/health")
async def health():
    return {
        "status": "running",
        "application": "EpiScanner",
        "ai_provider": "gemini",
        "supported_languages": ["en", "hi", "pa"],
        "medical_status": "experimental_not_diagnostic",
    }

@app.post("/api/profiles")
async def register_person(profile: ProfileRegistration):
    try:
        result = create_profile(
            card_uid=profile.card_uid,
            display_name=profile.display_name,
        )

        return {
            "success": True,
            "message": "Profile registered successfully.",
            "profile": result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        print(
            f"Profile registration failed: "
            f"{type(exc).__name__}: {exc}"
        )
        raise HTTPException(
            status_code=500,
            detail="Could not register the profile. Check the server terminal.",
        ) from exc

@app.get("/api/profiles")
async def get_profiles():
    try:
        profiles = list_profiles()
        return {
            "success": True,
            "profiles": profiles
        }
    except Exception as exc:
        print(f"Could not retrieve profiles: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve profiles from the database."
        ) from exc    

@app.get("/api/capture")
async def capture_from_pi_camera():
    """
    Capture a still image from a Raspberry Pi camera.
    Requires Picamera2 on a compatible Raspberry Pi OS installation.
    """

    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Raspberry Pi camera support is not installed on this device.",
        ) from exc

    try:
        camera = Picamera2()
        try:
            camera.configure(camera.create_still_configuration())
            camera.start()
            camera.capture_file("/tmp/episcan_capture.jpg")
        finally:
            camera.stop()
            camera.close()

        with open("/tmp/episcan_capture.jpg", "rb") as image_file:
            image_bytes = image_file.read()

        if not image_bytes:
            raise RuntimeError("The camera returned an empty image.")

        from fastapi.responses import Response

        return Response(
            content=image_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Raspberry Pi camera capture failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not capture an image. Check the Raspberry Pi camera connection.",
        ) from exc

@app.post("/api/profiles/lookup")
async def lookup_person(profile: ProfileLookup):
    try:
        result = find_profile(
            card_uid=profile.card_uid,
            display_name=profile.display_name,
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="No matching profile found. Check your name and RFID UID.",
            )

        return {
            "success": True,
            "message": "Profile found successfully.",
            "profile": result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        print(f"Profile lookup failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not look up the profile. Check the server terminal.",
        ) from exc


@app.post("/api/analyse")
async def analyse(
    file: UploadFile = File(...),
    language: str = Form("en"),
    card_uid: str | None = Form(default=None),
):
    save_result = None

    try:
        if file.content_type not in ALLOWED_TYPES:
            raise HTTPException(415, "Upload JPG, PNG, or WEBP.")

        if language not in ALLOWED_LANGUAGES:
            raise HTTPException(400, "Choose English, Hindi, or Punjabi.")

        image_bytes = await file.read(MAX_IMAGE_BYTES + 1)

        if not image_bytes:
            raise HTTPException(400, "Uploaded image is empty.")

        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image must not exceed 8 MB.")

        # AI image analysis
        report = analyse_image(
            image_bytes=image_bytes,
            mime_type=file.content_type,
            language=language,
        )

        # Save report for registered RFID user
        if card_uid and card_uid.strip():
            try:
                storage_result = save_scan_report(
                    report,
                    card_uid=card_uid.strip(),
                )
                print("Scan storage result:", save_result)

            except Exception as storage_error:
                print(
                    "Storage error:",
                    type(storage_error).__name__,
                    str(storage_error),
                )

        return {
            "success": True,
            "filename": file.filename,
            "language": language,
            "report": report,
            "storage": save_result,
        }

    except HTTPException:
        raise

    except ValueError as error:
        print("Image validation error:", str(error))
        raise HTTPException(400, detail=str(error)) from error

    except RuntimeError as error:
        print("AI service error:", str(error))
        raise HTTPException(502, detail=str(error)) from error

    except Exception as error:
        print(
            "EpiScanner error:",
            type(error).__name__,
            str(error),
        )
        raise HTTPException(
            500,
            detail="Analysis failed. Check server logs.",
        ) from error

    finally:
        await file.close()

@app.get("/api/history/{card_uid}")
async def get_patient_history(card_uid: str):
    try:
        profile = find_profile(
            card_uid=card_uid,
            display_name=""
        )

        if not profile:
            raise HTTPException(status_code=404, detail="Patient not found")

        history = get_scan_history(card_uid)

        return {
            "success": True,
            "history": history
        }

    except HTTPException:
        raise
    except Exception as exc:
        print("History error:", str(exc))
        raise HTTPException(status_code=500, detail="History unavailable")

@app.get("/api/history/{card_uid}")
async def patient_history(card_uid: str):
    try:
        result = get_scan_history(card_uid)

        return {
            "success": True,
            "history": result
        }

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    except Exception as exc:
        print("History error:", str(exc))
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve patient history."
        )