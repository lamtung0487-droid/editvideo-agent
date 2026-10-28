"""Round 13, the sixth cut: figures and documents on screen, so the narration can say one number and leave the rest
to the picture (the owner's team review)."""
import pytest


def _timeline():
    roles = ("label", "display", "data", "caption", "source", "quote", "body")
    ty = {r: {"font_id": "notoserif", "size": 40, "weight": 400} for r in roles}
    ty["label"]["tracking"] = .18
    return {"width": 1920, "height": 1080, "total_frames": 1200, "shots": [], "layers": [], "design": {"typography": ty}}


def test_data_story_names_every_source_and_shows_a_contested_number_as_contested():
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    req = {"recipe": "data_story", "id": "ds72", "start_frame": 0, "end_frame": 480, "title": "MÁY BAY MỸ BỊ BẮN RƠI · 12.1972", "compare": True,
           "figures": [{"value": 81, "label": "máy bay, trong đó 34 chiếc B-52", "source": "Phía Việt Nam công bố"},
                       {"value": 26, "label": "máy bay, trong đó 15 chiếc B-52", "source": "Không quân Mỹ"}]}
    r = cinematic.data_story(_timeline(), cinematic.DataStory.model_validate(req))
    layers = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    assert {"ds72-n0", "ds72-n1", "ds72-s0", "ds72-s1", "ds72-tag", "ds72-divider"} <= set(layers)
    assert layers["ds72-n1"]["kind"] == "counter" and layers["ds72-n1"]["data"]["to"] == 26
    assert layers["ds72-s1"]["text"] == "Không quân Mỹ"
    SvgGraphic.model_validate(layers["ds72-divider"]["data"])
    # the second number counts after the first; a figure without a source, or one source "compared" with itself, is refused
    assert layers["ds72-n1"]["effects"][0]["start_frame"] > layers["ds72-n0"]["effects"][0]["start_frame"]
    with pytest.raises(Exception):
        cinematic.DataStory.model_validate({**req, "figures": [{"value": 81, "label": "máy bay"}]})
    same = [{**f, "source": "Không quân Mỹ"} for f in req["figures"]]
    with pytest.raises(Exception, match="different sources"):
        cinematic.DataStory.model_validate({**req, "figures": same})
    with pytest.raises(Exception, match="needs >= "):
        cinematic.DataStory.model_validate({**req, "end_frame": 120})


def test_document_highlight_underlines_the_exact_words_of_the_passage():
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    passage = ("Nước Pháp đã có xứ này, ba mươi triệu dân, gần một trăm năm, và người dân ở đó còn khổ hơn lúc ban đầu. "
               "Người dân Đông Dương xứng đáng được hưởng điều tốt hơn thế.")
    req = {"recipe": "document_highlight", "id": "fdr", "start_frame": 0, "end_frame": 720, "heading": "Roosevelt gửi Hull · 24.1.1944",
           "passage": passage, "highlight": "xứng đáng được hưởng điều tốt hơn thế", "highlight_at": 90, "source": "FRUS 1944, tập III, văn kiện 708"}
    r = cinematic.document_highlight(_timeline(), cinematic.DocumentHighlight.model_validate(req))
    layers = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    lines = [l for k, l in layers.items() if k.startswith("fdr-line")]
    assert " ".join(l["text"] for l in lines).split() == passage.split()  # every word, once, in order
    mark = SvgGraphic.model_validate(layers["fdr-mark"]["data"])
    assert 1 <= len(mark.elements) <= r["measurements"]["lines"] and mark.elements[0].draw[0] == 90
    # the underline sits under the line that holds the words, not above the panel or past its edge
    first = next(l for l in lines if "xứng" in l["text"] or "đáng" in l["text"])
    assert first["y"] * 1080 < mark.elements[0].y1 < (first["y"] + first["height"] * 1.2) * 1080
    assert all(e.x2 <= 1920 * .86 for e in mark.elements)
    with pytest.raises(Exception, match="words of the passage"):
        cinematic.DocumentHighlight.model_validate({**req, "highlight": "điều không có trong văn bản"})
    with pytest.raises(Exception, match="needs >= "):
        cinematic.DocumentHighlight.model_validate({**req, "end_frame": 200})


def test_restore_starts_from_the_true_resolution_of_an_enlarged_clip(tmp_path, monkeypatch):
    """The archive was cut at 1080 from 360-480p re-broadcasts (cropped, logos removed, steadied). from_height brings the
    frames back to their real height before the model enlarges them, so it sees detail rather than an earlier blur."""
    import subprocess
    from editvideo import restore, store
    from editvideo.media import FFMPEG
    if not (restore.MODELS / restore.WEIGHTS["general"]).is_file():
        pytest.skip("Real-ESRGAN weights not installed")
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    src = tmp_path / "enlarged.mp4"  # a 320x180 picture already blown up to 1280x720
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=1.2", "-vf",
                    "scale=320:180:flags=area,scale=1280:720:flags=bicubic", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(src)], check=True)
    r = restore.restore_clip(src, height=720, from_height=180)
    assert r["from"] == [320, 180] and r["to"] == [1280, 720] and r["frames"] == 30
    assert r["report"]["sharpness_gain"] > 1.2
    assert restore.restore_clip(src, height=720)["path"] != r["path"]  # a different restoration, cached apart


