import asyncio
import json
import websockets
import ssl
from config import DEEPGRAM_API_KEY, SAMPLE_RATE, ENCODING, CHANNELS

DEEPGRAM_URL = (
    f"wss://api.deepgram.com/v1/listen"
    f"?model=nova-2"
    f"&encoding={ENCODING}"
    f"&sample_rate={SAMPLE_RATE}"
    f"&channels={CHANNELS}"
)

# Using default SSL context (with verification)
# pip-system-certs should now allow this to work on Windows
ssl_context = ssl.create_default_context()
# ssl_context.check_hostname = False # Re-enable these for security
# ssl_context.verify_mode = ssl.CERT_NONE

async def _run_test_logic(ws):
    print("DEBUGGER AGENT: ✅ SUCCESS! Connected to Deepgram.")
    # Send a tiny silent chunk
    silent_chunk = b'\x00' * 3200
    await ws.send(silent_chunk)
    print("DEBUGGER AGENT: Sent silent audio chunk.")
    await ws.send(json.dumps({"type": "CloseStream"}))
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"DEBUGGER AGENT: Received response: {msg[:100]}...")
    except asyncio.TimeoutError:
         print("DEBUGGER AGENT: No response received (timeout).")

async def test_deepgram():
    print(f"DEBUGGER AGENT: Testing Deepgram Connection...")
    print(f"URL: {DEEPGRAM_URL}")
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    
    connect_args = {
        "ssl": ssl_context,
        "open_timeout": 10
    }
    
    try:
        # Try both argument names for different websockets versions
        try:
            from websockets.asyncio.client import connect as connect_v14
            print("DEBUGGER AGENT: Trying websockets 14+ API")
            async with connect_v14(DEEPGRAM_URL, additional_headers=headers, **connect_args) as ws:
                await _run_test_logic(ws)
        except (ImportError, TypeError):
            print("DEBUGGER AGENT: Trying websockets < 14 API")
            async with websockets.connect(DEEPGRAM_URL, extra_headers=headers, **connect_args) as ws:
                await _run_test_logic(ws)
                
    except Exception as e:
        print(f"DEBUGGER AGENT: ❌ FAILED! Deepgram Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_deepgram())
    except KeyboardInterrupt:
        print("\nStopped.")
