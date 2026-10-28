"""Vịnh Bắc Bộ 1964: a `dossier` montage from five public-domain US government documents and photographs, fetched from
Wikimedia Commons (National Archives scans published through DPLA). Runs on any machine with the core install:

    python examples/public_domain/dossier_tonkin.py            # fetch, compose, score (no render)
    python examples/public_domain/dossier_tonkin.py --render   # and render, then gates, form_arc and the licence ledger

The documents go to <EDITVIDEO_DATA>/sources/commons/tonkin-1964 with their Commons records; the film goes to
outputs/demo/vinh-bac-bo.mp4. Every file's licence is read from Commons before it is used: anything not marked public
domain stops the script.
"""
import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from editvideo import agent, cinematic as cin, ledger, montage_forms as mf, review, store
import editvideo.mcp_server as m

UA = {"User-Agent": "EditVideoAgent-example/1.0 (https://github.com/lamtung0487-droid/editvideo-agent)"}
FEDERAL = "Public domain (US federal government work)"
CABLE = "File:Cable Regarding the Attack on the USS Maddox in the Gulf of Tonkin - DPLA - 8d4c053fc577dbe78124a3599ac5accc (page {}).gif"
DOCS = [  # (Commons title, local name, the dossier item); underlines measured on the scans, snapped to the gap under each line
    (CABLE.format(1), "maddox_cable_p1", {"date": "4.8.1964", "source": "JCS 042158Z · NARA", "caption": "Điện FLASH", "focus": [.42, .5],
                                          "underline": [[.033, .396, .316], [.468, .607, .362]]}),
    (CABLE.format(2), "maddox_cable_p2", {"date": "4.8.1964", "source": "JCS 042158Z · NARA", "caption": "trang 2", "focus": [.45, .33],
                                          "underline": [[.55, .306, .356], [.057, .323, .225]]}),
    ("File:Photograph of President Lyndon B. Johnson's Midnight Address on Second Gulf of Tonkin Incident - NARA - 192482.tif", "lbj_midnight_address",
     {"kind": "photo", "date": "4.8.1964", "source": "NARA 192482", "caption": "Phát biểu nửa đêm", "focus": [.47, .25], "travel": "in"}),
    ("File:Joint Resolution for the Maintenance of Peace and Security in Southeast Asia - DPLA - 0f7693e83ae519b750f466badb772021.jpg", "tonkin_resolution",
     {"date": "10.8.1964", "source": "Public Law 88-408 · NARA", "caption": "Nghị quyết", "focus": [.48, .48],
      "underline": [[.3125, .45, .357], [.281, .521, .345]]}),
    ("File:President Lyndon B. Johnson signs Gulf of Tonkin resolution - NARA - 192484.jpg", "lbj_signs_resolution",
     {"kind": "photo", "date": "10.8.1964", "source": "NARA 192484", "caption": "Johnson ký", "focus": [.52, .5], "travel": "in", "climax": True}),
]


def _get(url, timeout=120, tries=7):
    """Commons answers with 503 or 429 now and then (a clean-machine run met four 503s in a row): wait, honouring
    Retry-After, and try again for about five minutes."""
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or k == tries - 1:
                raise
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(120, float(wait)) if wait and wait.isdigit() else 5 * 2 ** k)
        except (TimeoutError, urllib.error.URLError, ConnectionError):  # a slow line: the same download again
            if k == tries - 1:
                raise
            time.sleep(5 * 2 ** k)


