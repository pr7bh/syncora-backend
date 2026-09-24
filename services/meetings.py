from bson import ObjectId
from datetime import datetime
from database import meetings_collection


async def save_meeting(
    user_id: str,
    filename: str,
    source: str = None,
    transcript: str = None,
    timeline: list = None,
    summary: str = None,
    chat_history: list = None,
    title: str = None
):
    meeting = {
        "user_id": ObjectId(user_id),
        "filename": filename,
        "source": source,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "transcript": transcript,
        "timeline": timeline,
        "summary": summary,
        "chat_history": chat_history or []
    }

    result = await meetings_collection.insert_one(meeting)

    meeting["id"] = str(result.inserted_id)

    return meeting


async def update_chat_history(
    meeting_id: str,
    user_id: str,
    chat_history: list
):
    try:
        meeting_object_id = ObjectId(meeting_id)
        user_object_id = ObjectId(user_id)
    except Exception:
        return None

    result = await meetings_collection.update_one(
        {
            "_id": meeting_object_id,
            "user_id": user_object_id
        },
        {
            "$set": {
                "chat_history": chat_history
            }
        }
    )

    if result.matched_count == 0:
        return None

    return await get_meeting(
        meeting_id,
        user_id
    )


async def get_meetings(user_id: str):

    try:
        user_object_id = ObjectId(user_id)
    except Exception:
        return []

    cursor = (
        meetings_collection
        .find({
            "user_id": user_object_id
        })
        .sort("_id", -1)
    )

    meetings = await cursor.to_list(length=None)

    formatted_meetings = []

    for meeting in meetings:

        formatted_meetings.append({
            "id": str(meeting["_id"]),
            "user_id": str(meeting["user_id"]),
            "filename": meeting.get("filename"),
            "source": meeting.get("source"),
            "title": meeting.get("title"),
            "created_at": meeting.get("created_at"),
            "transcript": meeting.get("transcript"),
            "timeline": meeting.get("timeline"),
            "summary": meeting.get("summary"),
            "chat_history": meeting.get("chat_history", [])
        })

    return formatted_meetings


async def get_meeting(
    meeting_id: str,
    user_id: str
):

    try:
        meeting_object_id = ObjectId(meeting_id)
        user_object_id = ObjectId(user_id)
    except Exception:
        return None

    meeting = await meetings_collection.find_one({
        "_id": meeting_object_id,
        "user_id": user_object_id
    })

    if not meeting:
        return None

    return {
        "id": str(meeting["_id"]),
        "user_id": str(meeting["user_id"]),
        "filename": meeting.get("filename"),
        "source": meeting.get("source"),
        "title": meeting.get("title"),
        "created_at": meeting.get("created_at"),
        "transcript": meeting.get("transcript"),
        "timeline": meeting.get("timeline"),
        "summary": meeting.get("summary"),
        "chat_history": meeting.get("chat_history", [])
    }


async def delete_meeting_by_id(meeting_id: str, user_id: str):
    try:
        result = await meetings_collection.delete_one({
            "_id": ObjectId(meeting_id),
            "user_id": ObjectId(user_id)
        })

        return result.deleted_count > 0

    except Exception:
        return False