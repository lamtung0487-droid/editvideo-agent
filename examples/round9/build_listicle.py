"""Round-9 real build B: a vertical TikTok listicle, "3 cảnh Việt Nam nên thấy một lần", from Wikimedia Commons takes
(Hội An market CC0 Poiana11; Hạ Long Bay CC BY-SA 4.0 and Hạ Long cruise CC BY 4.0 L. Shyamal; Saigon traffic CC BY-SA
4.0 Karel Bilek), narrated offline with Piper, the item that ends the list previewed in the first frame, a 3-2-1
countdown, shots landing on the words they show, whip transitions between items, pop captions, a 124 BPM bed and a
comment CTA, mastered to -14 LUFS. Every line describes something visible in the takes.
Usage: python examples/round9/build_listicle.py [--replan]"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, agent, beatmap, sound
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
SRC = {"hoian": C / "hoian_market.webm", "halong": C / "halong_dec2024.webm", "sunset": C / "halong_cruise.webm", "saigon": C / "saigon_traffic.webm"}
STATE = ROOT / "data" / "films" / "r9-listicle.json"
SENT = [  # display | spoken (Piper reads digits poorly: numbers are spelled in the spoken text)
    ("3 cảnh Việt Nam bạn phải xem tận mắt một lần.", "Ba cảnh Việt Nam bạn phải xem tận mắt một lần."),
    ("Số 3: chợ sáng ở Hội An.", "Số ba: chợ sáng ở Hội An."),
    ("Rau xanh, thịt, trái cây bày kín sạp hàng.", "Rau xanh, thịt, trái cây bày kín sạp hàng."),
    ("Số 2: vịnh Hạ Long.", "Số hai: vịnh Hạ Long."),
    ("Hơn 1.000 hòn đảo đá vôi nhô lên giữa biển.", "Hơn một nghìn hòn đảo đá vôi nhô lên giữa biển."),  # UNESCO: some 1,600
    ("Số 1: dòng xe máy ở Sài Gòn.", "Số một: dòng xe máy ở Sài Gòn."),
    ("Cả một biển xe cùng đổ về một hướng.", "Cả một biển xe cùng đổ về một hướng."),
    ("Bạn muốn đến nơi nào trước?", "Bạn muốn đến nơi nào trước?"),
]
rev = lambda pid: m.editvideo_read_project(pid)["revision"]
f = lambda sec: int(round(sec * 30))


def project():
    if STATE.exists():
        return json.loads(STATE.read_text())["pid"]
    pid = m.editvideo_create_project({"title": "3 cảnh Việt Nam", "script": " ".join(a for a, _ in SENT), "spoken_text": " ".join(b for _, b in SENT),
                                      "profile": "vertical", "renderer": "remotion", "captions": False, "voice": "vi-VN-NamMinhNeural",
                                      "voice_backend": "piper"})["id"]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"pid": pid}))
    return pid


def main():
    pid = project()
    A = {a["name"]: a["id"] for a in store.assets(pid)}
    tags = {"hoian": "Hội An market, CC0 Poiana11", "halong": "Ha Long Bay Dec 2024, CC BY-SA 4.0", "sunset": "Ha Long cruise, CC BY 4.0 L. Shyamal",
            "saigon": "Saigon traffic, CC BY-SA 4.0 Karel Bilek"}
    for k, p in SRC.items():
        if p.name not in A:
            A[p.name] = m.editvideo_import_media(pid, str(p), role="evidence", tags=tags[k])["id"]
    cfg = store.get_project(pid)["config"]
    script, spoken = " ".join(a for a, _ in SENT), " ".join(b for _, b in SENT)
    changed = cfg.get("script") != script or cfg.get("spoken_text") != spoken
    if changed:  # a new script means new narration (Piper listen-back found words heard wrong: lines were reworded)
        store.update_project(pid, {**cfg, "script": script, "spoken_text": spoken})
    if not agent.read(pid).get("timeline") or changed or "--replan" in sys.argv:
        j = store.create_job(pid, "plan")
        m.worker.run(j["id"])
        assert m.editvideo_get_job(j["id"])["state"] == "completed", m.editvideo_get_job(j["id"])
    words = (store.read_json(store.folder(pid) / "plan" / "words.json") or {}).get("words") or []
    sents = beatmap.beat_map(pid, 0, 40)["beats"]
    assert len(sents) == len(SENT), [b["text"] for b in sents]
    t = agent.read(pid)["timeline"]
    N = t["total_frames"]
    bounds = [0] + [f(s["t"][0]) - 4 for s in sents[1:]] + [N]

    def said(i, needle):  # frame the narration says `needle` inside sentence i
        a0, b0 = sents[i]["t"]
        hit = next((w["start"] for w in words if a0 - .05 <= w["start"] <= b0 + .05 and needle in w["text"].lower()), None)
        return f(hit) - 3 if hit is not None else None

    # (asset, source s, focus x) per shot; sentence 2 is two shots, the second landing on "trái cây" (a third on
    # "thịt" would last 0.4 s: Piper says the list fast, and sub-half-second shots read as flicker, not rhythm).
    v = lambda k: A[SRC[k].name]
    cuts2 = [bounds[2], said(2, "trái") or bounds[2] + 40, bounds[3]]
    plan = [(bounds[0], bounds[1], v("saigon"), 27.0, .5, None),          # the list's last item, previewed: motion on frame 0
            (bounds[1], bounds[2], v("hoian"), 1.0, .55, "whip_left"),
            (cuts2[0], cuts2[1], v("hoian"), 47.0, .45, None),             # rau (greens on the stalls)
            (cuts2[1], cuts2[2], v("hoian"), 116.0, .5, None),             # trái cây
            (bounds[3], bounds[4], v("halong"), 0.5, .45, "whip_left"),
            (bounds[4], bounds[5], v("halong"), 9.0, .55, None),           # the boat passes a limestone island
            (bounds[5], bounds[6], v("saigon"), 20.0, .55, "whip_left"),
            (bounds[6], bounds[7], v("saigon"), 33.0, .5, None),
            (bounds[7], bounds[8], v("sunset"), 6.0, .5, "dissolve")]
    shots = []
    for i, (a, b, asset, src, fx, tr) in enumerate(plan):
        sh = {"id": f"s{i}", "beat_id": f"b{i}", "start_frame": a, "end_frame": b, "asset_id": asset, "source_start": src, "fit": "cover",
              "focus_x": fx, "focus_y": .5, "motion": "hold", "role": "evidence", "effects": []}
        if tr:
            sh["transition"] = {"name": tr, "duration_frames": 8 if tr.startswith("whip") else 12}
        shots.append(sh)
    t["shots"], t["layers"] = shots, []
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "replace_timeline", "timeline": t}])
    m.editvideo_apply_design(pid, rev(pid), {"style_id": "short_bold"})
    from editvideo.design_library import stack_line_height, fit_size
    lh = lambda text: max(1.2, stack_line_height("oswald", text.split("\n"), 700)["line_height"] + .02)
    out = lambda d: [{"name": "fade_out", "start_frame": d - 7, "end_frame": d - 1}]
    outline = lambda d, w=4: {"name": "text_outline", "start_frame": 0, "end_frame": d - 1, "params": {"color": "#000000", "amount": w}}
    T = lambda id, text, a, b, y, size, color="#ffffff", h=.1, x=.08, w=.84, **kw: {"op": "upsert_layer", "layer": {
        "id": id, "kind": "text", "text": text, "start_frame": a, "end_frame": b, "x": x, "y": y, "width": w, "height": h, "z": 900,
        "font_id": "oswald", "font_weight": 700, "font_size": fit_size("oswald", text, w, 1080, 700, size), "line_height": lh(text), "color": color,
        "effects": [{"name": "rise", "start_frame": 0, "end_frame": 6, "params": {"amount": 26}}, outline(b - a)] + out(b - a), **kw}}
    hook = "3 CẢNH VIỆT NAM\nPHẢI XEM MỘT LẦN"
    ops = [T("hook", hook, 0, bounds[1] - 1, .14, 88, h=.18)]  # on frame 0: the feed's thumbnail
    items = [(1, "3", "CHỢ HỘI AN", bounds[1], bounds[3]), (3, "2", "VỊNH HẠ LONG", bounds[3], bounds[5]), (5, "1", "XE MÁY SÀI GÒN", bounds[5], bounds[7])]
    for k, num, label, a, b in items:
        ops.append(T(f"num{num}", num, a + 2, b - 1, .13, 150, "#ffd400", h=.13, w=.16))
        ops.append(T(f"label{num}", label, a + 2, b - 1, .165, 62, h=.07, x=.25, w=.6))
    ops.append(T("cta", "BẠN CHỌN SỐ MẤY?", bounds[7] + 2, N, .14, 84, "#ffd400", h=.1))
    ops.append(T("cta2", "Bình luận 1, 2 hay 3", bounds[7] + 10, N, .25, 44, h=.05))
    ops.append(T("credit", "Video: Wikimedia Commons · Poiana11 (CC0)\nKarel Bilek, പയ്യൻ (CC BY-SA 4.0) · L. Shyamal (CC BY 4.0)",
                 bounds[7] + 10, N, .31, 28, h=.06, typography_role="source"))
    m.editvideo_patch_timeline(pid, rev(pid), ops)
    r = m.editvideo_compose_edit(pid, rev(pid), {"recipe": "word_captions", "platform": "tiktok", "id": "cap", "start_frame": 0, "end_frame": N,
                                                 "caption_style": "karaoke", "mode": "color", "accent": "#ffd400", "color": "#ffffff", "uppercase": True,
                                                 "emphasis": ["Hội", "An", "Hạ", "Long", "Sài", "Gòn", "biển"], "word_animation": "pop", "outline": .07,
                                                 "font_size": 66, "caption_y": .66})
    A = {a["name"]: a["id"] for a in store.assets(pid)}
    if "bed-124.wav" not in A:
        bed = sound.design("beat", round(N / 30 + 1, 2), 5, -12, 124)
        p = Path(bed["path"]).with_name("bed-124.wav")
        Path(bed["path"]).replace(p)
        A["bed-124.wav"] = m.editvideo_import_media(pid, str(p), role="decoration", tags="procedural beat bed 124 BPM", preserve_plan=True, base_revision=rev(pid))["asset"]["id"]
    m.editvideo_patch_timeline(pid, rev(pid), [{"op": "upsert_audio", "audio": {"id": "bed", "asset_id": A["bed-124.wav"], "start_frame": 0, "end_frame": N,
                                                                                "volume": .6, "fade_in": .2, "fade_out": .8, "duck_under_voice": True, "role": "music", "normalize": True}}])
    sfx = m.editvideo_sfx_sync(pid, rev(pid), {"replace": True}, dry_run=False)
    m.editvideo_compose_edit(pid, rev(pid), {"recipe": "audio_finish", "platform": "tiktok", "id": "master", "start_frame": 0, "end_frame": N})
    au = [(x["code"], x["level"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]
    vb = store.folder(pid) / "plan" / "voice-backend.json"
    print(json.dumps({"pid": pid, "frames": N, "timing": (store.read_json(store.folder(pid) / "plan" / "words.json") or {}).get("method"),
                      "sfx": sfx.get("placed"), "audit": au, "asr_check": (store.read_json(vb).get("asr_check") or {}).get("not_heard_as_written") if vb.exists() else None},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
