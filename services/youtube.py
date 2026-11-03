
import re
import requests
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

FREETRANSCRIPT_URL = "https://api.freetranscriptapi.com/v1/transcript"

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"
)


def _extract_video_id(url: str) -> str:
    match = _VIDEO_ID_RE.search(url)
    if not match:
        raise ValueError(
            "Could not extract a YouTube video ID from the provided URL."
        )
    return match.group(1)


def _segments_from_list(items: list) -> dict:
    segments = []
    for item in items:
        start = float(item.get("start", 0))
        duration = float(item.get("duration", 0))
        text = item.get("text", "").strip()
        if not text:
            continue
        segments.append({
            "start": start,
            "end": start + duration,
            "text": text,
        })
    if not segments:
        raise ValueError("The YouTube transcript contains no usable text.")
    return {
        "text": " ".join(s["text"] for s in segments),
        "segments": segments,
    }


def _via_freetranscript(url: str) -> dict:
    response = requests.get(
        FREETRANSCRIPT_URL,
        params={"video_url": url},
        timeout=60,
    )

    if not response.ok:
        try:
            error_details = response.json().get("error", {})
            msg = (
                error_details.get("message", str(error_details))
                if isinstance(error_details, dict)
                else str(error_details)
            )
        except ValueError:
            msg = response.text
        print(f"FreeTranscriptAPI failed: HTTP {response.status_code} - {msg}")
        raise ValueError(f"FreeTranscriptAPI: {msg}")

    data = response.json()
    transcript_data = data.get("transcript", [])
    if not transcript_data:
        raise ValueError("No transcript is available for this YouTube video.")
    return _segments_from_list(transcript_data)


def _via_ytapi(url: str) -> dict:
    video_id = _extract_video_id(url)
    fetched = YouTubeTranscriptApi().fetch(video_id)
    items = []
    for snippet in fetched:
        if hasattr(snippet, "text"):
            items.append({
                "text": snippet.text,
                "start": snippet.start,
                "duration": getattr(snippet, "duration", 0),
            })
        else:
            items.append(snippet)
    return _segments_from_list(items)


def get_youtube_transcript(url: str) -> dict:
    try:
        return _via_freetranscript(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"FreeTranscriptAPI network error, trying fallback: {err}")
    except ValueError as err:
        print(f"FreeTranscriptAPI error, trying fallback: {err}")

    try:
        return _via_ytapi(url)
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as err:
        print(f"youtube-transcript-api: no transcript ({type(err).__name__}): {err}")
        raise ValueError(
            "No transcript is available for this YouTube video. "
            "The video may not have captions enabled."
        ) from err
    except Exception as err:
        print(f"youtube-transcript-api fallback failed ({type(err).__name__}): {err}")
        raise ValueError(
            "Could not retrieve the YouTube transcript. Please try again later."
        ) from err
