import os

from dotenv import load_dotenv
from google import genai
from langchain_groq import ChatGroq

load_dotenv()


# Gemini
gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


# Groq fallback
groq_client = ChatGroq(
    model="openai/gpt-oss-20b",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2
)


def generate_response(prompt: str) -> str:

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        return response.text

    except Exception as error:

        error_message = str(error)

        # Gemini rate limit / temporary unavailable
        if (
            "429" in error_message
            or "RESOURCE_EXHAUSTED" in error_message
            or "503" in error_message
            or "UNAVAILABLE" in error_message
        ):
            response = groq_client.invoke(prompt)

            return response.content

        raise


def format_time(seconds: float):

    minutes = int(seconds // 60)
    seconds = int(seconds % 60)

    return f"{minutes:02d}:{seconds:02d}"


def generate_summary(segments):

    timestamped_transcript = "\n".join(
        f"[{format_time(segment['start'])} - "
        f"{format_time(segment['end'])}] "
        f"{segment['text']}"
        for segment in segments
    )

    prompt = f"""
        You are an AI meeting assistant.

        Analyze the following timestamped transcript:

        {timestamped_transcript}

        Provide:

        1. A short summary
        2. Main topics discussed
        3. Important conclusions
        4. Action items
        5. Decisions made

        For each topic, conclusion, action item, or decision,
        include the timeframe where it was discussed.

        Important:
        - Use only the timestamps provided.
        - Do not invent timestamps.
        - Do not invent information.
        - Keep the response concise.
        """

    return generate_response(prompt)


def generate_meeting_title(transcript: str):

    prompt = f"""
        Generate a short, meaningful title for this meeting transcript.

        Rules:
        - Keep it between 2 and 5 words.
        - Capture the main topic being discussed.
        - Do not use generic titles like "Meeting Summary".
        - Do not include quotes.
        - Return ONLY the title.

        Transcript:
        {transcript[:10000]}
        """

    return generate_response(prompt).strip()