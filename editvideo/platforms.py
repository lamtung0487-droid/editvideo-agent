"""Short-form platform facts in one place (TikTok, Instagram Reels, YouTube Shorts): interface zones, safe areas,
delivery specs and the evidence behind each short-form rule. Data with its source; nothing here predicts retention.

Two kinds of zone:
- "ads": the platforms' published AD safe zones at 1080x1920. Official, and conservative for organic posts (an ad adds
  a CTA button and a longer caption block).
- "organic": the feed UI of an ordinary post (tabs, action rail, caption and username block). Not published; an
  editable heuristic.
"""
from PIL import Image, ImageDraw

W, H = 1080, 1920

# Published ad safe zones in px at 1080x1920 (TikTok publishes a 720x1280 template: 160 top / 440 bottom / 80 sides;
# the right action column, ~180 px from y≈840, was measured by a third party; Shorts' numbers were read from Google's
# guide image by a third party).
ADS_PX = {
    "tiktok": {"top": 240, "bottom": 660, "left": 120, "right": 120, "rail": (900, 840)},
    "reels": {"top": 269, "bottom": 672, "left": 65, "right": 65, "rail": None},
    "shorts": {"top": 288, "bottom": 672, "left": 48, "right": 192, "rail": None},
}
# Organic feed UI, normalised (heuristic): top tabs, right action rail, caption/username/music block.
ORGANIC = {
    "tiktok": {"top": (0, 0, 1, .08), "right_rail": (.85, .55, 1, .85), "bottom": (0, .80, 1, 1)},
    "reels": {"top": (0, 0, 1, .07), "right_rail": (.86, .50, 1, .85), "bottom": (0, .80, 1, 1)},
    "shorts": {"top": (0, 0, 1, .06), "right_rail": (.86, .55, 1, .88), "bottom": (0, .82, 1, 1)},
}
PLATFORMS = tuple(ADS_PX)
# Common organic safe area: clear of every platform's organic UI (the existing editable default).
ORGANIC_SAFE = (.08, .12, .82, .78)

DELIVERY = {  # published upload limits; the encode below satisfies all three
    "tiktok": {"max_seconds": 600, "min_size": (540, 960), "max_mb": 500},
    "reels": {"max_seconds": 180, "min_size": (540, 960), "audio": "AAC stereo >= 128 kbps"},
    "shorts": {"max_seconds": 180, "min_size": (540, 960)},
}
# One encode for all three (YouTube's published 1080p30 recommendation is the strictest stated spec).
ENCODE = {"width": W, "height": H, "fps": 30, "codec": "h264 High, yuv420p, BT.709, constant frame rate",
          "video_kbps": 8000, "max_kbps": 12000, "audio": "AAC-LC 48 kHz stereo 256 kbps", "faststart": True,
          "loudness_lufs": -14.0, "true_peak_dbtp": -1.0,
          "master_true_peak_dbtp": -2.0}  # headroom: AAC encoding raised a -1.0 dBTP master to -0.7

# Evidence behind the short-form rules: S = standard/spec, PR = peer-reviewed, P = platform research (internal,
# correlational), A = academic not peer-reviewed, H = heuristic/practice. Short source keys; URLs in the docs.
EVIDENCE = {
    "safe_area": ("S", "TikTok/Meta/Google ad safe zones (ads only)"),
    "first_frame": ("H", "Meta feed attention: ~1.7 s per item, recall after 0.25 s"),
    "first_change": ("H", "derived from Meta feed attention"),
    "first_text": ("P", "TikTok: text within 7 s; key message within 3 s in 63% of top-CTR ads"),
    "key_message": ("P", "TikTok creative tips: key message within 3 s"),
    "hold_5s": ("PR", "Snapchat Spotlight, 90k videos: staying past 5 s correlates r=0.93 with watch share (ECCV'24)"),
    "cut_rate": ("A", "50 top talking-head TikToks: 0.19-0.52 cuts/s; faster pacing lowered completion (N=242)"),
    "longest_still": ("H", "derived from the low-pace percentile of the same 50 videos"),
    "caption_coverage": ("P", "Meta: captions +12% view time; ~69% watch muted in public (survey)"),
    "caption_lines": ("S", "BBC/Netflix subtitle guidelines: <= 2 lines, <= 42 characters per line"),
    "reading_time": ("S", "BBC subtitles: 160-180 wpm (~0.33 s per word) when there is no voice"),
    "contrast": ("S", "WCAG 2.1: 4.5:1 (3:1 for large text)"),
    "av_sync": ("S", "ITU-R BT.1359 / EBU R37: sound within +40/-60 ms of the picture"),
    "loudness": ("H", "no published TikTok/Reels target; -14 LUFS is the measured YouTube norm"),
    "true_peak": ("S", "EBU R128 family: <= -1 dBTP"),
    "cta": ("P", "TikTok conversion model: text CTA +152% (ads)"),
    "length": ("P", "TikTok ads: 21-34 s +280% (conversion); Reels/Shorts cap 180 s"),
    "scenes": ("P", "TikTok: >= 5 distinct scenes +171% (gaming ads)"),
    "native": ("P", "TikTok: 9:16 without bars +91%, >= 720p +312% (ads)"),
    "loop": ("H", "no evidence found for seamless loops; informational"),
    "face_clear": ("H", "practice: keep the speaker's eyes and mouth clear; TikTok's data favours visible people addressing the camera"),
}


