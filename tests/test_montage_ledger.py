"""The blockbuster archive montage (editvideo.montage) and the licence ledger (editvideo.ledger)."""
import pytest


def _req(**kw):
    shots = [{"asset_id": f"a{i}", "duration": 4.0, "role": "threat" if i > 24 else "news", "date": "8.1964" if i == 0 else ("3.1965" if i == 6 else ""),
              "place": "Vịnh Bắc Bộ" if i == 0 else ("Đà Nẵng" if i == 6 else "")} for i in range(60)]
    shots.append({"asset_id": "hit", "duration": 4.0, "role": "climax"})
    return {"recipe": "archive_montage", "id": "m", "start_frame": 0, "end_frame": 2100, "shots": shots, "title": "Leo thang", "seed": 3,
            "allow_undated": True,
            "cards": [{"kind": "teletype", "at": .8, "text": "7.8.1964 · Quốc hội Mỹ thông qua nghị quyết"},
                      {"kind": "redact", "at": 6.9, "lines": ["PUBLIC LAW 88-408", "TO TAKE ALL NECESSARY STEPS"], "keep": ["PUBLIC LAW 88-408", "ALL NECESSARY STEPS"]},
                      {"kind": "headline", "at": 11.6, "text": "Mỹ ném bom miền Bắc", "source": "Rolling Thunder · 2.3.1965"},
                      {"kind": "counter", "at": 20, "text": "Quân Mỹ · cuối 1965", "value_from": 23300, "value_to": 184300},
                      {"kind": "quote", "at": 30, "text": "Một câu trích có nguồn.", "source": "Ai đó · 1965"}], **kw}


def _compile(**kw):
    from editvideo import montage
    q = montage.ArchiveMontage.model_validate(_req(**kw))
    return montage.archive_montage({"width": 1920, "height": 1080}, q), q


def test_rhythm_fills_the_body_and_tightens_toward_the_end():
    from editvideo import montage
    lens = montage.rhythm(1800, 2.3, .55, 1.6, seed=7)
    assert sum(lens) == 1800 and min(lens) >= 8
    third = len(lens) // 3
    assert sum(lens[:third]) / third > 2 * sum(lens[-third:]) / third  # WWZ: 2.36 s -> 1.25 s by thirds, 0.6 s at the end
    beats = [i * 60 / 126 for i in range(200)]
    snapped = montage.rhythm(900, 1.0, 1.0, 1.0, seed=2, beats=beats)
    cuts = [sum(snapped[:i + 1]) for i in range(len(snapped) - 1)]
    grid = beats + [(a + b) / 2 for a, b in zip(beats, beats[1:])]  # beats and half-beats
    on_beat = sum(any(abs(c - b * 30) <= .51 for b in grid) for c in cuts)
    assert on_beat >= .8 * len(cuts)
    with pytest.raises(ValueError, match="not enough footage"):
        montage.rhythm(900, 1.0, 1.0, avail=[30] * 5)


def test_montage_cuts_tighten_cards_hold_and_the_hit_lands_after_silence():
    r, q = _compile()
    ops = [o["layer"] for o in r["ops"]]
    shots = sorted((l for l in ops if l["id"].startswith("m-s") and l["kind"] == "video"), key=lambda l: l["start_frame"])
    lens = [l["end_frame"] - l["start_frame"] for l in shots]
    assert len({l["asset_id"] for l in shots}) == len(shots)  # no footage repeats
    assert sum(lens[:5]) / 5 > 2 * sum(lens[-5:]) / 5
    plan = r["sound_plan"]
    climax = next(l for l in ops if l["id"] == "m-climax")
    assert climax["asset_id"] == "hit" and climax["start_frame"] == plan["hit"]
    # nothing is on screen in the gap before the hit but the black ground
    gap = (plan["body"][1], plan["hit"])
    assert gap[1] - gap[0] == 18
    assert not [l for l in ops if l["kind"] not in ("shape", "null", "film") and l["start_frame"] < gap[1] and l["end_frame"] > gap[0]]
    assert next(l for l in ops if l["id"] == "m-gap-intent")["data"] == {"intent": "deliberate_black"}
    # leader frames: one or two frames, never closer than flash_gap_s
    leads = sorted(l["start_frame"] for l in ops if l["id"].startswith("m-lead"))
    assert leads and all(b - a >= q.flash_gap_s * 30 for a, b in zip(leads, leads[1:]))
    assert all(l["end_frame"] - l["start_frame"] <= 2 for l in ops if l["id"].startswith("m-lead"))
    # full-frame cards never overlap; overlays (but a stamp) stop before a card; dates never sit on a card
    cards = sorted((l["start_frame"], l["end_frame"]) for l in ops if l["id"].endswith("bg") and l["id"][:3] in ("m-r", "m-h"))
    assert len(cards) == 2 and cards[0][1] <= cards[1][0]
    for l in ops:
        if l["id"].startswith(("m-tt", "m-date", "m-cl", "m-q")):
            assert not any(a < l["end_frame"] and b > l["start_frame"] for a, b in cards), l["id"]
    dates = [l for l in ops if l["id"].startswith("m-date") and l["kind"] == "text"]
    assert [d["text"] for d in dates] == ["8.1964 · VỊNH BẮC BỘ", "3.1965 · ĐÀ NẴNG"]
    assert all(d["end_frame"] - d["start_frame"] >= 60 for d in dates)
    # the end: white-out, silence, a small title
    title = next(l for l in ops if l["id"] == "m-title")
    assert title["start_frame"] == plan["title"] and plan["silence"][1] == plan["title"]


