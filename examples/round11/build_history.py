"""Round-11 build H: a 16:9 ARCHIVAL explainer, "Cầu Long Biên" (70 s), from public-domain and CC0 archive images on
Wikimedia Commons: Léon Busy's 1915-16 autochromes (musée Albert-Kahn, CC0), period postcards (public domain; one from
NYPL), the 1902 city map (BnF Gallica, public domain), a 1920-40 photograph (Leiden University Libraries / KITLV,
CC BY 4.0), a 1972 USAF reconnaissance photograph (public domain) and Paul Doumer's portrait (public domain).
Archival practice: decide what each still is for; moves of 5-8 % toward the detail that carries the sentence, mixed with
holds, pans and a pull-back; a map to orient (zoom from the city to the bridge, with a label on it); a paper click on
each new photograph. The pushes aim at the bridge where open-vocabulary detection found it; the NYPL scan is cropped to
the postcard it detected. Sound is synthesized (a low bed, drizzle under the rain photograph, the clicks).
Facts on screen are limited to well-documented ones (opened 1902, 19 steel spans by Daydé & Pillé, the first bridge across the Red River,
named after Governor-General Paul Doumer, bombed 1967-1972). Usage: python examples/round11/build_history.py"""
import glob, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, semantic, sound, audiofx
from editvideo.media import working_copy
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
g = lambda pat: next(iter(sorted(C.glob(f"history-{pat}*"))), None)
SRC = {"sunset": g("Des_sampans_au_soleil"), "drizzle": g("Des_sampans_sur"), "doumer_card": g("Hano_-_Le_Pont_Doumer"),
       "nypl": g("Tonkin_-_Hanoi"), "aerial": g("Hanoi_Le_Petit_Lac"), "kitlv": g("Indo_China_Hanoi_KITLV"), "rice": g("Le_pont_Doumer_et_les_rizi"),
       "1972": g("Long_Bien_Bridge"), "portrait": g("Paul_Doumer"), "map": g("Plan_de_la_ville"), "lake": g("Le_Grand_Lac")}
N = 2100  # 70 s
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def subject(key, query="bridge", fit="cover", focus=(.5, .5)):
    """Where `query` was detected in a still, as canvas shares through the shot's fit and focus (a 4:3 photo framed
    16:9 shifts it), or None."""
    from PIL import Image
    path = working_copy(SRC[key])[0]
    det = semantic.detect([str(path)], [query], fps=1)
    best = next(iter(det["clips"].values()))[query].get("best")
    if not best:
        return None
    w, h = Image.open(path).size
    return semantic.to_canvas(best["box"], w, h, 1920, 1080, fit, *focus)


