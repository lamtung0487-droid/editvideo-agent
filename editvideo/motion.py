"""Bounded temporal measurements and visual evidence for a multimodal director.

These are observable pixel signals, not semantic identity or aesthetic scores.
Dense flow is classical Farneback; camera estimation is robust sparse LK/affine.
"""
import math
import time
import uuid
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from . import store
from .graphics import font
from .media import FFMPEG, command, probe, sha256


def _region(region):
    if region is None:
        return [0., 0., 1., 1.]
    if len(region) != 4 or not all(math.isfinite(x) for x in region) or not 0 <= region[0] < region[2] <= 1 or not 0 <= region[1] < region[3] <= 1:
        raise ValueError("region=[left,top,right,bottom] normalized 0..1")
    return region


def _camera(prev, curr):
    import cv2
    points = cv2.goodFeaturesToTrack(prev, maxCorners=500, qualityLevel=.015, minDistance=5)
    if points is None or len(points) < 12:
        return None, 0., 0
    moved, ok, _ = cv2.calcOpticalFlowPyrLK(prev, curr, points, None, winSize=(21, 21), maxLevel=3)
    if moved is None:
        return None, 0., 0
    back, back_ok, _ = cv2.calcOpticalFlowPyrLK(curr, prev, moved, None, winSize=(21, 21), maxLevel=3)
    if back is None:
        return None, 0., 0
    valid = (ok.ravel() == 1) & (back_ok.ravel() == 1) & (np.linalg.norm(points[:, 0]-back[:, 0], axis=1) < 1.)
    n = int(valid.sum())
    if n < 12:
        return None, 0., n
    matrix, inliers = cv2.estimateAffinePartial2D(points[valid, 0], moved[valid, 0], method=cv2.RANSAC,
                                                ransacReprojThreshold=1.5, maxIters=2000, confidence=.99)
    fraction = float(inliers.mean()) if inliers is not None else 0.
    if matrix is None or fraction < .45 or not .8 < np.hypot(matrix[0, 0], matrix[1, 0]) < 1.25:
        return None, fraction, n
    # A small cluster can belong entirely to one moving subject. Require broad
    # coverage before presenting the transform as a global-motion candidate.
    accepted = points[valid, 0][inliers.ravel().astype(bool)]
    span = np.ptp(accepted, axis=0)
    if span[0] < prev.shape[1]*.4 or span[1] < prev.shape[0]*.4:
        return None, fraction, n
    return matrix, fraction, n


