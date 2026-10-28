from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Effect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    start_frame: int = Field(default=0, ge=0)
    end_frame: int = Field(default=18, ge=1)
    params: dict = Field(default_factory=dict)
    easing: Literal["linear", "smooth", "ease_in", "ease_out", "snappy", "dramatic", "bouncy", "springy", "dreamy", "ease_in_out", "stepped"] = "smooth"
    # Graph-editor curve: cubic-bezier(x1,y1,x2,y2) overrides easing (x1,x2 in 0..1; y may overshoot, e.g. anticipation).
    bezier: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def valid(self):
        if self.bezier and (not 0 <= self.bezier[0] <= 1 or not 0 <= self.bezier[2] <= 1 or any(abs(v) > 3 for v in self.bezier)):
            raise ValueError("bezier needs x1,x2 in 0..1 and |y| <= 3")
        from .effects import validate_effect
        validate_effect(self.name,self.params)
        if self.end_frame <= self.start_frame:
            raise ValueError("Effect end_frame must follow start_frame")
        return self


class Keyframe(BaseModel):
    frame: int = Field(ge=0)
    value: float = Field(allow_inf_nan=False)
    easing: Literal["linear", "smooth", "ease_in", "ease_out", "snappy", "dramatic", "bouncy", "springy", "dreamy", "ease_in_out", "stepped"] = "linear"
    bezier: list[float] | None = Field(default=None, min_length=4, max_length=4)


class Inertia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(default=.5, ge=0, le=2)  # initial slope of the bounce as a share of the arrival velocity
    period_frames: float = Field(default=8, ge=2, le=60)
    decay: float = Field(default=.5, gt=0, le=1)  # amplitude kept per period (.5 = halves each cycle)


class Wiggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amp: float = Field(ge=0, le=2000)
    hz: float = Field(default=1, gt=0, le=12)
    seed: int = Field(default=7, ge=0, le=2147483647)


class TrackMod(BaseModel):
    """After Effects expression equivalents on a keyframe track: loopOut, inertial bounce, wiggle."""
    model_config = ConfigDict(extra="forbid")
    loop: Literal["cycle", "pingpong", "offset"] | None = None
    inertia: Inertia | None = None
    wiggle: Wiggle | None = None


TRACK_LIMITS = {"x": (-40000, 40000), "y": (-40000, 40000), "scale": (.01, 100), "rotate": (-3600, 3600), "opacity": (0, 1), "blur": (0, 100),
                "scale_x": (.01, 100), "scale_y": (.01, 100), "squash": (.05, 20), "skew": (-80, 80)}


class Animated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effects: list[Effect] = Field(default_factory=list, max_length=16)
    keyframes: dict[str,list[Keyframe]] = Field(default_factory=dict)
    # Per-track modifiers keyed like keyframes (loop / inertia / wiggle).
    track_mods: dict[str, TrackMod] = Field(default_factory=dict)

    @model_validator(mode="after")
    def tracks(self):
        # Wide enough for a camera travelling over a canvas several frames across (explainer.camera_stage).
        # squash is width/height at constant area (>1 squashes, <1 stretches); skew is skewX degrees.
        limits=TRACK_LIMITS
        if set(self.track_mods)-set(self.keyframes):
            raise ValueError("track_mods apply to keyframe tracks that exist on this item")
        for key,points in self.keyframes.items():
            if key not in limits or not 1<=len(points)<=100:
                raise ValueError("Keyframe track: x/y pixels, scale, scale_x, scale_y, squash, skew, rotate degrees, opacity, blur pixels; 1..100 points")
            if any(b.frame<=a.frame for a,b in zip(points,points[1:])):
                raise ValueError("Keyframe frames must be strictly increasing")
            if any(not limits[key][0]<=p.value<=limits[key][1] for p in points):
                raise ValueError(f"Keyframe {key} out of range")
        return self


