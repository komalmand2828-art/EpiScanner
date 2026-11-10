import json
import os
from io import BytesIO
import logging
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from google import genai
from PIL import Image, UnidentifiedImageError

from app.prompts import SYSTEM_PROMPT

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

client = genai.Client(api_key=API_KEY) if API_KEY else None

LANGUAGES = {
    "en": "simple English",
    "hi": "simple Hindi",
    "pa": "simple Punjabi",
}


def analyse_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    language: str = "en",
) -> dict:
    """Generate a concise experimental image assessment."""

    if client is None:
        raise RuntimeError(
            "Gemini API key is missing. Check GEMINI_API_KEY in the root .env file."
        )

    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Only JPG, PNG, and WEBP images are supported.")

    if language not in LANGUAGES:
        language = "en"

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise ValueError("The uploaded file is not a valid image.")

    language_instructions = {
        "en": """
Write the complete report in simple English.
""",
        "hi": """
Write the complete report in simple Hindi using Devanagari script (हिन्दी).
Do not write report descriptions in English.
""",
        "pa": """
Write the complete report in natural Punjabi using Gurmukhi script (ਪੰਜਾਬੀ).
Do not write report descriptions in English or Hindi.
"""
    }

    language_instruction = (
        language_instructions.get(language, language_instructions["en"])
        + """
IMPORTANT LANGUAGE RULES:
- Keep all JSON keys exactly as defined in the system prompt.
- Translate EVERY human-readable value into the selected language.
- Translate image quality, scan area, observations, possible explanations,
  reasoning, confidence descriptions, care advice, warning signs,
  urgency, doctor recommendations, limitations and disclaimer.
- Translate all text inside lists and nested objects.
- Do not leave any report section in English.
- Use short sentences and simple everyday language.
- Return valid JSON only, without Markdown or extra text.
"""
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                SYSTEM_PROMPT,
                language_instruction,
                (
                    "Carefully review this image. Describe only visible features. "
                    "Do not make a definitive diagnosis or prescribe medication."
                ),
                genai.types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
            ],
            config={
                "temperature": 0.2,
            },
        )
    except Exception as exc:
        print("GEMINI ERROR TYPE:", type(exc).__name__)

    print("GEMINI ERROR DETAILS:", repr(exc))

    print("GEMINI RESPONSE:", getattr(exc, "response_json", None))

    raise RuntimeError(

        f"Gemini API failed: {str(exc)}"

    ) from exc

    if not response.text:
        raise RuntimeError("The AI returned an empty report. Please try again.")

    try:
        report = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The AI returned an invalid report. Please try again.") from exc

    if not isinstance(report, dict):
        raise RuntimeError("The AI returned an unexpected report format.")

    report.setdefault(
        "disclaimer",
        "Experimental visual assessment only; this is not a medical diagnosis.",
    )

    return report