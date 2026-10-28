"""Explainer toolkit: inline emphasis, number readouts, arrows/ripples, particle modes, light layers and recipe compilation."""
import json
import math
import subprocess
import pytest
from editvideo import store, explainer
from editvideo.models import Layer
from editvideo.design_library import tokens, layout_text


def fx(tmp_path, code):
    src = tmp_path / "effects.cjs"
    src.write_bytes((store.ROOT / "engines/effects.js").read_bytes())
    return json.loads(subprocess.check_output(["node", "-e", "const fx=require(process.argv[1]);" + code, str(src)], text=True, encoding="utf-8"))


def test_inline_emphasis_survives_every_reveal(tmp_path):
    r = fx(tmp_path, """const t=(e)=>({kind:'text',text:'Hơn một tỷ **mỗi giây** ==nhanh==',data:{accent:'#ffd166'},effects:e});
    console.log(JSON.stringify({plain:fx.widget(t([]),0),word:fx.widget(t([{name:'word_reveal',end_frame:10}]),20),
      line:fx.widget(t([{name:'mask_reveal',end_frame:10}]),20),char:fx.widget(t([{name:'char_spring',end_frame:10}]),20),
      type:fx.widget(t([{name:'typewriter',end_frame:10}]),10),dec:fx.widget(t([{name:'decode',end_frame:10}]),20),
      at:fx.textAt(t([]),0),esc:fx.widget({kind:'text',text:'<b>**x**</b>'},0)}));""")
    for k in ("plain", "word", "line", "char", "type", "dec"):
        html = r[k]
        assert "**" not in html and "==" not in html, k
        assert "font-weight:800" in html and "color:#ffd166" in html, k
    assert '<span style="font-weight:800;">mỗi giây</span>' in r["plain"]
    assert r["at"] == "Hơn một tỷ mỗi giây nhanh"
    assert "&lt;b&gt;" in r["esc"] and "<b>" not in r["esc"]
    # Python measurement ignores the markup characters.
    a = layout_text("bevietnampro", "Hơn một tỷ mỗi giây", 54)["line_widths"][0]
    b = layout_text("bevietnampro", "Hơn một tỷ **mỗi giây**", 54)["line_widths"][0]
    assert abs(a - b) < .5


def test_counters_group_and_land_on_target(tmp_path):
    r = fx(tmp_path, """const c=(d,f)=>fx.widget({kind:'counter',data:d,effects:[{name:'progress',start_frame:0,end_frame:20}]},f);
    console.log(JSON.stringify({count:c({from:0,to:50000000000,group:' '},20),half:c({from:0,to:1000,group:','},10),
      roll:c({to:4070,group:' ',style:'roll'},20),rollmid:c({to:4070,style:'roll'},8),scr:c({to:925,style:'scramble'},20),
      scr2:c({to:925,style:'scramble'},12),scr3:c({to:925,style:'scramble'},12),align:fx.widget({kind:'counter',data:{to:5,align:'center'}},0),
      vi:c({to:774.7,decimals:1,decimal_mark:',',suffix:' %'},20),vig:c({to:1234.5,decimals:1,group:'.',decimal_mark:','},20),vin:c({to:4717.5,decimals:1,group:'.'},20),barg:fx.widget({kind:'bar_chart',data:{values:[4717.5,99],group:'.',max:5000}},0),
      bars:fx.widget({kind:'bar_chart',data:{values:[774.7,323.1],labels:['1986','1987'],max:800,decimal_mark:','}},0)}));""")
    assert r["count"] == "50 000 000 000"
    assert r["half"] == "500"
    shifts = [float(x) for x in __import__("re").findall(r"translateY\((-?[\d.]+)em\)", r["roll"])]
    assert shifts == pytest.approx([-4 * 1.15, -0.0, -7 * 1.15, -0.0], abs=1e-3)  # columns settle on 4, 0, 7, 0
    assert r["roll"].count("</span></span> <span") == 1  # the group separator sits between the 4 and 070 columns
    assert r["rollmid"] != r["roll"]
    assert r["scr"] == "925" and r["scr2"] == r["scr3"]  # settled, and deterministic mid-way
    assert r["align"].startswith('<div style="text-align:center">')
    assert r["vi"] == "774,7 %" and r["vig"] == "1.234,5"  # Vietnamese numbers: comma decimal mark, dot thousands
    assert r["vin"] == "4.717,5" and ">4.717,5<" in r["barg"]  # dot thousands imply the comma decimal mark
    Layer(id="g", kind="counter", start_frame=0, end_frame=30, data={"to": 4717, "group": "."})  # valid without decimal_mark
    assert ">774,7<" in r["bars"] and ">323,1<" in r["bars"]
    for bad in ({"style": "flip"}, {"group": "...."}, {"style": "roll", "to": -5}, {"decimal_mark": ";"}, {"group": ",", "decimal_mark": ","}, {"decimal_mark": 0}, {"decimal_mark": False}):
        with pytest.raises(ValueError):
            Layer(id="c", kind="counter", start_frame=0, end_frame=30, data=bad)