class Transition(BaseModel):
    name: Literal["dissolve","wipe_left","wipe_right","wipe_up","wipe_down","iris","blur_in","zoom_in",
                  "push_left","push_right","push_up","push_down","whip_left","whip_right","whip_up","whip_down","zoom_through","flash","burn",
                  "spin","luma_key","glitch_cut","dip_black","dip_white","pass_left","pass_right"] = "dissolve"
    # Up to 10 s: measured film grammar needs long dissolves (1.3-2.5 s), superimpositions (6-9 s) and opening fades (4-5 s).
    duration_frames: int = Field(default=12,ge=1,le=300)
    # freeze: outgoing last frame held (no source handle needed). live: outgoing shot keeps playing
    # from its source handle for duration_frames, so both sides move during the transition.
    mode: Literal["freeze","live"] = "freeze"
    # Strength of the move: whip blur, spin angle (90deg x intensity), glitch jitter. Match it to the motion in the footage.
    intensity: float = Field(default=1, ge=.2, le=3)
    hold_frames: int = Field(default=0, ge=0, le=240)  # dip_*: frames held on black/white between the fade out and in
    center: list[float] | None = Field(default=None, min_length=2, max_length=2)  # iris: normalized [x, y] of the opening

    @model_validator(mode="after")
    def shape(self):
        if self.hold_frames and self.hold_frames >= self.duration_frames - 1:
            raise ValueError("hold_frames must leave frames for the fade out and in")
        if self.center and not all(0 <= v <= 1 for v in self.center):
            raise ValueError("iris center is normalized [x, y]")
        return self


class Mask(BaseModel):
    """A shape in the layer's own box (0..1 units, may extend past it). Modes combine in order like After Effects:
    add paints, subtract cuts, intersect keeps only the overlap. feather softens the edge in pixels."""
    model_config = ConfigDict(extra="forbid")
    shape: Literal["rect", "ellipse", "polygon"] = "rect"
    geom: list[float] = Field(min_length=4, max_length=64)  # rect x,y,w,h | ellipse cx,cy,rx,ry | polygon x1,y1,x2,y2,...
    mode: Literal["add", "subtract", "intersect"] = "add"
    feather_px: float = Field(default=0, ge=0, le=300)
    opacity: float = Field(default=1, ge=0, le=1)
    keyframes: list[dict] = Field(default_factory=list, max_length=60)  # [{frame, geom, easing?, bezier?}] same length as geom

    @model_validator(mode="after")
    def check(self):
        if self.shape == "polygon" and (len(self.geom) < 6 or len(self.geom) % 2):
            raise ValueError("polygon mask needs >= 3 x,y points")
        if self.shape != "polygon" and len(self.geom) != 4:
            raise ValueError(f"{self.shape} mask geom has 4 numbers")
        if any(not -2 <= v <= 3 for v in self.geom):
            raise ValueError("mask geometry is in layer-box units (-2..3)")
        prev = -1
        for k in self.keyframes:
            if set(k) - {"frame", "geom", "easing", "bezier"} or not isinstance(k.get("frame"), int) or k["frame"] <= prev:
                raise ValueError("mask keyframes need increasing integer frames and geom")
            if not isinstance(k.get("geom"), list) or len(k["geom"]) != len(self.geom) or any(not isinstance(v, (int, float)) for v in k["geom"]):
                raise ValueError("every mask keyframe needs the same number of geometry values as geom")
            prev = k["frame"]
        return self


class Matte(BaseModel):
    """Track matte: another layer's coverage (alpha) or brightness (luma) decides where this layer shows."""
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=100)
    mode: Literal["alpha", "alpha_inverted", "luma", "luma_inverted"] = "alpha"
    hide_source: bool = True


class ChromaKey(BaseModel):
    """Green/blue screen key for image/video layers (SVG filter, both engines)."""
    model_config = ConfigDict(extra="forbid")
    screen: Literal["green", "blue"] = "green"
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")  # sampled screen colour; defaults to a typical green/blue
    clip_black: float = Field(default=.1, ge=0, le=.9)
    clip_white: float = Field(default=.6, ge=.05, le=1)
    choke_px: float = Field(default=0, ge=0, le=8)
    soften_px: float = Field(default=0, ge=0, le=8)
    spill: float = Field(default=.8, ge=0, le=1)
    view: Literal["final", "matte"] = "final"

    @model_validator(mode="after")
    def check(self):
        if self.clip_white < self.clip_black + .05:
            raise ValueError("clip_white must exceed clip_black by at least .05")
        if self.color:
            r, g, b = (int(self.color[i:i + 2], 16) for i in (1, 3, 5))
            if (self.screen == "green" and g <= max(r, b)) or (self.screen == "blue" and b <= max(r, g)):
                raise ValueError(f"key colour {self.color} is not a {self.screen} screen colour")
        return self