def test_english_subtitles_follow_the_vietnamese_sentence_they_translate():
    """The owner chose English subtitles: each English sentence is on screen while its Vietnamese sentence is spoken
    (time shared by syllables), long sentences split at a clause into cues of two lines, and an abbreviation is not
    the end of a sentence."""
    from editvideo import subtitles
    vi = ("Ở Đức Phổ, Quảng Ngãi, bác sĩ Đặng Thùy Trâm, người Hà Nội, mổ cho thương binh dưới bom đạn, và viết nhật ký mỗi đêm. "
          "Một câu thường được trích từ những trang viết ấy:")
    en = ("In Đức Phổ, Quảng Ngãi, Dr. Đặng Thùy Trâm, from Hanoi, operated on the wounded under bombing, and wrote in her diary every night. "
          "One line is often quoted from those pages:")
    assert len(subtitles.sentences(en)) == 2
    cues = subtitles.timed(vi, en, 10.0, 22.0)
    assert cues[0]["start"] == 10.0 and abs(cues[-1]["end"] - 22.0) < .01
    assert all(len(c["text"]) <= 84 for c in cues) and len(cues) >= 3
    first_sentence_end = 10.0 + 12.0 * 23 / 32  # 23 of the 32 Vietnamese syllables
    assert any(abs(c["end"] - first_sentence_end) < .05 for c in cues)
    assert " ".join(c["text"] for c in cues).split() == en.split()
    srt = subtitles.to_srt(cues)
    assert srt.startswith("1\n00:00:10,000 --> ") and "-->" in srt
    ass = subtitles.to_ass([{**cues[0], "raise": True}])
    assert "Dialogue: 0,0:00:10.00," in ass and ",Sub,,0,0,220,," in ass
    assert subtitles.report(cues)["cues"] == len(cues)


def test_unison_lands_two_voices_on_the_same_words():
    """Hồ Chí Minh's declaration and an American reading of 1776 say the same sentence together: the American recording
    is placed so its phrase ends on the Vietnamese one ("bình đẳng" with "equal")."""
    from editvideo import audiofx
    a = [{"word": w, "start": i * .4, "end": i * .4 + .35} for i, w in enumerate("Tất cả mọi người đều sinh ra có quyền bình đẳng".split())]
    b = [{"word": w, "start": 3 + i * .3, "end": 3 + i * .3 + .25} for i, w in enumerate("We hold these truths that all men are created equal,".split())]
    r = audiofx.unison_offset(a, "có quyền bình đẳng", b, "all men are created equal")
    assert r["a"] == [2.8, 4.35] and r["b"][1] == round(3 + 9 * .3 + .25, 3)
    assert abs((r["b"][1] + r["offset"]) - r["a"][1]) < 1e-6  # B's last word ends with A's
    with pytest.raises(ValueError, match="not heard"):
        audiofx.unison_offset(a, "tự do", b, "liberty")


def test_faces_keep_their_heads_in_a_cropped_four_by_three_shot():
    """4:3 archive filled to 16:9 shows 75 % of its height; a centred crop cut foreheads off (the fifth cut). The faces'
    centre goes a third of the way down the visible picture, below the letterbox bar when there is one."""
    from editvideo import semantic
    face = [[.40, .08, .52, .26]]  # a head high in a 4:3 frame
    r = semantic.focus_for_faces(face, 1440, 1080, 1920, 1080)
    assert r["visible"] == .75 and r["kept"] and r["focus_y"] < .2   # the window moves up, not centred
    centred_top = .5 * (1 - .75)
    assert face[0][1] < centred_top  # the old centred crop would have cut this forehead
    bars = semantic.focus_for_faces(face, 1440, 1080, 1920, 1080, band_top=.128, band_bottom=.128)
    assert bars["focus_y"] == 0.0 and not bars["kept"]  # too high to clear a bar at cover: reported, not hidden
    low = semantic.focus_for_faces([[.4, .6, .5, .8]], 1440, 1080, 1920, 1080)
    assert low["kept"] and low["focus_y"] > .5
    assert semantic.focus_for_faces(face, 1920, 1080, 1920, 1080)["focus_y"] == .5  # nothing cropped


def test_black_cuts_refuses_an_unreadable_render(tmp_path):
    """An unreadable file is an error, never 'no hard cuts' (the learnkit session's review of review.black_cuts)."""
    from editvideo import review
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(RuntimeError, match="could not read"):
        review.black_cuts(bad)


def test_data_story_draws_a_unit_grid_and_a_bar_series():
    """A share as a hundred squares (illiteracy in 1945) and a yearly series as bars (US troops in the South), the
    named value in the accent colour, with its source."""
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    g = cinematic.DataStory.model_validate({"recipe": "data_story", "id": "lit", "start_frame": 0, "end_frame": 300, "kind": "grid", "title": "NĂM 1945",
                                            "figures": [{"value": 95, "suffix": " %", "label": "dân số không biết chữ", "source": "Nha Bình dân học vụ"}]})
    r = cinematic.data_story(_timeline(), g)
    els = SvgGraphic.model_validate(next(o["layer"] for o in r["ops"] if o["layer"]["id"] == "lit-grid")["data"]).elements
    assert len(els) == 100 and sum(1 for e in els if e.fill != "#2a2d33") == 95
    b = cinematic.DataStory.model_validate({"recipe": "data_story", "id": "us", "start_frame": 0, "end_frame": 300, "kind": "bars", "title": "QUÂN MỸ Ở MIỀN NAM",
                                            "figures": [{"value": 536100, "label": "1968", "source": "Bộ Quốc phòng Mỹ"}],
                                            "series": [{"label": "1965", "value": 184300}, {"label": "1968", "value": 536100}, {"label": "1972", "value": 24200}]})
    els = SvgGraphic.model_validate(next(o["layer"] for o in cinematic.data_story(_timeline(), b)["ops"] if o["layer"]["id"] == "us-bars")["data"]).elements
    bars = [e for e in els if e.type == "rect"]
    assert len(bars) == 3 and bars[1].height > bars[0].height > bars[2].height and bars[1].fill != bars[0].fill
    with pytest.raises(Exception, match="share of 100"):
        cinematic.DataStory.model_validate({**g.model_dump(), "figures": [{"value": 140, "label": "x", "source": "y y y"}]})


