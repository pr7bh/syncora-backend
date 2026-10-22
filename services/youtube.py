
import requests

API_URL = "https://api.freetranscriptapi.com/v1/transcript"


def get_youtube_transcript(url: str):
    try:
        response = requests.get(
            API_URL,
            params={
                "video_url": url,
            },
            timeout=60,
        )

        if not response.ok:
            try:
                error_data = response.json()
                error_details = error_data.get("error", {})

                if isinstance(error_details, dict):
                    error_message = error_details.get(
                        "message",
                        str(error_details),
                    )
                else:
                    error_message = str(error_details)

            except ValueError:
                error_message = response.text

            print(
                f"FreeTranscriptAPI failed: "
                f"HTTP {response.status_code} - {error_message}"
            )

            raise ValueError(
                f"YouTube transcript retrieval failed: {error_message}"
            )

        data = response.json()

        transcript_data = data.get("transcript", [])

        if not transcript_data:
            raise ValueError(
                "No transcript is available for this YouTube video."
            )

        segments = []

        for item in transcript_data:
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
            raise ValueError(
                "The YouTube transcript contains no usable text."
            )

        full_text = " ".join(
            segment["text"] for segment in segments
        )

        return {
            "text": full_text,
            "segments": segments,
        }

    except requests.Timeout as error:
        raise ValueError(
            "YouTube transcript request timed out. Please try again."
        ) from error

    except requests.RequestException as error:
        raise ValueError(
            "Could not connect to the transcript service. "
            "Please try again later."
        ) from error