def test_redaction_bars_cover_every_word_but_the_kept_ones():
    from editvideo import montage
    bars = montage._redact_bars("TO TAKE ALL NECESSARY STEPS", ["ALL NECESSARY STEPS"], "ibmplexmono", 40, 500, 1500)
    assert len(bars) == 2  # TO, TAKE
    adv = 40 * .6  # IBM Plex Mono advance
    assert abs(bars[0][0]) < 6 and abs(bars[1][0] - 3 * adv) < 6 and bars[1][1] < 8 * adv


def test_montage_refuses_a_cut_without_its_climax_or_its_footage():
    from editvideo import montage
    req = _req()
    req["shots"] = [s for s in req["shots"] if s["role"] != "climax"]
    with pytest.raises(Exception, match="role=climax"):
        montage.ArchiveMontage.model_validate(req)
    with pytest.raises(Exception, match="needs >="):
        montage.ArchiveMontage.model_validate({**_req(), "end_frame": 300})
    short = _req()
    short["shots"] = short["shots"][:5] + short["shots"][-1:]
    with pytest.raises(ValueError, match="not enough footage"):
        montage.archive_montage({"width": 1920, "height": 1080}, montage.ArchiveMontage.model_validate(short))
    with pytest.raises(Exception, match="kept legible"):
        montage.ArchiveMontage.model_validate({**_req(), "cards": [{"kind": "redact", "at": 2, "lines": ["A B"]}]})


def test_score_keeps_the_gap_silent_and_cuts_the_cue_dead(tmp_path, monkeypatch):
    from editvideo import montage, store
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    r, _ = _compile()
    plan = r["sound_plan"]
    clips = montage.score(plan, music={"path": "cue.mp3", "source_start": 10.0})
    gap = (plan["body"][1], plan["hit"])
    sounding = [c for c in clips if c["start_frame"] < gap[1] and c["end_frame"] > gap[0] and c["role"] != "music"]
    assert not sounding  # a weak sound 30-500 ms before the hit blunts the startle
    cue = max((c for c in clips if c["role"] == "music"), key=lambda c: c["end_frame"])
    assert cue["end_frame"] <= gap[0] and cue["fade_out"] <= .05
    kinds = [c.get("kind") for c in clips]
    assert {"drone", "clock", "shepard", "suck_out", "braam", "impact", "sub_drop", "tinnitus", "typewriter", "shutter"} <= set(kinds)
    assert kinds.count("braam") <= 4  # three threats at most, and the hit


def test_ledger_classes_take_the_most_restrictive_part():
    from editvideo import ledger
    c = ledger.classify
    assert c("CC0 (US National Archives)") == "public_domain"
    assert c("Copyrighted; downloaded with the owner's approval for internal use only, credited") == "internal_only"
    assert c("Marked CC0 by the US National Archives; NBC footage may still be NBC's: internal use only") == "internal_only"
    assert c("CC BY-NC-ND 4.0") == "no_derivatives" and c("CC BY-NC-SA 4.0") == "noncommercial" and c("CC BY-SA 4.0") == "share_alike"
    assert c("SIL Open Font License 1.1") == "open" and c("CC BY 4.0") == "open" and c("") == "unknown"
    assert c("Generated for this project via Magnific (ElevenLabs v3)") == "generated" and c("Freepik Premium licence (Magnific subscription)") == "stock"
    assert c("Public domain (NASA SRTM) + Copernicus DEM GLO-30 licence (free use with attribution)") == "public_domain"
    assert c("Sentinel-2 cloudless 2016 (EOX): CC BY 4.0 claimed, unverified (EOX now lists CC BY-NC-SA 4.0) + Public domain") == "unknown"
    assert set(ledger.BLOCKS["online"]) == {"unknown", "internal_only", "editorial", "no_derivatives", "noncommercial"} and not ledger.BLOCKS["internal"]
    # the reviewer's cases: negations, hedges, licences spelled with spaces, editorial-only stock, NASA's "not copyrighted"
    assert c("CC BY NC 4.0") == "noncommercial" and c("CC BY SA 3.0") == "share_alike"
    assert c("No copyright infringement intended") == "unknown" and c("Public domain? not verified") == "unknown"
    assert c("Not public domain; AP licence required") == "internal_only"
    assert c("Freepik Premium licence (editorial use only)") == "editorial"
    assert c("NASA media (generally not copyrighted in the US; NASA media guidelines)") == "public_domain"
    assert c("NASA media (no copyright in the US; follow NASA media guidelines)") == "public_domain"
    # a composite owes every part's duty: PD + CC BY is classed public domain but still carries the CC BY credit
    assert ledger.classes("Public domain (NASA SRTM) + Copernicus DEM GLO-30 licence (free use with attribution)") == {"public_domain", "open"}