def test_then_and_now_align_when_the_view_matches_and_say_so_when_it_does_not(tmp_path):
    """The present-day frame lands on the archival one through ORB + RANSAC when they share the view; a different view
    is reported (round 13: archive and drone shots of the palace shared 12-16 matches) and the caller dissolves instead.
    The corner-pin track holds the aligned quad, then eases to the full frame."""
    import subprocess
    from editvideo import thennow
    from editvideo.media import FFMPEG
    old = tmp_path / "old.mp4"
    new = tmp_path / "new.mp4"
    other = tmp_path / "other.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=1", "-vf", "format=gray", str(old)], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(old), "-vf", "crop=1100:619:90:50,scale=1280:720", str(new)], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=25", "-t", "1", str(other)], check=True)
    r = thennow.align(old, .5, new, .5)
    assert r["ok"] and r["inliers"] >= 24
    x0, y0 = r["quad"][0]
    assert 0 < x0 < .15 and 0 < y0 < .15  # the zoomed-in view sits inside the old frame, near its top left
    assert not thennow.align(old, .5, other, .5)["ok"]
    track = thennow.relax_track(r["quad"], 60)
    assert track[0]["corners"] == r["quad"] and track[-1]["corners"] == [[0, 0], [1, 0], [1, 1], [0, 1]]


def test_document_highlight_piles_the_unanswered_letters_before_the_last_one():
    """Hồ Chí Minh's letters to Truman land one by one behind the telegram of 28 February 1946; the passage comes up only
    once the pile has landed, so the underline cannot start before it."""
    from editvideo import cinematic
    req = {"recipe": "document_highlight", "id": "hcm", "start_frame": 0, "end_frame": 420, "heading": "Hồ Chí Minh gửi Tổng thống Truman · 28.2.1946",
           "passage": "Tôi khẩn thiết kêu gọi cá nhân ngài và nhân dân Mỹ can thiệp khẩn cấp để ủng hộ nền độc lập của chúng tôi.",
           "highlight": "ủng hộ nền độc lập của chúng tôi", "highlight_at": 150, "source": "NARA 305263 · bản dịch của đoàn làm phim",
           "stack": ["10.1945 · THƯ", "11.1945 · ĐIỆN", "1.1946 · THƯ", "16.2.1946 · THƯ"]}
    q = cinematic.DocumentHighlight.model_validate(req)
    r = cinematic.document_highlight(_timeline(), q)
    L = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    assert [L[f"hcm-stl{k}"]["text"] for k in range(4)] == req["stack"]
    assert L["hcm-st0"]["y"] < L["hcm-st3"]["y"] < L["hcm-paper"]["y"]  # the oldest letter shows the highest strip
    assert L["hcm-st3"]["z"] < L["hcm-paper"]["z"] < L["hcm-mark"]["z"] < L["hcm-line0"]["z"]
    assert L["hcm-line0"]["effects"][0]["start_frame"] >= q.stack_frames()
    assert r["measurements"]["stack"] == 4 and not r["notes"]
    with pytest.raises(Exception, match="underline starts"):
        cinematic.DocumentHighlight.model_validate({**req, "highlight_at": 30})


def test_night_log_counts_the_campaign_night_by_night():
    """Twelve days and nights of December 1972 (B-52 sorties per night, US Air Force): the night on screen in the accent
    colour, the ones before grey, Christmas a gap with its note, the sum on the last night."""
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    vals = [129, 93, 99, 30, 30, 30, 30, None, 120, 60, 60, 60]
    nights = [{"label": f"{18 + i}.12", "value": v} if v is not None else {"label": "25.12", "note": "ngừng ném bom"} for i, v in enumerate(vals)]
    at = [i * 60 for i in range(12)]
    q = cinematic.NightLog.model_validate({"recipe": "night_log", "id": "nl", "start_frame": 100, "end_frame": 100 + 12 * 60 + 60, "title": "LINEBACKER II",
                                           "unit": "lượt B-52", "nights": nights, "at": at, "source": "Không quân Mỹ"})
    r = cinematic.night_log(_timeline(), q)
    L = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    assert L["nl-line0"]["text"] == "ĐÊM 1 · 18.12 · 129 lượt B-52" and L["nl-line7"]["text"] == "25.12 · ngừng ném bom"
    assert L["nl-line11"]["text"].endswith("TỔNG · 741 lượt B-52")
    assert L["nl-bars2"]["start_frame"] == 220 and L["nl-bars2"]["end_frame"] == 280
    els = {e.id: e for e in SvgGraphic.model_validate(L["nl-bars2"]["data"]).elements}
    assert els["b2"].fill == "#e8b04a" and els["b0"].fill == "#7d8590" and els["b5"].fill == "none" and els["p7"].type == "line"
    assert r["measurements"]["counted"] == 741
    with pytest.raises(Exception, match="at must rise"):
        cinematic.NightLog.model_validate({**q.model_dump(), "at": [0] + at[:-1]})


