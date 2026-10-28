"""Round 13, the fourth cut of the Vietnam film (docs/PRO_WORKFLOWS.md §33): the owner found the cutting too fast, the text
gone before it was read, and the maps unable to show where things happened. Located footage on relief maps, chapter
cards that give the question its own time, and pacing checks scaled to a documentary."""
import sys
from pathlib import Path
import numpy as np
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import agent, store, review, cinematic, resources
from editvideo.models import Shot

TY = {r: {"font_id": "notoserif", "size": 30, "weight": 600} for r in ("label", "headline", "caption")}
T = {"width": 1920, "height": 1080, "total_frames": 900, "shots": [], "layers": [], "design": {"typography": TY}}
CITIES = [{"name": "Điện Biên Phủ", "lat": 21.39, "lon": 103.02}, {"name": "Hà Nội", "lat": 21.03, "lon": 105.85}]


def _map(steps, **kw):
    return cinematic.HistoryMap.model_validate({"recipe": "history_map", "id": "m", "start_frame": 0, "end_frame": 300, "country": "Vietnam",
                                                "cities": CITIES, "steps": steps, **kw})


def test_a_map_flies_to_a_place_and_opens_its_footage_from_the_pin():
    q = _map([{"kind": "camera", "city": "Điện Biên Phủ", "at": 20, "frames": 60, "zoom": 2.0, "focus": [.3, .5]},
              {"kind": "footage", "city": "Điện Biên Phủ", "asset_id": "v1", "source_start": 1.0, "at": 100, "frames": 120, "caption": "ĐIỆN BIÊN PHỦ · 1954"},
              {"kind": "footage", "city": "Hà Nội", "asset_id": "v2", "at": 225, "frames": 75, "expand": True}], box=[0, 0, 1, 1], fill_aspect=16 / 9)
    r = cinematic.history_map(T, q)
    by = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    cam = by["m"]["keyframes"]
    at = {k["frame"]: k["value"] for k in cam["scale"]}
    assert by["m"]["anchor"] == [0, 0] and at[80] == 2.0 and cam["scale"][0]["frame"] == 0  # the move lands on its zoom
    assert at[20] > 1.0 and cam["scale"][-1]["value"] > 2.0  # ... and the map creeps on before and after it
    assert at[100] == at[220] and at[225] == at[299]  # but holds still while located footage is open
    assert all(k["value"] <= 0 for k in cam["x"] + cam["y"])  # the scaled map keeps covering its box: never pulled inward
    f0, f1 = by["m-f0"], by["m-f1"]
    assert f0["kind"] == "video" and f0["start_frame"] == 108 and f0["keyframes"]["scale"][0]["value"] < .1  # grows from the pin
    assert {"m-f0-line", "m-f0-dim", "m-f0-cap", "m-f0-edge"} <= set(by)
    ho = r["measurements"]["footage"][1]["handoff"]  # the expanding frame hands its footage on to the next shot
    assert ho["asset_id"] == "v2" and ho["source_start"] == pytest.approx((300 - 225 - 8) / 30, abs=.01)
    assert f1["keyframes"]["scale"][-1]["value"] == pytest.approx(1 / .42, abs=.01)
    from editvideo.models import Layer
    for o in r["ops"]:  # every layer valid, every effect and key inside its own span (what the timeline enforces)
        L = Layer.model_validate(o["layer"])
        n = L.end_frame - L.start_frame
        assert all(e.end_frame <= n for e in L.effects) and all(k.frame < n for ks in L.keyframes.values() for k in ks), L.id
    with pytest.raises(Exception, match="ends the map"):
        _map([{"kind": "footage", "city": "Hà Nội", "asset_id": "v2", "at": 100, "frames": 100, "expand": True}])
    with pytest.raises(Exception, match="two footage"):
        _map([{"kind": "footage", "city": "Hà Nội", "asset_id": f"v{k}", "at": 10 + k, "frames": 100} for k in range(3)])


