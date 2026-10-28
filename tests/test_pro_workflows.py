"""Pro workflow upgrades learned from tutorials: transitions, sound accents and their placement, primary grade, scopes."""
import json
import math
import subprocess
import numpy as np
import pytest
from editvideo import store, sound, audiofx, color_grade, scopes
from editvideo.models import Transition


def fx(tmp_path, code):
    src = tmp_path / "effects.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    return json.loads(subprocess.check_output(["node", "-e", "const fx=require(process.argv[1]);" + code, str(src)], text=True))


def test_transitions_follow_direction_and_measured_grammar(tmp_path):
    r = fx(tmp_path, """const T=(name,x={})=>({name,duration_frames:12,...x});
    console.log(JSON.stringify({wu:fx.transitionStyle(T('whip_up'),6),wl:fx.transitionOutStyle(T('whip_left'),6),
      spin:[fx.transitionStyle(T('spin'),2),fx.transitionStyle(T('spin'),12)],luma:[0,6,12].map(f=>fx.transitionStyle(T('luma_key'),f).filter||'none'),
      g1:fx.transitionStyle(T('glitch_cut',{duration_frames:6}),2),g2:fx.transitionStyle(T('glitch_cut',{duration_frames:6}),2),
      dip:[0,5,6,7,11].map(f=>[fx.transitionStyle(T('dip_black',{hold_frames:2}),f).opacity,fx.transitionOutStyle(T('dip_black',{hold_frames:2}),f).filter]),
      iris:fx.transitionStyle(T('iris',{center:[.2,.3]}),6),pass:fx.transitionStyle(T('pass_right'),6),defs:fx.filterDefs()}));""")
    assert r["wu"]["filter"].startswith("url(#ev-mb-v-") and "translate(0%," in r["wu"]["transform"]
    assert r["wl"]["filter"].startswith("url(#ev-mb-h-")
    assert r["spin"][0]["opacity"] == 0 and "rotate(0.00deg)" in r["spin"][1]["transform"]
    assert r["luma"][0] == "url(#ev-luma-0)" and r["luma"][-1] == "none"
    assert r["g1"] == r["g2"]  # deterministic per frame
    dip = r["dip"]  # frames 0,5,6,7,11 of a 12-frame dip with a 2-frame hold: out over 0-4, black 5-6, in over 7-11
    assert dip[0][1] == "brightness(1.000)" and dip[1][1] == "brightness(0.000)"
    assert all(o == 0 for o, _ in dip[:3]) and dip[-1][0] > .5  # black held, then the incoming rises
    assert "at 20.0% 30.0%" in r["iris"]["clipPath"] and "linear-gradient(90deg" in r["pass"]["maskImage"]
    assert r["defs"].count("<filter") == 2 * 10 + 21 + 3 * 4 + 8  # directional blur, luma key, boil variants, channel split steps
    Transition(name="dissolve", duration_frames=75)  # measured long dissolves fit
    Transition(name="dip_white", duration_frames=12, hold_frames=2)
    with pytest.raises(ValueError):
        Transition(name="dip_black", duration_frames=10, hold_frames=10)
    with pytest.raises(ValueError):
        Transition(name="iris", center=[1.5, .2])


def test_sound_kinds_report_their_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    rc = sound.design("reverse_cymbal", 1.5, seed=3)
    imp = sound.design("impact", .6, seed=3)
    wh = sound.design("whoosh", .6, seed=3)
    assert rc["peak_s"] > 1.4 and imp["peak_s"] < .05 and .2 < wh["peak_s"] < .4
    for k in ("pop", "shutter", "drone", "room_tone", "wind", "chime", "sub_drop", "crunch"):
        r = sound.design(k, .8 if k not in ("pop", "shutter") else .15, seed=1, gain_db=-30)
        assert r["onset_s"] <= r["peak_s"] <= r["duration"]
    assert sound.design("pop", .12, seed=1)["sha256"] == sound.design("pop", .12, seed=1)["sha256"]
    with pytest.raises(ValueError):
        sound.design("laser", .5)


