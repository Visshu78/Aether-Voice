import asyncio
from llm_handler import stream_llm_sentences

async def run_test():
    async def fake_on_state(state):
        pass
        
    cancel_event = asyncio.Event()
    
    print("Testing local LLM streaming chunks...")
    
    async for sentence in stream_llm_sentences(
        transcript="Tell me a quick two sentence joke about a robot.",
        cancel_event=cancel_event,
        on_state=fake_on_state
    ):
        print(f"CHUNK: {sentence}")
        
if __name__ == "__main__":
    asyncio.run(run_test())
