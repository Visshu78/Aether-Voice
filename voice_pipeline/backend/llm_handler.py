"""
llm_handler.py — Local LLM streaming + sentence-level chunker.

Uses `httpx` and Server-Sent Events (SSE). Streams tokens and emits complete sentences
one at a time to minimize TTS latency.
"""
import asyncio
import json
import logging
import re
import traceback
from typing import AsyncGenerator

import httpx

from config import LOCAL_LLM_API_KEY, LOCAL_LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)

# Sentence-ending punctuation pattern. Added a comma so we can yield
# the first chunk even faster (e.g. "Well," -> TTS fires instantly)
_SENTENCE_END = re.compile(r'(?<=[.!?,\n])\s+')

# Emit a chunk after this many words even if no punctuation has arrived yet.
WORD_CHUNK_THRESHOLD = 10

SYSTEM_PROMPT = (
    "You are a fast, highly conversational voice assistant. "
    "Respond with EXTREMELY punchy, abrupt, short sentences. "
    "CRITICAL RULES:\n"
    "1. Never use filler words like 'Ah', 'Well', 'Hmm', 'Let me see'. Start your answer immediately.\n"
    "2. Never use markdown (*, **, #), bullet points, or special characters.\n"
    "3. Do not output any <think> tags or reasoning steps. Output only the final response text.\n"
    "4. Keep responses strictly under 2 sentences unless complex detail is requested."
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
    Stream Local LLM and yield one complete sentence at a time.

    Args:
        transcript: User's spoken text.
        cancel_event: Checked between token batches — set to abort.
        on_state: Callback to update pipeline state.
    """
    await on_state("thinking")

    buffer = ""
    headers = {
        "Authorization": f"Bearer {LOCAL_LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript}
        ],
        "temperature": 0.5,
        "stream": True,
        "max_tokens": 300
    }
    
    # Optional trailing slash handling
    base_url = LOCAL_LLM_BASE_URL.rstrip('/')
    url = f"{base_url}/chat/completions"

    in_think_block = False

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if cancel_event.is_set():
                        logger.info("LLM streaming cancelled")
                        break
                    
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                        
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                        
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if not delta:
                            continue
                            
                        # Handle streaming <think> tags by simply eating tokens while inside one
                        if "<think>" in delta:
                            in_think_block = True
                            delta = delta.split("<think>")[-1] # take anything after (unlikely)
                        if "</think>" in delta:
                            in_think_block = False
                            delta = delta.split("</think>")[-1] # take actual content after
                            continue # skip this chunk just in case
                            
                        if in_think_block:
                            continue
                            
                        buffer += delta
                        # Clean possible bold markers
                        buffer = buffer.replace("**", "").replace("*", "")
                        sentences, buffer = _split_sentences(buffer)

                        # Word-count fallback
                        if not sentences and len(buffer.split()) >= WORD_CHUNK_THRESHOLD:
                            sentences = [buffer.strip()]
                            buffer = ""

                        for sentence in sentences:
                            if sentence and not sentence.isspace():
                                logger.debug(f"📤 LLM sentence: {sentence}")
                                yield sentence

                    except json.JSONDecodeError:
                        continue
                        
        # Emit any remaining text as a final sentence
        if buffer.strip() and not cancel_event.is_set():
            yield buffer.strip()

    except asyncio.CancelledError:
        logger.info("LLM task cancelled")
    except Exception as e:
        print(f"CRITICAL LLM ERROR: {e}")
        traceback.print_exc()
        logger.error(f"LLM error: {e}", exc_info=True)
