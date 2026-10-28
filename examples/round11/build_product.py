"""Round-11 build P: a vertical PRODUCT REVEAL (20 s) of a CC0 3D model (BoomBox, Microsoft, Khronos glTF Sample
Assets). Product-film practice: the product waits in the dark, a rim light draws its silhouette, the key light lands
on the hit; then a close detail with a soft strip light crossing the glossy panel, a bright studio turntable in
contrast, and an end card. No footage: three Scene3D layers (compose_product reveal dark / a detail scene / reveal
slide). Sound is procedural (a drone bed, a riser into the reveal, an impact, whooshes on the changes, a sub drop under
the end card). Usage: python examples/round11/build_product.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, scene3d, sound, audiofx
store.initialize(recover=False)
MODEL = ROOT / "data" / "sources" / "other" / "product-BoomBox.glb"
N, REVEAL = 600, 45  # 20 s; the key light lands at 1.5 s (a feed decides in the first 1-2 s)
A_END, B_END, C_END = 180, 330, N  # reveal | detail | turntable + end card
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def build():
    pid = agent.create_silent("vertical", N, "remotion", "Product reveal", color="#0e0f12")["id"]
    mid = m.editvideo_import_media(pid, str(MODEL), role="illustration", tags="BoomBox, Microsoft, CC0 (Khronos glTF Sample Assets)",
                                   preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    # 1. from black: rim light, then the key light on the hit
    r = m.editvideo_compose_product(pid, rev(pid), 0, A_END, model=mid, light=1.0, reveal="dark", reveal_at=REVEAL, id="reveal")
    print("reveal beats", r["beats"], flush=True)
    # 2. detail: the camera close on the panel while a narrow strip light crosses it
    scene, beats = scene3d.product_scene(B_END - A_END, mid, size=None, light=1.0, reveal="dark", reveal_at=20, sweep=True, aspect=1080 / 1920)
    d = scene["camera_keyframes"]
    far = d[-1]["position"]["z"]
    scene["camera_keyframes"] = [{"frame": 0, "position": {"x": .6, "y": .45, "z": round(far * .52, 2)}, "target": {"x": 0, "y": .2, "z": 0}},
                                 {"frame": B_END - A_END - 1, "position": {"x": -.4, "y": .4, "z": round(far * .36, 2)}, "target": {"x": 0, "y": .2, "z": 0}}]
    scene["fog"] = {"color": "#0e0f12", "near": round(far * .66, 2), "far": round(far * 1.2, 2)}  # past the product from the farthest camera
    scene3d.compose(pid, rev(pid), {"id": "detail", "scene": scene, "start_frame": A_END, "end_frame": B_END, "x": 0, "y": 0, "width": 1, "height": 1})
    # 3. the studio turntable (bright, reflective) and the end card over its last seconds
    # one full turn from the settle (60 frames in) to the last frame: the front faces the camera again under the end card
    m.editvideo_compose_product(pid, rev(pid), B_END, C_END, model=mid, light=.9, reveal="slide", turn_deg_per_s=round(360 / ((C_END - B_END - 61) / 30), 2), id="turn")
    # hard cuts between the beats, on the whooshes: a 3D layer fading in from nothing where the previous one ends showed
    # two black frames at each change
    from editvideo.design_library import fit_size
    def T(id, text, a, b, y, size, weight=800, color="#ffffff", font="montserrat"):
        fs = fit_size(font, text, .84, 1080, weight, size, tracking=.12)
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .08, "y": y, "width": .84,
                "height": round(fs * 1.5 * (text.count(chr(10)) + 1) / 1920 + .012, 3), "z": 900, "font_id": font, "font_weight": weight, "font_size": fs, "line_height": 1.2,
                "color": color, "data": {"align": "center"},
                "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 10}, {"name": "tracking", "start_frame": 0, "end_frame": 24, "params": {"amount": .12}},
                            {"name": "fade_out", "start_frame": b - a - 10, "end_frame": b - a - 1}]}}
    agent.patch(pid, rev(pid), [
        T("t1", "NHỎ GỌN.", REVEAL + 10, A_END - 4, .2, 120),
        T("t2", "ÂM THANH LỚN.", A_END + 20, B_END - 4, .2, 110),
        T("end", "Nhỏ gọn.\nÂm thanh lớn.", C_END - 120, N - 2, .13, 110, 700),  # two lines read larger on a phone
        T("credit", "Mô hình 3D: Microsoft · Khronos glTF Sample Assets (CC0)", C_END - 110, N - 2, .72, 34, 400, "#e1e4ea", "bevietnampro"),
    ])
    # sound: a low drone bed under all, a riser into the reveal, the hit on it, whooshes on the changes, a sub drop at the end card
    bed = sound.design("drone", 20.0, 9, -20)
    bid = m.editvideo_import_media(pid, bed["path"], role="decoration", tags="procedural drone bed", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    t = agent.read(pid)["timeline"]
    t["audio_clips"] = [{"id": "bed", "asset_id": bid, "start_frame": 0, "end_frame": N, "source_start": 0, "volume": .8, "fade_in": 1.5, "fade_out": 1.5,
                         "duck_under_voice": False, "role": "ambience", "normalize": False}]
    agent.patch(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    r = audiofx.sync(pid, rev(pid), {"transitions": False, "entrances": "none", "replace": True, "hits": [
        {"frame": REVEAL, "kind": "riser"}, {"frame": REVEAL, "kind": "impact"}, {"frame": A_END, "kind": "whoosh"},
        {"frame": B_END, "kind": "whoosh"}, {"frame": C_END - 120, "kind": "sub_drop"}]})
    print("sfx", r["placed"], flush=True)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
