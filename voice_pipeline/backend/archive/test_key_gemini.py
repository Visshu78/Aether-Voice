import asyncio
import os
from google import genai
from config import GEMINI_API_KEY, LLM_MODEL

async def test_gemini():
    print(f"DEBUGGER AGENT: Testing Gemini Key... Model: {LLM_MODEL}")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
        
        response = await client.aio.models.generate_content(
            model=LLM_MODEL,
            contents="Say 'API Key is working!'"
        )
        print(f"DEBUGGER AGENT: SUCCESS! Response: {response.text}")
    except Exception as e:
        print(f"DEBUGGER AGENT: FAILED! Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
