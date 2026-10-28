"""Round 7: narration fallback chain, effect guide/atlas v2, direction checks."""
import json
import wave
import pytest
from editvideo import store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    return tmp_path


def test_narration_falls_back_to_a_timed_silent_placeholder(workspace, monkeypatch):
    from editvideo import voices
    async def offline(text, config, target, cancelled):
        raise OSError("network down")
    monkeypatch.setattr(voices, "sapi_voices", lambda: [("Microsoft Zira Desktop", "en-US")])  # no Vietnamese OS voice
    monkeypatch.setattr(store, "SHARED_MODELS", workspace / "no-models")  # nor Piper in the installation
    text = "Một điểm sáng đi qua màn hình. Ta nhìn thấy nó chuyển động."
    path, words, backend, attempts = voices.speak(text, {"voice": "vi-VN-HoaiMyNeural"}, workspace / "n.mp3", lambda: False, offline)
    assert backend == "silent" and words == []
    assert [a["backend"] for a in attempts] == ["edge", "piper", "sapi"]
    with wave.open(str(path)) as w:
        secs = w.getnframes() / w.getframerate()
    assert 4.5 < secs < 7  # 14 words at ~2.6 words/s plus two pauses
    with pytest.raises(ValueError, match="No narration backend"):
        voices.speak(text, {"voice": "vi-VN-HoaiMyNeural", "voice_backend": "edge"}, workspace / "m.mp3", lambda: False, offline)


def test_voice_capabilities_report_language_and_backends():
    from editvideo import voices
    c = voices.capabilities({"voice": "vi-VN-NamMinhNeural"})
    assert c["language"] == "vi-VN" and c["silent_placeholder"] is True and "piper" in c


def test_effect_atlas_covers_every_effect_and_combo_in_both_engines():
    from editvideo.effects import CATALOG, validate_effect, catalog
    from editvideo.effect_guide import COMBOS, FAMILY, NOTES
    atlas = json.loads((store.ROOT / "assets/previews/effect-atlas.json").read_text(encoding="utf-8"))
    assert atlas["version"] == 2
    for group, ids in (("effects", CATALOG), ("combos", COMBOS)):
        for k in ids:
            strips = atlas[group][k]["strip"]
            assert set(strips) == {"remotion", "hyperframes"}, k
            assert all((store.ROOT / p).is_file() for p in strips.values()), k
    for k, v in NOTES.items():
        assert k in CATALOG and set(v["pairs"]) <= set(CATALOG), k
    assert all(set(v["pairs"]) <= set(CATALOG) for v in FAMILY.values())
    for c in COMBOS.values():
        for e in c["stack"]:
            validate_effect(e["name"], e.get("params", {}))
    card = catalog("light_wrap")["effects"][0]
    assert card["pairs_with"] and card["avoid"] and set(card["preview"]["strip"]) == {"remotion", "hyperframes"}
    assert catalog("archival_film")["combo"]["preview"]["strip"]
    assert [c["id"] for c in catalog()["combos"]] == list(COMBOS)


def test_hyperframes_declares_every_video_clip_with_its_source_offset():
    from editvideo.code_engine import hyperframes_videos, hyperframes_html
    shots = [{"id": "a", "start_frame": 0, "end_frame": 60, "asset_id": "v", "source_start": 4.0},
             {"id": "b", "start_frame": 60, "end_frame": 120, "asset_id": "v", "source_start": 41.5, "transition": {"mode": "live", "duration_frames": 12}},
             {"id": "c", "start_frame": 120, "end_frame": 150, "asset_id": "img", "source_start": 0}]
    payload = {"timeline": {"width": 1920, "height": 1080, "total_frames": 150, "shots": shots,
                            "layers": [{"id": "pip", "start_frame": 30, "end_frame": 90, "asset_id": "v", "source_start": 9, "z": 40}]},
               "media": {"v": {"kind": "video", "src": "v.mp4"}, "img": {"kind": "image", "src": "i.png"}}}
    tags = hyperframes_videos(payload)
    assert tags.count("<video") == 3  # same file, three clips, each declared (HyperFrames otherwise sees none)
    assert 'id="video-s-a"' in tags and 'data-media-start="4.0"' in tags and 'data-media-start="41.5"' in tags
    assert 'id="video-s-a" class="scene" data-start="0.0" data-duration="2.4"' in tags  # extended by the next shot's live transition
    assert 'id="video-l-pip" class="layer"' in tags and 'data-track-index="40"' in tags
    assert tags in hyperframes_html(payload)


