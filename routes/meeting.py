import os
import shutil

from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Depends
)
from pydantic import BaseModel

from services.transcriber import transcribe_audio
from services.youtube import download_youtube_audio
from services.llm import (
    generate_summary,
    generate_meeting_title
)
from services.rag import store_transcript

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

    file_path = download_youtube_audio(
        request.url
    )

    transcription = transcribe_audio(
        file_path
    )

    transcript = transcription["text"]
    timeline = transcription["segments"]

    summary = generate_summary(
        timeline
    )

    title = generate_meeting_title(
        transcript
    )

    # Save meeting
    meeting = await save_meeting(
        user_id=user_id,
        filename=os.path.basename(file_path),
        source=request.url,
        transcript=transcript,
        timeline=timeline,
        summary=summary,
        title=title
    )

    # Store transcript in RAG
    store_transcript(
        meeting["id"],
        timeline
    )

    return {
        "meeting_id": meeting["id"],
        "filename": os.path.basename(file_path),
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

    extension = os.path.splitext(
        file.filename
    )[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return {
            "error": "Unsupported file format"
        }

    os.makedirs(
        "uploads",
        exist_ok=True
    )

    file_path = os.path.join(
        "uploads",
        file.filename
    )

    with open(
        file_path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    transcription = transcribe_audio(
        file_path
    )

    transcript = transcription["text"]
    timeline = transcription["segments"]

    summary = generate_summary(
        timeline
    )

    title = generate_meeting_title(
        transcript
    )

    # Save meeting
    meeting = await save_meeting(
        user_id=user_id,
        filename=file.filename,
        transcript=transcript,
        timeline=timeline,
        summary=summary,
        title=title
    )

    # Store transcript in RAG
    store_transcript(
        meeting["id"],
        timeline
    )

    return {
        "meeting_id": meeting["id"],
        "filename": file.filename,
        "transcript": transcript,
        "timeline": timeline,
        "summary": summary,
        "title": title
    }


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

    return {
        "message": "Meeting deleted successfully"
    }