def test_arrow_grows_from_centre_with_heads_on_tips_and_ripples(tmp_path):
    r = fx(tmp_path, """const s={id:'s',kind:'svg',data:{view_box:[1000,500],elements:[{id:'a',type:'arrow',x1:100,y1:250,x2:900,y2:250,heads:'both',grow:'center',
      draw:[0,20],stroke:'#ffffff',stroke_width:4},{id:'c',type:'circle',cx:500,cy:250,r:40,fill:'#3cd2ff',stroke:'#3cd2ff',stroke_width:3,ripple:[0,30],ripple_count:3}]}};
    console.log(JSON.stringify({mid:fx.widget(s,10),end:fx.widget(s,20),before:fx.widget({...s,data:{...s.data,elements:[s.data.elements[0]]}},-1)}));""")
    import re
    x = lambda html: [float(v) for v in re.findall(r'<line x1="([\d.]+)"', html)] + [float(v) for v in re.findall(r'x2="([\d.]+)"', html)]
    a, b = x(r["mid"])
    assert 250 < a < 320 and 680 < b < 750 and abs((a + b) / 2 - 500) < 1  # symmetric growth, heads inset from tips
    a, b = x(r["end"])
    assert a < 140 and b > 860
    assert r["mid"].count("<path") == 2  # both heads
    assert len(re.findall(r'fill="none" stroke="#3cd2ff"', r["mid"])) >= 1  # ripple rings
    assert "<line" not in r["before"]


def test_particle_modes_are_deterministic_and_bounded(tmp_path):
    r = fx(tmp_path, """const p=(d,f,e)=>fx.widget({id:'p',kind:'particles',width:1,height:.5,color:'#ff9a3c',data:d,effects:e||[]},f);
    const prog=[{name:'progress',end_frame:60}];
    console.log(JSON.stringify({bunch:p({mode:'bunch',count:300},30,prog),bunch2:p({mode:'bunch',count:300},30,prog),
      early:p({mode:'bunch',count:300},0,prog),drift:p({mode:'drift',count:200},10),drift2:p({mode:'drift',count:200},11),
      tracks:p({mode:'tracks',count:50},5,prog),tracksEnd:p({mode:'tracks',count:50},60,prog),stream:p({mode:'stream',count:200},40)}));""")
    assert r["bunch"] == r["bunch2"] and r["bunch"].count("<circle") > 250
    assert r["early"].count("<circle") < 30  # the bunch enters from outside the box
    assert r["drift"] != r["drift2"] and r["drift"].count("<circle") == 200
    assert r["tracks"].count("<polyline") > 0 and r["tracksEnd"].count("<polyline") == 50
    assert "radialGradient" in r["stream"]
    for bad in ({"mode": "laser"}, {"mode": "bunch", "count": 5000}, {"mode": "tracks", "origin": [3, 3]}):
        with pytest.raises(ValueError):
            Layer(id="p", kind="particles", start_frame=0, end_frame=30, data=bad)


