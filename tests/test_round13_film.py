"""Round 13 (the Vietnam film): the two failures that cost hours are pinned.
- a download the CDN cut short keeps its header, so fetch_source must compare bytes with Content-Length;
- an engine CLI that wrote its whole output but never exited must be counted as finished, not timed out."""
import http.server, sys, threading, time
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import media


class _Short(http.server.BaseHTTPRequestHandler):
    """Announces 1000 bytes, sends 300, closes cleanly: what a CDN did to 30 of 64 clips."""
    body = b"x" * 300

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "1000")
        self.send_header("Content-Type", "video/mp4")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):
        pass


def test_fetch_source_rejects_a_short_download(tmp_path, monkeypatch):
    from editvideo import resources
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Short)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(resources, "ROOT", tmp_path)
        orig = resources.urllib.request.urlopen  # fetch_source insists on https; the local server speaks http
        monkeypatch.setattr(resources.urllib.request, "urlopen", lambda req, timeout=60: orig(req.full_url.replace("https://", "http://"), timeout=timeout))
        url = f"https://127.0.0.1:{srv.server_port}/clip.mp4"
        with pytest.raises(ValueError, match="Short download"):
            resources.fetch_source(url, "other", "short clip", "test", "test", "https://example.test", "footage", "short.mp4")
        assert not (tmp_path / "data" / "sources" / "other" / "short.mp4").exists()
        assert not (tmp_path / "data" / "sources" / "other" / "short.mp4.part").exists()
    finally:
        srv.shutdown()


def test_frame_grid_finds_and_rebuild_cfr_repairs_irregular_timestamps(tmp_path):
    """A clip whose frames 20.. sit one frame late (a gap) is found by frame_grid and put back on the 1/30 s grid by
    rebuild_cfr with every frame kept, in order."""
    src = tmp_path / "gap.mp4"
    # no edit list: FFmpeg 7.1's ends where the frame durations add up, which hides the frame the gap pushed past it
    media.command([media.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=2", "-vf",
                   "settb=1/15360,setpts=(N+gte(N\\,20))*512", "-fps_mode", "passthrough", "-video_track_timescale", "15360",
                   "-c:v", "libx264", "-bf", "0", "-use_editlist", "0", "-pix_fmt", "yuv420p", src])
    g = media.frame_grid(src, 30)
    assert g["frames"] == 60 and g["irregular_count"] == 1 and g["irregular"][0][0] == 20
    fixed = media.rebuild_cfr(src, 30)
    assert fixed["frames"] == 60 and fixed["irregular_count"] == 0


def test_command_done_hook_counts_a_hung_tool_as_finished():
    """A process that sleeps past the timeout is killed and its run returned the moment `done` says the work is on disk."""
    t0 = time.monotonic()
    media.command([sys.executable, "-c", "import time; print('written'); time.sleep(120)"], timeout=60, done=lambda: True)
    assert time.monotonic() - t0 < 30
    with pytest.raises(TimeoutError):
        media.command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=2, done=lambda: False)


def test_pixel_effects_reach_shots_in_both_engines(tmp_path):
    """tritone/halation/highlight_glow are catalogued for shots, but both engines applied them to layers only: the third
    Vietnam film's archival shots kept their magenta and blue casts. Shots now get the same SVG filters."""
    import json, subprocess
    src = tmp_path / "effects.cjs"
    src.write_bytes((ROOT / "engines/effects.js").read_bytes())
    code = r"""const shot={id:'p00',effects:[{name:'tritone',start_frame:0,end_frame:1,params:{amount:1}},{name:'vignette',start_frame:0,end_frame:1,params:{amount:.5}},
      {name:'halation',start_frame:4,end_frame:5,params:{}}]};
    const a=fx.pixelFilters(shot,0),b=fx.pixelFilters(shot,6),none=fx.pixelFilters({id:'x',effects:[]},0),st=fx.withPixel({filter:'contrast(1.1)'},b);
    console.log(JSON.stringify({a:a.filter,b:b.filter,nb:(b.defs.match(/<filter /g)||[]).length,none:[none.filter,none.defs],st:st.filter}));"""
    r = json.loads(subprocess.check_output(["node", "-e", "const fx=require(process.argv[1]);" + code, str(src)], text=True))
    assert r["a"] == "url(#ev-sfx-p00-0)"                      # halation not yet active at frame 0
    assert r["b"].split() == ["url(#ev-sfx-p00-0)", "url(#ev-sfx-p00-1)"] and r["nb"] == 2
    assert r["none"] == ["", ""] and r["st"].endswith("contrast(1.1)") and r["st"].startswith("url(#ev-sfx-p00-0)")
    tsx = (ROOT / "engines/AgentVideo.tsx").read_text(encoding="utf-8")
    hf = (ROOT / "engines/hyper-runtime.js").read_text(encoding="utf-8")
    assert "FX.pixelFilters(shot,frame)" in tsx and "FX.pixelFilters(v.item,vl)" in hf and "FX.pixelFilters(old," in hf


