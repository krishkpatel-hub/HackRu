"""Callback service; optional audio dependencies are loaded only for microphone mode."""

import codecs
import io
import os
import select
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Event
from typing import TextIO
from uuid import uuid4

from .parser import parse_command


class VoiceError(RuntimeError):
    """An actionable voice failure; callers may continue accepting typed commands."""


def stderr_feedback(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


@dataclass
class VoiceConfig:
    source: str = "microphone"
    input_stream: TextIO | None = None
    feedback: Callable[[str], None] = stderr_feedback
    device: int | str | None = None
    sample_rate: int = 16000
    push_to_talk_event: Event | None = None
    connection_timeout: float = 10.0
    operation_timeout: float = 5.0
    state: Callable[[str], None] = stderr_feedback
    # Integration hooks: each audio stream is bound to one ready Blender session.
    session_id: Callable[[], str | None] | None = None
    emit_for_session: Callable[[dict, str], bool] | None = None


def emit_command(text: str, emit: Callable[[dict], None], stop_event: Event, *, parser=parse_command) -> bool:
    payload = parser(text)
    if payload is None or stop_event.is_set():
        return False
    return emit({"type": "command", "payload": {"id": str(uuid4()), **payload}}) is not False


def typed_lines(stream: TextIO, stop_event: Event):
    """Poll POSIX input without blocking shutdown on a partial line or open pipe."""
    if isinstance(stream, io.StringIO):
        while not stop_event.is_set():
            line = stream.readline()
            if not line:
                return
            yield line.rstrip("\r\n")
        return
    if os.name != "posix":
        raise VoiceError("Typed console input currently requires macOS/Linux.")
    decoder = codecs.getincrementaldecoder(stream.encoding or "utf-8")(errors="replace")
    pending = ""
    while not stop_event.is_set():
        if not select.select([stream.fileno()], [], [], 0.1)[0]:
            continue
        chunk = os.read(stream.fileno(), 4096)
        pending += decoder.decode(chunk, final=not chunk)
        while "\n" in pending and not stop_event.is_set():
            line, pending = pending.split("\n", 1)
            yield line.rstrip("\r")
        if not chunk:
            if pending and not stop_event.is_set():
                yield pending
            return


def run_voice(emit, stop_event, config) -> None:
    """Run until EOF/stop; config is VoiceConfig or a dict of its documented fields."""
    if isinstance(config, Mapping) or config is None:
        config = VoiceConfig(**(config or {}))
    if stop_event.is_set():
        return
    if config.source == "typed":
        for text in typed_lines(config.input_stream or sys.stdin, stop_event):
            if not emit_command(text, emit, stop_event) and text.strip():
                config.feedback("Ignored: enter one supported command phrase.")
    elif config.source == "microphone":
        from .microphone import run_microphone

        run_microphone(emit, stop_event, config)
    else:
        raise VoiceError("source must be 'typed' or 'microphone'.")