def test_a_footage_frame_does_not_cover_the_words_on_the_map():
    """Round 13, the fifth cut: Huế's footage opened level with its pin and cut its own label ("Huế · 26 ngày giao tranh",
    centred below the pin) in half. The frame now moves above or below the pin, or to the other side, to keep the words
    clear."""
    q = _map([{"kind": "camera", "city": "Hà Nội", "at": 0, "frames": 30, "zoom": 2.0, "focus": [.42, .5]},
              {"kind": "marker", "city": "Hà Nội", "at": 35, "text": "Hà Nội · mười hai ngày đêm trên bầu trời", "side": "below"},
              {"kind": "footage", "city": "Hà Nội", "asset_id": "v1", "at": 60, "frames": 120, "caption": "HÀ NỘI · 1972"}], box=[0, 0, 1, 1],
             fill_aspect=16 / 9)
    r = cinematic.history_map(T, q)
    by = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    lab = next(e for e in by["m"]["data"]["elements"] if e.get("text", "").startswith("Hà Nội ·"))
    pin = next(e for e in by["m"]["data"]["elements"] if e.get("type") == "circle")
    W, H = 1920, 1080
    k = 2.0 * by["m"]["width"] * W / by["m"]["data"]["view_box"][0]  # view-box units to screen px at zoom 2
    c = r["measurements"]["footage"][0]
    x0, y0, fw, fh = c["box"]
    half = .4 * lab["font_size"] * k * len(lab["text"]) / 2 / W  # the middle 80 % of the label's width (glyph widths vary)
    base = c["pin"][1] + (lab["y"] - pin["cy"]) * k / H  # the label's baseline on screen
    lx0, lx1, ly0, ly1 = c["pin"][0] - half, c["pin"][0] + half, base - .7 * lab["font_size"] * k / H, base
    overlap = max(0, min(x0 + fw, lx1) - max(x0, lx0)) * max(0, min(y0 + fh, ly1) - max(y0, ly0))
    assert overlap == 0, (c["box"], (lx0, ly0, lx1, ly1))
    assert not (x0 <= c["pin"][0] <= x0 + fw and y0 <= c["pin"][1] <= y0 + fh)  # nor the pin it opens from


def test_a_relief_crop_lines_up_with_the_map_projection(tmp_path):
    """An equirectangular image cropped to map_extent puts a point where the map projects it (the projection is linear in
    longitude and latitude, scaled by cos of the middle latitude)."""
    from PIL import Image
    src = np.zeros((900, 900, 3), np.uint8)  # 90 x 90 degrees at 10 px a degree, 90-180E, 0-90N
    x, y = round((105.85 - 90) * 10), round((90 - 21.03) * 10)
    src[y - 2:y + 3, x - 2:x + 3] = 255  # Hà Nội
    Image.fromarray(src).save(tmp_path / "eq.png")
    q = _map([{"kind": "marker", "city": "Hà Nội", "at": 1}], fill_aspect=16 / 9)
    e = cinematic.map_extent(q)
    out = resources.relief_crop(e["extent"], tmp_path / "crop.png", tmp_path / "eq.png", [90, 0, 180, 90], width=1000)
    im = np.asarray(Image.open(out).convert("L"))
    VW, VH = e["view_box"]
    assert im.shape[1] / im.shape[0] == pytest.approx(VW / VH, rel=.01)
    ys, xs = np.nonzero(im > 128)
    proj = resources.MapProjection(cinematic.map_view(q), 1000, pad=.04)
    px, py = proj(21.03, 105.85)
    assert abs(xs.mean() / im.shape[1] - px / VW) < .01 and abs(ys.mean() / im.shape[0] - py / VH) < .01


def test_a_chapter_card_holds_its_question_by_reading_speed():
    vi = cinematic.question_frames("Một đội quân nông dân đã thắng như thế nào, và vì sao chiến thắng chưa mang lại thống nhất?")
    en = cinematic.question_frames("How did a peasant army win, and why did the victory not unite the country at last?")
    assert cinematic.QUESTION_AT + 6 * 30 + 10 <= vi < en  # Vietnamese syllables read faster than English words
    assert cinematic.question_frames("") == 75


def _audit(monkeypatch, shots, layers=(), direction=True):
    from editvideo.directions import DIRECTIONS
    d = DIRECTIONS["cinematic_documentary"] if direction else None
    t = {"width": 1920, "height": 1080, "total_frames": shots[-1]["end_frame"], "shots": shots, "layers": list(layers), "cues": [], "audio_clips": [],
         "design": {"typography": TY, **({"direction": {k: d[k] for k in ("id", "name", "energy", "motion", "pacing", "transitions", "titles", "captions",
                                                                           "finish", "composition", "negative")}} if d else {})}}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t, "revision": 1})
    monkeypatch.setattr(store, "assets", lambda pid: [{"id": "v", "kind": "video", "path": "v.mp4", "width": 1920, "height": 1080, "duration": 600}])
    return {f["code"]: f for f in review.audit_timeline("p", t)["findings"]}


def _shots(lengths, hit_at=()):
    out, f = [], 0
    for k, s in enumerate(lengths):
        sh = Shot(id=f"s{k}", beat_id="b", start_frame=f, end_frame=f + round(s * 30), asset_id="v", source_start=float(k)).model_dump()
        if k in hit_at:
            sh["effects"] = [{"name": "white_flash", "start_frame": 0, "end_frame": 2, "params": {"amount": 1}}]
        out.append(sh)
        f += round(s * 30)
    return out


