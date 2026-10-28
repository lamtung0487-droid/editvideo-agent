"""Export actual editable Hyperframes/Remotion sources and render source snapshots."""
import functools
import html
import math
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from . import store
from .audio import write_srt
from .media import FFMPEG, FFPROBE, command, display_size, probe, sha256, safe_asset_path
from .planner import validate_sources
from .renderer import mix_audio, verify, contact_sheet

ENGINES = store.ROOT/"engines"
THREE_ADDONS = ("environments/RoomEnvironment.js","loaders/GLTFLoader.js","loaders/DRACOLoader.js","utils/BufferGeometryUtils.js","utils/SkeletonUtils.js","postprocessing/EffectComposer.js","postprocessing/RenderPass.js",
                "postprocessing/UnrealBloomPass.js","postprocessing/OutputPass.js","postprocessing/ShaderPass.js",
                "postprocessing/MaskPass.js","postprocessing/Pass.js","shaders/CopyShader.js",
                "shaders/LuminosityHighPassShader.js","shaders/OutputShader.js")


def legacy_hyperframes_html(payload):
    t, config, media = payload["timeline"], payload["config"], payload["media"]
    blocks, tweens = [], []
    for i, s in enumerate(t["shots"]):
        start, duration = s["start_frame"]/30, (s["end_frame"]-s["start_frame"])/30
        a = media.get(s.get("asset_id"))
        if a:
            style = f"width:100%;height:100%;object-fit:{s['fit']};object-position:{s['focus_x']*100}% {s['focus_y']*100}%"
            src = html.escape("public/"+a["src"], quote=True)
            content = f'<video id="media-{i}" class="clip scene" data-start="{start}" data-duration="{duration}" data-track-index="0" data-media-start="{grid(s["source_start"])}" src="{src}" muted playsinline style="position:absolute;inset:0;{style}"></video>' if a["kind"] == "video" else f'<img id="media-{i}" src="{src}" style="{style}">'
            if a["kind"] == "image" and s["motion"] != "hold" and s["fit"] != "contain":
                init, end = (1.075,1) if s["motion"] == "pull" else (1,1.075)
                tweens.append(f'tl.fromTo("#media-{i}",{{scale:{init}}},{{scale:{end},duration:{duration},ease:"sine.inOut"}},{start});')
        else:
            content = f'<div class="card"><small>{html.escape(config["title"])}</small><h1>{html.escape(s["text"])}</h1></div>'
        if a and a["kind"]=="video":
            blocks.append(content)
        else:
            blocks.append(f'<section class="clip scene" data-start="{start}" data-duration="{duration}" data-track-index="0">{content}</section>')
    for i, o in enumerate(t.get("overlays", [])):
        style = f"left:{o['x']*100}%;top:{o['y']*100}%;width:{o['width']*100}%;font-size:{o['font_size']}px;color:{o['color']};background:{o['background']}"
        blocks.append(f'<div id="overlay-{i}" class="clip overlay" data-start="{o["start_frame"]/30}" data-duration="{(o["end_frame"]-o["start_frame"])/30}" data-track-index="1" style="{html.escape(style,quote=True)}">{html.escape(o["text"])}</div>')
        if o["animation"] != "none":
            tweens.append(f'tl.from("#overlay-{i}",{{opacity:0,y:{24 if o["animation"]=="rise" else 0},duration:.3}},{o["start_frame"]/30});')
    if config["captions"]:
        for c in t["cues"]:
            blocks.append(f'<div class="clip caption" data-start="{c["start"]}" data-duration="{c["end"]-c["start"]}" data-track-index="2"><span>{html.escape(c["text"])}</span></div>')
    # Local GSAP dependency; render never relies on a CDN.
    return f'''<!doctype html><html lang="vi"><head><meta charset="UTF-8"><script src="gsap.min.js"></script>
<style>body{{margin:0;color:white;font-family:"Segoe UI",sans-serif;background:#102322}}#root{{position:relative;overflow:hidden;width:{t['width']}px;height:{t['height']}px}}
.scene{{position:absolute;inset:0;overflow:hidden}}.card{{box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;height:100%;padding:12% 9%;background:linear-gradient(135deg,#102e2c,#24524b)}}small{{font-size:32px;color:#a9e6c8;margin-bottom:32px}}h1{{font-size:72px;font-weight:700;line-height:1.22;margin:0}}.overlay{{position:absolute;box-sizing:border-box;padding:24px;border-radius:16px;white-space:pre-wrap}}.caption{{position:absolute;bottom:17%;left:8%;width:84%;text-align:center;font-size:{62 if t['width']>t['height'] else 50}px;font-weight:700;line-height:1.35}}.caption span{{background:rgba(10,22,26,.84);padding:8px 16px;box-decoration-break:clone}}</style></head><body>
<div id="root" data-composition-id="AgentVideo" data-width="{t['width']}" data-height="{t['height']}" data-duration="{t['total_frames']/30}" data-fps="30">{''.join(blocks)}</div>
<script>const tl=gsap.timeline({{paused:true}});{''.join(tweens)}window.__timelines=window.__timelines||{{}};window.__timelines.AgentVideo=tl;</script></body></html>'''


def hyperframes_videos(payload):
    """Static <video> declarations for every video shot and layer. HyperFrames' compiler only sees media present in the
    HTML (runtime-created elements leave videoCount 0, so clips never seek to their source offsets); the runtime adopts
    these elements by id. Track indices and durations mirror hyper-runtime.js."""
    t, media = payload["timeline"], payload.get("media") or {}
    tags = []
    shots = t["shots"]
    for i, s in enumerate(shots):
        a = media.get(s.get("asset_id"))
        if not a or a.get("kind") != "video" or s.get("freeze"):  # a freeze shot shows its still, not the video
            continue
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        extra = nxt["transition"]["duration_frames"] if nxt and (nxt.get("transition") or {}).get("mode") == "live" else 0
        tags.append(("s-" + s["id"], "scene", s["start_frame"], s["end_frame"] - s["start_frame"] + extra, s.get("source_start", 0), s.get("playback_rate", 1), i % 2, a["src"]))
    for l in t.get("layers") or []:
        a = media.get(l.get("asset_id"))
        if not a or a.get("kind") != "video":
            continue
        tags.append(("l-" + l["id"], "layer", l["start_frame"], l["end_frame"] - l["start_frame"], l.get("source_start", 0), l.get("playback_rate", 1), l.get("z", 10), a["src"]))
    esc = lambda v: html.escape(str(v), quote=True)
    # media start on the 30 fps grid, as Remotion's trimBefore=round(source_start*30): a start between frames (0.25 s
    # = frame 7.5) otherwise showed the earlier frame here and the later one there, a whole shot one frame apart.
    # preload="metadata": with "auto", each <video> held a streaming connection and Chrome's six per host ran out
    # past six distinct sources, so HyperFrames' player never became ready (a 17-source travel film; frames come
    # from HyperFrames' own extraction, the elements only need their metadata)
    return "".join(f'<video id="video-{esc(i)}" class="{c}" data-start="{a / 30}" data-duration="{d / 30}" data-media-start="{grid(ms)}" data-playback-rate="{r}" '
                   f'data-track-index="{tr}" src="public/{esc(src)}" muted playsinline preload="metadata"></video>' for i, c, a, d, ms, r, tr, src in tags)


VIDEO_START, VIDEO_END = "<!--editvideo:videos-->", "<!--/editvideo:videos-->"


def sync_video_declarations(source, payload):
    """Rewrite the generated <video> block of a HyperFrames index.html from the current timeline (between markers; an
    older export without markers gets the block inserted after the root tag). Run on every payload refresh so a patch
    after export (a punch-in split, a new select) never renders clips HyperFrames does not know about."""
    path = source/"index.html"
    if not path.exists():
        return False
    page = path.read_text(encoding="utf-8")
    block = VIDEO_START + hyperframes_videos(payload) + VIDEO_END
    if VIDEO_START in page and VIDEO_END in page:
        a, b = page.index(VIDEO_START), page.index(VIDEO_END) + len(VIDEO_END)
        new = page[:a] + block + page[b:]
    else:
        import re
        m = re.search(r'<div id="root"[^>]*data-composition-id[^>]*>', page) or re.search(r'<div id="root">', page)
        if not m:
            return False
        # Drop declarations an earlier export wrote without markers, then insert the current block.
        rest = re.sub(r'<video id="video-[^"]*" class="(?:scene|layer)"[^>]*></video>', "", page[m.end():])
        new = page[:m.end()] + block + rest
    if new != page:
        path.write_text(new, encoding="utf-8")
    return True