def test_speed_lines_and_flare_layers(tmp_path):
    r = fx(tmp_path, """const f=(d,fr)=>fx.widget({id:'f',kind:'film',width:1,height:1,_canvas_width:1920,_canvas_height:1080,data:d},fr);
    console.log(JSON.stringify({s1:f({type:'speed_lines',intensity:.7},10),s2:f({type:'speed_lines',intensity:.7},11),fl:f({type:'flare',intensity:.8,center:[.3,.3]},5)}));""")
    assert r["s1"] != r["s2"] and r["s1"].count("<line") > 60
    assert "mix-blend-mode:screen" in r["fl"] and "radialGradient" in r["fl"] and 'cx="576.0"' in r["fl"]
    Layer(id="f", kind="film", start_frame=0, end_frame=30, data={"type": "flare", "center": [.2, .3]})
    with pytest.raises(ValueError):
        Layer(id="f", kind="film", start_frame=0, end_frame=30, data={"type": "lensflare"})


@pytest.fixture
def timeline():
    return {"width": 1920, "height": 1080, "total_frames": 900, "fps": 30, "design": tokens("minimal_explainer"), "shots": [], "layers": []}


REQUESTS = [
    {"recipe": "measure", "id": "m", "start_frame": 0, "end_frame": 120, "start": [.1, .6], "end": [.9, .6], "value_to": 10000, "suffix": " m"},
    {"recipe": "diagram", "id": "d", "start_frame": 0, "end_frame": 120, "nodes": [{"id": "a", "x": .5, "y": .7, "ripple": [0, 20]},
     {"id": "b", "x": .2, "y": .2, "label": "γ"}], "edges": [{"source": "a", "target": "b", "style": "wave"}, {"source": "b", "target": "a", "style": "arrow"}]},
    {"recipe": "unit_grid", "id": "u", "start_frame": 0, "end_frame": 120, "rows": 20, "cols": 50, "highlight_count": 3,
     "bands": [{"row": 4, "at": 30}], "brackets": [{"cols": [0, 24], "label": "500", "at": 40}]},
    {"recipe": "plot", "id": "p", "start_frame": 0, "end_frame": 120, "x_range": [0, 10], "y_range": [0, 100], "x_ticks": [0, 5, 10],
     "y_ticks": [0, 50, 100], "series": [{"points": [[i, i * 9] for i in range(11)], "errors": [3] * 11}, {"type": "line", "points": [[0, 0], [10, 90]]}],
     "highlight": {"cx": 5, "cy": 45, "rx": 1, "ry": 10}},
    {"recipe": "annotate", "id": "a", "start_frame": 0, "end_frame": 60, "shape": "arrow", "region": [.5, .4, .1, .1]},
    {"recipe": "chips", "id": "c", "start_frame": 0, "end_frame": 120, "theme": "dark", "chips": [{"id": "x", "text": "Độ sáng", "x": .5, "y": .5,
     "moves": [{"at": 20, "x": .5, "y": .2, "scale": .7}]}, {"id": "y", "text": "Số va chạm", "x": .5, "y": .5, "at": 30, "exit_at": 90}],
     "dividers": [{"x": .5, "y": .55, "at": 40}]},
    {"recipe": "number_wall", "id": "n", "start_frame": 0, "end_frame": 150, "text": "4 000 000 000", "wall_at": 60},
    {"recipe": "hud_card", "id": "h", "start_frame": 0, "end_frame": 90, "caption": "Mỗi 25 ns", "value_to": 25, "suffix": " ns"},
    {"recipe": "stat_line", "id": "s", "start_frame": 0, "end_frame": 90, "text": "Hơn một tỷ lần **mỗi giây**"},
    {"recipe": "particles", "id": "pt", "start_frame": 0, "end_frame": 90, "preset": "collision"},
]


@pytest.mark.parametrize("req", REQUESTS, ids=[r["recipe"] for r in REQUESTS])
def test_recipes_compile_to_valid_layers(timeline, req):
    model, fn = explainer.RECIPES[req["recipe"]]
    out = fn(timeline, model.model_validate(req))
    assert out["ops"] and all(op["op"] == "upsert_layer" for op in out["ops"])
    for op in out["ops"]:
        layer = Layer.model_validate(op["layer"])
        length = layer.end_frame - layer.start_frame
        assert all(e.end_frame <= length for e in layer.effects)
        assert all(p.frame < length for track in layer.keyframes.values() for p in track)
    assert out["inspect_frames"]


