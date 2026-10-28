"""Structured, frame-addressed vector illustration: maps, routes, diagrams and labels that draw themselves.

Elements are declarative (no raw SVG/script). Timing ranges are local layer frames [start, end].
draw: stroke reveals along its length; appear: fade+scale in; fill_in: fill fades in; follower: a dot
that travels along a polyline route; arrow: a line whose heads ride its growing tips (from the start or outward from
the middle, e.g. dimension lines); ripple: rings expand and fade from a circle. Rendered identically by Remotion and
Hyperframes via effects.js.
"""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

COLOR = r"^(none|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})$"
PATH_D = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\-\s]*$")


class SvgElement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    type: Literal["path", "polyline", "circle", "rect", "line", "text", "follower", "arrow"]
    d: str | None = Field(default=None, max_length=400000)
    points: list[list[float]] | None = Field(default=None, max_length=5000)
    cx: float = 0
    cy: float = 0
    r: float = Field(default=4, ge=0, le=100000)
    x: float = 0
    y: float = 0
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)
    rx: float = Field(default=0, ge=0)
    x1: float = 0
    y1: float = 0
    x2: float = 0
    y2: float = 0
    text: str = Field(default="", max_length=300)
    font_size: float = Field(default=28, gt=0, le=1000)
    font_weight: int = Field(default=600, ge=100, le=900)
    anchor: Literal["start", "middle", "end"] = "start"
    stroke: str = Field(default="#ffffff", pattern=COLOR)
    fill: str = Field(default="none", pattern=COLOR)
    fill_opacity: float = Field(default=1, ge=0, le=1)
    stroke_width: float = Field(default=3, ge=0, le=1000)
    opacity: float = Field(default=1, ge=0, le=1)
    dashed: float = Field(default=0, ge=0, le=1000)  # dash length in viewBox units; 0 = solid
    glow: float = Field(default=0, ge=0, le=200)  # drop-shadow radius in viewBox units
    draw: list[int] | None = None
    appear: list[int] | None = None
    fill_in: list[int] | None = None
    route: str | None = Field(default=None, max_length=60)  # follower: polyline element id
    progress: list[int] | None = None  # follower travel range
    heads: Literal["end", "start", "both", "none"] = "end"  # arrow
    head_size: float = Field(default=0, ge=0, le=1000)  # arrow head length; 0 = 4x stroke width
    grow: Literal["start", "center"] = "start"  # arrow draw grows from x1,y1 or outward from the middle
    ripple: list[int] | None = None  # circle: rings expand and fade over [start, end]
    ripple_count: int = Field(default=3, ge=1, le=6)
    ripple_scale: float = Field(default=2.4, gt=1, le=10)
    # Trim paths: over trim.frames the visible window moves from [start0,end0] to [start1,end1] of the path (0..1),
    # e.g. {"frames":[0,30],"start":[0,0],"end":[0,1]} draws on; {"start":[0,1],"end":[1,1]} draws off from the start.
    trim: dict | None = None
    trim_bezier: list[float] | None = Field(default=None, min_length=4, max_length=4)
    width_ramp: list[float] | None = Field(default=None, min_length=4, max_length=4)  # [start_frame, end_frame, w0, w1]
    linecap: Literal["round", "butt", "square"] = "round"  # butt for bars and rules that must stop exactly at their ends

    @model_validator(mode="after")
    def check(self):
        for name in ("draw", "appear", "fill_in", "progress", "ripple"):
            r = getattr(self, name)
            if r is not None and (len(r) != 2 or not 0 <= r[0] < r[1]):
                raise ValueError(f"{self.id}: {name} needs [start, end] local frames with start < end")
        if self.type == "path" and (not self.d or not PATH_D.match(self.d)):
            raise ValueError(f"{self.id}: path d must contain only SVG path commands and numbers")
        if self.type == "polyline" and (not self.points or len(self.points) < 2 or any(len(p) != 2 for p in self.points)):
            raise ValueError(f"{self.id}: polyline needs >= 2 [x, y] points")
        if self.type == "follower" and (not self.route or not self.progress):
            raise ValueError(f"{self.id}: follower needs route (polyline id) and progress")
        if self.type == "text" and not self.text:
            raise ValueError(f"{self.id}: text element needs text")
        if self.type == "arrow" and (self.x1, self.y1) == (self.x2, self.y2):
            raise ValueError(f"{self.id}: arrow needs distinct ends")
        if self.ripple and self.type != "circle":
            raise ValueError(f"{self.id}: ripple applies to circle elements")
        if self.trim is not None:
            t = self.trim
            if set(t) - {"frames", "start", "end"} or "frames" not in t:
                raise ValueError(f"{self.id}: trim needs frames [a,b] and optional start/end [from,to] in 0..1")
            fr = t["frames"]
            if not (isinstance(fr, list) and len(fr) == 2 and all(isinstance(v, int) for v in fr) and 0 <= fr[0] < fr[1]):
                raise ValueError(f"{self.id}: trim frames [start, end] local frames")
            for k in ("start", "end"):
                v = t.get(k, [0, 0] if k == "start" else [1, 1])
                if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in v)):
                    raise ValueError(f"{self.id}: trim {k} is [from, to] in 0..1")
            if self.type in ("text", "follower", "arrow"):
                raise ValueError(f"{self.id}: trim applies to stroked shapes and paths")
        if self.width_ramp is not None and not self.width_ramp[0] < self.width_ramp[1]:
            raise ValueError(f"{self.id}: width_ramp [start_frame, end_frame, w0, w1]")
        return self


class SvgGraphic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view_box: list[float] = Field(min_length=2, max_length=2)
    elements: list[SvgElement] = Field(min_length=1, max_length=2000)  # unit grids reach ~1000 dots
    font_family: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def refs(self):
        if any(v <= 0 for v in self.view_box):
            raise ValueError("view_box needs positive width/height")
        ids = [e.id for e in self.elements]
        if len(set(ids)) != len(ids):
            raise ValueError("SVG element ids must be unique")
        polylines = {e.id for e in self.elements if e.type == "polyline"}
        for e in self.elements:
            if e.type == "follower" and e.route not in polylines:
                raise ValueError(f"{e.id}: route {e.route!r} must reference a polyline element")
        if self.font_family and not re.match(r"^[A-Za-z0-9 _-]+$", self.font_family):
            raise ValueError("font_family must be a plain family name")
        return self
