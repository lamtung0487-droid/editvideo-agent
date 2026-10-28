"""Round 11: semantic perception (open-vocabulary detection, text/image search), three new genres, technical debt."""
import subprocess
from pathlib import Path
import numpy as np
import pytest
from editvideo import store
from editvideo.media import FFMPEG

ENGINES_READY = (Path(__file__).parents[1] / "engines" / "node_modules").is_dir()


def _binary_counter(path, fps=24, seconds=3):
    """Frame N shows its number in six vertical bands (white = bit set): readable through any range or gamma change."""
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=320x180:r={fps}:d={seconds}", "-vf",
                    r"geq=lum='16+219*mod(floor(N/pow(2\,floor(X*6/W)))\,2)':cb=128:cr=128",
                    "-c:v", "libx264", "-qp", "0", "-g", "1", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _read_counter(img):
    g = np.asarray(img.convert("L").resize((60, 36)), np.float32)
    return sum(int(g[8:28, b * 10 + 3:b * 10 + 7].mean() > 128) << b for b in range(6))


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_off_speed_shots_show_the_same_source_frames_in_both_engines(tmp_path, monkeypatch):
    """A 0.85x shot of a 24 fps clip: both engines play its pre-timed 30 fps clip, frame k = the source frame covering
    s0 + k * 0.85 / 30 (HyperFrames had shown the previous source frame on about a third of the frames)."""
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    src = _binary_counter(tmp_path / "count.mp4")
    frames = [0, 3, 7, 11, 14, 18, 21, 24]
    want = [int(np.floor((.2 + f * .85 / 30) * 24 + 1e-6)) for f in frames]
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", 30, engine, "offspeed")["id"]
        aid = agent.import_media(pid, str(src), "count", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
        p = agent.read(pid)
        t = p["timeline"]
        t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": .2, "playback_rate": .85, "text": "", "motion": "hold", "effects": []}]
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
        scaffold(pid, engine, False)
        got = [_read_counter(Image.open(f["path"])) for f in snapshot(pid, engine, frames)["frames"]]
        assert got == want, (engine, got, want)


def test_fetch_source_stops_waiting_after_a_minute(tmp_path, monkeypatch):
    import time
    import urllib.error
    from editvideo import resources
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    def busy(req, timeout=60):
        raise urllib.error.HTTPError(req.full_url, 429, "Too many requests", {"Retry-After": "50"}, None)
    monkeypatch.setattr(resources.urllib.request, "urlopen", busy)
    monkeypatch.setattr(resources, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="try this file again"):
        resources.fetch_source("https://example.org/a.mp3", "other", "t", "CC0", "c", "https://example.org", "audio", "a.mp3", 5)
    assert sum(slept) <= 60  # one call never hangs for minutes


def test_pack_gltf_embeds_buffers_and_textures(tmp_path):
    import json
    import struct
    from PIL import Image
    from editvideo.media import pack_gltf
    tri = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    (tmp_path / "geo.bin").write_bytes(tri)
    Image.new("RGB", (4, 4), (200, 30, 30)).save(tmp_path / "tex.png")
    gltf = {"asset": {"version": "2.0"}, "buffers": [{"uri": "geo.bin", "byteLength": len(tri)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(tri)}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]}],
            "images": [{"uri": "textures/tex.png"}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
    (tmp_path / "m.gltf").write_text(json.dumps(gltf))
    out = pack_gltf(tmp_path / "m.gltf", tmp_path / "m.glb", files={"textures/tex.png": str(tmp_path / "tex.png")})  # parts saved under other names
    data = out.read_bytes()
    assert data[:4] == b"glTF" and struct.unpack("<I", data[8:12])[0] == len(data)
    n = struct.unpack("<I", data[12:16])[0]
    packed = json.loads(data[20:20 + n])
    assert "uri" not in packed["buffers"][0] and packed["images"][0]["mimeType"] == "image/png" and len(packed["bufferViews"]) == 2
    from editvideo.media import register_model  # what Scene3D accepts
    assert register_model("x", out, "m.glb", persist=False)["model"]["meshes"] == 1


MODELS_READY = all((store.DATA / "models" / n / "install.json").is_file() for n in ("owlv2", "siglip"))
needs_models = pytest.mark.skipif(not MODELS_READY, reason="OWLv2/SigLIP not installed (find_subjects allow_download)")


def _shapes(path, circle_at=(120, 170), square_at=(640, 180), size=(960, 540)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, (235, 235, 235))
    d = ImageDraw.Draw(im)
    if circle_at:
        d.ellipse([circle_at[0], circle_at[1], circle_at[0] + 200, circle_at[1] + 200], fill=(220, 30, 30))
    if square_at:
        d.rectangle([square_at[0], square_at[1], square_at[0] + 180, square_at[1] + 180], fill=(30, 60, 220))
    im.save(path)
    return path


@needs_models
def test_detect_finds_named_subjects_where_they_are(tmp_path):
    from editvideo import semantic
    img = _shapes(tmp_path / "shapes.png")
    r = semantic.detect([str(img)], ["red circle", "blue square"], fps=1)
    per = next(iter(r["clips"].values()))
    assert per["red circle"]["best"]["box"] == pytest.approx([.125, .315, .333, .685], abs=.04)
    assert per["blue square"]["best"]["box"][0] > .6 and Path(r["sheet"]).is_file()
    # in a clip: present only while it is on screen (the circle enters at 1 s and leaves at 3 s)
    clip = tmp_path / "enter.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xebebeb:s=960x540:r=30:d=4", "-vf",
                    "drawbox=x=300:y=170:w=200:h=200:color=0xdc1e1e:t=fill:enable='between(t,1,3)'", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    spans = next(iter(semantic.detect([str(clip)], ["red square"], fps=2)["clips"].values()))["red square"]["spans"]
    assert len(spans) == 1 and spans[0][0] == pytest.approx(1, abs=.5) and spans[0][1] == pytest.approx(3, abs=.5)


@needs_models
def test_search_ranks_by_text_and_by_example(tmp_path):
    from editvideo import semantic
    red, blue = _shapes(tmp_path / "red.png", square_at=None), _shapes(tmp_path / "blue.png", circle_at=None)
    by_text = semantic.search([str(blue), str(red)], text="a red circle")
    assert Path(by_text["windows"][0]["path"]).name == "red.png"
    by_image = semantic.search([str(red), str(blue)], image={"path": str(blue), "at": 0})
    assert Path(by_image["windows"][0]["path"]).name == "blue.png"


@needs_models
def test_lower_third_keeps_clear_of_a_named_subject(tmp_path, monkeypatch):
    from editvideo import agent, professional
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    monkeypatch.setattr("editvideo.semantic.model_root", lambda n: Path(__file__).parents[1] / "data" / "models" / n)
    img = _shapes(tmp_path / "bl.png", circle_at=(80, 300), square_at=None)  # the subject sits bottom left, where cards go
    pid = agent.create_silent("landscape", 90, "remotion", "avoid")["id"]
    aid = agent.import_media(pid, str(img), "bl", "evidence", True, agent.read(pid)["revision"])["asset"]["id"]
    p = agent.read(pid)
    t = p["timeline"]
    t["shots"] = [{**t["shots"][0], "asset_id": aid, "fit": "cover", "source_start": 0, "text": "", "motion": "hold"}]
    agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": t}])
    req = {"recipe": "lower_third", "id": "lt", "start_frame": 10, "end_frame": 80, "text": "Tên", "secondary_text": "Vai trò"}
    plain = professional.compose(pid, agent.read(pid)["revision"], req, dry_run=True)
    kept = professional.compose(pid, agent.read(pid)["revision"], {**req, "avoid": "red circle"}, dry_run=True)
    x = lambda r: next(o["layer"]["x"] for o in r["operations"] if o["op"] == "upsert_layer" and o["layer"]["id"] == "lt-name")
    assert x(plain) < .2 and x(kept) > .5  # the card moved to the clear side


def test_archival_scans_import_as_working_copies_that_keep_their_credit(tmp_path, monkeypatch):
    from PIL import Image
    from editvideo import agent, resources
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(resources, "ROOT", tmp_path)
    store.initialize(recover=False)
    scan = tmp_path / "scan.tiff"
    Image.new("RGB", (900, 600), (120, 100, 80)).save(scan)  # a TIFF: no browser decodes it
    big = tmp_path / "map.jpg"
    Image.new("L", (7000, 6000), 200).save(big, quality=60)  # 42 MP: over the import limit
    resources.register_resource(str(scan), "image", "Old photo", "CC BY 4.0", "An Archive", "https://example.org/scan")
    pid = agent.create_silent("landscape", 60, "remotion", "archive")["id"]
    a = agent.import_media(pid, str(scan), "scan", "evidence", True, agent.read(pid)["revision"])["asset"]
    b = agent.import_media(pid, str(big), "map", "evidence", True, agent.read(pid)["revision"])["asset"]
    assert Path(a["path"]).suffix == ".jpg" and (a["width"], a["height"]) == (900, 600)
    assert b["width"] * b["height"] <= 40_000_000 and b["width"] / b["height"] == pytest.approx(7000 / 6000, rel=.01)
    t = agent.read(pid)["timeline"]
    t["shots"][0] = {**t["shots"][0], "asset_id": a["id"]}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    assert "An Archive (CC BY 4.0)" in resources.project_credits(pid)["text"]  # traced through the original's sha


def test_text_is_measured_with_the_face_a_browser_draws():
    from editvideo.design_library import fit_size, font, layout_text, pick_face
    family = font("bevietnampro")  # bundled 400 / 600 / 700
    assert [pick_face(family, w)["weight"] for w in (300, 500, 550, 800)] == ["400", "400", "600", "700"]  # CSS Fonts 4 matching
    assert layout_text("bevietnampro", "Một ngày", 48, 800, 500)["line_widths"] == layout_text("bevietnampro", "Một ngày", 48, 800, 400)["line_widths"]
    assert fit_size("bevietnampro", "Một ngày giữa thiên nhiên", .5, 1920, 500, 48) > 0  # it had raised "not bundled"


def test_anamorphic_video_imports_with_square_pixels(tmp_path, monkeypatch):
    """PAL 720x576 at 16:15 shows 4:3: a browser honours the pixel aspect, frame extraction does not, so the engines
    drew it at different widths. The import is a square-pixel working copy whose credit still traces to the original."""
    from editvideo import agent, resources
    from editvideo.media import probe
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(resources, "ROOT", tmp_path)
    store.initialize(recover=False)
    film = tmp_path / "film.webm"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=720x576:r=30:d=1", "-vf", "setsar=16/15",
                    "-c:v", "libvpx-vp9", "-b:v", "1M", str(film)], check=True)
    resources.register_resource(str(film), "footage", "Old film", "CC0", "An Archive", "https://example.org/film")
    pid = agent.create_silent("landscape", 30, "remotion", "film")["id"]
    a = agent.import_media(pid, str(film), "film", "evidence", True, agent.read(pid)["revision"])["asset"]
    v = next(s for s in probe(a["path"])["streams"] if s["codec_type"] == "video")
    assert (a["width"], a["height"]) == (768, 576) and (int(v["width"]), v.get("sample_aspect_ratio", "1:1")) == (768, "1:1")
    t = agent.read(pid)["timeline"]
    t["shots"][0] = {**t["shots"][0], "asset_id": a["id"]}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    assert "An Archive (CC0)" in resources.project_credits(pid)["text"]


