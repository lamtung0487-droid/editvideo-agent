"""Round 6: two-bone IK, drivers, follow-through cache determinism, rig validation."""
import json
import subprocess
import pytest
from editvideo import store
from editvideo.models import Layer, Timeline


def _fx(tmp_path, code, *args):
    src = tmp_path / "fx.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    return json.loads(subprocess.check_output(["node", "-e", "const FX=require(process.argv[1]);const ap=(m,p)=>[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]];" + code, str(src), *args], text=True))


ARM = r"""const W=1920,H=1080;
const up={id:'up',kind:'shape',start_frame:0,end_frame:60,x:.49,y:.3,width:.02,height:.2,anchor:[.5,0]};
const lo={id:'lo',kind:'shape',start_frame:0,end_frame:60,x:.49,y:.5,width:.02,height:.2,anchor:[.5,0],parent:'up',ik:{target:'hand',tip:[.5,1],bend:BEND,weight:WEIGHT}};
const hand={id:'hand',kind:'null',start_frame:0,end_frame:60,x:.6,y:.55,width:.01,height:.01,keyframes:{x:[{frame:0,value:0},{frame:59,value:DX,easing:'linear'}],y:[{frame:0,value:0},{frame:59,value:-100,easing:'linear'}]}};
const byId={up,lo,hand},rows=[];
for(let g=0;g<60;g+=6){const tip=ap(FX.worldMatrix(lo,g,byId,W,H),[(lo.x+.5*lo.width)*W,(lo.y+lo.height)*H]),T=ap(FX.worldMatrix(hand,g,byId,W,H),[(hand.x+.005)*W,(hand.y+.005)*H]),
 el=ap(FX.worldMatrix(up,g,byId,W,H),[(up.x+.01)*W,(up.y+up.height)*H]);rows.push({tip,T,el});}
console.log(JSON.stringify(rows));"""


def _arm(tmp_path, bend="'cw'", weight=1, dx=-300):
    return _fx(tmp_path, ARM.replace("BEND", bend).replace("WEIGHT", str(weight)).replace("DX", str(dx)))


def test_two_bone_ik_reaches_target_and_bends_to_the_chosen_side(tmp_path):
    cw, ccw = _arm(tmp_path), _arm(tmp_path, "'ccw'")
    for r in cw + ccw:
        assert abs(r["tip"][0] - r["T"][0]) < .5 and abs(r["tip"][1] - r["T"][1]) < .5
    shoulder = (960, 324)
    side = lambda r: (r["T"][0] - shoulder[0]) * (r["el"][1] - shoulder[1]) - (r["T"][1] - shoulder[1]) * (r["el"][0] - shoulder[0])
    assert all(side(a) < 0 for a in cw) and all(side(b) > 0 for b in ccw)  # elbows on opposite sides of the reach line
    for r in cw:  # bone lengths are preserved (216 px each)
        assert abs(((r["el"][0] - shoulder[0]) ** 2 + (r["el"][1] - shoulder[1]) ** 2) ** .5 - 216) < .5


def test_ik_out_of_reach_straightens_and_weight_zero_keeps_fk(tmp_path):
    far = _arm(tmp_path, dx=900)  # target ends ~1100 px away from a 432 px limb
    r = far[-1]
    d_tip = ((r["tip"][0] - 960) ** 2 + (r["tip"][1] - 324) ** 2) ** .5
    assert abs(d_tip - 432) < 1
    fk = _arm(tmp_path, weight=0)
    assert all(abs(r["tip"][0] - 960) < .5 and abs(r["tip"][1] - 756) < .5 for r in fk)  # rest pose: straight down


