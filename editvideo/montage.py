"""Archival montage in the blockbuster manner: real footage cut over a driving cue toward a catastrophe, with text that
lands on screen (research: reports/Montage tư liệu kiểu bom tấn.md).

Measured on the reference sequences (research_notes/.../measured_sequences.md):
- World War Z (2013) opening: 78 cuts in 127 s, average shot 2.36 s -> 1.63 s -> 1.25 s by thirds and 0.6 s in the
  last ten seconds, the sound rising about 25 LU over two minutes;
- Kong: Skull Island (2017) titles: 146 cuts in 98 s (median 0.5 s), 45 one- or two-frame leader/flash frames, dates
  in small tracked capitals walking through 1945-1973, some shots shown as a projected film frame;
- Godzilla (2014) titles: documents whose words are struck out by redaction bars except the names, a 13 LU crescendo
  to the blast, then a white-out and near silence before a small title.

The recipe is the "flood" (WWZ/Kong) with the Godzilla dossier's devices as cards and its ending:
1. the body: footage in the given order, each shot shorter than the last (asl_start -> asl_end, most of the
   acceleration in the last third), snapped to the cue's beats when given, some shots projected as film frames, a
   leader frame on some cuts (never more than two a second: the photosensitivity gate allows three);
2. cards: dates and places in small tracked capitals, a headline slammed full frame (the film's own words, never a
   newspaper's masthead), a document struck out by redaction bars leaving the words that matter, a stamp, a
   teletype line, a counter that climbs;
3. the hit: picture and sound drop to black for `gap_s` (the silence before the hit; a weak sound 30-500 ms before a
   loud one blunts the startle), then the climax shot lands with a flash;
4. the end: white-out or black, `silence_s` of silence, a small title, out.

Real archive stays attached to its real event: a shot's date and place are its own, never a borrowed meaning.
`sound_plan` in the result times every cut, flash, card, the suck-out, the hit and the silence; `score()` turns it
into procedural layers and a music cut so the caller imports and places them.
"""
import random
import re
from types import SimpleNamespace
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

FPS = 30
HEX = r"^#[0-9a-fA-F]{6}$"
LEADER = ("#c8461c", "#e0802c", "#f0b85c", "#b8321a", "#f2dcae")  # leader/flash-frame tints: warm, never pure white


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1, max_length=100)
    source_start: float = Field(default=0.0, ge=0)
    duration: float = Field(gt=.2, le=600)              # usable seconds from source_start (no cut, title card, dark or burnt frame inside)
    kind: Literal["archive", "reconstruction", "graphic"] = "archive"  # a CG reconstruction or a graphic is never captioned as archive
    year: int | None = Field(default=None, ge=1880, le=2100)  # the year the footage was SHOT; None: unknown (reported)
    date: str = Field(default="", max_length=24)        # its own date, e.g. "8.1964"
    place: str = Field(default="", max_length=32)       # its own place, e.g. "Vịnh Bắc Bộ"
    role: Literal["calm", "news", "threat", "climax"] = "news"
    frame: Literal["auto", "full", "projected"] = "auto"
    sound: bool = False                                  # its own sound is usable (a voice, an engine): heard under the cue
    voice_s: float | None = Field(default=None, gt=0, le=8)  # its sound runs this long from its cut in, over the next shots (an L-cut to the phrase's end)
    says: str = Field(default="", max_length=160)         # what its voice says, translated: shown as its subtitle while it plays
    says_by: str = Field(default="", max_length=60)       # who said it, and when ("Robert McNamara · 4.8.1964")
    date_source: Literal["own", "compilation"] = "own"   # compilation: the date is a later film's claim, never captioned
    fps: float | None = Field(default=None, gt=0, le=120)  # the source's rate: 24/25 fps archive is played through motion-interpolated frames
    saturation: float = Field(default=1.0, ge=0, le=1.5)  # tame a colour cast (a magenta or cyan reel) without a full grade

    @model_validator(mode="after")
    def honest(self):
        if self.kind != "archive" and (self.date or self.place):
            raise ValueError(f"a {self.kind} carries no archive date or place: caption it as what it is, or use real footage")
        y = re.search(r"(18|19|20)\d\d", self.date or "")
        if y and self.year and int(y.group()) != self.year:
            raise ValueError(f"date {self.date} disagrees with year {self.year}")
        if y and not self.year:
            self.year = int(y.group())
        if self.voice_s and not self.says:
            raise ValueError("a voice that runs on (voice_s) is speech: give its translation in `says` (an untranslated line reaches no one)")
        if self.says and not self.sound:
            raise ValueError("`says` subtitles the shot's own sound: set sound")
        return self


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["headline", "redact", "stamp", "teletype", "counter", "quote"]
    at: float = Field(ge=0)                               # seconds from the montage start
    hold: float | None = Field(default=None, gt=.3, le=8)  # default: reading time (bible: 17 characters a second, 1.5 s floor)
    text: str = Field(default="", max_length=160)        # headline/stamp/teletype/quote; counter: its label
    lines: list[str] = Field(default_factory=list, max_length=8)  # redact: the document's lines
    keep: list[str] = Field(default_factory=list, max_length=12)  # redact: words left legible (all others are struck out)
    source: str = Field(default="", max_length=80)        # who said or wrote it; shown small under headlines and quotes
    value_from: float = 0                                 # counter
    value_to: float = 0
    suffix: str = Field(default="", max_length=12)


