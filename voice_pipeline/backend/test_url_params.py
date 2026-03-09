import asyncio
import websockets
import ssl
from config import DEEPGRAM_API_KEY, SAMPLE_RATE, ENCODING, CHANNELS

headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
ssl_context = ssl.create_default_context()

async def test_url(url, test_name):
    try:
        from websockets.asyncio.client import connect
        async with connect(url, additional_headers=headers, ssl=ssl_context) as ws:
            print(f"✅ {test_name}: SUCCESS")
    except websockets.exceptions.InvalidStatus as e:
        print(f"❌ {test_name}: HTTP 400 - {e}")
        try:
            print(f"Body: {e.response.body}")
        except: pass
    except Exception as e:
        print(f"❌ {test_name}: ERROR {e}")

async def main():
    URL1 = f"wss://api.deepgram.com/v1/listen?model=nova-2&encoding={ENCODING}&sample_rate={SAMPLE_RATE}&channels={CHANNELS}"
    URL2 = f"{URL1}&interim_results=true&endpointing=100&utterance_end_ms=600"
    URL3 = f"{URL1}&interim_results=true&endpointing=300"
    
    await test_url(URL1, "Base URL")
    await test_url(URL2, "Failing URL params")
    await test_url(URL3, "Standard Params")

if __name__ == "__main__":
    asyncio.run(main())
