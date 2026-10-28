"""Actual FFmpeg LUT frames on a real picture, not invented colour mockups: assets/previews/lut/<id>.jpg (768x448) and an
atlas in outputs/. The bundled previews use a public-domain frame of the US Navy film "Operation Piranha" (NARA
428-NPC-35664, NAID 84617, 1965): sky, foliage, sand and skin in one frame. Any picture you may publish works:

    python scripts/build_lut_atlas.py --source path/to/frame.png [--credit "who made it, licence"]
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from editvideo import store, media_tasks, color_pipeline
from editvideo.media import FFMPEG, command, sha256

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True, help="a still you may publish (PNG/JPG)")
parser.add_argument("--credit", default="US Navy, Operation Piranha (1965), NARA 428-NPC-35664 (NAID 84617): public domain")
args = parser.parse_args()
store.initialize(recover=False)
source = Path(args.source).resolve()
tmp = store.DATA / "tmp" / "lut-previews"
tmp.mkdir(parents=True, exist_ok=True)
assets = store.ROOT / "assets" / "previews" / "lut"
records = []
for spec in [s for s in color_pipeline.catalog()["luts"] if s.get("preview")]:  # display LUTs; print looks are graph nodes
    task = media_tasks.submit("color", {"path": str(source), "input_space": "srgb", "input_range": "full", "lut_id": spec["id"]}, launch=False)
    media_tasks.run(task["id"])
    r = media_tasks.get(task["id"])
    assert r["state"] == "completed", r["error"]
    png = tmp / (spec["id"] + ".png")
    command([FFMPEG, "-y", "-v", "error", "-i", r["result"]["video"], "-frames:v", "1", "-vf",
             "zscale=pin=bt709:tin=bt709:min=bt709:rin=limited:p=bt709:t=iec61966-2-1:m=gbr:r=full,format=gbrp,format=rgb24", png])
    im = Image.open(png).convert("RGB")
    k = max(768 / im.width, 448 / im.height)  # cover 768x448, centred
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    x, y = (im.width - 768) // 2, (im.height - 448) // 2
    out = assets / (spec["id"] + ".jpg")
    im.crop((x, y, x + 768, y + 448)).save(out, quality=88)
    records.append({"id": spec["id"], "path": str(out.relative_to(store.ROOT)).replace("\\", "/"), "sha256": sha256(out), "lut_sha256": spec["sha256"]})
sheet = Image.new("RGB", (1536, 2 * 348), "#101820")
draw = ImageDraw.Draw(sheet)
for i, r in enumerate(records):
    x, y = i % 3 * 512, i // 3 * 348
    sheet.paste(Image.open(store.ROOT / r["path"]).resize((512, 320)), (x, y))
    draw.text((x + 12, y + 326), r["id"] + " / strength 100%", fill="white")
(store.ROOT / "outputs").mkdir(exist_ok=True)
sheet.save(store.ROOT / "outputs" / "lut-atlas.jpg")
store.write_json(store.ROOT / "outputs" / "color-lut-atlas.json",
                 {"source": source.name, "source_sha256": sha256(source), "credit": args.credit, "entries": records,
                  "scope": "The original display-domain LUTs applied through FFmpeg at strength 100 % for comparison; choose a "
                           "restrained strength for authored scenes."})
print(f"{len(records)} LUT previews written to assets/previews/lut")