def test_frame_subject_keeps_it_whole_in_the_free_region():
    from editvideo.semantic import frame_subject
    # a compact subject: cover, centred on it
    f = frame_subject([.60, .30, .70, .70], 1920, 1080, 1080, 1920)
    assert f["fit"] == "cover" and not f["effects"] and (f["subject"][0] + f["subject"][2]) / 2 == pytest.approx(.5, abs=.01)
    # too wide for a 9:16 cover: contain framed up by a held zoom (never above 2x), whole, centred in the region
    region = (0, .3, 1, .9)
    f = frame_subject([.31, .10, .69, .95], 3840, 2160, 1080, 1920, region=region)
    z = f["effects"][0]["params"]
    assert f["fit"] == "contain" and z["cut"] and 0 < z["amount"] <= 1
    x0, y0, x1, y1 = f["subject"]
    assert 0 <= x0 and x1 <= 1 and region[1] - 1e-3 <= y0 and y1 <= region[3] + 1e-3
    assert ((y0 + y1) / 2, (x0 + x1) / 2) == (pytest.approx(.6, abs=.01), pytest.approx(.5, abs=.01))
    # already as wide as the canvas at contain: contain, no zoom
    assert frame_subject([0, .3, .99, .7], 3840, 2160, 1080, 1920)["effects"] == []


