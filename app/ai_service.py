import json
import os
import logging
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, UnidentifiedImageError

from app.prompts import SYSTEM_PROMPT

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Logging
logger = logging.getLogger(__name__)

# Gemini configuration
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

client = (
    genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(
            api_version="v1beta"
        )
    )
    if API_KEY else None
)

# Supported languages
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
    """Generate an experimental AI image assessment."""

    # Check API key
    if client is None:
        raise RuntimeError(
            "Gemini API key is missing. "
            "Check GEMINI_API_KEY in Vercel Environment Variables."
        )

    # Validate image type
    if mime_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        raise ValueError(
            "Only JPG, PNG, and WEBP images are supported."
        )

    # Validate language
    if language not in LANGUAGES:
        language = "en"

    # Validate image
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()

    except (UnidentifiedImageError, OSError) as error:
        raise ValueError(
            "The uploaded file is not a valid image."
        ) from error

    # Language instructions
    language_instructions = {
        "en": """
Write the complete report in simple English.
""",
        "hi": """
Write the complete report in simple Hindi using Devanagari script.
Do not write descriptions in English.
""",
        "pa": """
Write the complete report in natural Punjabi using Gurmukhi script.
Do not write descriptions in English or Hindi.
""",
    }

    language_instruction = (
        language_instructions[language]
        + """
IMPORTANT LANGUAGE RULES:

- Keep all JSON keys exactly as defined in the system prompt.
- Translate EVERY human-readable value.
- Translate all observations and possible explanations.
- Translate confidence descriptions and care advice.
- Translate warning signs and urgency.
- Translate doctor recommendations and limitations.
- Translate all lists and nested objects.
- Do not leave report sections in English.
- Use short and simple sentences.
- Return valid JSON only.
- Do not include Markdown.
"""
    )

    # Gemini image analysis
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                SYSTEM_PROMPT,
                language_instruction,
                (
                    "Carefully review this image. "
                    "Describe only visible features. "
                    "Do not make a definitive diagnosis "
                    "or prescribe medication."
                ),
                genai.types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
            ],
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        )

    except Exception as error:
        logger.exception(
            "Gemini API failed. Model: %s",
            MODEL_NAME,
        )

        raise RuntimeError(
            f"Gemini API failed: "
            f"{type(error).__name__}: {error}"
        ) from error

    # Check response
    if not response.text:
        raise RuntimeError(
            "Gemini returned an empty report. Please try again."
        )

    # Convert JSON response
    try:
        report = json.loads(response.text)

    except json.JSONDecodeError as error:
        logger.exception("Gemini returned invalid JSON.")

        raise RuntimeError(
            "Gemini returned an invalid report. Please try again."
        ) from error

    # Validate report
    if not isinstance(report, dict):
        raise RuntimeError(
            "Gemini returned an unexpected report format."
        )

    # Add disclaimer
    disclaimers = {
    "en": "Experimental visual assessment only; this is not a medical diagnosis.",
    "hi": "यह केवल प्रायोगिक दृश्य आकलन है; यह चिकित्सा निदान नहीं है।",
    "pa": "ਇਹ ਸਿਰਫ਼ ਪ੍ਰਯੋਗਾਤਮਕ ਤਸਵੀਰੀ ਮੁਲਾਂਕਣ ਹੈ; ਇਹ ਡਾਕਟਰੀ ਨਿਦਾਨ ਨਹੀਂ ਹੈ।",
}

    report.setdefault("disclaimer", disclaimers[language])

    logger.info(
        "Image analysis completed successfully. Language: %s",
        language,
    )

    return report