def _quad(corners, where):
    """Four frame-normalised corners TL, TR, BR, BL forming a convex, non-degenerate quad (a homography exists)."""
    if len(corners) != 4 or any(len(c) != 2 for c in corners):
        raise ValueError(f"{where}: corners are four [x, y] points (TL, TR, BR, BL)")
    if not all(-3 <= v <= 4 for c in corners for v in c):
        raise ValueError(f"{where}: corner coordinates are frame-normalised (-3..4)")
    cross = [(corners[(i + 1) % 4][0] - corners[i][0]) * (corners[(i + 2) % 4][1] - corners[(i + 1) % 4][1])
             - (corners[(i + 1) % 4][1] - corners[i][1]) * (corners[(i + 2) % 4][0] - corners[(i + 1) % 4][0]) for i in range(4)]
    if not (all(c > 1e-7 for c in cross) or all(c < -1e-7 for c in cross)):
        raise ValueError(f"{where}: corners must form a convex quad in order TL, TR, BR, BL (no crossing, no collapse)")


class PinSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame: int = Field(ge=0)
    corners: list[list[float]]


class CornerPin(BaseModel):
    """Map the layer box onto four frame points (screen replacement, signs, posters). Either fixed corners or a
    per-frame track (layer-local frames, e.g. from track_plane); samples interpolate linearly."""
    model_config = ConfigDict(extra="forbid")
    corners: list[list[float]] | None = None
    track: list[PinSample] = Field(default_factory=list, max_length=20000)

    @model_validator(mode="after")
    def check(self):
        if (self.corners is None) == (not self.track):
            raise ValueError("corner_pin needs exactly one of corners or track")
        if self.corners is not None:
            _quad(self.corners, "corner_pin")
        prev = -1
        for s in self.track:
            if s.frame <= prev:
                raise ValueError("corner_pin track frames must increase")
            prev = s.frame
            _quad(s.corners, f"corner_pin track frame {s.frame}")
        return self


class Follow(BaseModel):
    """Follow-through on a parented layer: it swings about its anchor behind the parent's motion (damped spring)."""
    model_config = ConfigDict(extra="forbid")
    preset: Literal["stiff", "soft"] = "stiff"  # stiff: antenna/tag (5-frame period, halves per cycle); soft: feather/hair
    period_frames: float | None = Field(default=None, ge=2, le=60)
    decay: float | None = Field(default=None, gt=0, lt=1)
    k_v: float | None = Field(default=None, ge=0, le=5)  # degrees per (px/frame at 1920 wide) of drag while moving
    k_a: float | None = Field(default=None, ge=0, le=5)
    max_deg: float | None = Field(default=None, gt=0, le=180)
    axis: Literal["x", "y"] = "x"
    invert: bool = False


class Driver(BaseModel):
    """A keyframe track computed from another (or this) layer's track at the same global frame (AE expression link):
    add + mul x value (or its per-frame velocity), clamped; replace or add to the layer's own track."""
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=100)
    track: Literal["x", "y", "scale", "rotate", "opacity", "blur", "scale_x", "scale_y", "squash", "skew"] | None = None  # default: same track
    mul: float = Field(default=1, ge=-1000, le=1000, allow_inf_nan=False)
    add: float = Field(default=0, ge=-40000, le=40000, allow_inf_nan=False)
    mode: Literal["value", "velocity"] = "value"
    delay_frames: int = Field(default=0, ge=-300, le=300)  # read the source this many frames earlier (overlap / follow-the-leader)
    clamp: list[float] | None = Field(default=None, min_length=2, max_length=2)
    mix: Literal["replace", "add"] = "replace"

    @model_validator(mode="after")
    def check(self):
        if self.clamp and self.clamp[0] >= self.clamp[1]:
            raise ValueError("driver clamp is [low, high]")
        return self


class IK(BaseModel):
    """Two-bone inverse kinematics on the lower bone: its parent is the upper bone; both rotate so ik.tip reaches the
    target layer's anchor (a null with keyframes, or any layer)."""
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=100)
    tip: list[float] = Field(default_factory=lambda: [.5, 1.0], min_length=2, max_length=2)  # end point in the lower bone's box
    bend: Literal["cw", "ccw"] = "cw"  # side the joint bends to (clockwise on screen from upper to lower bone)
    weight: float = Field(default=1, ge=0, le=1)  # 0 = keyed (FK) pose, 1 = full IK

    @model_validator(mode="after")
    def check(self):
        if not all(-1 <= v <= 2 for v in self.tip):
            raise ValueError("ik.tip is in the lower bone's box units (-1..2)")
        return self


