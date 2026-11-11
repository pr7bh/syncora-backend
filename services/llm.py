import os

from dotenv import load_dotenv
from google import genai
from groq import Groq

load_dotenv()


# ============================================================
# Gemini
# ============================================================

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options={"timeout": 10},
)

GEMINI_MODEL = "gemini-3.8-flash"

# ============================================================
# Groq fallback (native SDK — no langchain dependency)
# ============================================================

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Try models in order; first one that works is used.
# llama-3.3-70b-versatile removed — confirmed not found on this account.
GROQ_MODELS = [
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
# Generate Summary + Title in a single LLM call
# ============================================================

def generate_summary_and_title(segments: list, transcript: str) -> tuple[str, str]:
    """Returns (summary, title) using one LLM call instead of two."""

    timestamped_transcript = "\n".join(
        f"[{format_time(segment['start'])} - "
        f"{format_time(segment['end'])}] "
        f"{segment['text']}"
        for segment in segments
    )

    prompt = f"""
You are an AI meeting assistant.

The transcript may be in any language (English, Hindi, Hinglish, Punjabi,
Spanish, French, or mixed). Understand it and ALWAYS respond in ENGLISH.

Timestamped Transcript:

{timestamped_transcript}

---

Respond with EXACTLY this structure — no extra text before or after:

TITLE: <2 to 5 English words capturing the main topic — no quotes, no punctuation unless necessary>

1. Short Summary
   Concise summary of the entire meeting/video in English.

2. Main Topics Discussed
   List important topics with timeframes.

3. Important Conclusions
   List conclusions with timeframes.

4. Action Items
   List action items with timeframes, or state that none were identified.

5. Decisions Made
   List decisions with timeframes, or state that none were identified.

Rules:
- Use ONLY timestamps that appear in the transcript.
- Do NOT invent information.
- Keep it concise and easy to read.
"""

    response = generate_response(prompt)

    # Split title from summary body
    lines = response.strip().splitlines()
    title = "Meeting Summary"
    summary_lines = lines

    if lines and lines[0].upper().startswith("TITLE:"):
        raw_title = lines[0][6:].strip()
        if raw_title:
            title = raw_title
        summary_lines = lines[1:]

    summary = "\n".join(summary_lines).strip()
    return summary, title


# Keep these wrappers so existing call sites still work
def generate_summary(segments: list) -> str:
    summary, _ = generate_summary_and_title(segments, "")
    return summary


def generate_meeting_title(transcript: str) -> str:
    # Thin wrapper — only called standalone if needed elsewhere
    prompt = f"""
Generate a 2-to-5-word English title for this transcript. Return ONLY the title.

{transcript[:5000]}
"""
    return generate_response(prompt).strip()