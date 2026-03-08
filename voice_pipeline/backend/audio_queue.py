"""
audio_queue.py — asyncio.Queue wrapper for piping PCM audio chunks.
"""
import asyncio


class AudioQueue:
    """
    Thread-safe async queue for raw PCM bytes.
    - Producer: WebSocket receive loop
    - Consumer: Deepgram STT sender
    """

    def __init__(self, maxsize: int = 0):
        self._q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=maxsize)

    async def put(self, chunk: bytes) -> None:
        await self._q.put(chunk)

    async def get(self) -> bytes:
        return await self._q.get()

    def put_nowait(self, chunk: bytes) -> None:
        try:
            self._q.put_nowait(chunk)
        except asyncio.QueueFull:
            pass  # drop frame if full (back-pressure safety)

    def clear(self) -> None:
        """Discard all buffered audio — called on interruption."""
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except asyncio.QueueEmpty:
                break

    def empty(self) -> bool:
        return self._q.empty()
