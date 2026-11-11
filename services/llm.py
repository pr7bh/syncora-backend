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
    http_options={"timeout": 20},
)

GEMINI_MODEL = "gemini-3.8-flash"

# ============================================================
# Groq fallback (native SDK — no langchain dependency)
# ============================================================

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Dynamically discovered at first use — never needs manual updates when
# Groq deprecates models.
_groq_model_cache: list[str] | None = None

_SKIP_GROQ_KEYWORDS = ("whisper", "distil-whisper", "tts", "guard", "vision")


def _discover_groq_models() -> list[str]:
    """Query Groq /models and return active chat-completion model IDs."""
    try:
        resp = groq_client.models.list()
        models = [
            m.id for m in resp.data
            if getattr(m, "active", True)
            and not any(kw in m.id.lower() for kw in _SKIP_GROQ_KEYWORDS)
        ]
        # Prefer larger models first (rough heuristic on name)
        def _size_rank(mid: str) -> int:
            for tag in ("405b", "90b", "72b", "70b", "32b", "13b", "9b", "8b", "7b"):
                if tag in mid:
                    return int(tag.rstrip("b"))
            return 0
        models.sort(key=_size_rank, reverse=True)
        print(f"Groq available models: {models}")
        return models
    except Exception as exc:
        print(f"Groq model discovery failed: {exc}")
        return []


def _get_groq_models() -> list[str]:
    global _groq_model_cache
    if _groq_model_cache is None:
        _groq_model_cache = _discover_groq_models()
    return _groq_model_cache


def _groq_generate(prompt: str) -> str:
    global _groq_model_cache
    models = _get_groq_models()
    if not models:
        raise RuntimeError("No Groq models discovered.")

    last_err: Exception = RuntimeError("All Groq models failed.")
    working: list[str] = []
    for model in models:
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            working.append(model)
            # Narrow the cache to models that actually work
            if working != models:
                _groq_model_cache = working + [
                    m for m in models if m not in working
                ]
            return response.choices[0].message.content
        except Exception as err:
            print(f"Groq {model} failed: {err}")
            last_err = err

    # All models failed — reset cache so next request re-discovers
    _groq_model_cache = None
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