def test_credibility_gap_reads_the_claim_before_the_record_beside_it():
    from editvideo import cinematic
    req = {"recipe": "credibility_gap", "id": "tk", "start_frame": 0, "end_frame": 400, "claim_clips": [{"asset_id": "a1", "source_start": 2.0, "duration": 10.0}],
           "claim_label": "WASHINGTON · 4.8.1964", "claim": "Tàu chiến Mỹ bị tấn công lần thứ hai ở vịnh Bắc Bộ.",
           "record_label": "NSA · GIẢI MẬT NĂM 2005", "record": "Cuộc tấn công thứ hai, đêm 4.8.1964, đã không xảy ra.",
           "source": "Robert J. Hanyok, Cryptologic Quarterly", "split_at": 120}
    r = cinematic.credibility_gap(_timeline(), cinematic.CredibilityGap.model_validate(req))
    L = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    assert L["tk-claim0"]["end_frame"] == L["tk-claim0h"]["start_frame"] == 120 and L["tk-claim0h"]["width"] == .5
    assert L["tk-claim0h"]["source_start"] == 6.0  # the claim's footage keeps playing through the split
    assert L["tk-claim1h"]["asset_id"] == "a1" and L["tk-claim1h"]["source_start"] == 2.0  # a short clip gives way to the next
    assert L["tk-record-text"]["x"] >= .5 and L["tk-claim-text"]["x"] + L["tk-claim-text"]["width"] <= .5
    with pytest.raises(Exception, match="read before the record"):
        cinematic.CredibilityGap.model_validate({**req, "split_at": 30})


def test_intensity_curve_finds_a_flat_stretch_and_a_chosen_silence(tmp_path):
    """Two minutes at one level read as flat; a five-second hush in the middle of a loud minute reads as a drop."""
    import subprocess
    from editvideo import review
    from editvideo.media import FFMPEG
    f = tmp_path / "mix.wav"
    expr = "0.3*sin(2*PI*220*t)*(lt(t,120)+gte(t,125))"  # 200 s of tone, silent from 120 s to 125 s
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=8000:d=200", str(f)], check=True)
    r = review.intensity_curve(f)
    assert len(r["levels"]) == 40 and r["flat"][0] == {"start_s": 0.0, "end_s": 120.0}
    assert [d["at_s"] for d in r["drops"]] == [120.0]


def test_models_installed_with_the_code_are_found_from_a_store_on_another_drive(tmp_path, monkeypatch):
    """Round 13, sixth cut: with the project store on G: the depth model (installed under the repository's data/models)
    was reported missing; every model lookup goes through store.models_root."""
    from editvideo import depth, local_footage, store, subjects
    shared = tmp_path / "shared"
    (shared / "depth-anything-v2-small").mkdir(parents=True)
    (shared / "ltx").mkdir()
    (shared / "sam2.1_hiera_tiny.pt").write_bytes(b"x")
    monkeypatch.setattr(store, "DATA", tmp_path / "store")
    monkeypatch.setattr(store, "SHARED_MODELS", shared)
    assert depth.model_root() == shared / "depth-anything-v2-small"
    assert local_footage.root() == shared / "ltx"
    assert subjects.model_path("sam2.1_hiera_tiny.pt") == shared / "sam2.1_hiera_tiny.pt"


def test_subtitles_too_fast_borrow_the_pause_around_them_not_the_next_line():
    from editvideo import subtitles
    cues = [{"start": 0.0, "end": 2.0, "text": "One night, as the guns were being hauled, a winch cable snapped."},
            {"start": 3.0, "end": 6.0, "text": "A soldier threw himself under the wheel."}]
    subtitles.relax(cues)
    assert cues[0]["end"] == 2.92 and cues[0]["start"] == 0.0  # up to the next cue, less the gap
    assert cues[1]["end"] == 6.0  # already readable: untouched
    late = [{"start": 10.0, "end": 11.0, "text": "x" * 51}]
    subtitles.relax(late)
    assert late[0]["end"] == 12.5 and late[0]["start"] == 9.7  # the full hold, then a lead into the quiet before


def test_news_montage_plays_the_set_then_floods_the_frame_then_stops():
    """Rebuilt from five studied sequences: one period TV fills the frame and pushes in (its parts ride one null), then
    the bulletins flood the frame with each cut shorter and a wedge carrying the place, then the last picture is held and
    the screen goes black. Every screen stays inside its clip; no ticker, no title."""
    from editvideo import cinematic
    bl = [{"asset_id": f"a{i}", "source_start": .5, "duration": d, "caption": f"Nơi {i} · 1964"} for i, d in enumerate([6.0, 4.0, 5.0, 9.0, 3.0, 7.0])]
    q = cinematic.NewsMontage.model_validate({"recipe": "news_montage", "id": "nm", "start_frame": 100, "end_frame": 100 + 18 * 30, "bulletins": bl,
                                              "static_asset": "noise"})
    r = cinematic.news_montage(_timeline(), q)
    L = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    dur = {b["asset_id"]: b["duration"] for b in bl}
    vids = [l for l in L.values() if l["kind"] == "video" and l["asset_id"] != "noise"]
    assert all((l["end_frame"] - l["start_frame"]) / 30 <= dur[l["asset_id"]] for l in vids)
    assert L["nm-rig"]["kind"] == "null" and L["nm-tv0"]["parent"] == "nm-rig" and L["nm-cabinet"]["parent"] == "nm-rig"
    flood = sorted((l for k, l in L.items() if k.startswith("nm-fl")), key=lambda l: l["start_frame"])
    spans = [l["end_frame"] - l["start_frame"] for l in flood]
    assert len(flood) >= 4 and spans[0] > spans[-2] and min(spans) >= 12 and flood[0]["width"] == 1
    assert any(k.startswith("nm-wedge") for k in L) and not any("crawl" in k or "title" in k for k in L)
    ph = r["phases"]
    assert ph["tv"][1] == ph["flood"][0] and ph["flood"][1] == ph["hold"][0] and ph["black"][1] == 100 + 18 * 30
    assert "NƠI 0 · 1964" in L["nm-tvcap0"]["text"]
    with pytest.raises(Exception, match="needs >="):
        cinematic.NewsMontage.model_validate({**q.model_dump(), "end_frame": 300})


