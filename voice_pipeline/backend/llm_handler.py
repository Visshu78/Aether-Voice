"""
llm_handler.py — Google Gemini streaming + sentence-level chunker.

Uses `google-genai` SDK. Streams tokens and emits complete sentences
one at a time to minimize TTS latency.
"""
import asyncio
import logging
import re
from typing import AsyncGenerator

from google import genai

from config import GEMINI_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

# Initialize the official Gemini SDK client
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})

# Sentence-ending punctuation pattern
_SENTENCE_END = re.compile(r'(?<=[.!?\n])\s+')

# Emit a chunk after this many words even if no punctuation has arrived yet.
WORD_CHUNK_THRESHOLD = 10

SYSTEM_PROMPT = (
    "You are a helpful, concise voice assistant. "
    "Respond in short, natural sentences. "
    "Avoid markdown, bullet points, or special characters. "
    "Keep responses under 3 sentences unless asked for more detail."
)

config = genai.types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.5,
    max_output_tokens=300,
)


def _split_sentences(text: str) -> tuple[list[str], str]:
    """
    Split `text` into complete sentences and a leftover fragment.

    Returns:
        (sentences, remainder) where remainder is accumulated text without
        a terminal punctuation mark yet.
    """
    parts = _SENTENCE_END.split(text)
    if not parts:
        return [], text

    last = parts[-1]
    complete = parts[:-1]

    # If text ends with sentence terminator, last part is also complete
    if text and text[-1] in '.!?\n':
        complete = parts
        last = ''

    return [s.strip() for s in complete if s.strip()], last


async def stream_llm_sentences(
    transcript: str,
    cancel_event: asyncio.Event,
    on_state,    # async callable(state: str)
) -> AsyncGenerator[str, None]:
    """
    Stream Gemini and yield one complete sentence at a time.

    Args:
        transcript: User's spoken text.
        cancel_event: Checked between token batches — set to abort.
        on_state: Callback to update pipeline state.
    """
    await on_state("thinking")

    buffer = ""
    try:
        response_stream = await client.aio.models.generate_content_stream(
            model=LLM_MODEL,
            contents=transcript,
            config=config,
        )

        async for chunk in response_stream:
            if cancel_event.is_set():
                logger.info("LLM streaming cancelled")
                break

            delta = chunk.text
            if not delta:
                continue

            buffer += delta
            # Clean possible bold markers from Gemini
            buffer = buffer.replace("**", "")
            sentences, buffer = _split_sentences(buffer)

            # Word-count fallback
            if not sentences and len(buffer.split()) >= WORD_CHUNK_THRESHOLD:
                sentences = [buffer.strip()]
                buffer = ""

            for sentence in sentences:
                if sentence:
                    logger.debug(f"📤 LLM sentence: {sentence}")
                    yield sentence

        # Emit any remaining text as a final sentence
        if buffer.strip() and not cancel_event.is_set():
            yield buffer.strip()

    except asyncio.CancelledError:
        logger.info("LLM task cancelled")
    except Exception as e:
        logger.error(f"LLM error: {e}", exc_info=True)