class Layer(Animated):
    id: str = Field(min_length=1,max_length=100)
    kind: Literal["text","image","video","shape","counter","bar_chart","line_chart","flow","particles","caption","callout","pattern","icon","scene3d","svg","film","adjust","null"] = "text"
    # Optional shot ID: the layer then moves with that shot through its incoming/outgoing transitions
    # (push/whip/zoom transforms apply to the layer too) and keeps playing during live outgoing overlaps.
    attach_shot: str | None = Field(default=None, max_length=100)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    x: float = Field(default=.1,ge=-1,le=2)
    y: float = Field(default=.1,ge=-1,le=2)
    width: float = Field(default=.8,gt=0,le=2)
    height: float = Field(default=.3,gt=0,le=2)
    z: int = Field(default=10,ge=0,le=1000)
    opacity: float = Field(default=1,ge=0,le=1)
    rotation: float = Field(default=0,ge=-3600,le=3600)
    text: str = Field(default="",max_length=2000)
    asset_id: str | None = None
    source_start: float = Field(default=0,ge=0)
    playback_rate: float = Field(default=1,ge=.1,le=8)
    fit: Literal["contain","cover"] = "contain"
    # flow: a video layer (a framed clip on a map, a picture-in-picture) plays a motion-interpolated 30 fps proxy, as a
    # shot does (off-cadence sources, slow motion, files that repeat frames)
    frame_sampling: Literal["nearest","flow"] = "nearest"
    # add (= CSS plus-lighter) for fire, light and particles on dark; hard_light for textures over a whole frame.
    blend: Literal["normal","screen","multiply","overlay","difference","lighten","darken","add","soft_light","hard_light","color_dodge"] = "normal"
    color: str = "#ffffff"
    background: str = "transparent"
    font_size: int = Field(default=60,ge=12,le=900)  # frame-filling titles reach ~.45 H cap height (≈ 600-700 px at 1080p)
    font_weight: int | None = Field(default=None,ge=100,le=900)  # overrides the role weight (variable fonts)
    line_height: float | None = Field(default=None,ge=.8,le=3)
    typography_role: Literal['display','headline','title','body','caption','label','source','data','quote','code'] | None = None
    color_role: Literal['background','surface','text','muted','accent','secondary','on_accent'] | None = None
    background_role: Literal['background','surface','text','muted','accent','secondary','on_accent'] | None = None
    font_id: str | None = None
    # Animate "on twos/threes": the layer's motion holds each pose for n frames (stepped, hand-made feel; the
    # infographic house style measured at 12 fps motion in 24 fps video). 1 = every frame; design.step_frames sets a default.
    step_frames: int = Field(default=1, ge=1, le=4)
    # Compositing. parent: inherit another layer's (or a null's) translate/scale/rotate around its anchor; anchor: pivot in
    # the layer box (default centre); masks: shapes that cut the layer; matte: another layer as track matte; key: chroma key.
    parent: str | None = Field(default=None, max_length=100)
    parent_bind_frame: int | None = Field(default=None, ge=0)  # keep the child where it is at this frame (parent without jump)
    anchor: list[float] | None = Field(default=None, min_length=2, max_length=2)
    masks: list[Mask] = Field(default_factory=list, max_length=8)
    mask_invert: bool = False
    matte: Matte | None = None
    key: ChromaKey | None = None
    # Corner pin replaces the layer's own transform with the homography onto four frame points (parent is not combined).
    corner_pin: CornerPin | None = None
    follow: Follow | None = None
    # Rigging: drivers link a track to another layer's track; ik makes this layer the lower bone of a two-bone chain.
    drivers: dict[str, Driver] = Field(default_factory=dict)
    ik: IK | None = None
    data: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def content(self):
        if self.font_id:
            from .design_library import font
            font(self.font_id)
        if self.kind in ("image","video") and not self.asset_id:
            raise ValueError("Media layer requires asset_id")
        if self.key and self.kind not in ("image","video"):
            raise ValueError("Chroma key applies to image/video layers")
        if set(self.drivers) - set(TRACK_LIMITS):
            raise ValueError(f"drivers are keyed by track: {', '.join(TRACK_LIMITS)}")
        if self.ik and not self.parent:
            raise ValueError("ik goes on the lower bone, whose parent is the upper bone")
        if self.ik and (self.follow or self.corner_pin):
            raise ValueError("ik sets the bone rotation; do not combine it with follow or corner_pin")
        if self.follow and not self.parent:
            raise ValueError("follow needs a parent (the layer swings behind its parent's motion)")
        if self.corner_pin and self.parent:
            raise ValueError("corner_pin and parent both set the layer transform; use one")
        if self.corner_pin and self.corner_pin.track and self.corner_pin.track[-1].frame >= self.end_frame - self.start_frame:
            raise ValueError("corner_pin track frames are layer-local and must be inside the layer duration")
        if self.parent == self.id or (self.matte and self.matte.source == self.id):
            raise ValueError("A layer cannot parent or matte itself")
        if self.anchor and not all(-1 <= v <= 2 for v in self.anchor):
            raise ValueError("anchor is in layer-box units (-1..2)")
        from .widgets import validate_data
        validate_data(self.kind,self.data)
        from .effects import CATALOG
        if any(CATALOG[e.name]["family"]=="text" for e in self.effects) and self.kind not in ("text","caption"):
            raise ValueError("Text effects require text layer")
        if self.kind=='caption' and any(CATALOG[e.name]['family']=='text' and e.name!='text_outline' for e in self.effects):
            raise ValueError('Caption uses timed-word data; text_outline is its supported text effect. Other text effects require a text layer.')
        if any(e.name=="progress" for e in self.effects) and self.kind not in ("counter","bar_chart","line_chart","flow","particles","callout"):
            raise ValueError("progress requires infographic layer")
        duration=self.end_frame-self.start_frame
        if self.kind=='scene3d':
            keys=[*self.data.get('camera_keyframes',[]),*[k for o in self.data.get('objects',[]) for k in o.get('keyframes',[])]]
            if any(k['frame']>=duration for k in keys):raise ValueError('3D pose outside local layer duration')
        if any(page['end_frame']>duration for page in self.data.get('pages',[])):raise ValueError('Caption page outside layer duration')
        if any(w['end_frame']>duration for w in self.data.get('words',[])) or any(k['frame']>=duration for k in self.data.get('target_keyframes',[])):
            raise ValueError("Caption word/callout target keyframes outside layer duration")
        return self