def test_an_even_four_second_rhythm_reads_as_relentless_in_a_documentary(monkeypatch):
    f = _audit(monkeypatch, _shots([3] * 20))
    assert f["short_shots"]["evidence"]["share"] == 1.0 and "pacing_vs_direction" in f
    # a burst of short shots around a hit (<= 45 s) between long holds is a set piece, not the rhythm
    f = _audit(monkeypatch, _shots([7] * 10 + [2.4] * 8 + [7] * 10, hit_at=(12,)))
    assert "short_shots" not in f
    # a 14 s hold is a documentary's breath, not a long shot to cut
    assert "long_shot" not in _audit(monkeypatch, _shots([14, 6, 7]))
    assert "long_shot" in _audit(monkeypatch, _shots([14, 6, 7]), direction=False)


def test_a_label_must_stay_long_enough_to_be_read_twice(monkeypatch):
    lab = lambda i, text, secs: {"id": i, "kind": "text", "text": text, "start_frame": 30, "end_frame": 30 + round(secs * 30), "x": .05, "y": .1,
                                 "width": .8, "height": .05, "z": 900, "typography_role": "label", "color": "#ffffff", "effects": []}
    f = _audit(monkeypatch, _shots([8, 8]), [lab("a", "QUÂN NHẬT VÀO ĐÔNG DƯƠNG · 1940", 2.5)])
    assert f["text_too_brief"]["evidence"]["needed_s"] == pytest.approx(2 * 31 / 15 + .5, abs=.1)
    assert "text_too_brief" not in _audit(monkeypatch, _shots([8, 8]), [lab("a", "QUÂN NHẬT VÀO ĐÔNG DƯƠNG · 1940", 5.0)])


def test_a_label_held_across_a_cut_is_flagged(monkeypatch):
    lab = {"id": "lab", "kind": "text", "text": "B-52 RƠI · HÀ NỘI", "start_frame": 10, "end_frame": 200, "x": .05, "y": .1, "width": .8, "height": .05,
           "z": 900, "typography_role": "label", "color": "#ffffff", "effects": []}
    f = _audit(monkeypatch, _shots([4, 4]), [lab])
    assert f["label_crosses_cut"]["evidence"]["cuts"] == [120]
    assert "label_crosses_cut" not in _audit(monkeypatch, _shots([4, 4]), [{**lab, "data": {"same_subject": True}}])


def test_voices_without_a_pause_for_long_are_flagged(monkeypatch):
    from editvideo import audiofx
    def codes(gap_s):
        clips, f = [], 0
        for k in range(8):  # eight 8 s lines
            clips.append({"id": f"vo-{k}", "asset_id": "a", "start_frame": f, "end_frame": f + 240, "role": "dialogue", "volume": 1.0})
            f += 240 + round(gap_s * 30)
        t = {"total_frames": f + 60, "timing_method": "silent", "shots": [{"id": "s", "start_frame": 0, "end_frame": f + 60}], "audio_clips": clips}
        monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t})
        monkeypatch.setattr(store, "assets", lambda pid: [])
        return {x["code"]: x for x in audiofx.audit("p")["findings"]}
    assert codes(1.0)["voice_run"]["evidence"]["longest_s"] > 60  # 1 s pauses: one run
    assert "voice_run" not in codes(2.5)  # a breath of 2.5 s after every line


def test_repeated_frames_are_measured_on_the_render(tmp_path):
    """The first shot repeats every frame twice (a 15 fps picture in a 30 fps file); the second moves every frame."""
    import subprocess
    from editvideo.media import FFMPEG
    out = tmp_path / "render.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=4", "-f", "lavfi", "-i", "color=c=white:s=16x40:r=30:d=4",
                    "-filter_complex", "[0][1]overlay=x='if(lt(t,2),20+120*floor(t*15)/15,20+120*(t-2))':y=70", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p",
                    str(out)], check=True)
    sh = lambda i, a, b: Shot(id=i, beat_id="b", start_frame=a, end_frame=b, asset_id="v").model_dump()
    r = {x["shot"]: x["repeated_share"] for x in review.render_repeats(out, {"shots": [sh("rep", 0, 60), sh("ok", 60, 120)]})}
    assert r["rep"] > .4 and r["ok"] < .05


