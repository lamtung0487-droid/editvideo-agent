"""One finishing stack for every CG plate, so 3D sits with the archive instead of beside it (reports/Nâng cấp 3D phim
tài liệu.md, P1-8; FilmLight's Hatton case study, No Film School's four elements of film emulation): CG is softened a
little (clean CG beside 16 mm reads as fake), highlights get a faint warm halation, a luminance grain moves every
frame, the frame weaves by under a pixel and the corners fall off. Values come from the series bible (style.finish).
Text and labels are composited after this, in the engines, and stay clean."""
from pathlib import Path
from . import style


def filter_graph(width=1920, height=1080, finish=None, seed=7):
    """An ffmpeg -filter_complex graph from [0:v] to [v] (yuv420p, BT.709)."""
    f = {**style.get("finish", default={}), **(finish or {})}
    soften = float(f.get("soften", .6))
    hal = float(f.get("halation", .18))
    amp = max(0, int(round(float(f.get("grain", .035)) * 255)))
    size = max(1.0, float(f.get("grain_size", 1.6)))
    weave = float(f.get("gate_weave_px", .6))
    vig = float(f.get("vignette", .25))
    gw, gh = int(width / size) // 2 * 2, int(height / size) // 2 * 2
    pad = 4 if weave > 0 else 0
    parts = [f"[0:v]format=gbrp,scale={width}:{height},gblur=sigma={soften:.2f},split=3[base][hi][gsrc]"]
    # halation: only what is near white, blurred wide, pulled toward red-orange, screened back at low opacity
    parts.append(f"[hi]curves=all='0/0 0.72/0 1/1',gblur=sigma=7,colorchannelmixer=rr=1:gg=0.38:bb=0.16[hal]")
    parts.append(f"[base][hal]blend=all_mode=screen:all_opacity={hal:.3f}[lit]")
    # grain: grey noise at a coarser size, scaled up so it clumps like silver, merged around mid-grey
    parts.append(f"[gsrc]scale={gw}:{gh},format=gray,geq=lum=128,noise=c0s={amp}:c0f=t+u:c0_seed={seed},"
                 f"scale={width}:{height}:flags=bicubic,format=gbrp[grain]")
    parts.append("[lit][grain]blend=all_mode=grainmerge[g]")
    tail = "[g]"
    if weave > 0:  # the gate: an offset that wanders slowly, never more than ~weave px
        parts.append(f"{tail}pad={width + 2 * pad}:{height + 2 * pad}:{pad}:{pad}:color=black,"
                     f"crop={width}:{height}:'{pad}+{weave:.2f}*sin(n*0.41)+{weave * .5:.2f}*sin(n*1.33)':'{pad}+{weave:.2f}*sin(n*0.29+1)+{weave * .5:.2f}*sin(n*1.07)'[w]")
        tail = "[w]"
    if vig > 0:
        parts.append(f"{tail}vignette=angle={0.35 + 0.5 * vig:.3f}[vg]")
        tail = "[vg]"
    parts.append(f"{tail}scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[v]")
    return ";".join(parts)


def encode_args():
    """Colour tags so players and browsers do not guess (BT.709, TV range)."""
    return ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def apply(src, out, finish=None, crf=16):
    """Finish a clip (an image sequence pattern or a video) into an H.264 file."""
    import subprocess
    from .media import FFMPEG
    src = str(src)
    inp = ["-framerate", "30", "-i", src] if "%" in src else ["-i", src]
    subprocess.run([FFMPEG, "-v", "error", "-y", *inp, "-filter_complex", filter_graph(finish=finish), "-map", "[v]", "-c:v", "libx264",
                    "-crf", str(crf), "-preset", "slow", *encode_args(), "-movflags", "+faststart", str(out)], check=True)
    return str(out)