class Ducking(BaseModel):
    model_config=ConfigDict(extra="forbid")
    threshold: float = Field(default=.025,ge=.001,le=.5)
    ratio: float = Field(default=8,ge=1,le=20)
    attack_ms: float = Field(default=25,ge=1,le=200)
    release_ms: float = Field(default=350,ge=20,le=2000)


class AudioMix(BaseModel):
    model_config=ConfigDict(extra="forbid")
    target_lufs: float = Field(default=-16,ge=-24,le=-9)
    true_peak_db: float = Field(default=-1.5,ge=-6,le=-1)
    loudness_range: float = Field(default=11,ge=5,le=20)
    music_ducking: Ducking = Field(default_factory=Ducking)


class AudioClip(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id: str
    asset_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    source_start: float = Field(default=0,ge=0)
    volume: float = Field(default=.5,ge=0,le=2)
    playback_rate: float = Field(default=1,ge=.5,le=2)
    fade_in: float = Field(default=.05,ge=0,le=10)
    fade_out: float = Field(default=.15,ge=0,le=10)
    # Ducking: a non-dialogue clip dips under the voice bus (the narration track plus every dialogue clip); a dialogue
    # clip with the flag dips under the narration track only (an interview bed under the narrator)
    duck_under_voice: bool = True
    ducking: Ducking = Field(default_factory=Ducking)
    # Mix role: picks a processing chain (dialogue: 80 Hz high-pass, 3:1 compression, -3 dBFS limiter; ambience: gentle
    # low-pass; foley: rumble cut) and, with normalize, a level target measured on the used section of the source:
    # dialogue -16 LUFS, music -30, ambience -42, foley -28; short accents (<1.5 s) by peak: sfx -12 dBFS, foley -18.
    role: Literal["dialogue","music","sfx","ambience","foley"] | None = None
    normalize: bool = False
    # Overrides the role's loudness target when normalising. A score that ducks under every voice can sit near -22 LUFS
    # and rise in the pauses; the -30 default assumes a bed that never moves under constant speech.
    target_lufs: float | None = Field(default=None, ge=-45, le=-10)
    # Character filter after the role chain: radio = newsreel/broadcast (300-3400 Hz band, compressed, softly clipped);
    # muffled = hearing after a blast, the "shell-shock" low-pass (~450 Hz) to pair with a tinnitus ring; distant = far
    # away (low-pass, late reflections); telephone = narrow 500-3000 Hz; archival = an optical track of the 1940s-70s
    # (140-5200 Hz, a slow wow, gentle compression): a synthesized sound made to sit with the picture's age, Ribicoff's
    # "smudged" degraded layer. reverse plays the used section backwards, so a
    # real sound (an explosion, a cymbal) swells into the cut instead of decaying from it.
    treatment: Literal["radio","muffled","distant","telephone","archival"] | None = None
    reverse: bool = False


class TypeStyle(BaseModel):
    model_config=ConfigDict(extra='forbid')
    font_id:str
    size:float=Field(default=42,ge=12,le=300,allow_inf_nan=False)
    weight:int=Field(default=400,ge=100,le=900)
    italic:bool=False
    line_height:float=Field(default=1.45,ge=1.1,le=2,allow_inf_nan=False)
    tracking:float=Field(default=0,ge=-.05,le=.2,allow_inf_nan=False)
    variation_axes:dict[str,float]=Field(default_factory=dict,max_length=8)

    @model_validator(mode='after')
    def available(self):
        from .design_library import font
        faces=font(self.font_id)['faces']
        selected=[f for f in faces if f['style']==('italic' if self.italic else 'normal')]
        if not any(int(f['weight'].split()[0])<=self.weight<=int(f['weight'].split()[-1]) for f in selected):
            raise ValueError('Requested font weight/style is not bundled; choose a listed face')
        import math
        axes=next(f['axes'] for f in selected if int(f['weight'].split()[0])<=self.weight<=int(f['weight'].split()[-1]))
        for axis,value in self.variation_axes.items():
            if axis=='wght' or axis not in axes or not math.isfinite(value) or not axes[axis][0]<=value<=axes[axis][2]:raise ValueError('Variation axis outside bundled face; set wght through weight')
        return self

class Design(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str = Field(default="",max_length=2000)
    audience: str = Field(default="",max_length=1000)
    palette: list[str] = Field(default_factory=lambda:["#102322","#81e6be","#ffffff"],min_length=1,max_length=8)
    font_family: str = Field(default="Segoe UI, sans-serif",max_length=200)
    background: str = "#102322"
    step_frames: int = Field(default=1, ge=1, le=4)  # default for layers that keep step_frames=1
    safe_margin: float = Field(default=.08,ge=0,le=.3)
    references: list[str] = Field(default_factory=list,max_length=20)
    notes: str = Field(default="",max_length=4000)
    style_id:str=Field(default='',max_length=100)
    bundled_font_ids:list[str]=Field(default_factory=list,max_length=32)
    typography:dict[Literal['display','headline','title','body','caption','label','source','data','quote','code'],TypeStyle]=Field(default_factory=dict)
    color_roles:dict[Literal['background','surface','text','muted','accent','secondary','on_accent'],str]=Field(default_factory=dict)
    direction:dict=Field(default_factory=dict)  # creative direction block (directions.py): motion, pacing, transitions, finish

    @model_validator(mode='after')
    def library_tokens(self):
        from .design_library import font,luminance
        for fid in self.bundled_font_ids:font(fid)
        for color in self.color_roles.values():luminance(color)
        return self

PROFILES = {
    "vertical": (1080, 1920),
    "landscape": (1920, 1080),
    "square": (1080, 1080),
    "portrait45": (1080, 1350),  # 4:5 feed placement
}


class ProjectInput(BaseModel):
    title: str = Field(default="Video mới", min_length=1, max_length=160)
    script: str = Field(default="", max_length=24000)
    spoken_text: str = Field(default="", max_length=24000)
    profile: Literal["vertical", "landscape", "square", "portrait45"] = "vertical"
    style: Literal["documentary", "energetic", "calm"] = "documentary"
    voice: Literal["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"] = "vi-VN-HoaiMyNeural"
    voice_rate: int = Field(default=0, ge=-30, le=30)
    # auto: Edge TTS → Piper (offline model installed) → OS voice in the same language → silent placeholder with
    # reading-speed timing (import the real narration later). A fixed backend fails instead of falling back.
    voice_backend: Literal["auto", "edge", "piper", "sapi", "silent"] = "auto"
    # Silence after generated narration so the last picture/end card breathes instead of ending on the last syllable.
    tail_seconds: float = Field(default=.8, ge=0, le=5)
    narration_id: str | None = None
    music_id: str | None = None
    music_volume: float = Field(default=0.14, ge=0, le=0.5)
    captions: bool = True
    renderer: Literal["ffmpeg", "remotion", "hyperframes"] = "ffmpeg"


class Cue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Thời điểm kết thúc phải sau bắt đầu")
        return self


class Shot(Animated):
    id: str
    beat_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    asset_id: str | None = None
    source_start: float = Field(default=0, ge=0)
    playback_rate: float = Field(default=1,ge=.1,le=8)
    # Freeze frame: the shot shows the still of its source_start frame for its whole span (both engines).
    freeze: bool = False
    # flow: a 1x shot of a 24/25/50 fps source, or any slow-motion shot (rate < 1), plays a motion-interpolated 30 fps
    # clip (repeating every 4th-6th frame, or 1-2-1-2 at 0.7x, reads as judder on a slow glide); nearest repeats or drops
    # frames as a player does
    frame_sampling: Literal["nearest", "flow"] = "nearest"
    transition: Transition | None = None
    text: str = Field(default="", max_length=500)
    role: Literal["illustration", "evidence", "metaphor", "reconstruction", "decoration"] = "illustration"
    motion: Literal["hold", "push", "pull", "pan"] = "push"
    fit: Literal["cover", "contain"] = "cover"
    focus_x: float = Field(default=0.5, ge=0, le=1)
    focus_y: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""

    @model_validator(mode="after")
    def ordered(self):
        if self.end_frame <= self.start_frame:
            raise ValueError("Shot phải có ít nhất một frame")
        from .effects import CATALOG
        if any(CATALOG[e.name]["family"]=="text" or e.name=="progress" for e in self.effects):
            raise ValueError("Text/data effects require an appropriate layer")
        return self


class Overlay(BaseModel):
    id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    text: str = Field(max_length=1000)
    x: float = Field(default=0.08, ge=0, le=1)
    y: float = Field(default=0.12, ge=0, le=1)
    width: float = Field(default=0.84, gt=0, le=1)
    font_size: int = Field(default=54, ge=12, le=240)
    color: str = "#ffffff"
    background: str = "#102322"
    animation: Literal["none", "fade", "rise"] = "rise"


class Timeline(BaseModel):
    schema_version: str = "2.0"
    fps: int = 30
    width: int
    height: int
    total_frames: int
    audio_samples: int
    sample_rate: int = 48000
    timing_method: str
    beats: list[dict]
    shots: list[Shot]
    cues: list[Cue]
    overlays: list[Overlay] = Field(default_factory=list)
    layers: list[Layer] = Field(default_factory=list,max_length=1000)
    audio_clips: list[AudioClip] = Field(default_factory=list,max_length=400)  # a 14 min documentary's sound design needs ~150
    audio_mix: AudioMix = Field(default_factory=AudioMix)
    design: Design = Field(default_factory=Design)

    @model_validator(mode="after")
    def validate_track(self):
        if self.fps != 30 or self.sample_rate != 48000:
            raise ValueError("Bản đầu dùng 30 fps, audio 48 kHz")
        if (self.width, self.height) not in PROFILES.values():
            raise ValueError("Kích thước đầu ra chưa hỗ trợ")
        cursor = 0
        for s in self.shots:
            if s.start_frame != cursor:
                raise ValueError("Track hình phải liên tục, không hở hoặc chồng frame")
            cursor = s.end_frame
        if not self.shots or cursor != self.total_frames:
            raise ValueError("Shot phải phủ toàn bộ thời lượng giọng")
        if len({s.id for s in self.shots}) != len(self.shots):
            raise ValueError("ID shot bị trùng")
        if abs(self.total_frames - self.audio_samples / 1600) > 1:
            raise ValueError("Timeline không khớp thời lượng giọng")
        prior = 0.0
        for collection in (self.layers,self.audio_clips):
            if len({item.id for item in collection})!=len(collection):
                raise ValueError("Duplicate layer/audio ID")
            for item in collection:
                if item.end_frame<=item.start_frame or item.end_frame>self.total_frames:
                    raise ValueError("Layer/audio outside timeline")
        for item in [*self.shots,*self.layers]:
            length=item.end_frame-item.start_frame
            if any(e.end_frame>length for e in item.effects) or any(p.frame>=length for points in item.keyframes.values() for p in points):
                raise ValueError("Effect/keyframe outside local shot/layer duration")
        shot_ranges={sh.id:(sh.start_frame,sh.end_frame) for sh in self.shots}
        for layer in self.layers:
            if layer.attach_shot:
                if layer.attach_shot not in shot_ranges:raise ValueError(f"{layer.id}: attach_shot {layer.attach_shot} not found")
                a,b=shot_ranges[layer.attach_shot]
                if layer.start_frame<a or layer.end_frame>b:raise ValueError(f"{layer.id}: attached layer must stay inside shot {layer.attach_shot} [{a},{b})")
        # Compositing graph: parents exist, share the child's shot container, no cycles, depth <= 8; matte sources exist,
        # are vector/text layers, and are not themselves matted (one level, like After Effects).
        by_id={l.id:l for l in self.layers}
        for layer in self.layers:
            seen,cur,depth=set(),layer,0
            while cur.parent:
                if cur.parent not in by_id:raise ValueError(f"{cur.id}: parent {cur.parent} not found")
                if cur.id in seen or depth>8:raise ValueError(f"{layer.id}: parenting forms a cycle or is deeper than 8")
                if by_id[cur.parent].attach_shot!=cur.attach_shot:raise ValueError(f"{cur.id}: parent must share attach_shot")
                seen.add(cur.id);cur=by_id[cur.parent];depth+=1
            if layer.matte:
                src=by_id.get(layer.matte.source)
                if not src:raise ValueError(f"{layer.id}: matte source {layer.matte.source} not found")
                if src.kind not in ("svg","shape","icon","text","counter","bar_chart","line_chart","flow","particles","callout"):
                    raise ValueError(f"{layer.id}: matte source must be a vector or text layer (svg, shape, icon, text, counter, charts)")
                if src.matte:raise ValueError(f"{layer.id}: a matte source cannot itself use a matte")
                if src.attach_shot!=layer.attach_shot:raise ValueError(f"{layer.id}: matte source must share attach_shot")
        # Rigs: driver sources exist with no (layer, track) cycle; an IK target exists outside its own chain (the target
        # must not inherit the bones it moves), and an upper bone serves one chain and is not itself an IK lower bone.
        def ancestors(l):
            out=[]
            while l.parent and l.parent in by_id and len(out)<10:out.append(l.parent);l=by_id[l.parent]
            return out
        uppers={}
        for layer in self.layers:
            for key,d in layer.drivers.items():
                if d.source not in by_id:raise ValueError(f"{layer.id}: driver source {d.source} not found")
                if d.source==layer.id and (d.track or key)==key:raise ValueError(f"{layer.id}: a track cannot drive itself")
            if layer.ik:
                if layer.ik.target not in by_id:raise ValueError(f"{layer.id}: ik target {layer.ik.target} not found")
                up=layer.parent
                if layer.ik.target in (layer.id,up) or layer.id in ancestors(by_id[layer.ik.target]) or up in ancestors(by_id[layer.ik.target]):
                    raise ValueError(f"{layer.id}: ik target must not be a bone of this chain or parented under it")
                if up in uppers:raise ValueError(f"{up}: upper bone of two IK chains ({uppers[up]}, {layer.id})")
                if by_id[up].ik:raise ValueError(f"{up}: an IK lower bone cannot also be an upper bone")
                uppers[up]=layer.id
        state={}
        def visit(node):
            if state.get(node)==1:raise ValueError(f"driver cycle through {node[0]}.{node[1]}")
            if state.get(node)==2:return
            state[node]=1
            d=by_id[node[0]].drivers.get(node[1])
            if d:visit((d.source,d.track or node[1]))
            state[node]=2
        for layer in self.layers:
            for key in layer.drivers:visit((layer.id,key))
        for layer in self.layers:
            if layer.typography_role:
                if layer.typography_role not in self.design.typography:raise ValueError('Typography role has no design token')
                if layer.font_id:
                    token=self.design.typography[layer.typography_role].model_dump()
                    TypeStyle.model_validate({**token,'font_id':layer.font_id})
            for role in (layer.color_role,layer.background_role):
                if role and role not in self.design.color_roles:raise ValueError('Color role has no design token')
        for i,s in enumerate(self.shots):
            if s.transition and (i==0 or s.transition.duration_frames>s.end_frame-s.start_frame):
                raise ValueError("Transition requires previous shot and must fit incoming shot")
        if len({o.id for o in self.overlays}) != len(self.overlays):
            raise ValueError("ID overlay bị trùng")
        for o in self.overlays:
            if o.end_frame <= o.start_frame or o.end_frame > self.total_frames:
                raise ValueError("Overlay vượt timeline hoặc không có thời lượng")
        for cue in self.cues:
            if cue.start < prior - 0.001 or cue.end > self.total_frames / self.fps + 0.04:
                raise ValueError("Phụ đề chồng nhau hoặc vượt thời lượng")
            prior = cue.end
        return self


class TimelineUpdate(BaseModel):
    base_revision: int
    timeline: Timeline
