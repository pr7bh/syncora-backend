import os
import chromadb

from dotenv import load_dotenv
from google import genai

load_dotenv()


# Gemini client for embeddings
gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


# ChromaDB – path is configurable; on ephemeral hosts (Render free tier, etc.)
# set CHROMA_PATH to a persistent-disk mount path so embeddings survive restarts.
chroma_client = chromadb.PersistentClient(
    path=os.getenv("CHROMA_PATH", "./chroma_db")
)

collection = chroma_client.get_or_create_collection(
    name="meeting_transcripts"
)



def create_embedding(text: str):

    response = gemini_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text
    )

    return response.embeddings[0].values


def is_meeting_complete(meeting_id: str, segments: list) -> bool:
    if not segments:
        return True
    meeting_id = str(meeting_id)
    expected = {f"{meeting_id}_{i}" for i in range(len(segments))}
    result = collection.get(
        where={"meeting_id": meeting_id},
        include=[]
    )
    return set(result["ids"]) == expected


def patch_missing_chunks(meeting_id: str, segments: list) -> dict:
    meeting_id = str(meeting_id)
    result = collection.get(
        where={"meeting_id": meeting_id},
        include=[]
    )
    existing_ids = set(result["ids"])
    existing_before = len(existing_ids)

    for index, segment in enumerate(segments):
        chunk_id = f"{meeting_id}_{index}"
        if chunk_id in existing_ids:
            continue
        embedding = create_embedding(segment["text"])
        collection.add(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[segment["text"]],
            metadatas=[{
                "meeting_id": meeting_id,
                "start": segment["start"],
                "end": segment["end"]
            }]
        )

    return {
        "expected": len(segments),
        "existing_before": existing_before
    }


def delete_meeting_chunks(meeting_id):
    collection.delete(
        where={"meeting_id": str(meeting_id)}
    )


def store_transcript(meeting_id, segments):

    meeting_id = str(meeting_id)

    # Remove only chunks belonging to this meeting
    collection.delete(
        where={"meeting_id": meeting_id}
    )

    for index, segment in enumerate(segments):

        text = segment["text"]

        embedding = create_embedding(text)

        collection.add(
            ids=[f"{meeting_id}_{index}"],
            embeddings=[embedding],
            documents=[text],
            metadatas=[
                {
                    "meeting_id": meeting_id,
                    "start": segment["start"],
                    "end": segment["end"]
                }
            ]
        )


def search_transcript(
    meeting_id,
    question,
    n_results=10
):

    meeting_id = str(meeting_id)

    question_embedding = create_embedding(question)

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=n_results,
        where={
            "meeting_id": meeting_id
        }
    )

    chunks = []

    if not results["documents"]:
        return chunks

    for i in range(
        len(results["documents"][0])
    ):

        chunks.append({
            "text": results["documents"][0][i],
            "start": results["metadatas"][0][i]["start"],
            "end": results["metadatas"][0][i]["end"]
        })

    return chunks