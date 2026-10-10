"""Deliberately small, whole-phrase command grammar."""

import unicodedata
import re
from shared.protocol import validate_mode, validate_precision, ProtocolError


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    # Replace punctuation with boundaries; never delete arbitrary words or symbols.
    text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
    return " ".join(text.split())


def parse_command(text: str) -> dict | None:
    """Return a fresh action payload without an ID, or None for noncommands."""
    precise = " ".join(unicodedata.normalize("NFKC", text).casefold().strip().split()).rstrip(".!?")
    number = r"([+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))"
    patterns = ((rf"rotate ([xyz]) {number} degrees?", 'ROTATE'),
                (rf"move ([xyz]) {number} units?", 'MOVE'),
                (rf"scale by {number}", 'SCALE'),
                (rf"(?:extrude|extend) {number} units?", 'EXTRUDE'))
    for pattern, mode in patterns:
        match = re.fullmatch(pattern, precise)
        if match:
            payload = dict(action='precision', mode=mode, value=float(match.groups()[-1]))
            if mode in ('MOVE','ROTATE'):
                payload['axis'] = match[1].upper()
            try:
                validate_precision(dict(payload, id='validation-only'))
            except ProtocolError:
                return None
            return payload
    # Plane/axis phrases remain whole commands: no conversational extraction.
    plane_match = re.fullmatch(r"(?:extrude|extend) plane (auto|xy|xz|yz)(?: axis (none|x|y|z))?", precise)
    axis_match = re.fullmatch(r"(?:extrude|extend) axis (none|x|y|z)", precise)
    if plane_match or axis_match:
        payload = dict(action="set_mode", mode="EXTRUDE", plane="AUTO", axis="NONE")
        if plane_match:
            payload["plane"] = plane_match[1].upper()
            payload["axis"] = (plane_match[2] or "none").upper()
        else:
            payload["axis"] = axis_match[1].upper()
        try:
            validate_mode(dict(payload, id="validation-only"))
        except ProtocolError:
            return None
        return payload
    words = normalize_text(text).split()
    if len(words) >= 2 and words[0] in {"create", "add"}:
        shape = " ".join(words[1:])
        if shape == "triangular prism":
            shape = "prism"
        if shape in {"cube", "sphere", "cylinder", "prism"}:
            return {"action": "spawn", "shape": shape}
    if words == ["rotate"]:
        return {"action": "set_mode", "mode": "ROTATE", "axis": "Z"}
    if len(words) == 2 and words[0] == "rotate" and words[1] in {"x", "y", "z"}:
        return {"action": "set_mode", "mode": "ROTATE", "axis": words[1].upper()}
    if len(words) == 1:
        if words[0] == "extend":
            return {"action":"set_mode", "mode":"EXTRUDE"}
        if words[0] in {"scale", "extrude", "move"}:
            return {"action": "set_mode", "mode": words[0].upper()}
        if words[0] in {"cancel", "undo"}:
            return {"action": words[0]}
    return None
