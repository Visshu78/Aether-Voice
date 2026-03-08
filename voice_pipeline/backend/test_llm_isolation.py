import asyncio
import os
from dotenv import load_dotenv
from llm_handler import stream_llm_sentences

async def on_state(state):
    print(f"State: {state}")

async def test():
    load_dotenv()
    cancel_event = asyncio.Event()
    transcript = "Hello, how are you? Tell me a short joke."
    
    print(f"Testing Gemini with transcript: '{transcript}'")
    
    try:
        count = 0
        async for sentence in stream_llm_sentences(transcript, cancel_event, on_state):
            print(f"Sentence {count}: {sentence}")
            count += 1
            if count > 5: break
            
        if count == 0:
            print("No sentences generated.")
        else:
            print(f"Generated {count} sentences.")
            
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test())
