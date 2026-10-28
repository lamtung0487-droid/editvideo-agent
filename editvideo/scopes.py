"""Display-referred scopes the way colourists read them (0-100 % display code values): luma waveform with crushed and
clipped fractions, RGB parade and colour cast per tonal band, vectorscope with the skin-tone line, and optional skin
statistics in a region. One combined image for all sampled frames keeps image tokens low.

Working targets (from grading practice, adjust to intent): p0.5 luma 1-4 % with <=1 % of pixels under 2 %; p99 85-93 %
with ~0 % above 98 % apart from speculars; neutral cast under ~2 % chroma before the look; skin hue within about ±10° of
the 123° skin line unless the look is deliberately warm or cool.
"""
import math
import subprocess
import uuid
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from . import store
from .media import FFMPEG, probe, sha256

SKIN_DEG = 123.0  # vectorscope angle of the skin-tone (I) line in Cb/Cr, measured from +Cb toward +Cr


def _frame(path, t, w=480):
    p = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:-2:flags=area,format=rgb24",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=60)
    if p.returncode or not p.stdout:
        raise ValueError(f"Could not decode a frame at {t:.2f}s")
    h = len(p.stdout) // (w * 3)
    return np.frombuffer(p.stdout[: w * h * 3], np.uint8).reshape(h, w, 3).astype(np.float32) / 255


def active_area(rgb):
    """Crop letterbox/pillarbox bars: edge rows/columns that are >=85 % near-black (burned-in captions inside a bar
    still count as bar). Picture content that is merely dark is kept."""
    y = rgb @ np.array([.2126, .7152, .0722], np.float32)
    dark = y < .03
    def run(fracs):
        n = 0
        for f in fracs:
            if f < .85:
                break
            n += 1
        return n
    rows, cols = dark.mean(1), dark.mean(0)
    t, b = run(rows), run(rows[::-1])
    l, r = run(cols), run(cols[::-1])
    h, w = y.shape
    if t + b > h * .8 or l + r > w * .8:  # an almost black frame: measure all of it
        return rgb, None
    box = (t, h - b, l, w - r)
    return rgb[t:h - b, l:w - r], (box if (t or b or l or r) else None)


def ycc(rgb):
    y = rgb @ np.array([.2126, .7152, .0722], np.float32)
    return y, (rgb[..., 2] - y) / 1.8556, (rgb[..., 0] - y) / 1.5748


def measure(full, skin_region=None):
    """Statistics on the active picture (bars excluded); skin_region is read on the full frame it was chosen on."""
    rgb, bars = active_area(full)
    y, cb, cr = ycc(rgb)
    pct = lambda a, q: round(float(np.percentile(a, q)) * 100, 2)
    out = {"luma_pct": {str(q): pct(y, q) for q in (0.5, 1, 50, 99, 99.5)},
           "crushed_under_2pct": round(float((y < .02).mean()), 4), "clipped_over_98pct": round(float((y > .98).mean()), 4),
           "bars_excluded": bars is not None}
    bands = {"shadows": y < .25, "mids": (y >= .25) & (y <= .75), "highlights": y > .75}
    cast = {}
    for name, m in bands.items():
        if m.mean() < .01:
            continue
        r, g, b = (float(rgb[..., i][m].mean()) for i in range(3))
        cast[name] = {"rgb_pct": [round(r * 100, 1), round(g * 100, 1), round(b * 100, 1)], "cb_pct": round(float(cb[m].mean()) * 100, 2),
                      "cr_pct": round(float(cr[m].mean()) * 100, 2)}
    out["cast_by_band"] = cast
    chroma = np.hypot(cb, cr)
    out["chroma_pct"] = {"mean": round(float(chroma.mean()) * 100, 2), "p95": round(float(np.percentile(chroma, 95)) * 100, 2)}
    if skin_region:
        y, cb, cr = ycc(full)
        h, w = y.shape
        x0, y0, rw, rh = skin_region
        sl = (slice(int(y0 * h), max(int(y0 * h) + 1, int((y0 + rh) * h))), slice(int(x0 * w), max(int(x0 * w) + 1, int((x0 + rw) * w))))
        c_b, c_r = cb[sl], cr[sl]
        sel = np.hypot(c_b, c_r) > .015  # ignore near-neutral pixels (eyes, hair, background)
        if sel.sum() > 20:
            ang = float(np.degrees(np.arctan2(c_r[sel].mean(), c_b[sel].mean())) % 360)
            out["skin"] = {"hue_deg": round(ang, 1), "off_skin_line_deg": round((ang - SKIN_DEG + 180) % 360 - 180, 1),
                           "chroma_pct": round(float(np.hypot(c_b[sel], c_r[sel]).mean()) * 100, 2), "luma_pct": round(float(y[sl][sel].mean()) * 100, 1)}
    return out


