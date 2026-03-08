"""
interruption.py — InterruptionHandler that cancels the backend pipeline
and signals the frontend to stop audio playback.
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class InterruptionHandler:
    """
    Manages interruption state for a single WebSocket session.

    Usage:
        handler = InterruptionHandler(websocket, audio_queue)
        await handler.trigger()   # call when user speech detected mid-playback
        handler.reset()           # call when pipeline is idle / ready for new turn
    """

    def __init__(self, websocket: WebSocket, audio_queue):
        self._ws = websocket
        self._audio_queue = audio_queue
        self.cancel_event: asyncio.Event = asyncio.Event()
        self._active_tasks: list[asyncio.Task] = []

    def register_task(self, task: asyncio.Task) -> None:
        """Register a pipeline task so it can be cancelled on interrupt."""
        self._active_tasks.append(task)

    async def trigger(self) -> None:
        """
        Interrupt the current pipeline turn:
        1. Set cancel_event (tasks must check this)
        2. Cancel all registered asyncio Tasks
        3. Clear buffered audio
        4. Send {"type": "stop"} to frontend
        """
        logger.info("⚡ Interruption triggered")
        print("DEBUG: ⚡ Interruption triggered")
        self.cancel_event.set()

        # Cancel running pipeline tasks
        for task in self._active_tasks:
            if not task.done():
                task.cancel()
        self._active_tasks.clear()

        # Flush buffered audio
        self._audio_queue.clear()

        # Signal frontend to stop playback
        try:
            await self._ws.send_text(json.dumps({"type": "stop"}))
        except Exception as e:
            logger.warning(f"Could not send stop signal: {e}")

    def reset(self) -> None:
        """Clear the interrupt state for the next turn."""
        self.cancel_event.clear()
        self._active_tasks.clear()
