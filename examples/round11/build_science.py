"""Round-11 build S: a vertical SCIENCE explainer, "how the James Webb telescope unfolds" (about 52 s), from NASA's
public-domain deployment animations (SVS 20339, NASA Goddard / Adriana Manrique Gutierrez), Webb's orbit animation
and the Cosmic Cliffs image (NASA, ESA, CSA, STScI), cut to High-Energy Adventure Theme (SRG774, CC0).
Science-explainer practice: one clear story (folded to fit a rocket -> four deployment steps in their real order ->
where it sits -> what it sees), guide the eye to the feature that matters. The vertical framing is decided per clip by
open-vocabulary detection: a compact telescope fills the frame at its detected centre, a wide one (the sunshield)
stays whole on the black of space. Usage: python examples/round11/build_science.py"""
import glob, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, music, semantic
from editvideo.media import probe
store.initialize(recover=False)
NASA, C = ROOT / "data" / "sources" / "nasa", ROOT / "data" / "sources" / "commons"
SRC = {"turn": NASA / "jwst-WEBB_360_4k_30fps_Sudio_h264.mp4", "solar": NASA / "jwst-WEBB_Solar_Array_Deployment_4k_30fps_h264.mp4",
       "shield": NASA / "jwst-WEBB_SS_qtr_4k_30fps_h264.mp4", "secondary": NASA / "jwst-WEBB_SMA_1_4k_30fps_h264.mp4",
       "wings": NASA / "jwst-WEBB_Pos_J2_Primary_Mirror_Wing_Deployment_4k_30fps_h264.mp4",
       "orbit": Path(glob.glob(str(C / "science-Animation_Of_Webb*.webm"))[0]), "cliffs": Path(glob.glob(str(C / "science-NASA_s_Webb_Reveals_Cosmic_Cliffs*"))[0])}
MUSIC = ROOT / "data" / "sources" / "other" / "music-High-Energy_Adventure_Theme.ogg"
N = 1560  # 52 s
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def framing(key, src0, seconds, region):
    """The telescope kept whole over the shot's source window and as large as the canvas region the titles leave free
    allows (semantic.frame_subject: cover at its centre, or contain framed up by a held zoom on the black of space)."""
    det = next(iter(semantic.detect([str(SRC[key])], ["space telescope", "spacecraft"], fps=1.0)["clips"].values()))
    track = max((d.get("track") or [] for d in det.values()), key=len)  # the query that saw it in the most frames
    boxes = [b for t, b in track if src0 - .5 <= t <= src0 + seconds + .5] or [b for _, b in track]
    if not boxes:
        return {"fit": "contain", "focus_x": .5, "focus_y": .5, "effects": [], "why": "no telescope detected"}
    u = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    v = next(s for s in probe(str(SRC[key]))["streams"] if s["codec_type"] == "video")
    f = semantic.frame_subject(u, int(v["width"]), int(v["height"]), 1080, 1920, region=region)
    return {**f, "why": f"telescope spans {u[2] - u[0]:.2f} of the width: {f['fit']} {f['effects'][0]['params']['amount'] if f['effects'] else ''} -> {f['subject']}"}


