"""The map_matte and dossier montage forms: honest claims in the schema, no cut, one camera path shared by every map
layer, footage only inside its region, the dossier's macro travel, its marks drawn as the camera reaches them."""
import pytest
from editvideo import montage_forms as mf, store

T = {"width": 1920, "height": 1080}


def _map(**kw):
    req = {"recipe": "map_matte", "id": "mm", "start_frame": 0, "end_frame": 900, "country": "Vietnam", "neighbors": ["Laos"],
           "focus": [15.0, 107.0, 1.6], "dates": ["1.1965", "12.1966"], "sides": {"south": "#6f93bd", "north": "#c8a35a"},
           "regions": [{"name": "Miền Bắc", "country": "Vietnam", "lat_range": [17.0, 90], "side": "north"},
                       {"name": "Miền Nam", "country": "Vietnam", "lat_range": [-90, 17.0], "side": "south", "places": ["Huế", "Tây Ninh"],
                        "footage": [{"asset_id": "a1", "duration": 5, "date": "4.1965", "place": "Huế"},
                                    {"asset_id": "a2", "duration": 5, "date": "4.1966", "place": "Tây Ninh"}]}],
           "events": [{"lat": 16.07, "lon": 108.22, "date": "8.3.1965", "label": "Đà Nẵng", "source": "USMC History Division"},
                      {"lat": 16.46, "lon": 107.59, "date": "12.1966", "source": "USMC History Division", "keep": True}]}
    req.update(kw)
    return mf.MapMatte.model_validate(req)


def test_map_matte_refuses_footage_claimed_for_a_place_or_time_it_was_not_shot():
    with pytest.raises(ValueError, match="cannot play inside"):
        _map(regions=[{"name": "Miền Nam", "country": "Vietnam", "lat_range": [-90, 17], "side": "south",
                       "footage": [{"asset_id": "a1", "duration": 5, "date": "4.1965", "place": "Hà Nội"}]}])
    with pytest.raises(ValueError, match="outside the clock"):
        _map(regions=[{"name": "Miền Nam", "country": "Vietnam", "lat_range": [-90, 17], "side": "south", "places": ["Huế"],
                       "footage": [{"asset_id": "a1", "duration": 5, "date": "1975", "place": "Huế"}]}])
    with pytest.raises(ValueError, match="source"):
        _map(events=[{"lat": 16, "lon": 108, "date": "3.1965"}])
    with pytest.raises(ValueError, match="not among sides"):
        _map(sides={"north": "#c8a35a"})


def test_map_matte_plays_footage_inside_its_region_on_one_camera_path():
    r = mf.map_matte(T, _map())
    layers = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    assert r["measurements"]["cuts"] == 0 and r["measurements"]["footage"] == 2
    videos = [l for l in layers.values() if l["kind"] == "video"]
    # footage is cut to its region's shape (a hidden track matte that moves with the map) and covers it: the region's
    # outline at the clip's middle frame lies inside the clip's box
    for v, chk in zip(videos, r["sound_plan"]["checks"]):
        src = layers[v["matte"]["source"]]
        assert src["kind"] == "svg" and src["start_frame"] <= v["start_frame"] and src["end_frame"] >= v["end_frame"]
        assert all(v["x"] - 1e-3 <= x <= v["x"] + v["width"] + 1e-3 and v["y"] - 1e-3 <= y <= v["y"] + v["height"] + 1e-3 for x, y in chk["polygon"])
    # one camera: a null carries the keys, the map, the mattes and the labels ride it (no copy of the keys per layer)
    cam = layers["mm-cam"]
    assert cam["kind"] == "null" and set(cam["keyframes"]) == {"scale", "x", "y"}
    riders = [l for l in layers.values() if l["kind"] == "svg"]
    assert riders and all(l.get("parent") == "mm-cam" and not l.get("keyframes") for l in riders)
    # the drain: the kept event lights again over the darkening map, the clock walks forward, the sound plan is timed
    kept = layers["mm-kept"]["data"]["elements"]
    assert any(e["appear"][0] >= r["sound_plan"]["drain"][0] for e in kept)
    assert [l["text"] for l in layers.values() if l["id"].startswith("mm-clk") and l["kind"] == "text"] == ["1965", "1966"]
    assert len(r["sound_plan"]["events"]) == 2 and r["sound_plan"]["drain"][1] == 900


def _dossier(**kw):
    req = {"recipe": "dossier", "id": "ds", "start_frame": 0, "end_frame": 600,
           "items": [{"asset_id": "d1", "date": "4.8.1964", "source": "JCS · NARA", "caption": "Điện", "underline": [[.05, .4, .3], [.45, .6, .35]]},
                     {"asset_id": "p1", "kind": "photo", "date": "4.8.1964", "source": "NARA 192482", "travel": "in", "focus": [.47, .25]},
                     {"asset_id": "d2", "date": "10.8.1964", "source": "PL 88-408", "underline": [[.3, .45, .36]], "climax": True}],
           "title": "Vịnh Bắc Bộ"}
    req.update(kw)
    return mf.Dossier.model_validate(req)


