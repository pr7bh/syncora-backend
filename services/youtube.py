import os
import requests


API_URL = "https://www.youtubetranscript.dev/api/v2/transcribe"


def get_youtube_transcript(url: str):

    api_key = os.getenv("YOUTUBE_TRANSCRIPT_API_KEY")

    if not api_key:
        raise ValueError(
            "YOUTUBE_TRANSCRIPT_API_KEY is not configured"
        )

    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "video": url,
            "source": "auto",
            "format": {
                "timestamp": True,
                "paragraphs": False,
                "words": False,
            },
        },
        timeout=60,
    )

    if not response.ok:
        try:
            error_data = response.json()
            error_message = error_data.get(
                "message",
                "Failed to retrieve YouTube transcript"
            )
        except Exception:
            error_message = response.text

        raise ValueError(error_message)

    data = response.json()

    transcript_data = data.get("data", {}).get("transcript")

    if not transcript_data:
        raise ValueError(
            "No transcript was returned for this YouTube video"
        )

    segments = []

    for item in transcript_data.get("segments", []):

        start_ms = float(item.get("start", 0))
        end_ms = float(item.get("end", start_ms))

        segments.append({
            "start": start_ms / 1000,
            "end": end_ms / 1000,
            "text": item.get("text", "").strip()
        })

    text = transcript_data.get("text", "").strip()

    return {
        "text": text,
        "segments": segments
    }