# HyperFrames on Windows paints only W-8 px of a portrait/square capture window (columns 1072-1079 of a 1080x1920
# frame came out black on every frame, whatever the screenshot path); its snapshot command, which opens a wider window,
# does not. Portrait and square pages are therefore authored on a canvas CAPTURE_MARGIN px wider than the frame (the
# picture stays at the left, unchanged), and the render/snapshot is cropped back to the frame.
CAPTURE_MARGIN = 16


def capture_margin(t):
    return CAPTURE_MARGIN if t["height"] >= t["width"] else 0


def hyperframes_html(payload):
    t=payload["timeline"]
    videos=hyperframes_videos(payload)
    pad=capture_margin(t)
    W,H=t["width"],t["height"]
    comp=f'data-composition-id="AgentVideo" data-width="{W+pad}" data-height="{H}" data-duration="{t["total_frames"]/30}" data-fps="30"'
    inner=VIDEO_START+videos+VIDEO_END
    root=(f'<div id="root" {comp}>{inner}</div>' if not pad else
          f'<div id="capture" {comp} style="position:relative;width:{W+pad}px;height:{H}px;background:#000"><div id="root">{inner}</div></div>')
    return f'''<!doctype html><html lang="vi"><head><meta charset="UTF-8"><script src="gsap.min.js"></script>
<script src="input.js"></script><script src="effects.js"></script><script src="design.js"></script>
<style>body{{margin:0;color:white;font-family:"Segoe UI",sans-serif}}#root{{position:relative;overflow:hidden;width:{t['width']}px;height:{t['height']}px}}
.scene,.frozen{{position:absolute;overflow:hidden}}.layer{{position:absolute}}.card{{box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;height:100%;padding:12% 9%;background:linear-gradient(135deg,#102e2c,#24524b)}}small{{font-size:32px;color:#a9e6c8;margin-bottom:32px}}h1{{font-size:72px;font-weight:700;line-height:1.22;margin:0}}.overlay{{position:absolute;box-sizing:border-box;padding:24px;border-radius:16px;white-space:pre-wrap}}.frozen{{inset:0}}.caption{{position:absolute;bottom:17%;left:8%;width:84%;text-align:center;font-size:{62 if t['width']>t['height'] else 50}px;font-weight:700;line-height:1.35}}.caption span{{background:rgba(10,22,26,.84);padding:8px 16px;box-decoration-break:clone}}</style></head><body>
{root}
<script>window.__timelines=window.__timelines||{{}};</script><script type="importmap">{{"imports":{{"three":"./three.module.js","three/addons/":"./three-addons/"}}}}</script><script src="hyper-runtime.js"></script></body></html>'''


MEDIA_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".glb", ".wav", ".mp3", ".m4a", ".ttf", ".otf", ".woff", ".woff2", ".exr", ".hdr"}


def _same_bytes(src, dst, want):
    """dst holds the asset's bytes: the same file (a hardlink place_file made) needs no hash; another file of another
    size is stale; only a same-sized copy is hashed (every snapshot hashed 2.9 GB of a long film's media, ~33 s)."""
    import os
    try:
        if os.path.samefile(src, dst):
            return True
    except OSError:
        return False
    return Path(dst).stat().st_size == Path(src).stat().st_size and sha256(dst) == want


def place_file(src, dst):
    """Put an asset at dst without duplicating bytes: hardlink on the same volume, copy otherwise. Any existing dst is
    unlinked first so a shared inode is never rewritten in place."""
    import os
    dst = Path(dst)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def link_media_copy(src, dst, *, follow_symlinks=True):
    """copytree copy_function: media and fonts become hardlinks (read-only by convention), code/json are real copies."""
    if Path(src).suffix.lower() in MEDIA_SUFFIXES:
        place_file(src, dst)
        return dst
    return shutil.copy2(src, dst, follow_symlinks=follow_symlinks)


def fit_tracking(timeline):
    """Letter-spacing entrances never reflow a title: each tracking/tracking_in effect carries the widest spacing its
    resting lines take in the layer box (measured on the bundled font), and the runtime clamps to it. Copies; the
    authored timeline is unchanged."""
    from .review import tracking_fit
    design,layers=timeline.get("design") or {},[]
    for l in timeline.get("layers",[]):
        fx=[e for e in l.get("effects") or [] if e.get("name") in ("tracking","tracking_in")]
        fit=tracking_fit(l,design,timeline["width"],timeline["height"]) if fx and l.get("text") else None
        if fit is not None:
            t=design.get("typography",{}).get(l.get("typography_role") or "")
            px=t["size"]*min(timeline["width"],timeline["height"])/1080 if t else l.get("font_size",60)
            l={**l,"effects":[{**e,"params":{**(e.get("params") or {}),"_fit_px":fit,"_fit_em":round(fit/px,4)}} if e in fx else e for e in l["effects"]]}
        layers.append(l)
    return {**timeline,"layers":layers}


HDR_TRANSFERS = {"arib-std-b67": "arib-std-b67", "smpte2084": "smpte2084"}
PROXY_RECIPE = "sdr709-hable-g30-cfr-v3"  # bump when the proxy encode changes


def keyframe_gap(path):
    """Longest interval between keyframes (s), from keyframes only (fast on long files); None if unreadable."""
    try:  # packet flags, no decoding (skip_frame=nokey still decodes every VP9 frame)
        out = command([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
                       "-of", "csv=p=0", str(path)], timeout=300)
        ts = sorted(float(t) for t, flags in (ln.split(",")[:2] for ln in out.splitlines() if ln.count(",") >= 1)
                    if "K" in flags and t.replace(".", "", 1).isdigit())
        end = float(probe(str(path))["format"].get("duration") or 0)
        ts = [0.0, *ts] if not ts or ts[0] > 0 else ts
        return max((b - a for a, b in zip(ts, [*ts[1:], max(end, ts[-1])])), default=0.0)  # the tail counts: one keyframe = whole clip
    except Exception:
        return None