class ArchiveMontage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: Literal["archive_montage"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    start_frame: int = Field(ge=0)
    end_frame: int
    shots: list[Shot] = Field(min_length=3, max_length=120)
    cards: list[Card] = Field(default_factory=list, max_length=24)
    years: list[int] | None = Field(default=None, min_length=2, max_length=2)  # [first, last]: footage shot outside is refused
    asl_start: float = Field(default=2.3, ge=.3, le=8)    # average shot length at the start and at the end (s)
    asl_end: float = Field(default=.6, ge=.25, le=8)
    curve: float = Field(default=1.6, ge=.5, le=4)        # >1 keeps the acceleration for the last third
    beats: list[float] = Field(default_factory=list, max_length=2000)  # cue beat times (s from the montage start)
    projected_share: float = Field(default=.3, ge=0, le=1)
    flash: Literal["none", "leader"] = "leader"
    flash_gap_s: float = Field(default=1.2, ge=.5, le=10)  # at least this long between two leader frames
    gap_s: float = Field(default=.6, ge=0, le=2)          # black and silence before the hit
    climax_s: float = Field(default=2.4, ge=.8, le=8)     # the climax shot after the hit
    ending: Literal["whiteout", "black", "drain"] = "whiteout"
    silence_s: float = Field(default=1.6, ge=0, le=6)
    title: str = Field(default="", max_length=60)
    title_s: float = Field(default=3.2, ge=1.5, le=8)
    accent: str = Field(default="#e8c46a", pattern=HEX)   # dates and places (Kong's warm yellow)
    ink: str = Field(default="#f4ead8", pattern=HEX)
    stamp_color: str = Field(default="#9e2318", pattern=HEX)  # dark enough for 3:1 on paper under a vignette
    grain: float = Field(default=.16, ge=0, le=1)          # 16 mm grain (overlay: blacks stay black), off the gap and the end
    allow_undated: bool = False                           # a dated card may sit over footage of unknown year (the caller vouches)
    seed: int = Field(default=7, ge=0, le=2 ** 31 - 1)
    z: int = Field(default=900, ge=0, le=990)

    @model_validator(mode="after")
    def check(self):
        N = self.end_frame - self.start_frame
        tail = self.gap_s + self.climax_s + (self.silence_s + self.title_s if self.title else self.silence_s) + .5
        if N < int((6 + tail) * FPS):
            raise ValueError(f"archive_montage needs >= {6 + tail:.1f} s: six seconds of body, the gap, the climax, the silence and the title")
        if not any(s.role == "climax" for s in self.shots):
            raise ValueError("mark one shot role=climax: the picture the hit lands on")
        if self.years:
            lo, hi = sorted(self.years)
            out = [f"#{i} ({s.year})" for i, s in enumerate(self.shots) if s.year and not lo <= s.year <= hi]
            if out:
                raise ValueError(f"footage shot outside {lo}-{hi}: {', '.join(out[:8])}; move it to its own story or widen `years`")
        for c in self.cards:
            if c.kind == "redact" and (not c.lines or not c.keep):
                raise ValueError("a redact card needs its document lines and the words kept legible")
            if c.kind == "counter" and c.value_to <= c.value_from:
                raise ValueError("a counter climbs: value_to > value_from")
            if c.kind in ("headline", "stamp", "teletype", "quote", "counter") and not c.text.strip():
                raise ValueError(f"a {c.kind} card needs its text")
        return self


def rhythm(frames, asl_start, asl_end, curve=1.6, seed=7, beats=(), floor=8, avail=None):
    """Shot lengths in frames filling `frames`: the average moves from asl_start to asl_end (s) geometrically with the
    elapsed share to the power `curve`; each length varies by a seeded factor 0.8-1.25 and its cut snaps to the nearest
    beat or half-beat within four frames. avail: per-shot maxima in frames; no slot ever runs past its shot's footage."""
    rng = random.Random(seed)
    bs = sorted(beats)  # beats and the half-beats between them: at 120-130 BPM an eighth note is 7 frames, so every cut lands
    beat_f = sorted({round(b * FPS) for b in bs} | {round((a + b) / 2 * FPS) for a, b in zip(bs, bs[1:])})
    out, f, k = [], 0, 0
    while f < frames:
        u = f / frames
        asl = asl_start * (asl_end / asl_start) ** (u ** curve)
        want = max(floor, round(asl * FPS * rng.uniform(.8, 1.25)))
        least = max(floor, round(.35 * asl * FPS))  # no sliver: a 0.3 s shot among 2 s shots reads as a glitch
        cap = None
        if avail is not None:
            if k >= len(avail):
                raise ValueError(f"not enough footage: {(frames - f) / FPS:.1f} s of the body left unfilled after {k} shots")
            cap = avail[k]
            want = min(want, cap)
        nxt = f + want
        if beat_f:
            near = min(beat_f, key=lambda b: abs(b - nxt))
            if abs(near - nxt) <= 4 and near - f >= min(floor, want) and (cap is None or near - f <= cap):
                nxt = near
        if frames - nxt < least:  # the remainder is too short for a shot of its own
            if cap is None or frames - f <= cap:
                nxt = frames
            elif frames - least - f >= min(floor, cap):
                nxt = frames - least  # leave the next shot a proper length rather than overrun this one's footage
            elif frames - nxt <= floor:
                out.append(nxt - f)  # a few frames no shot can take: the caller gives them to the next card or the gap
                return out
        out.append(nxt - f)
        f = nxt
        k += 1
    return out


def _when(text):
    """((y, m, d) earliest, (y, m, d) latest) a caption or card speaks of: "28.7.1965", "10.1967", "cuối năm 1965" /
    "end of 1965", "từ 2.3.1965" / "since …" (open-ended), a bare year; None when it names no year."""
    t = (text or "").lower()
    since = re.search(r"\b(từ|since|from)\s+\d", t)
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.((?:18|19|20)\d\d)", t)
    if m:
        lo = (int(m[3]), int(m[2]), int(m[1]))
        return lo, (9999, 12, 31) if since else lo
    m = re.search(r"\b(\d{1,2})\.((?:18|19|20)\d\d)", t)
    if m:
        return (int(m[2]), int(m[1]), 1), (9999, 12, 31) if since else (int(m[2]), int(m[1]), 31)
    m = re.search(r"(cuối năm|cuối|end of)\s*((?:18|19|20)\d\d)", t)
    if m:
        return (int(m[2]), 12, 1), (int(m[2]), 12, 31)
    m = re.search(r"\b((?:18|19|20)\d\d)\b", t)
    return ((int(m[1]), 1, 1), (int(m[1]), 12, 31)) if m else None


def _hold(text, s=None):
    """Frames an overlay of `text` stays up: what both the audit and the delivery gate accept as readable
    (review.reading_frames). A given hold can lengthen it, never cut it below that: a 2.0 s counter with a 36-character
    label failed the gate at 55 of 64 frames, and at 2.43 s its nine words still failed the audit."""
    from .review import reading_frames
    return max(int(round(s * FPS)) if s else 0, reading_frames(text, FPS))


def _redact_bars(line, keep, font_id, size, weight, width_px):
    """[x0, x1] in px (from the line's left edge) of each word that is not kept, measured on the bundled glyphs."""
    from .design_library import layout_text
    words = line.split(" ")
    keep = {w.casefold().strip(".,:;") for k in keep for w in k.split()}
    bars, pos = [], ""
    for i, w in enumerate(words):
        start = layout_text(font_id, pos + "x", size, 4000, weight)["line_widths"][0] - layout_text(font_id, "x", size, 4000, weight)["line_widths"][0] if pos else 0.0
        end = layout_text(font_id, (pos + w) or "x", size, 4000, weight)["line_widths"][0]
        if w.casefold().strip(".,:;") not in keep and w.strip():
            bars.append([round(start - size * .08, 1), round(min(width_px, end + size * .08), 1)])
        pos += w + " "
    return bars


def archive_montage(t, q: ArchiveMontage):
    W, H = t.get("width", 1920), t.get("height", 1080)
    N = q.end_frame - q.start_frame
    A = lambda f: q.start_frame + f
    rng = random.Random(q.seed)
    gap, climax, sil = round(q.gap_s * FPS), round(q.climax_s * FPS), round(q.silence_s * FPS)
    title_n = round(q.title_s * FPS) if q.title else 0
    C = N - (climax + sil + title_n + 12) - (12 if q.ending == "whiteout" else 0)  # the hit
    body = C - gap
    notes = []

    def L(lid, kind, a, b, x, y, w, h, z, **kw):
        return {"op": "upsert_layer", "layer": {"id": f"{q.id}-{lid}", "kind": kind, "start_frame": A(a), "end_frame": A(b), "x": round(x, 4),
                                                "y": round(y, 4), "width": round(w, 4), "height": round(h, 4), "z": q.z + z, **kw}}

    def text(lid, s_, a, b, x, y, w, h, z, font_id="bevietnampro", size=34, weight=600, color=None, align="center", effects=(), **kw):
        return L(lid, "text", a, b, x, y, w, h, z, text=s_, font_id=font_id, font_size=size, font_weight=weight, color=color or q.ink,
                 data={"align": align}, effects=[{"name": "text_outline", "start_frame": 0, "end_frame": 1, "params": {"amount": 2, "color": "#0a0908"}},
                                                 {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 14}}, *effects], **kw)

    fade = lambda n, fi=6, fo=6: [{"name": "fade_in", "start_frame": 0, "end_frame": min(fi, n // 3)},
                                  {"name": "fade_out", "start_frame": max(0, n - fo), "end_frame": n - 1}]
    ops = [L("bg", "shape", 0, N, 0, 0, 1, 1, 0, color="#000000", data={"shape": "rectangle", "corner_radius": 0})]

    def scrim(lid, a, b, x, y, w, h, opacity=.55):
        """A soft dark field under small type: tracked capitals over a bright sky failed 3:1 in the first render."""
        return L(lid, "shape", a, b, x, y, w, h, 55, color="#000000", opacity=opacity, data={"shape": "rectangle", "corner_radius": 0},
                 effects=[{"name": "edge_feather", "start_frame": 0, "end_frame": 1, "params": {"amount": .3, "shape": "rect"}}, *fade(b - a, 6, 8)])
    sound = {"cuts": [], "flashes": [], "cards": [], "voices": [], "threats": []}

    # the full-frame cards take their time out of the body, the overlays do not
    full = sorted([c for c in q.cards if c.kind in ("headline", "redact")], key=lambda c: c.at)
    climax_shot = next(s for s in q.shots if s.role == "climax")
    footage = [s for s in q.shots if s is not climax_shot]
    unknown = [i for i, s in enumerate(footage) if s.kind == "archive" and not s.year]
    if unknown:
        notes.append(f"{len(unknown)} archive shot(s) without a year: check they belong to the story's years")
    # 1. the body: plan the slots around the full-frame cards, then fill them in order
    slots, f = [], 0
    card_spans = []
    for c in full:
        a = max(f, round(c.at * FPS))
        if 0 < a - f < 24:
            a = f  # a sliver of footage between two cards reads as a glitch: the cards run back to back
        if a >= body - 12:
            notes.append(f"{c.kind} card at {c.at:.1f} s dropped: no room before the hit")
            continue
        # a redacted document is read by the words left standing, not the lines struck out
        n = _hold(" ".join(c.keep or c.lines) if c.kind == "redact" else c.text, c.hold) + (18 if c.kind == "redact" else 8)
        if c.kind == "headline" and c.source:  # its source line comes up 8 frames in and must still be read
            n = max(n, 8 + _hold(c.source))
        card_spans.append((a, min(body, a + n), c))
        f = min(body, a + n)
    edges = [0] + [x for a, b, _ in card_spans for x in (a, b)] + [body]
    runs = [(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2) if edges[i + 1] - edges[i] > 0]
    used = 0
    body0 = body
    for a, b in runs:
        avail = [max(8, int((s.duration - .05) * FPS)) for s in footage[used:]]
        lens = rhythm(b - a, q.asl_start * (q.asl_end / q.asl_start) ** ((a / body0) ** q.curve), q.asl_end * 1.0 if b == body0 else
                      q.asl_start * (q.asl_end / q.asl_start) ** ((b / body0) ** q.curve), 1.0, q.seed + a, [x - a / FPS for x in q.beats if a / FPS <= x <= b / FPS],
                      avail=avail)
        f = a
        for n in lens:
            slots.append((f, f + n, footage[used]))
            f += n
            used += 1
        if f < b:  # frames no shot could take without overrunning its footage: the card after the run starts earlier,
            # or the black before the hit grows by them (never a one-frame shot: the first fix left one before a card)
            if b == body0:
                body = f
            else:
                card_spans = [(f if ca == b else ca, cb, c) for ca, cb, c in card_spans]
    years = [s.year for _, _, s in slots if s.year]
    back = [(i, y0, y1) for i, (y0, y1) in enumerate(zip(years, years[1:])) if y1 < y0]
    if back:
        notes.append(f"the footage's years go backwards {len(back)} time(s) (first: {back[0][1]} -> {back[0][2]}): a montage that walks through time keeps it moving forward")
    # projected frames: about projected_share of the footage, never three in a row, not the threats
    proj = set()
    run = 0
    for i, (a, b, s) in enumerate(slots):
        want = s.frame == "projected" or (s.frame == "auto" and s.role in ("calm", "news") and rng.random() < q.projected_share)
        if want and run < 2:
            proj.add(i)
            run += 1
        else:
            run = 0
    last_flash = -10 ** 6
    flow = lambda s_: {"frame_sampling": "flow"} if s_.fps and abs(s_.fps - FPS) > .5 else {}  # 23.976 fps repeated every 5th frame
    for i, (a, b, s) in enumerate(slots):
        n = b - a
        grade = [{"name": "contrast", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.03}}] + (
            [{"name": "saturate", "start_frame": 0, "end_frame": 1, "params": {"amount": s.saturation}}] if s.saturation != 1.0 else [])
        if i in proj:
            dx, dy = rng.uniform(-.015, .015), rng.uniform(-.012, .012)
            sc = rng.uniform(.78, .86)
            ops.append(L(f"s{i}", "video", a, b, (1 - sc) / 2 + dx, (1 - sc) / 2 + dy, sc, sc, 10, asset_id=s.asset_id, source_start=round(s.source_start, 3),
                         fit="cover", **flow(s), effects=[*grade, {"name": "rounded", "start_frame": 0, "end_frame": 1, "params": {"amount": 22}},
                                               {"name": "vignette", "start_frame": 0, "end_frame": 1, "params": {"amount": .55}},
                                               {"name": "gate_weave", "start_frame": 0, "end_frame": n, "params": {"amount": .8, "frequency": 12, "seed": q.seed + i}}]))
        else:
            fx = [*grade] + ([{"name": "zoom_in", "start_frame": 0, "end_frame": n - 1, "easing": "linear", "params": {"amount": .04}}] if n >= 45 else [])
            ops.append(L(f"s{i}", "video", a, b, 0, 0, 1, 1, 10, asset_id=s.asset_id, source_start=round(s.source_start, 3), fit="cover", **flow(s), effects=fx))
        sound["cuts"].append(A(a))
        if s.role == "threat" and (i == 0 or slots[i - 1][2].role != "threat"):
            sound["threats"].append(A(a))
        if s.sound:
            sound["voices"].append({"asset_id": s.asset_id, "source_start": s.source_start, "start": A(a),
                                    "end": A(max(b, a + round(min(s.voice_s or 0, s.duration) * FPS)))})
        # a leader frame on the cut: warm, one or two frames, spaced (the PSE gate allows three flashes a second)
        if q.flash == "leader" and i > 0 and a - last_flash >= q.flash_gap_s * FPS and a > body * .25 and rng.random() < .55:
            k = 2 if rng.random() < .4 else 1
            ops.append(L(f"lead{i}", "shape", a, a + k, 0, 0, 1, 1, 30, color=rng.choice(LEADER), opacity=.82, blend="screen",
                         data={"shape": "rectangle", "corner_radius": 0}))
            sound["flashes"].append(A(a))
            last_flash = a

    # 2. type: ONE line of text on screen at a time (dates, teletype, counters, quotes), as the references keep it; a
    # date belongs to its own shot (skipped when it cannot start there), an overlay waits its turn and never runs into a
    # full-frame card (it moves past the card, or is dropped with a note)
    def card_at(f_):
        return next(((ca, cb) for ca, cb, _ in card_spans if ca <= f_ < cb), None)

    def next_card(f_):
        return next(((ca, cb) for ca, cb, _ in card_spans if ca >= f_), None)
    events = []
    last_txt = ""
    withheld = 0
    for i, (a, b, s) in enumerate(slots):
        txt = " · ".join(x for x in (s.date, s.place.upper()) if x)
        if txt and s.date_source != "own":
            withheld += txt != last_txt
            last_txt = txt
            continue  # a compilation's date is its claim, not the footage's: no caption
        if txt and txt != last_txt:
            # the date may wait through its event: the shots after it that carry no date of their own
            j = i
            while j + 1 < len(slots) and not slots[j + 1][2].date and (slots[j + 1][0] - slots[j][1] <= 2 or any(
                    ca <= slots[j][1] + 2 and cb >= slots[j + 1][0] - 2 for ca, cb, _ in card_spans)):  # a card between two shots of one event
                j += 1
            n = max(60, _hold(txt))  # the whole caption stays over its own event: it ran 4 frames into Tay Ninh's
            events.append({"kind": "date", "at": a, "latest": slots[j][1] - n, "n": n, "text": txt, "i": i})
            last_txt = txt
    for i, (a, b, s) in enumerate(slots):
        if s.says:  # a voice on the record gets its words on screen while it speaks, before anything else
            spoken = max(b, a + round(min(s.voice_s or 0, s.duration) * FPS)) - a
            n = max(spoken, _hold(s.says) + 6, 6 + _hold(s.says_by) if s.says_by else 0)
            line = SimpleNamespace(kind="quote", text=s.says, source=s.says_by)
            events.append({"kind": "say", "at": a, "latest": a + 6, "n": n, "card": line, "j": f"v{i}", "typed": 0, "year": None})
    for j, c in enumerate(q.cards):
        if c.kind in ("teletype", "counter", "quote"):
            typed = int(len(c.text) / 24 * FPS) if c.kind == "teletype" else 0
            n = typed + _hold(c.text, c.hold) if c.kind != "counter" else max(_hold(c.text, c.hold), 60)
            if c.source:  # the source line comes in a few frames late and must still be readable
                n = max(n, 6 + _hold(c.source))
            yrs = re.findall(r"(?:18|19|20)\d\d", c.text) or re.findall(r"(?:18|19|20)\d\d", c.source)
            events.append({"kind": c.kind, "at": round(c.at * FPS), "latest": body - n, "n": n, "card": c, "j": j, "typed": typed,
                           "year": int(yrs[-1]) if yrs else None, "when": _when(c.text) or _when(c.source)})
    if withheld:
        notes.append(f"{withheld} date caption(s) withheld: their date comes from a compilation, not the footage")
    events.sort(key=lambda e: (e["at"], {"say": 0, "date": 1}.get(e["kind"], 2)))
    dated = [(a_, _when(s_.date)) for a_, b_, s_ in slots if _when(s_.date)]

    def in_order(st, n, when):
        """A dated card falls between the dates of the footage before and after it: "end of 1965: 184,300" over
        carriers of 11.2.1965, before "15.4.1965 · Huế", read as 184,300 by February."""
        if not when:
            return True
        before = [w for a_, w in dated if a_ <= st]
        after = [w for a_, w in dated if a_ > st]  # a caption that comes up while the card is still on is read after it
        return (not before or before[-1][0] <= when[1]) and (not after or when[0] <= after[0][1])

    def of_its_year(st, n, yr):
        """A dated card sits only over footage shot that year (a 28.7.1965 quote over undated compilation helicopters
        claimed them for 1965)."""
        if yr is None:
            return True
        under = [s_ for a_, b_, s_ in slots if a_ < st + n and b_ > st]
        return bool(under) and all(s_.year == yr or (s_.year is None and q.allow_undated) for s_ in under)
    busy, placed = [], []  # lines already placed: one on screen at a time, 6 frames apart

    def clash(st, n):
        return next((b_ for a_, b_ in busy if st < b_ + 6 and a_ < st + n + 6), None)
    for e in sorted(events, key=lambda e: e["kind"] != "say"):  # a voice has one moment: its words are placed first
        found, steps, cand = None, 0, e["at"]
        while cand <= e["latest"]:
            st, steps = cand, 0
            for _ in range(len(card_spans) + 1):  # step past a full-frame card the line would touch
                inside, nc = card_at(st), next_card(st)
                if inside:
                    st, steps = inside[1] + 4, steps + 1
                elif nc and nc[0] < st + e["n"]:
                    st, steps = nc[1] + 4, steps + 1
                else:
                    break
            # an overlay moved past more than one card would land in another chapter of the story
            if st > e["latest"] or st + e["n"] > body or (e["kind"] != "date" and steps > 1):
                break
            end = clash(st, e["n"])
            if end is not None:
                cand = end + 6
                continue
            if e["kind"] in ("date", "say") or (of_its_year(st, e["n"], e.get("year")) and in_order(st, e["n"], e.get("when"))):
                found = st
                break
            cand = st + 3
        if found is None:
            why = ("its footage ends" if e["kind"] == "date" else "its voice starts" if e["kind"] == "say" else
                   f"no free stretch of {e['year']} footage between captions dated around it" if e.get("year") else "the hit")
            notes.append(f"{e['kind']} '{(e.get('text') or e['card'].text)[:30]}' dropped: no free time for it before {why}")
            continue
        placed.append((found, e))
        busy.append((found, found + e["n"]))
    for st, e in placed:
        n = e["n"]
        if e["kind"] == "date":
            txt = e["text"]
            w = min(.9, (len(txt) * 36 * .78 + 160) / W)
            ops.append(scrim(f"date{e['i']}sc", st, st + n, (1 - w) / 2 - .06, .80 - .035, w + .12, .13))
            ops.append(text(f"date{e['i']}", txt.upper(), st, st + n, (1 - w) / 2, .80, w, .06, 60, size=32, weight=600, color=q.accent,
                            effects=fade(n, 5, 8) + [{"name": "tracking", "start_frame": 0, "end_frame": n - 1, "easing": "ease_out",
                                                      "params": {"amount": .32, "from_em": .5, "center": True}}]))
            sound["cards"].append({"kind": "date", "start": A(st), "end": A(st + n)})
            continue
        c, j = e["card"], e["j"]
        if c.kind == "teletype":
            from .design_library import fit_width
            ops.append(L(f"tt{j}", "text", st, st + n, .06, .12, min(.88, fit_width("ibmplexmono", c.text.upper(), 30, W, 500) + .02), .06, 70,
                         text=c.text.upper(), font_id="ibmplexmono", font_size=30, font_weight=500, color="#e9e2d0", background="#0b0a09cc",
                         data={"align": "left"},
                         effects=[{"name": "typewriter", "start_frame": 0, "end_frame": n - 1, "params": {"cps": 24, "cursor": True, "cursor_color": q.accent}},
                                  {"name": "fade_out", "start_frame": n - 5, "end_frame": n - 1}]))
            sound["cards"].append({"kind": "teletype", "start": A(st), "end": A(st + e["typed"]), "chars": len(c.text)})
        elif c.kind == "counter":
            ops.append(scrim(f"cl{j}sc", st, st + n, -.04, -.04, .6, .36, .72))
            ops.append(text(f"cl{j}", c.text.upper(), st, st + n, .06, .07, .6, .05, 70, size=28, weight=600, color=q.accent, align="left",
                            effects=fade(n, 5, 6) + [{"name": "tracking", "start_frame": 0, "end_frame": 1, "params": {"amount": .18, "from_em": .18, "center": False}}]))
            ops.append(L(f"cn{j}", "counter", st, st + n, .06, .12, .6, .11, 70, font_id="oswald", font_size=92, font_weight=600, color=q.ink,
                         data={"from": c.value_from, "to": c.value_to, "decimals": 0, "group": ".", "prefix": "", "suffix": c.suffix, "align": "left"},
                         effects=[{"name": "progress", "start_frame": 0, "end_frame": min(n - 10, 40), "easing": "ease_out"},
                                  {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 16}}, *fade(n, 4, 6)]))
            if c.source:
                ops.append(text(f"cs{j}", c.source, st + 6, st + n, .06, .235, .6, .04, 70, size=26, weight=500, color="#ddd4c4", align="left",
                                effects=fade(n - 6, 6, 6)))
            sound["cards"].append({"kind": "counter", "start": A(st), "end": A(st + min(n - 10, 40))})
        else:  # quote: a voice on the record, small, lower left, with who said it
            ops.append(scrim(f"q{j}sc", st, st + n, -.04, .72, .74, .30, .6))
            ops.append(text(f"q{j}", f"“{c.text}”", st, st + n, .06, .78, .62, .09, 70, font_id="notoserif", size=32, weight=500, align="left",
                            effects=fade(n, 6, 6)))
            if c.source:
                ops.append(text(f"qs{j}", c.source.upper(), st + 4, st + n, .06, .87, .62, .04, 70, size=26, weight=600, color=q.accent, align="left",
                                effects=fade(n - 4, 6, 6)))
            sound["cards"].append({"kind": "quote", "start": A(st), "end": A(st + n)})

    # full-frame cards (and a stamp lands on the document under it, below its lines)
    for j, (a, b, c) in enumerate(card_spans):
        n = b - a
        if c.kind == "headline":
            ops.append(L(f"h{j}bg", "shape", a, b, 0, 0, 1, 1, 40, color="#0c0b0a", data={"shape": "rectangle", "corner_radius": 0},
                         effects=[{"name": "paper_grain", "start_frame": 0, "end_frame": 1, "params": {"amount": .1, "seed": q.seed}}]))
            from .design_library import fit_size
            size = fit_size("oswald", c.text.upper(), .86, W, 700, start=150, minimum=48)
            ops.append(text(f"h{j}", c.text.upper(), a, b, .05, .5 - size * 1.25 / H / 2, .9, size * 1.4 / H, 41, font_id="oswald", size=size, weight=700,
                            effects=[{"name": "impact_zoom", "start_frame": 0, "end_frame": 6, "params": {"amount": .07}},
                                     {"name": "fade_out", "start_frame": n - 4, "end_frame": n - 1}]))
            if c.source:
                ops.append(text(f"h{j}src", c.source, a + 8, b, .05, .5 + size * .8 / H, .9, .05, 41, size=28, weight=500, color="#b8ad98",
                                effects=fade(n - 8, 6, 4)))
            sound["cards"].append({"kind": "headline", "start": A(a), "end": A(b)})
        else:  # redact: the document on paper, every word struck out except the kept ones, line by line
            ops.append(L(f"r{j}bg", "shape", a, b, 0, 0, 1, 1, 40, color="#d9cfb8", data={"shape": "rectangle", "corner_radius": 0},
                         effects=[{"name": "paper_grain", "start_frame": 0, "end_frame": 1, "params": {"amount": .18, "seed": q.seed}},
                                  {"name": "vignette", "start_frame": 0, "end_frame": 1, "params": {"amount": .6}},
                                  {"name": "zoom_in", "start_frame": 0, "end_frame": n - 1, "easing": "linear", "params": {"amount": .12}},
                                  {"name": "pan_x", "start_frame": 0, "end_frame": n - 1, "easing": "linear", "params": {"amount": -24}}]))
            size, lh = 40, 1.6
            x0, y0 = .12, .5 - len(c.lines) * size * lh / H / 2
            for li, line in enumerate(c.lines):
                y = y0 + li * size * lh / H
                ops.append(L(f"r{j}l{li}", "text", a, b, x0, y, .8, size * 1.5 / H, 41, text=line, font_id="ibmplexmono", font_size=size, font_weight=500,
                             color="#1c1a17", data={"align": "left"}, effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 4}]))
                bars = _redact_bars(line, c.keep, "ibmplexmono", size, 500, .8 * W)  # an unplated text layer has no padding (effects.js)
                if bars:
                    t0 = 10 + li * 6  # each line's bars sweep in, one line after another
                    els = [{"id": f"b{bi}", "type": "rect", "x": round(bx0, 1), "y": 6, "width": round(bx1 - bx0, 1), "height": round(size * 1.1, 1),
                            "fill": "#0d0c0b", "stroke": "none"} for bi, (bx0, bx1) in enumerate(bars)]
                    ops.append(L(f"r{j}b{li}", "svg", a + t0, b, x0, y, .8, size * 1.5 / H, 42,
                                 data={"view_box": [round(.8 * W), round(size * 1.5)], "elements": els},
                                 effects=[{"name": "wipe_right", "start_frame": 0, "end_frame": 8, "easing": "ease_out"}]))
            sound["cards"].append({"kind": "redact", "start": A(a), "end": A(b), "bars_at": [A(a + 10 + li * 6) for li in range(len(c.lines))]})
            doc_bottom = y0 + len(c.lines) * size * lh / H
            for jj, sc_ in enumerate(x for x in q.cards if x.kind == "stamp"):
                sa = round(sc_.at * FPS)
                if not a <= sa < b - 12:
                    continue
                sn = min(b - sa, _hold(sc_.text, sc_.hold) + 12)
                ssize = 68  # display size: WCAG asks 3:1 there, and red ink on paper gives 3.9
                w = min(.6, (len(sc_.text) * ssize * .62 + 120) / W)
                ops.append(L(f"st{j}-{jj}", "text", sa, sa + sn, min(.52, .95 - w), min(.86, doc_bottom + .04), w, ssize * 1.7 / H, 70, text=sc_.text.upper(),
                             font_id="oswald", font_size=ssize, font_weight=700, color=q.stamp_color, rotation=-7, background="transparent",
                             data={"align": "center"},
                             effects=[{"name": "border", "start_frame": 0, "end_frame": 1, "params": {"amount": 5, "color": q.stamp_color}},
                                      {"name": "impact_zoom", "start_frame": 0, "end_frame": 5, "params": {"amount": .35}},
                                      {"name": "paper_grain", "start_frame": 0, "end_frame": 1, "params": {"amount": .25, "seed": q.seed + jj}},
                                      {"name": "fade_out", "start_frame": sn - 5, "end_frame": sn - 1}], opacity=.9))
                sound["cards"].append({"kind": "stamp", "start": A(sa), "end": A(sa + sn)})
    stamps_on_docs = {round(x.at * FPS) for x in q.cards if x.kind == "stamp" and any(ca <= round(x.at * FPS) < cb - 12 for ca, cb, c in card_spans if c.kind == "redact")}
    for x in q.cards:
        if x.kind == "stamp" and round(x.at * FPS) not in stamps_on_docs:
            notes.append(f"stamp '{x.text[:24]}' dropped: a stamp lands on a redacted document, and none is on screen at {x.at:.1f} s")

    # 3. the gap (true black, silent), then the hit on the climax picture
    hold_src = min(climax, int((climax_shot.duration - .05) * FPS))
    cgrade = [{"name": "contrast", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.06}}]
    ops.append(L("climax", "video", C, C + hold_src, 0, 0, 1, 1, 10, asset_id=climax_shot.asset_id, source_start=round(climax_shot.source_start, 3), fit="cover",
                 effects=[*cgrade, {"name": "white_flash", "start_frame": 0, "end_frame": 2, "params": {"amount": .75}},
                          {"name": "zoom_in", "start_frame": 0, "end_frame": hold_src - 1, "easing": "ease_out", "params": {"amount": .06}}]))
    end_climax = C + hold_src
    # the gap is the editor's black, the end card a held picture: declared, so the delivery gates read them as meant
    ops.append(L("gap-intent", "null", body, C, 0, 0, 1, 1, 0, data={"intent": "deliberate_black"}))
    # grain in overlay (blacks stay black: in normal blend it lifted the gap to RGB 42) over the body and the climax,
    # never over the gap or the end card: one film for footage from many sources, and the dither that breaks the banding
    # of compressed dark archive (CAMBI ran 75 frames over 5 on a smoky 1964 reel)
    if q.grain:
        for gid, ga, gb in (("grain", 0, body), ("grain-hit", C, end_climax)):
            ops.append(L(gid, "film", ga, gb, 0, 0, 1, 1, 50, blend="overlay", data={"type": "grain", "intensity": q.grain, "seed": q.seed, "gauge": 16}))
            # overlay leaves deep shadows untouched, so the banding of a dark compressed reel came back (CAMBI 14 frames on
            # a B-52 at dawn): a faint normal grain dithers them (it lifts black by a few levels, never in the gap)
            ops.append(L(gid + "-dither", "film", ga, gb, 0, 0, 1, 1, 49, opacity=.09,  # coarse enough to survive the encode
                         data={"type": "grain", "intensity": 1.0, "seed": q.seed + 1, "gauge": 16}))
    # 4. the end
    if q.ending == "whiteout":
        out_a = end_climax - 10
        ops.append(L("white", "shape", out_a, N, 0, 0, 1, 1, 80, color="#ece6da", data={"shape": "rectangle", "corner_radius": 0},
                     effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "fade_out", "start_frame": N - out_a - 14, "end_frame": N - out_a - 1}]))
        title_color = "#1d1b18"
    elif q.ending == "drain":
        next(o for o in ops if o["layer"]["id"] == f"{q.id}-climax")["layer"]["effects"].append(
            {"name": "fade_out", "start_frame": max(0, hold_src - 30), "end_frame": hold_src - 1})
        title_color = q.ink
    else:
        title_color = q.ink
    tt = None
    if q.title:
        tt = end_climax + sil
        size = 40
        w = min(.9, (len(q.title) * size * .95 + 200) / W)
        ops.append(L("title", "text", tt, tt + title_n, (1 - w) / 2, .47, w, .07, 90, text=q.title.upper(), font_id="bevietnampro", font_size=size,
                     font_weight=500, color=title_color, data={"align": "center"},
                     effects=[{"name": "fade_in", "start_frame": 0, "end_frame": 10},
                              {"name": "tracking", "start_frame": 0, "end_frame": title_n - 1, "easing": "linear", "params": {"amount": .42, "from_em": .3, "center": True}},
                              {"name": "fade_out", "start_frame": title_n - 10, "end_frame": title_n - 1}]))
    ops.append(L("end-intent", "null", end_climax, N, 0, 0, 1, 1, 0, data={"intent": "deliberate_still"}))
    sound.update({"suck_out": [A(max(0, body - 24)), A(body)], "hit": A(C), "climax_end": A(end_climax), "silence": [A(end_climax), A(tt if tt is not None else N)],
                  "title": A(tt) if tt is not None else None, "end": A(N), "body": [A(0), A(body)]})
    shot_lens = [b - a for a, b, _ in slots]
    thirds = [round(sum(1 for a, b, _ in slots if lo <= a < hi) and (hi - lo) / FPS / sum(1 for a, b, _ in slots if lo <= a < hi), 2)
              for lo, hi in ((0, body / 3), (body / 3, 2 * body / 3), (2 * body / 3, body))]
    if used < len(footage):
        notes.append(f"{len(footage) - used} footage shot(s) unused")
    return {"ops": ops, "notes": notes,
            "inspect_frames": [A(slots[0][0] + 10), A(body // 2), A(body - 20), A(C + 4), A(min(N - 1, (tt or end_climax) + 20))],
            "sound_plan": sound,
            "measurements": {"shots": len(slots), "asl_by_thirds_s": thirds, "shortest_s": round(min(shot_lens) / FPS, 2),
                             "projected": len(proj), "leader_frames": len(sound["flashes"]), "cards": len(q.cards), "hit_s": round(C / FPS, 2),
                             "gap_s": round(gap / FPS, 2), "silence_s": round(sil / FPS, 2), "text_lines": len(placed)},
            "verify": "snapshot a projected frame, a date super, each card and the hit; play the moving cut: the rhythm should tighten, "
                      "the dates walk forward, the black before the hit is silent and black; run review.delivery_gates and montage.arc."}


def score(plan, fps=FPS, music=None, seed=7):
    """Procedural sound for an archive_montage sound_plan, as clips to import and place: {"path" | "asset_id",
    "start_frame", "end_frame", "volume", "role", "fade_in", "fade_out", "treatment"?, "source_start"?}. Frames are
    timeline frames.

    Layers (reports/Montage tư liệu kiểu bom tấn.md, sound): a low drone rising under the body; a clock pulse from the
    body's second third that quickens to the hit (Chernobyl's dosimeter, WWZ's metronome); a Shepard riser over the last
    third that stops dead; a braam on the first threat shot of each run (at most three); a typewriter under each
    teletype line, a stamp hit, a hit under each headline; the suck-out into the gap; silence in the gap (a weaker sound
    30-500 ms before a loud one blunts the startle); the hit (braam + impact + sub drop) on the climax; a tinnitus ring
    over the climax; silence; a low swell under the title. The archive's own voices come through a radio filter, low,
    and only in the first two thirds. The cue and the drone RISE by thirds (three overlapping copies of the same sound
    at rising gains, crossfaded: a clip has one volume), so the last third is the loudest and the hit still clears it.
    music: {"path", "source_start", "volume"?} of a cue whose build should end at the suck-out: it is cut dead there.
    Check the mix with arc(video, plan)."""
    from . import sound as snd
    out = []
    b0, b1 = plan["body"]
    hit, so = plan["hit"], plan["suck_out"][0]
    s = lambda f: f / fps
    n_ = [0]

    def design(kind, d, **kw):
        n_[0] += 1  # a seed per sound: two braams are two braams, not one copied
        cap = 60 if kind in snd.BEDS else 12
        return snd.design(kind, round(max(.08, min(d, cap)), 3), seed + n_[0], **kw)

    def add(kind, a, b, vol=1.0, fi=.05, fo=.05, role="sfx", **kw):
        r = design(kind, s(b - a), **kw)
        out.append({"path": r["path"], "kind": kind, "start_frame": a, "end_frame": min(b, a + round(r["duration"] * fps)), "volume": vol, "role": role,
                    "fade_in": fi, "fade_out": fo, "peak_s": r.get("peak_s", 0)})
        return r

    def rising(path, kind, a, b, gains, role, fi, fo, src=0.0, xf=24):
        """One sound over [a, b) in len(gains) overlapping copies at rising gains, crossfaded over xf frames."""
        k = len(gains)
        cuts = [a + (b - a) * i // k for i in range(k + 1)]
        for i, g in enumerate(gains):
            sa, sb = max(a, cuts[i] - (xf // 2 if i else 0)), min(b, cuts[i + 1] + (xf // 2 if i < k - 1 else 0))
            out.append({"path": path, "kind": kind, "start_frame": sa, "end_frame": sb, "source_start": round(src + (sa - a) / fps, 3), "volume": g,
                        "role": role, "fade_in": fi if i == 0 else xf / fps, "fade_out": fo if i == k - 1 else xf / fps})

    # the drone: beds are at most 60 s, so a long body chains them
    a = b0
    while a < so:
        e = min(so, a + 58 * fps)
        r = design("drone", s(e - a) + .5, gain_db=-20)
        rising(r["path"], "drone", a, e, [.45, .65, .9] if a == b0 else [.9], "ambience", min(4.0, s(e - a) * .3) if a == b0 else .6, .3)
        a = e
    # the clock and the riser accelerate INTO the suck-out: a bed is at most 60 s, so a long body starts them later rather
    # than letting them stop early (on a 125 s montage the clock had ended 16.8 s before the suck-out)
    cap = 59 * fps
    third = max(b0 + (b1 - b0) // 3, so - cap)
    add("clock", third, so, vol=.6, fi=1.0, fo=.02, bpm=120, end_bpm=360, gain_db=-20)
    sh0 = max(b0 + 2 * (b1 - b0) // 3, so - cap)
    add("shepard", sh0, so, vol=.6, fi=1.5, fo=.002, bpm=110, end_bpm=170, gain_db=-18)
    for k in ("clock", "shepard"):
        late = next(c for c in out if c.get("kind") == k)
        if so - late["end_frame"] > 2:
            raise ValueError(f"the {k} stops {s(so - late['end_frame']):.1f} s before the suck-out")
    for f in plan["threats"][:3]:
        if f < so - 7 * fps:  # the last seconds belong to the riser and the clock: a braam there flattens the hit
            add("braam", f, f + 75, vol=.7, fi=.005, fo=.6, gain_db=-12)
    for c in plan["cards"]:
        if c["kind"] == "teletype":
            add("typewriter", c["start"], max(c["end"], c["start"] + 12), vol=.55, fi=.01, fo=.05, gain_db=-20)
        elif c["kind"] == "stamp":
            add("impact", c["start"], c["start"] + 18, vol=.85, fi=.001, fo=.1, gain_db=-12)
        elif c["kind"] == "headline":
            add("impact", c["start"], c["start"] + 24, vol=.9, fi=.001, fo=.15, gain_db=-10)
            add("sub_drop", c["start"], c["start"] + 36, vol=.75, fi=.001, fo=.2, gain_db=-12)
        elif c["kind"] == "redact":
            for f in c.get("bars_at", []):
                add("shutter", f, f + 6, vol=.45, fi=.001, fo=.02, gain_db=-18)
    # the suck-out ends where the gap begins; nothing sounds in the gap
    add("suck_out", plan["suck_out"][0], plan["suck_out"][1], vol=.9, fi=.01, fo=.002, gain_db=-12)
    add("braam", hit, hit + 90, vol=1.0, fi=.002, fo=.8, gain_db=-4)
    add("impact", hit, hit + 30, vol=1.0, fi=.001, fo=.2, gain_db=-4)
    add("sub_drop", hit, hit + 60, vol=1.0, fi=.001, fo=.4, gain_db=-5)
    # body under the hit's first second: a second braam (its own seed, so the two beat against each other) and debris;
    # an impact alone decays in 0.2 s and left the hit 5 dB over the build
    add("braam", hit, hit + 75, vol=1.0, fi=.002, fo=.7, gain_db=-5)
    add("crunch", hit + 2, hit + 40, vol=.9, fi=.002, fo=.3, gain_db=-6)
    add("tinnitus", hit + 6, plan["climax_end"], vol=.35, fi=.3, fo=.4, gain_db=-24)
    if plan.get("title"):
        add("drone", plan["title"], min(plan["end"], plan["title"] + 4 * fps), vol=.5, fi=1.2, fo=1.0, role="ambience", gain_db=-24)
    for v in plan["voices"]:  # the period's own voices: a texture under the first two thirds, never louder than the cue
        if v["start"] < sh0:
            out.append({"asset_id": v["asset_id"], "source_start": v["source_start"], "start_frame": v["start"], "end_frame": min(v["end"] + 12, sh0),
                        "volume": .3, "role": "sfx", "fade_in": .04, "fade_out": .15, "treatment": "radio"})
    if music:
        v = music.get("volume", .85)
        src = music.get("source_start", 0.0)
        level = _loudness(music["path"], src, s(so + 6 - b0), 6)
        if level:  # a straight climb from the cue's opening level to its loudest, whatever the cue does in between
            top = max(level)
            want = [level[0] + (top - level[0]) * (i + 1) / len(level) for i in range(len(level))]
            gains = [round(v * min(1.0, max(.2, 10 ** ((w - m) / 20) * .7)), 3) for w, m in zip(want, level)]
        else:
            gains = [v * .45, v * .6, v * .7]
        rising(music["path"], "music", b0, so + 6, gains, "music", music.get("fade_in", .5), .03, src)
    return out


def _loudness(path, start, seconds, k):
    """Mean momentary loudness (LUFS) of k equal parts of a stretch of a file; None when it cannot be read."""
    import subprocess
    import numpy as np
    from .media import FFMPEG
    r = subprocess.run([FFMPEG, "-v", "info", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace").stderr
    m = [(float(a), float(b)) for a, b in re.findall(r"t:\s*([\d.]+)\s+TARGET.*?M:\s*([-\d.]+)", r)]
    if not m:
        return None
    out = []
    for i in range(k):
        v = [b for a, b in m if seconds * i / k <= a < seconds * (i + 1) / k and b > -70]
        out.append(float(np.mean(v)) if v else -70.0)
    return out


def arc(video, plan, fps=FPS):
    """The mix's shape, measured on the render (RMS dB): the body by thirds, its last 5 s, the hit's first 0.8 s and the
    gap. A dread montage climbs (each third at least as loud as the one before, 1 dB of slack) and the hit clears the
    last 5 s by 8 dB. Returns {"thirds", "last5", "hit", "gap", "rises", "hit_margin", "pass"}."""
    import subprocess
    import numpy as np
    from .media import FFMPEG
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    db = lambda a, b: round(float(20 * np.log10(max(1e-9, np.sqrt(np.mean(x[int(a / fps * 16000):int(b / fps * 16000)] ** 2) if b > a else 0)))), 1)
    b0, b1 = plan["body"]
    so = plan["suck_out"][0]
    th = [db(b0 + (b1 - b0) * i // 3, b0 + (b1 - b0) * (i + 1) // 3 if i < 2 else so) for i in range(3)]
    last5, hit, gap = db(so - 5 * fps, so), db(plan["hit"], plan["hit"] + round(.8 * fps)), db(b1, plan["hit"])
    rises = th[1] >= th[0] - 1 and th[2] >= th[1] - 1 and last5 >= th[2] - 1  # no sag into the hit (a 3 dB dip hid inside the last third)
    return {"thirds": th, "last5": last5, "hit": hit, "gap": gap, "rises": rises, "hit_margin": round(hit - last5, 1),
            "pass": bool(rises and hit - last5 >= 8 and gap <= -60)}
