import asyncio
import httpx
import json

URL = "http://192.168.56.1:2424"

async def test_local_endpoint():
    print(f"DEBUGGER AGENT: Testing connection to local LLM at {URL} ...")
    
    # 1. Test basic connectivity / models endpoint (standard OpenAI format)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{URL}/v1/models")
            if response.status_code == 200:
                print("✅ OPENAI-COMPATIBLE API DETECTED: /v1/models responded.")
                data = response.json()
                models = [m.get("id") for m in data.get("data", [])]
                print(f"Available Models: {models}")
                if models:
                    return models[0], "openai"
            else:
                print(f"⚠️ /v1/models returned status {response.status_code}")
                print(f"Response: {response.text[:200]}")
    except httpx.RequestError as e:
         print(f"❌ Connection failed: {e}")
         return None, None

    # 2. Test base URL (maybe it's Ollama or text-generation-webui)
    try:
         async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{URL}/api/tags") # Ollama format
            if response.status_code == 200:
                print("✅ OLLAMA API DETECTED: /api/tags responded.")
                data = response.json()
                models = [m.get("name") for m in data.get("models", [])]
                print(f"Available Models: {models}")
                if models:
                    return models[0], "ollama"
    except Exception:
        pass
        
    print("❌ Could not determine API format. It might require a specific path like /v1/chat/completions.")
    return None, "unknown"


if __name__ == "__main__":
    asyncio.run(test_local_endpoint())
