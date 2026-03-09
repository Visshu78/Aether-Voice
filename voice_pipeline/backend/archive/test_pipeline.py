import asyncio
import os
import sys

sys.path.append(os.path.dirname(__file__))

from llm_handler import stream_llm_sentences

async def run_test():
    cancel_event = asyncio.Event()
    
    async def mock_on_state(state):
        print(f"State: {state}")
        
    try:
        gen = stream_llm_sentences('hello, respond with exactly 5 words.', cancel_event, mock_on_state)
        async for s in gen:
            print(f"Sentence chunk: {s}")
    except Exception as e:
        print(f"CRASH: {type(e).__name__} - {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