def test_black_is_faded_into_cards_dissolve_in_and_freezes_stay_rare(monkeypatch):
    """The owner's review of the fifth cut: "đang xem thì giật thành đen" (16 hard cuts into black), chapter cards cut
    in abruptly, and 39 frozen frames (74.5 s) read as "lạm dụng hiệu ứng đứng hình"."""
    sh = _shots([8, 1, 6, 8])
    sh[1]["asset_id"] = None  # one second of black after a picture, cut straight in
    sh[2]["asset_id"] = None  # a card (text drawn over it) after the black
    card = {"id": "t", "kind": "text", "text": "PHẦN 2", "start_frame": sh[2]["start_frame"], "end_frame": sh[2]["end_frame"], "x": .1, "y": .4,
            "width": .8, "height": .1, "z": 900, "typography_role": "title", "color": "#ffffff", "effects": []}
    f = _audit(monkeypatch, sh, [card])
    assert f["hard_black_cut"]["where"]["shot"] == "s1"
    sh[1]["transition"] = {"name": "dip_black", "duration_frames": 12, "mode": "freeze", "intensity": 1, "hold_frames": 6, "center": None}
    assert "hard_black_cut" not in _audit(monkeypatch, sh, [card])
    sh2 = _shots([8, 6, 8])
    sh2[1]["asset_id"] = None
    card2 = {**card, "start_frame": sh2[1]["start_frame"], "end_frame": sh2[1]["end_frame"]}
    assert _audit(monkeypatch, sh2, [card2])["card_entry"]["where"]["shot"] == "s1"
    sh2[1]["transition"] = {"name": "dissolve", "duration_frames": 24, "mode": "freeze", "intensity": 1, "hold_frames": 0, "center": None}
    assert "card_entry" not in _audit(monkeypatch, sh2, [card2])
    many = _shots([7, 2] * 6)
    for s in many[1::2]:
        s["freeze"] = True
    f = _audit(monkeypatch, many)
    assert f["freeze_overuse"]["evidence"]["freezes"] == 6
    one = _shots([7, 2, 7, 7])
    one[1]["freeze"] = True
    assert "freeze_overuse" not in _audit(monkeypatch, one)


def test_the_render_shows_hard_cuts_to_black_and_blur_the_edit_added(tmp_path):
    """Measured on the render, not the plan: a picture cut to black is found and told apart from a fade; a blurred
    render of a sharp source is told apart from a soft source."""
    import subprocess
    from editvideo.media import FFMPEG
    src = tmp_path / "src.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=6", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    film = tmp_path / "film.mp4"  # 2 s picture, cut to 1 s black; 2 s picture fading to 1 s black
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-filter_complex",
                    "[0]trim=0:2,setpts=PTS-STARTPTS[a];color=black:s=1920x1080:r=30:d=1[b];[0]trim=2:4,setpts=PTS-STARTPTS,fade=out:st=1.2:d=0.8[c];"
                    "color=black:s=1920x1080:r=30:d=1[d];[a][b][c][d]concat=n=4:v=1:a=0", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(film)],
                   check=True)
    runs = review.black_cuts(film)
    assert [r["hard"] for r in runs][:2] == [True, False], runs
    soft = tmp_path / "soft.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-vf", "gblur=sigma=3", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(soft)], check=True)
    t = {"shots": [{"id": "a", "asset_id": "v", "start_frame": 0, "end_frame": 90, "source_start": 1.0}], "layers": []}
    sharp = review.render_sharpness(src, {**t, "shots": [{**t["shots"][0], "source_start": 0.0}]}, {"v": src})[0]
    blurred = review.render_sharpness(soft, {**t, "shots": [{**t["shots"][0], "source_start": 0.0}]}, {"v": src})[0]
    assert sharp["ratio"] > .9 and blurred["ratio"] < .6


def test_restore_enlarges_soft_archive_sharper_without_shimmer(tmp_path, monkeypatch):
    """Round 13: 45 archive sources were 360-480p and looked soft at 1080p. editvideo.restore enlarges them with
    Real-ESRGAN's compact model (weights in data/models/realesrgan): sharper than a plain enlargement, the size asked
    for, frames kept, and a report of the shimmer per-frame AI adds."""
    import subprocess
    from editvideo import restore
    from editvideo.media import FFMPEG
    if not (restore.MODELS / restore.WEIGHTS["general"]).is_file():
        pytest.skip("Real-ESRGAN weights not installed")
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    src = tmp_path / "small.mp4"  # a sharp test pattern brought down to 320x180
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=1.2", "-vf", "scale=320:180:flags=area",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(src)], check=True)
    r = restore.restore_clip(src, height=720, denoise=.5, mix=.85)
    assert r["to"] == [1280, 720] and r["frames"] == 30
    assert r["report"]["sharpness_gain"] > 1.5 and r["report"]["flicker_ratio"] < 1.3
    assert restore.restore_clip(src, height=720, denoise=.5, mix=.85)["path"] == r["path"]  # cached