def test_tracking_entrance_is_capped_so_a_title_never_reflows():
    from editvideo.code_engine import fit_tracking
    title = {"id": "t", "kind": "text", "text": "432.210 KM", "start_frame": 0, "end_frame": 60, "x": .06, "y": .4, "width": .76, "height": .2,
             "font_id": "oswald", "font_weight": 700, "font_size": 150,
             "effects": [{"name": "tracking", "start_frame": 0, "end_frame": 14, "params": {"amount": .04, "from_em": .3}}]}
    t = {"width": 1080, "height": 1920, "design": {}, "layers": [title]}
    out = fit_tracking(t)
    p = out["layers"][0]["effects"][0]["params"]
    assert 0 < p["_fit_em"] < .3  # .3em on 10 glyphs at 150px would push the line past its 820px box
    assert "_fit_em" not in title["effects"][0]["params"]  # authored timeline untouched
    from editvideo.design_library import layout_text
    w = layout_text("oswald", "432.210 KM", 150, 4000, 700)["line_widths"][0]
    assert w + p["_fit_px"] * len("432.210 KM") <= .76 * 1080


def test_reading_load_counts_vietnamese_syllables_not_words():
    from editvideo.review import is_vietnamese
    assert is_vietnamese("tên lửa mạnh nhất NASA") and not is_vietnamese("the most powerful rocket")


def test_adapt_keeps_a_card_together_as_one_unit():
    from editvideo.aspect import _groups, _place
    panel = {"id": "p", "kind": "shape", "start_frame": 0, "end_frame": 90, "x": .6, "y": .1, "width": .3, "height": .15}
    cap = {"id": "c", "kind": "text", "start_frame": 0, "end_frame": 90, "x": .62, "y": .11, "width": .26, "height": .04}
    val = {"id": "v", "kind": "text", "start_frame": 4, "end_frame": 90, "x": .62, "y": .17, "width": .26, "height": .06}
    far = {"id": "f", "kind": "text", "start_frame": 0, "end_frame": 90, "x": .05, "y": .8, "width": .3, "height": .05}
    later = {"id": "l", "kind": "text", "start_frame": 200, "end_frame": 260, "x": .62, "y": .27, "width": .26, "height": .04}
    groups = _groups([panel, cap, val, far, later], 1920, 1080)
    assert groups == [[0, 1, 2]]
    from editvideo.aspect import SAFE
    x, y, w, h, _ = _place([.6, .1, .3, .15], 1920, 1080, 1080, 1920, SAFE["vertical"], 1.0)
    assert abs(h * 1920 - .15 * 1080) < 1  # the card keeps its pixel height (type size) instead of stretching with the frame


def test_beat_map_flags_late_text_static_sentences_and_even_rhythm(workspace, monkeypatch):
    from editvideo import beatmap
    words = [{"text": w, "start": i * .5, "end": i * .5 + .4} for i, w in enumerate(
        "Tàu Orion bay xa Trái Đất 432.210 km. Đó là kỷ lục mới của tàu chở người trong không gian sâu thẳm.".split())]
    pid = "00000000-0000-4000-8000-000000000001"
    plan = store.folder(pid) / "plan"
    plan.mkdir(parents=True)
    store.write_json(plan / "words.json", {"words": words})
    shots = [{"id": f"s{i}", "start_frame": i * 120, "end_frame": i * 120 + 120, "role": "illustration"} for i in range(5)]
    late = {"id": "km", "kind": "text", "text": "432.210 km", "start_frame": 150, "end_frame": 260, "x": .1, "y": .1, "width": .5, "height": .1}
    t = {"shots": shots, "layers": [late], "cues": []}
    monkeypatch.setattr(beatmap.agent, "read", lambda pid: {"timeline": t, "config": {}})
    r = beatmap.beat_map(pid)
    codes = {f["code"] for f in r["findings"]}
    assert r["sentences"] == 2 and r["timing"] == "timed words"
    assert "late_visual" in codes  # "432.210 km" said at ~3 s, shown at 5 s
    assert "uniform_rhythm" in codes  # five 4 s shots
    assert next(f for f in r["findings"] if f["code"] == "late_visual")["layer"] == "km"


def _fx(tmp_path, code):
    import subprocess
    src = tmp_path / "effects.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    return json.loads(subprocess.check_output(["node", "-e", "const fx=require(process.argv[1]);" + code, str(src)], text=True, encoding="utf-8"))


def test_slide_spring_is_invisible_at_its_offset_start_and_tracking_respects_the_cap(tmp_path):
    item = {"id": "t", "kind": "text", "start_frame": 0, "end_frame": 60, "effects": [
        {"name": "slide_spring", "start_frame": 4, "end_frame": 18, "params": {"amount": 260}},
        {"name": "tracking", "start_frame": 4, "end_frame": 18, "params": {"amount": .04, "from_em": .3, "_fit_em": .05}}]}
    r = _fx(tmp_path, f"const it={json.dumps(item)};console.log(JSON.stringify([0,4,6,30].map(f=>fx.styleAt(it,f))))")
    assert float(r[0]["opacity"]) == 0 and float(r[1]["opacity"]) == 0  # the hold before the start and the offset start
    assert float(r[3]["opacity"]) == 1
    assert r[1]["letterSpacing"] == "0.0500em"  # .3em would reflow the line; capped to what the box holds


