
import os
import re
import requests

FREETRANSCRIPT_URL = "https://api.freetranscriptapi.com/v1/transcript"
SUPADATA_URL = "https://api.supadata.ai/v1/youtube/transcript"

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


def _via_supadata(url: str) -> dict:
    """
    Supadata API (https://supadata.ai) — free tier, optional API key.
    Response: {"content": [{"text": "...", "offset": <ms>, "duration": <ms>, "lang": "en"}, ...]}
    offset and duration are in milliseconds; convert to seconds.
    """
    headers = {}
    api_key = os.getenv("SUPADATA_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    response = requests.get(
        SUPADATA_URL,
        params={"url": url, "text": "false"},
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        try:
            msg = response.json().get("message", response.text)
        except ValueError:
            msg = response.text
        print(f"Supadata failed: HTTP {response.status_code} - {msg}")
        raise ValueError(f"Supadata: HTTP {response.status_code}")

    data = response.json()
    content = data.get("content", [])

    if not content:
        raise ValueError("No transcript is available for this YouTube video.")

    segments = []
    for item in content:
        # offset and duration from Supadata are in milliseconds
        start = float(item.get("offset", 0)) / 1000
        duration = float(item.get("duration", 0)) / 1000
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


def _via_ytapi(url: str) -> dict:
    """
    youtube-transcript-api last-resort fallback.
    Note: This library uses HTML scraping and is typically blocked on cloud IPs.
    Included for completeness and local/non-cloud environments.
    """
    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
        )
    except ImportError as err:
        raise ValueError("youtube-transcript-api is not available.") from err

    video_id = _extract_video_id(url)

    try:
        fetched = YouTubeTranscriptApi().fetch(video_id)
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as err:
        print(f"youtube-transcript-api: no transcript ({type(err).__name__}): {err}")
        raise ValueError(
            "No transcript is available for this YouTube video. "
            "The video may not have captions enabled."
        ) from err
    except Exception as err:
        print(f"youtube-transcript-api failed ({type(err).__name__}): {err}")
        raise ValueError(
            "Could not retrieve the YouTube transcript via youtube-transcript-api."
        ) from err

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
    # Validate URL format before any network call
    _extract_video_id(url)

    # Provider 1: FreeTranscriptAPI
    try:
        return _via_freetranscript(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"FreeTranscriptAPI network error, trying Supadata: {err}")
    except ValueError as err:
        print(f"FreeTranscriptAPI error, trying Supadata: {err}")

    # Provider 2: Supadata
    try:
        return _via_supadata(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"Supadata network error, trying youtube-transcript-api: {err}")
    except ValueError as err:
        print(f"Supadata error, trying youtube-transcript-api: {err}")

    # Provider 3: youtube-transcript-api (last resort; blocked on most cloud IPs)
    return _via_ytapi(url)