def test_a_cut_inherits_its_reel_and_a_render_its_inputs(tmp_path, monkeypatch):
    from editvideo import ledger, resources
    monkeypatch.setattr(resources, "CATALOG", tmp_path / "catalog.json")
    reel, cut, render = tmp_path / "reel.mp4", tmp_path / "cut.mp4", tmp_path / "render.mp4"
    reel.write_bytes(b"reel" * 100)
    cut.write_bytes(b"cut" * 100)
    render.write_bytes(b"render" * 100)
    ledger.register_source(reel, "CC0 (US National Archives)", "US National Archives", "https://catalog.archives.gov/id/1", "Operation Medina")
    e = ledger.register_cut(cut, reel, (151, 157.5))
    assert e["license"] == "CC0 (US National Archives)" and e["credit"] == "US National Archives" and "cut 151-157.5 s" in e["notes"]
    with pytest.raises(ValueError, match="register_source"):
        ledger.register_cut(cut, tmp_path / "unknown.mp4")
    r = ledger.register_render(render, "terrain", [("Public domain (NASA SRTM)", "NASA"), ("Esri World Imagery: internal research use only", "Esri")])
    assert ledger.classify(r["license"]) == "internal_only"
    assert ledger.find_entry(cut)["id"] == e["id"]


def test_four_layers_age_with_the_picture_and_share_a_bed_across_one_place(tmp_path, monkeypatch):
    from editvideo import archival_sound as A, store, sound
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    shots = [{"start_frame": 0, "end_frame": 90, "place": "waves", "year": 1965, "fidelity": "worn",
              "events": [{"kind": "helicopter", "at": .5, "distance": "near"}]},
             {"start_frame": 90, "end_frame": 150, "place": "waves", "year": 1965, "events": [{"kind": "artillery", "at": 1.0, "seconds": 1.5, "distance": "far"}]},
             {"start_frame": 150, "end_frame": 240, "place": "crowd", "year": 2016, "fidelity": "clean"}]
    clips = A.plan(shots, moments=[{"kind": "projector", "start_frame": 0, "end_frame": 150}])
    beds = [c for c in clips if c["layer"] == "ambience"]
    assert [(c["kind"], c["start_frame"]) for c in beds] == [("waves", 0), ("crowd", 150)]  # one bed for the two beach shots
    heli = next(c for c in clips if c["kind"] == "helicopter")
    gun = next(c for c in clips if c["kind"] == "artillery")
    assert heli["treatment"] == "archival" and heli["start_frame"] == 15 and gun["treatment"] == "distant" and gun["fade_in"] < .01
    assert "treatment" not in next(c for c in beds if c["kind"] == "crowd")  # a clean 2016 picture keeps clean sound
    assert next(c for c in clips if c["layer"] == "abstract")["kind"] == "projector"
    assert A.coverage(shots, clips) == [{"shot": 2, "frames": [150, 240], "missing": ["literal"]}]
    for k in ("helicopter", "jet", "artillery", "gunfire", "waves", "crowd", "projector"):
        assert k in sound.KINDS


def test_a_georeferenced_raster_lands_where_its_tags_say_and_reads_only_its_window(tmp_path):
    import numpy as np
    tifffile = pytest.importorskip("tifffile")  # the geo extras
    Transformer = pytest.importorskip("pyproj").Transformer
    from editvideo import period_maps as pm
    # a 1 m UTM 48N raster (EPSG:32648) around Quảng Trị citadel, tiled, with one bright 20 m square at a known place
    tr = Transformer.from_crs(4326, 32648, always_xy=True)
    x0, y0 = tr.transform(107.17, 16.76)
    img = np.full((800, 800), 90, np.uint8)
    img[400:420, 300:320] = 250  # 300-320 m east, 400-420 m south of the corner
    path = tmp_path / "kh9.tif"
    tifffile.imwrite(path, img, tile=(256, 256), compression="zlib", extratags=[
        (33550, "d", 3, (1.0, 1.0, 0.0)), (33922, "d", 6, (0, 0, 0, x0, y0, 0)),
        (34735, "H", 16, (1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 32648))])
    info = pm.geotiff(path)
    assert info["epsg"] == 32648 and info["tiled"] and info["affine"][0] == 1.0
    assert (pm.read_window(path, 290, 395, 330, 425) == img[395:425, 290:330]).all()
    lon_c, lat_c = Transformer.from_crs(32648, 4326, always_xy=True).transform(x0 + 310, y0 - 410)
    d = .0006  # about 64 m across
    out, rep = pm.drape_raster([lon_c - d, lat_c - d, lon_c + d, lat_c + d], 65, 65, path, base=np.zeros((65, 65, 3), np.uint8))
    assert rep["covered"] > .99 and rep["pixel_m"] == 1.0
    assert out[32, 32, 0] > 200 and out[2, 2, 0] < 120  # the bright square sits at the centre of its own bbox