def test_a_grid_figure_too_wide_for_its_column_takes_the_smaller_face():
    from editvideo import cinematic
    g = cinematic.DataStory.model_validate({"recipe": "data_story", "id": "lit", "start_frame": 0, "end_frame": 300, "kind": "grid", "title": "NĂM 1945",
                                            "figures": [{"value": 90, "prefix": "hơn ", "suffix": " %", "label": "đồng bào mù chữ", "source": "Hồ Chí Minh"}]})
    t = _timeline()
    t["design"]["typography"]["display"].update(size=150, tracking=.2)  # the film's display face: wide, letter-spaced
    n0 = next(o["layer"] for o in cinematic.data_story(t, g)["ops"] if o["layer"]["id"] == "lit-n0")
    assert n0["typography_role"] == "data"


def test_figure_labels_that_break_into_lines_push_their_sources_down():
    from editvideo import cinematic
    long = "người Việt Nam chết, cả quân nhân và dân thường"
    q = cinematic.DataStory.model_validate({"recipe": "data_story", "id": "c", "start_frame": 0, "end_frame": 600, "title": "CÁI GIÁ",
                                            "figures": [{"value": 3, "suffix": " triệu", "label": long, "source": "Chính phủ Việt Nam, 1995"},
                                                        {"value": 220, "suffix": " nghìn", "label": "quân nhân", "source": "Ước tính"},
                                                        {"value": 58220, "label": "quân nhân Mỹ", "source": "NARA"}]})
    L = {o["layer"]["id"]: o["layer"] for o in cinematic.data_story(_timeline(), q)["ops"]}
    assert L["c-l0"]["height"] > .1 and L["c-s0"]["y"] >= L["c-l0"]["y"] + L["c-l0"]["height"]
    assert L["c-s1"]["y"] == L["c-s0"]["y"]  # sources stay on one line across the columns


def test_night_log_stacks_title_bars_line_and_source_without_overlap():
    from editvideo import cinematic
    q = cinematic.NightLog.model_validate({"recipe": "night_log", "id": "nl", "start_frame": 0, "end_frame": 400, "title": "LƯỢT B-52 MỖI ĐÊM", "unit": "lượt",
                                           "nights": [{"label": "18.12", "value": 129}, {"label": "19.12", "value": 93}], "at": [0, 200],
                                           "source": "Không quân Mỹ · Linebacker II", "top": .145})
    t = _timeline()
    t["design"]["typography"]["source"]["size"] = 24  # the film's source face
    L = {o["layer"]["id"]: o["layer"] for o in cinematic.night_log(t, q)["ops"]}
    stack = [L["nl-title"], L["nl-bars1"], L["nl-line1"], L["nl-src"]]
    assert all(a["y"] + a["height"] <= b["y"] + 1e-6 for a, b in zip(stack, stack[1:]))
    assert L["nl-src"]["y"] + L["nl-src"]["height"] <= L["nl-bg"]["y"] + L["nl-bg"]["height"]


def test_the_master_limits_a_loud_onset_under_its_true_peak(tmp_path):
    """Linear loudnorm only applies gain: a sharp onset over a quiet bed went past 0 dBTP. The master's limiter keeps
    every sample under the target."""
    import json, re, subprocess
    import numpy as np
    from editvideo import renderer
    from editvideo.media import FFMPEG
    from editvideo.models import AudioMix
    src = tmp_path / "mix.wav"
    expr = "0.05*sin(2*PI*220*t)+0.95*sin(2*PI*1500*t)*between(t,5,5.05)"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d=20", "-ac", "2", str(src)], check=True)
    master = AudioMix(target_lufs=-16.0, true_peak_db=-1.5)
    log = subprocess.run([FFMPEG, "-v", "info", "-i", str(src), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    measured = json.loads(re.search(r'\{\s*"input_i".*?\}', log, re.S).group())
    out = tmp_path / "master.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-af", renderer.master_filter(master, measured), "-ar", "48000", str(out)], check=True)
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(out), "-f", "f32le", "-"], capture_output=True).stdout
    assert 20 * np.log10(np.abs(np.frombuffer(raw, np.float32)).max()) <= -1.9


def test_figure_cards_draw_a_picture_for_every_number():
    """The owner on the sixth cut: the cards were only text. A share gets a ring, a count its pictograms (the accent on
    the part named), magnitudes far apart proportional circles; footage stays behind the card."""
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    t = _timeline()

    def pics(req):
        q = cinematic.DataStory.model_validate({"recipe": "data_story", "id": "d", "start_frame": 0, "end_frame": 600, "title": "X", **req})
        L = {o["layer"]["id"]: o["layer"] for o in cinematic.data_story(t, q)["ops"]}
        return L, {e.id: e for e in SvgGraphic.model_validate(L["d-pictures"]["data"]).elements}
    L, els = pics({"figures": [{"value": 37, "suffix": " %", "label": "thuốc phiện", "source": "Báo cáo 1914"}],
                   "backdrop": {"asset_id": "a9", "source_start": 4.0}})
    assert "ra0" in els and els["ra0"].draw and L["d-plate"]["asset_id"] == "a9" and L["d-card"]["opacity"] < 1
    L, els = pics({"compare": True, "figures": [{"value": 81, "label": "máy bay", "source": "Phía Việt Nam", "icon": "plane", "highlight": 34},
                                                {"value": 26, "label": "máy bay", "source": "Không quân Mỹ", "icon": "plane", "highlight": 15}]})
    first = [e for k, e in els.items() if k.startswith("u0_")]
    assert len({k.split("p")[0] for k in els if k.startswith("u0_")}) == 81
    assert sum(1 for e in first if e.stroke == "#e8b04a") == 34  # B-52s in the accent, the rest grey
    L, els = pics({"figures": [{"value": 3, "suffix": " triệu", "scale": 1e6, "label": "người Việt Nam", "source": "Chính phủ Việt Nam"},
                               {"value": 58220, "label": "quân nhân Mỹ", "source": "NARA"}]})
    assert 7 < els["ar0"].r / els["ar1"].r < 7.4  # areas, not radii, carry the ratio (3 million against 58,220)
    L, els = pics({"figures": [{"value": .45, "decimals": 2, "suffix": " tỷ USD", "label": "1995", "source": "Census"},
                               {"value": 209.5, "decimals": 1, "suffix": " tỷ USD", "label": "2025", "source": "USTR"}]})
    assert els["ar0"].ripple and not els["ar1"].ripple  # a dot this small is pointed at


