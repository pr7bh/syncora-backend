import asyncio
import os
import secrets

from fastapi import APIRouter, Header, HTTPException

from database import meetings_collection
from services.rag import is_meeting_complete, patch_missing_chunks

router = APIRouter(prefix="/api/admin", tags=["Admin"])

BATCH_SIZE = 20
RATE_LIMIT_DELAY = 5


def _is_rate_limit_error(error: Exception) -> bool:
    msg = str(error)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


@router.post("/reembed")
async def reembed_meetings(
    x_admin_key: str = Header(default=None)
):
    admin_secret = os.getenv("ADMIN_SECRET")

    if not admin_secret:
        raise HTTPException(
            status_code=503,
            detail="Admin endpoint not configured"
        )

    if not x_admin_key or not secrets.compare_digest(
        x_admin_key.encode(),
        admin_secret.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

    processed = 0
    skipped_no_timeline = 0
    skipped_already_embedded = 0
    failed = 0
    errors = []
    repaired = []

    last_id = None

    while True:
        query = {"_id": {"$gt": last_id}} if last_id else {}

        cursor = (
            meetings_collection
            .find(query, {"_id": 1, "timeline": 1})
            .sort("_id", 1)
            .limit(BATCH_SIZE)
        )

        batch = await cursor.to_list(length=BATCH_SIZE)

        if not batch:
            break

        for meeting in batch:
            meeting_id = str(meeting["_id"])
            timeline = meeting.get("timeline")

            if not timeline:
                skipped_no_timeline += 1
                continue

            if is_meeting_complete(meeting_id, timeline):
                skipped_already_embedded += 1
                continue

            for attempt in range(2):
                try:
                    counts = patch_missing_chunks(meeting_id, timeline)
                    processed += 1
                    repaired.append({
                        "meeting_id": meeting_id,
                        "expected": counts["expected"],
                        "existing_before_repair": counts["existing_before"]
                    })
                    break
                except Exception as exc:
                    if attempt == 0 and _is_rate_limit_error(exc):
                        await asyncio.sleep(RATE_LIMIT_DELAY)
                        continue
                    failed += 1
                    errors.append({
                        "meeting_id": meeting_id,
                        "error": "Embedding failed"
                    })
                    break

        last_id = batch[-1]["_id"]

        if len(batch) < BATCH_SIZE:
            break

    return {
        "processed": processed,
        "skipped_no_timeline": skipped_no_timeline,
        "skipped_already_embedded": skipped_already_embedded,
        "failed": failed,
        "repaired": repaired,
        "errors": errors
    }
