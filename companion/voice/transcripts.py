"""Execute the timestamped committed event, once per audio span in this session.

With include_timestamps=True the provider sends a plain commit followed by its
timestamped partner. Plain commits and partials are feedback only. This avoids a
time-based text cooldown, which would suppress intentional repeated commands.
Source: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/event-reference
"""

import math

from .parser import normalize_text
from .service import emit_command

MAX_RECENT_TRANSCRIPTS = 1024


class TranscriptHandler:
    def __init__(self, emit, stop_event, feedback):
        self.emit = emit
        self.stop_event = stop_event
        self.feedback = feedback
        self.seen = {}
        self.discard_through = -1.0

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
        words = data.get("words")
        for word in words if isinstance(words, list) else []:
            if not isinstance(word, dict):
                spans = []
                break
            if word.get("type") == "spacing":
                continue
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
        end = max(span[1] for span in spans)
        if end <= self.discard_through or fingerprint in self.seen:
            return
        self.seen[fingerprint] = end
        if len(self.seen) > MAX_RECENT_TRANSCRIPTS:
            # Keep recent spans and reject replays older than the evicted audio.
            # This uses the provider's session audio timeline, never wall time.
            oldest = min(self.seen, key=self.seen.get)
            self.discard_through = max(self.discard_through, self.seen.pop(oldest))
        self.feedback(f"Committed with timestamps: {text}")
        if not emit_command(text, self.emit, self.stop_event):
            self.feedback("Ignored: speech did not match one supported command phrase.")
