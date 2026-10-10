"""Execute the timestamped committed event, once per audio span in this session.

With include_timestamps=True the provider sends a plain commit followed by its
timestamped partner. Plain commits and partials are feedback only. This avoids a
time-based text cooldown, which would suppress intentional repeated commands.
Source: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/event-reference
"""

import math

from .parser import normalize_text
from .service import emit_command


class TranscriptHandler:
    def __init__(self, emit, stop_event, feedback):
        self.emit = emit
        self.stop_event = stop_event
        self.feedback = feedback
        self.seen = set()

    def handle(self, data: dict) -> None:
        if self.stop_event.is_set():
            return
        kind = data.get("message_type")
        text = data.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return
        if kind == "partial_transcript":
            self.feedback(f"Partial: {text}")
            return
        if kind == "committed_transcript":
            self.feedback(f"Committed: {text}")
            return
        if kind != "committed_transcript_with_timestamps":
            return
        spans = []
        for word in data.get("words") or []:
            start, end = word.get("start"), word.get("end")
            if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                    or not math.isfinite(start) or not math.isfinite(end)
                    or start < 0 or end < start):
                spans = []
                break
            spans.append((start, end))
        if not spans:
            self.feedback("Ignored committed speech: valid word timestamps are required.")
            return
        fingerprint = (normalize_text(text), tuple(spans))
        if fingerprint in self.seen:
            return
        self.seen.add(fingerprint)
        self.feedback(f"Committed with timestamps: {text}")
        if not emit_command(text, self.emit, self.stop_event):
            self.feedback("Ignored: speech did not match one supported command phrase.")