def test_measure_label_counts_in_sync_and_centres_on_the_line(timeline):
    out = explainer.measure(timeline, explainer.Measure.model_validate(REQUESTS[0]))
    line, value = (op["layer"] for op in out["ops"])
    arrow = line["data"]["elements"][0]
    prog = next(e for e in value["effects"] if e["name"] == "progress")
    assert [prog["start_frame"], prog["end_frame"]] == arrow["draw"] and prog["easing"] == "smooth"
    assert abs(value["x"] + value["width"] / 2 - .5) < .01 and value["data"]["align"] == "center"
    assert value["y"] > .6


def test_plot_maps_data_inside_the_box_and_rejects_bad_ranges(timeline):
    out = explainer.plot(timeline, explainer.Plot.model_validate(REQUESTS[3]))
    els = out["ops"][0]["layer"]["data"]["elements"]
    vb = out["ops"][0]["layer"]["data"]["view_box"]
    pts = [e for e in els if e["id"].startswith("s0p")]
    assert len(pts) == 11 and all(0 < e["cx"] < vb[0] and 0 < e["cy"] < vb[1] for e in pts)
    assert pts[0]["cy"] > pts[-1]["cy"]  # y grows upward
    with pytest.raises(ValueError):
        explainer.Plot.model_validate({**REQUESTS[3], "x_range": [5, 1]})


def test_unit_grid_limits_and_highlights(timeline):
    out = explainer.unit_grid(timeline, explainer.UnitGrid.model_validate(REQUESTS[2]))
    assert out["measurements"]["dots"] == 1000 and out["measurements"]["highlighted"] == 3
    with pytest.raises(ValueError):
        explainer.UnitGrid.model_validate({**REQUESTS[2], "rows": 50, "cols": 50})


def test_wave_connector_starts_and_ends_on_the_axis():
    d = explainer._wave(0, 0, 300, 0, 20, 30)
    pts = [tuple(map(float, p.split())) for p in d[1:].split("L")]
    assert abs(pts[0][1]) < 1e-6 and abs(pts[-1][1]) < 1e-6 and max(abs(y) for _, y in pts) > 15


def test_catalog_lists_every_recipe():
    names = {r["recipe"] for r in explainer.catalog()["recipes"]}
    assert names == set(explainer.RECIPES) and all(r["purpose"] for r in explainer.catalog()["recipes"])


def test_pie_columns_and_text_window_zoom(timeline):
    pie = explainer.pie(timeline, explainer.Pie.model_validate({"recipe": "pie", "id": "p", "start_frame": 0, "end_frame": 120,
                                                                 "values": [50, 30, 20], "labels": ["a", "b", "c"], "pop": 1}))
    base, popped = (op["layer"] for op in pie["ops"])
    slices = [e for e in base["data"]["elements"] if e["type"] == "path"]
    assert [round(e["trim"]["start"][0], 2) for e in slices] == [0, .8]  # slice 1 moved to its own layer
    # slice 1 spans 50-80 % clockwise from 12 o'clock: bisector at 65 % (234 deg) points lower-left
    assert popped["keyframes"]["x"][-1]["value"] < 0 and popped["keyframes"]["y"][-1]["value"] > 0
    for op in pie["ops"]:
        Layer.model_validate(op["layer"])
    col = explainer.columns(timeline, explainer.Columns.model_validate({"recipe": "columns", "id": "c", "start_frame": 0, "end_frame": 120,
                                                                        "values": [1, 4, 2], "labels": ["x", "y", "z"]}))
    bars = [e for e in col["ops"][0]["layer"]["data"]["elements"] if e["id"][0] == "b" and e["id"][1:].isdigit()]
    assert all(e["linecap"] == "butt" for e in bars) and [e["trim"]["frames"][0] for e in bars] == [12, 22, 32]
    tw = explainer.text_window_zoom(timeline, explainer.TextWindowZoom.model_validate(
        {"recipe": "text_window_zoom", "id": "tw", "start_frame": 0, "end_frame": 150, "text": "MARS", "asset_id": "a1", "hold": 30, "zoom_frames": 30}))
    word, plate, full = (op["layer"] for op in tw["ops"])
    assert plate["matte"] == {"source": word["id"], "mode": "alpha"} and full["start_frame"] == plate["end_frame"] == 60
    assert word["keyframes"]["scale"][-1]["value"] == tw["measurements"]["zoom_to"] and tw["measurements"]["stroke_half_width_px"] > 5
    assert abs(full["source_start"] - 2.0) < 1e-6  # footage continues where the matted plate stopped
    with pytest.raises(ValueError):
        explainer.text_window_zoom(timeline, explainer.TextWindowZoom.model_validate(
            {"recipe": "text_window_zoom", "id": "tw", "start_frame": 0, "end_frame": 60, "text": "MARS", "asset_id": "a1", "hold": 30, "zoom_frames": 30}))