def test_text_contrast_is_read_through_held_zooms_and_letterbox_bands(tmp_path):
    """A white frame contained on a black 9:16 canvas: a white title above the band reads on black; the same title over
    the band, or where a 2x held zoom has brought the picture under it, does not."""
    from PIL import Image
    from editvideo.review import _plate_contrast
    img = tmp_path / "white.png"
    Image.new("RGB", (1600, 900), (250, 250, 250)).save(img)
    asset = lambda _id: {"kind": "image", "width": 1600, "height": 900, "path": str(img)}
    shot = {"id": "s", "start_frame": 0, "end_frame": 60, "asset_id": "a", "fit": "contain", "focus_x": .5, "focus_y": .5, "effects": []}
    t = {"shots": [shot], "layers": []}
    design = {"background": "#000000"}
    title = lambda y: {"id": "t", "kind": "text", "text": "Title", "x": .1, "y": y, "width": .8, "height": .05, "color": "#ffffff",
                       "font_size": 60, "start_frame": 0, "end_frame": 60, "z": 900}
    assert _plate_contrast(title(.2), t, asset, design, 1080, 1920) > 15  # the band is .34-.66: black under the title
    assert _plate_contrast(title(.45), t, asset, design, 1080, 1920) < 1.5
    shot["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.0, "focus_x": .5, "focus_y": .5, "cut": True}}]
    assert _plate_contrast(title(.2), t, asset, design, 1080, 1920) < 1.5  # the 2x picture now reaches .18
    thin, soft = ({**title(.45), "effects": [{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": a}}]} for a in (2, 18))
    assert _plate_contrast(thin, t, asset, design, 1080, 1920) < 1.5 and _plate_contrast(soft, t, asset, design, 1080, 1920) is None


def test_silent_projects_paint_their_colour_behind_contained_shots(tmp_path, monkeypatch):
    from editvideo import agent
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    p = agent.create_silent("vertical", 30, "remotion", "space", color="#000000")
    assert agent.read(p["id"])["timeline"]["design"]["background"] == "#000000" and p["revision"] == agent.read(p["id"])["revision"]


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_contained_shots_and_held_zooms_through_transitions_match_across_engines(tmp_path, monkeypatch):
    """A red full-frame shot, then a white strip contained on a black canvas and held at 2x, entering by dissolve and
    then by push: HyperFrames had left the red outgoing shot in the side bands for the whole dissolve, and dropped the
    held zoom to 1x for the length of the push."""
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    red, strip = tmp_path / "red.png", tmp_path / "strip.png"
    Image.new("RGB", (320, 180), (220, 20, 20)).save(red)
    Image.new("RGB", (400, 100), (250, 250, 250)).save(strip)  # 4:1 contained on 16:9: bands above and below
    got = {}
    for engine in ("remotion", "hyperframes"):
        for name, tr in (("dissolve", {"name": "dissolve", "duration_frames": 10}), ("push", {"name": "push_left", "duration_frames": 10})):
            pid = agent.create_silent("landscape", 40, engine, "bands", color="#000000")["id"]
            ids = [agent.import_media(pid, str(x), x.stem, "evidence", True, agent.read(pid)["revision"])["asset"]["id"] for x in (red, strip)]
            p = agent.read(pid)
            base = {**p["timeline"]["shots"][0], "text": "", "motion": "hold", "effects": []}
            zoom = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.0, "focus_x": .5, "focus_y": .5, "cut": True}}]
            p["timeline"]["shots"] = [{**base, "id": "a", "start_frame": 0, "end_frame": 20, "asset_id": ids[0], "fit": "cover"},
                                      {**base, "id": "b", "start_frame": 20, "end_frame": 40, "asset_id": ids[1], "fit": "contain", "effects": zoom, "transition": tr}]
            agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": p["timeline"]}])
            scaffold(pid, engine, False)
            got[engine, name] = np.asarray(Image.open(snapshot(pid, engine, [25])["frames"][0]["path"]).convert("RGB").resize((160, 90)), np.float32)
    for name in ("dissolve", "push"):
        r, h = got["remotion", name], got["hyperframes", name]
        assert np.abs(r - h).mean() < 6, (name, float(np.abs(r - h).mean()))
    band = got["hyperframes", "dissolve"][0:3, 70:90]  # above the 2x strip (its band is the top 5 %): red fading to black, not red held
    assert band[..., 0].mean() < 160


def test_dropped_frames_play_from_a_constant_rate_proxy(tmp_path, monkeypatch):
    """Every fifth frame missing (a variable-rate transfer): at each gap the engines had chosen different neighbours.
    Both now play a constant-rate proxy where the gap holds the frame before it."""
    from editvideo.code_engine import engine_media, frame_gaps
    from editvideo.media import probe
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    src = tmp_path / "vfr.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=3", "-vf", r"select='mod(n\,5)'",
                    "-fps_mode", "passthrough", "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p", str(src)], check=True)
    assert frame_gaps(src) >= 10
    out, why = engine_media(src, {"kind": "video", "sha256": "c" * 64})
    v = next(s for s in probe(str(out))["streams"] if s["codec_type"] == "video")
    assert why.endswith("dropped frames") and frame_gaps(out) == 0 and int(v["nb_frames"]) == pytest.approx(90, abs=2)