def test_drivers_link_tracks(tmp_path):
    r = _fx(tmp_path, r"""const car={id:'car',kind:'shape',start_frame:0,end_frame:60,x:.1,y:.5,width:.1,height:.05,keyframes:{x:[{frame:0,value:0},{frame:30,value:300,easing:'linear'}]}};
    const wheel={id:'wheel',kind:'shape',start_frame:10,end_frame:60,x:.1,y:.55,width:.03,height:.05,drivers:{rotate:{source:'car',track:'x',mul:180/Math.PI/30},x:{source:'car'}}};
    const lean={id:'lean',kind:'shape',start_frame:0,end_frame:60,x:.1,y:.4,width:.05,height:.1,drivers:{skew:{source:'car',track:'x',mode:'velocity',mul:-2,clamp:[-15,15]}}};
    const late={id:'late',kind:'shape',start_frame:0,end_frame:60,x:.1,y:.3,width:.05,height:.05,drivers:{x:{source:'car',delay_frames:5,mix:'add',add:20}},keyframes:{x:[{frame:0,value:7}]}};
    const byId={car,wheel,lean,late},S=(l,f)=>FX.styleAt(l,f,true,byId);
    console.log(JSON.stringify({w5:S(wheel,5),l10:S(lean,10),l40:S(lean,40),late20:S(late,20),noById:FX.styleAt(wheel,5,true)}));""")
    # wheel local 5 = global 15: car x = 150 → rotation 150 px / 30 px radius in degrees
    assert r["w5"]["x"] == pytest.approx(150) and r["w5"]["rot"] == pytest.approx(150 / 30 * 57.29578, rel=1e-4)
    assert r["l10"]["skew"] == pytest.approx(-15) and r["l40"]["skew"] == pytest.approx(0)  # leans while moving, clamped
    assert r["late20"]["x"] == pytest.approx(7 + 20 + 150)  # own 7 + add 20 + car x at frame 15
    assert r["noById"]["x"] == 0  # without the scene, drivers are inert (no crash)


def test_follow_through_cache_is_order_independent(tmp_path):
    r = _fx(tmp_path, r"""const mk=()=>{const body={id:'body',kind:'shape',start_frame:0,end_frame:90,x:.4,y:.5,width:.1,height:.1,keyframes:{x:[{frame:0,value:0},{frame:5,value:134,easing:'linear'}]}};
     const ant={id:'ant',kind:'shape',start_frame:0,end_frame:90,x:.44,y:.38,width:.02,height:.12,anchor:[.5,1],parent:'body',follow:{preset:'stiff'}};return {body,ant};};
    const ang=(b,f)=>{const m=FX.composite(b.ant,f,f,{byId:b,W:1920,H:1080}).style.transform.match(/matrix\(([^)]*)\)/)[1].split(',').map(Number);return Math.atan2(m[1],m[0]);};
    const a=mk(),fw=[];for(let f=0;f<40;f++)fw.push(ang(a,f));
    const b=mk(),order=[...Array(40).keys()].reverse(),bw=Array(40);for(const f of order)bw[f]=ang(b,f);
    const c=mk(),mix=[30,2,17,17,39,0,25].map(f=>[f,ang(c,f)]);
    console.log(JSON.stringify({fw,bw,mix}));""")
    assert r["fw"] == pytest.approx(r["bw"], abs=1e-9)
    assert all(v == pytest.approx(r["fw"][f], abs=1e-9) for f, v in r["mix"])


