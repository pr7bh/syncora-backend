
import os
import re
import requests

FREETRANSCRIPT_URL = "https://api.freetranscriptapi.com/v1/transcript"
SUPADATA_URL = "https://api.supadata.ai/v1/youtube/transcript"


class TranscriptNotAvailable(ValueError):
    """400 — invalid URL, video has no captions, private/deleted video."""


class TranscriptProviderError(Exception):
    """502 — all providers failed due to server/network issues."""

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"
)


def _extract_video_id(url: str) -> str:
    match = _VIDEO_ID_RE.search(url)
    if not match:
        raise TranscriptNotAvailable(
            "Invalid YouTube URL. Please provide a valid youtube.com or youtu.be link."
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
    Supadata API — requires SUPADATA_API_KEY env var (free signup at supadata.ai).
    Raises ValueError immediately if no key is configured.
    Response: {"content": [{"text": "...", "offset": <ms>, "duration": <ms>}]}
    offset and duration are milliseconds; converted to seconds.
    """
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        raise ValueError("SUPADATA_API_KEY is not configured.")

    response = requests.get(
        SUPADATA_URL,
        params={"url": url, "text": "false"},
        headers={"x-api-key": api_key},
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


def _via_timedtext(url: str) -> dict:
    """
    YouTube timedtext endpoint — no auth required, different path from
    the HTML watch-page scraping that cloud IPs have blocked.
    Used by the YouTube embed player on third-party sites.
    """
    import xml.etree.ElementTree as ET

    video_id = _extract_video_id(url)
    headers = {"User-Agent": "Mozilla/5.0"}

    list_resp = requests.get(
        "https://www.youtube.com/api/timedtext",
        params={"type": "list", "v": video_id},
        headers=headers,
        timeout=15,
    )

    if not list_resp.ok or not list_resp.text.strip():
        raise ValueError("No caption tracks found via timedtext endpoint.")

    try:
        root = ET.fromstring(list_resp.text)
    except ET.ParseError as err:
        raise ValueError("Could not parse timedtext track list.") from err

    tracks = root.findall("track")
    if not tracks:
        raise ValueError("No caption tracks available for this video.")

    lang_code = None
    for track in tracks:
        lc = track.get("lang_code", "")
        if lc.startswith("en"):
            lang_code = lc
            break
    if not lang_code:
        lang_code = tracks[0].get("lang_code", "")

    cap_resp = requests.get(
        "https://www.youtube.com/api/timedtext",
        params={"v": video_id, "lang": lang_code, "fmt": "json3"},
        headers=headers,
        timeout=15,
    )

    if not cap_resp.ok:
        raise ValueError(f"Timedtext fetch failed: HTTP {cap_resp.status_code}")

    cap_data = cap_resp.json()
    segments = []
    for event in cap_data.get("events", []):
        if "segs" not in event:
            continue
        start = event.get("tStartMs", 0) / 1000
        duration = event.get("dDurationMs", 0) / 1000
        text = "".join(
            seg.get("utf8", "") for seg in event["segs"]
        ).strip()
        if not text or text == "\n":
            continue
        segments.append({
            "start": start,
            "end": start + duration,
            "text": text,
        })

    if not segments:
        raise ValueError("No usable transcript text from timedtext endpoint.")

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
        raise TranscriptNotAvailable(
            "No transcript is available for this YouTube video. "
            "The video may not have captions enabled."
        ) from err
    except Exception as err:
        print(f"youtube-transcript-api failed ({type(err).__name__}): {err}")
        raise

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
    # Validate URL first — raises TranscriptNotAvailable (→ 400) on bad input
    _extract_video_id(url)

    # Provider 1: FreeTranscriptAPI
    try:
        return _via_freetranscript(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"FreeTranscriptAPI network error, trying Supadata: {err}")
    except TranscriptNotAvailable:
        raise
    except ValueError as err:
        print(f"FreeTranscriptAPI error, trying Supadata: {err}")

    # Provider 2: Supadata (requires SUPADATA_API_KEY env var)
    try:
        return _via_supadata(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"Supadata network error, trying timedtext: {err}")
    except TranscriptNotAvailable:
        raise
    except ValueError as err:
        print(f"Supadata error, trying timedtext: {err}")

    # Provider 3: YouTube timedtext endpoint (no auth, different path from scraping)
    try:
        return _via_timedtext(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"Timedtext network error, trying youtube-transcript-api: {err}")
    except TranscriptNotAvailable:
        raise
    except ValueError as err:
        print(f"Timedtext error, trying youtube-transcript-api: {err}")

    # Provider 4: youtube-transcript-api (last resort; blocked on most cloud IPs)
    try:
        return _via_ytapi(url)
    except TranscriptNotAvailable:
        raise
    except Exception as err:
        print(f"All providers exhausted. Last error ({type(err).__name__}): {err}")
        raise TranscriptProviderError(
            "All transcript providers are currently unavailable. Please try again later."
        ) from err
