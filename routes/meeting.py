import os
import uuid

from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Depends
)
from pydantic import BaseModel

from services.transcriber import transcribe_audio
from services.youtube import (
    get_youtube_transcript,
    TranscriptNotAvailable,
    TranscriptProviderError,
)
from services.llm import generate_summary_and_title
from services.rag import store_transcript, delete_meeting_chunks

from services.meetings import (
    delete_meeting_by_id,
    save_meeting,
    get_meetings,
    get_meeting
)

from services.dependencies import get_current_user


router = APIRouter(prefix="/api")


class YouTubeRequest(BaseModel):
    url: str


ALLOWED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv"
}

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


# =========================
# Get Recent Meetings
# =========================

@router.get("/meetings")
async def get_recent_meetings(
    current_user=Depends(get_current_user)
):

    user_id = str(current_user["_id"])

    return await get_meetings(
        user_id
    )


# =========================
# YouTube Meeting
# =========================

@router.post("/youtube")
async def summarize_youtube(
    request: YouTubeRequest,
    current_user=Depends(get_current_user)
):

    user_id = str(current_user["_id"])

    try:
        transcription = get_youtube_transcript(request.url)
    except TranscriptNotAvailable as error:
        raise HTTPException(status_code=400, detail=str(error))
    except TranscriptProviderError as error:
        raise HTTPException(status_code=502, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while retrieving the transcript."
        )

    transcript = transcription["text"]
    timeline = transcription["segments"]

    # Generate summary and title in a single LLM call
    summary, title = generate_summary_and_title(timeline, transcript)

    meeting = await save_meeting(
        user_id=user_id,
        filename="youtube",
        source=request.url,
        transcript=transcript,
        timeline=timeline,
        summary=summary,
        title=title
    )

    store_transcript(
        meeting["id"],
        timeline
    )

    return {
        "meeting_id": meeting["id"],
        "filename": "youtube",
        "source": request.url,
        "transcript": transcript,
        "timeline": timeline,
        "summary": summary,
        "title": title
    }
# =========================
# Upload / Transcribe
# =========================

@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user)
):

    user_id = str(current_user["_id"])
    original_filename = file.filename

    extension = os.path.splitext(
        original_filename
    )[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return {
            "error": "Unsupported file format"
        }

    os.makedirs("uploads", exist_ok=True)

    file_path = os.path.join(
        "uploads",
        f"{uuid.uuid4()}{extension}"
    )

    # Stream to disk; reject before fully writing if too large
    written = 0
    try:
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_MB} MB"
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    try:
        transcription = transcribe_audio(file_path)

        transcript = transcription["text"]
        timeline = transcription["segments"]

        summary, title = generate_summary_and_title(timeline, transcript)

        meeting = await save_meeting(
            user_id=user_id,
            filename=original_filename,
            transcript=transcript,
            timeline=timeline,
            summary=summary,
            title=title
        )

        store_transcript(meeting["id"], timeline)

        return {
            "meeting_id": meeting["id"],
            "filename": original_filename,
            "transcript": transcript,
            "timeline": timeline,
            "summary": summary,
            "title": title
        }
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# =========================
# Get Single Meeting
# =========================

@router.get("/meetings/{meeting_id}")
async def get_single_meeting(
    meeting_id: str,
    current_user=Depends(get_current_user)
):

    user_id = str(
        current_user["_id"]
    )

    meeting = await get_meeting(
        meeting_id,
        user_id
    )

    if not meeting:
        return {
            "error": "Meeting not found"
        }

    return meeting

@router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    current_user=Depends(get_current_user)
):
    user_id = str(current_user["_id"])

    deleted = await delete_meeting_by_id(
        meeting_id,
        user_id
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Meeting not found"
        )

    try:
        delete_meeting_chunks(meeting_id)
    except Exception as exc:
        print(f"Warning: ChromaDB cleanup failed for meeting {meeting_id}: {exc}")

    return {
        "message": "Meeting deleted successfully"
    }