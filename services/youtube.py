import os
import yt_dlp


def download_youtube_audio(url: str):

    output_dir = "uploads"
    os.makedirs(output_dir, exist_ok=True)

    output_template = os.path.join(
        output_dir,
        "%(id)s.%(ext)s"
    )

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    return filename