def measure_pair(previous, current):
    """Input RGB uint8 arrays; output metrics, flow, reliable mask, residual map."""
    import cv2
    p = cv2.cvtColor(previous, cv2.COLOR_RGB2GRAY)
    c = cv2.cvtColor(current, cv2.COLOR_RGB2GRAY)
    h, w = p.shape
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    forward = cv2.calcOpticalFlowFarneback(p, c, None, .5, 3, 19, 4, 7, 1.5, 0)
    backward = cv2.calcOpticalFlowFarneback(c, p, None, .5, 3, 19, 4, 7, 1.5, 0)
    x, y = xx+forward[..., 0], yy+forward[..., 1]
    back_at = cv2.remap(backward, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    fb = np.linalg.norm(forward+back_at, axis=2)
    magnitude = np.linalg.norm(forward, axis=2)
    reliable = (x >= 1) & (x < w-2) & (y >= 1) & (y < h-2) & (fb < .75 + .05*magnitude)
    aligned = cv2.remap(current, x, y, cv2.INTER_LINEAR)
    residual = np.mean(np.abs(aligned.astype(np.float32)-previous), axis=2)
    matrix, inlier_fraction, features = _camera(p, c)
    histp = cv2.calcHist([p], [0], None, [32], [0, 256]); histc = cv2.calcHist([c], [0], None, [32], [0, 256])
    cv2.normalize(histp, histp); cv2.normalize(histc, histc)
    hp=cv2.calcHist([cv2.cvtColor(previous,cv2.COLOR_RGB2HSV)],[0,1],None,[24,16],[0,180,0,256])
    hc=cv2.calcHist([cv2.cvtColor(current,cv2.COLOR_RGB2HSV)],[0,1],None,[24,16],[0,180,0,256])
    cv2.normalize(hp,hp);cv2.normalize(hc,hc)
    raw = float(np.mean(np.abs(current.astype(np.float32)-previous)))
    histogram_change=max(cv2.compareHist(histp,histc,cv2.HISTCMP_BHATTACHARYYA),cv2.compareHist(hp,hc,cv2.HISTCMP_BHATTACHARYYA))
    cut = raw > 50 and histogram_change > .65
    if cut:
        reliable[:] = False
        matrix = None
    residual_motion = None
    if matrix is not None:
        camflow = np.stack([matrix[0, 0]*xx+matrix[0, 1]*yy+matrix[0, 2]-xx,
                            matrix[1, 0]*xx+matrix[1, 1]*yy+matrix[1, 2]-yy], axis=2)
        residual_motion = np.linalg.norm(forward-camflow, axis=2)
    m = {"raw_rgb_change": round(raw, 4), "histogram_change":round(histogram_change,4), "cut_candidate": cut,
         "reliable_flow_fraction": round(float(reliable.mean()), 4),
         "forward_backward_error_p50": round(float(np.median(fb)), 4),
         "motion_pixels_p50": round(float(np.median(magnitude[reliable])), 4) if reliable.any() else None,
         "motion_pixels_p95": round(float(np.percentile(magnitude[reliable], 95)), 4) if reliable.any() else None,
         "aligned_rgb_residual": round(float(residual[reliable].mean()), 4) if reliable.mean() > .1 else None,
         "camera_affine_previous_to_current": matrix.tolist() if matrix is not None else None,
         "camera_inlier_fraction": round(inlier_fraction, 4), "camera_features": features,
         "non_camera_motion_pixels_p95": round(float(np.percentile(residual_motion[reliable], 95)), 4) if residual_motion is not None and reliable.any() else None}
    return m, forward, reliable, residual


def spectrum(values, fps):
    """Hann-windowed demeaned FFT with physical frequency and resolution."""
    values = np.asarray(values, dtype=np.float64)
    if len(values) < 8:
        return {"peaks": [], "resolution_hz": fps/max(1, len(values)), "nyquist_hz": fps/2}
    power = np.abs(np.fft.rfft((values-values.mean())*np.hanning(len(values))))**2
    frequencies = np.fft.rfftfreq(len(values), 1/fps)
    power[0] = 0
    candidates = [i for i in range(1, len(power)-1) if power[i] >= power[i-1] and power[i] > power[i+1]]
    if not candidates and power.sum() > 1e-12:
        candidates = [int(np.argmax(power))]
    selected = sorted(candidates, key=lambda i: power[i], reverse=True)[:5] if power.sum() > 1e-12 else []
    return {"peaks": [{"frequency_hz": round(float(frequencies[i]), 4), "relative_power": round(float(power[i]/power.sum()), 4)} for i in selected],
            "resolution_hz": round(fps/len(values), 4), "nyquist_hz": fps/2,
            "method": "demeaned ROI mean luma, Hann window, rFFT; camera/object movement may also create peaks"}


def _decode(path, start, end, sampling_fps, width, out):
    source = Path(path).resolve(strict=True)
    info = probe(source); duration = float(info["format"].get("duration", 0))
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not video or not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= duration+.001 or end-start > 15:
        raise ValueError("Video window within source, <=15 seconds")
    if not 2 <= sampling_fps <= 30 or not 160 <= width <= 640 or (end-start)*sampling_fps > 240:
        raise ValueError("sampling_fps 2..30, max 240 samples, width 160..640")
    scale = min(1, width/video["width"], 640/video["height"])
    w, h = max(2, round(video["width"]*scale/2)*2), max(2, round(video["height"]*scale/2)*2)
    if (end-start)*sampling_fps*w*h*3 > 200_000_000:
        raise ValueError("Sample budget exceeds 200MB; narrow window or reduce width/fps")
    raw = out/"frames.rgb"
    # CFR evidence positions are on this explicit sample grid, not native VFR PTS.
    command([FFMPEG, "-y", "-v", "error", "-xerror", "-ss", start, "-i", source, "-t", end-start,
             "-vf", f"setpts=PTS-STARTPTS,fps={sampling_fps}:round=down,scale={w}:{h}",
             "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", raw], timeout=120)
    frames = np.memmap(raw, dtype=np.uint8, mode="r").reshape(-1, h, w, 3)
    if len(frames) < 2:
        frames._mmap.close(); raw.unlink()
        raise ValueError("At least two samples required")
    return source, frames, raw, [video["width"], video["height"]]


def analyze(path, start, end, region=None, sampling_fps=12, width=384, evidence_frames=6):
    """Dense correspondence, camera motion, residuals, ROI trace and FFT."""
    import cv2
    r = _region(region)
    if not 2 <= evidence_frames <= 8:
        raise ValueError("evidence_frames 2..8")
    out = store.DATA/"motion"/str(uuid.uuid4()); out.mkdir(parents=True)
    source, frames, raw, source_size = _decode(path, start, end, sampling_fps, width, out)
    began = time.monotonic()
    pairs, trace, evidence = [], [], []
    try:
        h, w = frames.shape[1:3]
        x0, y0, x1, y1 = [round(r[0]*w), round(r[1]*h), round(r[2]*w), round(r[3]*h)]
        if x1 <= x0 or y1 <= y0:
            raise ValueError("ROI contains no sampled pixels; enlarge it")
        for i, frame in enumerate(frames):
            if time.monotonic()-began > 180:
                raise TimeoutError("Temporal analysis exceeds 180s; narrow window")
            roi = frame[y0:y1, x0:x1]
            gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
            trace.append({"timestamp": round(start+i/sampling_fps, 6), "sample": i,
                          "mean_luma": round(float(gray.mean()), 4),
                          "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_32F).var()), 4),
                          "clipped_dark_fraction": round(float((gray <= 3).mean()), 4),
                          "clipped_bright_fraction": round(float((gray >= 252).mean()), 4)})
            if i:
                m, _, reliable, residual = measure_pair(frames[i-1], frame)
                m.update(sample=i, timestamp=trace[-1]["timestamp"])
                valid = reliable[y0:y1, x0:x1]
                m["roi_aligned_rgb_residual"] = round(float(residual[y0:y1, x0:x1][valid].mean()), 4) if valid.mean() > .1 else None
                pairs.append(m)
        # Include endpoints plus actual peaks, de-duplicate neighboring samples.
        selected = {0, len(frames)-1}
        ranked = sorted(pairs, key=lambda p: (p["cut_candidate"], p["roi_aligned_rgb_residual"] or p["raw_rgb_change"]), reverse=True)
        for m in ranked:
            if len(selected) >= evidence_frames:
                break
            if all(abs(m["sample"]-i) > max(1, round(sampling_fps*.15)) for i in selected):
                selected.add(m["sample"])
        if len(selected) < evidence_frames:
            for i in np.linspace(0, len(frames)-1, evidence_frames, dtype=int):
                if len(selected) >= evidence_frames:break
                selected.add(int(i))
        for j, i in enumerate(sorted(selected)):
            p = out/f"evidence-{j:02}.png";Image.fromarray(frames[i]).save(p)
            evidence.append({"index": j, "evidence_id": f"sample-{i}", "sample": i, "timestamp": trace[i]["timestamp"],
                             "path": str(p), "sha256": sha256(p), "display_size": [w, h]})
        # Diagnostic panels at strongest usable temporal residual, with fixed
        # scale (0..32 RGB levels) so different calls remain comparable.
        candidates = [p for p in ranked if not p["cut_candidate"] and p["aligned_rgb_residual"] is not None]
        diagnostic = None
        if candidates:
            i = candidates[0]["sample"]
            m, flow, reliable, residual = measure_pair(frames[i-1], frames[i])
            hsv = np.zeros((h, w, 3), np.uint8)
            mag, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            hsv[..., 0] = angle*90/np.pi;hsv[..., 1] = 255;hsv[..., 2] = np.clip(mag*255/8, 0, 255)
            flow_rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB);flow_rgb[~reliable] = 0
            heat = cv2.cvtColor(cv2.applyColorMap(np.clip(residual*255/32, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO), cv2.COLOR_BGR2RGB)
            heat[~reliable] = [40, 40, 40]
            panels = [(frames[i-1], f"Previous {trace[i-1]['timestamp']:.3f}s"), (frames[i], f"Current {trace[i]['timestamp']:.3f}s"),
                      (flow_rgb, "Flow: hue direction, 8px saturation"), (heat, "Aligned residual: 0..32 RGB; gray invalid")]
            sheet = Image.new("RGB", (w*2, (h+28)*2), "#101820")
            for k, (rgb, label) in enumerate(panels):
                x, y = k%2*w, k//2*(h+28);sheet.paste(Image.fromarray(rgb), (x, y))
                ImageDraw.Draw(sheet).text((x+6, y+h+4), label, fill="white", font=font(12))
            p = out/"motion-evidence.png";sheet.save(p)
            diagnostic = {"path": str(p), "timestamp": trace[i]["timestamp"], "sha256": sha256(p)}
        spec = spectrum([t["mean_luma"] for t in trace], sampling_fps)
        bounds=[0]+[p['sample'] for p in pairs if p['cut_candidate']]+[len(trace)]
        segment_spectra=[{'sample_range':[a,b],'window':[trace[a]['timestamp'],min(end,start+b/sampling_fps)],
                          **spectrum([t['mean_luma'] for t in trace[a:b]],sampling_fps)} for a,b in zip(bounds,bounds[1:])]
        values = [p["aligned_rgb_residual"] for p in pairs if p["aligned_rgb_residual"] is not None]
        result = {"source": str(source), "source_sha256": sha256(source), "window": [start, end],
                  "sampling_fps": sampling_fps, "sample_count": len(frames), "sample_size": [w, h], "source_size": source_size,
                  "region": r, "roi_sample_pixels": [x0, y0, x1, y1], "frames": evidence,
                  "diagnostic": diagnostic, "luma_spectrum": spec,
                  "luma_spectrum_segments":segment_spectra,
                  "summary": {"cut_candidate_times": [p["timestamp"] for p in pairs if p["cut_candidate"]],
                              "aligned_residual_p50": float(np.median(values)) if values else None,
                              "camera_estimated_pairs": sum(p["camera_affine_previous_to_current"] is not None for p in pairs)},
                  "events": ranked[:8], "pairs": pairs, "roi_trace": trace,
                  "units": "RGB/luma 0..255; motion in sampled pixels per sampled interval, not source pixels or physical speed",
                  "limitations": "Classical correspondence may fail on occlusion, repeated texture, deformation, blur and cuts. Reliability is forward/backward consistency, not semantic confidence. Affine global motion is a camera candidate; a dominant moving object or parallax can mislead it. Aligned residual includes lighting, interpolation and generation changes; not a flicker or beauty verdict. ROI is fixed in image coordinates. FFT aliases above Nyquist and needs a long enough window. Sample grid uses resampled CFR positions, not native VFR PTS. No recovery of unseen information.",
                  "seconds": round(time.monotonic()-began, 3), "manifest": str(out/"motion.json")}
        store.write_json(out/"motion.json", result)
        return {k: v for k, v in result.items() if k not in ("pairs", "roi_trace")}
    finally:
        frames._mmap.close();raw.unlink(missing_ok=True)


def read(path, offset=0, limit=24):
    manifest = Path(path).resolve(strict=True)
    if not manifest.is_relative_to((store.DATA/"motion").resolve()) or manifest.name != "motion.json":
        raise ValueError("Use motion manifest returned by analyze_motion")
    if offset < 0 or not 1 <= limit <= 60:
        raise ValueError("offset>=0, limit1..60")
    result = store.read_json(manifest)
    rows = result["pairs"][offset:offset+limit]
    return {"pairs": rows, "roi_trace": result["roi_trace"][offset:offset+limit], "total": len(result["pairs"]),
            "next_offset": offset+limit if offset+limit < len(result["pairs"]) else None,
            "source_sha256": result["source_sha256"], "units": result["units"]}


def temporal_lens(path, start, end, region=None, sampling_fps=24, width=256, low_hz=.5, high_hz=4., gain=4.):
    """Derived original/amplified view of a temporal RGB frequency band.

    Fixed-grid color magnification, not phase-based motion magnification or
    physiological inference. Boundaries use periodic FFT; edge ringing is real.
    """
    r = _region(region)
    if not all(math.isfinite(v) for v in (low_hz, high_hz, gain)) or not 0 < low_hz < high_hz < sampling_fps/2 or not 1 <= gain <= 10 or width > 384:
        raise ValueError("0<low_hz<high_hz<Nyquist, gain1..10, width<=384")
    out = store.DATA/"motion"/str(uuid.uuid4());out.mkdir(parents=True)
    source, frames, raw, source_size = _decode(path, start, end, sampling_fps, width, out)
    output_raw = out/"lens.rgb"
    try:
        n, h, w = frames.shape[:3]
        if n < 16 or n*w*h*3 > 80_000_000:
            raise ValueError("Temporal lens needs >=16 samples and <=80MB; narrow window/width")
        frequencies = np.fft.rfftfreq(n, 1/sampling_fps)
        band = (frequencies >= low_hz) & (frequencies <= high_hz)
        if not band.any():
            raise ValueError("No frequency bin inside band; lengthen window")
        x0, y0, x1, y1 = round(r[0]*w), round(r[1]*h), round(r[2]*w), round(r[3]*h)
        if x1 <= x0 or y1 <= y0:raise ValueError("ROI contains no sampled pixels")
        amplified_raw = out/"amplified.rgb"
        amplified = np.memmap(amplified_raw, mode="w+", dtype=np.uint8, shape=frames.shape)
        clipped, values = 0, 0
        try:
            amplified[:] = frames
            for y in range(y0, y1, 16):
                stop = min(y1, y+16)
                block = frames[:, y:stop, x0:x1].astype(np.float32)
                transformed = np.fft.rfft(block, axis=0)
                transformed[~band] = 0
                detail = np.fft.irfft(transformed, n=n, axis=0).real
                result = block+(gain-1)*detail
                clipped += int(((result < 0) | (result > 255)).sum());values += result.size
                amplified[:, y:stop, x0:x1] = np.clip(result, 0, 255).astype(np.uint8)
            with output_raw.open("wb") as f:
                for i in range(n):
                    sheet = Image.new("RGB", (w*2, h+28), "#101820")
                    sheet.paste(Image.fromarray(frames[i]), (0, 0));sheet.paste(Image.fromarray(amplified[i]), (w, 0))
                    draw = ImageDraw.Draw(sheet)
                    draw.text((6, h+4), f"Original {start+i/sampling_fps:.3f}s", fill="white", font=font(12))
                    draw.text((w+6, h+4), f"Derived {low_hz:g}-{high_hz:g}Hz x{gain:g}", fill="white", font=font(12))
                    f.write(np.asarray(sheet).tobytes())
                    if i in (0, n//2, n-1):sheet.save(out/f"lens-{i:03}.png")
            video = out/"temporal-lens.mp4"
            command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w*2}x{h+28}",
                     "-r", sampling_fps, "-i", output_raw, "-c:v", "libx264", "-crf", 18, "-pix_fmt", "yuv420p", video], timeout=120)
            command([FFMPEG, "-v", "error", "-xerror", "-i", video, "-f", "null", "-"], timeout=120)
        finally:
            amplified._mmap.close();amplified_raw.unlink(missing_ok=True)
        result = {"source": str(source), "source_sha256": sha256(source), "video": str(video), "video_sha256": sha256(video),
                  "window": [start, end], "sample_count": n, "sampling_fps": sampling_fps, "source_size": source_size,
                  "region": r, "sample_size": [w, h], "band_hz": [low_hz, high_hz], "gain": gain,
                  "frequency_resolution_hz": sampling_fps/n, "clipped_channel_fraction": clipped/max(1, values),
                  "frames": [{"index": j, "timestamp": round(start+i/sampling_fps, 6), "path": str(out/f"lens-{i:03}.png")} for j, i in enumerate((0, n//2, n-1))],
                  "limitations": "Derived fixed-grid RGB band amplification, not new evidence. Camera/object motion, codec noise, FFT periodic boundary ringing and aliasing can be amplified. No motion stabilization, hidden-information recovery, medical/physical signal inference or factual colors. Inspect original alongside derived view. No audio.",
                  "manifest": str(out/"temporal-lens.json")}
        store.write_json(out/"temporal-lens.json", result)
        return result
    finally:
        frames._mmap.close();raw.unlink(missing_ok=True);output_raw.unlink(missing_ok=True)
