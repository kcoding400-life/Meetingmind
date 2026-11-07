"""
AI Intelligence Engine — the core of MeetingMind.

Two AI systems, two jobs:

  1. GROQ WHISPER  → transcription
     - Runs Whisper-large-v3 on Groq's LPU hardware (~200x realtime)
     - REST API: POST audio bytes → get transcript text
     - Detects language automatically

  2. GEMINI 2.5 FLASH  → structured analysis
     - 1M token context window — no chunking needed even for long meetings
     - Prompt engineering produces a strict JSON schema output
     - Pydantic validates the response before it touches the database
     - Fallback: if JSON parsing fails, we retry with an explicit repair prompt

Design principles:
  - Pure functions: audio bytes in → structured data out
  - No side effects: DB writes happen in processor.py, not here
  - Explicit error handling: every external call has a specific except clause
  - Token optimisation: we trim transcript to 800k chars max (~200k tokens)
    to stay well inside Gemini's context window with headroom for the prompt
"""

import json
import logging
import time
from typing import Optional
import groq
import google.generativeai as genai
from pydantic import BaseModel, Field

from .config import settings

logger = logging.getLogger(__name__)


# Pydantic models for structured AI output


class ActionItem(BaseModel):
    task: str = Field(description="The specific task to be completed")
    owner: str = Field(description="Person responsible (or 'Unassigned')")
    deadline: str = Field(description="Deadline if mentioned, else 'Not specified'")
    priority: str = Field(description="High | Medium | Low")


class Decision(BaseModel):
    decision: str = Field(description="The decision that was made")
    rationale: str = Field(description="Why this decision was made")
    made_by: str = Field(description="Who made or approved the decision")


class Risk(BaseModel):
    risk: str = Field(description="The identified risk or concern")
    impact: str = Field(description="High | Medium | Low")
    mitigation: str = Field(description="Suggested mitigation or 'None discussed'")


class MeetingAnalysis(BaseModel):
    """
    Structured output from Gemini analysis.
    Every field is optional to handle partial results gracefully.
    """
    executive_summary: str = Field(
        description="3-5 sentence executive summary of the entire meeting"
    )
    key_topics: list[str] = Field(
        default_factory=list,
        description="Main topics discussed, in order"
    )
    action_items: list[ActionItem] = Field(
        default_factory=list,
        description="All action items with owner and deadline"
    )
    decisions: list[Decision] = Field(
        default_factory=list,
        description="All decisions made during the meeting"
    )
    risks: list[Risk] = Field(
        default_factory=list,
        description="Risks, blockers, or concerns raised"
    )
    participants: list[str] = Field(
        default_factory=list,
        description="Names of participants mentioned in the transcript"
    )
    follow_up_email: str = Field(
        description="Professional follow-up email ready to send, with subject line"
    )
    sentiment: str = Field(
        default="Neutral",
        description="Overall meeting sentiment: Positive | Neutral | Negative | Mixed"
    )
    meeting_type: str = Field(
        default="General",
        description="Type: Standup | Planning | Retrospective | Review | Sales | General"
    )



# Groq Whisper — Transcription


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.mp3") -> dict:
    """
    Transcribe audio using Groq's Whisper-large-v3.

    Returns:
        {
            "text": str,          — full transcript
            "language": str,      — detected language code (e.g. "en")
            "duration": float,    — audio duration in seconds
        }

    Raises:
        RuntimeError: if transcription fails after retries
        ValueError: if GROQ_API_KEY is not configured
    """
    if not settings.GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. Get your key at https://console.groq.com/keys"
        )

    client = groq.Groq(api_key=settings.GROQ_API_KEY)

    # Groq Whisper accepts: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
    # Max file size: 25MB. For larger files we'd chunk — out of scope here.
    MAX_GROQ_SIZE = 25 * 1024 * 1024
    if len(audio_bytes) > MAX_GROQ_SIZE:
        logger.warning(
            f"Audio file ({len(audio_bytes) / 1024 / 1024:.1f}MB) exceeds Groq's 25MB limit. "
            "Truncating to first 25MB — transcription may be incomplete."
        )
        audio_bytes = audio_bytes[:MAX_GROQ_SIZE]

    logger.info(f"Transcribing {len(audio_bytes) / 1024:.1f}KB of audio via Groq Whisper")
    start = time.time()

    try:
        transcription = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=settings.GROQ_WHISPER_MODEL,
            response_format="verbose_json",   # includes language + segments
            temperature=0.0,                  # deterministic output
        )
    except groq.RateLimitError:
        raise RuntimeError(
            "Groq rate limit reached. Please wait a moment and try again."
        )
    except groq.APIConnectionError as e:
        raise RuntimeError(f"Could not connect to Groq API: {e}")
    except groq.APIStatusError as e:
        raise RuntimeError(f"Groq API error {e.status_code}: {e.message}")

    elapsed = time.time() - start
    transcript_text = transcription.text.strip()

    logger.info(
        f"Transcription complete in {elapsed:.1f}s — "
        f"{len(transcript_text)} chars, language={getattr(transcription, 'language', 'unknown')}"
    )

    return {
        "text": transcript_text,
        "language": getattr(transcription, "language", "en"),
        "duration": getattr(transcription, "duration", None),
    }



