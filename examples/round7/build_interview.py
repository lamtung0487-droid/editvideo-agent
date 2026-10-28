"""Round-7 real build B: an interview selects cut from NASA soundbites (public domain), English audio, Vietnamese
subtitles timed to the real words, alternating framing at every join (no jump cuts), a punch on the key phrase.
Usage: python examples/round7/build_interview.py"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, beatmap
store.initialize(recover=False)
SRC = ROOT / "data" / "sources" / "nasa" / "artemis_interview_soundbites.mp4"
TRANSCRIPT = next((ROOT / "data" / "transcripts").glob("*/transcript.json"))
STATE = ROOT / "data" / "films" / "r7-interview.json"
# Selects in story order (source seconds, cut on word boundaries from the transcript). The reel has a 5 s slug
# (silence + black) between 34.1 and 39.3: the first answer is two selects around it (from_segments reports such gaps).
SEG = [(28.0, 34.25), (39.3, 45.15), (164.4, 173.75), (132.9, 139.65), (290.6, 295.25), (297.6, 304.6)]
# Vietnamese subtitles: (source start, source end, text) — translated from the transcript, one line each.
SUB = [(28.1, 30.9, "Người chị em song sinh của Apollo tên là Artemis,"),
       (31.2, 34.15, "và Artemis chính là nữ thần Mặt Trăng."),
       (39.6, 45.0, "Vậy là 50 năm sau Apollo, ta có một chương trình mới mang tên người chị em ấy."),
       (164.5, 165.9, "Mặt Trăng là nơi thử thách."),
       (165.9, 173.6, "Không chỉ là làm sao đến đó, mà khi đã đến, sống và làm việc bằng tài nguyên của một thế giới khác."),
       (133.0, 134.4, "Băng nước chính là sự sống."),
       (134.4, 139.5, "Là nước để uống, không khí để thở, và cũng là nhiên liệu tên lửa."),
       (290.7, 295.1, "Tôi chưa ra đời vào thời Apollo. Chương trình ấy đã thôi thúc cả cuộc đời tôi."),
       (297.7, 304.45, "Khi ta dám làm điều lớn lao, táo bạo, ta chắc chắn sẽ truyền cảm hứng cho thế hệ sau.")]
rev = lambda pid: m.editvideo_read_project(pid)["revision"]


def to_timeline(src_s):
    """Source seconds → timeline seconds through the selects (segments are cut at whole frames)."""
    cursor = 0.0
    for a, b in SEG:
        n = int((b - a) * 30 + 1e-6) / 30
        if a <= src_s <= a + n + 1e-6:
            return cursor + (src_s - a)
        cursor += n
    raise ValueError(src_s)


def srt(rows):
    ts = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(round(s % 1 * 1000)) % 1000:03d}"
    return "\n".join(f"{i + 1}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(rows))


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not state.get("pid") or state.get("seg") != [list(s) for s in SEG]:  # new selects: new project
        r = m.editvideo_project_from_video(str(SRC), "landscape", "remotion", "Vì sao quay lại Mặt Trăng?", segments=[list(s) for s in SEG])
        state = {"pid": r["id"], "seg": [list(s) for s in SEG], "gaps": r.get("gaps", [])}
    pid = state["pid"]
    t = agent.read(pid)["timeline"]
    if "base_shots" not in state:  # the selects cut as created: every run starts from it (re-runnable build)
        base = [s for s in t["shots"] if "-p" not in s["id"]]
        for i, sh in enumerate(base):  # undo earlier punch splits: each select runs to the next one
            sh["end_frame"] = base[i + 1]["start_frame"] if i + 1 < len(base) else t["total_frames"]
        state["base_shots"] = base
        STATE.write_text(json.dumps(state))
    t["shots"] = json.loads(json.dumps(state["base_shots"]))
    for sh in t["shots"]:
        sh.pop("transition", None)
    # Alternate framing at every join (the same camera set-up joined to itself is a jump cut): wide / close.
    for k, sh in enumerate(t["shots"]):
        sh["effects"] = [e for e in sh.get("effects", []) if e["name"] != "focus_zoom"]
        if k % 2:
            sh["effects"].append({"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .16, "focus_x": .5, "focus_y": .35, "cut": True}})
    t["layers"] = []
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    m.editvideo_apply_design(pid, rev(pid), {"style_id": "monochrome_focus", "palette_id": "amber", "heading_font_id": "oswald", "body_font_id": "inter"})
    rows = [(round(to_timeline(a), 3), round(to_timeline(b), 3), txt) for a, b, txt in SUB]
    m.editvideo_set_captions(pid, rev(pid), srt(rows))
    cfg = store.get_project(pid)["config"]
    store.update_project(pid, {**cfg, "captions": True})
    N = t["total_frames"]
    L = lambda **kw: {"op": "upsert_layer", "layer": {"z": 300, **kw}}
    m.editvideo_patch_timeline(pid, rev(pid), [
        L(id="topic", kind="text", text="VÌ SAO QUAY LẠI MẶT TRĂNG?", start_frame=12, end_frame=150, x=.06, y=.07, width=.6, height=.07, font_id="oswald",
          font_weight=600, font_size=46, color="#ffffff", effects=[{"name": "fade_in", "end_frame": 10}, {"name": "fade_out", "start_frame": 126, "end_frame": 137},
                                                                  {"name": "shadow", "end_frame": 1, "params": {"amount": 14}}]),
        L(id="source", kind="text", text="Tư liệu: NASA · Artemis", start_frame=12, end_frame=150, x=.06, y=.135, width=.6, height=.05,
          font_id="inter", font_weight=500, font_size=28, color="#e8b04a", effects=[{"name": "fade_in", "start_frame": 6, "end_frame": 16},
                                                                                     {"name": "fade_out", "start_frame": 126, "end_frame": 137}]),
    ])
    # Punch on the line the piece hangs on ("rocket fuel").
    # Long answers get punch-ins on their turning phrases ("so 50 years after Apollo", "it's not just about", "rocket
    # fuel", "you're definitely going to motivate"): the picture changes where the thought turns.
    m.editvideo_punch_in(pid, rev(pid), frames=[int(to_timeline(src) * 30) for src in (31.2, 42.8, 165.9, 138.6, 301.3)], scale=1.1, anchor=[.5, .35], min_gap_s=3, ladder=True)
    # One wide/close alternation across every cut (select joins and punches alike), so no cut lands on the same size.
    t = agent.read(pid)["timeline"]
    for k, sh in enumerate(t["shots"]):
        sh["effects"] = [e for e in sh.get("effects", []) if not (e["name"] == "focus_zoom" and (e.get("params") or {}).get("cut"))]
        if k % 2:
            sh["effects"].append({"name": "focus_zoom", "start_frame": 0, "end_frame": 1, "params": {"amount": .16, "focus_x": .5, "focus_y": .35, "cut": True}})
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "update_shot", "shot_id": sh["id"], "changes": {"effects": sh["effects"]}} for sh in t["shots"]])
    bm = beatmap.beat_map(pid, 0, 40)
    au = [(x["code"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]
    print(json.dumps({"pid": pid, "frames": N, "select_gaps": state.get("gaps"), "rhythm": bm["rhythm"], "beat_findings": bm["findings"][:6], "audit": au}, ensure_ascii=False)[:2500])
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)


if __name__ == "__main__":
    main()
