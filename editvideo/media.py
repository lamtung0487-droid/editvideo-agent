import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from . import store

FFMPEG = os.environ.get("FFMPEG_BINARY", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BINARY", "ffprobe")


_FFMPEG_MAJOR = []


def ffmpeg_major():
    """Major version of the FFmpeg in use (0 when it cannot be read)."""
    if not _FFMPEG_MAJOR:
        try:
            out = subprocess.run([FFMPEG, "-hide_banner", "-version"], capture_output=True, text=True, timeout=30).stdout
            m = re.search(r"version\s+n?(\d+)\.", out)
            _FFMPEG_MAJOR.append(int(m.group(1)) if m else 0)
        except Exception:
            _FFMPEG_MAJOR.append(0)
    return _FFMPEG_MAJOR[0]


def filter_complex_args(graph, work, name="filter.txt", inline_limit=6000):
    """-filter_complex for a short graph; a long one (a documentary mix of ~70 clips ran past Windows' 32 767-character
    command line) is written to a file in `work` and passed by name (-/filter_complex on FFmpeg 7+, else
    -filter_complex_script)."""
    if len(graph) <= inline_limit:
        return ["-filter_complex", graph]
    path = Path(work) / name
    path.write_text(graph, encoding="utf-8")
    return ["-/filter_complex" if ffmpeg_major() >= 7 else "-filter_complex_script", str(path)]


class Cancelled(Exception):
    pass


def command(args, cwd=None, log=None, cancelled=None, timeout=1800, env=None, done=None, stall=None):
    """Argument lists only. No shell, bounded execution, cancellation kills decoder.
    log: the output is written there as it comes (a killed or hung tool still leaves its last lines; it used to be
    written only after a normal exit, so the hung HyperFrames job of round 13 left no log at all).
    done: asked every 10 s while the process lives; True means the tool's work is on disk though the process has not
    exited (HyperFrames' CLI wrote a 164 s film in 6 minutes and sat until the 82-minute timeout): killed, finished.
    stall: (seconds, last_activity) — last_activity() returns the epoch of the tool's latest output (files it writes);
    no activity for that long and the tool is called stalled instead of waiting out the whole timeout."""
    import tempfile
    finished = False
    sink = Path(log).open("a+b") if log else tempfile.TemporaryFile()  # read back below: append mode alone cannot read
    with sink as output:
        start_at = output.tell()
        proc = subprocess.Popen([str(x) for x in args], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        started = asked = time.monotonic()
        try:
            while True:
                try:  # returns as soon as the process exits (a fixed sleep added ~120 ms to every probe)
                    proc.wait(timeout=0.15)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancelled and cancelled():
                    raise Cancelled()
                now = time.monotonic()
                if (done or stall) and now - asked > 10:
                    asked = now
                    if done and done():
                        finished = True
                        break
                    if stall and now - started > stall[0] and time.time() - max(stall[1](), time.time() - (now - started)) > stall[0]:
                        raise TimeoutError(f"Tác vụ media không tiến triển trong {int(stall[0])} s (stalled)")
                if now - started > timeout:
                    raise TimeoutError("Tác vụ media vượt thời gian cho phép")
        finally:
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                proc.kill()
                proc.wait()
        output.flush()
        output.seek(start_at)
        result = output.read().decode("utf-8", errors="replace")
    if proc.returncode and not finished:
        # The exit code tells a crash (killed for memory, access violation) from a tool's own error message.
        raise RuntimeError(f"exit code {proc.returncode}\n" + (result[-3500:] or "Không chạy được FFmpeg"))
    return result


def frame_grid(path, fps=30):
    """A video's frames against an exact 1/fps grid: count and the frames whose timestamp repeats or skips (index,
    step in grid units). Remotion's chunked render had given frames 1200, 1800 and 3000 of a film the timestamp of the
    frame before: the picture ran 1-3 frames ahead of the sound and a frame-by-frame comparison slid out of step."""
    from fractions import Fraction
    v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    tb = Fraction(v.get("time_base") or "1/90000")
    out = command([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts", "-of", "csv=p=0", path], timeout=600)
    pts = sorted(int(x.strip().rstrip(",")) for x in out.split() if x.strip().rstrip(",").lstrip("-").isdigit())
    step = 1 / (tb * fps)
    bad = [(i, round(float((b - a) / step), 3)) for i, (a, b) in enumerate(zip(pts, pts[1:]), 1) if abs((b - a) - step) > max(1, step * .02)]
    return {"frames": len(pts), "irregular": bad[:50], "irregular_count": len(bad), "time_base": str(tb)}


def rebuild_cfr(path, fps=30, cancelled=None):
    """Put every frame of a video on an exact 1/fps grid by its index (frame n at n/fps), keeping every frame (two
    frames that shared a timestamp are both kept, in decode order) and the audio as it is. Re-encodes the picture at
    CRF 14: regenerating timestamps on the copied stream (Annex B in at a declared rate) had shifted the B-frame order
    by one frame."""
    path = Path(path)
    fixed = path.with_name(path.stem + ".cfr.mp4")
    try:
        has_audio = any(s["codec_type"] == "audio" for s in probe(path)["streams"])
        command([FFMPEG, "-y", "-v", "error", "-i", path, "-map", "0:v:0", *(["-map", "0:a:0", "-c:a", "copy"] if has_audio else []),
                 "-fps_mode", "passthrough", "-vf", f"settb=1/{fps * 512},setpts=N*512", "-video_track_timescale", str(fps * 512), "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                 "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart", fixed],
                cancelled=cancelled, timeout=7200)
        fixed.replace(path)
    finally:
        fixed.unlink(missing_ok=True)
    return frame_grid(path, fps)


def probe(path):
    output = command([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", path], timeout=60)
    return json.loads(output)


def sha256(path):
    h = hashlib.sha256()
    # Large cached models also live on HDDs. Tell Windows this is a sequential
    # scan and avoid interleaved tiny reads defeating read-ahead.
    fd=os.open(str(path),os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_SEQUENTIAL",0))
    with os.fdopen(fd,"rb") as f:
        for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


WORKING_MAX_PIXELS = 40_000_000


def working_copy(path):
    """A working copy every engine and measurement reads the same way, made at import. Archival scans: a TIFF/BMP, or
    an image over 40 MP (a 1902 map scan is 93 MP), becomes a JPEG within 40 MP and 8192 px on the long side. Pictures
    a browser shows differently from their stored pixels are baked as shown: EXIF-rotated photos, rotated phone video
    and anamorphic video (non-square pixels: PAL 720x576 at 16:15 shows 4:3; frame extraction drew it 5:4).
    Returns (path to import, original sha256), or (path, None) when the file can be used as it is. The original stays
    where it is; its sha is the import's provenance (credits)."""
    import math
    p = Path(path)
    ext = p.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return _display_video(p)
    if ext not in (".tif", ".tiff", ".bmp", ".png", ".jpg", ".jpeg", ".webp"):
        return p, None
    limit, Image.MAX_IMAGE_PIXELS = Image.MAX_IMAGE_PIXELS, None  # opening a known archival scan is not a decompression bomb
    try:
        with Image.open(p) as im:
            try:
                orient = int(im.getexif().get(0x0112) or 1)
            except Exception:
                orient = 1
            w, h = (im.size[1], im.size[0]) if orient in (5, 6, 7, 8) else im.size  # as shown
            if ext not in (".tif", ".tiff", ".bmp") and w * h <= WORKING_MAX_PIXELS and max(w, h) <= 8192 and orient == 1:
                return p, None
            k = min(1.0, math.sqrt(WORKING_MAX_PIXELS / (w * h)), 8192 / max(w, h))
            digest = sha256(p)
            nw, nh = max(1, int(w * k)), max(1, int(h * k))  # floor: rounding up put a 1902 map 140 pixels over the limit
            alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
            out = store.DATA / "cache" / "working-images" / f"{digest[:24]}-{nw}x{nh}-v2.{'png' if alpha else 'jpg'}"
            if not out.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                if im.mode in ("I;16", "I;16B", "I", "F"):  # 16-bit/float scans: scale to 8 bits
                    im = im.point(lambda v: v / 256).convert("L")
                im = ImageOps.exif_transpose(im).convert("RGBA" if alpha else "RGB")  # rotated first: nw x nh are shown sizes
                if im.size != (nw, nh):
                    im = im.resize((nw, nh), Image.LANCZOS)
                tmp = out.with_name(f"{out.stem}.{uuid.uuid4().hex[:8]}.part{out.suffix}")
                try:
                    im.save(tmp, **({} if alpha else {"quality": 92}))
                    tmp.replace(out)
                finally:
                    tmp.unlink(missing_ok=True)
            return out, digest
    finally:
        Image.MAX_IMAGE_PIXELS = limit


VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpg", ".mpeg", ".ogv", ".mts", ".m2ts")


def _rotation(v):
    """Display rotation of a video stream in degrees (0/90/180/270), from its display matrix or rotate tag."""
    r = next((sd.get("rotation") for sd in v.get("side_data_list") or [] if "rotation" in sd), None)
    if r is None:
        r = (v.get("tags") or {}).get("rotate", 0)
    try:
        return int(round(float(r))) % 360
    except (TypeError, ValueError):
        return 0


def display_size(path):
    """(width, height) as a player or browser shows the picture: pixel aspect and rotation applied (EXIF orientation for
    images). Stored sizes put a portrait phone clip, a PAL transfer or a rotated JPEG in the wrong shape."""
    p = Path(path)
    if p.suffix.lower() not in VIDEO_EXTENSIONS:
        try:
            with Image.open(p) as im:
                o = int(im.getexif().get(0x0112) or 1)
                return (im.size[1], im.size[0]) if o in (5, 6, 7, 8) else im.size
        except Exception:
            pass
    v = next(x for x in probe(str(p))["streams"] if x["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    try:
        num, den = (int(x) for x in str(v.get("sample_aspect_ratio") or "1:1").split(":"))
    except ValueError:
        num = den = 1
    if num > 0 and den > 0 and abs(num / den - 1) >= .01:
        w, h = (round(w * num / den), h) if num > den else (w, round(h * den / num))
    return (h, w) if _rotation(v) in (90, 270) else (w, h)


def _display_video(p):
    try:
        v = next(x for x in probe(str(p))["streams"] if x["codec_type"] == "video")
        num, den = (int(x) for x in str(v.get("sample_aspect_ratio") or "1:1").split(":"))
    except (StopIteration, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError):
        return p, None
    w, h, rot = int(v["width"]), int(v["height"]), _rotation(v)
    square = num <= 0 or den <= 0 or abs(num / den - 1) < .01
    if square and rot == 0:
        return p, None
    nw, nh = (w, h) if square else (round(w * num / den / 2) * 2, h) if num > den else (w, round(h * den / num / 2) * 2)
    if rot in (90, 270):  # FFmpeg rotates before the filters run: sizes as shown
        nw, nh = nh, nw
    digest = sha256(p)
    trc = v.get("color_transfer")
    hdr = trc in ("arib-std-b67", "smpte2084")  # HLG / PQ phone video: kept 10-bit and tagged, tone-mapped later by the engine proxy
    out = store.DATA / "cache" / "working-videos" / f"{digest[:24]}-{nw}x{nh}-cfr-g30{'-hdr10' if hdr else ''}.mp4"
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f"{out.stem}.{uuid.uuid4().hex[:8]}.part.mp4")  # two imports at once never share a temp file
        # constant rate at the stream's nominal rate (old transfers drop frames; a gap holds the frame before it) and a
        # keyframe a second, so neither engine needs a further proxy
        rate = v.get("r_frame_rate") or "30/1"
        try:
            command([FFMPEG, "-y", "-v", "error", "-i", str(p), "-map", "0:v:0", "-map", "0:a:0?", "-vf", f"scale={nw}:{nh}:flags=lanczos,setsar=1,fps={rate}",
                     "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
                     *(["-pix_fmt", "yuv420p10le", "-profile:v", "high10", "-color_primaries", "bt2020", "-color_trc", trc, "-colorspace", "bt2020nc"]
                       if hdr else ["-pix_fmt", "yuv420p"]),
                     "-metadata:s:v:0", "rotate=0", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)])
            tmp.replace(out)
        finally:
            tmp.unlink(missing_ok=True)
    return out, digest


def pack_gltf(gltf_path, out_path, files=None):
    """Pack a .gltf with external buffers and images into one self-contained .glb (what Scene3D accepts). files maps a
    URI in the .gltf to a local path when the parts were saved under other names (as fetch_source names them)."""
    import struct
    gltf_path = Path(gltf_path)
    gltf = json.loads(gltf_path.read_text(encoding="utf-8"))
    where = lambda uri: Path(files[uri]) if files and uri in files else gltf_path.parent / urllib.parse.unquote(uri)
    blob, offsets = bytearray(), []
    for b in gltf.get("buffers", []):  # every buffer into one BIN chunk, each start 4-byte aligned
        if "uri" not in b or b["uri"].startswith("data:"):
            raise ValueError("pack_gltf: only external buffer files are supported")
        blob += b"\0" * (-len(blob) % 4)
        offsets.append(len(blob))
        blob += where(b["uri"]).read_bytes()
    for v in gltf.get("bufferViews", []):
        v["byteOffset"] = v.get("byteOffset", 0) + offsets[v.get("buffer", 0)]
        v["buffer"] = 0
    for img in gltf.get("images", []):  # textures become buffer views inside the GLB
        if "uri" not in img:
            continue
        data = where(img["uri"]).read_bytes()
        mime = img.get("mimeType") or ("image/png" if data[:4] == b"\x89PNG" else "image/jpeg")
        blob += b"\0" * (-len(blob) % 4)
        gltf.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob += data
        img.pop("uri")
        img.update(bufferView=len(gltf["bufferViews"]) - 1, mimeType=mime)
    blob += b"\0" * (-len(blob) % 4)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    Path(out_path).write_bytes(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
                               + struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))
    return Path(out_path)


def register_model(pid, path, original_name, tags="", role="illustration", source_url="", persist=True):
    """Self-contained binary glTF (.glb) for Scene3D. Validates the header; no external buffers/URIs."""
    import struct
    data = Path(path).read_bytes()
    if len(data) > 64*1024*1024:
        raise ValueError("GLB model must be <= 64 MB")
    if len(data) < 20 or data[:4] != b"glTF" or struct.unpack("<I", data[4:8])[0] != 2 or struct.unpack("<I", data[8:12])[0] != len(data):
        raise ValueError("Only self-contained binary glTF 2.0 (.glb) is supported")
    chunk_len, chunk_type = struct.unpack("<II", data[12:20])
    if chunk_type != 0x4E4F534A:
        raise ValueError("GLB JSON chunk missing")
    gltf = json.loads(data[20:20+chunk_len])
    if any("uri" in b for b in gltf.get("buffers", [])) or any("uri" in i for i in gltf.get("images", [])):
        raise ValueError("GLB references external files; embed buffers/images first")
    meta = {"id": Path(path).stem, "name": original_name, "path": str(Path(path).resolve()), "kind": "model", "duration": 0,
            "width": None, "height": None, "tags": tags, "role": role, "sha256": sha256(path), "source_url": source_url,
            "created_at": store.now(), "model": {"meshes": len(gltf.get("meshes", [])), "animations": [a.get("name", f"anim{i}") for i, a in enumerate(gltf.get("animations", []))],
                                                 "materials": len(gltf.get("materials", []))}}
    if persist:
        store.add_asset(pid, meta)
    return meta


def register(pid, path, original_name, tags="", role="illustration", source_url="", persist=True):
    if Path(path).suffix.lower() == ".glb":
        return register_model(pid, path, original_name, tags, role, source_url, persist)
    info = probe(path)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    ext = Path(path).suffix.lower()
    image = ext in (".png", ".jpg", ".jpeg", ".webp")
    audio_file = ext in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")
    # Embedded cover art is a video stream, not a reason to classify MP3 as a clip.
    kind = "image" if image else "audio" if audio_file and audio else "video" if video else "audio" if audio else None
    if kind is None:
        raise ValueError("File không có hình hoặc âm thanh đọc được")
    if video and video["width"] * video["height"] > 40000000:
        raise ValueError("Ảnh/video quá lớn (giới hạn 40 megapixel)")
    aid = Path(path).stem
    duration = float(info.get("format", {}).get("duration", 0) or 0)
    if kind != "image" and (duration <= 0 or duration > 3600):
        raise ValueError("Thời lượng media phải từ 0 đến 60 phút")
    meta = {"id": aid, "name": original_name, "path": str(Path(path).resolve()), "kind": kind,
            "duration": duration, "width": video.get("width") if video else None,
            "height": video.get("height") if video else None, "tags": tags, "role": role,
            "sha256": sha256(path), "source_url": source_url, "created_at": store.now()}
    if kind == "video":
        meta["alpha"] = video.get("tags",{}).get("alpha_mode") == "1" or video.get("tags",{}).get("ALPHA_MODE") == "1" or "a" in video.get("pix_fmt","") and video.get("pix_fmt","").startswith(("rgba","bgra","yuva"))
    if video and kind in ("image", "video"):
        thumb = Path(path).with_suffix(".thumb.jpg")
        if image:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((480, 480))
                im.save(thumb, quality=88)
        else:
            command([FFMPEG, "-y", "-v", "error", "-ss", min(1, duration / 3), "-i", path,
                     "-frames:v", "1", "-vf", "scale=480:480:force_original_aspect_ratio=decrease", thumb], timeout=90)
        meta["thumbnail"] = str(thumb)
    if persist:
        store.add_asset(pid, meta)
    return meta


def normalize_audio(source, dest, cancelled=None, log=None):
    command([FFMPEG, "-y", "-v", "error", "-i", source, "-vn", "-ac", "1", "-ar", "48000",
             "-c:a", "pcm_s16le", dest], cancelled=cancelled, log=log)


def safe_asset_path(pid, aid):
    a = store.find_asset(pid, aid)
    p = Path(a["path"]).resolve()
    if not p.is_relative_to(store.folder(pid).resolve()):
        raise ValueError("Đường dẫn tư liệu không hợp lệ")
    return p
