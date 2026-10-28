"""Round 4: dialogue senses/hands, ad structure, punch-ins, film halation/grain, focus_zoom cut."""
import importlib.util
import json
import subprocess
from pathlib import Path
import numpy as np
import pytest
from editvideo import store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    return tmp_path


def _mod(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    d = tmp_path_factory.mktemp("speech")
    truth = _mod("synth_speech").make(str(d / "s.wav"), seed=2, hum=True)
    return str(d / "s.wav"), truth


def test_read_dialogue_regions_speakers_fillers(speech, workspace):
    from editvideo import dialogue
    path, truth = speech
    r = dialogue.read(path)
    m = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
    assert len(r["speakers"]) == 2 and r["fillers"]["count"] == len(truth["fillers"])
    for f, tf in zip(sorted(m["fillers"], key=lambda x: x["start"]), truth["fillers"]):
        assert abs(f["start"] - tf["start"]) < .06
    fill = {f["start"] for f in m["fillers"]}
    found = [s for s in m["segments"] if s["start"] not in fill]
    assert len(found) == len(truth["regions"])
    for s, t in zip(found, truth["regions"]):
        assert abs(s["start"] - t["start"]) < .06 and abs(s["end"] - t["end"]) < .08  # boundaries within ~2 frames
    mapping = {}
    for s, t in zip(found, truth["regions"]):
        mapping.setdefault(t["speaker"], set()).add(s["speaker"])
    assert all(len(v) == 1 for v in mapping.values()) and mapping["A"] != mapping["B"]  # consistent, distinct labels


def test_audio_profile_hum_and_clean_deltas(speech, workspace):
    from editvideo import dialogue
    path, _ = speech
    p = dialogue.profile(path)
    assert p["hum"] and p["hum_db_over_neighbours"]["50"] > 20
    c = dialogue.clean(path, "medium")
    d = c["delta"]
    assert d["snr_db"] > 6 and d["hum_db"] < -15 and abs(d["sibilance_index_db"]) < 3 and not d["warnings"]


def test_condense_plan_hits_measured_pause_targets(speech, workspace):
    from editvideo import dialogue
    path, truth = speech
    r = dialogue.read(path)
    m = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
    keep, nf = dialogue.plan_condense(m, .5, .3, True)
    assert nf == len(truth["fillers"])
    assert all(b > a for a, b in keep) and all(k2[0] >= k1[1] for k1, k2 in zip(keep, keep[1:]))
    kept_speech = [s for s in m["segments"] if s["start"] not in {f["start"] for f in m["fillers"]}]
    for s in kept_speech:  # every word is kept whole
        assert any(a <= s["start"] + 1e-6 and s["end"] - 1e-6 <= b for a, b in keep)
    for f in m["fillers"]:  # fillers are gone
        assert not any(a <= f["start"] and f["end"] <= b for a, b in keep)


def test_condense_builds_an_aligned_project(speech, workspace):
    from editvideo import dialogue, agent
    path, truth = speech
    mp4 = Path(path).with_suffix(".mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=320x180:r=30:d={truth['duration']:.3f}", "-i", path,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mp4)], check=True)
    r = dialogue.condense(str(mp4), dry_run=False, cover="punch_in", title="t")
    assert r["removed_s"] > 4 and r["pauses_after"]["max_s"] <= .5
    t = agent.read(r["project_id"])["timeline"]
    assert t["total_frames"] == r["frames"] and len(t["shots"]) == r["shots"]
    assert all(a["end_frame"] == b["start_frame"] for a, b in zip(t["shots"], t["shots"][1:]))
    zoomed = [s for s in t["shots"] if any(e["name"] == "focus_zoom" and e["params"].get("cut") for e in s.get("effects") or [])]
    assert len(zoomed) == len(t["shots"]) // 2
    again = dialogue.read(store.folder(r["project_id"]) / "plan" / "voice.wav")
    assert again["pause_stats"]["max_s"] < .7  # the assembled voice really has the short pauses


def test_ad_plan_matches_measured_commercial_and_punch_in(workspace):
    from editvideo import ads
    p = ads.plan(28.7, "brand_promo")
    by = {s["section"]: s for s in p["sections"]}
    assert abs(by["offer_1"]["start"] - 8.8) < .5 and abs(by["offer_main"]["start"] - 14.8) < .5 and abs(by["cta_end_card"]["start"] - 25.3) < .5
    assert p["sections"][-1]["end"] == 28.7
    h = ads.plan(20)
    assert h["sections"][-1]["end"] - h["sections"][-1]["start"] >= 2.5


def test_punch_in_splits_and_holds_zoom(workspace, monkeypatch):
    from editvideo import ads, agent
    shots = [{"id": "a", "beat_id": "b", "start_frame": 0, "end_frame": 300, "asset_id": "x", "source_start": 1.0}]
    t = {"shots": shots, "layers": [], "total_frames": 300, "width": 1920, "height": 1080}
    sent = {}
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 3, "timeline": t})
    monkeypatch.setattr(agent, "patch", lambda pid, rev, ops: sent.update(ops=ops) or {"revision": rev + 1})
    words = [{"word": "a", "start": 0.0, "end": 1.0}, {"word": "b", "start": 1.5, "end": 2.0}, {"word": "c", "start": 2.1, "end": 2.5}, {"word": "d", "start": 3.0, "end": 3.4}]
    r = ads.punch_in("p", 3, words=words, min_gap_s=.5)
    new = sent["ops"][0]["timeline"]["shots"]
    assert [p_["frame"] for p_ in r["placed"]] == [45, 90] and len(new) == 3
    assert new[1]["source_start"] == pytest.approx(1.0 + 45 / 30) and new[1]["effects"][0]["params"]["cut"] is True
    assert new[1]["effects"][0]["params"]["amount"] == pytest.approx(.14)


