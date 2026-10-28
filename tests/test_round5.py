"""Round 5: multicam sync/switching, room tone, aspect adaptation, follow-through, product scene, tracked windows,
typewriter script."""
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


def _fx(tmp_path, code, *args):
    src = tmp_path / "fx.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    return json.loads(subprocess.check_output(["node", "-e", "const FX=require(process.argv[1]);" + code, str(src), *args], text=True))


def test_multicam_syncs_and_switches_on_turns(tmp_path, workspace):
    from editvideo import multicam, agent
    truth = _mod("synth_speech").make(tmp_path / "s.wav", seed=2)
    paths = _mod("synth_multicam").make(tmp_path, tmp_path / "s.wav", truth, offsets=(0.0, .73, 1.41))
    angles = [{"path": str(paths["wide"]), "kind": "wide"}, {"path": str(paths["camA"]), "kind": "single"}, {"path": str(paths["camB"]), "kind": "single"}]
    r = multicam.build(angles, dry_run=False, title="mc")
    assert abs(r["offsets_s"][1] - .73) < 1 / 30 and abs(r["offsets_s"][2] - 1.41) < 1 / 30
    assert set(r["speakers_to_angles"].values()) == {1, 2}
    t = agent.read(r["project_id"])["timeline"]
    shots = t["shots"]
    assert shots[0]["start_frame"] == 0 and all(a["end_frame"] == b["start_frame"] for a, b in zip(shots, shots[1:]))
    assert all(s["end_frame"] - s["start_frame"] >= 75 for s in shots[1:-1])
    assert len({s["asset_id"] for s in shots}) == 3  # every angle used
    turns = [round(x["start"] * 30) for a, x in zip([None] + truth["regions"], truth["regions"]) if a is None or a["speaker"] != x["speaker"]]
    for s in shots[1:]:
        assert any(-30 <= ft - s["start_frame"] <= 90 for ft in turns)  # cuts sit at (or held shortly after) a turn


def test_room_tone_matches_the_floor(tmp_path, workspace):
    from editvideo import dialogue
    _mod("synth_speech").make(tmp_path / "s.wav", seed=3)
    r = dialogue.room_tone(str(tmp_path / "s.wav"), 4)
    assert abs(r["level_db"] - r["floor_db"]) < 3 and r["seconds"] == pytest.approx(4, abs=.05)


def test_follow_through_lags_then_overshoots(tmp_path):
    r = _fx(tmp_path, r"""const body={id:'body',kind:'shape',start_frame:0,end_frame:90,x:.4,y:.5,width:.1,height:.1,keyframes:{x:[{frame:0,value:0},{frame:5,value:134,easing:'linear'}]}};
    const ant={id:'ant',kind:'shape',start_frame:0,end_frame:90,x:.44,y:.38,width:.02,height:.12,anchor:[.5,1],parent:'body',follow:{preset:'stiff',period_frames:null}};
    const byId={body,ant},out=[];for(let f=0;f<40;f++){const m=FX.composite(ant,f,f,{byId,W:1920,H:1080}).style.transform.match(/matrix\(([^)]*)\)/)[1].split(',').map(Number);out.push(Math.atan2(m[1],m[0])*180/Math.PI);}
    console.log(JSON.stringify(out));""")
    assert min(r[1:6]) < -8  # bent back while moving
    after = r[5:20]
    assert max(after) > 3 and abs(r[39]) < 1  # overshoots past rest after the stop, then settles


def test_product_scene_and_scene3d_light_keys():
    from editvideo import scene3d
    scene, beats = scene3d.product_scene(180)
    assert beats["slide_in"] == [0, 40] and beats["turn_from"] == 60 and beats["light_sweep"][0] > beats["rock_settle"][1]
    spot = next(l for l in scene["lights"] if l["kind"] == "spot")
    assert spot["keyframes"][0]["intensity"] == 0 and max(k["intensity"] or 0 for k in spot["keyframes"]) > 10
    rot = [k["rotation"]["z"] for k in scene["objects"][0]["keyframes"][1:]]
    assert rot[0] > 0 > rot[1] and abs(rot[2]) < abs(rot[1]) and rot[3] == 0  # rock decays to rest
    with pytest.raises(ValueError):
        scene3d.Scene3D.model_validate({"objects": [{"id": "a"}], "lights": [{"kind": "spot", "keyframes": [{"frame": 5}, {"frame": 5}]}]})


def test_tracked_window_follows_a_region_track(workspace, monkeypatch):
    from editvideo import windows, agent
    sent = {}
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 2, "timeline": {}})
    monkeypatch.setattr(agent, "patch", lambda pid, rev, ops: sent.update(ops=ops) or {"revision": rev + 1})
    track = {"tracks": [{"local_frame": f, "region": [.1 + f * .002, .2, .2 + f * .002, .4]} for f in range(0, 150, 4)]}
    r = windows.tracked_window("p", 2, track, 30, mode="blur")
    L = sent["ops"][0]["layer"]
    keys = L["masks"][0]["keyframes"]
    assert L["kind"] == "adjust" and L["data"]["blur"] >= 18 and L["start_frame"] == 30
    assert keys[0]["geom"][0] == pytest.approx(.15, abs=1e-3) and keys[-1]["geom"][0] > keys[0]["geom"][0] and len(keys) <= 60
    sp = windows.tracked_window("p", 2, track, 0, mode="spotlight", dry_run=True)
    assert sp["dry_run"]


def test_typewriter_script_and_cursor(tmp_path):
    r = _fx(tmp_path, r"""const L={kind:'text',text:'x',effects:[{name:'typewriter',start_frame:0,end_frame:100,params:{script:['Hello world','Hello there'],cursor:true,cps:20,hold:10}}]};
    const strip=h=>h.replace(/<span[^>]*><\/span>/,'');console.log(JSON.stringify([0,6,20,30,45].map(f=>strip(FX.widget(L,f)))));""")
    assert r == ["", "Hell", "Hello world", "Hello w", "Hello there"]
    from editvideo.effects import validate_effect
    with pytest.raises(ValueError):
        validate_effect("typewriter", {"script": "not a list"})


def test_aspect_adapt_keeps_layers_in_frame(workspace):
    from editvideo import aspect, agent
    import importlib
    tp = importlib.import_module("test_agent")
    pid = tp.planned()
    p = agent.read(pid)
    agent.patch(pid, p["revision"], [{"op": "upsert_layer", "layer": {"id": "title", "kind": "text", "text": "PERSEVERANCE", "start_frame": 0, "end_frame": 30,
                                                                       "x": .05, "y": .4, "width": .9, "height": .2, "font_size": 200, "font_id": "oswald", "font_weight": 700}},
                                     {"op": "upsert_layer", "layer": {"id": "foot", "kind": "text", "text": "a b", "start_frame": 0, "end_frame": 30, "x": .3, "y": .92, "width": .4, "height": .05}}])
    r = aspect.adapt(pid, "portrait45")
    t = agent.read(r["project_id"])["timeline"]
    assert (t["width"], t["height"]) == (1080, 1350)
    for l in t["layers"]:
        assert l["x"] >= 0 and l["y"] >= 0 and l["x"] + l["width"] <= 1.0001 and l["y"] + l["height"] <= 1.0001
    title = next(l for l in t["layers"] if l["id"] == "title")
    from editvideo.design_library import layout_text
    w = layout_text("oswald", "PERSEVERANCE", 100, 4000, 700)["line_widths"][0] * title["font_size"] / 100
    assert w <= title["width"] * 1080 * .97