def test_live_dissolve_on_the_same_moment_is_a_grade_change(monkeypatch):
    """Grey dissolving into colour on one continuous take is not a doubled subject; a frozen or offset one still is."""
    from editvideo import review, agent, store
    from editvideo.models import Shot
    a = Shot(id="grey", beat_id="b", start_frame=0, end_frame=45, asset_id="v", source_start=.4, motion="hold").model_dump()
    b = Shot(id="colour", beat_id="b", start_frame=45, end_frame=90, asset_id="v", source_start=1.9, motion="hold",
             transition={"name": "dissolve", "duration_frames": 16, "mode": "live"}).model_dump()
    t = {"width": 1920, "height": 1080, "total_frames": 90, "shots": [a, b], "layers": [], "audio_clips": [], "design": {}, "cues": []}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": t, "revision": 1})
    monkeypatch.setattr(store, "assets", lambda pid: [{"id": "v", "kind": "video", "path": "v.mp4", "width": 1920, "height": 1080, "duration": 10}])
    codes = lambda: {(f["code"], f["level"]) for f in review.audit_timeline("p", t)["findings"]}
    assert ("grade_dissolve", "info") in codes() and not any(c == "same_clip_dissolve" for c, _ in codes())
    for motion in ("push", "pull", "pan"):  # a camera move on either side doubles the picture at the seam
        a["motion"] = motion
        assert ("same_clip_dissolve", "likely_problem") in codes(), motion
    a["motion"] = "hold"
    b["transition"]["mode"] = "freeze"
    assert ("same_clip_dissolve", "likely_problem") in codes()


def test_history_map_tells_a_campaign_step_by_step():
    """history_map: a partition, campaign markers, arrows and a trail as one timed vector layer, labels sized for 1080p."""
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    t = {"width": 1920, "height": 1080, "total_frames": 600, "shots": [], "layers": [],
         "design": {"typography": {"label": {"font_id": "notoserif", "size": 44, "weight": 600}}}}
    req = {"recipe": "history_map", "id": "m1975", "start_frame": 30, "end_frame": 330, "country": "Vietnam", "neighbors": ["Laos", "Cambodia"],
           "view": [100.5, 8.2, 111.5, 23.6],
           "cities": [{"name": "Huế", "lat": 16.46, "lon": 107.59}, {"name": "Buôn Ma Thuột", "lat": 12.67, "lon": 108.04}, {"name": "Sài Gòn", "lat": 10.78, "lon": 106.7}],
           "steps": [{"kind": "parallel", "lat": 17, "at": 10, "frames": 40, "text": "Vĩ tuyến 17"},
                     {"kind": "marker", "city": "Buôn Ma Thuột", "at": 70, "text": "Buôn Ma Thuột 10/3"},
                     {"kind": "arrow", "origin": "Buôn Ma Thuột", "to": "Sài Gòn", "at": 120, "frames": 40},
                     {"kind": "route", "points": [[20, 105.5], [16, 106.6], [12, 106.9]], "at": 180, "frames": 50, "dashed": True, "text": "Trường Sơn"}]}
    r = cinematic.history_map(t, cinematic.HistoryMap.model_validate(req))
    bg, svg = r["ops"][0]["layer"], r["ops"][1]["layer"]
    assert bg["kind"] == "shape" and svg["kind"] == "svg" and svg["start_frame"] == 30
    g = SvgGraphic.model_validate(svg["data"])
    by = {e.id: e for e in g.elements}
    assert by["s0"].type == "line" and by["s0"].draw == [10, 50] and by["s0"].dashed
    assert by["s2"].type == "arrow" and by["s2"].draw == [120, 160]
    px = svg["width"] * 1920 / svg["data"]["view_box"][0]
    assert 33 <= by["s1t"].font_size * px <= 39  # ~36 px labels on the whole map (30 px could not be read)
    zoomed = cinematic.history_map(t, cinematic.HistoryMap.model_validate(
        {**req, "steps": [{"kind": "camera", "city": "Huế", "at": 0, "frames": 30, "zoom": 3.0}, *req["steps"]]}))
    zb = {e["id"]: e for e in zoomed["ops"][1]["layer"]["data"]["elements"]}
    assert 58 <= zb["s2t"]["font_size"] * px * 3.0 <= 66  # at 3x ~62 px on screen, not 108
    import pytest
    with pytest.raises(Exception, match="arrow"):
        cinematic.HistoryMap.model_validate({**req, "steps": [{"kind": "arrow", "origin": "Hà Nội", "to": "Sài Gòn", "at": 0}]})