def _grey_clip(path, value=.5):
    """1 s flat grey Rec.709-tagged clip (code value `value`)."""
    import numpy as np
    from editvideo.media import FFMPEG, command
    raw = path.with_suffix(".bin")
    raw.write_bytes((np.full((180, 320, 3), value * 255, np.float32).round().astype(np.uint8)).tobytes())
    command([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "320x180", "-r", "30", "-i", raw, "-vf", "loop=loop=29:size=1:start=0",
             "-c:v", "libx264", "-crf", "4", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", path])
    return path


def _frame(path, t):
    import cv2
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    cap.release()
    assert ok
    return img.astype(float).mean(2)


def test_colour_graph_identity_print_look_and_tracked_window(tmp_path, monkeypatch):
    from editvideo import media_tasks, color_graph as cg
    from editvideo.color_pipeline import ColorRequest
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.initialize()
    src = _grey_clip(tmp_path / "grey.mp4")

    def run(graph):
        t = media_tasks.submit("color", {"path": str(src), "input_space": "bt709", "input_range": "limited", "graph": graph}, launch=False)
        media_tasks.run(t["id"])
        r = media_tasks.get(t["id"])
        assert r["state"] == "completed", r["error"]
        return r["result"]
    same = run({"nodes": [{"op": "exposure", "stops": 0}]})
    assert abs(_frame(same["video"], .5).mean() - _frame(src, .5).mean()) < 1.5  # an empty graph is an identity
    up = run({"nodes": [{"op": "exposure", "stops": 1}]})["report"]["graph_checks"]
    assert up["grey18_display"] == pytest.approx((.36 ** (1 / 2.4)) * 1, abs=.01)
    # window moving left → right brightens a feathered ellipse; outside stays put
    win = run({"nodes": [{"op": "window", "keys": [{"t": 0, "box": [.05, .3, .35, .7]}, {"t": .9, "box": [.6, .3, .9, .7]}],
                          "feather_px": 12, "pad": 0, "nodes": [{"op": "exposure", "stops": 1}]}]})
    a, b = _frame(win["video"], .05), _frame(win["video"], .85)
    assert a[90, 64] - a[90, 250] > 20 and b[90, 250] - b[90, 64] > 20  # inside brighter, and the window moved
    assert abs(a[10, 160] - _frame(src, .05)[10, 160]) < 2
    assert len(win["report"]["windows"]) == 1
    with pytest.raises(ValueError, match="expects cineon"):
        ColorRequest(path="x.mp4", graph={"nodes": [{"op": "look", "lut_id": "print_film_cineon", "input": "display"}]})
    with pytest.raises(ValueError, match="last node"):
        cg.Graph.model_validate({"nodes": [{"op": "look", "lut_id": "print_film_cineon"}, {"op": "exposure"}]})
    look = run({"nodes": [{"op": "look", "lut_id": "print_film_cineon", "input": "cineon"}]})["report"]["graph_checks"]
    assert .37 < look["grey18_display"] < .43  # the print look lands grey near .40


def _tl(layers):
    return {"width": 1920, "height": 1080, "total_frames": 60, "audio_samples": 96000, "timing_method": "t", "beats": [], "cues": [],
            "shots": [{"id": "s", "beat_id": "b", "start_frame": 0, "end_frame": 60, "text": "x"}], "layers": layers}


def _L(i, **k):
    return {"id": i, "kind": "shape", "start_frame": 0, "end_frame": 60, **k}


def test_rig_validation():
    ok = [_L("up"), _L("lo", parent="up", ik={"target": "hand"}), _L("hand", kind="null")]
    Timeline.model_validate(_tl(ok))
    with pytest.raises(ValueError, match="parented under it|bone of this chain"):
        Timeline.model_validate(_tl([_L("up"), _L("lo", parent="up", ik={"target": "hand"}), _L("hand", kind="null", parent="lo")]))
    with pytest.raises(ValueError, match="lower bone"):
        Layer.model_validate(_L("lo", ik={"target": "hand"}))
    with pytest.raises(ValueError, match="driver cycle"):
        Timeline.model_validate(_tl([_L("a", drivers={"x": {"source": "b"}}), _L("b", drivers={"x": {"source": "a"}})]))
    with pytest.raises(ValueError, match="cannot drive itself"):
        Timeline.model_validate(_tl([_L("a", drivers={"x": {"source": "a"}})]))
    Timeline.model_validate(_tl([_L("w", drivers={"rotate": {"source": "w", "track": "x", "mul": 2}}, keyframes={"x": [{"frame": 0, "value": 0}]})]))
    with pytest.raises(ValueError, match="not found"):
        Timeline.model_validate(_tl([_L("a", drivers={"x": {"source": "zz"}})]))


def test_routes_name_registered_tools_and_bootstrap_reports_server():
    from editvideo import mcp_server as m, agent_interface as ai
    reg = {k.removeprefix("editvideo_") for k in m.TOOL_REGISTRY}
    names = {t for r in ai.ROUTES.values() for t in r["tools"]}
    names |= {t.split("(")[0] for t in ai.bootstrap("create a video", None, "claude").get("next_tools", [])}
    assert names <= reg, names - reg
    b = m.editvideo_bootstrap("x")
    assert b["server"]["tools"] == len(m.TOOL_REGISTRY)


def test_mcp_edge_json_is_valid_and_numpy_safe():
    import numpy as np
    from editvideo.mcp_server import compact_result, _slim_schema
    out = json.loads(compact_result({"a": float("nan"), "b": np.float32(.5), "c": np.bool_(True), "d": np.int64(3)}))
    assert out == {"a": None, "b": .5, "c": True, "d": 3}
    s = _slim_schema({"properties": {"x": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "X"}}})
    assert s == {"properties": {"x": {"type": "string"}}}


def test_readme_counts_match_registries_and_skills_in_parity():
    import importlib.util
    import re
    spec = importlib.util.spec_from_file_location("repo_facts", store.ROOT / "scripts/repo_facts.py")
    rf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rf)
    f = rf.facts()
    readme = (store.ROOT / "README.md").read_text(encoding="utf-8")
    want = {"MCP tools": f["tools"], "runnable effects": f["effects"], "layer kinds": f["layer_kinds"], "explainer recipes": f["explainer_recipes"],
            "title recipes": f["title_recipes"], "font families": f["font_families"], "palettes": f["palettes"], "style kits": f["style_kits"],
            "original LUTs": f["luts"]}
    for label, n in want.items():
        m = re.search(r"(\d+) (?:Vietnamese-complete )?" + label, readme)
        assert m and int(m.group(1)) == n, (label, m and m.group(1), n)
    assert f"v{f['version']}" in readme
    a = (store.ROOT / ".claude/skills/editvideo-agent/SKILL.md").read_bytes()
    b = (store.ROOT / ".agents/skills/editvideo-agent/SKILL.md").read_bytes()
    assert a == b


