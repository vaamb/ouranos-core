from __future__ import annotations

import asyncio
from asyncio import Event
import signal
import threading
from types import FrameType


SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)


class Runner:
    __slots__ = ("_should_exit", )

    def __init__(self) -> None:
        self._should_exit = Event()

    def _handle_stop_signal(self, sig: int, frame: FrameType | None) -> None:  # noqa
        self._should_exit.set()

    def add_signal_handler(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return

        loop = asyncio.get_event_loop()

        try:
            for sig in SIGNALS:
                loop.add_signal_handler(sig, self._handle_stop_signal, sig, None)
        except NotImplementedError:
            for sig in SIGNALS:
                signal.signal(sig, self._handle_stop_signal)

    async def run_until_stop(self) -> None:
        await asyncio.sleep(0.1)
        self.add_signal_handler()
        await self._should_exit.wait()
        await self.shutdown()

    async def stop(self) -> None:
        self._should_exit.set()

    async def shutdown(self):
        # TODO: look more closely what happens when closing loop
        await asyncio.sleep(0.4)