def test_a_timed_glitch_ends_at_its_end_frame(tmp_path):
    """A 4-frame glitch at a news wall's phase change ran for the rest of the clip (effects ignored end_frame) and broke
    half the screens; a timed accent stops, a one-frame span keeps its old whole-layer meaning."""
    from test_pro_workflows import fx
    r = fx(tmp_path, """const G=(e,f)=>JSON.stringify(fx.styleAt({effects:[e]},f));
    const g={name:'glitch',start_frame:0,end_frame:4,params:{amount:14,rate:1,seed:3}}, whole={...g,end_frame:1};
    console.log(JSON.stringify({during:G(g,2),after:G(g,40),plain:G({effects:[]},40),whole:G(whole,40)}));""")
    assert r["during"] != r["plain"] and r["after"] == r["plain"] and r["whole"] != r["plain"]


def test_icon_paths_move_and_scale_into_a_chart():
    from editvideo import icons
    assert icons.place("M12 2a5 5 0 1 1 -5 5z", 100, 50, 48) == "M124 54a10 10 0 1 1 -10 10Z"
    assert icons.place("M7 17m-2 0h4V5", 0, 0, 12) == "M3.5 8.5m-1 0h2V2.5"
    with pytest.raises(ValueError):
        icons.icon("tank")


def test_satellite_imagery_lands_on_the_terrain_grid(monkeypatch, tmp_path):
    """Tiles (Web Mercator) are resampled onto the same north-up lon/lat grid as terrain.elevation."""
    import io
    import numpy as np
    from PIL import Image
    from editvideo import imagery, store
    monkeypatch.setattr(store, "DATA", tmp_path)

    def fake(z, x, y, retries=3, source="s2c2016"):  # every tile red on its west half, blue on its east half
        a = np.zeros((256, 256, 3), np.uint8)
        a[:, :128, 0], a[:, 128:, 2] = 255, 255
        b = io.BytesIO()
        Image.fromarray(a).save(b, "PNG")
        return b.getvalue()
    monkeypatch.setattr(imagery, "_tile", fake)
    x0, _ = imagery._tile_xy(103.0, 21.4, 14)
    w = 103.0 + (1 - (x0 % 1)) * 360 / 2 ** 14  # the bbox starts on a tile boundary
    out = imagery.satellite([w, 21.30, w + 360 / 2 ** 14, 21.31], 64, 32, 14)
    assert out.shape == (32, 64, 3) and out[:, 5, 0].mean() > 200 and out[:, 58, 2].mean() > 200


def test_blender_jobs_are_cached_by_their_inputs(monkeypatch, tmp_path):
    """A finished job with the same script, params and input files is returned without starting Blender."""
    import json
    from editvideo import blender, store
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(blender, "find", lambda: "blender.exe")
    f = tmp_path / "h.npy"
    f.write_bytes(b"x")
    from editvideo import style
    params = {"frames": 10, "camera": []}
    key = blender._digest({**style.blender_defaults("terrain_shot"), **params}, blender.SCRIPTS / "terrain_shot.py", [f])  # the bible is in the key
    job = tmp_path / "cache" / "blender" / f"terrain_shot-{key}"
    job.mkdir(parents=True)
    (job / "done.json").write_text(json.dumps({"frames": 10, "per_frame_s": .6}))
    monkeypatch.setattr(blender.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Blender started")))
    r = blender.run("terrain_shot", params, files=[f])
    assert r["cached"] and r["per_frame_s"] == .6
    assert blender._digest({**params, "frames": 11}, blender.SCRIPTS / "terrain_shot.py", [f]) != key


def test_a_clock_pulse_can_race_like_a_news_montage():
    from editvideo import sound
    r = sound.design("clock", 2.0, 7, gain_db=-16, bpm=180, end_bpm=540)
    assert r["duration"] == pytest.approx(2.0, abs=.05)
    with pytest.raises(ValueError):
        sound.design("heartbeat", 2.0, 7, bpm=300)


def test_credit_tracing_follows_each_copy_of_a_file_once(monkeypatch, tmp_path):
    """Every rebuild re-imports the same files, so one sha had 100+ assets across projects; each copy traced every
    other copy again, eight levels deep, and the episode 2 render sat in project_credits for hours."""
    import time
    from editvideo import media_tasks, resources
    monkeypatch.setattr(resources, "SHA_CACHE", tmp_path / "sha-cache.json")
    src = tmp_path / "reel.mp4"
    src.write_bytes(b"archive reel")
    lib = resources._sha(src)
    calls = []
    monkeypatch.setattr(media_tasks, "get", lambda tid: calls.append(tid) or {"kind": "retime", "request": {"path": str(src)}})
    index = resources._Index.__new__(resources._Index)
    index.cache, index.library, index.by_path = {}, {lib: {"id": "lib1", "title": "Reel", "credit": "An Archive", "license": "CC0"}}, {}
    index._artifacts, index._artifact_paths, index.tasks, index.seen = None, {}, {}, set()
    copies = [{"id": f"a{i:03d}", "sha256": "f" * 64, "created_at": f"2026-10-{i:03d}", "provenance": {"operation": "import", "n": i}}
              for i in range(120)]
    index.assets = {"f" * 64: copies}
    t = time.time()
    assert resources.trace_origin(copies[60], index)[0] is None  # no copy leads anywhere: every copy looked at once
    copies[-1]["provenance"] = {"media_task_id": "task-1"}
    hit, chain = resources.trace_origin(copies[0], index)
    assert time.time() - t < 2
    assert hit["id"] == "lib1" and chain == ["copy of asset a119", "retime task task-1"]  # only the path that led somewhere
    assert calls == ["task-1"]


def test_still_runs_find_a_card_that_barely_moves(tmp_path):
    """Round 13, ninth cut: cards with one growing line, 92-100 % of the picture never moving for 9-12 s."""
    import subprocess
    from editvideo import review
    from editvideo.media import FFMPEG
    slide = tmp_path / "slide.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x203030:s=640x360:r=30:d=5", "-f", "lavfi",
                    "-i", "color=c=0xd8c8a0:s=640x4:r=30:d=5", "-filter_complex",
                    "[0:v]drawbox=x=60:y=60:w=200:h=120:color=0x9a8f80:t=fill[b];[b][1:v]overlay=x='-640+640*t/5':y=300[v]",
                    "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(slide)], check=True)
    move = tmp_path / "move.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=5", "-vf",
                    "crop=640:360:'320*t/5':'180*t/5'", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(move)], check=True)
    r = review.still_runs(slide)
    assert r["runs"] and r["seconds"] >= 3 and r["runs"][0]["static_share"] > .95
    assert review.still_runs(move)["runs"] == []


