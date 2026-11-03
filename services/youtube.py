
import re
import requests

FREETRANSCRIPT_URL = "https://api.freetranscriptapi.com/v1/transcript"
INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player"

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"
)

_INNERTUBE_PAYLOAD = {
    "context": {
        "client": {
            "clientName": "ANDROID",
            "clientVersion": "19.09.37",
            "androidSdkVersion": 30,
            "userAgent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11)",
            "hl": "en",
            "gl": "US",
        }
    }
}

_INNERTUBE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11)",
    "X-YouTube-Client-Name": "3",
    "X-YouTube-Client-Version": "19.09.37",
}


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


def _via_innertube(url: str) -> dict:
    video_id = _extract_video_id(url)

    payload = {**_INNERTUBE_PAYLOAD, "videoId": video_id}
    resp = requests.post(
        INNERTUBE_URL,
        json=payload,
        headers=_INNERTUBE_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    caption_tracks = (
        data.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    )

    if not caption_tracks:
        raise ValueError(
            "No captions are available for this video. "
            "The video may not have captions enabled."
        )

    # Prefer English; fall back to first available track
    track_url = None
    for track in caption_tracks:
        if track.get("languageCode", "").startswith("en"):
            track_url = track["baseUrl"]
            break
    if not track_url:
        track_url = caption_tracks[0]["baseUrl"]

    cap_resp = requests.get(track_url + "&fmt=json3", timeout=30)
    cap_resp.raise_for_status()
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
        raise ValueError("The YouTube transcript contains no usable text.")

    return {
        "text": " ".join(s["text"] for s in segments),
        "segments": segments,
    }


def get_youtube_transcript(url: str) -> dict:
    try:
        return _via_freetranscript(url)
    except (requests.Timeout, requests.RequestException) as err:
        print(f"FreeTranscriptAPI network error, trying Innertube: {err}")
    except ValueError as err:
        print(f"FreeTranscriptAPI error, trying Innertube: {err}")

    try:
        return _via_innertube(url)
    except ValueError:
        raise
    except Exception as err:
        print(f"Innertube fallback failed ({type(err).__name__}): {err}")
        raise ValueError(
            "Could not retrieve the YouTube transcript. "
            "The video may not have captions, or the URL is invalid."
        ) from err