def build():
    st = music.structure(str(MUSIC))
    m0 = 8.16  # the excerpt: 8 s of build into the section change at 16.16 s (round 10's measurement of this track)
    downs = [round((b - m0) * 30) for b in st["downbeats"] if 0 <= b - m0 < N / 30 + 2]
    D = lambda k: downs[k] if k < len(downs) else N
    pid = agent.create_silent("vertical", N, "remotion", "How Webb unfolds", color="#000000")["id"]
    A = {k: m.editvideo_import_media(pid, str(p), role="evidence", tags="NASA (public domain)", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
         for k, p in SRC.items()}
    A["music"] = m.editvideo_import_media(pid, str(MUSIC), role="decoration", tags="SRG774, CC0", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    # (from bar, to bar, clip, source s, playback rate, label)
    plan = [(0, 2, "turn", 0.0, 1, "hook"), (2, 4, "turn", 14.0, 1, "problem"),
            (4, 7, "solar", 0.0, 2.5, "step 1"), (7, 11, "shield", 0.0, 2, "step 2"), (11, 14, "secondary", 0.0, 1.5, "step 3"),
            (14, 17, "wings", 0.0, 1.2, "step 4"), (17, 22, "orbit", 5.0, 1.5, "where"), (22, None, "cliffs", 0.0, 1, "payoff")]
    # each rate fits the deployment into its bars without running past the end of its clip (solar 14.3 s, wings 7.0 s);
    # the orbit starts at 5 s, after its view has turned the L2 label away from the titles at the top of a 9:16 crop
    t = agent.read(pid)["timeline"]
    base = {**t["shots"][0], "text": "", "role": "evidence", "effects": []}
    shots = []
    for i, (b0, b1, k, src0, rate, label) in enumerate(plan):
        a, b = (D(b0) if i else 0), (D(b1) if b1 is not None else N)  # the hook opens on frame 0, before the first downbeat
        if k in ("orbit", "cliffs"):
            f = {"fit": "cover", "focus_x": .5, "focus_y": .5, "effects": [], "why": "full-frame plate"}
        else:
            # the free area under the titles (hook: down to the bottom; others: between the title and the fact line)
            f = framing(k, src0, (b - a) * rate / 30, (0, .31, 1, .97) if i == 0 else (0, .31, 1, .71))
        print(label, k, f["why"], flush=True)
        sh = {**base, "id": f"j{i:02d}", "start_frame": a, "end_frame": b, "asset_id": A[k], "source_start": src0, "playback_rate": rate,
              "fit": f["fit"], "focus_x": f["focus_x"], "focus_y": f["focus_y"], "motion": "push" if k == "cliffs" else "hold", "effects": f["effects"]}
        if k == "orbit":  # cuts on the downbeats through the steps; a dissolve only where the journey to L2 passes time
            sh["transition"] = {"name": "dissolve", "duration_frames": 12}
        if k == "cliffs":
            sh["transition"] = {"name": "dip_white", "duration_frames": 14}  # the reveal of what it sees
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    t["audio_clips"] = [{"id": "music", "asset_id": A["music"], "start_frame": 0, "end_frame": N, "source_start": m0, "volume": 1.0, "fade_in": .3,
                         "fade_out": 2.0, "duck_under_voice": False, "role": "music", "normalize": True}]
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    from editvideo.design_library import fit_size
    def T(id, text, a, b, y, size, weight=700, color="#ffffff", w=.84, font="bevietnampro"):
        fs = fit_size(font, text, w, 1080, weight, size)  # every line fits its width
        return {"op": "upsert_layer", "layer": {"id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": (1 - w) / 2, "y": y, "width": w,
                "height": round(fs * 1.3 * (text.count("\n") + 1) / 1920 + .02, 3), "z": 900, "font_id": font, "font_weight": weight, "font_size": fs,
                "line_height": 1.25, "color": color, "data": {"align": "center"},
                "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": 8}, {"name": "rise", "start_frame": 0, "end_frame": 10, "params": {"amount": 18}},
                            {"name": "fade_out", "start_frame": b - a - 8, "end_frame": b - a - 1},
                            # over the nebula (not the black of space) a soft shadow keeps the lines and credits apart from the stars
                            *([{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 18}}] if id.startswith(("pay", "credit")) else [])]}}
    gold = "#f2c14e"
    step = lambda i, n, title, fact: [T(f"s{n}", f"BƯỚC {n}/4", shots[i]["start_frame"] + 6, shots[i]["end_frame"] - 2, .2, 44, 800, gold),
                                       T(f"s{n}t", title, shots[i]["start_frame"] + 10, shots[i]["end_frame"] - 2, .245, 64),
                                       T(f"s{n}f", fact, shots[i]["start_frame"] + 22, shots[i]["end_frame"] - 2, .73, 44, 500, "#d9dde6")]
    agent.patch(pid, rev(pid), [
        T("hook", "KÍNH JAMES WEBB", 4, D(2) - 2, .2, 96, 800),
        T("hook2", "mở ra trong không gian thế nào?", 14, D(2) - 2, .27, 52, 500, gold),
        T("prob", "Gương chính rộng 6,5 m —\nkhông vừa đầu tên lửa Ariane 5.", D(2) + 4, D(4) - 2, .2, 60),
        T("prob2", "Nên nó được gấp lại để phóng.", D(2) + 30, D(4) - 2, .73, 46, 500, "#d9dde6"),
        *step(2, 1, "Mở tấm pin mặt trời", "Ngay sau khi phóng, 25/12/2021"),
        *step(3, 2, "Trải tấm chắn nắng", "5 lớp, rộng cỡ một sân tennis"),
        *step(4, 3, "Vươn gương phụ", "Đưa ánh sáng từ gương chính vào thiết bị"),
        *step(5, 4, "Mở hai cánh gương chính", "18 mảnh lục giác phủ vàng"),
        T("where", "Cách Trái Đất 1,5 triệu km", shots[6]["start_frame"] + 8, shots[6]["end_frame"] - 2, .2, 64),
        T("where2", "quay quanh điểm L2, luôn khuất nắng sau tấm chắn", shots[6]["start_frame"] + 24, shots[6]["end_frame"] - 2, .265, 42, 500, "#d9dde6"),
        T("pay", "Và đây là thứ nó nhìn thấy.", shots[7]["start_frame"] + 20, N - 130, .16, 64),
        T("pay2", "“Vách núi vũ trụ”, tinh vân Carina (2022)", shots[7]["start_frame"] + 40, N - 130, .23, 44, 500, gold),
        T("credit", "NASA Goddard (SVS 20339) · NASA, ESA, CSA, STScI", N - 126, N - 2, .72, 32, 400, "#e6e8ee"),
        T("credit2", "Nhạc: SRG774 (CC0)", N - 120, N - 2, .755, 32, 400, "#e6e8ee"),
    ])
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(f["code"], f["level"]) for f in m.editvideo_audit_timeline(pid)["findings"]]
    print(json.dumps({"pid": pid, "cuts": [s["start_frame"] for s in shots], "audit": au}, ensure_ascii=False))


if __name__ == "__main__":
    build()