def test_punch_keeps_the_push_speed_and_steps_from_what_is_on_screen():
    from editvideo.ads import _truncate, _on_screen_scale
    push = {"name": "focus_zoom", "start_frame": 0, "end_frame": 50, "easing": "linear", "params": {"amount": .43}}
    cut = _truncate(push, 25)
    assert cut["end_frame"] == 25 and abs(cut["params"]["amount"] - (1.43 ** .5 - 1)) < 1e-3  # same speed, half the travel
    assert abs(_on_screen_scale([push], 25) - 1.43 ** .5) < 1e-6
    assert _on_screen_scale([{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .2, "cut": True}}], 10) == 1.2


def test_hyperframes_video_block_follows_the_timeline_after_export(tmp_path):
    from editvideo.code_engine import hyperframes_html, sync_video_declarations
    media = {"v": {"kind": "video", "src": "v.mp4"}}
    t = {"width": 640, "height": 360, "total_frames": 90, "shots": [{"id": "a", "start_frame": 0, "end_frame": 90, "asset_id": "v", "source_start": 0}], "layers": []}
    (tmp_path / "index.html").write_text(hyperframes_html({"timeline": t, "media": media}), encoding="utf-8")
    t2 = {**t, "shots": [{"id": "a", "start_frame": 0, "end_frame": 40, "asset_id": "v", "source_start": 0},
                         {"id": "a-p1", "start_frame": 40, "end_frame": 90, "asset_id": "v", "source_start": 1.3333}]}  # a punch split after export
    assert sync_video_declarations(tmp_path, {"timeline": t2, "media": media})
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert page.count("<video") == 2 and 'id="video-s-a-p1"' in page and f'data-media-start="{40 / 30}"' in page  # on the 30 fps grid, as Remotion's trimBefore
    old = page.replace("<!--editvideo:videos-->", "").replace("<!--/editvideo:videos-->", "")  # an export from before the markers
    (tmp_path / "index.html").write_text(old, encoding="utf-8")
    assert sync_video_declarations(tmp_path, {"timeline": t, "media": media})
    assert (tmp_path / "index.html").read_text(encoding="utf-8").count("<video") == 1


def test_selects_report_dead_air_and_black_inside_a_range(tmp_path):
    import subprocess
    import numpy as np
    from editvideo import agent
    from editvideo.media import FFMPEG
    clip = tmp_path / "reel.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=160x90:r=30:d=2", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=30:d=1",
                    "-f", "lavfi", "-i", "testsrc=s=160x90:r=30:d=2", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]", "-map", "[v]",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    sr = 48000
    tone = .2 * np.sin(np.arange(sr * 5) * 2 * np.pi * 220 / sr).astype(np.float32)
    tone[int(1.8 * sr):int(3.4 * sr)] = 0  # 1.6 s of dead air around the black slug
    gaps = agent.segment_gaps(clip, [(0.0, 5.0)], tone, sr, [{"src": [0.0, 5.0], "frames": [0, 150]}])
    kinds = {g["kind"]: g for g in gaps}
    assert set(kinds) == {"silence", "black"}
    assert 1.7 <= kinds["silence"]["source"][0] <= 1.9 and 1.9 <= kinds["black"]["source"][0] <= 2.1
    assert agent.segment_gaps(clip, [(0.0, 1.5)], tone, sr, [{"src": [0.0, 1.5], "frames": [0, 45]}]) == []


def test_upscale_and_cut_scale_helpers():
    from editvideo.review import upscale_factor, edge_scale, max_magnification
    sh = {"fit": "cover", "effects": [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .12, "cut": True}},
                                      {"name": "focus_zoom", "start_frame": 0, "end_frame": 60, "params": {"amount": .1}}]}
    assert abs(max_magnification(sh) - 1.232) < 1e-3
    assert abs(upscale_factor(sh, {"kind": "video", "width": 1280, "height": 720}, 1080, 1920) - 1920 / 720 * 1.232) < 1e-3
    assert upscale_factor(sh, {"kind": "video"}, 1080, 1920) is None
    assert abs(edge_scale(sh, False) - 1.12) < 1e-9 and abs(edge_scale(sh, True) - 1.232) < 1e-9


def test_hud_card_takes_the_film_palette():
    from editvideo.design_library import tokens
    from editvideo.explainer import hud_card, HudCard
    design = tokens("monochrome_focus", "amber", "oswald", "inter")
    t = {"width": 1920, "height": 1080, "design": design, "shots": [], "layers": []}
    r = hud_card(t, HudCard(recipe="hud_card", id="h", start_frame=0, end_frame=90, caption="LỰC ĐẨY", value_to=39))
    panel, cap, val = (op["layer"] for op in r["ops"])
    assert panel["color"] == design["color_roles"]["surface"] and val["color"] == design["color_roles"]["accent"]
    assert cap["height"] < val["y"] - panel["y"]  # a one-line caption reserves one line, not two


def test_hyperframes_layers_do_not_clip_marks_above_the_line_box():
    from editvideo.code_engine import hyperframes_html
    page = hyperframes_html({"timeline": {"width": 640, "height": 360, "total_frames": 30, "shots": [], "layers": []}, "media": {}})
    # Remotion layers overflow their box; a clipped HyperFrames .layer cut the marks above Â/Ô ("LẦN CUỐI" read "LÂN CUÔI").
    assert ".layer{position:absolute}" in page and ".layer,.frozen{position:absolute;overflow:hidden}" not in page


