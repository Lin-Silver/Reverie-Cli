"""Signals and event bus primitives for Reverie Engine Lite."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict


class Signal:
    """A small observer primitive."""

    def __init__(self) -> None:
        self._listeners: list[Callable[..., Any]] = []

    def connect(self, listener: Callable[..., Any]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def disconnect(self, listener: Callable[..., Any]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for listener in list(self._listeners):
            listener(*args, **kwargs)


class EventBus:
    """Named pub-sub channels shared by the runtime."""

    def __init__(self) -> None:
        self._channels: DefaultDict[str, Signal] = defaultdict(Signal)

    def subscribe(self, channel: str, listener: Callable[..., Any]) -> None:
        self._channels[str(channel)].connect(listener)

    def unsubscribe(self, channel: str, listener: Callable[..., Any]) -> None:
        self._channels[str(channel)].disconnect(listener)

    def publish(self, channel: str, *args: Any, **kwargs: Any) -> None:
        self._channels[str(channel)].emit(*args, **kwargs)