def test_rotated_pictures_import_as_they_are_shown(tmp_path, monkeypatch):
    """An EXIF-rotated photo (stored 400x200, shown 200x400) and a phone clip with a 90 degree display matrix import as
    shown, whatever their size; detection reads the same shape."""
    from PIL import Image
    from editvideo import agent
    from editvideo.media import display_size, working_copy
    from editvideo.semantic import frames
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    photo = tmp_path / "phone.jpg"
    img = Image.new("RGB", (400, 200), (200, 30, 30))
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 CW to show
    img.save(photo, exif=exif)
    assert display_size(photo) == (200, 400)
    out, origin = working_copy(photo)
    assert origin and Image.open(out).size == (200, 400)
    plain, clip = tmp_path / "plain.mp4", tmp_path / "portrait.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(plain)], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-display_rotation:v:0", "90", "-i", str(plain), "-c", "copy", str(clip)], check=True)  # a display matrix, as phones write
    assert display_size(clip) == (180, 320)
    assert frames(clip, 1.0, 90)[1][0].shape[:2] == (160, 90)  # decoded upright, not squashed
    pid = agent.create_silent("vertical", 30, "remotion", "phone")["id"]
    a = agent.import_media(pid, str(clip), "clip", "evidence", True, agent.read(pid)["revision"])["asset"]
    assert (a["width"], a["height"]) == (180, 320) and a["name"] == "portrait.mp4"


