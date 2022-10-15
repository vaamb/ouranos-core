from __future__ import annotations

import asyncio
import signal
from types import FrameType


SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)


class Runner:
    def __init__(self) -> None:
        self.should_exit = False

    def stop(self) -> None:
        self.should_exit = True

    def handle_signal(self, sig: int, frame: FrameType | None) -> None:
        self.stop()

    def add_signal_handler(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            for sig in SIGNALS:
                loop.add_signal_handler(sig, self.handle_signal, sig, None)
        except NotImplementedError:
            for sig in SIGNALS:
                signal.signal(sig, self.handle_signal)

    async def start(self) -> None:
        while not self.should_exit:
            await asyncio.sleep(0.2)