def test_doc_chapter_places_the_viewer_in_time():
    """doc_chapter: part/title/years/context and a strip with earlier chapters drawn and this span growing."""
    from editvideo import cinematic
    from editvideo.svg_graphics import SvgGraphic
    import pytest
    ty = {r: {"font_id": "notoserif", "size": 40, "weight": 600} for r in ("label", "headline", "caption")}
    t = {"width": 1920, "height": 1080, "total_frames": 600, "shots": [], "layers": [], "design": {"typography": ty}}
    req = {"recipe": "doc_chapter", "id": "ch3", "start_frame": 60, "end_frame": 420, "part": "PHẦN 3", "title": "Mỹ đổ quân", "years": "1965 — 1967",
           "context": "Ngày 8/3/1965, lính thủy đánh bộ Mỹ đổ bộ Đà Nẵng.", "timeline": [1945, 2025], "span": [1965, 1967],
           "marks": [1954, 1975], "done": [[1945, 1954], [1954, 1964]]}
    r = cinematic.doc_chapter(t, cinematic.DocChapter.model_validate(req))
    ids = [o["layer"]["id"] for o in r["ops"]]
    assert ids == ["ch3-card", "ch3-part", "ch3-title", "ch3-years", "ch3-context", "ch3-timeline"]
    strip = SvgGraphic.model_validate(r["ops"][-1]["layer"]["data"])
    by = {e.id: e for e in strip.elements}
    assert by["now"].draw == [12, 40] and {"d0", "d1"} <= set(by)
    assert by["d1"].x1 < by["now"].x1  # earlier chapters sit left of this one
    with pytest.raises(Exception, match="24 words"):
        cinematic.DocChapter.model_validate({**req, "context": " ".join(["chữ"] * 30)})
    # the question enters on its own after the title, and the card must hold it long enough to read twice
    ctx = next(o["layer"] for o in r["ops"] if o["layer"]["id"] == "ch3-context")
    assert ctx["effects"][0]["start_frame"] == cinematic.QUESTION_AT
    with pytest.raises(Exception, match="needs >= "):
        cinematic.DocChapter.model_validate({**req, "end_frame": 210})
    with pytest.raises(Exception, match="span"):
        cinematic.DocChapter.model_validate({**req, "span": [1940, 1950]})


def test_silent_projects_reach_documentary_length(tmp_path, monkeypatch):
    """A 12 minute documentary needs a silent timeline past the former 10 minute cap; 30 minutes is the new ceiling."""
    from editvideo import agent
    import pytest
    with pytest.raises(ValueError, match="30 min"):
        agent.create_silent("landscape", 30 * 1800 + 1)


def test_long_filter_graphs_go_through_a_file(tmp_path):
    """A 70-clip documentary mix built a filter graph past Windows' 32 767-character command line (WinError 206);
    long graphs are written to a file and FFmpeg reads them by name."""
    from editvideo.media import filter_complex_args, command, FFMPEG
    short = filter_complex_args("anullsrc=d=1[a]", tmp_path)
    assert short == ["-filter_complex", "anullsrc=d=1[a]"]
    graph = ";".join([f"sine=f={200 + k}:d=1[s{k}]" for k in range(400)] + ["".join(f"[s{k}]" for k in range(400)) + "amix=inputs=400[out]"])
    args = filter_complex_args(graph, tmp_path, "mix.txt")
    assert len(graph) > 6000 and args[1].endswith("mix.txt") and (tmp_path / "mix.txt").read_text(encoding="utf-8") == graph
    out = tmp_path / "mix.wav"
    command([FFMPEG, "-y", "-v", "error", *args, "-map", "[out]", "-t", "1", out])
    assert out.stat().st_size > 1000


