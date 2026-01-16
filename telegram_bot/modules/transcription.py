"""
Audio transcription using Google Gemini.
"""

import os
import google.generativeai as genai


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcribe audio to text using Gemini."""
    api_key = os.environ.get("GOOGLE_AI_API_KEY")

    if not api_key:
        return "Error: GOOGLE_AI_API_KEY not configured"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-001")

        response = model.generate_content([
            "Transcribe this audio accurately. Return only the transcription.",
            {"mime_type": mime_type, "data": audio_bytes}
        ])

        return response.text.strip()

    except Exception as e:
        return f"Error transcribing: {str(e)}"