def test_focus_zoom_cut_halation_and_grain_gauge(tmp_path):
    src = tmp_path / "fx.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    js = r"""const FX=require(process.argv[1]);const L={kind:'video',effects:[{name:'focus_zoom',start_frame:0,end_frame:1,params:{amount:.14,cut:true,focus_x:.51,focus_y:.31}}]};
    const H=FX.composite({id:'h',kind:'video',x:0,y:0,width:1,height:1,effects:[{name:'halation',start_frame:0,end_frame:1,params:{}}]},2,2,{});
    const g16=FX.widget({id:'g',kind:'film',data:{type:'grain',gauge:16}},3),g35=FX.widget({id:'g',kind:'film',data:{type:'grain',gauge:35}},3);
    console.log(JSON.stringify({f0:FX.styleAt(L,0),h:H.style._keyFilter,bad:/NaN|undefined/.test(H.defs),g16:g16.match(/baseFrequency="([\d.]+)"/)[1],g35:g35.match(/baseFrequency="([\d.]+)"/)[1],
      o16:+g16.match(/opacity="([\d.]+)"/)[1],o35:+g35.match(/opacity="([\d.]+)"/)[1]}));"""
    r = json.loads(subprocess.check_output(["node", "-e", js, str(src)], text=True))
    sx = float(r["f0"]["transform"].split("scale(")[1].split(")")[0].split(",")[0])
    assert sx == pytest.approx(1.14) and r["f0"]["transformOrigin"] == "51% 31%"  # punched on the very first frame
    assert r["h"] == "url(#ev-fx-h-0)" and not r["bad"]
    assert float(r["g16"]) < float(r["g35"]) and r["o16"] > r["o35"]  # 16 mm: bigger, stronger grain


def test_event_profile_classifies_cuts_punches_and_pops(tmp_path, workspace):
    import cv2
    from editvideo import study
    W, H = 640, 360
    def scene(seed):
        r = np.random.default_rng(seed)
        img = cv2.GaussianBlur((r.random((H, W, 3)) * 255).astype(np.uint8), (0, 0), 4)
        for _ in range(25):
            cv2.circle(img, (int(r.uniform(0, W)), int(r.uniform(0, H))), int(r.uniform(8, 40)), tuple(int(v) for v in r.integers(0, 255, 3)), -1)
        return img
    zoom = lambda img, s: cv2.warpAffine(img, np.float32([[s, 0, (1 - s) * .51 * W], [0, s, (1 - s) * .31 * H]]), (W, H))
    frames, base, z, pop = [], scene(0), 1.0, False
    for kind, v in [("hold", 40), ("cut", 1), ("hold", 35), ("punch", 1.14), ("hold", 40), ("pop", 1), ("hold", 30), ("cut", 2), ("hold", 30)]:
        if kind == "hold":
            for _ in range(v):
                img = zoom(base, z) if z != 1 else base.copy()
                if pop:
                    cv2.rectangle(img, (40, 280), (300, 330), (255, 255, 255), -1)
                frames.append(img)
        elif kind == "cut":
            base, z, pop = scene(v * 11), 1.0, False
        elif kind == "punch":
            z = v
        else:
            pop = True
    p = tmp_path / "e.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", "30", "-i", "-", "-c:v", "libx264", "-crf", "16",
                    "-pix_fmt", "yuv420p", str(p)], input=np.stack(frames).tobytes(), check=True)
    r = study.event_profile(str(p))
    ev = json.loads(Path(r["manifest"]).read_text())["events"]
    assert [e["kind"] for e in ev] == ["cut", "punch_in", "overlay_pop", "cut"]
    assert ev[1]["scale"] == pytest.approx(1.14, abs=.01) and ev[1]["fixed_point"] == pytest.approx([.51, .31], abs=.02)


def test_motion_quality_flags_linear_abrupt_and_twins(workspace, monkeypatch):
    from editvideo import motion_quality, agent
    lin = {"id": "lin", "kind": "shape", "start_frame": 0, "end_frame": 60, "x": .1, "y": .1, "width": .1, "height": .1,
           "keyframes": {"x": [{"frame": 0, "value": 0}, {"frame": 30, "value": 400, "easing": "linear"}]}}
    eased = {**lin, "id": "eased", "keyframes": {"x": [{"frame": 0, "value": 0}, {"frame": 30, "value": 400, "easing": "ease_in_out"}],
                                               "y": [{"frame": 0, "value": 0}, {"frame": 30, "value": 200, "easing": "ease_out"}]}}
    twin = {**lin, "id": "twin"}
    t = {"layers": [lin, eased, twin], "width": 1920, "height": 1080}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t})
    r = motion_quality.audit("p")
    codes = {(f["code"], f["where"]) for f in r["findings"]}
    assert ("mechanical_move", "lin") in codes and ("abrupt_stop", "lin") in codes
    assert not any(w == "eased" for c, w in codes if c in ("mechanical_move", "abrupt_stop", "straight_path"))
    assert any(c == "twinning" and "lin" in w and "twin" in w for c, w in codes)