def test_frame_subject_reports_when_the_region_cannot_hold_it():
    from editvideo.semantic import frame_subject
    f = frame_subject([.05, .3, .25, .6], 1920, 1080, 1920, 1080, region=(.5, 0, 1, 1))  # same aspect: nothing can move it right
    assert f["inside_region"] is False
    f = frame_subject([.4, 0, .6, .2], 1920, 1080, 1080, 1920, region=(0, .4, 1, 1))  # at the top of its frame, wanted low
    assert f["inside_region"] and f["subject"][1] >= .4 - 1e-3
    with pytest.raises(ValueError):
        frame_subject([.7, .7, .3, .3], 1920, 1080, 1080, 1920)


def test_detection_keeps_whole_tracks_merges_flicker_and_names_clips_apart(tmp_path, monkeypatch):
    """Without the models: 100 sampled frames with a hit on every frame but every fourth (flicker). The track covers the
    whole clip (it had stopped at 60 samples), spans merge across one missed sample, and two clips with one file name
    stay two clips in find_subjects."""
    import json
    from PIL import Image
    from editvideo import mcp_server as m, semantic
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    n = 100
    monkeypatch.setattr(semantic, "frames", lambda path, fps=1.0, width=960, start=0.0, end=None:
                        ([round((i + .5) / fps, 2) for i in range(n)], [np.zeros((54, 96, 3), np.uint8)] * n))
    monkeypatch.setattr(semantic, "_detect_frames", lambda imgs, queries, thr: [[] if i % 4 == 3 else [{"q": 0, "score": .5, "box": [.2, .2, .4, .6]}]
                                                                                  for i in range(len(imgs))])
    paths = []
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        paths.append(tmp_path / d / "GX010001.mp4")
        paths[-1].write_bytes(d.encode())
    r = semantic.detect([str(paths[0])], ["car"], fps=1.0)
    car = next(iter(r["clips"].values()))["car"]
    assert len(car["track"]) == 75 and car["spans"] == [[0.0, 99.0]]
    out = json.loads(m.editvideo_find_subjects([str(p) for p in paths], ["car"])[0].text)
    assert len(out["clips"]) == 2 and len(set(out["paths"].values())) == 2


