"""Run events for live progress (M2). The agent loop, the debate and the web layer call `emit`;
when nobody listens (every non-streaming path) it does nothing, so behaviour is unchanged.

The sink lives in a ContextVar, so it is per run / per thread and needs no global state.
"""
from __future__ import annotations
from contextvars import ContextVar, Token
from typing import Callable

_SINK: ContextVar[Callable[[dict], None] | None] = ContextVar("run_event_sink", default=None)


def set_sink(fn: Callable[[dict], None] | None) -> Token:
    return _SINK.set(fn)


def reset_sink(token: Token) -> None:
    _SINK.reset(token)


def emit(kind: str, **data) -> None:
    sink = _SINK.get()
    if sink is not None:
        sink({"type": kind, **data})