def zones(platform="tiktok", kind="organic"):
    """Named UI rectangles, normalised (x0, y0, x1, y1), that cover the picture on this platform."""
    if kind == "organic":
        return dict(ORGANIC[platform])
    p = ADS_PX[platform]
    z = {"top": (0, 0, 1, p["top"] / H), "bottom": (0, 1 - p["bottom"] / H, 1, 1),
         "left": (0, 0, p["left"] / W, 1), "right": (1 - p["right"] / W, 0, 1, 1)}
    if p["rail"]:
        z["right_rail"] = (p["rail"][0] / W, p["rail"][1] / H, 1, 1 - p["bottom"] / H)
    return z


def safe_area(platform="all", kind="organic"):
    """The rectangle clear of the UI (normalised). platform "all" = clear on TikTok, Reels and Shorts at once."""
    names = PLATFORMS if platform == "all" else (platform,)
    if kind == "organic":
        if platform == "all":
            return ORGANIC_SAFE
        z = ORGANIC[platform]
        return (.08, round(z["top"][3] + .04, 4), round(z["right_rail"][0] - .03, 4), round(z["bottom"][1] - .02, 4))
    x0 = max(ADS_PX[n]["left"] for n in names) / W
    x1 = 1 - max(ADS_PX[n]["right"] for n in names) / W
    for n in names:
        if ADS_PX[n]["rail"]:
            x1 = min(x1, ADS_PX[n]["rail"][0] / W)
    y0 = max(ADS_PX[n]["top"] for n in names) / H
    y1 = 1 - max(ADS_PX[n]["bottom"] for n in names) / H
    return (round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4))


def covered(box, platform="tiktok", kind="organic"):
    """{zone: overlap fraction of box} for the zones a normalised box overlaps."""
    x0, y0, x1, y1 = box
    area = max(1e-9, (x1 - x0) * (y1 - y0))
    out = {}
    for name, (a, b, c, d) in zones(platform, kind).items():
        ov = max(0.0, min(x1, c) - max(x0, a)) * max(0.0, min(y1, d) - max(y0, b))
        if ov > 0:
            out[name] = round(ov / area, 3)
    return out


def draw_ui(img, platform="tiktok", kind="organic"):
    """The platform interface drawn over a frame (PIL image, any size): translucent zones, a mock action rail and
    caption block, and the safe area outline, so a reviewer sees what the viewer's screen will cover."""
    im = img.convert("RGBA")
    w, h = im.size
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for name, (a, b, c, e) in zones(platform, kind).items():
        d.rectangle([a * w, b * h, c * w, e * h], fill=(255, 40, 80, 70))
    z = ORGANIC[platform]
    rx = (z["right_rail"][0] + z["right_rail"][2]) / 2 * w
    for i in range(5):  # avatar, like, comment, save, share
        cy = (z["right_rail"][1] + (z["right_rail"][3] - z["right_rail"][1]) * (i + .5) / 5) * h
        r = .028 * w
        d.ellipse([rx - r, cy - r, rx + r, cy + r], outline=(255, 255, 255, 220), width=max(2, w // 270))
    by = z["bottom"][1] * h
    for i, frac in enumerate((.35, .62, .48)):  # @username, caption line, music ticker
        y = by + (.025 + .045 * i) * h
        d.rounded_rectangle([.04 * w, y, (.04 + frac * .8) * w, y + .022 * h], radius=.01 * h, fill=(255, 255, 255, 170))
    s = safe_area(platform, kind)
    d.rectangle([s[0] * w, s[1] * h, s[2] * w, s[3] * h], outline=(60, 255, 120, 230), width=max(2, w // 360))
    return Image.alpha_composite(im, over).convert("RGB")
