from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.chat import ask_question
from services.meetings import (
    get_meeting,
    update_chat_history
)
from services.dependencies import get_current_user


router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    meeting_id: str
    question: str


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user=Depends(get_current_user)
):

    user_id = str(current_user["_id"])

    # Check that the meeting belongs to the logged-in user
    meeting = await get_meeting(
        request.meeting_id,
        user_id
    )

    if not meeting:
        return {
            "error": "Meeting not found"
        }

    # Generate answer
    answer = ask_question(
        request.meeting_id,
        request.question
    )

    # Existing conversation
    chat_history = meeting.get(
        "chat_history",
        []
    )

    # User message
    chat_history.append({
        "role": "user",
        "content": request.question
    })

    # AI message
    chat_history.append({
        "role": "assistant",
        "content": answer
    })

    # Save conversation
    await update_chat_history(
        request.meeting_id,
        user_id,
        chat_history
    )

    return {
        "question": request.question,
        "answer": answer
    }