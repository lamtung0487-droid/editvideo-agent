"""Round-7 real build C: an 18 s vertical (9:16) promo from NASA footage + a 3D model, silent, on-screen text only.
Structure from ad_plan (hook → problem → demo → proof → goal → CTA), typography from the impact_title combo, the 1972
beat from the archival_film combo. Usage: python examples/round7/build_ad.py"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, beatmap
from editvideo.effect_guide import COMBOS
store.initialize(recover=False)
NS = ROOT / "data" / "sources" / "nasa"
STATE = ROOT / "data" / "films" / "r7-ad.json"
rev = lambda pid: m.editvideo_read_project(pid)["revision"]
N = 540
CUT = [0, 50, 118, 176, 262, 340, 396, N]  # beats sized by content (hook short, CTA held), not equal


def project():
    if STATE.exists():
        return json.loads(STATE.read_text())["pid"]
    carrier = ROOT / "data" / "films" / "carrier-ad-vertical.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x050607:s=1080x1920:r=30:d={N / 30}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(carrier)], check=True)
    pid = m.editvideo_project_from_video(str(carrier), "vertical", "remotion", "Artemis · quảng cáo dọc")["id"]
    STATE.write_text(json.dumps({"pid": pid}))
    return pid


def stack(name, start, end):
    """A combo's effects timed for one layer (looks immediate, moves over the entrance)."""
    out = []
    for e in COMBOS[name]["stack"]:
        look = e["name"] in ("motion_blur", "highlight_glow", "tritone", "halation", "vignette", "rgb_split", "bloom")
        loop = e["name"] in ("gate_weave", "handheld", "jitter", "boil")
        out.append({"name": e["name"], "start_frame": 0 if look or loop else start, "end_frame": end if loop else (1 if look else start + 14),
                    "params": e.get("params", {}), "easing": "smooth"})
    return out