# Gemini — Meeting Analysis


# Embed the JSON schema in the prompt so Gemini knows exactly what to produce.
# We generate it from the Pydantic model to keep schema + model in sync.
_ANALYSIS_SCHEMA = json.dumps(MeetingAnalysis.model_json_schema(), indent=2)

_ANALYSIS_PROMPT_TEMPLATE = """You are an expert meeting analyst. Analyse the following meeting transcript and extract structured information.

TRANSCRIPT:
{transcript}

Respond ONLY with a valid JSON object matching this exact schema. Do not include any text before or after the JSON.

SCHEMA:
{schema}

RULES:
- executive_summary: 3-5 sentences covering what was discussed and decided
- action_items: every commitment made by any person, however small
- decisions: only firm decisions, not options being discussed
- risks: blockers, concerns, or risks explicitly raised
- participants: names mentioned as speaking or being assigned tasks
- follow_up_email: start with "Subject: ..." then a blank line, then the email body. Sign it "MeetingMind AI"
- sentiment: judge the overall tone of the meeting
- meeting_type: pick the best fit from the allowed values
- If a field has no data, use an empty list [] or appropriate default string
- All text must be in the same language as the transcript"""

_REPAIR_PROMPT = """The previous response was not valid JSON. 
Please return ONLY the corrected JSON object with no other text, markdown, or explanation.
Schema: {schema}
Previous response to fix: {bad_response}"""


def analyse_transcript(transcript: str) -> MeetingAnalysis:
    """
    Send transcript to Gemini 2.5 Flash and return structured MeetingAnalysis.

    Strategy:
      1. Build prompt with transcript + schema
      2. Call Gemini
      3. Parse JSON → validate with Pydantic
      4. If JSON parse fails → retry with repair prompt (1 attempt)
      5. If repair fails → raise RuntimeError with the raw response

    Raises:
        ValueError: if GEMINI_API_KEY is not configured
        RuntimeError: if Gemini returns unparseable output after repair attempt
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Get your key at https://aistudio.google.com/app/apikey"
        )

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        generation_config=genai.GenerationConfig(
            temperature=0.2,       # low temperature = consistent structured output
            max_output_tokens=8192,
        ),
    )

    # Token optimisation: 800k chars ≈ 200k tokens, well inside 1M context
    MAX_TRANSCRIPT_CHARS = 800_000
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        logger.warning(
            f"Transcript truncated from {len(transcript)} to {MAX_TRANSCRIPT_CHARS} chars"
        )
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n[TRANSCRIPT TRUNCATED]"

    prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
        transcript=transcript,
        schema=_ANALYSIS_SCHEMA,
    )

    logger.info(f"Sending {len(transcript)} char transcript to Gemini for analysis")
    start = time.time()

    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")

    elapsed = time.time() - start
    logger.info(f"Gemini analysis complete in {elapsed:.1f}s")

    
    # Parse and validate
    
    analysis = _parse_analysis(raw_text)
    if analysis is not None:
        return analysis

    
    # First parse failed — attempt one repair
    
    logger.warning("Initial Gemini response failed JSON validation. Attempting repair...")
    repair_prompt = _REPAIR_PROMPT.format(
        schema=_ANALYSIS_SCHEMA,
        bad_response=raw_text[:4000],  # truncate to avoid huge repair prompt
    )

    try:
        repair_response = model.generate_content(repair_prompt)
        repaired_text = repair_response.text.strip()
    except Exception as e:
        raise RuntimeError(f"Gemini repair attempt failed: {e}")

    analysis = _parse_analysis(repaired_text)
    if analysis is not None:
        logger.info("Repair attempt succeeded")
        return analysis

    raise RuntimeError(
        f"Gemini returned invalid JSON after repair attempt. "
        f"Raw response (first 500 chars): {raw_text[:500]}"
    )


def _parse_analysis(raw: str) -> Optional[MeetingAnalysis]:
    """
    Try to parse a Gemini response string into a MeetingAnalysis.
    Returns None on any parse/validation error.
    """
    # Gemini sometimes wraps in ```json ... ``` despite instructions
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first and last lines (the ``` fences)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return MeetingAnalysis.model_validate_json(text)
    except Exception as e:
        logger.debug(f"JSON parse failed: {e} | raw[:200]={raw[:200]}")
        return None



# Q&A — Question Answering against transcript


_QA_PROMPT_TEMPLATE = """You are an intelligent meeting assistant with access to a meeting transcript.
Answer the user's question based ONLY on information in the transcript.
If the answer is not in the transcript, say so clearly.
Be concise and direct. Use bullet points for lists.