@pytest.mark.skipif(not ENGINES_READY, reason="Local rendering dependencies not installed")
def test_every_transition_and_attached_layer_stacks_alike_in_both_engines(tmp_path, monkeypatch):
    """Every transition at its midpoint, from a red frame into a contained white strip held at 2x, with a layer attached
    to each outgoing shot and global layers at z 0 and z 10 under an attached one at z 30: HyperFrames had played wipes
    and iris as hard cuts (a -webkit-clip-path reset erased the clip), kept attached layers above the incoming shot and
    hid a z 0 layer under the shot."""
    from PIL import Image
    from editvideo import agent
    from editvideo.code_engine import scaffold
    from editvideo.models import Transition
    from editvideo.snapshot import snapshot
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    red, strip = tmp_path / "red.png", tmp_path / "strip.png"
    Image.new("RGB", (320, 180), (220, 20, 20)).save(red)
    Image.new("RGB", (400, 100), (250, 250, 250)).save(strip)
    names = list(Transition.model_fields["name"].annotation.__args__)
    L = 12  # frames per shot; each transition lasts 8 and is read at its 4th frame
    got = {}
    for engine in ("remotion", "hyperframes"):
        pid = agent.create_silent("landscape", L * (2 * len(names)), engine, "transitions", color="#000000")["id"]
        ids = [agent.import_media(pid, str(x), x.stem, "evidence", True, agent.read(pid)["revision"])["asset"]["id"] for x in (red, strip)]
        p = agent.read(pid)
        base = {**p["timeline"]["shots"][0], "text": "", "motion": "hold", "effects": []}
        zoom = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": 1.0, "focus_x": .5, "focus_y": .5, "cut": True}}]
        shots, layers = [], []
        for i, name in enumerate(names):
            a = 2 * i * L
            shots += [{**base, "id": f"r{i}", "start_frame": a, "end_frame": a + L, "asset_id": ids[0], "fit": "cover"},
                      {**base, "id": f"s{i}", "start_frame": a + L, "end_frame": a + 2 * L, "asset_id": ids[1], "fit": "contain", "effects": zoom,
                       "transition": {"name": name, "duration_frames": 8}}]
            layers.append({"id": f"tag{i}", "kind": "shape", "attach_shot": f"r{i}", "start_frame": a, "end_frame": a + L, "x": .05, "y": .05, "width": .2,
                           "height": .2, "z": 30, "color": "#2040ff", "data": {"shape": "rectangle"}})
        layers += [{"id": "g0", "kind": "shape", "start_frame": 0, "end_frame": L * 2 * len(names), "x": .8, "y": .8, "width": .15, "height": .15, "z": 0,
                    "color": "#20c040", "data": {"shape": "rectangle"}},
                   {"id": "g10", "kind": "shape", "start_frame": 0, "end_frame": L * 2 * len(names), "x": .15, "y": .15, "width": .2, "height": .2, "z": 10,
                    "color": "#ffd000", "data": {"shape": "rectangle"}}]
        p["timeline"]["shots"], p["timeline"]["layers"] = shots, layers
        agent.patch(pid, p["revision"], [{"op": "replace_timeline", "timeline": p["timeline"]}])
        scaffold(pid, engine, False)
        frames = [2 * i * L + L + 4 for i in range(len(names))] + [5]  # each midpoint, and a frame inside the first red shot
        for k in range(0, len(frames), 8):  # snapshots take up to 8 frames a call
            for f, shot in zip(frames[k:k + 8], snapshot(pid, engine, frames[k:k + 8])["frames"]):
                got[engine, f] = np.asarray(Image.open(shot["path"]).convert("RGB").resize((160, 90)), np.float32)
    bad = {name: round(float(np.abs(got["remotion", f] - got["hyperframes", f]).mean()), 1)
           for name, f in zip(names, [2 * i * L + L + 4 for i in range(len(names))])
           if np.abs(got["remotion", f] - got["hyperframes", f]).mean() > 8}
    assert not bad, bad
    fd = 2 * names.index("dissolve") * L + L + 4  # the outgoing shot's attached tag fades under the incoming shot
    assert np.abs(got["remotion", fd][6:18, 10:36] - got["hyperframes", fd][6:18, 10:36]).mean() < 20
    still = got["hyperframes", 5]
    assert still[78, 140, 1] > 150 and still[78, 140, 0] < 100  # the z 0 global layer (green) shows over the shot
    assert still[18, 32, 2] < 100 and still[18, 32, 0] > 200  # where the z 30 attached tag and the z 10 global overlap, the global wins (yellow)


