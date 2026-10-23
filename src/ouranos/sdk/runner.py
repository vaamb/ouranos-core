from __future__ import annotations

import asyncio
from asyncio import Event
import signal
import threading
from types import FrameType
from typing import Awaitable, Callable


SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)


class Runner:
    __slots__ = ("_handling_signal", "_should_exit", )

    def __init__(self) -> None:
        self._should_exit = Event()
        self._handling_signal: bool = False

    def _handle_stop_signal(self, sig: int, frame: FrameType | None) -> None:  # noqa
        self._should_exit.set()

    def add_signal_handler(self) -> None:
        if self._handling_signal:
            return

        if threading.current_thread() is not threading.main_thread():
            return

        loop = asyncio.get_event_loop()

        try:
            for sig in SIGNALS:
                loop.add_signal_handler(sig, self._handle_stop_signal, sig, None)
        except NotImplementedError:
            for sig in SIGNALS:
                signal.signal(sig, self._handle_stop_signal)

        self._handling_signal = True

    async def run_until_stop(
            self,
            funcs: list[Callable[[], Awaitable[None]]] | None = None,
    ) -> None:
        funcs = funcs or []
        await asyncio.sleep(0.1)
        if not self._handling_signal:
            self.add_signal_handler()
        while not self._should_exit.is_set():
            for func in funcs:
                await func()
            try:
                await asyncio.wait_for(self._should_exit.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
        await self.shutdown()

    @property
    def stopping(self) -> bool:
        return self._should_exit.is_set()

    def stop(self) -> None:
        self._should_exit.set()

    async def shutdown(self):
        # TODO: look more closely what happens when closing loop
        await asyncio.sleep(0.4)


runner = Runner()
