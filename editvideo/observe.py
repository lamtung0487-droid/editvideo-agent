"""Time-addressed perception for multimodal coding agents (no hidden vision model)."""
import math
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from . import store
from .graphics import font
from .media import FFMPEG, command, probe, sha256


def observe(path: str, timestamps: list[float] | None = None, max_frames: int = 6,
            width: int = 640, audio_start: float | None = None, audio_duration: float = 12):
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise ValueError("Cần đường dẫn file media")
    if not 1 <= max_frames <= 12 or not 160 <= width <= 1280:
        raise ValueError("max_frames: 1..12; width: 160..1280")
    info = probe(source)
    duration = float(info.get("format", {}).get("duration", 0) or 0)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    out = store.DATA/"observations"/str(uuid.uuid4())
    out.mkdir(parents=True)
    frames = []
    if video:
        still = source.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        times = [0.0] if still else timestamps if timestamps is not None else [
            duration*(i+.5)/max_frames for i in range(max_frames)]
        if not times or len(times) > max_frames:
            raise ValueError("Số timestamp phải từ 1 đến max_frames")
        for i, t in enumerate(times):
            if not math.isfinite(t) or t < 0 or (duration and t >= duration):
                raise ValueError(f"Timestamp {t} ngoài media, duration={duration}")
            target = out/f"frame-{i:02}.jpg"
            if still:
                with Image.open(source) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((width, width))
                    im.save(target, quality=90)
            else:
                command([FFMPEG, "-y", "-v", "error", "-ss", t, "-i", source,
                         "-frames:v", 1, "-vf", f"scale={width}:{width}:force_original_aspect_ratio=decrease", target], timeout=90)
            frames.append({"index": i, "timestamp": t, "path": str(target), "sha256": sha256(target)})
        with Image.open(frames[0]["path"]) as first:
            aspect=first.width/first.height
            tile_width=min(640 if aspect>=1 else 320,first.width)
        image_height=max(1,round(tile_width/aspect));tile_height=image_height+32
        columns=min(2 if aspect>=1 else 4,len(frames))
        tiles = []
        for f in frames:
            with Image.open(f["path"]) as im:
                im.thumbnail((tile_width, image_height))
                tile = Image.new("RGB", (tile_width, tile_height), "#111c23")
                tile.paste(im, ((tile_width-im.width)//2, (image_height-im.height)//2))
                ImageDraw.Draw(tile).text((12, image_height+4), f"{f['timestamp']:.3f}s", fill="white", font=font(18 if tile_width>=160 else 14))
                tiles.append(tile)
        sheet = Image.new("RGB", (columns*tile_width, math.ceil(len(tiles)/columns)*tile_height), "#111c23")
        for i, tile in enumerate(tiles):
            sheet.paste(tile, (i%columns*tile_width, i//columns*tile_height))
        sheet.save(out/"contact-sheet.jpg", quality=90)
    snippet = None
    if audio_start is not None:
        if not audio or not math.isfinite(audio_start) or audio_start < 0 or audio_start >= duration:
            raise ValueError("Không có audio hoặc audio_start ngoài thời lượng")
        if not 0 < audio_duration <= 30:
            raise ValueError("Audio snippet tối đa 30 giây")
        target = out/"listen.wav"
        command([FFMPEG, "-y", "-v", "error", "-ss", audio_start, "-i", source,
                 "-t", min(audio_duration, duration-audio_start), "-vn", "-ar", 16000, "-ac", 1, target], timeout=90)
        snippet = str(target)
    result = {"source": str(source), "sha256": sha256(source), "duration": duration,
              "streams": [{k: s.get(k) for k in ("codec_type", "codec_name", "width", "height", "r_frame_rate", "sample_rate")}
                          for s in info["streams"]], "frames": frames,
              "contact_sheet": str(out/"contact-sheet.jpg") if frames else None, "audio": snippet,
              "interpretation": "Pixels/audio for the calling AI to interpret; no automatic semantic claims or transcription."}
    store.write_json(out/"observation.json", result)
    result["manifest"] = str(out/"observation.json")
    return result


def extract_clip(path: str, start: float, end: float):
    source = Path(path).resolve(strict=True)
    duration = float(probe(source)["format"]["duration"])
    if not all(math.isfinite(x) for x in (start, end)) or start < 0 or end <= start or end > duration+.001 or end-start > 60:
        raise ValueError("Đoạn phải nằm trong video và tối đa 60 giây")
    dest = store.DATA/"observations"/str(uuid.uuid4())/"clip.mp4"
    dest.parent.mkdir(parents=True)
    command([FFMPEG, "-y", "-v", "error", "-ss", start, "-i", source, "-t", end-start,
             "-c:v", "libx264", "-preset", "fast", "-crf", 20, "-c:a", "aac", "-movflags", "+faststart", dest])
    return {"path": str(dest), "start": start, "end": end, "sha256": sha256(dest)}
