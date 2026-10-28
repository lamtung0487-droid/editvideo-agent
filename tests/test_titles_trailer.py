"""Title design recipes (measured title-card numbers) and trailer structure planning/audit."""
import importlib.util
from pathlib import Path
import pytest
from editvideo import titles, trailer
from editvideo.design_library import tokens
from editvideo.models import Layer


def timeline():
    return {"width": 1920, "height": 1080, "total_frames": 900, "fps": 30, "design": tokens("minimal_explainer"), "shots": [], "layers": []}


def layers(r):
    return {op["layer"]["id"]: op["layer"] for op in r["ops"] if op["op"] == "upsert_layer"}


def test_title_presets_follow_measured_sizes_and_timing():
    t = timeline()
    imp = titles.title_card(t, titles.TitleCard(recipe="title_card", id="t", text="Hỏa Tinh", start_frame=0, end_frame=110, hit_frame=40))
    L = layers(imp)
    assert L["t"]["start_frame"] == 40 and L["t-plate"]["start_frame"] == 4  # hard cut on the hit after 36 frames of black
    assert L["t"]["text"] == "HỎA TINH" and not [e for e in L["t"]["effects"] if e["name"] == "fade_in"]
    m = imp["measurements"]
    assert m["width_share_W"] <= .95 and .25 <= m["cap_share_H"] <= .46  # frame-filling, shrunk to the width limit
    for k in L.values():
        Layer.model_validate(k)
    wide = titles.title_card(t, titles.TitleCard(recipe="title_card", id="w", preset="minimal_wide", text="Những ngày cuối", start_frame=0, end_frame=200))
    w = layers(wide)["w"]
    tr = next(e for e in w["effects"] if e["name"] == "tracking")
    assert tr["params"]["from_em"] == .6 and tr["params"]["amount"] == .45 and tr["params"]["center"]
    fade = next(e for e in w["effects"] if e["name"] == "fade_in")
    assert fade["easing"] == "linear" and fade["end_frame"] == 54
    two = layers(titles.title_card(t, titles.TitleCard(recipe="title_card", id="d", preset="two_tone", text="Đế chế đỏ", start_frame=0, end_frame=90)))["d"]
    assert two["text"].startswith("==ĐẾ==")
    integ = titles.title_card(t, titles.TitleCard(recipe="title_card", id="i", preset="integrated", text="Jezero", start_frame=0, end_frame=95, placement="right_third"))
    li = layers(integ)
    assert "i-plate" not in li and li["i"]["keyframes"]["x"][0]["value"] > 0 and li["i"]["x"] > .5
    assert any(e["name"] == "text_animate" and e["params"]["mode"] == "out" for e in li["i"]["effects"])  # scatter exit
    short = titles.title_card(t, titles.TitleCard(recipe="title_card", id="s", preset="minimal_wide", text="Một hai ba bốn năm sáu", start_frame=0, end_frame=100))
    assert any("Readable hold" in n for n in short["notes"])
    with pytest.raises(ValueError):
        titles.title_card(t, titles.TitleCard(recipe="title_card", id="x", text="A", start_frame=0, end_frame=60, hit_frame=58))


def test_title_cap_band_is_centred_on_target():
    t = timeline()
    for preset in ("impact", "two_tone", "minimal_wide"):
        r = titles.title_card(t, titles.TitleCard(recipe="title_card", id="c", preset=preset, text="HTH", start_frame=0, end_frame=120, y=.5))
        L = layers(r)["c"]
        pr = titles._probe(L["font_id"], "HTH", L["font_weight"])
        px, lh = L["font_size"], L["line_height"]
        k = px / 100
        cap_mid = L["y"] * 1080 + (lh * px - (pr["ascent"] + pr["descent"]) * k) / 2 + (pr["cap_top"] + pr["cap_bottom"]) / 2 * k
        assert abs(cap_mid - 540) < 3, preset