def test_portrait_hyperframes_pages_carry_a_capture_margin_that_render_crops():
    from editvideo.code_engine import hyperframes_html, capture_margin, CAPTURE_MARGIN
    tall = {"width": 1080, "height": 1920, "total_frames": 30, "shots": [], "layers": []}
    wide = {**tall, "width": 1920, "height": 1080}
    page = hyperframes_html({"timeline": tall, "media": {}})
    # HyperFrames on Windows painted only W-8 px of a portrait capture: the page is wider, the picture stays at the left.
    assert capture_margin(tall) == CAPTURE_MARGIN and capture_margin(wide) == 0
    assert f'data-width="{1080 + CAPTURE_MARGIN}"' in page and '<div id="root"><!--editvideo:videos-->' in page
    assert 'data-width="1920"' in hyperframes_html({"timeline": wide, "media": {}}) and 'id="capture"' not in hyperframes_html({"timeline": wide, "media": {}})


def test_dead_air_with_room_tone_is_found_relative_to_the_voice(tmp_path):
    import numpy as np
    from editvideo import agent
    sr = 48000
    rng = np.random.default_rng(1)
    voice = (.3 * np.sin(np.arange(sr * 4) * 2 * np.pi * 180 / sr)).astype(np.float32)
    voice[int(1.5 * sr):int(2.8 * sr)] = (.004 * rng.standard_normal(int(1.3 * sr))).astype(np.float32)  # room tone ≈ -48 dBFS
    clip = tmp_path / "missing.mp4"  # black detection is skipped for an unreadable file; the audio test stands alone
    gaps = agent.segment_gaps(clip, [(0.0, 4.0)], voice, sr, [{"src": [0.0, 4.0], "frames": [0, 120]}])
    assert [g["kind"] for g in gaps] == ["silence"] and 1.4 <= gaps[0]["source"][0] <= 1.6