def frame_jitter(path):
    """Spread of the intervals between frames (std / median); ~0 for constant-rate video (millisecond timestamps of
    WebM add ~2 %). A phone's variable rate shows here even when its average equals the nominal rate."""
    try:
        out = command([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)], timeout=300)
        ts = sorted(float(x) for x in out.split() if x.replace(".", "", 1).isdigit())
        d = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
        if len(d) < 10:
            return 0.0
        mean = sum(d) / len(d)
        return round((sum((x - mean) ** 2 for x in d) / len(d)) ** .5 / d[len(d) // 2], 3)
    except Exception:
        return 0.0


def frame_gaps(path):
    """Missing frames from packet times: intervals over 1.5x the usual one. A transfer with dropped frames (a 1921 film:
    157 gaps in 787 frames) is variable-rate; at each gap the engines chose different neighbours."""
    try:
        out = command([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)], timeout=300)
        ts = sorted(float(x) for x in out.split() if x.replace(".", "", 1).isdigit())
        d = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
        return sum(1 for x in d if x > 1.5 * d[len(d) // 2]) if len(d) >= 10 else 0
    except Exception:
        return 0


def engine_media(path, asset, max_width=None):
    """The file both engines play for a video asset: the original, or a cached H.264 SDR proxy with a keyframe every
    second when the source is HDR (one HLG phone clip made HyperFrames promote a whole render to BT.2020 with washed
    colours and overlays lost, while Remotion showed it as SDR), has sparse keyframes (browser seeks land on the
    wrong frame or freeze) or dropped frames (made constant-rate: each gap holds the frame before it, as a player
    shows it) or a variable frame rate (made constant 30 fps). max_width: the widest the picture is ever drawn (the
    canvas through its fit and zooms); a source over 15 % wider plays from a proxy at that width (67 shots cut from 4K
    pieces stalled HyperFrames' capture; nothing drawn is lost). Same timing; (path, reason or None)."""
    if (asset or {}).get("kind") != "video":
        return Path(path), None
    cache = store.DATA / "cache" / "engine-proxies"
    decided = cache / f"{asset['sha256'][:24]}.json"  # the scan once per source, not every refresh
    d = store.read_json(decided) if decided.is_file() else {}
    if "vfr" not in d:  # scanned before frame timing was read: scan again
        info = next((x for x in probe(str(path))["streams"] if x["codec_type"] == "video"), {})
        rate = lambda s: (lambda n, _, m: float(n) / float(m or 1) if float(m or 1) and float(n or 0) else 0.0)(*str(s or "0/1").partition("/"))
        r, avg = rate(info.get("r_frame_rate")), rate(info.get("avg_frame_rate"))
        # a phone's variable rate: a fine timebase (120) over ~27 frames a second; HyperFrames failed to normalise it
        vfr = bool(r and avg and abs(r - avg) / avg > .01) or frame_jitter(path) > .1
        d = {"trc": info.get("color_transfer"), "gap": keyframe_gap(path), "dropped": frame_gaps(path), "fps": info.get("r_frame_rate"), "vfr": vfr,
             "avg": round(avg, 3)}
        cache.mkdir(parents=True, exist_ok=True)
        store.write_json(decided, d)
    trc, gap, dropped, nominal, vfr = d.get("trc"), d.get("gap"), d.get("dropped") or 0, d.get("fps"), d.get("vfr")
    reason = "HDR " + trc if trc in HDR_TRANSFERS else (f"keyframes {gap:.1f} s apart" if gap and gap > 2.0 else
                                                        f"{dropped} dropped frames" if dropped >= 2 and nominal else
                                                        f"variable frame rate (~{d.get('avg')} fps)" if vfr else None)
    sw = int(asset.get("width") or 0)
    shrink = int(math.ceil(max_width / 2) * 2) if max_width and sw > 1.15 * max_width else None
    if shrink:
        reason = f"{reason}; " if reason else ""
        reason += f"drawn at most {shrink} px wide (source {sw})"
    if not reason:
        return Path(path), None
    hi = vfr and (d.get("avg") or 30) > 45  # a 60 fps phone clip keeps 60 (slow motion is built from this proxy)
    out = cache / f"{asset['sha256'][:24]}-{PROXY_RECIPE}{f'-w{shrink}' if shrink else ''}{'-r60' if hi else ''}.mp4"  # a new recipe never reuses an old proxy
    if out.is_file() and out.stat().st_size > 0:
        return out, reason
    import uuid
    tmp = out.with_name(f"{out.stem}.{uuid.uuid4().hex[:8]}.tmp.mp4")  # two renders at once never share a temp file
    vf = []
    if trc in HDR_TRANSFERS:  # linear light, Hable tone map from a 1000-nit peak, BT.709 SDR (as process_color does)
        vf = [f"zscale=pin=bt2020:tin={trc}:min=bt2020nc:rin=limited:p=bt709:t=linear:m=gbr:r=full:npl=100,format=gbrpf32le",
              "tonemap=tonemap=hable:desat=0:peak=10", "zscale=p=bt709:t=bt709:m=bt709:r=limited:dither=error_diffusion,format=yuv420p"]
    if shrink:
        vf.append(f"scale={shrink}:-2:flags=lanczos")
    if vfr:  # constant 30 (or 60) fps, each frame the one showing at its time
        vf.append(f"fps={60 if hi else 30}:round=down")
    elif dropped >= 2 and nominal:
        vf.append(f"fps={nominal}")  # the stream's nominal rate, constant; a gap repeats the frame before it
    command([FFMPEG, "-y", "-v", "error", "-i", str(path), *(["-vf", ",".join(vf)] if vf else []), "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-g", "30", "-keyint_min", "30", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
             "-colorspace", "bt709", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)], timeout=3600)
    tmp.replace(out)
    return out, reason


def grid(t):
    """Seconds on the 30 fps grid exactly as the engines round them (JS Math.round: halves go up; Python's round()
    sends 4.5 to 4, which put a whole HyperFrames shot one frame behind Remotion at source_start 0.15 s)."""
    return math.floor(t * 30 + .5) / 30


@functools.lru_cache(maxsize=256)
def _fps(path):
    v = next((x for x in probe(str(path))["streams"] if x["codec_type"] == "video"), {})
    num, _, den = str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").partition("/")
    return float(num) / float(den or 1) if float(den or 1) and float(num) else 30.0


def still_seek(path, t):
    """The seek that extracts the frame a player shows at t: the one whose interval covers t (largest pts <= t).
    FFmpeg's accurate seek returns the first frame at or after the seek point, so a 25 fps clip at 3.3 s gave the frame
    at 3.32 while Remotion showed 3.28 (a frozen car one frame further on); seek one source frame back plus 1 ms."""
    return max(0.0, t - 1 / _fps(str(path)) + .001)  # the frame rate is read once per file (avg rate: VFR can land one frame off)


RATE_RECIPE = "cover-30fps-x264crf16-shutter-v2"


def probe_duration(path):
    return float(probe(str(path))["format"].get("duration") or 0)


def _frame_count(path):
    """Video frames in an MP4 from its header (no decode); 0 for a file without a video stream."""
    try:
        v = next((x for x in probe(str(path))["streams"] if x["codec_type"] == "video"), {})
    except RuntimeError:
        return 0
    return int(v.get("nb_frames") or 0)


def rate_proxy(path, asset, s0, rate, frames):
    """An off-speed shot pre-timed for both engines: a 30 fps clip whose frame k is the source frame a player shows at
    s0 + k*rate/30 (the one whose interval covers that time, as Remotion picks it). Both engines then play it at 1x
    and agree frame for frame; left to its own extraction, HyperFrames showed the previous source frame on about a
    third of the frames of a 0.85x shot of a 24 fps clip. A fast-forward at a fractional step (2.5x: alternately 2 and 3
    source frames per output frame, read as judder) averages the source frames each output frame's 1/30 s covers,
    weighted by overlap, as a 360-degree shutter would; whole steps (2x of 30 fps) and slow motion stay sharp single
    frames. Assumes a constant frame rate (avg_frame_rate)."""
    import hashlib, subprocess
    v = next(x for x in probe(str(path))["streams"] if x["codec_type"] == "video")
    fps, start = _fps(str(path)), float(v.get("start_time") or 0)
    w, h = int(v["width"]) // 2 * 2, int(v["height"]) // 2 * 2
    cache = store.DATA / "cache" / "engine-proxies"
    key = hashlib.sha256(f"{asset['sha256']}|{Path(path).name}|{s0:.5f}|{rate:.6f}|{frames}|{RATE_RECIPE}".encode()).hexdigest()[:24]
    out = cache / f"rate-{key}.mp4"
    if out.is_file() and out.stat().st_size > 0:
        return out
    cache.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.tmp.mp4")
    index = lambda t: int(math.floor((t - start) * fps + 1e-6))
    want = [index(s0 + k * rate / 30) for k in range(frames)]
    size = w * h * 3 // 2
    dec = subprocess.Popen([FFMPEG, "-v", "error", "-ss", f"{still_seek(path, s0):.6f}", "-i", str(path), "-vf", f"crop={w}:{h}:0:0",
                            "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}", "-r", "30", "-i", "-",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-g", "30", "-pix_fmt", "yuv420p",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(tmp)],
                           stdin=subprocess.PIPE)
    step = rate * fps / 30  # source frames per output frame
    shutter = rate > 1 and abs(step - round(step)) > 1e-3
    try:
        cur, buf = index(s0) - 1, None  # the decoder starts on the frame covering s0
        if not shutter:
            for target in want:
                while cur < target:
                    b = dec.stdout.read(size)
                    if len(b) < size:  # past the clip's end: hold its last frame
                        break
                    buf, cur = b, cur + 1
                if buf is None:
                    raise RuntimeError("rate proxy: no frame decoded at the shot's source start")
                enc.stdin.write(buf)
        else:
            import numpy as np
            held, ended = {}, False

            def frame(i):  # source frame i (the last one past the clip's end)
                nonlocal cur, ended
                while cur < i and not ended:
                    b = dec.stdout.read(size)
                    if len(b) < size:
                        ended = True
                        break
                    cur += 1
                    held[cur] = np.frombuffer(b, np.uint8).astype(np.float32)
                if not held:
                    raise RuntimeError("rate proxy: no frame decoded at the shot's source start")
                return held[min(i, cur)]
            base = (s0 - start) * fps
            for k in range(frames):
                a, b = base + k * step, base + (k + 1) * step
                acc, total = None, 0.0
                for i in range(int(math.floor(a + 1e-6)), int(math.ceil(b - 1e-6))):
                    w = min(b, i + 1) - max(a, i)
                    if w > 1e-6:
                        f = frame(i) * w
                        acc, total = (f if acc is None else acc + f), total + w
                enc.stdin.write(np.clip(acc / total + .5, 0, 255).astype(np.uint8).tobytes())
                for i in [i for i in held if i < math.floor(b) - 1 and i != cur]:  # frames behind the window are done (the last stays: it is held past the end)
                    del held[i]
        enc.stdin.close()
        if enc.wait(timeout=900) != 0:
            raise RuntimeError("rate proxy: encode failed")
        tmp.replace(out)
    finally:
        dec.kill()
        if enc.poll() is None:
            enc.kill()
        if tmp.exists():
            tmp.unlink()
    return out


CADENCE_RECIPE = "mci-aobmc-bidir-30fps-x264crf16-v2"  # v2: ghosting risk measured first, fast or occluding motion falls back to nearest frames
# fall back from interpolation above either: px per frame at 1920 wide (median of the top 5 % moving pixels), share of
# pixels whose forward and backward flows disagree by over 1.5 px at 320 wide (what one frame shows and the next hides)
FLOW_MAX_MOTION, FLOW_MAX_OCCLUSION = 12.0, .04
NATIVE_MIN_RATE = .85  # at or above it, a shot that would ghost plays its own frames instead of a blurring blend
_LOGGED = set()


def off_cadence(fps):
    """A rate the 30 fps timeline cannot show evenly: neither a multiple (60) nor a divisor (15) of 30."""
    return bool(fps) and abs(fps / 30 - round(fps / 30)) > .01 and abs(30 / fps - round(30 / fps)) > .01


def cadence_risk(path, s0, seconds, width=320, max_pairs=48):
    """How much a window would ghost under motion interpolation, from Farneback flow between consecutive source frames
    at 320 px wide (at most max_pairs pairs spread over the window; the worst pair counts): top_motion_px, the median
    flow magnitude of the top 5 % moving pixels in px per frame at 1920 wide (a drone glide 2-6, a man walking past
    the camera 20-40); occlusion_share, the share of pixels whose forward and backward flows disagree by over 1.5 px
    (covered or uncovered between the frames: the interpolator blends them with what is behind, round 12's walking man
    wearing a hat from the background). Both 0 when the window holds a single frame."""
    import cv2
    import numpy as np
    w0, h0 = display_size(path)
    h = int(round(width * h0 / w0 / 2) * 2)
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, s0):.6f}", "-t", f"{seconds + 1 / 15:.6f}", "-i", str(path), "-vf",
                          f"scale={width}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, width)
    out = {"top_motion_px": 0.0, "occlusion_share": 0.0, "pairs": 0}
    if len(fr) < 2:
        return out
    gx, gy = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(h, dtype=np.float32))
    for i in sorted({int(x) for x in np.linspace(0, len(fr) - 2, min(max_pairs, len(fr) - 1))}):
        a, b = fr[i], fr[i + 1]
        fwd = cv2.calcOpticalFlowFarneback(a, b, None, .5, 3, 15, 3, 5, 1.2, 0)
        bwd = cv2.calcOpticalFlowFarneback(b, a, None, .5, 3, 15, 3, 5, 1.2, 0)
        mag = np.hypot(fwd[..., 0], fwd[..., 1])
        top = float(np.median(mag[mag >= np.percentile(mag, 95)])) * 1920 / width
        back = [cv2.remap(bwd[..., k], gx + fwd[..., 0], gy + fwd[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) for k in (0, 1)]
        occl = float(np.mean(np.hypot(fwd[..., 0] + back[0], fwd[..., 1] + back[1]) > 1.5))
        out = {"top_motion_px": round(max(out["top_motion_px"], top), 2), "occlusion_share": round(max(out["occlusion_share"], occl), 4),
               "pairs": out["pairs"] + 1}
    return out


def cadence_decision(proxy):
    """What a cadence proxy did, from the note beside it: mode "flow" (interpolated), "blend" (fell back to blending the
    two nearest frames by time, slow motion only), "native" (no proxy: the shot plays its own frames) or "nearest" (an
    older fallback that repeated frames), with the risk it measured; a proxy without a note (an older cache) counts as
    flow. None (no proxy was made) reads as native."""
    if proxy is None:
        return {"mode": "native"}
    try:
        return json.loads(Path(proxy).with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": "flow"}


def cadence_log(shot_id, proxy):
    """The render log line for a flow shot that could not be interpolated, printed once per shot and proxy (stderr: stdout
    is the MCP channel) and returned; None when there is nothing to say."""
    d = cadence_decision(proxy)
    if d.get("mode") not in ("nearest", "blend", "native") or (shot_id, str(proxy)) in _LOGGED:
        return None
    _LOGGED.add((shot_id, str(proxy)))
    if d["mode"] == "native":
        msg = f"[cadence] shot {shot_id}: frame_sampling flow plays its own frames, interpolation would ghost and a blend would blur"
    else:
        how = "blended source frames" if d["mode"] == "blend" else "nearest source frames"
        msg = (f"[cadence] shot {shot_id}: frame_sampling flow fell back to {how}, interpolation would ghost "
               f"(top motion {d.get('top_motion_px', 0):.0f} px/frame at 1920 wide, limit {FLOW_MAX_MOTION:.0f}; occlusion "
               f"{100 * d.get('occlusion_share', 0):.1f} %, limit {100 * FLOW_MAX_OCCLUSION:.0f} %)")
    print(msg, file=sys.stderr)
    return msg


def cadence_proxy(path, asset, s0, frames, max_width=None, rate=1.0, dedupe=False):
    """A 1x shot of an off-cadence source (24, 25, 50 fps) re-timed to the timeline by motion-compensated interpolation
    (FFmpeg minterpolate: bidirectional estimation, overlapped blocks): frame k shows the picture at s0 + k*rate/30.
    Played as is, a 25 fps clip shows every fifth frame twice, a judder on a slow glide; slow motion (rate < 1) from
    nearest frames repeats them unevenly (1, 2, 1, 2 at 0.7x), so it is interpolated too, from any source rate.
    Interpolation can smear thin detail and fast occlusions; about 2 frames a second at 1080p, so it runs on the shot's
    window only, cached. The window's ghosting risk is measured first (cadence_risk): past FLOW_MAX_MOTION or
    FLOW_MAX_OCCLUSION the proxy blends the two source frames around each output time instead (FFmpeg framerate, a soft
    double image on fast motion rather than the repeats that read as judder: round 13 measured 169 of 205 archive
    windows past the limit, 1-2-1-2 stutter on all of them), still a per-shot proxy so both engines agree frame for
    frame; the decision sits beside the proxy
    (cadence_decision) and refresh_payload logs it once per shot. dedupe: the file repeats frames inside a constant rate
    (a 25 fps or film source conformed to 30 by duplication, review.repeated_frames): the repeats are dropped first
    (mpdecimate keeps the remaining frames at their own times), so the interpolation runs between true pictures.
    Returns None where the shot should play its own frames: interpolation would ghost and the shot runs at NATIVE_MIN_RATE
    or faster. The blend cost a fifth cut 40 % of its sharpness on 154 of 257 shots (median Laplacian 57 against 93), which
    the owner saw as blur; one repeated frame in six at 1x is the smaller fault. Only real slow motion still blends."""
    import hashlib
    v = next(x for x in probe(str(path))["streams"] if x["codec_type"] == "video")
    start = float(v.get("start_time") or 0)
    w = int(v["width"])
    width = min(w, int(math.ceil((max_width or 1920) / 2) * 2), 3840)
    cache = store.DATA / "cache" / "engine-proxies"
    slow = (f"|x{rate:.6f}" if rate != 1 else "") + ("|dedupe2" if dedupe else "")  # 1x keys stay as they were (cached proxies remain valid)
    key = hashlib.sha256(f"{asset['sha256']}|{Path(path).name}|{s0:.5f}|{frames}|{width}|{CADENCE_RECIPE}{slow}".encode()).hexdigest()[:24]
    out = cache / f"cad-{key}.mp4"
    note = out.with_suffix(".json")
    # frames the window can give: all of them when a still tail is padded (dedupe), else up to the source's end (a shot's
    # window carries the next shot's dissolve and may run past it)
    dur = float(v.get("duration") or probe_duration(path) or 0) - s0
    expect = frames if dedupe or not dur else max(1, min(frames, int(dur * 30 / rate) - 2))
    known = cadence_decision(out) if note.is_file() else {}
    if known.get("mode") in ("native", "blend") and rate >= NATIVE_MIN_RATE:
        if known["mode"] == "blend":  # made before blends gave way to the shot's own frames
            store.write_json(note, {**known, "mode": "native"})
        return None
    if out.is_file() and known and known.get("mode") != "nearest" and _frame_count(out) >= expect - 1:
        return out  # an older nearest-frame fallback is made again as a blend; an empty or short file is made again
    cache.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.{threading.get_ident()}.tmp.mp4")
    a = start + s0  # absolute source time of frame 0 (-copyts keeps the source's timestamps through the filters)
    risk = cadence_risk(path, s0, frames * rate / 30)
    flow = risk["top_motion_px"] <= FLOW_MAX_MOTION and risk["occlusion_share"] <= FLOW_MAX_OCCLUSION
    if not flow and rate >= NATIVE_MIN_RATE:
        store.write_json(note, {"mode": "native", **risk, "limits": {"top_motion_px": FLOW_MAX_MOTION, "occlusion_share": FLOW_MAX_OCCLUSION}})
        return None
    from fractions import Fraction
    # frames per source second, spread to 1/30 s each; slow motion then declares 30 fps again, or the encoder keeps the
    # interpolated rate and pads the shot with repeats. Given as an exact fraction: `framerate` turned 31.347962 into
    # 772163/24632 and wrote one frame (round 13, ten empty proxies at 0.84-0.98x)
    Fq = (Fraction(30) / Fraction(f"{rate:.6f}")).limit_denominator(10000)
    F, Fs = float(Fq), f"{Fq.numerator}/{Fq.denominator}"
    vf = ([f"scale={width}:-2:flags=lanczos"] if width < w else []) + (["mpdecimate=hi=768:lo=320:frac=0.33"] if dedupe else []) + [
        f"minterpolate=fps={Fs}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" if flow else f"framerate=fps={Fs}:interp_start=0:interp_end=255:scene=100",
        f"trim=start={a - .25 / F:.6f}", *(["setpts=PTS-STARTPTS"] if rate == 1 else [f"setpts=(PTS-STARTPTS)/{rate:.6f}", "fps=30"])]
    if dedupe:  # a still tail is all repeats: mpdecimate drops it and the interpolation stops at the last moving frame
        vf.append("tpad=stop_mode=clone:stop_duration=4")
    if vf[-1] != "fps=30":  # FFmpeg 7.1's MP4 muxer marks frames off a regular grid as discarded (15 of 60, 39 of 40 written)
        vf.append("fps=30")
    try:
        command([FFMPEG, "-y", "-v", "error", "-ss", f"{max(0.0, s0 - 1.0):.6f}", "-copyts", "-i", str(path), "-vf", ",".join(vf),
                 "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-g", "30", "-pix_fmt", "yuv420p",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(tmp)], timeout=3600)
        got = _frame_count(tmp)
        if got < expect - 1:  # FFmpeg can exit 0 having written nothing; a short proxy would end the shot early
            raise RuntimeError(f"cadence proxy of {Path(path).name} at {s0:.3f} s ({rate:.3f}x) wrote {got} of {expect} frames")
        tmp.replace(out)
        store.write_json(note, {"mode": "flow" if flow else "blend", **risk,
                                "limits": {"top_motion_px": FLOW_MAX_MOTION, "occlusion_share": FLOW_MAX_OCCLUSION}})
    finally:
        if tmp.exists():
            tmp.unlink()
    return out


def drawn_widths(timeline, pid):
    """Per video asset, the widest its picture is drawn in source pixels' terms: the shot or layer box through its fit,
    times every zoom it takes (focus_zoom, zoom_in, impact_zoom, the start of a zoom_out, scale keys above 1, the 7.5 %
    push of motion). Assets without a size are left out (no downscale)."""
    W, H = timeline["width"], timeline["height"]
    out = {}
    by_id = {a["id"]: a for a in store.assets(pid)}  # one read: find_asset per item re-read every asset (2.6 s on a long film)
    for item in [*timeline.get("shots", []), *timeline.get("layers", [])]:
        aid = item.get("asset_id")
        if not aid:
            continue
        a = by_id.get(aid)
        if a is None:
            try:
                a = store.find_asset(pid, aid)
            except Exception:
                continue
        sw, sh = a.get("width"), a.get("height")
        if a.get("kind") != "video" or not sw or not sh:
            continue
        bw, bh = (W, H) if "beat_id" in item else (item.get("width", 1) * W, item.get("height", 1) * H)
        k = max(bw / sw, bh / sh) if item.get("fit", "cover") == "cover" else min(bw / sw, bh / sh)
        zoom = 1.075 if item.get("motion") in ("push", "pull", "pan") and item.get("fit", "cover") != "contain" else 1.0
        for e in item.get("effects") or []:
            if e.get("name") in ("focus_zoom", "zoom_in", "zoom_out", "impact_zoom"):
                zoom *= 1 + max(0.0, float((e.get("params") or {}).get("amount", .1)))
        keys = item.get("keyframes") or {}
        zoom *= max([1.0] + [float(q["value"]) for q in keys.get("scale", [])]) * max([1.0] + [float(q["value"]) for q in keys.get("scale_x", [])])
        out[aid] = max(out.get(aid, 0), sw * k * zoom)
    return out


def _poster(path, at, out):
    """One frame of a shot as its still. A file whose last frames do not decode at the seek point (an interpolated proxy
    whose window ran out of source frames writes nothing: FFmpeg then fails opening the JPEG encoder) gets a second
    try half a second earlier in full-range 4:2:0; the error names the file."""
    try:
        command([FFMPEG, "-y", "-v", "error", "-ss", still_seek(path, at), "-i", path, "-frames:v", "1", out], timeout=90)
    except RuntimeError as first:
        try:
            command([FFMPEG, "-y", "-v", "error", "-ss", f"{max(0.0, at - .5):.4f}", "-i", path, "-frames:v", "1", "-pix_fmt", "yuvj420p", out], timeout=90)
        except RuntimeError:
            raise RuntimeError(f"no still at {at:.3f} s in {path}: {str(first)[:300]}") from first


def refresh_payload(pid, source, timeline, config):
    """Refresh data/assets in a render snapshot without rewriting authored source."""
    public=source/"public"
    public.mkdir(exist_ok=True)
    media={}
    # Off-speed video shots play a pre-timed 30 fps clip at 1x in both engines (rate_proxy), and 1x shots asking for
    # frame_sampling "flow" from an off-cadence source a motion-interpolated one (cadence_proxy): a virtual asset per shot.
    virtual,shots={},[]
    widths0=drawn_widths(timeline,pid)
    def extra_frames(i):
        nx=timeline["shots"][i+1] if i+1<len(timeline["shots"]) else None
        return nx["transition"]["duration_frames"] if nx and (nx.get("transition") or {}).get("mode")=="live" else 0
    flows={}
    for i,s in enumerate(timeline["shots"]):
        rate=s.get("playback_rate",1) or 1
        if s.get("asset_id") and s.get("frame_sampling")=="flow" and rate<=1 and not s.get("freeze"):
            a=store.find_asset(pid,s["asset_id"])
            if a["kind"]=="video" and not a.get("alpha"):
                src,_=engine_media(safe_asset_path(pid,s["asset_id"]),a)
                from .review import repeated_frames
                n=s["end_frame"]-s["start_frame"]+extra_frames(i)+1
                baked=repeated_frames(str(src),float(s.get("source_start",0)),min(2.0,max(.5,n*rate/30)))>=.1  # duplicates inside the file
                if rate<1 or baked or off_cadence(_fps(str(src))):  # slow motion is interpolated from any source rate
                    flows[i]=(src,a,grid(s.get("source_start",0)),n,widths0.get(s["asset_id"]),rate,baked)
    if flows:  # minterpolate is single-threaded: several windows at once, as many as memory allows
        from concurrent.futures import ThreadPoolExecutor
        # one 4K-decoded minterpolate at 1920 wide held 1.4-1.7 GB (round 13, 28 windows): budget 2 GB per worker
        # from the memory free now, so six at once cannot push a 32 GB machine into its pagefile
        try:
            import psutil
            room=int(psutil.virtual_memory().available//(2*1024**3))
        except Exception:
            room=6
        with ThreadPoolExecutor(max_workers=max(1,min(6,(os.cpu_count() or 4)//2,room))) as ex:
            flows={i:f for i,f in zip(flows,ex.map(lambda j:cadence_proxy(*j),flows.values()))}
    for i,s in enumerate(timeline["shots"]):
        rate=s.get("playback_rate",1) or 1
        if i in flows and flows[i] is None:
            cadence_log(s["id"],None)  # interpolation would ghost: the shot plays its own frames (a rate proxy below if off-speed)
        if flows.get(i):
            proxy=flows[i]
            d=cadence_decision(proxy)
            cadence_log(s["id"],proxy)
            vid=f"{s['asset_id']}-c{proxy.stem[4:16]}"
            virtual[vid]={"kind":"video","sha256":sha256(proxy),"path":proxy,"alpha":False,"duration":probe_duration(proxy),"cadence":d}
            s={**s,"asset_id":vid,"source_start":0,"playback_rate":1}  # pre-timed: slow motion is in the proxy
        elif s.get("asset_id") and rate!=1 and not s.get("freeze"):
            a=store.find_asset(pid,s["asset_id"])
            if a["kind"]=="video" and not a.get("alpha"):
                src,_=engine_media(safe_asset_path(pid,s["asset_id"]),a)
                proxy=rate_proxy(src,a,grid(s.get("source_start",0)),rate,s["end_frame"]-s["start_frame"]+extra_frames(i)+1)
                vid=f"{s['asset_id']}-r{proxy.stem[5:17]}"
                virtual[vid]={"kind":"video","sha256":sha256(proxy),"path":proxy,"alpha":False,"duration":probe_duration(proxy)}
                s={**s,"asset_id":vid,"source_start":0,"playback_rate":1}
        shots.append(s)
    layers=[]
    for l in timeline.get("layers",[]):  # video layers asking for flow get the same proxies (a footage frame on a map)
        rate=l.get("playback_rate",1) or 1
        if l.get("kind")=="video" and l.get("asset_id") and l.get("frame_sampling")=="flow" and rate<=1:
            a=store.find_asset(pid,l["asset_id"])
            if a["kind"]=="video" and not a.get("alpha"):
                src,_=engine_media(safe_asset_path(pid,l["asset_id"]),a)
                from .review import repeated_frames
                n=l["end_frame"]-l["start_frame"]+1
                baked=repeated_frames(str(src),float(l.get("source_start",0)),min(2.0,max(.5,n*rate/30)))>=.1
                if rate<1 or baked or off_cadence(_fps(str(src))):
                    proxy=cadence_proxy(src,a,grid(l.get("source_start",0)),n,widths0.get(l["asset_id"]),rate,baked)
                    cadence_log(l["id"],proxy)
                    if proxy:
                        vid=f"{l['asset_id']}-c{proxy.stem[4:16]}"
                        virtual[vid]={"kind":"video","sha256":sha256(proxy),"path":proxy,"alpha":False,"duration":probe_duration(proxy),"cadence":cadence_decision(proxy)}
                        l={**l,"asset_id":vid,"source_start":0,"playback_rate":1}
        layers.append(l)
    timeline={**timeline,"shots":shots,"layers":layers}
    visuals=[*timeline["shots"],*timeline.get("layers",[]),*timeline.get("audio_clips",[])]
    visuals += [{"asset_id":config.get(k)} for k in ("music_id","narration_id") if config.get(k)]
    for layer in timeline.get("layers",[]):
        if layer.get("kind")=="scene3d":
            d=layer.get("data",{})
            visuals += [{"asset_id":o.get(k)} for o in d.get("objects",[]) for k in ("texture","bump_texture","emissive_texture","alpha_texture","displacement_texture","model") if o.get(k)]
            visuals += [{"asset_id":d.get(k)} for k in ("background_texture","environment_texture") if d.get(k)]
    widths=drawn_widths(timeline,pid)
    by_id={a["id"]:a for a in store.assets(pid)}
    for aid in {s.get("asset_id") for s in visuals}-{None}:
        if aid in virtual:
            asset=virtual[aid];path,proxied=asset["path"],None
        else:
            asset=by_id.get(aid) or store.find_asset(pid,aid);path=safe_asset_path(pid,aid)
            path,proxied=engine_media(path,asset,widths.get(aid)) if asset["kind"]=="video" and not asset.get("alpha") else (path,None)
        name=aid+path.suffix
        target=public/name
        want=asset["sha256"] if not proxied else None
        if not target.exists() or (want and not _same_bytes(path,target,want)) or (proxied and target.stat().st_size!=path.stat().st_size):
            place_file(path,target)
        media[aid]={"src":name,"kind":asset["kind"],"sha256":asset["sha256"],"alpha":asset.get("alpha",False),"posters":{},**({"proxy":proxied} if proxied else {}),
                    **({"cadence":asset["cadence"]} if asset.get("cadence") else {})}  # the flow/nearest decision stays in the payload
        if asset["kind"]=="video":
            for s in timeline["shots"]:
                if s.get("asset_id")!=aid:
                    continue
                # Stable filename is internal; ID is never interpolated into a filesystem path.
                import hashlib
                # the shot's last shown frame: a freeze shows its first frame throughout. Past the clip's end there is no
                # frame (25.147 s found nothing in a 25.18 s, 24 fps clip): clamp half a source frame inside the end;
                # still_seek steps one frame back from there, onto the last frame (a 0.1 s margin had shown a frame two
                # frames early under a dissolve)
                s0=grid(s["source_start"])  # the engines start media on the 30 fps grid
                at=s0 if s.get("freeze") else min(s0+(s["end_frame"]-s["start_frame"]-1)*s.get("playback_rate",1)/30,
                                                   max(0.0,(asset.get("duration") or 1e9)-.5/_fps(str(path))))
                name="poster-"+hashlib.sha256(f"{s['id']}|{asset['sha256']}|{at:.4f}".encode()).hexdigest()[:20]+".jpg"  # named by what it shows
                if not (public/name).is_file():_poster(path,at,public/name)
                media[aid]["posters"][s["id"]]=name
                if s.get("freeze"):  # the held still of a freeze frame: its first source frame
                    fname="freeze-"+hashlib.sha256(f"{s['id']}|{asset['sha256']}|{s0:.4f}".encode()).hexdigest()[:20]+".png"
                    if not (public/fname).is_file():command([FFMPEG,"-y","-v","error","-ss",still_seek(path,s0),"-i",path,"-frames:v","1",public/fname],timeout=90)
                    media[aid]["posters"]["freeze:"+s["id"]]=fname
    if any(o.get("model") for l in timeline.get("layers",[]) if l.get("kind")=="scene3d" for o in l.get("data",{}).get("objects",[])):
        # Draco-compressed glTF needs three's local decoder; no CDN at render time.
        (public/"draco").mkdir(exist_ok=True)
        for name in ("draco_decoder.js","draco_decoder.wasm","draco_wasm_wrapper.js"):
            target=public/"draco"/name
            if not target.exists():shutil.copyfile(ENGINES/"node_modules/three/examples/jsm/libs/draco/gltf"/name,target)
    from .design_library import embed_fonts
    timeline=fit_tracking(timeline)
    payload={"timeline":timeline,"config":config,"media":media,"fonts":embed_fonts(source,timeline)}
    store.write_json(source/"input.json",payload)
    sync_video_declarations(source,payload)
    (source/"input.js").write_text("window.EditVideoInput="+json.dumps(payload,ensure_ascii=False)+";",encoding="utf-8")
    if (source/"source-meta.json").exists():
        meta=store.read_json(source/"source-meta.json")
        meta.update(data_revision=store.get_project(pid)["revision"],data_timeline_hash=store.read_json(store.folder(pid)/"plan/plan-meta.json")["timeline_hash"])
        store.write_json(source/"source-meta.json",meta)
    return payload


def scaffold(pid, engine="remotion", overwrite=False):
    if engine not in ("remotion", "hyperframes"):
        raise ValueError("engine: remotion|hyperframes")
    project = store.get_project(pid)
    plan = store.folder(pid)/"plan"
    meta = store.read_json(plan/"plan-meta.json")
    if meta["revision"] != project["revision"]:
        raise ValueError("Plan stale; plan again first")
    source = store.folder(pid)/"code"/engine
    if source.exists() and not overwrite:
        raise ValueError("Code exists; edit existing files or explicitly overwrite=True to rebuild from timeline")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.busy(db,pid):
            raise ValueError("Project busy")
        if store.get_project(pid)["revision"]!=project["revision"]:
            raise ValueError("Revision conflict; read project and export again")
        source.mkdir(parents=True,exist_ok=True)
        public = source/"public"
        public.mkdir(exist_ok=True)
        timeline = store.read_json(plan/"timeline.json")
        payload=refresh_payload(pid,source,timeline,project["config"])
        shutil.copyfile(ENGINES/"effects.js",source/"effects.js")
        shutil.copyfile(ENGINES/"effects.js",source/"effects.cjs")
        shutil.copyfile(ENGINES/"design.js",source/"design.js")
        shutil.copyfile(ENGINES/"design.js",source/"design.cjs")
        shutil.copyfile(ENGINES/"scene3d.js",source/"scene3d.js")
        shutil.copyfile(ENGINES/"Scene3D.tsx",source/"Scene3D.tsx")
        shutil.copyfile(ENGINES/'node_modules/three/build/three.module.js',source/'three.module.js')
        shutil.copyfile(ENGINES/'node_modules/three/build/three.core.js',source/'three.core.js')
        # Local three addons for HTML importmap "three/addons/" (studio environment + bloom post chain).
        for addon in THREE_ADDONS:
            target=source/'three-addons'/addon;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ENGINES/'node_modules/three/examples/jsm'/addon,target)
        if engine == "remotion":
            shutil.copyfile(ENGINES/"AgentVideo.tsx",source/"index.tsx")
            shutil.copyfile(ENGINES/"render-remotion.mjs",source/"render.mjs")
        else:
            (source/"index.html").write_text(hyperframes_html(payload),encoding="utf-8")
            shutil.copyfile(ENGINES/"hyper-runtime.js",source/"hyper-runtime.js")
            shutil.copyfile(ENGINES/"node_modules"/"gsap"/"dist"/"gsap.min.js",source/"gsap.min.js")
        shutil.copyfile(ENGINES/"package.json",source/"package.json")
        shutil.copyfile(ENGINES/"package-lock.json",source/"package-lock.json")
        store.write_json(source/"source-meta.json",{"engine":engine,"runtime_version":2,"revision":project["revision"],"timeline_hash":meta["timeline_hash"]})
    return {"directory":str(source),"entry":str(source/("index.tsx" if engine=="remotion" else "index.html")),
            "input":str(source/"input.json"),"revision":project["revision"],
            "instructions":"Edit entry/runtime directly. Runtime v2 refreshes timeline/config/media in isolated render snapshots; custom source edits survive timeline patches. input.json/input.js are generated data."}


def hyperframes_low_memory(args, env):
    """The same HyperFrames render in its safe profile: --workers dropped for --low-memory-mode (one worker, screenshot
    capture, streaming encode) and segmented capture, which recycles the browser between segments."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if str(a) == "--workers":
            skip = True
            continue
        out.append(a)
    return [*out, "--low-memory-mode"], {**env, "HF_SEGMENTED_CAPTURE": "true"}


def render(pid, timeline, config, work, quality, cancelled, progress):
    engine = config.get("renderer", "remotion")
    validate_sources(pid,timeline,store.assets(pid))
    source = store.folder(pid)/"code"/engine
    if not source.exists():
        raise ValueError("Export code first with editvideo_export_code")
    meta = store.read_json(source/"source-meta.json")
    current = store.read_json(store.folder(pid)/"plan"/"plan-meta.json")
    if meta.get("runtime_version",1)<2 and meta["timeline_hash"] != current["timeline_hash"]:
        raise ValueError("Timeline changed; export code with overwrite=True, then reapply custom code changes")
    authored_config = store.read_json(source/"input.json")["config"]
    authored_timeline=store.read_json(source/"input.json")["timeline"]
    if engine=="hyperframes" and any(authored_timeline.get(k)!=getattr(timeline,k) for k in ("width","height","total_frames","fps")):
        raise ValueError("Hyperframes root timebase/profile changed by replanning; preserve custom source and export again to update root metadata")
    if meta.get("runtime_version",1)<2 and engine=="hyperframes" and any(authored_config.get(k)!=config.get(k) for k in ("title","captions")):
        raise ValueError("Hyperframes visual settings changed; export code again before rendering")
    snapshot = work/"source"
    shutil.copytree(source,snapshot,copy_function=link_media_copy)
    if meta.get("runtime_version",1)>=2:
        refresh_payload(pid,snapshot,timeline.model_dump(),config)
    hashes = {str(p.relative_to(snapshot)):sha256(p) for p in snapshot.rglob("*") if p.is_file()}
    store.write_json(work/"source-manifest.json",hashes)
    if engine == "remotion":
        payload = store.read_json(snapshot/"input.json")
        # refresh_payload already wrote the render timeline (off-speed shots on their pre-timed clips, tracking fitted);
        # older exports without it get the project timeline
        payload.update(config=config,**({} if meta.get("runtime_version",1)>=2 else {"timeline":fit_tracking(timeline.model_dump())}))
        store.write_json(snapshot/"input.json",payload)
        hashes["input.json"] = sha256(snapshot/"input.json")
        store.write_json(work/"source-manifest.json",hashes)
    progress(35,f"Rendering {engine} code snapshot")
    ensure_free(work, 1.5)
    if engine == "remotion":
        args = ["node",ENGINES/"render-remotion.mjs",snapshot,work/"visual.mp4",quality]
    else:
        args = ["node",ENGINES/"node_modules"/"hyperframes"/"bin"/"hyperframes.mjs","render",snapshot,
                "--output",work/"visual.mp4","--fps","30","--workers",os.environ.get("EDITVIDEO_RENDER_CONCURRENCY","6"),"--quality","draft" if quality=="preview" else "delivery",
                *([] if quality=="preview" else ["--crf","18"]),  # Remotion's CRF: its delivery preset had written twice the bitrate for the same picture
                # HyperFrames loads every extracted video frame before its player is ready: ~0.09 s a frame measured (1
                # shot of 288 frames 36 s, 5 shots 62 s), so a 128 s film cut from video needs minutes, not the default 45 s
                "--player-ready-timeout",str(min(1800000,60000+150*sum(s.end_frame-s.start_frame for s in timeline.shots if s.asset_id)+2000*len(timeline.layers or [])))]
    render_temp=store.engine_temp()  # short: the browser profile below it stays under Windows' 260-character limit
    env={**engine_env(pid),'TEMP':str(render_temp),'TMP':str(render_temp)}
    if engine=="hyperframes":
        # HyperFrames' Node heap grows with the frames captured (a 29 s 1096x1920 reel from a 1080p VP9 take ran out
        # of Node's default ~4 GB around frame 550-740, with 6 or 3 workers alike). Never below the default; up to 8 GB.
        free=available_memory_mb() or 8192
        env["NODE_OPTIONS"]=f"--max-old-space-size={int(min(8192,max(4096,free*.4)))}"
    def written():
        """The HyperFrames CLI wrote this 164 s film in 6 minutes and never exited (its job hit the 82-minute
        timeout with the file complete): the render is done when visual.mp4 stopped growing and covers the timeline."""
        out_f=work/"visual.mp4"
        if engine!="hyperframes" or not out_f.is_file():
            return False
        size=out_f.stat().st_size
        if size!=written.size:
            written.size=size
            return False
        try:
            return float(probe(str(out_f))["format"]["duration"])>=timeline.total_frames/30-.2
        except Exception:
            return False
    written.size=-1
    try:
        # Software WebGL fallback runs ~2-4 fps, so allow about 1 s per frame before calling the render hung.
        try:
            out = command(args,cwd=ENGINES,cancelled=cancelled,log=work/"engine.log",timeout=max(1800,timeline.total_frames),env=env,done=written)
        except Exception as error:
            log=(work/"engine.log").read_text(encoding="utf-8",errors="replace")[-20000:] if (work/"engine.log").exists() else ""
            code=str(error).split("\n",1)[0]
            crashed="heap out of memory" in log+str(error) or (code.startswith("exit code") and code not in ("exit code 1","exit code 2"))
            # Six browsers each loading nine 1080p clips did not get the page ready in 45 s ("Starting browsers 0/6"):
            # not a broken composition (one-browser snapshots of it work), so the one-worker profile is tried too.
            starved="__hf not ready" in log or "Starting browsers (0/" in log
            if engine!="hyperframes" or not (crashed or starved) or cancelled():
                raise
            # Out of heap, killed mid-capture or starved at start: once more in HyperFrames' own safe profile (one
            # worker, screenshot capture) with segmented capture, which recycles the browser between segments.
            args,env=hyperframes_low_memory(args,env)
            progress(36,"HyperFrames "+("could not start its parallel browsers" if starved and not crashed else "ran out of memory")+"; retrying in low-memory segmented mode")
            (work/"engine.log").replace(work/"engine-oom.log")
            written.size=-1
            out = command(args,cwd=ENGINES,cancelled=cancelled,log=work/"engine.log",timeout=max(1800,timeline.total_frames)*3,env=env,done=written)
    finally:
        shutil.rmtree(render_temp,ignore_errors=True)  # this run's temp: browser profile + Remotion's downloaded copies of every video
    from .media import probe
    stream = next(s for s in probe(work/"visual.mp4")["streams"] if s["codec_type"]=="video")
    width,height = stream["width"],stream["height"]
    if engine=="hyperframes" and width==timeline.width+CAPTURE_MARGIN and height==timeline.height:
        # Portrait/square capture margin (see capture_margin): crop back to the frame, visually lossless.
        cropped=work/"visual-cropped.mp4"
        command([FFMPEG,"-y","-v","error","-i",work/"visual.mp4","-vf",f"crop={timeline.width}:{timeline.height}:0:0","-c:v","libx264",
                 "-preset","medium","-crf","14","-pix_fmt","yuv420p","-movflags","+faststart","-an",cropped],cancelled=cancelled,log=work/"render.log")
        cropped.replace(work/"visual.mp4")
        width=timeline.width
    # Every engine output on an exact 1/30 s grid: Remotion's chunk concat had given frames 1200, 1800 and 3000 of a
    # film the previous frame's timestamp (the picture ran 1-3 frames ahead of the sound). Rebuilt by frame index.
    from .media import frame_grid, rebuild_cfr
    grid=frame_grid(work/"visual.mp4",30)
    timing_repair=None
    if grid["irregular_count"] or grid["frames"]!=timeline.total_frames:
        progress(78,f"Rebuilding frame timestamps ({grid['irregular_count']} irregular, {grid['frames']} frames)")
        timing_repair={"before":grid,"after":rebuild_cfr(work/"visual.mp4",30,cancelled)}
    progress(80,"Mixing narration and ducked music")
    mix_audio(pid,config,work,timeline.total_frames/30,cancelled)
    final = work/("preview.mp4" if quality=="preview" else "final.mp4")
    video_args = ["-c:v","copy"]
    if quality=="preview" and engine=="hyperframes":
        scale = 640/max(width,height)
        width,height = round(width*scale/2)*2,round(height*scale/2)*2
        video_args = ["-vf",f"scale={width}:{height}","-c:v","libx264","-preset","fast","-crf","20"]
    command([FFMPEG,"-y","-v","error","-i",work/"visual.mp4","-i",work/"mix.wav","-map","0:v","-map","1:a",
             *video_args,"-c:a","aac","-b:a","192k","-ar","48000","-t",timeline.total_frames/30,"-movflags","+faststart",final],cancelled=cancelled)
    if quality == 'final':
        from .renderer import encoded_audio_guard
        encoded_audio_guard(final, timeline.audio_mix.true_peak_db, work, cancelled)
    report = verify(final,timeline,width,height,cancelled)
    report.update(engine=engine,timing_method=timeline.timing_method,source_manifest=str(work/"source-manifest.json"))
    if timing_repair:
        report["timing_repair"]=timing_repair
    summary = [line[len("EDITVIDEO_RENDER "):] for line in out.splitlines() if line.startswith("EDITVIDEO_RENDER ")]
    if summary:  # chunk count and any chunk that needed a retry or software WebGL, without reading engine.log
        report["render"] = json.loads(summary[-1])
    store.write_json(work/"technical.json",report)
    write_srt(work/"captions.srt",[c.model_dump() for c in timeline.cues])
    contact_sheet(final,timeline,work,cancelled)
    (work/"visual.mp4").unlink(missing_ok=True)  # intermediate: final.mp4 holds the same picture plus the mixed audio
    package(pid,work,snapshot,include_media=False)
    return final,report


def package(pid,work,snapshot=None,include_media=False):
    """Editable source package. Default: code + timeline + a media manifest (asset id, file, sha256, kind, credit) — media
    already live in the project and library, so a per-render copy of every video is waste. include_media=True writes
    delivery-full.zip with the media for moving the project to another machine. Media are stored, not re-deflated."""
    snapshot = Path(snapshot or work/"source")
    name = "delivery-full.zip" if include_media else "delivery.zip"
    manifest = []
    for a in store.assets(pid):
        manifest.append({k: a.get(k) for k in ("id","name","kind","sha256","duration","width","height","tags","role")})
    try:
        from .resources import project_credits
        pc = project_credits(pid)
        credits = pc["text"]
    except Exception as e:  # said in the package, never an empty credits file that reads as "nothing to credit"
        pc, credits = {"error": f"{type(e).__name__}: {e}"}, ""
    # Attribution travels with the files (CC BY / BY-SA media need it next to the copy, not only on screen).
    def credit_line(c):  # creator — licence (deed link): works. Source: pages (CC BY asks for all of these)
        lic = c["license"] + (f" ({c['license_url']})" if c.get("license_url") else "")
        return f"- {c['credit']} — {lic}: {', '.join(c['works'])}" + (f". Source: {', '.join(c['sources'])}" if c.get("sources") else "")
    credit_txt = "\n".join(["Credits and licences for media used by this project", "",
                             *([f"CREDITS COULD NOT BE COMPILED ({pc['error']}): ask the owner before distributing this package.", ""] if pc.get("error") else []),
                             *[credit_line(c) for c in pc.get("credits", [])],
                             "", "Footage and images were adapted for this video (cut, cropped, reframed, retimed, colour-adjusted or overlaid); "
                                 "the originals are at the sources above.",
                             *(["", "Media without a recorded origin (ask the owner before redistributing):",
                                *[f"- {m.get('name')} ({m.get('asset')})" for m in pc.get("unrecorded_assets", [])]] if pc.get("unrecorded_assets") else []),
                             "", "Share-alike (BY-SA) media keep their licence in any adaptation; fonts carry their own licence files under source/."]) + "\n"
    # The renderer's audio is mixed outside source/public. A portable package must
    # carry both the locked narration and the final master, not just SFX assets.
    audio_files={fname:sha256(work/fname) for fname in ("voice.wav","mix.wav") if include_media and (work/fname).is_file()}
    with zipfile.ZipFile(work/name,"w",zipfile.ZIP_DEFLATED) as z:
        for current_dir, dirs, files in os.walk(snapshot):
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for fname in files:
                p = Path(current_dir)/fname
                media = p.suffix.lower() in MEDIA_SUFFIXES and "fonts" not in p.parts
                if media and not include_media:
                    continue
                z.write(p,"source/"+str(p.relative_to(snapshot)),compress_type=zipfile.ZIP_STORED if p.suffix.lower() in MEDIA_SUFFIXES else zipfile.ZIP_DEFLATED)
        for fname in ("timeline.json","captions.srt","words.json","meaning.json","technical.json","source-manifest.json"):
            if (work/fname).exists():
                z.write(work/fname,fname)
        for fname in audio_files:
            z.write(work/fname,fname,compress_type=zipfile.ZIP_STORED)
        z.writestr("media-manifest.json",json.dumps({"media_included":include_media,"assets":manifest,"credits":credits,"audio_sha256":audio_files},ensure_ascii=False,indent=1))
        z.writestr("CREDITS.txt",credit_txt)
    return work/name


def engine_env(pid=None):
    # Author code executes locally; do not forward API keys to browser/bundler processes.
    names = {"PATH","PATHEXT","SYSTEMROOT","WINDIR","TEMP","TMP","USERPROFILE","LOCALAPPDATA","APPDATA","PROGRAMFILES","PROGRAMFILES(X86)","HOME",
             "EDITVIDEO_RENDER_CONCURRENCY","EDITVIDEO_GL","EDITVIDEO_CHUNK_FRAMES","FFMPEG_BINARY"}
    env = {**{k:v for k,v in os.environ.items() if k.upper() in names},"DO_NOT_TRACK":"1","HF_TELEMETRY_DISABLED":"1"}
    if pid:  # one webpack bundle per project+code version, reused by every snapshot/render (media hardlinked, not copied)
        env["EDITVIDEO_BUNDLE_CACHE"] = str(store.DATA/"cache"/"remotion"/pid)
    free = available_memory_mb()
    if free:  # the render sizes its browser tabs to this (GPU allocations count against Windows commit)
        env["EDITVIDEO_MEM_AVAILABLE_MB"] = str(free)
    return env


def available_memory_mb():
    """Memory a new process can still commit: Windows commit limit minus commit charge (RAM + pagefile), else free RAM."""
    try:
        if os.name == "nt":
            import ctypes
            class Status(ctypes.Structure):
                _fields_ = [("length",ctypes.c_ulong),("load",ctypes.c_ulong),*[(n,ctypes.c_ulonglong) for n in
                            ("phys","avail_phys","page","avail_page","virtual","avail_virtual","ext")]]
            s = Status(); s.length = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
                return int(s.avail_page // 2**20)
            return None
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // 2**20)
    except (OSError, ValueError, AttributeError):
        return None


def ensure_free(path, need_gb):
    """Fail before writing when the volume is nearly full (a half-written render or copy is worse than a clear error)."""
    target = Path(path)
    while not target.exists():
        target = target.parent
    free = shutil.disk_usage(target).free / 1024**3
    if free < need_gb:
        raise ValueError(f"Only {free:.1f} GB free on the drive holding {target}; need about {need_gb:.1f} GB. "
                         "Free space (storage_report lists temporary data) and retry.")