def test_vietnam_map_shows_hoang_sa_and_truong_sa():
    """The owner's review: the map of Vietnam lacked Trường Sa. Vietnam's map carries both archipelagos by default and its
    default view reaches them; an explicit empty list draws none."""
    from editvideo import cinematic
    t = {"width": 1920, "height": 1080, "total_frames": 300, "shots": [], "layers": [],
         "design": {"typography": {"label": {"font_id": "montserrat", "size": 32, "weight": 500}}}}
    req = {"recipe": "history_map", "id": "m", "start_frame": 0, "end_frame": 200, "country": "Vietnam",
           "steps": [{"kind": "parallel", "lat": 17, "at": 10}]}
    els = cinematic.history_map(t, cinematic.HistoryMap.model_validate(req))["ops"][1]["layer"]["data"]["elements"]
    names = {e["text"] for e in els if e["type"] == "text"}
    assert {"Quần đảo Hoàng Sa", "Quần đảo Trường Sa"} <= names
    assert sum(1 for e in els if e["id"].startswith("isl1_") and e["type"] == "circle") >= 15
    vw, vh = cinematic.history_map(t, cinematic.HistoryMap.model_validate(req))["ops"][1]["layer"]["data"]["view_box"]
    bare = cinematic.history_map(t, cinematic.HistoryMap.model_validate({**req, "archipelagos": []}))["ops"][1]["layer"]["data"]
    assert vw / vh > 1.3 * bare["view_box"][0] / bare["view_box"][1]  # the view widened east to the Spratlys
    assert not any(e["id"].startswith("isl") for e in bare["elements"])


def test_history_map_strokes_keep_their_screen_width_labels_clear_arrows_and_read():
    """The audit of 2026-10-27: a 23-26 px border at 3.5x, labels under arrowheads, a red sublabel at 2.0:1."""
    from editvideo import cinematic
    t = {"width": 1920, "height": 1080, "total_frames": 600, "shots": [], "layers": [],
         "design": {"typography": {"label": {"font_id": "notoserif", "size": 44, "weight": 600}}}}
    base = {"recipe": "history_map", "id": "m", "start_frame": 0, "end_frame": 300, "country": "Vietnam", "neighbors": ["Laos", "Cambodia"],
            "view": [100.5, 8.2, 111.5, 23.6],
            "cities": [{"name": "Buôn Ma Thuột", "lat": 12.67, "lon": 108.04}, {"name": "Sài Gòn", "lat": 10.78, "lon": 106.7}],
            "steps": [{"kind": "arrow", "origin": "Buôn Ma Thuột", "to": "Sài Gòn", "at": 10, "frames": 30, "color": "#c0392b", "text": "Tiến công"},
                      {"kind": "marker", "city": "Sài Gòn", "at": 60, "text": "Sài Gòn 30/4"}]}
    flat = {e["id"]: e for e in cinematic.history_map(t, cinematic.HistoryMap.model_validate(base))["ops"][1]["layer"]["data"]["elements"]}
    zoom = {e["id"]: e for e in cinematic.history_map(t, cinematic.HistoryMap.model_validate(
        {**base, "steps": [{"kind": "camera", "city": "Sài Gòn", "at": 0, "frames": 10, "zoom": 3.0}, *base["steps"]]}))["ops"][1]["layer"]["data"]["elements"]}
    assert zoom["s1"]["stroke_width"] * 3.0 < flat["s0"]["stroke_width"] * 1.4  # on screen, nearly the width it has unzoomed
    assert zoom["land"]["stroke_width"] < flat["land"]["stroke_width"]
    assert flat["s0t"]["fill"].lower() != "#c0392b"  # the red arrow's words are lightened until they read on the dark map
    lab = flat["s1t"]
    tw = .55 * lab["font_size"] * len(lab["text"])
    x0 = lab["x"] - {"start": 0, "middle": tw / 2, "end": tw}[lab.get("anchor", "start")]
    head = (flat["s0"]["x2"], flat["s0"]["y2"])
    assert not (x0 - 4 <= head[0] <= x0 + tw + 4 and lab["y"] - .8 * lab["font_size"] - 4 <= head[1] <= lab["y"] + 4)  # not on the arrowhead
