import os

import platform

if platform.system() == "Windows":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg")

    os.environ["PATH"] = (
        FFMPEG_DIR + os.pathsep + os.environ["PATH"]
    )

import whisper


print("Loading Whisper model...")

model = whisper.load_model("base")

print("Whisper model loaded.")


def transcribe_audio(file_path: str):
    result = model.transcribe(file_path)

    segments = []

    for segment in result["segments"]:
        segments.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip()
        })

    return {
        "text": result["text"].strip(),
        "segments": segments
    }