def main():
    pid = project()
    A = {a["name"]: a["id"] for a in store.assets(pid)}
    for name, path in (("launch_tracking.mp4", NS / "launch_tracking.mp4"), ("earthrise_saw4.mp4", NS / "earthrise_saw4.mp4"),
                       ("rollout_aerials.mp4", NS / "rollout_aerials.mp4"), ("apollo_lunar_module.glb", ROOT / "data/sources/models/apollo_lunar_module.glb")):
        if name not in A:
            A[name] = m.editvideo_import_media(pid, str(path), role="evidence", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    t = agent.read(pid)["timeline"]
    # 720p sources on a 1080x1920 canvas are already 2.7x enlarged by cover: pushes stay small (soft_upscale audit).
    plan = [("launch_tracking.mp4", 43.0, .5, .78, .04), (None, 0, .5, .5, 0), ("launch_tracking.mp4", 47.0, .5, .45, 0),
            ("earthrise_saw4.mp4", 20.0, .6, .5, 0), ("earthrise_saw4.mp4", 30.0, .57, .77, .06), ("rollout_aerials.mp4", 20.0, .5, .5, 0),
            ("earthrise_saw4.mp4", 36.0, .57, .7, .02)]
    shots = []
    for i, ((asset, src, fx, fy, zoom), a, b) in enumerate(zip(plan, CUT, CUT[1:])):
        sh = {"id": f"c{i}", "beat_id": f"b{i}", "start_frame": a, "end_frame": b, "fit": "cover", "motion": "hold", "focus_x": fx, "focus_y": fy,
              "role": "evidence", "text": ""}
        if asset:
            sh.update(asset_id=A[asset], source_start=src)
        sh["effects"] = [{"name": "focus_zoom", "start_frame": 0, "end_frame": b - a - 1, "easing": "linear", "params": {"amount": .04 + zoom, "focus_x": fx, "focus_y": fy}}]
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    m.editvideo_apply_design(pid, rev(pid), {"style_id": "monochrome_focus", "palette_id": "amber", "heading_font_id": "oswald", "body_font_id": "inter"})
    # 1972: the Lunar Module as an archival product shot.
    m.editvideo_compose_product(pid, rev(pid), CUT[1], CUT[2], model=A["apollo_lunar_module.glb"], id="lm", turn_deg_per_s=30, light=.38, ground=False, studio=False, bloom=False, size=3.0)
    lm = next(l for l in agent.read(pid)["timeline"]["layers"] if l["id"] == "lm")
    lm["effects"] = stack("archival_film", 0, CUT[2] - CUT[1]) + [{"name": "fade_in", "start_frame": 0, "end_frame": 6}]
    ops = [{"op": "upsert_layer", "layer": lm}]

    from editvideo.design_library import stack_line_height

    def big(i, lid, text, y=.38, size=150, delay=4, width=.76):
        a, b = CUT[i], CUT[i + 1]
        lh = max(1.05, stack_line_height("oswald", text.split("\n"), 700)["line_height"]) if "\n" in text else 1.05
        ops.append({"op": "upsert_layer", "layer": {"id": lid, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .06, "y": y, "width": width,
                                                    "height": .24, "z": 400, "font_id": "oswald", "font_weight": 700, "font_size": size, "line_height": lh,
                                                    "color": "#ffffff", "data": {"align": "center"},
                                                    "effects": stack("impact_title", delay, b - a) + [{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 24}}]}})

    def small(i, lid, text, y=.6, delay=6, width=.76):
        a, b = CUT[i], CUT[i + 1]
        ops.append({"op": "upsert_layer", "layer": {"id": lid, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": .06, "y": y, "width": width,
                                                    "height": .06, "z": 400, "font_id": "inter", "font_weight": 600, "font_size": 52, "color": "#e8b04a",
                                                    "data": {"align": "center"}, "effects": [{"name": "fade_in", "start_frame": delay, "end_frame": delay + 8},
                                                                                              {"name": "rise", "start_frame": delay, "end_frame": delay + 10, "params": {"amount": 16}},
                                                                                              {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 18}}]}})
    big(0, "hook", "39 TRIỆU\nNEWTON", y=.16, size=170, delay=2)
    big(1, "last", "LẦN CUỐI:\n1972", y=.09, size=150)
    small(1, "last-sub", "Apollo 17 rời Mặt Trăng", y=.262)
    big(2, "sls", "SLS", y=.1, size=200)
    small(2, "sls-sub", "tên lửa mạnh nhất NASA", y=.26)
    big(3, "orion", "ORION", y=.5, size=180, width=.66)
    small(3, "orion-sub", "tàu chở người mới", y=.7, width=.66)
    big(4, "far", "432.210 KM", y=.5, size=150)
    small(4, "far-sub", "kỷ lục tàu chở người", y=.64)
    big(5, "goal", "TRỞ LẠI\nMẶT TRĂNG", y=.36, size=160)
    big(6, "cta", "THEO DÕI\nARTEMIS", y=.34, size=150, delay=6)
    small(6, "cta-url", "nasa.gov/artemis", y=.56, delay=14)
    ops.append({"op": "upsert_layer", "layer": {"id": "credit", "kind": "text", "text": "Tư liệu: NASA", "start_frame": CUT[6], "end_frame": N,
                                                "x": .06, "y": .64, "width": .76, "height": .04, "z": 400, "font_id": "inter", "font_size": 30, "color": "#b8bec6",
                                                "data": {"align": "center"}, "effects": [{"name": "fade_in", "start_frame": 14, "end_frame": 24}]}})
    ops.append({"op": "upsert_layer", "layer": {"id": "end-dim", "kind": "shape", "start_frame": CUT[6], "end_frame": N, "x": 0, "y": 0, "width": 1, "height": 1, "z": 300,
                                                "color": "#000000", "data": {"shape": "rectangle", "corner_radius": 0},
                                                "keyframes": {"opacity": [{"frame": 0, "value": 0}, {"frame": 10, "value": .55}, {"frame": N - CUT[6] - 12, "value": .55},
                                                                          {"frame": N - CUT[6] - 1, "value": 1}]}}})
    m.editvideo_patch_timeline(pid, rev(pid), ops)
    # The opening runs at about twice the body's event rate: a punch into the flame mid-hook.
    m.editvideo_punch_in(pid, rev(pid), frames=[26], scale=1.14, anchor=[.5, .78], min_gap_s=1)
    ad = m.editvideo_ad_audit(pid, product_layers=["lm"], cta_layer="cta", platform="reels")
    au = [(x["code"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]
    print(json.dumps({"pid": pid, "ad_audit": {k: ad[k] for k in ad if k in ("findings", "score", "summary", "issues")}, "audit": au}, ensure_ascii=False)[:3000])
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)


if __name__ == "__main__":
    main()