def test_a_reconstruction_never_carries_an_archive_date_and_years_stay_in_the_story():
    from editvideo import montage
    with pytest.raises(Exception, match="carries no archive date"):
        montage.Shot.model_validate({"asset_id": "cg", "duration": 3, "kind": "reconstruction", "date": "5.8.1964"})
    with pytest.raises(Exception, match="disagrees"):
        montage.Shot.model_validate({"asset_id": "x", "duration": 3, "date": "5.8.1964", "year": 1966})
    assert montage.Shot.model_validate({"asset_id": "x", "duration": 3, "date": "5.8.1964"}).year == 1964
    req = _req(years=[1964, 1966])
    req["shots"][10]["year"] = 1975  # NARA's Saigon evacuation inside a 1964-67 film
    with pytest.raises(Exception, match="outside 1964-1966"):
        montage.ArchiveMontage.model_validate(req)


def test_one_line_of_type_at_a_time_and_no_slot_runs_past_its_footage():
    r, q = _compile()
    ops = [o["layer"] for o in r["ops"]]
    lines = sorted((l["start_frame"], l["end_frame"], l["id"]) for l in ops if l["kind"] in ("text", "counter")
                   and l["id"].split("-")[1][:2] in ("da", "tt", "cl", "q0", "q1", "q2", "q3", "q4") and not l["id"].endswith("sc"))
    groups = {}
    for a, b, i in lines:  # a counter's label/number and a quote's source belong to one line
        key = "".join(ch for ch in i.split("-")[1] if ch.isdigit())
        g = groups.setdefault((i.split("-")[1][:2].replace("cn", "cl").replace("cs", "cl").replace("qs", "q"), key), [a, b])
        g[0], g[1] = min(g[0], a), max(g[1], b)
    spans = sorted(groups.values())
    assert all(b0 <= a1 for (_, b0), (a1, _) in zip(spans, spans[1:])), spans
    by_asset = {s.asset_id: s for s in q.shots}
    for l in ops:
        if l["id"].startswith("m-s") and l["kind"] == "video":
            assert l["end_frame"] - l["start_frame"] <= int((by_asset[l["asset_id"]].duration - .05) * 30) + 1


def test_grain_keeps_blacks_black_and_stays_off_the_gap():
    r, q = _compile()
    plan = r["sound_plan"]
    grains = [o["layer"] for o in r["ops"] if o["layer"]["kind"] == "film"]
    assert grains and all(g["blend"] == "overlay" for g in grains if "dither" not in g["id"])
    assert all(g.get("opacity", 1) <= .1 for g in grains if "dither" in g["id"])  # the shadow dither lifts black by a few levels only
    assert not [g for g in grains if g["start_frame"] < plan["hit"] and g["end_frame"] > plan["body"][1]]


def test_rhythm_hands_leftover_frames_to_the_card_not_to_a_one_frame_shot():
    from editvideo import montage
    lens = montage.rhythm(24, 2.0, 2.0, 1.0, seed=1, avail=[23, 200])
    assert min(lens) >= 8 and sum(lens) <= 24 and lens[0] <= 23


def test_clean_runs_finds_a_burnt_flash_and_a_hidden_cut(tmp_path):
    import subprocess
    from editvideo import review
    from editvideo.media import FFMPEG
    clip = tmp_path / "reel.mp4"
    # 2 s of a textured grey shot, 0.3 s of the same with white burns, 1 s more, then a cut to another picture
    # (a burnt frame: the whole picture lifts and a few spots go white, as the punch holes in the Medina reel did)
    graph = ("testsrc2=s=320x180:r=30:d=4,format=gray,eq=contrast=.5:brightness=-.15,"
             "eq=brightness=.2:enable='between(t,2,2.3)',"
             "drawbox=x=40:y=40:w=30:h=30:color=white:t=fill:enable='between(t,2,2.3)',"
             "drawbox=x=200:y=90:w=24:h=24:color=white:t=fill:enable='between(t,2,2.3)',"
             "hflip=enable='gte(t,3.3)',negate=enable='gte(t,3.3)'")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", graph, "-pix_fmt", "yuv420p", str(clip)], check=True)
    r = review.clean_runs(clip)
    bad = {round(f["t"], 1) for f in r["flags"]}
    assert any(1.9 <= t <= 2.4 for t in bad) and any(3.2 <= t <= 3.4 for t in bad)
    assert r["runs"] and r["runs"][0][1] - r["runs"][0][0] >= 1.5


def test_a_declared_black_must_be_black(tmp_path):
    import subprocess
    from editvideo import review
    from editvideo.media import FFMPEG
    v = tmp_path / "gap.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x606060:s=320x180:r=30:d=1", "-f", "lavfi", "-i",
                    "color=c=0x2a2a2a:s=320x180:r=30:d=1", "-f", "lavfi", "-i", "color=c=0x606060:s=320x180:r=30:d=1", "-filter_complex",
                    "[0][1][2]concat=n=3:v=1:a=0,format=yuv420p", str(v)], check=True)
    t = {"fps": 30, "layers": [{"id": "gap", "kind": "null", "start_frame": 30, "end_frame": 60, "data": {"intent": "deliberate_black"}},
                              {"id": "long", "kind": "null", "start_frame": 0, "end_frame": 300, "data": {"intent": "deliberate_still"}}], "shots": []}
    g = review.delivery_gates(str(v), t)
    rows = {r["intent"]: r for r in g["gates"]["intent"]}
    assert rows["deliberate_black"]["not_black"] and rows["deliberate_black"]["luma"] > 16  # grey 42 is not black
    assert rows["deliberate_still"]["too_long"] and not g["pass"]



