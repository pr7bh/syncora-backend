from youtube_transcript_api import YouTubeTranscriptApi


def get_video_id(url: str) -> str:

    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]

    if "youtube.com/watch" in url:
        return url.split("v=")[1].split("&")[0]

    if "youtube.com/shorts/" in url:
        return url.split("youtube.com/shorts/")[1].split("?")[0]

    raise ValueError("Invalid YouTube URL")


def get_youtube_transcript(url: str):

    video_id = get_video_id(url)

    api = YouTubeTranscriptApi()

    transcript = api.fetch(video_id)

    segments = []

    for item in transcript:

        start = float(item.start)
        duration = float(item.duration)

        segments.append({
            "start": start,
            "end": start + duration,
            "text": item.text.strip()
        })

    text = " ".join(
        segment["text"]
        for segment in segments
    )

    return {
        "text": text,
        "segments": segments
    }