def test_source_mix_shares_switches_and_runs():
    """The kind of picture per shot (archive, stage, painterly/AI…) and how a film mixes them: runtime shares, how often a
    cut changes kind, the median run; a near tie between two kinds reads as mixed."""
    from editvideo import source_mix
    cats = {"archive": np.array([1.0, 0, 0]), "stage": np.array([0, 1.0, 0]), "painterly_ai": np.array([0, 0, 1.0])}
    v = np.array([[1, .1, 0], [.9, .1, .1], [.1, 1, 0], [0, .2, 1], [.7, .7, 0]], float)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    labels = source_mix.classify(v, cats)
    assert [c for c, _, _ in labels] == ["archive", "archive", "stage", "painterly_ai", "mixed"]
    m = source_mix.mix([(0, 4), (4, 8), (8, 10), (10, 18), (18, 20)], labels)
    assert m["share"]["archive"] == .4 and m["share"]["painterly_ai"] == .4
    assert m["switch_share"] == .75 and m["median_run_shots"] == 1.0
    assert m["pairs"] == {"archive>stage": 1, "stage>painterly_ai": 1, "painterly_ai>mixed": 1}


def test_frozen_time_is_measured_on_the_picture(tmp_path):
    """Round 13: the fifth cut froze 39 shots. A clip that moves for 2 s and then holds one frame for 2 s is half frozen;
    a black hold is not counted as a freeze."""
    import subprocess
    from editvideo.media import FFMPEG
    clip = tmp_path / "freeze.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-filter_complex",
                    "[0]split[a][b];[b]trim=start_frame=59:end_frame=60,setpts=PTS-STARTPTS,loop=59:1:0[c];[a][c]concat=n=2:v=1:a=0",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(clip)], check=True)
    r = review.frozen_share(clip)
    assert .4 < r["share"] < .6 and r["runs"] == 1


def test_a_generated_shot_needs_a_label_on_screen(monkeypatch):
    """Round 13: mixing AI imagery with archive is allowed (the owner's CCTV reference), but a generated shot without a
    label reads as evidence (the second cut's CGI battle)."""
    sh = _shots([6, 6])
    sh[1]["asset_id"] = "g"
    from editvideo.directions import DIRECTIONS
    t = {"width": 1920, "height": 1080, "total_frames": sh[-1]["end_frame"], "shots": sh, "layers": [], "cues": [], "audio_clips": [],
         "design": {"typography": TY}}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t, "revision": 1})
    monkeypatch.setattr(store, "assets", lambda pid: [{"id": "v", "kind": "video", "path": "v.mp4", "width": 1920, "height": 1080, "duration": 600},
                                                      {"id": "g", "kind": "video", "path": "g.mp4", "width": 1920, "height": 1080, "duration": 8,
                                                       "role": "illustration", "provenance": {"media_task_id": "t1", "operation": "local_ltx"}}])
    codes = {f["code"]: f for f in review.audit_timeline("p", t)["findings"]}
    assert codes["generated_unlabeled"]["where"]["shot"] == "s1"
    t["layers"] = [{"id": "lab", "kind": "text", "text": "MINH HỌA AI", "start_frame": sh[1]["start_frame"], "end_frame": sh[1]["end_frame"],
                    "x": .05, "y": .05, "width": .3, "height": .05, "z": 900, "typography_role": "label", "color": "#ffffff", "effects": []}]
    assert "generated_unlabeled" not in {f["code"] for f in review.audit_timeline("p", t)["findings"]}


def test_models_are_found_when_the_store_lives_elsewhere(tmp_path, monkeypatch):
    """Round 13 keeps projects on G: (EDITVIDEO_DATA); installed models stay in the repository's data/models. SigLIP,
    Whisper and Piper must still be found there."""
    monkeypatch.setattr(store, "DATA", tmp_path / "store")
    assert store.models_root("definitely-not-a-model") == tmp_path / "store" / "models"
    (store.ROOT / "data" / "models").mkdir(parents=True, exist_ok=True)
    probe = next((p.name for p in (store.ROOT / "data" / "models").iterdir()), None)
    if probe is None:
        pytest.skip("no installed models to probe")
    assert store.models_root(probe) == store.ROOT / "data" / "models"
    (tmp_path / "store" / "models" / probe).mkdir(parents=True)
    assert store.models_root(probe) == tmp_path / "store" / "models"  # a store's own copy wins