def test_a_dated_card_waits_for_footage_of_its_year_and_compilation_dates_are_not_captioned():
    from editvideo import montage
    req = _req(allow_undated=False)
    for i, sh in enumerate(req["shots"]):
        sh["year"] = None if 20 <= i < 30 else (1964 if i < 6 else 1965)
        if sh.get("date") and not sh["date"].endswith(str(sh["year"])):
            sh["date"] = ""
    req["shots"][6].update(date="3.1965", place="Đà Nẵng", date_source="compilation")
    req["cards"] = [{"kind": "quote", "at": 30, "text": "Một câu trích có nguồn.", "source": "Ai đó · 28.7.1965"}]
    q = montage.ArchiveMontage.model_validate(req)
    r = montage.archive_montage({"width": 1920, "height": 1080}, q)
    ops = [o["layer"] for o in r["ops"]]
    quote = next(l for l in ops if l["id"].startswith("m-q") and l["kind"] == "text" and not l["id"].startswith("m-qs"))
    by_asset = {s_.asset_id: s_ for s_ in q.shots}
    under = [by_asset[l["asset_id"]].year for l in ops if l["id"].startswith("m-s") and l["kind"] == "video"
             and l["start_frame"] < quote["end_frame"] and l["end_frame"] > quote["start_frame"]]
    assert under and set(under) == {1965}  # moved off the undated compilation stretch
    assert not [l for l in ops if l["id"].startswith("m-date") and "ĐÀ NẴNG" in (l.get("text") or "")]
    assert any("withheld" in n for n in r["notes"])


def test_hedged_or_negated_grants_are_not_grants():
    from editvideo import ledger
    for s_ in ("Not in the public domain", "likely public domain", "probably public domain", "presumed public domain",
               "Public domain (claimed by uploader)", "Standard YouTube License; public domain footage inside"):
        assert ledger.classify(s_) in ("unknown", "internal_only"), s_
    assert ledger.classify("Public domain (US federal government work)") == "public_domain"


def test_braams_with_different_seeds_differ(tmp_path, monkeypatch):
    from editvideo import store, sound
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    a, b = sound.design("braam", 1.0, 16, gain_db=-6), sound.design("braam", 1.0, 17, gain_db=-6)
    assert a["sha256"] != b["sha256"]
    assert sound.design("braam", 1.0, 16, gain_db=-6)["path"] == a["path"]  # the same request is the same file


def test_a_strided_window_matches_the_full_read(tmp_path):
    import numpy as np
    tifffile = pytest.importorskip("tifffile")  # the geo extras
    from editvideo import period_maps as pm
    img = (np.arange(700 * 900) % 251).astype(np.uint8).reshape(700, 900)
    path = tmp_path / "t.tif"
    tifffile.imwrite(path, img, tile=(256, 256))
    full = pm.read_window(path, 37, 51, 811, 655)
    for k in (2, 3, 5):
        assert (pm.read_window(path, 37, 51, 811, 655, step=k) == full[::k, ::k]).all()


def test_a_licence_written_per_part_is_read_for_the_parts_used():
    from editvideo import ledger
    reel = "picture: Public domain (Universal Newsreel, given to NARA); audio: unknown (the newsreel's music and narration may belong to others)"
    assert ledger.parts(reel)["audio"].startswith("unknown") and ledger.parts("CC BY 4.0") is None
    assert ledger.classify(reel, ("picture",)) == "public_domain"  # a silent use of the picture
    assert ledger.classify(reel) == "unknown" and ledger.classify(reel, ("audio",)) == "unknown"
    silent = "picture: Public domain (US federal government work, US Navy, 17 U.S.C. 105); audio: none (silent)"
    assert ledger.classify(silent) == "public_domain" and ledger.classes(silent, ("audio",)) == {"public_domain"}