def test_labels_over_a_3d_clip_follow_their_place_and_hide_behind_ridges():
    """Round 13, showcase: labels drawn by the film over a Blender clip (crisp, editable), moved by the screen track the
    template writes, shown from their cue while the place is visible, not drawn when a ridge hides it throughout."""
    from editvideo import blender
    n = 120
    tracks = {"tracks": {"a": [[f, .3 + .001 * f, .5, 1] for f in range(n)],
                         "b": [[f, .6, .4, int(f < 50)] for f in range(n)],
                         "c": [[f, .5, .5, 0] for f in range(n)]}}
    r = blender.label_layers(tracks, 300, [{"id": "a", "text": "Mường Thanh", "at": 20}, {"id": "b", "text": "Him Lam", "at": 10},
                                           {"id": "c", "text": "Hồng Cúm", "at": 0}])
    by = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    a, b = by["lab3d-a"], by["lab3d-b"]
    assert (a["start_frame"], a["end_frame"]) == (320, 420) and (b["start_frame"], b["end_frame"]) == (310, 350)
    assert a["x"] + a["width"] / 2 == pytest.approx(.32, abs=.002) and a["y"] + a["height"] < .5  # bottom centre just above the point
    xs = a["keyframes"]["x"]
    assert xs[0]["value"] == 0 and xs[-1]["value"] == pytest.approx(.099 * 1920, abs=1) and len(xs) <= 100
    assert [s["id"] for s in r["skipped"]] == ["c"]


def test_blender_runs_only_bundled_templates(monkeypatch, tmp_path):
    from editvideo import blender
    monkeypatch.setattr(blender, "find", lambda: "blender.exe")
    for bad in ("../evil", "nope_shot"):
        with pytest.raises(ValueError, match="bundled 3D template"):
            blender.run(bad, {})


def test_a_layer_window_that_crosses_a_cut_in_its_source_is_found(tmp_path):
    """Round 13 showcase: a portrait panel ran past a cut inside its archive clip and showed a title card."""
    import subprocess
    from editvideo import review
    from editvideo.media import FFMPEG
    clip = tmp_path / "reel.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=2", "-f", "lavfi", "-i", "color=c=0x101010:s=640x360:r=30:d=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    cuts = review.cuts_inside(clip)
    assert len(cuts) == 1 and abs(cuts[0] - 2.0) < .1
    assets = [{"id": "a", "kind": "video", "path": str(clip)}]
    tl = {"shots": [], "layers": [{"id": "over", "kind": "video", "asset_id": "a", "start_frame": 0, "end_frame": 90, "source_start": .5},
                                  {"id": "before", "kind": "video", "asset_id": "a", "start_frame": 0, "end_frame": 45, "source_start": .2}]}
    hits = review.source_cuts(tl, assets)
    assert [h["id"] for h in hits] == ["over"]


def test_a_2d_pin_comes_and_goes_with_its_label():
    """Round 13 showcase: a 3D stem stood with no label when the label was dropped for leaving the frame."""
    from editvideo import blender
    tracks = {"tracks": {"a": [[f, .5, .6, 1] for f in range(60)], "edge": [[f, .995, .5, 1] for f in range(60)]}}
    r = blender.label_layers(tracks, 0, [{"id": "a", "text": "Sê Pôn", "pin": True, "lift": .035}, {"id": "edge", "text": "Khe Sanh", "pin": True}])
    by = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    assert {"lab3d-a", "lab3d-a-dot", "lab3d-a-lead"} <= set(by) and not any(k.startswith("lab3d-edge") for k in by)
    assert by["lab3d-a-dot"]["keyframes"] == by["lab3d-a"]["keyframes"]
    assert by["lab3d-a-lead"]["y"] + by["lab3d-a-lead"]["height"] == pytest.approx(.6, abs=.002)  # the leader reaches the place
    assert [s_["id"] for s_ in r["skipped"]] == ["edge"]