def test_lockups_keep_hierarchy_and_heavier_surname():
    t = timeline()
    p = titles.type_lockup(t, titles.Lockup(recipe="type_lockup", id="lk", top="Một bộ phim", main="Perseverance", sub="Hành trình", footer=["Mùa thu 2026", "nhỏ"],
                                            start_frame=0, end_frame=120))
    L = layers(p)
    assert L["lk-main"]["font_size"] / L["lk-top"]["font_size"] > 4.5 and L["lk-top"]["y"] < L["lk-main"]["y"] < L["lk-sub"]["y"]
    assert L["lk-footer0"]["y"] >= .85 and L["lk-footer1"]["y"] > L["lk-footer0"]["y"] + .015
    c = titles.type_lockup(t, titles.Lockup(recipe="type_lockup", id="cr", mode="credit", role="Đạo diễn", name="Nguyễn Văn An", start_frame=0, end_frame=90))
    C = layers(c)
    assert C["cr-name"]["text"].endswith("**AN**") and C["cr-name"]["data"]["strong_weight"] == 800
    assert .35 <= C["cr-role"]["font_size"] / C["cr-name"]["font_size"] <= .5 and not c["notes"]
    for k in [*L.values(), *C.values()]:
        Layer.model_validate(k)


def test_word_cards_land_before_hits_and_flash():
    t = timeline()
    r = titles.word_cards(t, titles.WordCards(recipe="word_cards", id="wc", words=["một", "hai"], hit_frames=[100, 112], flash_frames=2))
    L = layers(r)
    assert L["wc-0"]["start_frame"] == 99 and L["wc-0"]["end_frame"] == 111  # 1 frame early, clipped at the next card
    assert L["wc-0-plate"]["data"]["corner_radius"] == 0
    op = L["wc-0"]["keyframes"]["opacity"]
    assert [k["value"] for k in op] == [1, 1, 0, 0, 1]
    with pytest.raises(ValueError):
        titles.WordCards(recipe="word_cards", id="x", words=["a", "b"], hit_frames=[10])
    sf = titles.sound_first(t, titles.SoundFirst(recipe="sound_first", id="sf", black_from=100, hit_frame=150))
    assert layers(sf)["sf"]["end_frame"] == 150 + 51 + 1


def _song(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("synth_song", Path(__file__).with_name("synth_song.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = tmp_path_factory.mktemp("tsong")
    return str(d / "song.wav"), mod.make(str(d / "song.wav"))


def test_trailer_plan_structure_and_music_anchors(tmp_path_factory):
    p = trailer.plan(90, bumper=True)
    names = [s["section"] for s in p["sections"]]
    assert names == ["bumper", "cold_open", "logos", "act1", "act2", "act3", "title", "button"]
    assert p["sections"][-1]["end"] == 90 and all(a["end"] == b["start"] for a, b in zip(p["sections"], p["sections"][1:]))
    assert 8 <= p["sections"][1]["end"] - p["sections"][1]["start"] <= 15
    path, truth = _song(tmp_path_factory)
    pm = trailer.plan(80, path, (90, 180))
    by = {s["section"]: s for s in pm["sections"]}
    assert abs(by["act2"]["start"] - truth["hit"]) < .05  # act 2 enters on the drop
    assert by["act2"]["dip_before"] is not None  # the silence before the drop is found
    assert by["act3"]["climax_music"]["seconds"] >= 6
    with pytest.raises(ValueError):
        trailer.plan(10)


def test_trailer_audit_flags_pacing_and_missing_button(monkeypatch):
    from editvideo import agent
    shots, f = [], 0
    for L in [36] * 10 + [30] * 10 + [12] * 10 + [60]:  # act1 1.2 s shots, act2 1.0 s, act3 bursts of 0.4 s, then a title shot
        shots.append({"id": f"s{len(shots)}", "start_frame": f, "end_frame": f + L})
        f += L
    t = {"shots": shots, "layers": [{"id": "title", "start_frame": f - 60, "end_frame": f}], "audio_clips": []}
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
    secs = [{"section": "act1", "start_frame": 0, "end_frame": 360}, {"section": "act2", "start_frame": 360, "end_frame": 660},
            {"section": "act3", "start_frame": 660, "end_frame": 780}]
    r = trailer.audit("p", secs, title_layer="title")
    codes = {x["code"] for x in r["findings"]}
    assert "no_button" in codes and "act_without_dialogue" in codes
    assert "no_climax_burst" not in codes  # ten 0.4 s shots form a burst
    pace = {row["section"]: row["median_shot_s"] for row in r["pacing"]}
    assert pace["act1"] == 1.2 and pace["act3"] == .4