def test_nara_rights_decide_picture_and_sound_apart_and_respect_a_restriction():
    from editvideo import ledger, pd_sources as P
    def rec(rg, status, sound):
        return {"naid": 1, "local_id": "X-1", "record_group": rg, "use": {"status": status}, "sound": sound}
    lic, _ = P.nara_rights(rec(428, "Undetermined", "Silent"))  # a Navy film: a federal work, nothing to hear
    assert ledger.classify(lic) == "public_domain" and "17 U.S.C. 105" in lic and "audio: none" in lic
    lic, _ = P.nara_rights(rec(111, "Unrestricted", "Sound"))
    assert ledger.classify(lic, ("audio",)) == "public_domain"
    for rg, status in ((127, "Restricted - Possibly"), ("UN", "Restricted - Possibly"), (263, "Unrestricted"), (None, "Undetermined")):
        lic, why = P.nara_rights(rec(rg, status, "Sound"))  # NARA's own warning, or a group that is not a federal maker
        assert ledger.classify(lic) == "unknown" and why, (rg, status)
    # federal groups hold other makers' films: a network newscast in OSD's RG 330, Hearst's film distributed by USIA
    hearst = {**rec(306, "Unrestricted", "Sound"), "about": "Guardians at the Gate. The film is a Hearst Metrotone News, Inc. production.",
              "makers": [("Distributor", "U.S. Information Agency. (08/01/1953 - 04/01/1978)")]}
    newscast = {**rec(330, "Undetermined", "Sound"), "about": "CBS Evening News, 12.3.1968", "makers": []}
    unnamed = {**rec(330, "Undetermined", "Sound"), "about": "Briefing film", "makers": []}
    made = {**rec(330, "Undetermined", "Sound"), "about": "Briefing film", "makers": [("Producer", "Department of Defense. Office of the Secretary")]}
    for r_ in (hearst, newscast, unnamed):
        assert ledger.classify(P.nara_rights(r_)[0]) == "unknown", r_["about"]
    assert ledger.classify(P.nara_rights(made)[0]) == "public_domain"
    lic, _ = P.nara_rights(rec("UN", "Unrestricted", "Sound"))  # were NARA to lift the newsreel's restriction
    assert ledger.classify(lic, ("picture",)) == "public_domain" and ledger.classify(lic) == "unknown"
    assert P.nara_local_id("428-npc-38421") == "428-NPC-38421" and P.nara_local_id("un-un-v38-r24") == "UN-UN-38-24"
    assert P.nara_local_id("gov.archives.arc.653177") == 653177 and P.nara_local_id("someone_upload") is None


def test_nara_search_keeps_downloadable_films_of_the_years_federal_first(monkeypatch):
    from editvideo import pd_sources as P
    def hit(naid, year, rg, status, files):
        return {"_source": {"record": {"naId": naid, "localIdentifier": f"L-{naid}", "title": f"film {naid}", "productionDates": [{"year": year}],
                                       "ancestors": [{"levelOfDescription": "recordGroup", "recordGroupNumber": rg}], "useRestriction": {"status": status},
                                       "soundType": "Silent", "shotList": "1) LS A-4C launched. VG",
                                       "digitalObjects": [{"objectFilename": f, "objectFileSize": 5_000_000, "objectUrl": f"https://x/{f}"} for f in files]}}}
    asked = []
    def fake(url, timeout=60):
        asked.append(url)
        return {"body": {"hits": {"hits": [hit(1, 1965, 127, "Restricted - Possibly", ["a.mp4"]), hit(2, 1965, 428, "Undetermined", ["b.mp4"]),
                                           hit(3, 1972, 428, "Undetermined", ["c.mp4"]), hit(4, 1965, 428, "Undetermined", ["notes.pdf"])]}}}
    monkeypatch.setattr(P, "_get", fake)
    out = P.nara_search("carrier", 428, (1964, 1968), rows=100)
    assert [x["naid"] for x in out] == [2, 1]  # 1972 and the film without a video file are left out; the restricted one last
    assert "limit=100" in asked[0] and "typeOfMaterials=Moving+Images" in asked[0] and "recordGroupNumber=428" in asked[0]
    assert out[0]["shot_list"].startswith("1) LS") and out[0]["mb"] == 5


def test_a_download_ends_at_the_servers_length_and_resumes_a_dropped_stream(tmp_path, monkeypatch):
    import io
    from editvideo import pd_sources as P
    data, calls = bytes(range(256)) * 40, []  # 10240 bytes; the catalog says one more
    class R(io.BytesIO):
        def __init__(self, body, status=200, length=None):
            super().__init__(body)
            self.status, self.headers = status, {"Content-Length": str(len(data) if length is None else length)}
        def __enter__(self):
            return self
        def __exit__(self, *a):
            self.close()
    def fake(req, timeout=60):
        rng = req.headers.get("Range")
        calls.append((req.get_method(), rng))
        if req.get_method() == "HEAD":
            return R(b"")
        if rng:
            return R(data[int(rng.split("=")[1].rstrip("-")):], 206)
        if len(calls) == 2:  # the first stream drops after 4000 bytes
            r = R(data[:4000])
            return r
        return R(data)
    monkeypatch.setattr(P.urllib.request, "urlopen", fake)
    out = tmp_path / "reel.mp4"
    assert P._download("https://x/reel.mp4", out, size=len(data) + 1) == len(data)
    assert out.read_bytes() == data and calls[-1] == ("GET", "bytes=4000-")


def test_a_cut_between_two_pictures_is_found_inside_pillarbox_bars(tmp_path):
    import subprocess
    import numpy as np
    from editvideo import review
    from editvideo.media import FFMPEG
    # two grey textures with the same histogram, between black bars: the bars alone kept the frames correlated (a cut
    # from NARA's teletype to its operator read 0.86 and went unseen)
    rng = np.random.default_rng(4)
    a, b = (np.clip(110 + rng.normal(0, 12, (90, 120)), 0, 255).astype(np.uint8) for _ in range(2))
    frames = []
    for pic in [a] * 45 + [b] * 45:
        f = np.zeros((90, 160), np.uint8)
        f[:, 20:140] = pic
        frames.append(f)
    clip = tmp_path / "boxed.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "160x90", "-r", "30", "-i", "-",
                    "-vf", "scale=320:180:flags=neighbor", "-pix_fmt", "yuv420p", "-crf", "8", str(clip)], input=b"".join(f.tobytes() for f in frames), check=True)
    r = review.clean_runs(clip)
    assert any(1.3 <= f["t"] <= 1.7 and "jump" in f["why"] for f in r["flags"]), r["flags"]
    assert len(r["runs"]) == 2