def fetch(folder):
    """Each document's Commons record (licence, date, credit) and a PNG/JPG of the original scan, at most 3000 px wide."""
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    q = {"action": "query", "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "format": "json",
         "titles": "|".join(t for t, _, _ in DOCS)}
    pages = json.loads(_get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(q)))["query"]["pages"].values()
    by_title = {p["title"]: p for p in pages}
    out = {}
    for title, name, _ in DOCS:
        ii = by_title[title]["imageinfo"][0]
        md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName") or {}).get("value", "")
        if "public domain" not in lic.lower():
            raise SystemExit(f"{title}: Commons lists the licence as {lic!r}, not public domain; not used")
        target = folder / (name + (".png" if ii["mime"] == "image/gif" else ".jpg"))
        if not target.is_file():
            raw = folder / (name + ".download")
            raw.write_bytes(_get(ii["url"], timeout=600))  # the original: Commons refuses large on-the-fly thumbnails at times
            im = Image.open(raw)
            im.load()
            im = im.convert("RGB")
            if im.width > 3000:
                im = im.resize((3000, round(im.height * 3000 / im.width)), Image.LANCZOS)
            im.save(target, **({"quality": 95} if target.suffix == ".jpg" else {}))
            raw.unlink()
        out[name] = {"path": target, "url": ii["url"], "title": title[5:], "licence": lic}
        (folder / (name + ".commons.json")).write_text(json.dumps({"title": title, "url": ii["url"], "licence": lic,
                                                                   "date": (md.get("DateTimeOriginal") or {}).get("value", "")[:60]},
                                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def place_sound(pid, N, clips):
    paths, ac = {}, []
    for i, c in enumerate(clips):
        if c["path"] not in paths:
            paths[c["path"]] = m.editvideo_import_media(pid, c["path"], preserve_plan=True, base_revision=agent.read(pid)["revision"],
                                                        role="decoration", tags=f"dossier sound {c.get('kind', '')}")["asset"]["id"]
        ac.append({"id": f"snd{i}-{c.get('kind', 'sound')}", "asset_id": paths[c["path"]], "start_frame": c["start_frame"],
                   "end_frame": min(N, c["end_frame"]), "source_start": c.get("source_start", 0.0), "volume": c["volume"],
                   "fade_in": c["fade_in"], "fade_out": c["fade_out"], "role": c["role"], "duck_under_voice": False})
    t = agent.read(pid)["timeline"]
    t["audio_clips"] = ac
    t["audio_mix"] = {**(t.get("audio_mix") or {}), "target_lufs": -18, "true_peak_db": -1.5, "loudness_range": 20}
    agent.patch(pid, agent.read(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "outputs" / "demo"))
    args = parser.parse_args()
    store.initialize(recover=False)
    docs = fetch(store.DATA / "sources" / "commons" / "tonkin-1964")
    N = int(19.5 * 30)
    pid = agent.create_silent("landscape", N, "remotion", "Vịnh Bắc Bộ 1964 · dossier", color="#000000")["id"]
    items = []
    for title, name, item in DOCS:
        d = docs[name]
        ledger.register_source(d["path"], FEDERAL, "National Archives and Records Administration", d["url"], d["title"], kind="image")
        aid = m.editvideo_import_media(pid, str(d["path"]), preserve_plan=True, base_revision=agent.read(pid)["revision"],
                                      role="evidence", tags=f"document {name}")["asset"]["id"]
        items.append({"asset_id": aid, **item})
    req = {"recipe": "dossier", "id": "vbb", "start_frame": 0, "end_frame": N, "items": items, "title": "Vịnh Bắc Bộ · 1964", "seed": 3}
    r = cin.compose(pid, agent.read(pid)["revision"], req, dry_run=True)
    print(json.dumps(r["measurements"], ensure_ascii=False), r["notes"], flush=True)
    plan = r["sound_plan"]
    cin.compose(pid, agent.read(pid)["revision"], req)
    place_sound(pid, N, mf.score_dossier(plan, seed=3))
    print("project", pid, flush=True)
    if not args.render:
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)
    m.worker.start()
    job = m.editvideo_submit_job(pid, "final")
    while True:
        j = m.editvideo_get_job(job["id"])
        if j.get("state") in ("completed", "failed", "cancelled", "interrupted"):
            break
        time.sleep(10)
    files = {a["name"]: a["path"] for a in j.get("artifacts") or []}
    if "final.mp4" not in files:
        raise SystemExit(f"render {j.get('state')}: {j.get('error')}")
    video = out / "vinh-bac-bo.mp4"
    shutil.copy(files["final.mp4"], video)
    gates = review.delivery_gates(str(video), agent.read(pid)["timeline"])
    shape = mf.form_arc(str(video), plan, "dossier")
    led = ledger.project_ledger(pid, "online")
    print("video", video, "| gates", gates["pass"], "| arc", shape["pass"], "| ledger for online use:", led["verdict"], flush=True)


if __name__ == "__main__":
    main()