def test_an_auto_label_takes_the_side_that_stays_in_frame():
    """Round 13 showcase: "MỸ" was dropped because the USA sat at the frame's left edge; its words fit on the right."""
    from editvideo import blender
    tracks = {"tracks": {"usa": [[f, .04, .5, 1] for f in range(60)]}}
    assert blender.label_layers(tracks, 0, [{"id": "usa", "text": "MỸ"}])["skipped"]
    r = blender.label_layers(tracks, 0, [{"id": "usa", "text": "MỸ", "side": "auto"}])
    lab = r["ops"][0]["layer"]
    assert not r["skipped"] and lab["x"] > .04 and lab["data"]["align"] == "left"


def test_the_series_bible_sets_reading_time_and_template_defaults():
    """reports/Nâng cấp 3D phim tài liệu.md P0-2: one bible every generator reads."""
    from editvideo import style
    assert style.hold_frames("Đèo Ban Karai") == 45  # the 1.5 s floor
    assert style.hold_frames("x" * 51) == 90 and style.hold_frames("x" * 51, lang="en") < 90  # Vietnamese reads at 17 cps
    d = style.blender_defaults("bloc_map")
    assert d["view"] == "Khronos PBR Neutral" and d["color_depth"] == "16"  # map colours keep their hues; no 8-bit banding
    assert style.blender_defaults("terrain_shot")["view"] == "AgX"


def test_the_finish_breaks_up_banding_in_a_dark_gradient(tmp_path):
    """The bloc map's dark sea measured CAMBI 6.6 raw and 0.003 through editvideo.finish."""
    import subprocess
    from editvideo import finish, review
    from editvideo.media import FFMPEG
    raw = tmp_path / "raw.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "gradients=s=640x360:c0=0x0b1018:c1=0x1c2a36:x0=0:y0=0:x1=640:y1=360:d=1:r=30",
                    "-vf", "format=yuv420p", "-c:v", "libx264", "-crf", "18", str(raw)], check=True)
    out = tmp_path / "fin.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(raw), "-filter_complex", finish.filter_graph(640, 360), "-map", "[v]", "-c:v", "libx264",
                    "-crf", "18", *finish.encode_args(), str(out)], check=True)
    assert review.banding(out)["mean"] < review.banding(raw)["mean"]


def test_flashes_and_legal_levels_are_screened(tmp_path):
    import subprocess
    from editvideo import review
    from editvideo.media import FFMPEG
    flash = tmp_path / "flash.mp4"  # black and white swapping every 3 frames: five flashes a second
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=2", "-vf",
                    "geq=lum='if(lt(mod(N,6),3),16,235)':cb=128:cr=128,format=yuv420p", "-c:v", "libx264", "-crf", "18", str(flash)], check=True)
    calm = tmp_path / "calm.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(calm)], check=True)
    assert review.flashes(flash)["fails"] and not review.flashes(calm)["fails"]
    grey = tmp_path / "grey.mp4"  # (testsrc2's saturated bars are themselves out of gamut: 6 % of the frame)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x606060:s=320x180:r=30:d=1", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(grey)], check=True)
    hot = tmp_path / "hot.mp4"  # luma pushed past 235 over the whole frame
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(grey), "-vf", "lutyuv=y=250", "-c:v", "libx264", "-crf", "18", str(hot)], check=True)
    assert review.legal_levels(hot)["frames"] > 0 and review.legal_levels(grey)["frames"] == 0


def test_text_that_leaves_before_it_can_be_read_is_reported():
    from editvideo import review
    tl = {"layers": [{"id": "quick", "kind": "text", "text": "MÃ LAI", "start_frame": 0, "end_frame": 30, "effects": []},
                     {"id": "fine", "kind": "text", "text": "MÃ LAI", "start_frame": 0, "end_frame": 60, "effects": []}]}
    assert [x["id"] for x in review.text_holds(tl)] == ["quick"]


def test_a_period_map_lands_where_its_datum_says(tmp_path):
    """A 1967 AMS sheet (Indian 1960 datum) draped on the WGS84 grid: the published datum shift moves it ~400 m; the
    pyproj default ("ballpark", no shift) had put the Điện Biên Phủ airstrip 400 m east of today's."""
    import numpy as np
    pytest.importorskip("pyproj")  # the geo extras
    from PIL import Image
    from pyproj.transformer import TransformerGroup
    from editvideo import period_maps as pm
    best = next(t_ for t_ in TransformerGroup(4326, 3148, always_xy=True).transformers if "Ballpark" not in t_.description)
    e, n = best.transform(103.0078, 21.3975)
    assert abs(e - 293894) < 60 and abs(n - 2367130) < 60
    # a synthetic sheet: page units are metres / 10 from a UTM origin, one red dot over the airstrip
    e0, n0 = e - 2000, n - 2000
    page_h = 400.0
    png = tmp_path / "sheet.png"
    a = np.full((400, 400, 3), 230, np.uint8)
    a[198:203, 198:203] = (255, 0, 0)  # page (200, 200) <-> (e, n)
    Image.fromarray(a).save(png)
    reg = [[0, 0, e0, n0], [400, 0, e0 + 4000, n0], [0, 400, e0, n0 + 4000], [400, 400, e0 + 4000, n0 + 4000]]
    sh = {"pdf": "x.pdf", "png": str(png), "dpi": 72, "page": [400, page_h], "registration": reg,
          "neatline": [[0, 0], [400, 0], [400, 400], [0, 400]], "epsg": 3148}
    bbox = [103.0078 - .01, 21.3975 - .01, 103.0078 + .01, 21.3975 + .01]
    img, rep = pm.drape(bbox, 201, 201, [sh])
    r, c = np.unravel_index(np.argmax(img[..., 0].astype(int) - img[..., 1]), img.shape[:2])
    assert abs(r - 100) <= 2 and abs(c - 100) <= 2 and rep[0]["registration_residual_m"] < 1