def test_stacked_marks_group_with_their_own_letter():
    from editvideo.design_library import stack_line_height
    need = stack_line_height("oswald", ["TRỞ LẠI", "MẶT TRĂNG"], 700)["line_height"]
    assert need >= 1.38  # the dot below Ạ must sit clearly nearer Ạ than the breve of Ă (1.3 still read TRẮNG)
    assert stack_line_height("oswald", ["HELLO", "WORLD"], 700)["line_height"] < 1.0  # no marks: tight stacks stay allowed
    assert stack_line_height("oswald", ["THÁNG BẢY", "NĂM ẤY"], 700)["line_height"] < 1.35  # stacked marks group with each other


def test_text_over_a_strong_push_is_flagged():
    from editvideo.review import _plate_scale
    push = {"effects": [{"name": "focus_zoom", "start_frame": 0, "end_frame": 59, "params": {"amount": .6}},
                        {"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .9, "cut": True}}],
            "keyframes": {"scale": [{"frame": 0, "value": 1}, {"frame": 59, "value": 1.1}]}}
    assert _plate_scale(push) == pytest.approx(1.6 * 1.1)  # held (cut) zooms do not change what lies under the text


def test_letterbox_detector_finds_baked_bars_not_titles_on_black(tmp_path):
    from editvideo import review
    from editvideo.media import FFMPEG, command
    bars, title = tmp_path / "bars.mp4", tmp_path / "title.mp4"
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x340:r=30:d=2", "-vf", "pad=640:360:0:10:black", "-pix_fmt", "yuv420p", bars])
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=2", "-vf",
             "drawbox=x=200:y=150:w=240:h=60:color=white:t=fill", "-pix_fmt", "yuv420p", title])
    shot = [{"id": "s", "start_frame": 0, "end_frame": 60}]
    found = review._letterbox(bars, shot)
    assert found and 6 <= found[0]["top_px"] <= 14 and 6 <= found[0]["bottom_px"] <= 14
    assert review._letterbox(title, shot) == []
