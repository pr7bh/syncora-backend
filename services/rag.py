import os
import chromadb

from dotenv import load_dotenv
from google import genai

load_dotenv()


# Gemini client for embeddings
gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


# ChromaDB
chroma_client = chromadb.PersistentClient(
    path="./chroma_db"
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