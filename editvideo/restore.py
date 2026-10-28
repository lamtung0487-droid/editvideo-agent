"""Archive restoration: low-resolution or soft footage brought up to the film's size with Real-ESRGAN's compact video model
(realesr-general-x4v3, BSD-3-Clause, weights in data/models/realesrgan). Round 13: the owner found archive clips too soft
to read (360-480p re-broadcasts shown at 1080p).

What it does to a picture, so it can be used honestly in a documentary:
- it sharpens edges and removes compression noise; it also invents fine texture that was never filmed. `mix` keeps part of a
  plain bicubic enlargement (less invention, less frame-to-frame shimmer); faces are not "restored" by a face model;
- each frame is processed alone, so detail can shimmer between frames: the report measures it against the plain
  enlargement (`flicker_ratio`), and a film's credits should say that some archive was enhanced with AI.

The network (SRVGGNetCompact) is defined here; the weights load with torch.load(weights_only=True), so no code in them runs.
"""
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from . import store
from .media import FFMPEG, probe

MODELS = Path(__file__).resolve().parent.parent / "data" / "models" / "realesrgan"
WEIGHTS = {"general": "realesr-general-x4v3.pth", "general_wdn": "realesr-general-wdn-x4v3.pth"}
_NET = {}


def _network(denoise, device):
    """realesr-general-x4v3 with its denoise strength: s x the full model + (1 - s) x the weak-denoise one (Real-ESRGAN's
    own interpolation of the two weight sets; 0 keeps grain and noise, 1 removes the most)."""
    import torch
    from torch import nn
    import torch.nn.functional as Fn

    class SRVGGNetCompact(nn.Module):  # Real-ESRGAN's compact VGG-style net: 64 features, 32 convs, PReLU, pixel shuffle
        def __init__(self, num_feat=64, num_conv=32, upscale=4):
            super().__init__()
            self.upscale = upscale
            body = [nn.Conv2d(3, num_feat, 3, 1, 1), nn.PReLU(num_parameters=num_feat)]
            for _ in range(num_conv):
                body += [nn.Conv2d(num_feat, num_feat, 3, 1, 1), nn.PReLU(num_parameters=num_feat)]
            body.append(nn.Conv2d(num_feat, 3 * upscale * upscale, 3, 1, 1))
            self.body = nn.ModuleList(body)
            self.upsampler = nn.PixelShuffle(upscale)

        def forward(self, x):
            out = x
            for layer in self.body:
                out = layer(out)
            return self.upsampler(out) + Fn.interpolate(x, scale_factor=self.upscale, mode="nearest")
    key = (round(float(denoise), 3), device)
    if key in _NET:
        return _NET[key]

    def params(name):
        p = MODELS / WEIGHTS[name]
        if not p.is_file():
            raise FileNotFoundError(f"{p} is missing: download realesr-general-x4v3.pth and realesr-general-wdn-x4v3.pth "
                                    "from github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0 into data/models/realesrgan")
        sd = torch.load(p, map_location="cpu", weights_only=True)
        return sd.get("params_ema") or sd.get("params") or sd
    full, weak = params("general"), params("general_wdn")
    s = min(1.0, max(0.0, float(denoise)))
    net = SRVGGNetCompact()
    net.load_state_dict({k: s * full[k] + (1 - s) * weak[k] for k in full})
    net.eval().to(device)
    if device == "cuda":
        net = net.half()
    _NET[key] = net
    return net


