import asyncio
import os
from google import genai

async def test_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set")
        return
        
    print(f"Testing with key: {api_key[:10]}...")
    client = genai.Client(api_key=api_key)
    
    try:
        response_stream = await client.aio.models.generate_content_stream(
            model='gemini-2.5-flash', 
            contents='Hello, respond with one word.'
        )
        print("Stream established. Chunks:")
        async for chunk in response_stream:
            print(f"- {chunk.text}")
        print("Success.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
