"""Senses: one adapter per kind of finished work, all with the same three verbs.

    measure(path)              -> {"features": {name: {"value", "unit"}}, "parts": [{"span", "features"}], "notes": [...]}
    measure_span(path, span)   -> {"features": {...}} for one caller-labelled part
    evidence(path, span, out)  -> [{"type": "image"|"audio"|"text", "path"|"text"}] for the caller to look at or listen to

A span is exactly one of {"t": [start_s, end_s]}, {"box": [x, y, w, h]} (fractions of the frame), {"chars": [a, b]}
or {"section": i}; each sense says which it accepts. Features are numbers with units so works of one kind can be
compared; anything that is not a number (a palette, a heading) is reported under "notes" or as a list value and is
left out of comparisons. A host adds senses with register(); kinds are free strings ("video", "image", …).
"""
import math
from pathlib import Path

REGISTRY = {}
SPAN_KEYS = ("t", "box", "chars", "section")


def register(sense):
    REGISTRY[sense.kind] = sense
    return sense


def kinds():
    return sorted(REGISTRY)


def get(kind):
    _builtin()
    if kind not in REGISTRY:
        raise ValueError(f"No sense for kind {kind!r}; available: {kinds()}")
    return REGISTRY[kind]


def for_path(path):
    _builtin()
    ext = Path(path).suffix.lower()
    for sense in REGISTRY.values():
        if ext in sense.extensions:
            return sense
    raise ValueError(f"No sense reads {ext or 'this file'}; available kinds: {kinds()} — pass kind explicitly")


def feature(value, unit):
    if isinstance(value, float):
        value = round(value, 4) if math.isfinite(value) else None
    return {"value": value, "unit": unit}


def numeric(features):
    """Name -> number for the comparable features (finite numbers only)."""
    out = {}
    for name, f in (features or {}).items():
        v = f.get("value") if isinstance(f, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out[name] = float(v)
    return out


def check_span(sense, span):
    if not isinstance(span, dict) or len(span) != 1 or next(iter(span)) not in SPAN_KEYS:
        raise ValueError(f"A span is one of {{'t': [start_s, end_s]}}, {{'box': [x, y, w, h]}}, {{'chars': [a, b]}}, {{'section': i}}")
    key, value = next(iter(span.items()))
    if key not in sense.spans:
        raise ValueError(f"{sense.kind} works take spans {sense.spans}, not {key!r}")
    if key == "section":
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("section span is a part index >= 0")
        return span
    if key == "box":
        if not (isinstance(value, list) and len(value) == 4 and all(isinstance(v, (int, float)) for v in value)):
            raise ValueError("box span is [x, y, w, h] as fractions of the frame")
        x, y, w, h = value
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-9 and 0 < h <= 1 - y + 1e-9):
            raise ValueError("box span must lie inside the frame (fractions 0..1)")
        return span
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in value)
            and 0 <= value[0] < value[1]):
        raise ValueError(f"{key} span is [start, end] with 0 <= start < end")
    return span


def _builtin():
    if not REGISTRY or not {"text", "image", "audio", "web"} <= REGISTRY.keys():
        from . import audio, image, text, web  # noqa: F401  (they register themselves)