def test_a_catalog_page_served_instead_of_json_is_an_error_not_an_empty_result(monkeypatch):
    import io
    from editvideo import pd_sources as P
    class R(io.BytesIO):
        headers = {"Content-Type": "text/html; charset=utf-8"}
        def __enter__(self):
            return self
        def __exit__(self, *a):
            self.close()
    monkeypatch.setattr(P.urllib.request, "urlopen", lambda req, timeout=60: R(b"<!doctype html><html>catalog</html>"))
    with pytest.raises(ValueError, match="web page, not JSON"):
        P.nara_search("carrier")


def test_an_archive_voice_runs_on_to_the_end_of_its_phrase_over_the_next_shots():
    from editvideo import montage
    req = _req()
    req["shots"][2] = {**req["shots"][2], "sound": True, "voice_s": 3.0,  # "I can tell you that some of that action has already taken place."
                       "says": "Một phần hành động đó đã diễn ra rồi.", "says_by": "Robert McNamara · 4.8.1964"}
    req["shots"][3] = {**req["shots"][3], "sound": True}
    r = montage.archive_montage({"width": 1920, "height": 1080}, montage.ArchiveMontage.model_validate(req))
    long_, short = r["sound_plan"]["voices"][:2]
    assert long_["end"] - long_["start"] >= 90  # an L-cut: the line carries over the cut
    slots = r["sound_plan"]["cuts"]
    assert short["end"] in slots or short["end"] - short["start"] < 90  # a voice without voice_s stops with its shot


def test_every_line_the_montage_places_passes_the_reading_time_gate():
    from editvideo import review
    req = _req()
    req["cards"][3] = {**req["cards"][3], "text": "Quân Mỹ tại miền Nam · cuối năm 1967", "hold": 2.0}  # a short hold for a long label
    from editvideo import montage
    r = montage.archive_montage({"width": 1920, "height": 1080}, montage.ArchiveMontage.model_validate(req))
    layers = [o["layer"] for o in r["ops"] if o.get("op") == "add_layer" or "layer" in o]
    assert not review.text_holds({"layers": layers}), review.text_holds({"layers": layers})
    for l in layers:  # and the audit's reading_load (words and characters a second) agrees with every line
        if l["kind"] == "text" and (l.get("text") or "").strip():
            assert l["end_frame"] - l["start_frame"] >= review.reading_frames(l["text"]) or l["id"].endswith(("sc", "-title")), l["id"]


def test_rights_rules_from_the_review_block_what_they_cleared():
    from editvideo import ledger, pd_sources as P
    # a render of a per-part reel joined to a closed part is not cleared by the reel's picture
    reel = "picture: Public domain (US federal government work, US Navy; NARA X); audio: unknown (music)"
    assert ledger.classify(reel + " + All rights reserved", ("picture",)) == "internal_only"
    assert ledger.classify(reel + " + CC BY-NC 4.0", ("picture",)) == "noncommercial"
    def rec(rg, status, makers, about="A film"):
        return {"naid": 1, "local_id": "X-1", "record_group": rg, "use": {"status": status}, "sound": "Sound", "makers": makers, "about": about}
    for maker in ("Republic of Vietnam. Department of Information", "Vietnam People's Army Film Studio"):
        assert ledger.classify(P.nara_rights(rec(306, "Unrestricted", [("Producer", maker)]))[0]) == "unknown", maker
    assert ledger.classify(P.nara_rights(rec(306, "Unrestricted", [("Producer", "U.S. Information Agency")]))[0]) == "public_domain"
    # RG 200 is the Gift Collection: a company's film there is not the Universal Newsreel
    assert ledger.classify(P.nara_rights(rec(200, "Unrestricted", [("Producer", "Ford Motor Company")]))[0], ("picture",)) == "unknown"


def test_the_mirror_defers_to_the_national_archives_record(tmp_path, monkeypatch):
    from editvideo import ledger, pd_sources as P, store
    md = {"identifier": "un-un-v38-r24", "title": "Marines land", "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/", "description": "Marines land."}
    monkeypatch.setattr(P, "item", lambda i: {"metadata": md, "videos": [{"name": "a.mp4", "size": 10, "url": "https://x/a.mp4"}]})
    monkeypatch.setattr(P, "_download", lambda url, path, size=None, **k: 10)
    monkeypatch.setattr(P, "nara_record", lambda naid=None, local_id=None: {"naid": 234274907, "local_id": "UN-UN-38-24", "record_group": "UN",
                                                                           "use": {"status": "Restricted - Possibly"}, "sound": "Sound", "makers": [], "about": ""})
    got = {}
    monkeypatch.setattr(ledger, "register_source", lambda path, lic, credit, url, title, notes="": got.update(lic=lic) or {"license": lic})
    monkeypatch.setattr(store, "DATA", tmp_path / "store")
    e = P.fetch("un-un-v38-r24")
    assert ledger.classify(got["lic"]) == "unknown" and e["check"]["nara"]["use"]["status"] == "Restricted - Possibly"


