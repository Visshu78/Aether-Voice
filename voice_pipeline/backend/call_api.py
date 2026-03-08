import asyncio, websockets; async def run():
    async with websockets.connect('ws://127.0.0.1:8000/ws/audio') as ws:
        await ws.send(b'\0'*32000)
        await asyncio.sleep(3)
        print('Done')
asyncio.run(run())
