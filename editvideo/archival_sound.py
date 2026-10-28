"""Four layers of sound for silent archive (reports/Nâng cấp 3D phim tài liệu.md, P1-9). Jacob Ribicoff, sound designer
of The Vietnam War, found almost no usable sound in the footage and rebuilt it: the first layer always repeats what the
picture shows; the place under it; sound "smudged" and kept low where the picture is degraded; tone and echo only where
the footage itself is chaos.

1. literal: the events the caller saw in the frames (a helicopter crossing, a gun firing, surf, a crowd), placed at
   their frame, near or far;
2. ambience: the place, one bed across consecutive shots of the same place, so the cut does not cut the air;
3. degraded: both pass through the "archival" treatment (an optical track's band and wow) when the picture is old or
   worn; poor footage is quieter still;
4. abstract: a drone, a heartbeat, a projector or a ring, only at the moments the caller names.
plan() returns clips to import and place (procedural, no third-party rights; say "synthesized" in the credits). It does
not look at the picture: the caller reads the frames and names the events.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

FPS = 30
LITERAL = ("helicopter", "jet", "artillery", "gunfire", "waves", "crowd", "typewriter", "morse", "siren", "impact", "whoosh", "rain", "wind")
PLACE = ("forest", "rain", "wind", "waves", "crowd", "room_tone", "ambient")
ABSTRACT = ("drone", "heartbeat", "tinnitus", "projector", "shepard", "clock")
DIST = {"near": (1.0, None), "mid": (.6, None), "far": (.4, "distant")}
FIDELITY = {"clean": 1.0, "worn": .8, "poor": .6}


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[LITERAL]
    at: float = Field(default=0, ge=0)            # seconds into the shot
    seconds: float | None = Field(default=None, gt=.1, le=60)  # default: to the end of the shot
    distance: Literal["near", "mid", "far"] = "mid"


class ShotSound(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_frame: int = Field(ge=0)
    end_frame: int
    events: list[Event] = Field(default_factory=list, max_length=12)
    place: Literal[PLACE] | None = None
    year: int = Field(default=1965, ge=1880, le=2030)
    fidelity: Literal["clean", "worn", "poor"] = "worn"


class Moment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[ABSTRACT]
    start_frame: int = Field(ge=0)
    end_frame: int


def _aged(sh):
    return sh.year < 1985 or sh.fidelity != "clean"


def plan(shots, moments=(), seed=7):
    """Clips for the four layers: [{"path", "kind", "layer", "start_frame", "end_frame", "volume", "role", "fade_in",
    "fade_out", "treatment"?}]. shots: ShotSound dicts in timeline order; moments: abstract Moment dicts."""
    from . import sound
    shots = [ShotSound.model_validate(s) for s in shots]
    moments = [Moment.model_validate(m) for m in moments]
    out = []

    def clip(kind, a, b, layer, vol, role, treat=None, fi=.08, fo=.12, gain=-18, **kw):
        d = max(.12, (b - a) / FPS)
        cap = 60 if kind in sound.BEDS else 12
        r = sound.design(kind, round(min(d, cap), 3), seed + len(out), gain_db=gain, **kw)
        out.append({"path": r["path"], "kind": kind, "layer": layer, "start_frame": a, "end_frame": a + round(r["duration"] * FPS), "volume": round(vol, 3),
                    "role": role, "fade_in": fi, "fade_out": fo, **({"treatment": treat} if treat else {})})

    for sh in shots:  # 1 + 3: the literal layer, aged with the picture
        n = sh.end_frame - sh.start_frame
        for e in sh.events:
            a = sh.start_frame + round(e.at * FPS)
            b = min(sh.end_frame + 12, a + (round(e.seconds * FPS) if e.seconds else n))
            vol, treat = DIST[e.distance]
            treat = treat or ("archival" if _aged(sh) else None)
            clip(e.kind, a, b, "literal", vol * FIDELITY[sh.fidelity], "foley", treat, fi=.005 if e.kind in ("artillery", "impact") else .08)
    i = 0  # 2 + 3: one bed per run of shots in the same place
    while i < len(shots):
        sh = shots[i]
        j = i
        while j + 1 < len(shots) and shots[j + 1].place == sh.place and shots[j + 1].start_frame - shots[j].end_frame <= 2:
            j += 1
        if sh.place:
            a, b = sh.start_frame, shots[j].end_frame
            k = 0
            while a < b:  # a bed is at most 60 s: chain them
                e = min(b, a + 60 * FPS)
                clip(sh.place, a, e, "ambience", .7 * FIDELITY[sh.fidelity], "ambience", "archival" if _aged(sh) else None, fi=.6 if k == 0 else .3,
                     fo=.6 if e == b else .3, gain=-22)
                a, k = e, k + 1
        i = j + 1
    for m in moments:  # 4: only where asked
        clip(m.kind, m.start_frame, m.end_frame, "abstract", .5, "ambience" if m.kind in ("drone", "projector") else "sfx", None, fi=.8, fo=.8, gain=-24)
    return out


def coverage(shots, clips):
    """Shots of silent archive that the plan leaves without a literal event or a place: Ribicoff's floor is both."""
    shots = [ShotSound.model_validate(s) for s in shots]
    gaps = []
    for k, sh in enumerate(shots):
        # a literal sound belongs to the shot it starts in (a gun's echo running into the next shot is not that shot's own)
        has = lambda layer: any(c["layer"] == layer and c["start_frame"] < sh.end_frame and
                                (sh.start_frame <= c["start_frame"] if layer == "literal" else c["end_frame"] > sh.start_frame) for c in clips)
        missing = [x for x, ok in (("literal", has("literal")), ("ambience", has("ambience"))) if not ok]
        if missing:
            gaps.append({"shot": k, "frames": [sh.start_frame, sh.end_frame], "missing": missing})
    return gaps