def test_a_spoken_line_is_subtitled_while_it_plays_and_cannot_run_on_untranslated():
    from editvideo import montage, review
    req = _req()
    req["shots"][1] = {**req["shots"][1], "sound": True, "says": "Một phần hành động đó đã diễn ra rồi.", "says_by": "Robert McNamara · 4.8.1964"}
    r = montage.archive_montage({"width": 1920, "height": 1080}, montage.ArchiveMontage.model_validate(req))
    layers = [o["layer"] for o in r["ops"]]
    sub = next(l for l in layers if l["kind"] == "text" and "đã diễn ra" in (l.get("text") or ""))
    shot = next(l for l in layers if l["kind"] == "video" and l.get("asset_id") == "a1")
    assert sub["start_frame"] == shot["start_frame"] and not review.text_holds({"layers": layers})
    with pytest.raises(ValueError, match="says"):
        montage.Shot.model_validate({"asset_id": "x", "duration": 4.0, "sound": True, "voice_s": 3.0})


def test_a_dated_card_waits_for_footage_between_the_dates_either_side_of_it():
    from editvideo import montage
    req = _req()
    req["shots"][6] = {**req["shots"][6], "date": "11.2.1965", "place": "Biển Đông"}
    req["shots"][9] = {**req["shots"][9], "date": "15.4.1965", "place": "Huế"}
    req["cards"] = [{"kind": "counter", "at": 0.5, "text": "Quân Mỹ tại miền Nam · cuối năm 1965", "value_from": 23300, "value_to": 184300}]
    r = montage.archive_montage({"width": 1920, "height": 1080}, montage.ArchiveMontage.model_validate(req))
    layers = [o["layer"] for o in r["ops"]]
    counter = next(l for l in layers if l["kind"] == "counter")
    hue = next(l for l in layers if l["kind"] == "video" and l.get("asset_id") == "a9")
    assert counter["start_frame"] >= hue["start_frame"]  # never between February and April 1965


def test_a_reels_sound_counts_when_it_becomes_the_narration(tmp_path, monkeypatch):
    """A project made from a reel whose picture is free and whose sound is not must not come out clear for online use."""
    import subprocess
    from editvideo import agent, ledger, resources, store
    from editvideo.media import FFMPEG
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize()
    monkeypatch.setattr(resources, "CATALOG", tmp_path / "catalog.json")
    monkeypatch.setattr(resources, "SHA_CACHE", tmp_path / "sha-cache.json")
    reel = tmp_path / "reel.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2",
                    "-shortest", "-pix_fmt", "yuv420p", "-c:a", "aac", str(reel)], check=True)
    ledger.register_source(reel, "picture: Public domain (US federal government work); audio: All rights reserved (network narration)",
                           "US National Archives", "https://catalog.archives.gov/id/1", "Newsreel")
    p = agent.from_video(str(reel))
    L = ledger.project_ledger(p["id"], "online", write=False)
    voice = next(r for r in L["rows"] if r.get("used") == ["audio"])
    assert voice["class"] == "internal_only" and L["verdict"] == "blocked"
    assert any("Newsreel" in (c.get("works") or [""])[0] or c["credit"] == "US National Archives" for c in resources.project_credits(p["id"])["credits"])


def test_a_long_montage_keeps_its_clock_and_riser_running_into_the_suck_out(tmp_path, monkeypatch):
    from editvideo import montage, store
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    req = _req()
    req["end_frame"] = 3750  # a 125 s montage: beds are at most 60 s long
    body, hit = req["shots"][:-1], req["shots"][-1]
    req["shots"] = body + [{**x, "asset_id": x["asset_id"] + "b", "date": "", "place": ""} for x in body[:50]] + [hit]
    r = montage.archive_montage({"width": 1920, "height": 1080}, montage.ArchiveMontage.model_validate(req))
    plan = r["sound_plan"]
    clips = montage.score(plan, music=None)
    for k in ("clock", "shepard"):
        c = next(c for c in clips if c.get("kind") == k)
        assert abs(c["end_frame"] - plan["suck_out"][0]) <= 2, (k, c["end_frame"], plan["suck_out"])


def test_a_silent_project_is_not_blocked_by_its_own_silence(tmp_path, monkeypatch):
    from editvideo import agent, ledger, resources, store
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize()
    monkeypatch.setattr(resources, "CATALOG", tmp_path / "catalog.json")
    monkeypatch.setattr(resources, "SHA_CACHE", tmp_path / "sha-cache.json")
    p = agent.create_silent("landscape", 60)
    L = ledger.project_ledger(p["id"], "online", write=False)
    assert L["verdict"] == "clear", [(r["name"], r["class"]) for r in L["rows"]]
    assert not resources.project_credits(p["id"])["unrecorded_assets"]
