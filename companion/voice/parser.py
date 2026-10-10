"""Deliberately small, whole-phrase command grammar."""

import unicodedata


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    # Replace punctuation with boundaries; never delete arbitrary words or symbols.
    text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
    return " ".join(text.split())


def parse_command(text: str) -> dict | None:
    """Return a fresh action payload without an ID, or None for noncommands."""
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
        if words[0] in {"scale", "extrude", "move"}:
            return {"action": "set_mode", "mode": words[0].upper()}
        if words[0] in {"cancel", "undo"}:
            return {"action": words[0]}
    return None