def test_log_zoom_dive_approaches_steadily_and_doc_recipes(timeline):
    kids = [{"x": .495, "y": .545, "width": .01, "height": .01, "layer": {"id": "dot", "kind": "shape", "color": "#ffffff", "data": {"shape": "ellipse"}}}]
    q = explainer.CameraStage.model_validate({"recipe": "camera_stage", "id": "st", "start_frame": 0, "end_frame": 150, "canvas": [3, 2], "children": kids,
                                              "stops": [{"at": 0, "cx": .5, "cy": .5, "zoom": .4}, {"at": 90, "cx": .5, "cy": .55, "zoom": 16, "frames": 60, "move": "land"}]})
    L = explainer.camera_stage(timeline, q)["ops"][0]["layer"]
    sc = [k["value"] for k in L["keyframes"]["scale"]]
    ys = [k["value"] for k in L["keyframes"]["y"]]
    assert len(sc) > 20 and all(b >= a for a, b in zip(sc, sc[1:]))  # dense, monotonic zoom
    ratios = [b / a for a, b in zip(sc[1:], sc[2:]) if a > 0]
    assert max(ratios) < 2.2 and ratios[-1] < 1.01  # "land" front-loads the zoom, then settles without a final jump
    # The target's screen position moves steadily toward centre: no overshoot past it.
    off = [abs(y + (L["y"] + L["height"] / 2) * 1080 - 540) for y in ys]
    assert off[-1] < 5 and max(off[1:]) <= off[0] + 1
    tc = explainer.doc_timecard(timeline, explainer.DocTimecard.model_validate({"recipe": "doc_timecard", "id": "tc", "start_frame": 0, "end_frame": 120,
                                                                                "year": 1969, "roll_from": 2024, "label": "Quá khứ"}))
    year = next(op["layer"] for op in tc["ops"] if op["layer"]["id"] == "tc-year")
    assert year["data"]["style"] == "roll" and year["data"]["from"] == 2024 and year["data"]["group"] == ""
    mp = explainer.motif_progress(timeline, explainer.MotifProgress.model_validate({"recipe": "motif_progress", "id": "mp", "start_frame": 0, "end_frame": 90,
                                                                                   "chapters": ["a", "b", "c"], "current": 1}))
    els = mp["ops"][0]["layer"]["data"]["elements"]
    assert [e["id"] for e in els if e["type"] == "circle"] == ["t0", "t1", "t2"] and any(e.get("ripple") for e in els)
    for op in tc["ops"] + mp["ops"]:
        Layer.model_validate(op["layer"])


def test_unit_grid_says_when_its_height_shrinks_the_row(timeline):
    """A row of 30 laid across a gap measures it only when it fills the gap: in a box too short for its cells and its
    bracket label it is centred at a third of the width (the reel's '30 Earths' row read as 90)."""
    req = {"recipe": "unit_grid", "id": "row", "start_frame": 0, "end_frame": 120, "rows": 1, "cols": 30, "dot": .5,
           "box": [.1, .47, .8, .06], "brackets": [{"cols": [0, 29], "label": "30 fit between them", "at": 40}], "label_size": 26}
    short = explainer.unit_grid(timeline, explainer.UnitGrid.model_validate(req))
    assert short["measurements"]["fill"][0] < .5 and any("make the box" in n for n in short["notes"])
    need = float(next(n for n in short["notes"] if "make the box" in n).split("make the box ")[1].split(" tall")[0])
    tall = explainer.unit_grid(timeline, explainer.UnitGrid.model_validate({**req, "box": [.1, .47, .8, need + .002]}))
    assert tall["measurements"]["fill"][0] > .99 and not any("spans" in n for n in tall["notes"])
    assert abs(tall["measurements"]["cell_px"] - .8 * timeline["width"] / 30) < 1