def build():
    have = {k: v for k, v in SRC.items() if v}
    print("sources", sorted(have), flush=True)
    pid = agent.create_silent("landscape", N, "remotion", "Cầu Long Biên", color="#16120e")["id"]
    A = {k: m.editvideo_import_media(pid, str(p), role="evidence", tags="archive, Wikimedia Commons", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
         for k, p in have.items()}
    centre = lambda b, dx=0, dy=0: (round((b[0] + b[2]) / 2 + dx, 3), round((b[1] + b[3]) / 2 + dy, 3))
    push = lambda n, amount, fx, fy, hold=0.0: [  # a slow move toward (fx, fy); hold: an instant zoom first (hides plate borders)
        *([{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": hold, "cut": True, "focus_x": fx, "focus_y": fy}}] if hold else []),
        {"name": "focus_zoom", "start_frame": 0, "end_frame": n - 1, "params": {"amount": amount, "focus_x": fx, "focus_y": fy}}]
    bx = {k: subject(k) for k in ("sunset", "rice", "kitlv", "doumer_card")}
    # the aerial view's bridge is a thin line near its top edge: a centred 16:9 crop cuts it away, so the frame is set on it
    bx["aerial"] = subject("aerial", focus=(.5, .15))
    card = subject("nypl", "postcard", focus=(.5, .482))  # framed on the postcard (its centre, measured below)
    print("bridge boxes", bx, "postcard", card, flush=True)
    sx, sy = centre(bx["sunset"]) if bx["sunset"] else (.3, .42)
    rx, ry = centre(bx["rice"]) if bx["rice"] else (.3, .6)
    ax, ay = centre(bx["aerial"]) if bx["aerial"] else (.62, .15)
    cx, cy = centre(card) if card else (.5, .48)  # with the focus on the card's centre, it stays where it was in the scan
    cz = round(1 / max(.3, card[2] - card[0]) - 1, 3) if card else .5  # the postcard fills the width
    vignette = lambda n: {"name": "vignette", "start_frame": 0, "end_frame": n - 1, "params": {"amount": .35}}
    # (key, frames, fit, focus x, focus y, effects(n), motion, transition)
    # the opening push holds a 14 % zoom about a point kept off the edges, so the autochrome's plate border and label
    # stay outside the frame (zooming about a point near an edge leaves that edge where it was)
    plan = [("sunset", 180, "cover", .5, .5, lambda n: push(n, .07, min(.75, max(.25, sx)), min(.75, max(.25, sy)), .14), "hold", None),
            ("map", 120, "contain", .5, .5, lambda n: [{"name": "focus_zoom", "start_frame": 0, "end_frame": n - 1, "params": {"amount": .05}}], "hold", "dissolve"),
            # into the bridge on the 1902 map: the zoom's fixed point sits on the bridge line, measured on the first frame of
            # this cover framing (.6, .335); measured on the contained map before it, (.6, .30) fell on the sandbank above
            ("map", 150, "cover", .6, .30, lambda n: push(n, .9, .6, .335), "hold", None),
            ("nypl", 180, "cover", .5, cy, lambda n: push(n, .05, cx, cy, cz), "hold", "dissolve"),
            ("doumer_card", 150, "cover", .5, .5, lambda n: push(n, .05, .45, .62, .04), "hold", None),  # cuts and dissolves alternate
            ("rice", 180, "cover", .5, .5, lambda n: push(n, .07, rx, ry, .1), "hold", "dissolve"),
            ("drizzle", 150, "cover", .5, .5, lambda n: push(n, .05, .55, .4, .1), "pan", None),
            *([("lake", 120, "contain", .5, .5, lambda n: [], "hold", "dissolve")] if "lake" in A else []),
            ("aerial", 180, "cover", .5, .15, lambda n: push(n, .3, ax, ay), "hold", None),
            ("1972", 210, "cover", .5, .5, lambda n: push(n, .06, .5, .3), "hold", "dip_black"),
            ("kitlv", 240, "cover", .5, .5, lambda n: [], "pull", "dissolve")]
    used = sum(p[1] for p in plan)
    plan.append(("sunset", N - used, "cover", .5, .5, lambda n: [{"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .1, "cut": True}}],
                 "pull", "dissolve"))  # the end: back to the river at sunset, pulling away, under the credits
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "text": "", "role": "evidence", "source_start": 0, "playback_rate": 1}
    shots, at = [], 0
    for i, (k, n, fit, fx, fy, fxs, motion, tr) in enumerate(plan):
        eff = [*fxs(n), vignette(n)]
        if k == "1972":
            eff.append({"name": "saturate", "start_frame": 0, "end_frame": n - 1, "params": {"amount": 0}})
        sh = {**base, "id": f"h{i:02d}", "start_frame": at, "end_frame": at + n, "asset_id": A[k], "fit": fit, "focus_x": fx, "focus_y": fy, "motion": motion, "effects": eff}
        if tr:
            sh["transition"] = {"name": tr, "duration_frames": 24 if tr == "dip_black" else 16}
        shots.append(sh)
        at += n
    t["shots"], t["layers"] = shots, []
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    S = {sh["id"]: sh for sh in shots}
    start = lambda i: shots[i]["start_frame"]
    end = lambda i: shots[i]["end_frame"]
    idx = {k: next(i for i, p in enumerate(plan) if p[0] == k and (k != "map" or p[2] == want)) for k, want in
           (("map", "cover"), ("nypl", None), ("doumer_card", None), ("rice", None), ("drizzle", None), ("aerial", None), ("1972", None), ("kitlv", None))}
    from editvideo.design_library import fit_size, layout_text
    def T(id, text, a, b, x, y, size, w=.6, font="bevietnampro", weight=500, color="#f3ead8", plate="#16120ecc", align="left"):
        fs = fit_size(font, text, w, 1920, weight, size)
        lines = text.count("\n") + 1
        if plate:  # the plate hugs its text (a fixed .62 plate had run 1190 px under 700 px of words), on the side it is aligned to
            fit = min(w, (max(layout_text(font, text, fs, round(w * 1920), weight)["line_widths"]) + 64) / 1920)
            x, w = (x + w - fit if align == "right" else x), fit
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": x, "y": y, "width": w,
                "height": round(fs * 1.35 * lines / 1080 + .03, 3), "z": 900, "font_id": font, "font_weight": weight, "font_size": fs, "line_height": 1.3,
                "color": color, **({"background": plate} if plate else {}), "data": {"align": align},
                "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}, {"name": "fade_out", "start_frame": b - a - 12, "end_frame": b - a - 1}]}}
    cap = lambda id, text, i, delay=14: T(id, text, start(i) + delay, end(i) - 6, .05, .8, 40, .62)
    # over a pale sunset sky the title needs its own plate (audit low_contrast_plate measured 1.2:1 without one)
    ops = [T("title", "CẦU LONG BIÊN", 20, 172, .52, .08, 110, .44, "notoserif", 700, "#fff4dc", "#16120ed9", "right"),
           T("title2", "Hơn 120 năm bắc qua sông Hồng", 40, 172, .52, .245, 42, .44, weight=500, color="#f2c97a", plate="#16120ed9", align="right"),
           T("map1", "Hà Nội, bản đồ năm 1902", start(1) + 8, end(1) - 4, .05, .08, 36, .36),
           cap("c2", "1902: cây cầu đầu tiên bắc qua sông Hồng", idx["map"]),
           cap("c3", "Thép, 19 nhịp: hãng Daydé & Pillé xây 1898–1902", idx["nypl"]),  # no length: the postcard prints its own 1800 m
           cap("c4", "Mang tên Toàn quyền Đông Dương Paul Doumer", idx["doumer_card"]),
           cap("c5", "Ảnh màu năm 1915: ruộng lúa ven sông, dưới chân cầu", idx["rice"]),
           cap("c6", "1916: thuyền trên sông Hồng trong mưa phùn, phía bắc cầu", idx["drizzle"]),  # the photograph's own title
           cap("c8", "Từ trên cao: Hồ Gươm, phố cũ và cây cầu phía xa", idx["aerial"]),
           cap("c9", "1967–1972: cầu bị ném bom nhiều lần,\nnhững nhịp gãy lại được nối", idx["1972"], 20),
           cap("c10", "Đường sắt ở giữa, hai bên dành cho xe và người đi bộ", idx["kitlv"], 30),
           # the closing line over the last shot, not over a 1920-40 photograph it would misdate
           T("end", "Hơn 120 năm, cây cầu vẫn đứng đó.", start(len(shots) - 1) + 12, N - 4, .05, .08, 56, .9, "notoserif", 700, "#fff4dc", "#16120ed9"),
           T("cr1", "Tư liệu: Léon Busy, musée Albert-Kahn (CC0) · NYPL · KITLV (CC BY 4.0)", end(len(shots) - 2) + 10, N - 4, .05, .78, 30, .9),
           T("cr2", "BnF Gallica · USAF · Wikimedia Commons · Âm thanh: tổng hợp offline", end(len(shots) - 2) + 16, N - 4, .05, .845, 30, .9)]
    if "lake" in A:
        il = next(i for i, p in enumerate(plan) if p[0] == "lake")
        ops.append(cap("c7", "Hồ Tây, 1921: thước phim của Léon Busy", il, 10))
    agent.patch(pid, rev(pid), ops)
    # the bridge on the map: a label pointing at it (the push keeps its focus point fixed on screen)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "tracked_callout", "id": "mapcall", "start_frame": start(idx["map"]) + 40, "end_frame": end(idx["map"]) - 4,
                                             "text": "Cầu Paul Doumer", "target": [.6, .335], "label_point": [.66, .12], "accent": "#f2c97a", "font_size": 40})
    # Paul Doumer's portrait over the postcard's stamps (top right)
    i4 = idx["doumer_card"]
    agent.patch(pid, rev(pid), [{"op": "upsert_layer", "layer": {"id": "portrait", "kind": "image", "asset_id": A["portrait"], "start_frame": start(i4) + 20,
        "end_frame": end(i4) - 2, "x": .72, "y": .06, "width": .2, "height": .41, "z": 850, "fit": "cover",
        "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 12}, {"name": "rounded", "start_frame": 0, "end_frame": 120, "params": {"amount": 10}},
                    {"name": "border", "start_frame": 0, "end_frame": 120, "params": {"amount": 3, "color": "#f2c97a"}},
                    {"name": "fade_out", "start_frame": end(i4) - start(i4) - 32, "end_frame": end(i4) - start(i4) - 23}]}}])
    # sound: a low bed, drizzle leading and trailing the rain photograph, a paper click on each new photograph
    bed = sound.design("drone", 60.0, 4, -22)
    rain = sound.design("rain", 9.0, 8, -18)
    ids = {k: m.editvideo_import_media(pid, r["path"], role="decoration", tags=f"synthesized {k}", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
           for k, r in (("bed", bed), ("rain", rain))}
    t = agent.read(pid)["timeline"]
    i6 = idx["drizzle"]
    t["audio_clips"] = [{"id": "bed", "asset_id": ids["bed"], "start_frame": 0, "end_frame": 1800, "source_start": 0, "volume": .7, "fade_in": 2, "fade_out": 1.5,
                         "duck_under_voice": False, "role": "ambience", "normalize": False},
                        # beds run up to 60 s: a second pass of the same bed overlaps the first and carries the last 11 s
                        {"id": "bed2", "asset_id": ids["bed"], "start_frame": 1755, "end_frame": N, "source_start": 30.0, "volume": .7, "fade_in": 1.5,
                         "fade_out": 2.5, "duck_under_voice": False, "role": "ambience", "normalize": False},
                        {"id": "rain", "asset_id": ids["rain"], "start_frame": start(i6) - 20, "end_frame": end(i6) + 30, "source_start": 0, "volume": .6,
                         "fade_in": .6, "fade_out": 1.0, "duck_under_voice": False, "role": "ambience", "normalize": False}]
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    audiofx.sync(pid, rev(pid), {"transitions": False, "entrances": "none", "replace": True,
                                  "hits": [{"frame": sh["start_frame"], "kind": "shutter"} for sh in shots[1:-1] if sh["asset_id"] != A.get("lake")]})
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "youtube_long", "id": "master", "start_frame": 0, "end_frame": N,
                                             "audio_mix": {"target_lufs": -20, "true_peak_db": -1.5, "loudness_range": 11}})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "cuts": [s["start_frame"] for s in shots], "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