def test_fast_forward_at_a_fractional_step_moves_evenly(tmp_path, monkeypatch):
    """A bar moving 4 px a source frame, played at 2.5x: picked frames jumped 8, 12, 8, 12 px; shutter-averaged frames
    move within a pixel of 10 px each."""
    from editvideo.code_engine import rate_proxy
    from editvideo.media import sha256
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    src = tmp_path / "bar.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x64:r=30:d=6", "-vf",
                    r"geq=lum='if(between(X\,4*N\,4*N+7)*between(Y\,16\,47)\,235\,16)':cb=128:cr=128", "-c:v", "libx264", "-qp", "0",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    out = rate_proxy(src, {"sha256": sha256(src)}, 0.0, 2.5, 24)
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    rows = np.clip(np.frombuffer(raw, np.uint8).reshape(-1, 64, 320)[:, 32].astype(float) - 30, 0, None)  # the bar only
    cx = [(r * np.arange(320)).sum() / r.sum() for r in rows]
    assert np.abs(np.diff(cx) - 10).max() < 1.0


def test_contained_subject_cut_by_its_frame_fades_into_the_canvas():
    from editvideo.semantic import frame_subject
    f = frame_subject([0, 0, .99, .7], 3840, 2160, 1080, 1920, region=(0, .31, 1, .71))
    assert f["cut_edges"] == ["left", "top", "right"]
    fe = next(e for e in f["effects"] if e["name"] == "edge_feather")
    assert fe["params"]["box"][1] > .3 and fe["params"]["box"][3] < .75  # the picture's own band, before any zoom
    from editvideo.models import Shot
    Shot.model_validate({"id": "s", "beat_id": "b", "start_frame": 0, "end_frame": 30, "effects": f["effects"]})  # a timeline accepts it
    assert not any(e["name"] == "edge_feather" for e in frame_subject([.3, .2, .6, .8], 3840, 2160, 1080, 1920)["effects"])