def test_dossier_marks_withheld_passages_only_sparingly_and_on_documents():
    doc = lambda k: {"asset_id": f"d{k}", "date": "1964", "source": "NARA", "withheld": [[.1, .2, .3, .02]]}
    with pytest.raises(ValueError, match="at most two"):
        _dossier(items=[doc(1), doc(2), doc(3)])
    with pytest.raises(ValueError, match="released document"):
        _dossier(items=[doc(1), {"asset_id": "p", "kind": "photo", "date": "1964", "source": "NARA", "withheld": [[.1, .2, .3, .02]]}])
    with pytest.raises(ValueError, match="year"):
        _dossier(items=[doc(1), {"asset_id": "p", "date": "August", "source": "NARA"}])


def test_dossier_travels_close_over_the_page_and_draws_each_mark_as_the_camera_reaches_it(monkeypatch):
    sizes = {"d1": (720, 945), "p1": (1920, 1937), "d2": (3840, 5762)}
    monkeypatch.setattr(store, "find_asset", lambda pid, aid: {"id": aid, "kind": "image", "width": sizes[aid][0], "height": sizes[aid][1]})
    r = mf.dossier(T, "pid", _dossier())
    layers = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    page = layers["ds-p0"]
    assert page["height"] > 1.2 and page["width"] <= 1.0      # close enough to read the type: the sheet is taller than the frame
    ys = [k["value"] for k in page["keyframes"]["y"]]
    assert ys[-1] < ys[0]                                      # it slides up: the camera travels down the page
    marks = layers["ds-p0marks"]["data"]["elements"]
    assert marks[0]["draw"][0] < marks[1]["draw"][0]           # the upper line is reached first
    soft = layers["ds-p0soft"]
    assert soft["masks"][1]["mode"] == "subtract" and soft["masks"][1]["keyframes"][0]["geom"] != soft["masks"][1]["keyframes"][-1]["geom"]
    photo = layers["ds-p1"]
    assert photo["height"] <= .85 and photo["keyframes"]["scale"][-1]["value"] > 1.1  # a photograph: whole, pushed into
    # one caption at a time: each leaves before the next comes up
    caps = sorted((l["start_frame"], l["end_frame"]) for k, l in layers.items() if k.startswith("ds-c") and k[4:].isdigit())
    assert all(b0 <= a1 for (_, b0), (a1, _) in zip(caps, caps[1:]))
    plan = r["sound_plan"]
    assert len(plan["marks"]) == 3 and plan["climax"] < plan["whiteout"] < plan["end"]
    assert r["measurements"]["withheld_items"] == 0


def test_dossier_asks_for_the_time_its_items_need(monkeypatch):
    sizes = {"d1": (720, 945), "p1": (1920, 1937), "d2": (3840, 5762)}
    monkeypatch.setattr(store, "find_asset", lambda pid, aid: {"id": aid, "kind": "image", "width": sizes[aid][0], "height": sizes[aid][1]})
    with pytest.raises(ValueError, match=r"3 items need >= \d+\.\d s"):
        mf.dossier(T, "pid", _dossier(end_frame=330))


def test_map_matte_checks_a_place_given_as_a_point_and_spreads_an_empty_clock():
    reg = lambda at: [{"name": "Miền Nam", "country": "Vietnam", "lat_range": [-90, 17.0], "side": "south", "places": ["Hà Nội"],
                       "footage": [{"asset_id": "a1", "duration": 5, "date": "4.1965", "place": "Hà Nội", "at": at}]}]
    with pytest.raises(ValueError, match="lies outside"):
        mf.map_matte(T, _map(regions=reg([21.03, 105.85])))   # Hà Nội named among the South's places is still in the North
    # three events bunched at the end of four years: an even clock leaves the map empty for most of it
    ev = [{"lat": 16.5, "lon": 107.5, "date": d, "source": "CMH"} for d in ("1.1968", "2.1968", "3.1968")]
    req = dict(dates=["1.1965", "3.1968"], regions=[{"name": "Miền Nam", "country": "Vietnam", "lat_range": [-90, 17.0], "side": "south"}], events=ev)
    even = mf.map_matte(T, _map(clock_warp=0, **req))
    warped = mf.map_matte(T, _map(clock_warp=.7, **req))
    assert warped["measurements"]["longest_empty_s"] < even["measurements"]["longest_empty_s"]
    assert any("nothing new on the map" in n for n in even["notes"])