def _panel(rgb, y, cb, cr, label, skin_region=None):
    """Thumbnail | luma waveform | RGB parade | vectorscope, 256 px tall."""
    H = 256
    thumb = Image.fromarray((rgb * 255).astype(np.uint8)).resize((int(H * rgb.shape[1] / rgb.shape[0]), H))
    if skin_region:
        d = ImageDraw.Draw(thumb)
        x0, y0, rw, rh = skin_region
        d.rectangle([x0 * thumb.width, y0 * H, (x0 + rw) * thumb.width, (y0 + rh) * H], outline=(255, 210, 120), width=2)

    def wave(channel, colour, width=256):
        img = np.zeros((H, width), np.float32)
        cols = np.linspace(0, channel.shape[1] - 1, width).astype(int)
        for i, c in enumerate(cols):
            v = np.clip((1 - channel[:, c]) * (H - 1), 0, H - 1).astype(int)
            np.add.at(img[:, i], v, 1)
        img = np.clip(img / max(1, np.percentile(img[img > 0], 95) if (img > 0).any() else 1), 0, 1)
        out = np.zeros((H, width, 3), np.float32)
        for k in range(3):
            out[..., k] = img * colour[k]
        return out

    wf = wave(y, (.5, 1, .75))
    parade = np.concatenate([wave(rgb[..., k], c, 128) for k, c in enumerate(((1, .3, .3), (.3, 1, .3), (.35, .5, 1)))], axis=1)
    vs = np.zeros((H, H), np.float32)
    px = np.clip((cb.ravel() * 2.2 + .5) * (H - 1), 0, H - 1).astype(int)
    py = np.clip((.5 - cr.ravel() * 2.2) * (H - 1), 0, H - 1).astype(int)
    np.add.at(vs, (py, px), 1)
    vs = np.clip(np.sqrt(vs / max(1, vs.max())) * 1.6, 0, 1)
    vsi = Image.fromarray((np.stack([vs * .6, vs, vs * .8], -1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(vsi)
    c = (H - 1) / 2
    a = math.radians(SKIN_DEG)
    d.line([c, c, c + math.cos(a) * c, c - math.sin(a) * c], fill=(255, 190, 120), width=1)
    d.ellipse([c - c * .5, c - c * .5, c + c * .5, c + c * .5], outline=(70, 70, 70))
    d.text((4, 4), "vectorscope", fill=(160, 160, 160))
    to_img = lambda a: Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    wfi, pai = to_img(wf), to_img(parade)
    for im, name in ((wfi, "luma"), (pai, "RGB parade")):
        d = ImageDraw.Draw(im)
        for lvl, col in ((0, (90, 90, 90)), (.02, (200, 80, 80)), (.5, (70, 70, 70)), (.98, (200, 80, 80)), (1, (90, 90, 90))):
            yy = int((1 - lvl) * (H - 1))
            d.line([0, yy, im.width, yy], fill=col)
        d.text((4, 4), name, fill=(160, 160, 160))
    row = Image.new("RGB", (thumb.width + wfi.width + pai.width + vsi.width + 12, H + 18), (24, 24, 28))
    x = 0
    for im in (thumb, wfi, pai, vsi):
        row.paste(im, (x, 18))
        x += im.width + 4
    ImageDraw.Draw(row).text((4, 3), label, fill=(255, 230, 120))
    return row


def scopes(path, timestamps=None, skin_region=None, compare=None):
    """compare: optional second file (e.g. the graded or reference version) measured at the same timestamps."""
    src = Path(path).resolve(strict=True)
    info = probe(src)
    duration = float(info["format"].get("duration", 1) or 1)
    times = timestamps or [duration * .5]
    if not 1 <= len(times) <= 6 or any(not 0 <= t < max(duration, .04) for t in times):
        raise ValueError("1..6 timestamps inside the source")
    if skin_region and (len(skin_region) != 4 or not all(0 <= v <= 1 for v in skin_region)):
        raise ValueError("skin_region is normalized [x, y, w, h]")
    out = store.DATA / "observations" / ("scopes-" + uuid.uuid4().hex[:12])
    out.mkdir(parents=True)
    rows, records = [], []
    for t in times:
        for name, p in [("", src)] + ([("compare", Path(compare).resolve(strict=True))] if compare else []):
            rgb = _frame(p, t)
            stats = measure(rgb, skin_region)
            y, cb, cr = ycc(rgb)  # scopes show the whole frame, bars included, as a colourist sees it
            stats["timestamp"] = t
            if name:
                stats["source"] = "compare"
            records.append(stats)
            label = f"{t:.2f}s {name or src.name}  p0.5 {stats['luma_pct']['0.5']}%  p99 {stats['luma_pct']['99']}%  crushed {stats['crushed_under_2pct']:.1%}  clipped {stats['clipped_over_98pct']:.1%}"
            rows.append(_panel(rgb, y, cb, cr, label, skin_region))
    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height + 4 for r in rows)), (16, 16, 18))
    yy = 0
    for r in rows:
        sheet.paste(r, (0, yy))
        yy += r.height + 4
    path_img = out / "scopes.jpg"
    sheet.save(path_img, quality=85)
    flags = []
    for r in records:
        tag = f"{r['timestamp']:.2f}s" + (" compare" if r.get("source") else "")
        if r["crushed_under_2pct"] > .01:
            flags.append(f"{tag}: {r['crushed_under_2pct']:.1%} of pixels crushed under 2% (lift shadows unless intended)")
        if r["clipped_over_98pct"] > .005:
            flags.append(f"{tag}: {r['clipped_over_98pct']:.1%} clipped over 98% (lower gain or roll off highlights)")
        mids = r["cast_by_band"].get("mids")
        if mids and math.hypot(mids["cb_pct"], mids["cr_pct"]) > 3:
            flags.append(f"{tag}: midtone cast Cb {mids['cb_pct']} / Cr {mids['cr_pct']} % (white balance on a neutral before the look)")
        if r.get("skin") and abs(r["skin"]["off_skin_line_deg"]) > 12:
            flags.append(f"{tag}: skin hue {r['skin']['hue_deg']}° is {r['skin']['off_skin_line_deg']}° off the skin line")
    return {"source": str(src), "source_sha256": sha256(src), "frames": records, "flags": flags, "image": str(path_img),
            "targets": "p0.5 luma 1-4 %, <=1 % under 2 %; p99 85-93 %, ~0 % over 98 %; neutral cast < 2-3 %; skin within ~±10° of 123°.",
            "method": "Display code values (BT.709 coefficients on decoded RGB, full scale 0-100 %) on a 480 px frame; Cb/Cr scaled to ±50 %. "
                      "Sampled frames, not whole-shot statistics; intent may justify crushed blacks or warm skin."}