def test_sfx_plan_anchors_moving_transitions_and_limits_density():
    t = {"total_frames": 900, "shots": [{"id": "a", "start_frame": 0, "end_frame": 300}, {"id": "b", "start_frame": 300, "end_frame": 600,
         "transition": {"name": "whip_left", "duration_frames": 12}}, {"id": "c", "start_frame": 600, "end_frame": 900, "transition": {"name": "dissolve", "duration_frames": 20}}],
         "layers": [{"id": f"t{i}", "kind": "text", "start_frame": 100 + i * 10, "end_frame": 200, "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 8}]} for i in range(5)]}
    kept, skipped = audiofx.plan(t, audiofx.SfxSync(hits=[{"frame": 700, "kind": "sub_drop"}]))
    frames = [(e["frame"], e["kind"]) for e in kept]
    assert (306, "whoosh") in frames and (700, "sub_drop") in frames
    assert not any(e["frame"] == 600 for e in kept)  # dissolves are not moves
    pops = [f for f, k in frames if k == "pop"]
    assert pops and all(b - a >= 36 for a, b in zip(pops, pops[1:])) and skipped  # 1.2 s minimum gap thins the entrances


def test_primary_grade_math():
    g = color_grade.Grade()
    x = np.random.default_rng(1).random((200, 3))
    assert np.allclose(color_grade.apply(g, x), x, atol=1e-9)  # neutral grade is identity
    g = color_grade.Grade(lift=.05, gain=.9)
    assert np.allclose(color_grade.apply(g, [[0, 0, 0], [1, 1, 1]]), [[.05] * 3, [.9] * 3])
    sat0 = color_grade.apply(color_grade.Grade(saturation=0), [[.8, .2, .1]])[0]
    assert np.ptp(sat0) < 1e-9
    curve = color_grade.Grade(curve=[[.25, .2], [.75, .82]])
    ramp = np.linspace(0, 1, 50)[:, None].repeat(3, 1)
    out = color_grade.apply(curve, ramp)[:, 0]
    assert np.all(np.diff(out) >= -1e-9)  # monotone, no solarisation
    lut = color_grade.cube(color_grade.Grade(contrast=1.2), size=5)
    assert lut.startswith("LUT_3D_SIZE 5") and len(lut.strip().splitlines()) == 1 + 125
    frame = np.full((40, 40, 3), [.6, .5, .4], np.float32)
    gains = color_grade.neutral_gains(frame, [.25, .25, .5, .5])
    assert np.allclose(np.array([.6, .5, .4]) * gains, .5, atol=1e-4)
    for bad in ({"lift": .5}, {"curve": [[.2, .5], [.6, .3]]}, {"shadow_tint": [.2, 0, 0]}):
        with pytest.raises(ValueError):
            color_grade.Grade(**bad)


def test_scopes_exclude_bars_and_read_skin_angle():
    frame = np.zeros((90, 160, 3), np.float32)
    frame[10:80] = .5  # letterboxed mid-grey picture
    frame[2:6, 20:40] = .9  # a burned-in caption inside the top bar
    s = scopes.measure(frame)
    assert s["bars_excluded"] and s["crushed_under_2pct"] < .01 and abs(s["luma_pct"]["50"] - 50) < 1
    a = math.radians(scopes.SKIN_DEG)
    y = .5
    cb, cr = .06 * math.cos(a), .06 * math.sin(a)
    skin = np.array([y + 1.5748 * cr, 0, y + 1.8556 * cb])
    skin[1] = (y - .2126 * skin[0] - .0722 * skin[2]) / .7152
    img = np.full((60, 60, 3), .5, np.float32)
    img[20:40, 20:40] = skin
    s = scopes.measure(img, [1 / 3, 1 / 3, 1 / 3, 1 / 3])
    assert abs(s["skin"]["off_skin_line_deg"]) < 1


def test_editing_grammar_audits(monkeypatch):
    from editvideo import agent, review
    t = {"width": 1920, "height": 1080, "total_frames": 900, "fps": 30,
         "design": {"typography": {"display": {"size": 112}, "body": {"size": 42}}},
         "shots": [{"id": "a", "start_frame": 0, "end_frame": 150, "asset_id": "v", "source_start": 0},
                   {"id": "b", "start_frame": 150, "end_frame": 300, "asset_id": "v", "source_start": 6},  # 1 s skip, same framing
                   {"id": "c", "start_frame": 300, "end_frame": 900, "asset_id": "w", "transition": {"name": "dissolve", "duration_frames": 4}}],
         "layers": [{"id": f"t{i}", "kind": "text", "text": "x", "start_frame": 310 + i * 10, "end_frame": 400, "x": .1, "y": .1 + .1 * i,
                     "width": .3, "height": .05, "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 8}]} for i in range(6)]}
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
    monkeypatch.setattr(store, "assets", lambda pid: [])
    codes = {f["code"] for f in review.audit_timeline("p")["findings"]}
    assert {"short_dissolve", "jump_cut", "attention_gap", "event_overload"} <= codes


def test_text_animate_range_selector_and_colour(tmp_path):
    r = fx(tmp_path, """const T=(p,f,fx2)=>fx.widget({kind:'text',text:'one two three',color:'#ffffff',effects:[{name:'text_animate',start_frame:0,end_frame:20,params:p}]},f);
    console.log(JSON.stringify({start:T({unit:'word',mode:'in'},0),end:T({unit:'word',mode:'in'},20),rev:T({unit:'word',mode:'in',order:'reverse'},8),
      out:T({unit:'word',mode:'out'},20),sweep:T({unit:'word',mode:'sweep',color:'#ff0000',window:.3,amount:0},10),
      col:[0,30].map(f=>fx.styleAt({color:'#ffffff',effects:[{name:'color_to',end_frame:30,params:{color:'#ff0000'}}]},f).color)}));""")
    op = lambda html: [float(x) for x in __import__("re").findall(r"opacity:([\d.]+)", html)]
    assert op(r["start"]) == [0, 0, 0] and op(r["end"]) == [1, 1, 1] and op(r["out"]) == [0, 0, 0]
    rev = op(r["rev"])
    assert rev[2] > rev[0]  # reverse order: the last word leads
    assert "color:rgb(" in r["sweep"] and op(r["sweep"]) == [1, 1, 1]
    assert r["col"] == ["rgb(255,0,0)", "rgb(255,255,255)"]


def test_camera_log_inputs_decode_grey_and_keep_white():
    from editvideo import color_log
    from editvideo.color_pipeline import ColorRequest
    assert abs(float(color_log.decode("slog3", 420 / 1023)) - .18) < 1e-4
    assert abs(float(color_log.decode("logc3", .391007)) - .18) < 1e-3
    assert abs(float(color_log.decode("vlog", .4233)) - .18) < 1e-3
    for name in ("slog3", "logc3", "vlog"):
        assert np.allclose(color_log.matrix(name) @ [1, 1, 1], 1, atol=1e-6)  # shared D65 white stays white
    assert abs(float(color_log.to_display(np.array([.18]))[0]) - .42) < 1e-3
    lut = color_log.cube("slog3", size=5)
    assert "LUT_3D_SIZE 5" in lut and len([l for l in lut.splitlines() if l[:1].isdigit()]) == 125
    with pytest.raises(ValueError):
        ColorRequest(path="x.mp4", input_space="slog3")  # range must be declared for camera log
    with pytest.raises(ValueError):
        ColorRequest(path="x.mp4", input_space="vlog", input_range="full", output="hdr10")


def test_cut_audit_flags_a_whip_against_the_footage_motion(tmp_path, monkeypatch):
    import cv2
    from PIL import Image as PILImage
    from editvideo import agent, review
    from editvideo.media import FFMPEG, command
    rng = np.random.default_rng(3)
    tex = cv2.GaussianBlur(rng.random((180, 1600)).astype(np.float32), (0, 0), 3)
    tex = ((tex - tex.min()) / (tex.max() - tex.min()) * 255).astype(np.uint8)
    PILImage.fromarray(tex).convert("RGB").save(tmp_path / "tex.png")
    clip = tmp_path / "pan.mp4"
    # The crop window travels right at 5 px/frame, so the picture content moves LEFT across the frame.
    command([FFMPEG, "-y", "-v", "error", "-loop", "1", "-framerate", "30", "-i", tmp_path / "tex.png", "-t", "4",
             "-vf", "crop=320:180:x='t*150':y=0,format=yuv420p", clip])

    def timeline(name):
        return {"width": 320, "height": 180, "total_frames": 120, "fps": 30, "layers": [],
                "shots": [{"id": "a", "start_frame": 0, "end_frame": 60}, {"id": "b", "start_frame": 60, "end_frame": 120,
                                                                          "transition": {"name": name, "duration_frames": 6}}]}
    codes = {}
    for name in ("whip_right", "whip_left"):
        monkeypatch.setattr(agent, "read", lambda pid, n=name: {"revision": 1, "timeline": timeline(n)})
        r = review.cut_audit(clip, "p")
        codes[name] = {f["code"] for f in r["findings"]}
        assert r["cuts"][0]["flow_before"][0] < -.6  # leftward motion measured
    assert "transition_against_motion" in codes["whip_right"] and "transition_against_motion" not in codes["whip_left"]


def test_hook_audit_for_vertical_short_form(monkeypatch):
    from editvideo import agent, review
    t = {"width": 1080, "height": 1920, "total_frames": 600, "fps": 30, "cues": [],
         "design": {"typography": {"display": {"size": 112}, "body": {"size": 42}}},
         "shots": [{"id": "a", "start_frame": 0, "end_frame": 600, "motion": "hold"}],
         "layers": [{"id": "hook", "kind": "text", "text": "This is a long hook line that keeps going on and on", "start_frame": 40, "end_frame": 200,
                     "x": .1, "y": .82, "width": .8, "height": .08, "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 8}]}]}
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 1, "timeline": t})
    monkeypatch.setattr(store, "assets", lambda pid: [])
    f = {x["code"]: x for x in review.audit_timeline("p")["findings"]}
    assert {"late_hook", "sparse_open", "hook_text_long", "hook_text_in_ui_zone", "attention_gap"} <= set(f)
    assert f["attention_gap"]["evidence"]["threshold_s"] == 4  # vertical profile


def test_stepped_time_jitter_trim_and_clock_wipe(tmp_path):
    r = fx(tmp_path, """const L={step_frames:2,effects:[{name:'rise',end_frame:10}]};
    const svg={id:'s',kind:'svg',data:{view_box:[100,100],elements:[{id:'p',type:'path',d:'M0 0L100 0',stroke:'#ffffff',stroke_width:4,
      trim:{frames:[0,10],start:[0,0],end:[0,1]},width_ramp:[0,10,0,8]}]}};
    console.log(JSON.stringify({steps:[0,1,2,3].map(f=>fx.stepFrame(L,f)),design:fx.stepFrame({},5,{step_frames:3}),
      j:[0,3,4].map(f=>fx.styleAt({effects:[{name:'jitter',end_frame:1,params:{amount:5,cycles:4}}]},f).transform),
      t0:fx.widget(svg,0),t10:fx.widget(svg,10),cw:fx.styleAt({effects:[{name:'clock_wipe',end_frame:20}]},10).maskImage,
      cwDone:fx.styleAt({effects:[{name:'clock_wipe',end_frame:20}]},20).maskImage||null}));""")
    assert r["steps"] == [0, 0, 2, 2] and r["design"] == 3
    assert r["j"][0] == r["j"][1] != r["j"][2]  # holds a pose for `cycles` frames
    assert "<path" not in r["t0"] and 'stroke-dasharray="1.00000 2"' in r["t10"] and 'stroke-width="8"' in r["t10"]
    assert "conic-gradient" in r["cw"] and r["cwDone"] is None


def test_camera_stage_bakes_camera_into_child_keyframes():
    from editvideo import explainer
    from editvideo.models import Layer
    from editvideo.design_library import tokens
    t = {"width": 1920, "height": 1080, "total_frames": 600, "fps": 30, "design": tokens("minimal_explainer"), "shots": [], "layers": []}
    req = {"recipe": "camera_stage", "id": "map", "start_frame": 0, "end_frame": 300, "canvas": [3, 2], "step_frames": 2,
           "children": [{"x": .05, "y": .1, "width": .25, "height": .3, "layer": {"kind": "text", "text": "A"}},
                        {"x": .6, "y": .55, "width": .3, "height": .35, "layer": {"kind": "shape", "data": {"shape": "rectangle"}}}],
           "stops": [{"at": 0, "cx": .175, "cy": .25}, {"at": 90, "cx": .75, "cy": .725, "zoom": 1.4}]}
    out = explainer.camera_stage(t, explainer.CameraStage.model_validate(req))
    a, b = (Layer.model_validate(op["layer"]) for op in out["ops"])
    # Child A is framed at the first stop (centre of frame, no offset); child B is centred when the camera lands on it.
    ax = {k.frame: k.value for k in a.keyframes["x"]}
    bx = {k.frame: k.value for k in b.keyframes["x"]}
    assert abs(ax[0]) < 1 and abs(bx[90]) < 1 and bx[0] > 1500
    assert {k.frame: k.value for k in b.keyframes["scale"]}[90] == 1.4 and a.step_frames == 2
    assert any(e.name == "motion_blur" for e in a.effects)
    with pytest.raises(ValueError):
        explainer.CameraStage.model_validate({**req, "stops": [{"at": 10, "cx": .5, "cy": .5}]})


def test_compositing_parent_mask_matte_key(tmp_path):
    r = fx(tmp_path, """const hub={id:'hub',kind:'null',x:.4,y:.4,width:.2,height:.2,start_frame:0,end_frame:100,keyframes:{rotate:[{frame:0,value:0},{frame:50,value:90}]}};
    const arm={id:'arm',kind:'null',x:.6,y:.45,width:.1,height:.1,start_frame:0,end_frame:100,parent:'hub',keyframes:{scale:[{frame:0,value:1},{frame:50,value:2}]}};
    const dot={id:'dot',kind:'shape',x:.7,y:.45,width:.05,height:.1,start_frame:0,end_frame:100,parent:'arm'};
    const byId={hub,arm,dot},ctx={byId,W:1000,H:1000};
    const c=fx.composite(dot,50,50,ctx);
    const masked={id:'m',kind:'shape',x:0,y:0,width:.5,height:.5,start_frame:0,end_frame:10,masks:[{shape:'rect',geom:[0,0,1,1]},{shape:'ellipse',geom:[.5,.5,.2,.2],mode:'subtract',feather_px:10},{shape:'rect',geom:[0,0,.5,1],mode:'intersect'}]};
    const word={id:'w',kind:'text',text:'HI',x:.1,y:.1,width:.3,height:.2,start_frame:0,end_frame:10,_type:{fontSize:'100px',fontFamily:'sans-serif'}};
    const tgt={id:'v',kind:'shape',x:.1,y:.1,width:.3,height:.2,start_frame:0,end_frame:10,matte:{source:'w',mode:'luma_inverted'}};
    console.log(JSON.stringify({dot:c.style,mask:fx.composite(masked,0,0,{W:1000,H:1000}),matte:fx.composite(tgt,0,0,{byId:{w:word,v:tgt},W:1000,H:1000}),
      key:fx.composite({id:'k',kind:'video',key:{screen:'green',clip_black:.1,clip_white:.6}},0,0,{}).style,plain:fx.composite({id:'p',x:0,y:0,width:1,height:1},0,0,{}).defs}));""")
    import re
    m = [float(v) for v in re.findall(r"-?[\d.]+", r["dot"]["transform"])]
    # dot centre (725,500) through arm (scale 2 about (650,500)) then hub (rotate 90 about (500,500)): -> (500, 800).
    a, b, c_, d, e, f = m
    cx, cy = a * 25 + c_ * 50 + e + 700, b * 25 + d * 50 + f + 450
    assert abs(cx - 500) < .5 and abs(cy - 800) < .5 and r["dot"]["transformOrigin"] == "0 0"
    mk = r["mask"]
    assert "url(#ev-mask-m)" in mk["style"]["maskImage"] and 'fill="#000"' in mk["defs"] and "ev-mask-m-i2" in mk["defs"] and "feGaussianBlur" in mk["defs"]
    mt = r["matte"]
    assert "url(#ev-matte-v)" in mt["style"]["maskImage"] and ">HI</text>" in mt["defs"] and "-1 0 0 0 1" in mt["defs"]
    assert r["key"]["_keyFilter"] == "url(#ev-key-k)" and r["plain"] == ""


def test_compositing_validation():
    from editvideo.models import Layer, Timeline
    from editvideo.design_library import tokens
    base = {"start_frame": 0, "end_frame": 30}
    with pytest.raises(ValueError):
        Layer(id="t", kind="text", text="x", key={"screen": "green"}, **base)  # keys need media
    with pytest.raises(ValueError):
        Layer(id="v", kind="video", asset_id="a", key={"screen": "green", "color": "#ff2020"}, **base)
    with pytest.raises(ValueError):
        Layer(id="s", kind="shape", masks=[{"shape": "polygon", "geom": [0, 0, 1, 1]}], **base)
    with pytest.raises(ValueError):
        Layer(id="s", kind="shape", masks=[{"shape": "rect", "geom": [0, 0, 1, 1], "keyframes": [{"frame": 0, "geom": [0, 0, 1]}]}], **base)
    tl = lambda layers: Timeline.model_validate({"width": 1920, "height": 1080, "total_frames": 30, "audio_samples": 48000, "timing_method": "x",
                                                  "beats": [], "cues": [], "shots": [{"id": "s", "beat_id": "b", "start_frame": 0, "end_frame": 30}],
                                                  "layers": layers})
    with pytest.raises(ValueError):
        tl([{"id": "a", "kind": "null", "parent": "b", **base}, {"id": "b", "kind": "null", "parent": "a", **base}])  # cycle
    with pytest.raises(ValueError):
        tl([{"id": "a", "kind": "shape", "matte": {"source": "zz"}, **base}])
    tl([{"id": "n", "kind": "null", **base}, {"id": "c", "kind": "shape", "parent": "n", "anchor": [0, 0], **base},
        {"id": "w", "kind": "text", "text": "A", **base}, {"id": "v", "kind": "shape", "matte": {"source": "w", "mode": "alpha"}, **base}])


def test_audio_roles_normalise_to_role_targets(tmp_path, monkeypatch):
    from editvideo import renderer
    from editvideo.media import FFMPEG, command
    from editvideo.models import AudioClip
    tone = tmp_path / "tone.wav"
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3", "-af", "volume=-6dB", tone])
    monkeypatch.setattr(renderer, "safe_asset_path", lambda pid, aid: tone)
    lufs, peak = renderer.clip_level(tone, 0, 3)
    long = {"asset_id": "a", "source_start": 0, "playback_rate": 1, "role": "music", "normalize": True}
    assert abs(renderer.role_gain_db("p", long, 2.5) - (renderer.ROLE_LUFS["music"] - lufs)) < .01
    short = {**long, "role": "sfx"}
    assert abs(renderer.role_gain_db("p", short, .5) - (renderer.ROLE_PEAK["sfx"] - renderer.clip_level(tone, 0, .5)[1])) < .01
    assert renderer.role_gain_db("p", {**long, "normalize": False}, 2.5) == 0
    AudioClip(id="c", asset_id="a", start_frame=0, end_frame=30, role="dialogue", normalize=True)
    assert "acompressor" in renderer.ROLE_CHAIN["dialogue"] and "alimiter" in renderer.ROLE_CHAIN["dialogue"]


def test_corner_pin_maps_box_corners_exactly_and_tracks(tmp_path):
    r = fx(tmp_path, r"""const it={id:'s1',kind:'image',x:.25,y:.25,width:.5,height:.5,corner_pin:{corners:[[.3,.2],[.8,.3],[.75,.85],[.2,.7]]}};
    const m=fx.composite(it,0,0,{W:1920,H:1080}).style.transform.match(/matrix3d\((.*)\)/)[1].split(',').map(Number);
    const ap=(x,y)=>{const X=m[0]*x+m[4]*y+m[12],Y=m[1]*x+m[5]*y+m[13],w=m[3]*x+m[7]*y+m[15];return [(X/w+480)/1920,(Y/w+270)/1080];};
    const tr={...it,corner_pin:{track:[{frame:0,corners:[[.25,.25],[.75,.25],[.75,.75],[.25,.75]]},{frame:10,corners:[[.35,.25],[.85,.25],[.85,.75],[.35,.75]]}]}};
    console.log(JSON.stringify({pts:[ap(0,0),ap(960,0),ap(960,540),ap(0,540)],mid:fx.composite(tr,5,5,{W:1920,H:1080}).style.transform,
      after:fx.composite(tr,40,40,{W:1920,H:1080}).style.transform}));""")
    want = [[.3, .2], [.8, .3], [.75, .85], [.2, .7]]
    assert all(abs(a - b) < 1e-6 for p, q in zip(r["pts"], want) for a, b in zip(p, q))
    assert r["mid"] == "matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,96,0,0,1)"  # halfway: +0.05 * 1920 px
    assert r["after"].endswith("192,0,0,1)")  # holds the last sample


def test_svg_pixel_effects_chain_after_key(tmp_path):
    r = fx(tmp_path, r"""const E=n=>({name:n,start_frame:0,end_frame:10,params:{color:'#ff8800'}});
    const it={id:'v1',kind:'video',x:0,y:0,width:1,height:1,key:{screen:'green'},effects:['luma_alpha','tint_fill','highlight_glow','tritone','heat_distortion','light_wrap'].map(E)};
    const a=fx.composite(it,3,3,{W:1920,H:1080}),b=fx.composite(it,3,3,{W:1920,H:1080}),h1=fx.composite(it,4,4,{W:1920,H:1080}),h9=fx.composite(it,9,9,{W:1920,H:1080});
    const late={...it,key:null,effects:[{...E('tritone'),start_frame:20}]};
    console.log(JSON.stringify({chain:a.style._keyFilter,n:(a.defs.match(/<filter /g)||[]).length,bad:/NaN|undefined/.test(a.defs),same:a.defs===b.defs,
      heat:[h1.defs.match(/seed="(\d+)"/)[1],h9.defs.match(/seed="(\d+)"/)[1]],late:fx.composite(late,5,5,{}).style._keyFilter||null}));""")
    assert r["chain"].split()[0] == "url(#ev-key-v1)" and r["chain"].count("url(#ev-fx-v1-") == 6
    assert r["n"] == 7 and not r["bad"] and r["same"]
    assert r["heat"] == ["7", "8"]  # noise seed advances every `cycles` (8) frames, frame-indexed
    assert r["late"] is None  # inactive before start_frame


def test_tracking_em_recentres_and_text_animate_stacks(tmp_path):
    r = fx(tmp_path, r"""const s=fx.styleAt({kind:'text',font_size:100,data:{align:'center'},effects:[{name:'tracking',start_frame:0,end_frame:10,params:{amount:.3,from_em:.1},easing:'linear'}]},5);
    const left=fx.styleAt({kind:'text',font_size:100,effects:[{name:'tracking',start_frame:0,end_frame:10,params:{amount:.3}}]},10);
    const T={id:'x',kind:'text',text:'one two three',color:'#ffffff',effects:[{name:'text_animate',start_frame:0,end_frame:10,params:{amount:30}},{name:'text_animate',start_frame:20,end_frame:30,params:{mode:'out',amount:30,shutter:180}}]};
    const op=h=>[...h.matchAll(/opacity:([\d.]+)/g)].map(m=>+m[1]);
    console.log(JSON.stringify({ls:s.letterSpacing,tf:s.transform,left:[left.letterSpacing,left.transform],
      a0:op(fx.widget(T,0)),a15:op(fx.widget(T,15)),a25:fx.widget(T,25),a35:op(fx.widget(T,35))}));""")
    assert r["ls"] == "0.2000em" and r["tf"].startswith("translate(10px,0px)")
    assert r["left"][0] == "0.3000em" and r["left"][1].startswith("translate(0px,0px)")
    assert r["a0"] == [0, 0, 0] and r["a15"] == [1, 1, 1] and r["a35"] == [0, 0, 0]  # entry, rest, exit on one layer
    assert "blur(" in r["a25"]  # per-word motion blur while words travel


def test_particle_system_presets_are_deterministic_and_bounded(tmp_path):
    r = fx(tmp_path, """const L=(preset,extra={})=>({id:'p',kind:'particles',width:1,height:1,_canvas_width:1920,_canvas_height:1080,
      data:{mode:'system',preset,seed:3,...extra}});const c=h=>(h.match(/<circle/g)||[]).length,l=h=>(h.match(/<line/g)||[]).length;
    const sp=L('sparks');
    console.log(JSON.stringify({fire:c(fx.widget(L('fire'),60)),same:fx.widget(L('fire'),60)===fx.widget(L('fire'),60),
      sparks:[1,6,30].map(f=>l(fx.widget(sp,f))),cap:c(fx.widget(L('fire',{max_particles:50}),60)),
      bad:/NaN|undefined/.test(fx.widget(L('smoke'),45)+fx.widget(L('bokeh'),45)+fx.widget(L('embers'),45))}));""")
    assert r["fire"] > 50 and r["same"] and not r["bad"]
    assert r["sparks"][0] > 0 and r["sparks"][2] == 0  # one burst that burns out
    assert r["cap"] <= 50


def test_corner_pin_and_new_effect_validation():
    from editvideo.models import Layer, CornerPin
    base = dict(id="sc", kind="image", asset_id="a", start_frame=0, end_frame=30)
    Layer(**base, corner_pin={"corners": [[.3, .2], [.8, .3], [.75, .85], [.2, .7]]})
    for bad in ({"corners": [[.3, .2], [.75, .85], [.8, .3], [.2, .7]]},  # crossed (bow-tie)
                {"corners": [[0, 0], [1, 0], [1, 1]]},
                {"track": [{"frame": 5, "corners": [[0, 0], [1, 0], [1, 1], [0, 1]]}, {"frame": 5, "corners": [[0, 0], [1, 0], [1, 1], [0, 1]]}]},
                {}):
        with pytest.raises(ValueError):
            CornerPin(**bad)
    with pytest.raises(ValueError):
        Layer(**base, parent="x", corner_pin={"corners": [[0, 0], [1, 0], [1, 1], [0, 1]]})
    with pytest.raises(ValueError):
        Layer(**base, corner_pin={"track": [{"frame": 40, "corners": [[0, 0], [1, 0], [1, 1], [0, 1]]}]})
    from editvideo.effects import validate_effect
    validate_effect("tracking", {"amount": .25, "from_em": .05})
    validate_effect("highlight_glow", {"threshold": .8, "anamorphic": 1, "color": "#88ccff"})
    for name, params in (("tracking", {"amount": 3}), ("luma_alpha", {"clip_black": .6, "clip_white": .6}),
                         ("highlight_glow", {"radius": 500}), ("tritone", {"shadow_color": "red"}), ("tint_fill", {"ramp": 1})):
        with pytest.raises(ValueError):
            validate_effect(name, params)
    assert Layer(**base, blend="add").blend == "add"


def test_color_match_recovers_a_known_mismatch_and_skin_protection():
    from editvideo import color_match as cm
    from editvideo.color_grade import Grade, apply, _ycc
    rng = np.random.default_rng(5)
    # A synthetic "scene": smooth gradients, a grey card, a skin patch and saturated objects.
    h, w = 120, 200
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    img = np.stack([.15 + .7 * xx, .2 + .6 * yy, .25 + .5 * (1 - xx) * yy], -1)
    img[20:60, 20:60] = [.78, .56, .45]  # skin
    img[70:100, 120:180] = [.2, .35, .7]
    img = np.clip(img + rng.normal(0, .01, img.shape), 0, 1)
    bad = apply(Grade(gain=[1.12, 1, .9], offset=[-.015, 0, .01], saturation=.82), img)
    grade, S, A, T = cm.solve([bad], [img])
    before, after = cm.residuals(S, T), cm.residuals(A, T)
    assert after["d_cast"] < .6 and abs(after["d_mid"]) < 1.5 and abs(after["chroma_ratio"] - 1) < .05
    assert after["d_cast"] < before["d_cast"] / 3
    look = dict(shadow_tint=[-.04, 0, .05], highlight_tint=[.05, .02, -.05], secondaries=[{"hue_deg": 123, "width_deg": 60, "sat_gain": .6}])
    skin = np.array([[.78, .56, .45]])
    plain, kept = apply(Grade(**look), skin), apply(Grade(**look, protect_skin=1), skin)
    c = lambda v: float(np.hypot(*_ycc(v)[1:])[0])
    assert c(plain) < .7 * c(skin) and abs(c(kept) - c(skin)) < .005
    blue = np.array([[.2, .35, .7]])
    assert np.allclose(apply(Grade(**look), blue), apply(Grade(**look, protect_skin=1), blue))


def test_new_camera_logs_decode_grey():
    from editvideo import color_log
    for name, code in color_log.GREY_CODE.items():
        assert abs(float(color_log.decode(name, np.array(code))) - .18) < 1e-3, name
    assert {"logc4", "log3g10", "applelog", "flog2", "bmdfilm5"} <= set(color_log.LOG_SPACES)
    from editvideo.color_pipeline import ColorRequest
    with pytest.raises(ValueError):
        ColorRequest(path="x.mp4", input_space="applelog")  # log input must declare its range


def _sample(tmp_path, layer, frames):
    src = tmp_path / "fx.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    js = ("const FX=require(process.argv[1]);const L=JSON.parse(process.argv[2]);const out=[];for(const f of JSON.parse(process.argv[3])){"
          r"const t=FX.styleAt(L,f).transform;const m=t.match(/translate\(([-\d.e]+)px,([-\d.e]+)px\) scale\(([-\d.e]+),?([-\d.e]+)?\) rotate\(([-\d.e]+)deg/);"
          "if(m[4]===undefined)m[4]=m[3];out.push(m.slice(1).map(Number));}console.log(JSON.stringify(out));")
    return json.loads(subprocess.check_output(["node", "-e", js, str(src), json.dumps(layer), json.dumps(list(frames))], text=True))


def test_track_modifiers_squash_and_loop(tmp_path):
    L = {"kind": "shape", "keyframes": {"x": [{"frame": 0, "value": 0}, {"frame": 10, "value": 100}], "squash": [{"frame": 0, "value": 1}, {"frame": 5, "value": 2.4}],
                                        "rotate": [{"frame": 0, "value": 0}, {"frame": 20, "value": 90}]},
         "track_mods": {"x": {"inertia": {"amount": .6, "period_frames": 5, "decay": .5}}, "rotate": {"loop": "cycle"}}}
    r = _sample(tmp_path, L, range(0, 30))
    xs = [v[0] for v in r]
    peak = max(xs[10:])
    assert 102 < peak < 106 and abs(xs[25] - 100) < 1.5  # overshoot then settles
    assert abs(r[5][2] * r[5][3] - 1) < 1e-6 and r[5][2] / r[5][3] == pytest.approx(2.4, rel=1e-3)  # squash keeps area
    assert r[25][4] == pytest.approx(r[5][4])  # loopOut cycle
    from editvideo.models import Layer
    with pytest.raises(ValueError):
        Layer(id="a", start_frame=0, end_frame=30, kind="shape", keyframes={"x": [{"frame": 0, "value": 1}]}, track_mods={"y": {"loop": "cycle"}})


def test_animate_hop_follows_measured_principles(tmp_path):
    from editvideo import animation as an
    layer = {"id": "ball", "kind": "shape", "start_frame": 0, "end_frame": 200, "x": .45, "y": .6, "width": .08, "height": .14}
    req = an.AnimateRequest(layer_id="ball", material="rubber", exaggerate=1, beats=[{"verb": "hop", "at": 0, "height": 200},
                                                                                        {"verb": "slide_to", "at": 90, "to": [300, 0]}, {"verb": "pop", "at": 140}])
    keys, mods, beats = an.compile_beats(req, layer)
    hop = beats[0]
    assert hop["takeoff"] - 0 >= 9  # crouch 5 + hold 4 before launch: anticipation ≈ 3x the 2-frame launch
    r = _sample(tmp_path, {**layer, "keyframes": keys, "track_mods": mods}, range(0, 170))
    ys = [v[1] for v in r]
    assert min(ys[:90]) == pytest.approx(-200) and ys.index(min(ys[:90])) == hop["apex"]
    c = hop["contacts"][0]
    assert r[c][2] > r[c][3] and r[c - 1][2] < r[c - 1][3]  # squash on contact, stretch the frame before
    assert all(abs(v[2] * v[3] - 1) < 1e-6 for v in r[:130])  # volume preserved throughout
    apex_i, half = hop["apex"], (hop["apex"] + c) // 2
    assert abs(r[half][2] / r[half][3] - 1) < .02  # still round mid-fall: stretch only near contact
    bounce_h = [-min(ys[a:b]) for a, b in zip(hop["contacts"], hop["contacts"][1:])]
    assert bounce_h[0] == pytest.approx(200 * .33, rel=.05) and bounce_h[1] < bounce_h[0] * .85
    xs = [v[0] for v in r]
    assert min(xs[90:110]) < -10 and max(xs[110:130]) > 300  # anticipation back, overshoot past the target
    assert [round(v[2], 2) for v in r[138:141]] == [1.0, 1.0, 1.0]  # a later pop is a pulse, not a re-entrance