def restore_clip(src, out=None, start=0.0, duration=None, height=1080, denoise=.5, mix=.85, device=None, crf=16, from_height=None):
    """Enlarge [start, start + duration) of `src` to `height` (aspect kept, even width) with the AI model, mixing `mix` of
    its picture with 1 - mix of a plain bicubic enlargement. Audio is copied. Cached in the store's cache by the source,
    window and settings. Returns {"path", "from", "to", "frames", "report"}; the report compares the first frames with
    the plain enlargement: sharpness (variance of the Laplacian) and flicker (mean change between frames).

    from_height: the picture's true height when `src` is already an enlargement (round 13: archive cut at 1080 from
    360-480p re-broadcasts, after cropping, logo removal and steadying). The frames are first brought back to that height
    (area average), so the model sees the real detail and not the blur of the earlier enlargement."""
    import torch
    import torch.nn.functional as Fn
    import cv2
    src = Path(src)
    v = next(x for x in probe(str(src))["streams"] if x["codec_type"] == "video")
    w0, h0 = int(v["width"]), int(v["height"])
    shrink = []
    if from_height and int(from_height) < h0:
        w0, h0 = int(round(w0 * int(from_height) / h0 / 2) * 2), int(from_height)
        shrink = ["-vf", f"scale={w0}:{h0}:flags=area"]
    rate = str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1")
    W = int(round(w0 * height / h0 / 2) * 2)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    st = src.stat()
    key = hashlib.sha256(f"{src.resolve()}|{st.st_size}|{st.st_mtime_ns}|{start:.3f}|{duration}|{height}|{denoise:.3f}|{mix:.3f}|{from_height}|v1".encode()).hexdigest()[:24]
    cache = store.DATA / "cache" / "restored"
    cache.mkdir(parents=True, exist_ok=True)
    out = Path(out) if out else cache / f"rst-{key}.mp4"
    note = out.with_suffix(".json")
    if out.is_file() and note.is_file():
        return json.loads(note.read_text(encoding="utf-8"))
    net = _network(denoise, device)
    win = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{duration:.3f}"] if duration else [])
    dec = subprocess.Popen([FFMPEG, "-v", "error", *win, "-i", str(src), "-an", *shrink, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{height}", "-r", rate, "-i", "-",
                            *win, "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(tmp)],
                           stdin=subprocess.PIPE)
    size = w0 * h0 * 3
    n, sharp_ai, sharp_plain, flick_ai, flick_plain = 0, [], [], [], []
    prev = None
    try:
        with torch.inference_mode():
            while True:
                buf = dec.stdout.read(size)
                if len(buf) < size:
                    break
                x = torch.from_numpy(np.frombuffer(buf, np.uint8).reshape(h0, w0, 3).copy()).to(device).permute(2, 0, 1)[None]
                x = x.half() / 255 if device == "cuda" else x.float() / 255
                ai = Fn.interpolate(net(x).float(), size=(height, W), mode="bicubic", antialias=True, align_corners=False)
                plain = Fn.interpolate(x.float(), size=(height, W), mode="bicubic", align_corners=False)
                y = (mix * ai + (1 - mix) * plain).clamp(0, 1)
                frame = (y[0].permute(1, 2, 0) * 255 + .5).byte().cpu().numpy()
                enc.stdin.write(frame.tobytes())
                if n < 48:  # the report: the first two seconds or so
                    g_ai = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                    g_pl = cv2.cvtColor((plain[0].clamp(0, 1).permute(1, 2, 0) * 255 + .5).byte().cpu().numpy(), cv2.COLOR_RGB2GRAY)
                    sharp_ai.append(cv2.Laplacian(g_ai, cv2.CV_64F).var())
                    sharp_plain.append(cv2.Laplacian(g_pl, cv2.CV_64F).var())
                    if prev is not None:
                        flick_ai.append(float(np.abs(g_ai.astype(int) - prev[0]).mean()))
                        flick_plain.append(float(np.abs(g_pl.astype(int) - prev[1]).mean()))
                    prev = (g_ai.astype(int), g_pl.astype(int))
                n += 1
        enc.stdin.close()
        if enc.wait() != 0:
            raise RuntimeError(f"encoding the restored {src.name} failed")
        dec.wait()
        if n == 0:
            raise RuntimeError(f"no frames decoded from {src.name} at {start:.2f} s")
        tmp.replace(out)
    finally:
        if dec.poll() is None:
            dec.kill()
        if enc.poll() is None:
            enc.kill()
        if tmp.exists():
            tmp.unlink()
    report = {"sharpness_ai": round(float(np.median(sharp_ai)), 1), "sharpness_plain": round(float(np.median(sharp_plain)), 1),
              "sharpness_gain": round(float(np.median(sharp_ai)) / max(float(np.median(sharp_plain)), 1e-6), 2),
              "flicker_ratio": round(float(np.mean(flick_ai)) / max(float(np.mean(flick_plain)), 1e-6), 2) if flick_ai else None,
              "denoise": denoise, "mix": mix, "device": device,
              "note": "AI-enhanced: fine texture is partly invented; credit it as enhanced archive. flicker_ratio > 1.3 shimmers."}
    res = {"path": str(out), "from": [w0, h0], "to": [W, height], "frames": n, "report": report}
    store.write_json(note, res)
    return res