MEETING TITLE: {title}

TRANSCRIPT:
{transcript}

USER QUESTION: {question}

ANSWER:"""


def answer_question(transcript: str, question: str, meeting_title: str = "") -> str:
    """
    Answer a question about a meeting using its transcript.

    No RAG, no vector DB — we pass the full transcript in context.
    Gemini's 1M token window makes this viable for any realistic meeting length.

    Returns:
        str: The answer text

    Raises:
        ValueError: if GEMINI_API_KEY not set or question/transcript empty
        RuntimeError: if Gemini call fails
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")
    if not question.strip():
        raise ValueError("Question cannot be empty")
    if not transcript.strip():
        raise ValueError("No transcript available for this meeting")

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        generation_config=genai.GenerationConfig(
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )

    # Trim transcript for Q&A — answers are simpler, can use less context
    MAX_QA_TRANSCRIPT = 600_000
    trimmed = transcript[:MAX_QA_TRANSCRIPT] if len(transcript) > MAX_QA_TRANSCRIPT else transcript

    prompt = _QA_PROMPT_TEMPLATE.format(
        title=meeting_title,
        transcript=trimmed,
        question=question.strip(),
    )

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"Gemini Q&A error: {e}")



# Full pipeline — called by processor.py


def run_ai_pipeline(meeting_id: str, db) -> dict:
    """
    Complete AI processing pipeline for a meeting.

    Called by processor.py's background thread via the ai_processor hook.
    Downloads audio → transcribes → analyses → writes results to DB.

    Returns a dict with all extracted fields (also persisted to DB).

    This function DOES write to DB (exception to the "pure function" rule)
    because the processor needs intermediate progress saves. The processor
    still controls job status updates.
    """
    from .models import Meeting
    from .storage import download_audio

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise RuntimeError(f"Meeting {meeting_id} not found")

    if not meeting.storage_path:
        raise RuntimeError("Meeting has no audio file in storage")

    
    # Step 1: Download audio from Supabase Storage
    
    logger.info(f"Downloading audio for meeting {meeting_id}")
    audio_bytes = download_audio(meeting.storage_path)
    logger.info(f"Downloaded {len(audio_bytes) / 1024:.1f}KB")

    
    # Step 2: Transcribe with Groq Whisper
    
    filename = meeting.file_name or "audio.mp3"
    transcription_result = transcribe_audio(audio_bytes, filename)

    transcript_text = transcription_result["text"]
    detected_language = transcription_result["language"]
    audio_duration = transcription_result["duration"]

    # Save transcript immediately — if analysis fails, we still have the transcript
    meeting.transcript = transcript_text
    meeting.language = detected_language
    if audio_duration:
        meeting.duration_seconds = float(audio_duration)
    db.commit()
    logger.info(f"Transcript saved for meeting {meeting_id} ({len(transcript_text)} chars)")

    
    # Step 3: Analyse with Gemini
    
    analysis = analyse_transcript(transcript_text)

    
    # Step 4: Persist structured results
    
    meeting.summary = analysis.executive_summary
    meeting.action_items = json.dumps(
        [item.model_dump() for item in analysis.action_items]
    )
    meeting.decisions = json.dumps(
        [d.model_dump() for d in analysis.decisions]
    )
    meeting.risks = json.dumps(
        [r.model_dump() for r in analysis.risks]
    )
    meeting.participants = json.dumps(analysis.participants)
    meeting.follow_up_email = analysis.follow_up_email
    db.commit()

    logger.info(
        f"AI analysis saved for meeting {meeting_id}: "
        f"{len(analysis.action_items)} action items, "
        f"{len(analysis.decisions)} decisions, "
        f"{len(analysis.risks)} risks"
    )

    return {
        "transcript": transcript_text,
        "language": detected_language,
        "duration_seconds": audio_duration,
        "summary": analysis.executive_summary,
        "action_items": analysis.action_items,
        "decisions": analysis.decisions,
        "risks": analysis.risks,
        "participants": analysis.participants,
        "follow_up_email": analysis.follow_up_email,
        "sentiment": analysis.sentiment,
        "meeting_type": analysis.meeting_type,
    }
