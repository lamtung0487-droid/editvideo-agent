"""Round-12 learning test, step 2: the learned grade. Each footage piece is matched to frames of the studied film taken
at the same time of day (color_match: channel percentiles, a luma curve, saturation, skin secondary), then graded by a
durable process_color task. Results are cached in data/tmp/r12_graded.json. Usage: python examples/round12/grade_pieces.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store, media_tasks
store.initialize(recover=False)
C = ROOT / "data" / "sources" / "commons"
REF = ROOT / "data" / "references" / "beauty-of-vietnam" / "reference.mp4"
# reference frames per time of day (seconds in the studied film) and how far to pull toward them
LOOK = {"dawn": ([10.3, 21.0], .85), "day": ([21.0, 26.0, 31.0], .8), "people": ([41.0, 44.0, 46.3], .75),
        "dusk": ([67.0, 72.0, 87.0], .6), "night": ([103.0, 107.0, 118.0], .5)}
PIECES = {  # key: (file, look, start, end, sample times)
    "dawn": ("vn-day-Halong_Bay_20220801_060102271.webm", "dawn", 26.0, 44.0, [30, 35, 40]),
    "karst": ("halong_dec2024.webm", "day", 0.0, 15.6, [2, 7, 12]),
    "hue": ("hue_citadel_aerial_1080p.webm", "day", 64.0, 84.0, [68, 74, 80]),
    "hn_day": ("vn-day-H_N_i_v_Tp._H_Ch_Minh_nh_n_t_tr_n_cao.webm", "day", 48.0, 62.0, [50, 55, 60]),
    "exp": ("vn-day-Experience_Hanoi_Vietnam.webm", "day", 0.0, 100.0, [5, 36, 59, 68, 82]),
    "market": ("hoian_market.webm", "people", 0.0, 120.0, [10, 40, 80, 110]),
    "traffic": ("saigon_traffic.webm", "people", 20.0, 46.8, [28, 35, 43]),
    "basket": ("vn-people-Basket_maker_Vietnam.webm", "people", 0.0, 67.6, [10, 40, 60]),
    "buffalo": ("vn-people-Water_buffalo_Bubalus_bubalis_in_Vietnam.webm", "people", 0.0, 12.0, [6, 9]),
    "dacau": ("vn-people-_c_u_in_Hanoi.ogv", "people", 0.0, 6.1, [2, 4]),
    "moto": ("vn-people-Veturo_sur_motorciklo_tra_Hanojo.webm", "people", 0.0, 46.2, [10, 25, 38]),
    "cruise": ("halong_cruise.webm", "dusk", 0.0, 20.3, [3, 10, 17]),
    "hn_dusk": ("vn-day-H_N_i_v_Tp._H_Ch_Minh_nh_n_t_tr_n_cao.webm", "dusk", 62.0, 132.6, [72, 100, 115, 125]),
    "hn_sunset": ("vn-day-H_N_i_v_Tp._H_Ch_Minh_nh_n_t_tr_n_cao.webm", "dusk", 0.0, 12.0, [2, 7]),
    "hcm_night": ("vn-day-H_N_i_v_Tp._H_Ch_Minh_nh_n_t_tr_n_cao.webm", "night", 20.0, 49.0, [24, 33, 44]),
    "fire": ("vn-night-Dragon_Bridge_breathing_fire.ogv", "night", 0.0, 17.7, [3, 6, 12]),
    "puppets": ("vn-people-Traditional_vietnamese_water_puppetry_-_dec_2018.webm", "night", 0.0, 12.8, [3, 8]),
}
cache_f = ROOT / "data" / "tmp" / "r12_graded.json"
cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.is_file() else {}
for key, (name, look, a, b, times) in PIECES.items():
    if key in cache and Path(cache[key]["path"]).is_file():
        continue
    ref_t, strength = LOOK[look]
    mt = m.editvideo_color_match(str(C / name), times, str(REF), ref_t, strength)
    from editvideo.media import probe
    info = probe(str(C / name))
    v = next(x for x in info["streams"] if x["codec_type"] == "video")
    b = min(b, float(info["format"]["duration"]) - .05)  # the window must lie inside the source
    # consumer SDR web video without colour tags: declared Rec.709 limited range (the pipeline never guesses)
    tags = {} if v.get("color_transfer") or v.get("color_primaries") else {"input_space": "bt709"}
    if v.get("color_range") not in ("tv", "pc"):
        tags["input_range"] = "limited"  # web encoders leave the range untagged; these are limited-range consumer files
    task = m.editvideo_process_color({"path": str(C / name), "start": a, "end": b, "grade": mt["grade"], **tags})
    tid = task.get("id") or task.get("task_id")
    while True:
        st = media_tasks.get(tid)
        if st["state"] in media_tasks.TERMINAL:
            break
        time.sleep(5)
    if st["state"] != "completed":
        print(key, "FAILED", st["state"], str(st.get("message"))[:300], flush=True)
        continue
    arts = (st.get("result") or {}).get("artifacts") or {}
    path = arts.get("video") or next(iter(arts.values()), None)
    cache[key] = {"path": path, "source": name, "start": a, "end": b, "look": look, "residual": mt.get("residual"), "task": tid}
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(key, "graded", look, mt.get("residual"), path, flush=True)
print("done", len(cache))
