import os

from dotenv import load_dotenv
from google import genai
from groq import Groq

load_dotenv()


# ============================================================
# Gemini
# ============================================================

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

GEMINI_MODEL = "gemini-3.8-flash"

# ============================================================
# Groq fallback (native SDK — no langchain dependency)
# ============================================================

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Try models in order; first one that works is used.
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]


def _groq_generate(prompt: str) -> str:
    last_err: Exception = RuntimeError("No Groq models available.")
    for model in GROQ_MODELS:
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return response.choices[0].message.content
        except Exception as err:
            print(f"Groq {model} failed: {err}")
            last_err = err
    raise last_err


# ============================================================
# Generate LLM Response
# ============================================================

def generate_response(prompt: str) -> str:

    try:

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        return response.text

    except Exception as gemini_error:

        # Always fall back to Groq on any Gemini failure.
        print(f"Gemini failed, falling back to Groq: {gemini_error}")

        try:
            return _groq_generate(prompt)
        except Exception as groq_error:
            print(f"All Groq models also failed: {groq_error}")
            raise gemini_error


# ============================================================
# Format Timestamp
# ============================================================

def format_time(seconds: float):

    minutes = int(seconds // 60)
    seconds = int(seconds % 60)

    return f"{minutes:02d}:{seconds:02d}"


# ============================================================
# Generate Meeting Summary
# ============================================================

def generate_summary(segments):

    timestamped_transcript = "\n".join(
        f"[{format_time(segment['start'])} - "
        f"{format_time(segment['end'])}] "
        f"{segment['text']}"
        for segment in segments
    )

    prompt = f"""
You are an AI meeting assistant.

Analyze the following timestamped transcript.

The transcript may be written in any language, including:
- English
- Hindi
- Hinglish
- Punjabi
- Spanish
- French
- or a mixture of multiple languages.

Your job is to understand the transcript regardless of its language
and ALWAYS generate the final summary in ENGLISH.

Timestamped Transcript:

{timestamped_transcript}


Provide the following:

1. Short Summary
   - Give a concise summary of the entire meeting/video.
   - ALWAYS write it in English.

2. Main Topics Discussed
   - List the important topics discussed.
   - ALWAYS write them in English.
   - Include the timeframe where each topic was discussed.

3. Important Conclusions
   - List the important conclusions.
   - ALWAYS write them in English.
   - Include the timeframe.

4. Action Items
   - List tasks or actions mentioned in the transcript.
   - ALWAYS write them in English.
   - Include the timeframe.

5. Decisions Made
   - List important decisions made during the meeting.
   - ALWAYS write them in English.
   - Include the timeframe.


Important Rules:

- ALWAYS respond in English.
- Understand the original language before generating the summary.
- Do NOT simply summarize based on individual words.
- Preserve the actual meaning and context of the conversation.
- Do NOT invent information.
- Do NOT invent timestamps.
- Use ONLY timestamps provided in the transcript.
- If the transcript contains multiple languages, understand all languages
  and provide one combined summary in English.
- If there are no clear action items, say that no specific action items
  were identified.
- If there are no clear decisions, say that no specific decisions
  were identified.
- Keep the summary concise and easy to read.
- Do not translate the entire transcript unless necessary for
  understanding the content.


Return the final response in English.

"""

    return generate_response(prompt)


# ============================================================
# Generate Meeting Title
# ============================================================

def generate_meeting_title(transcript: str):

    prompt = f"""
You are an AI meeting assistant.

Generate a short and meaningful title for the following meeting
or video transcript.

The transcript may be in:
- English
- Hindi
- Hinglish
- Punjabi
- or any other language.

Understand the transcript and ALWAYS generate the title in ENGLISH.

Rules:

- Keep the title between 2 and 5 words.
- Capture the main topic of the meeting/video.
- Use meaningful English words.
- Do not use generic titles such as:
  "Meeting Summary"
  "Meeting Transcript"
  "Video Summary"
- Do not include quotes.
- Do not include punctuation unless necessary.
- Return ONLY the title.
- Do not provide any explanation.

Transcript:

{transcript[:10000]}
"""

    return generate_response(prompt).strip()