# ---------------------------------------------------------------- round 8
def test_motion_spans_see_svg_draws_and_entrances_and_reading_holds_are_not_dead_frames():
    from editvideo.review import motion_spans, longest_still
    shot = {"id": "s2", "start_frame": 643, "end_frame": 972, "motion": "hold"}
    plot = {"id": "plot", "kind": "svg", "start_frame": 643, "end_frame": 972, "effects": [],
            "data": {"elements": [{"type": "polyline", "draw": [0, 18]}, {"type": "text", "text": "2000 2010 2020", "appear": [20, 150]}]}}
    title = {"id": "title2", "kind": "text", "text": "Số người đã lên Mặt Trăng", "start_frame": 643, "end_frame": 972,
             "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}, {"name": "shadow", "start_frame": 0, "end_frame": 1}]}
    spans = motion_spans(shot, [plot, title])
    assert (643, 661) in spans and (663, 793) in spans and (643, 655) in spans  # draw, appear, fade; the shadow is a look
    at, frames = longest_still(shot, spans)
    assert at == 793 and frames == 972 - 793
    assert longest_still(shot, []) == (643, 329)


def test_static_hold_levels_follow_what_is_on_screen(workspace):
    from editvideo import agent
    from editvideo.review import audit_timeline
    p = agent.create({"title": "t", "script": "Một câu.", "profile": "landscape"})
    t = {"width": 1920, "height": 1080, "total_frames": 600, "fps": 30, "design": {}, "cues": [], "beats": [],
         "shots": [{"id": "a", "start_frame": 0, "end_frame": 300, "motion": "hold", "role": "illustration"},
                   {"id": "b", "start_frame": 300, "end_frame": 600, "motion": "hold", "role": "illustration"}],
         "layers": [{"id": "card", "kind": "text", "text": "Ba mươi chín triệu niu-tơn lực đẩy", "start_frame": 300, "end_frame": 600,
                     "x": .1, "y": .1, "width": .6, "height": .1, "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 10}]}]}
    f = {(x["code"], x["where"].get("shot")): x["level"] for x in audit_timeline(p["id"], t)["findings"] if x["code"] in ("static_hold", "reading_hold")}
    assert f[("static_hold", "a")] == "likely_problem"  # nothing moves, nothing to read
    assert f[("static_hold", "b")] == "check"  # a 9.7 s still on 7 words (needs ~3.3 s): held longer than reading needs


def test_pin_maps_source_points_through_fit_focus_and_zoom():
    from editvideo.pin import canvas_point, _thin
    shot = {"fit": "cover", "focus_x": .4, "focus_y": .5, "effects": []}
    asset = {"width": 1920, "height": 1080}
    x, y = canvas_point(shot, asset, 1080, 1080, .5, .5, 0)  # 16:9 into a square: cover crops the sides around focus .4
    assert abs(x - 624) < 1e-6 and abs(y - 540) < 1e-6
    shot["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .5, "focus_x": .36, "focus_y": .22, "cut": True}}]
    x, y = canvas_point(shot, asset, 1080, 1080, .5, .5, 10)
    assert abs(x - (.36 * 1080 + (624 - .36 * 1080) * 1.5)) < 1e-6 and abs(y - (.22 * 1080 + (540 - .22 * 1080) * 1.5)) < 1e-6
    pts = list(range(250))
    thin = _thin(pts, 100)
    assert len(thin) == 100 and thin[0] == 0 and thin[-1] == 249


def test_offline_voice_words_are_timed_from_the_audio(monkeypatch):
    import sys, types
    from editvideo import voices
    W = types.SimpleNamespace
    heard = [W(word=" Nước", start=0.0, end=.3), W(word=" nóng", start=.3, end=.6), W(word=" xuống", start=1.0, end=1.3), W(word=" phễu.", start=1.3, end=1.7)]
    class Model:
        def __init__(self, *a, **k): pass
        def transcribe(self, *a, **k): return [W(words=heard)], None
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    w = voices.align_words("x.wav", "Nước nóng nhỏ xuống phễu.", "vi-VN", 1.8)
    assert [x["text"] for x in w] == ["Nước", "nóng", "nhỏ", "xuống", "phễu."]
    assert w[2]["start"] == .6 and w[2]["end"] == 1.0  # "nhỏ" was not heard: spread between its matched neighbours
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(w, w[1:]))


def test_piper_narration_pace_and_sentence_pauses(monkeypatch, tmp_path):
    from editvideo import voices
    seen = {}
    monkeypatch.setattr(voices, "piper_model", lambda lang: tmp_path / "vi_VN-x.onnx")
    monkeypatch.setattr(voices, "piper_available", lambda: True)
    monkeypatch.setattr(voices.subprocess, "run", lambda cmd, **k: seen.setdefault("cmd", cmd))
    voices.piper_speak("Một câu.", {"voice": "vi-VN-NamMinhNeural", "voice_rate": 20}, tmp_path / "n.mp3")
    cmd = seen["cmd"]
    assert cmd[cmd.index("--length-scale") + 1] == f"{voices.PIPER_LENGTH / 1.2:.3f}" and cmd[cmd.index("--sentence-silence") + 1] == "0.35"


def test_fetch_source_checks_kind_before_downloading():
    from editvideo import resources
    with pytest.raises(ValueError, match="kind must be one of"):
        resources.fetch_source("https://example.invalid/x.webm", "wikimedia", "t", "CC BY 4.0", "c", "https://example.invalid/", "bogus")


def test_a_speed_change_on_continuous_footage_is_not_a_jump_cut(workspace):
    from editvideo import agent
    from editvideo.review import audit_timeline
    p = agent.create({"title": "t", "script": "Một câu.", "profile": "vertical"})
    base = {"asset_id": None, "fit": "cover", "motion": "hold", "role": "evidence", "focus_x": .5, "focus_y": .5}
    t = {"width": 1080, "height": 1920, "total_frames": 240, "fps": 30, "design": {}, "cues": [], "beats": [], "layers": [],
         "shots": [{**base, "id": "a", "start_frame": 0, "end_frame": 120, "source_start": 42.0, "playback_rate": 1, "asset_id": "v"},
                   {**base, "id": "b", "start_frame": 120, "end_frame": 240, "source_start": 46.00004, "playback_rate": 2, "asset_id": "v"}]}
    assert not [x for x in audit_timeline(p["id"], t)["findings"] if x["code"] == "jump_cut"]  # 0.00004 s is rounding, not a skip
    t["shots"][1]["source_start"] = 47.0
    assert [x for x in audit_timeline(p["id"], t)["findings"] if x["code"] == "jump_cut"]  # a 1 s skip on one camera is a jump


def test_static_looks_list_matches_the_runtime():
    import re
    from editvideo.review import STATIC_EFFECTS
    js = (store.ROOT / "engines/effects.js").read_text(encoding="utf-8")
    for name in ("text_outline", "rgb_split", "shadow", "highlight_glow", "motion_blur"):
        body = re.search(r"case '" + name + r"':(.*?)(?:break;|return)", js, re.S).group(1)
        assert not re.search(r"(?<![\w.])(p|u|f|local|phase)(?![\w])", body), name  # its output does not depend on time
        assert name in STATIC_EFFECTS


def test_dead_frames_dressed_as_motion_are_still_dead(workspace):
    from editvideo import agent
    from editvideo.review import audit_timeline, reading_words
    p = agent.create({"title": "t", "script": "Một câu.", "profile": "landscape"})
    shot = {"id": "s", "start_frame": 0, "end_frame": 300, "motion": "push", "role": "illustration",  # no picture: push moves nothing
            "effects": [{"name": "focus_zoom", "start_frame": 0, "end_frame": 300, "params": {"amount": .2, "cut": True}}]}  # held zoom
    looks = {"id": "credit", "kind": "text", "text": "Ảnh: NASA", "typography_role": "source", "start_frame": 0, "end_frame": 300,
             "x": .1, "y": .9, "width": .5, "height": .04, "keyframes": {"opacity": [{"frame": 0, "value": 1}, {"frame": 299, "value": 1}]},
             "effects": [{"name": "text_outline", "start_frame": 0, "end_frame": 300}, {"name": "rgb_split", "start_frame": 0, "end_frame": 300}]}
    t = {"width": 1920, "height": 1080, "total_frames": 300, "fps": 30, "design": {}, "cues": [], "beats": [], "shots": [shot], "layers": [looks]}
    f = [x for x in audit_timeline(p["id"], t)["findings"] if x["code"] in ("static_hold", "reading_hold")]
    assert [(x["code"], x["level"]) for x in f] == [("static_hold", "likely_problem")]
    assert reading_words("2000 / 2010 · Mặt Trăng") == 3  # two numbers count half, symbols nothing


def test_silent_project_has_the_exact_length(workspace):
    from editvideo import agent
    r = agent.create_silent("square", 47, "remotion", "t")
    t = agent.read(r["id"])["timeline"]
    assert t["total_frames"] == 47 and t["width"] == t["height"] == 1080 and t["timing_method"] == "source_video_silent"


def test_speed_audits_find_jolts_judder_and_shaky_fast_forwards(workspace):
    from editvideo import agent
    from editvideo.review import audit_timeline
    p = agent.create({"title": "t", "script": "Một câu.", "profile": "vertical"})
    clip = workspace / "take.mp4"
    import subprocess
    from editvideo.media import FFMPEG
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=6", "-pix_fmt", "yuv420p", str(clip)], check=True)
    aid = agent.import_media(p["id"], str(clip), "take", "evidence")["id"]
    base = {"asset_id": aid, "fit": "cover", "motion": "hold", "role": "evidence", "focus_x": .5, "focus_y": .5}
    t = {"width": 1080, "height": 1920, "total_frames": 120, "fps": 30, "design": {}, "cues": [], "beats": [], "layers": [],
         "shots": [{**base, "id": "a", "start_frame": 0, "end_frame": 30, "source_start": 0.0, "playback_rate": 1},
                   {**base, "id": "b", "start_frame": 30, "end_frame": 60, "source_start": 1.0, "playback_rate": 1.5},
                   {**base, "id": "c", "start_frame": 60, "end_frame": 120, "source_start": 2.5, "playback_rate": 4}]}
    codes = {(x["code"], x["where"].get("shot") or tuple(x["where"].get("shots") or [])) for x in audit_timeline(p["id"], t)["findings"]}
    assert ("fractional_speed", "b") in codes and ("fast_forward", "c") in codes
    assert ("speed_step", ("b", "c")) in codes and ("speed_step", ("a", "b")) in codes  # x1.5 and x2.67 jumps on one continuous take


def test_pin_reports_unmodelled_shot_motion_and_early_track_end(workspace, monkeypatch):
    import subprocess
    from editvideo import agent
    from editvideo.media import FFMPEG
    import editvideo.pin as pin
    p = agent.create({"title": "t", "script": "Một câu.", "profile": "landscape"})
    clip = workspace / "take.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=6", "-pix_fmt", "yuv420p", str(clip)], check=True)
    aid = agent.import_media(p["id"], str(clip), "take", "evidence")["id"]
    tl = {"width": 1920, "height": 1080, "total_frames": 120,
          "shots": [{"id": "s", "start_frame": 0, "end_frame": 120, "asset_id": aid, "source_start": 0, "fit": "cover",
                     "effects": [{"name": "pan_x", "start_frame": 0, "end_frame": 119, "params": {"amount": 40}}]}],
          "layers": [{"id": "lab", "kind": "text", "text": "Nhãn", "start_frame": 0, "end_frame": 120, "x": .4, "y": .4, "width": .2, "height": .06}]}
    monkeypatch.setattr(pin.agent, "read", lambda pid: {"revision": 7, "timeline": tl})
    track = {"tracks": [{"timestamp": k / 10, "region": [.4 + k * .001, .4, .5 + k * .001, .5]} for k in range(20)], "lost_at": None}  # 2 s of a 4 s layer
    r = pin.pin_to_track(p["id"], 7, track, "s", ["lab"], dry_run=True)
    assert r["unmodelled_shot_motion"] == ["pan_x"] and r["pinned"][0]["holds_from"] < 100


def test_locked_stabilization_on_a_leash_removes_shake_and_never_jumps():
    import numpy as np
    from editvideo.footage_pro import leashed_path
    n = 600
    t = np.arange(n)
    drift = np.linspace(0, 200, n)  # the handheld camera wanders 200 px over the take...
    shake = 6 * np.sin(t * 1.7) + 4 * np.sin(t * 2.9)  # ... and shakes
    traj = np.stack([drift + shake, shake * .5, np.zeros(n), np.zeros(n)], axis=1)
    leash = np.array([30.0, 30.0, .01, .01])
    path = leashed_path(traj, np.zeros_like(traj), leash, 60)
    assert np.all(np.abs(path - traj) <= leash + 1e-9)  # the crop always hides the borders
    steps = np.abs(np.diff(path[:, 0]))
    assert steps.max() < 1.5 and np.abs(np.diff(traj[:, 0])).max() > 8  # no frame-to-frame jump left of the shake
    # the old behaviour (whole correction scaled down to fit) kept a share of the shake in every frame
    scaled = traj + (np.zeros_like(traj) - traj) * (30 / 200)
    assert np.abs(np.diff(scaled[:, 0])).max() > 5 * steps.max()


def test_hyperframes_retry_runs_in_the_low_memory_profile():
    from editvideo.code_engine import hyperframes_low_memory
    args = ["node", "hf.mjs", "render", "src", "--output", "visual.mp4", "--fps", "30", "--workers", "6", "--quality", "delivery"]
    a, env = hyperframes_low_memory(args, {"NODE_OPTIONS": "--max-old-space-size=4096"})
    assert "--workers" not in a and "6" not in a and a[-1] == "--low-memory-mode" and a[a.index("--quality") + 1] == "delivery"
    assert env["HF_SEGMENTED_CAPTURE"] == "true" and env["NODE_OPTIONS"].endswith("4096")


def test_unclear_synthetic_narration_becomes_a_finding(workspace):
    from editvideo import voices
    pid = "00000000-0000-4000-8000-0000000000aa"
    plan = store.folder(pid) / "plan"
    plan.mkdir(parents=True)
    for share, want in ((.05, None), (.12, "check"), (.22, "likely_problem")):
        store.write_json(plan / "voice-backend.json", {"backend": "piper", "asr_check": {"available": True, "not_heard_as_written": share,
                                                                                          "check_by_ear": [{"said": "vạch", "heard": "phải", "at_s": 4.0}]}})
        f = voices.narration_finding(pid)
        assert (f[0] if f else None) == want and (not f or f[1] == "narration_unclear")
    store.write_json(plan / "voice-backend.json", {"backend": "piper", "asr_check": {"available": False, "reason": "RuntimeError"}})
    assert voices.narration_finding(pid)[1] == "narration_unchecked"


def test_stabilizer_centre_conventions_undo_a_dolly_exactly():
    import math
    import numpy as np
    from editvideo.footage_pro import to_center, from_center
    c = (320.0, 180.0)
    # the camera moved closer (x1.06), turned 1 degree and slid: an origin-based similarity as RANSAC returns it
    s, a = 1.06, math.radians(1)
    M = np.array([[s * math.cos(a), -s * math.sin(a), 25.0], [s * math.sin(a), s * math.cos(a), -12.0]])
    params = to_center(M, c)
    assert np.allclose(from_center(params, c)[:2], M)  # same transform, centre-based
    # lock warp at output scale f: output = inverse(real) maps every moved point back where it was
    f = 3.0
    A = from_center(params, (c[0] * f, c[1] * f), f)
    W = np.linalg.inv(A)
    p = np.array([100.0 * f, 50.0 * f, 1.0])
    assert np.allclose(W @ (A @ p), p)
    # the old shortcut (negated params, warp about the centre) misses by pixels once the camera dollies
    old = from_center(tuple(-x for x in params), (c[0] * f, c[1] * f), f)
    assert np.abs((old @ (A @ p))[:2] - p[:2]).max() > 3


def test_fused_lock_path_is_drift_free_without_registration_noise():
    import numpy as np
    from editvideo.footage_pro import fuse_paths
    rng = np.random.default_rng(3)
    n = 1800
    t = np.arange(n)
    true = np.stack([40 * np.sin(t / 300) + 3 * np.sin(t * 1.3), 20 * np.cos(t / 250) + 2 * np.sin(t * 2.1),
                     .01 * np.sin(t / 400), .02 * np.sin(t / 500)], axis=1)
    # frame-to-frame chain: precise steps, but it wanders off over a minute
    chained = true + np.cumsum(rng.normal(0, [.05, .05, 1e-4, 1e-4], (n, 4)), axis=0) + np.linspace(0, 1, n)[:, None] * [8, -6, .01, .02]
    # registration to the first frame: never wanders, but every estimate is noisy (and sometimes wrong or missing)
    registered = true + rng.normal(0, [.5, .5, .005, .005], (n, 4))
    registered[500] += [40, 0, 0, 0]
    registered[900:905] = np.nan
    fused = fuse_paths(chained, registered, 30)
    err = lambda p: np.abs(p - true)
    step = lambda p: np.abs(np.diff(p - true, axis=0))
    assert err(fused)[:, :2].max() < 1.5 and err(chained)[:, :2].max() > 6  # no drift
    assert step(fused)[:, :2].max() < .4 and np.nanmax(step(registered)[:, :2]) > 1  # no per-frame jitter
    assert step(fused)[:, 3].max() < 1e-3 and np.nanmax(step(registered)[:, 3]) > 5e-3  # no breathing (scale noise)


def test_corner_shift_measures_the_subject_box_motion():
    import numpy as np
    import cv2
    from editvideo.footage_pro import corner_shift
    rng = np.random.default_rng(1)
    a = cv2.GaussianBlur((rng.random((360, 640)) * 255).astype(np.uint8), (0, 0), 2)
    M = cv2.getRotationMatrix2D((320, 180), .3, 1.01)
    M[:, 2] += (1.5, -.8)
    b = cv2.warpAffine(a, M, (640, 360), borderMode=cv2.BORDER_REFLECT)
    C = np.array([[200, 100], [440, 100], [200, 300], [440, 300]], float)
    pts = cv2.goodFeaturesToTrack(a, 300, .01, 8, blockSize=7)
    want = np.hypot(*(C @ M[:, :2].T + M[:, 2] - C).T).max()
    assert want > 2.5 and abs(corner_shift(a, pts, b, C) - want) < .3 and corner_shift(a, pts, a, C) < .05


def test_fast_forward_reads_the_measured_motion_at_its_effective_speed(workspace, monkeypatch):
    import subprocess
    from editvideo import agent, review
    from editvideo.media import FFMPEG
    p = agent.create({"title": "t", "script": "Một câu.", "profile": "vertical"})
    ids = {}
    for name, size in (("tall", "1080x1920"), ("wide", "1920x1080")):
        clip = workspace / f"{name}.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s={size}:r=30:d=4", "-pix_fmt", "yuv420p", str(clip)], check=True)
        ids[name] = agent.import_media(p["id"], str(clip), name, "evidence")["id"]

    def flagged(report, clip="tall"):  # a clip retimed x8 from a stabilized take, played at 3x: x24
        t = {"width": 1080, "height": 1920, "total_frames": 30, "fps": 30, "design": {}, "cues": [], "beats": [], "layers": [],
             "shots": [{"asset_id": ids[clip], "fit": "cover", "motion": "hold", "role": "evidence", "focus_x": .5, "focus_y": .5,
                        "id": "c", "start_frame": 0, "end_frame": 30, "source_start": 0.0, "playback_rate": 3}]}
        monkeypatch.setattr(review, "footage_speed", lambda a: (8.0, report))
        return [x["evidence"] for x in review.audit_timeline(p["id"], t)["findings"] if x["code"] == "fast_forward"]
    calm = {"residual_coverage": 1.0, "residual_px_over_frames": {"1": .3, "16": 1.7, "32": 2.1}}
    assert not flagged(calm)  # 1.9 px per output frame at x24, shown 1:1
    ev = flagged({**calm, "residual_px_over_frames": {"1": .3, "16": 1.7, "32": 2.7}})  # 2.2 px: the nearer window (16) alone passed it
    assert ev and ev[0]["effective_speed"] == 24 and ev[0]["on_screen_px_per_frame"] == 2.2
    assert flagged(calm, "wide")[0]["on_screen_px_per_frame"] == 3.4  # a 9:16 cover of a 16:9 clip enlarges it 1.78x
    # nothing trackable in the region: unmeasured, never "0 px"
    assert flagged({"residual_coverage": 0.0, "residual_px_over_frames": {}, "residual_step_px": None})[0]["on_screen_px_per_frame"] is None


