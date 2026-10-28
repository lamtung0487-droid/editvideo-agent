"""Recall -> inspect separately -> render an original example -> remember -> recall again.

Uses a pre-existing local study (no downloads). Demonstration is silent, original vector scenery in both engines.
Run after inspecting the source's 302..320 second strip, not as an automatic lesson generator.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import agent, learning, store, mcp_server as m
from editvideo.media import FFMPEG, command, sha256


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    store.initialize(recover=False)
    out = ROOT / "outputs" / "upgrade-20261017"
    out.mkdir(parents=True, exist_ok=True)
    sid = "study-6078b7eb90ced1ef"
    learning.library(item_id=sid)  # pre-existing tutorial; inspected by the calling agent
    pid = m.editvideo_create_silent_project("landscape", 12, "remotion", "Một ngày trôi qua")["id"]
    rev = lambda: store.get_project(pid)["revision"]
    t = agent.read(pid)["timeline"]
    base = t["shots"][0]
    t["shots"] = [{**base, "id": "morning", "start_frame": 0, "end_frame": 180, "source_start": 0, "text": ""},
                  {**base, "id": "evening", "start_frame": 180, "end_frame": 360, "source_start": 0, "text": "",
                   "transition": {"name": "dissolve", "duration_frames": 42, "mode": "live"}}]
    layers = []
    def shape(name, shot, x, y, w, h, color, z, geom="rectangle", **kw):
        layers.append({"id": name, "kind": "shape", "attach_shot": shot, "start_frame": 0 if shot == "morning" else 180,
                       "end_frame": 180 if shot == "morning" else 360, "x": x, "y": y, "width": w, "height": h,
                       "color": color, "z": z, "data": {"shape": geom, "corner_radius": 0}, **kw})
    for shot, sky, sun_x, sun_y, sun in [("morning", "#183e56", .21, .34, "#ffe8aa"), ("evening", "#633e52", .73, .54, "#ffa16e")]:
        shape(shot + "-sky", shot, 0, 0, 1, 1, sky, 10)
        shape(shot + "-sun", shot, sun_x, sun_y, .095, .169, sun, 12, "ellipse",
              keyframes={"y": [{"frame": 0, "value": sun_y}, {"frame": 179, "value": sun_y + .025}]})
        shape(shot + "-ground", shot, 0, .76, 1, .24, "#0c2430", 20)
        for i, (x, y, w, h) in enumerate([(.1, .65, .08, .12), (.21, .56, .1, .21), (.34, .61, .07, .16),
                                        (.47, .51, .12, .26), (.63, .63, .09, .14), (.78, .57, .12, .20)]):
            shape(f"{shot}-building-{i}", shot, x, y, w, h, "#102c38", 21)
    def text(name, content, y, size, color, start=0, end=360):
        effects = ([{"name": "fade_in", "start_frame": 0, "end_frame": 10}] if start else [])
        if end < 360:
            effects.append({"name": "fade_out", "start_frame": end - start - 10, "end_frame": end - start - 1})
        layers.append({"id": name, "kind": "text", "text": content, "start_frame": start, "end_frame": end,
                       "x": .08, "y": y, "width": .84, "height": .12, "font_id": "inter", "font_size": round(size * t["width"] / 1280),
                       "font_weight": 600, "color": color, "z": 100, "data": {"align": "left"}, "effects": effects})
    text("eyebrow", "NGÔN NGỮ DỰNG PHIM", .08, 22, "#b7d3db")
    text("title", "Một ngày trôi qua", .16, 58, "#fff5df")
    text("am", "07:00  /  BUỔI SÁNG", .84, 26, "#d5e9ea", end=174)
    text("pm", "18:00  /  BUỔI CHIỀU", .84, 26, "#ffdac3", start=228)
    t["layers"] = layers
    t["overlays"], t["cues"] = [], []
    m.editvideo_patch_timeline(pid, rev(), [{"op": "replace_timeline", "timeline": t}])
    audit = m.editvideo_audit_timeline(pid)
    store.write_json(out / "demo-audit.json", audit)
    videos = {}
    jobs = {}
    for engine in ("remotion", "hyperframes"):
        if store.get_project(pid)["config"]["renderer"] != engine:
            m.editvideo_configure_project(pid, rev(), {"renderer": engine})
        m.editvideo_export_code(pid, engine)
        job = store.create_job(pid, "final")
        m.worker.run(job["id"])
        result = store.get_job(job["id"])
        if result["state"] != "completed":
            raise RuntimeError(result)
        src = store.folder(pid) / "jobs" / job["id"] / "final.mp4"
        target = out / f"learning-demo-{engine}.mp4"
        import shutil
        shutil.copy2(src, target)
        command([FFMPEG, "-v", "error", "-i", target, "-f", "null", "-"], timeout=120)
        videos[engine] = str(target)
        jobs[engine] = job["id"]
    request = {
        "title": "Tan cảnh gợi thời gian trôi qua / temporal dissolve",
        "principle": "Chồng mờ hai cảnh có thể tạo cảm giác một quãng thời gian đã trôi qua; giữ hình dễ đọc và để câu chuyện quyết định điểm chuyển.",
        "when_to_use": "Cảnh trước và sau cùng địa điểm hoặc cùng ý, nhưng khác thời điểm; chuyển từ bối cảnh sang hành động.",
        "avoid": "Không chồng hai nhãn chữ cần đọc. Không mặc định mọi thay đổi thời gian đều phải tan cảnh; so sánh với cắt thẳng.",
        "steps": ["Quan sát chuyển động và bố cục ở hai phía điểm cắt.",
                  "Trong mẫu tự dựng này thử 42 khung ở 30 fps (1,4 giây); đây là lựa chọn cho mẫu, không phải số đo tutorial.",
                  "Giữ tiêu đề chung xuyên chuyển cảnh, tắt nhãn cũ trước và đưa nhãn mới vào sau phần chồng mờ.",
                  "Dựng và xem đoạn chuyển thực tế ở cả hai engine, điều chỉnh theo nhịp câu chuyện."],
        "tags": ["chuyển cảnh", "dissolve", "thời gian", "documentary"],
        "sources": [{"study_id": sid, "start": 302, "end": 320}],
        "examples": [{"tool": "editvideo_patch_timeline", "arguments": {"project_id": pid, "base_revision": rev(),
                       "operations": [{"op": "update_shot", "shot_id": "evening", "changes": {
                           "transition": {"name": "dissolve", "duration_frames": 42, "mode": "live"}}}]},
                      "note": "Project-specific example: reread a NEW project's shot ids and revision before adapting; never replay these ids blindly."}],
        "demonstration": {"path": videos["remotion"], "observation": "Original vector morning/evening illustration. Both engines rendered and decoded; the caller must inspect visual quality."}}
    prior = next((c for c in learning.library("temporal dissolve", kind="lesson")["items"] if c["title"] == request["title"]), None)
    saved = m.editvideo_remember_lesson(request, prior["id"] if prior else None, prior["revision"] if prior else None)
    recalled = m.editvideo_learning_library("thời gian dissolve", kind="lesson")
    result = {"project_id": pid, "videos": videos, "jobs": jobs, "lesson": saved, "recall": recalled,
              "sha256": {k: sha256(Path(v)) for k, v in videos.items()}, "source_material_in_output": False}
    store.write_json(out / "roundtrip.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