def test_map_matte_labels_keep_clear_and_inside_the_frame():
    ev = [{"lat": 16.65, "lon": 106.73, "date": "1.1966", "label": "Khe Sanh", "source": "USMC"},
          {"lat": 16.46, "lon": 107.59, "date": "1.1966", "label": "Huế", "source": "USMC"}]
    r = mf.map_matte(T, _map(events=ev, focus=[16.5, 107.0, 2.5]))
    texts = [o["layer"] for o in r["ops"] if o["layer"]["id"].startswith("mm-el")]
    assert len(texts) == 2
    a, b = (t["data"]["elements"][0] for t in texts)
    assert (a["x"], a["y"], a["anchor"]) != (b["x"], b["y"], b["anchor"])   # the second name took another side


def _scan(path, rows):
    """A fake typed page: dark rows of 'type' (8 px high) at the given page fractions, cream paper elsewhere."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (800, 1000), 228)
    d = ImageDraw.Draw(im)
    for y in rows:
        d.rectangle([60, int(y * 1000) - 8, 740, int(y * 1000)], fill=30)
    d.rectangle([100, 700, 500, 718], fill=10)               # a black bar the release left
    im.save(path)


def test_dossier_underlines_sit_in_the_gap_and_withheld_must_be_dark(tmp_path):
    f = tmp_path / "scan.png"
    _scan(f, [.30, .32, .34, .36])
    u, w = mf._check_marks(str(f), [[.1, .322, .5]], [[.125, .7, .5, .018]], "s")
    assert .3205 < u[0][1] < .3315                              # under the .32 line (rows 312-320), above the next (332-340)
    with pytest.raises(ValueError, match="not a black bar"):
        mf._check_marks(str(f), [], [[.1, .4, .5, .02]], "s")
    g = tmp_path / "tight.png"
    from PIL import Image, ImageDraw
    im = Image.new("L", (800, 1000), 228)
    ImageDraw.Draw(im).rectangle([60, 290, 740, 350], fill=30)  # type with no gap at all
    im.save(g)
    with pytest.raises(ValueError, match="cross the next line|no line of type"):
        mf._check_marks(str(g), [[.1, .32, .5]], [], "s")


def test_dossier_draws_its_last_mark_well_before_the_dissolve(monkeypatch):
    sizes = {"d1": (720, 945), "p1": (1920, 1937), "d2": (3840, 5762)}
    monkeypatch.setattr(store, "find_asset", lambda pid, aid: {"id": aid, "kind": "image", "width": sizes[aid][0], "height": sizes[aid][1]})
    r = mf.dossier(T, "pid", _dossier(items=[{"asset_id": "d1", "date": "4.8.1964", "source": "JCS - NARA", "underline": [[.05, .2, .3], [.45, .85, .35]]},
                                             {"asset_id": "d2", "date": "10.8.1964", "source": "PL 88-408"}], end_frame=420))
    layers = {o["layer"]["id"]: o["layer"] for o in r["ops"]}
    p0 = layers["ds-p0"]
    last = max(e["draw"][1] for e in layers["ds-p0marks"]["data"]["elements"])
    dissolve = p0["end_frame"] - p0["start_frame"] - 15
    assert dissolve - last >= 25


def test_the_master_keeps_a_crescendo_when_only_its_peaks_block_linear_loudnorm(tmp_path):
    """A quiet bed rising 12 dB to a hit: loudnorm's linear pass cannot lift it to -18 LUFS without the hit's peaks
    passing the true-peak target, so it fell back to its dynamic mode and flattened the rise (LRA 16.7 -> 5.3). A plain
    gain into the limiter keeps it."""
    import json, re, subprocess
    import numpy as np
    from editvideo import renderer
    from editvideo.media import FFMPEG
    from editvideo.models import AudioMix
    src = tmp_path / "mix.wav"
    expr = "(0.012*between(t,0,6)+0.024*between(t,6,12)+0.048*between(t,12,18))*sin(2*PI*220*t)+0.7*sin(2*PI*900*t)*between(t,18,18.05)"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d=20", "-ac", "2", str(src)], check=True)
    master = AudioMix(target_lufs=-18.0, true_peak_db=-1.5, loudness_range=20)
    log = subprocess.run([FFMPEG, "-v", "info", "-i", str(src), "-af", "loudnorm=I=-18:TP=-1.5:LRA=20:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    measured = json.loads(re.search(r'\{\s*"input_i".*?\}', log, re.S).group())
    assert renderer.linear_gain(master, measured)
    out = tmp_path / "master.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-af", renderer.master_filter(master, measured), "-ar", "48000", str(out)], check=True)
    x = np.frombuffer(subprocess.run([FFMPEG, "-v", "error", "-i", str(out), "-f", "f32le", "-"], capture_output=True).stdout, np.float32)[::2]  # one channel
    db = lambda a, b: 20 * np.log10(np.sqrt(np.mean(x[int(a * 48000):int(b * 48000)] ** 2)))
    assert db(13, 17) - db(1, 5) >= 11                        # the 12 dB climb survives
    assert 20 * np.log10(np.abs(x).max()) <= -1.9              # and the hit stays under the true-peak target