def test_stabilize_locks_a_shaken_clip_and_reports_a_flat_region_as_unmeasured(workspace, monkeypatch):
    import subprocess
    import numpy as np
    import cv2
    from editvideo import media_tasks
    from editvideo.footage_pro import stabilize
    from editvideo.media import FFMPEG
    rng = np.random.default_rng(5)
    scene = cv2.GaussianBlur((rng.random((300, 440, 3)) * 255).astype(np.uint8), (0, 0), 1.5)
    scene[:, :150] = 128  # a flat block: nothing to track
    clip = workspace / "shaken.mp4"
    enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "320x180", "-r", "30", "-i", "-",
                            "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(clip)], stdin=subprocess.PIPE)
    for i in range(60):  # handheld: +-12 px shake around a fixed view
        dx, dy = int(60 + 12 * np.sin(i * 1.9)), int(60 + 8 * np.sin(i * 2.7 + 1))
        enc.stdin.write(np.ascontiguousarray(scene[dy:dy + 180, dx:dx + 320]).tobytes())
    enc.stdin.close()
    enc.wait()
    out = workspace / "task"
    out.mkdir()
    monkeypatch.setattr(media_tasks, "folder", lambda tid: out)
    monkeypatch.setattr(media_tasks, "check", lambda tid: None)
    monkeypatch.setattr(media_tasks, "update", lambda tid, **kw: None)
    r = stabilize("t", {"path": str(clip), "mode": "lock", "max_zoom": 1.4, "region": [.55, .1, .95, .9]})["report"]
    assert r["residual_coverage"] > .9 and r["residual_step_px"]["p95"] < 1.0 and r["residual_px_over_frames"]["8"] < 1.5
    r = stabilize("t", {"path": str(clip), "mode": "lock", "max_zoom": 1.4, "region": [.0, .1, .2, .9]})["report"]
    assert r["residual_coverage"] < .5 and r["residual_step_px"] is None and r["residual_px_over_frames"] == {}
