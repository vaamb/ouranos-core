from __future__ import annotations

import asyncio
import signal
from types import FrameType


SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)


class Runner:
    __slots__ = ("_should_exit", )

    def __init__(self) -> None:
        self._should_exit = False

    def _handle_stop_signal(self, sig: int, frame: FrameType | None) -> None:
        self._should_exit = True

    def add_signal_handler(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            for sig in SIGNALS:
                loop.add_signal_handler(sig, self._handle_stop_signal, sig, None)
        except NotImplementedError:
            for sig in SIGNALS:
                signal.signal(sig, self._handle_stop_signal)

    async def wait_forever(self) -> None:
        while not self._should_exit:
            await asyncio.sleep(0.2)

    async def exit(self) -> None:
        self._should_exit = True
        await asyncio.sleep(0.4)
