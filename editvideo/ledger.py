"""Licence ledger: every asset a project uses, where it came from, under what licence, where it appears and for how
long, and whether the cut may go out for a given use (reports/Nâng cấp 3D phim tài liệu.md: "a licence ledger for every
asset"; round 13's films mixed public-domain NARA reels with copyrighted newsreels downloaded for internal research).

Origins come from the library (resources.trace_origin follows imports, media tasks and copies back to a record). A cut
of an archive reel is registered as derived from its reel (register_cut), a render as the sum of its inputs
(register_render), so a clip carries its reel's licence into every later project. Classes, most restrictive first:
unknown, internal_only, no_derivatives, noncommercial, generated, stock, share_alike, public_domain, open, procedural.
A licence string that names several sources ("A + B") takes the most restrictive class it contains.

Uses: "internal" (research and review: nothing blocks, unknowns are listed), "online" (YouTube and the like, monetised
or not), "broadcast". The ledger states obligations (credit, share-alike notice, AI/3D labelling, the stock licence's
terms) next to blockers. It reports what the records say; it is not legal advice and does not establish rights.
"""
import csv, json, os, re
from pathlib import Path
from . import resources, store

ORDER = ("unknown", "internal_only", "editorial", "no_derivatives", "noncommercial", "generated", "stock", "share_alike", "public_domain", "open",
         "procedural")
BLOCKS = {"internal": (), "online": ("unknown", "internal_only", "editorial", "no_derivatives", "noncommercial"),
          "broadcast": ("unknown", "internal_only", "editorial", "no_derivatives", "noncommercial")}
DUTY = {"open": "credit the author and licence", "share_alike": "credit, name the licence and link it; adaptations of the work stay under the same licence",
        "generated": "label as illustration (AI or 3D), keep the generation record", "stock": "within the stock licence's terms (subscription active at download)",
        "public_domain": "credit the archive as a courtesy (USGS, NARA ask for it)"}
FPS = 30
# a licence word preceded by a negation does not grant it ("not public domain", "no copyright infringement intended")
NEG = r"(?<!\bnot )(?<!\bno )(?<!\bnon-)(?<!\bnon )(?<!\bnot in the )(?<!\bnot in )"
# a grant someone only believes or reports is not a grant: "likely public domain", "claimed by the uploader"
HEDGE = r"\b(likely|probably|presumed|presumably|possibly|believed|apparently|seems|claimed|uploader|reportedly|assumed)\b"


def parts(licence):
    """{"picture": text, "audio": text} of a licence written per part ("picture: ...; audio: ..."), else None. A
    donated newsreel's picture can be free while its music and narration are not."""
    m = re.match(r"\s*picture:\s*(.*?);\s*audio:\s*(.*)$", licence or "", re.I | re.S)
    return {"picture": m.group(1).strip(), "audio": m.group(2).strip()} if m else None


def classes(licence, use=("picture", "audio")):
    """Every class a licence string names (several when sources are joined with "+"); hedged or negated grants
    ("public domain?", "not verified", "no copyright infringement intended") count as unknown, not as grants. A
    licence written per part is read for the parts in `use` only: a silent use of a newsreel's picture owes nothing
    to its sound, and a sound with "none" in it adds nothing. Joined licences are split first: a render of a
    per-part reel "+ All rights reserved" read as the reel's picture alone and was cleared."""
    comps = [c for c in re.split(r"\s\+\s", licence or "") if c.strip()]
    if len(comps) > 1:
        return set().union(*(classes(c, use) for c in comps))
    pp = parts(licence)
    if pp:
        found = set()
        for k in use:
            if k in pp and not re.match(r"\s*none\b", pp[k], re.I):
                found |= classes(pp[k])
        return found or {"public_domain"}
    s = " " + re.sub(r"\s+", " ", (licence or "").casefold()) + " "
    found = set()
    if not s.strip() or s.strip() in ("unknown", "none", "?"):
        return {"unknown"}
    if re.search(r"internal|all rights reserved|chỉ dùng nội bộ|licen[cs]e required|standard youtube licen|" + NEG + r"\bcopyrighted|not (?:in the )?public domain", s):
        found.add("internal_only")
    if re.search(r"editorial", s):
        found.add("editorial")
    if re.search(r"\bnd\b|noderiv|no derivatives|no-derivatives", s):
        found.add("no_derivatives")
    if re.search(r"\bnc\b|noncommercial|non-commercial|non commercial|phi thương mại", s):
        found.add("noncommercial")
    if re.search(r"unverified|not verified|chưa xác minh|unknown|\?|infringement intended|fair use|" + HEDGE, s):
        found.add("unknown")
    if "generated locally" in s or "procedural" in s:
        found.add("procedural")
    elif "generated" in s:
        found.add("generated")
    if re.search(r"freepik|pexels|pixabay|premium licen|stock licen", s):
        found.add("stock")
    if re.search(r"\bsa\b|sharealike|share-alike|share alike", s):
        found.add("share_alike")
    if re.search(r"cc0|" + NEG + r"public domain|no copyright in\b|no copyright\)|not copyrighted|copyright expired|federal work", s):
        found.add("public_domain")
    if re.search(r"cc[ -]?by|open font|\bofl\b|apache|\bmit\b|copernicus|attribution", s):
        found.add("open")
    return found or {"unknown"}


def classify(licence, use=("picture", "audio")):
    """The class of a licence string: the most restrictive one it names (for the parts in `use`)."""
    found = classes(licence, use)
    return next(c for c in ORDER if c in found)


def _register_outside(path, *args, **kw):
    """register_resource for a file outside the EditVideo folder (the store, the archive on another drive)."""
    p = Path(path).resolve()
    old = os.environ.get("EDITVIDEO_SOURCES")
    os.environ["EDITVIDEO_SOURCES"] = str(p.parent)
    try:
        return resources.register_resource(p, *args, **kw)
    finally:
        if old is None:
            os.environ.pop("EDITVIDEO_SOURCES", None)
        else:
            os.environ["EDITVIDEO_SOURCES"] = old


def find_entry(path):
    """The library record of a file: by path, then by bytes."""
    p = str(Path(path).resolve()).replace("\\", "/").casefold()
    entries = resources._load()
    for e in entries:
        ep = e["path"] if ":" in e["path"] else str((resources.ROOT / e["path"]).resolve())
        if ep.replace("\\", "/").casefold() == p:
            return e
    if Path(path).is_file():
        sha = resources._sha(path)
        return next((e for e in entries if e.get("sha256") == sha), None)
    return None


def register_source(path, license, credit, source_url="", title="", kind="footage", notes=""):
    """A source reel or file on any drive, with its licence as established (say "unknown" honestly)."""
    return _register_outside(path, kind, title or Path(path).parent.name, license, credit, source_url, "archive source", notes, "archive")


def register_cut(path, source, window=None, notes="", license=None, credit=None):
    """A clip cut from a source reel inherits the reel's record (licence, credit, page). Without a record for the reel
    (or the reel no longer on disk) license and credit must be given."""
    src = find_entry(source) if source else None
    if src is None and not (license and credit):
        raise ValueError(f"No library record for {source}: register_source it first, or pass license and credit")
    lic, cred = (license or src["license"]), (credit or src["credit"])
    note = " ".join(x for x in (notes, f"cut {window[0]}-{window[1]} s" if window else "", f"from {src['id']}" if src else f"from {source}") if x)
    return _register_outside(path, "footage", (src["title"] if src else Path(path).stem) + f" · {Path(path).stem}", lic, cred,
                             src.get("source_url", "") if src else "", "archive cut", note, src.get("provider", "archive") if src else "archive")


def register_render(path, title, parts, kind="footage"):
    """A render (Blender, a composite) made from inputs: parts [(licence, credit[, title, source_url])]; its licence names
    every part and so takes the most restrictive class, and each part stays a work of its own in the ledger's count and
    in the credits."""
    lic = " + ".join(dict.fromkeys(p[0] for p in parts))
    cred = " · ".join(dict.fromkeys(p[1] for p in parts))
    works = [{"title": p[2] if len(p) > 2 and p[2] else p[1], "license": p[0], "credit": p[1], "source_url": p[3] if len(p) > 3 else "",
              "used": ["picture", "audio"], "kind": "render input"} for p in parts]
    return _register_outside(path, kind, title, lic, cred, "", "render", "inputs: " + lic, "render", parts=works)


def register_project_render(path, pid, title, kind="footage"):
    """A render of another EditVideo project (a nested film, a beat-cut montage, a contact sheet of a cut) carries that
    project's ledger: one part per distinct work, with what of it (picture, audio) the project used. A project that uses
    the render then credits and counts each work; registered as one file under one licence, a montage of five reels by
    two authors had been credited to one of them, and its other reels were in no ledger."""
    works = project_ledger(pid, "internal", write=False)["works"]
    if not works:
        raise ValueError(f"Project {pid}'s ledger names no third-party work: register the render with register_source")
    parts = [{k: w.get(k) for k in ("title", "license", "credit", "source_url", "used", "kind")} for w in works]
    lic = " + ".join(dict.fromkeys(w["license"] for w in parts))
    cred = " · ".join(dict.fromkeys(w["credit"] for w in parts))
    return _register_outside(path, kind, title, lic, cred, "", "render", f"render of project {pid}", "render", parts=parts)


def _reel(e):
    """The reel a cut (or a cut of a cut) was taken from: its work, under the reel's own title."""
    by_id = None
    for _ in range(6):
        m = re.search(r"\bfrom ([a-z0-9-]+)$", e.get("notes") or "") if e.get("tags") == "archive cut" else None
        if not m:
            return e
        by_id = by_id or {x["id"]: x for x in resources._load()}
        if m.group(1) not in by_id:
            return e
        e = by_id[m.group(1)]
    return e


def _works(rows):
    """The distinct third-party works behind the rows: a reel cut into many clips, or reached through a nested render and
    directly, is one work (same page, or same title and credit). EditVideo's own synthesis is not a work."""
    out = {}
    for r in rows:
        for w in r.get("works") or []:
            key = w.get("source_url") or (w["title"], w["credit"])
            got = out.setdefault(key, {**w, "used": [], "in": []})
            got["used"] = sorted(set(got["used"]) | set(w.get("used") or []))
            if r.get("name") not in got["in"]:
                got["in"].append(r.get("name"))
    return sorted(out.values(), key=lambda w: (ORDER.index(w["class"]), w["title"]))


def _uses(t):
    """asset id -> [(start_frame, end_frame, where)] over shots, layers (and their 3D objects) and audio."""
    out = {}
    add = lambda aid, a, b, w: aid and out.setdefault(aid, []).append((a, b, w))
    f = 0
    for s in t.get("shots", []):
        n = s.get("end_frame", 0) - s.get("start_frame", 0) if "end_frame" in s else round(s.get("duration", 0) * FPS)
        a = s.get("start_frame", f)
        add(s.get("asset_id"), a, a + n, f"shot {s.get('id')}")
        f = a + n
    for l in t.get("layers", []):
        add(l.get("asset_id"), l["start_frame"], l["end_frame"], f"layer {l['id']}")
        d = l.get("data") or {}
        for o in d.get("objects", []):
            for k in ("texture", "bump_texture", "emissive_texture", "alpha_texture", "displacement_texture", "model"):
                add(o.get(k), l["start_frame"], l["end_frame"], f"layer {l['id']} {k}")
        for k in ("background_texture", "environment_texture"):
            add(d.get(k), l["start_frame"], l["end_frame"], f"layer {l['id']} {k}")
    for c in t.get("audio_clips", []):
        add(c.get("asset_id"), c["start_frame"], c["end_frame"], f"audio {c['id']}")
    return out


def _seconds(spans):
    tot, end = 0, -1
    for a, b, _ in sorted(spans):
        if b > end:
            tot += b - max(a, end)
            end = b
    return round(tot / FPS, 2)


def project_ledger(pid, use="online", write=True):
    """Every used asset with origin, licence, class, seconds on screen/in the mix and where; blockers and obligations
    for the use. Writes plan/licence-ledger.json and .csv in the project."""
    from . import agent, design_library
    if use not in BLOCKS:
        raise ValueError(f"use must be one of {sorted(BLOCKS)}")
    t = agent.read(pid).get("timeline") or {}
    uses = _uses(t)
    cfg = store.get_project(pid).get("config") or {}
    for key, where in (("music_id", "project music"), ("narration_id", "audio narration")):  # the voice track is a work too
        if cfg.get(key):
            uses.setdefault(cfg[key], []).append((0, t.get("total_frames", 0) or 0, where))
    procedural = {store.read_json(f).get("sha256") for f in (store.DATA / "sound-design").glob("*/sound.json")}
    index = resources._Index()
    rows = []
    for aid, spans in sorted(uses.items()):
        try:
            a = store.find_asset(pid, aid)
        except Exception:  # an asset the timeline uses but the store cannot find is unknown, and blocks
            rows.append({"asset": aid, "name": None, "kind": None, "origin": None, "title": "asset not found in the store", "license": "unknown",
                         "class": "unknown", "classes": ["unknown"], "credit": "", "source_url": "", "via": [], "seconds": _seconds(spans),
                         "first_frame": min(x[0] for x in spans), "where": sorted({w for *_, w in spans})[:12]})
            continue
        if a.get("sha256") in procedural or a.get("name") == "silent-carrier.mp4" or (a.get("provenance") or {}).get("operation") == "generated silence":
            # agent.create_silent's plain colour carrier and the silence it is given as narration
            e, chain, lic, cred = None, [], "Generated locally by EditVideo (procedural, no third-party rights)", "EditVideo"
        else:
            e, chain = resources.trace_origin(a, index)
            lic, cred = (e["license"], e["credit"]) if e else ("unknown", "")
        parts_used = tuple(sorted({"audio" if w.startswith(("audio", "project music")) else "picture" for *_, w in spans}))  # what of it the film actually uses
        works = None
        if e and e.get("parts"):  # a render: the works in the part of it this film uses (its picture, its sound)
            works = [{**w, "used": sorted(set(w.get("used") or parts_used) & set(parts_used))} for w in e["parts"]]
            works = [{**w, "class": classify(w["license"], tuple(w["used"]))} for w in works if w["used"]]
            lic = " + ".join(dict.fromkeys(w["license"] for w in works)) or "Generated locally by EditVideo (procedural, no third-party rights)"
        row = {"asset": aid, "name": a.get("name"), "kind": a.get("kind"), "origin": e["id"] if e else None, "title": e["title"] if e else a.get("tags"),
               "license": lic, "used": list(parts_used), "class": classify(lic, parts_used), "classes": sorted(classes(lic, parts_used)), "credit": cred, "source_url": (e or {}).get("source_url", ""), "via": chain,
               "seconds": _seconds(spans), "first_frame": min(s[0] for s in spans), "where": sorted({w for *_, w in spans})[:12]}
        row["works"] = works if works is not None else ([] if row["class"] == "procedural" else
                                                          [{"title": (_reel(e)["title"] if e else row["title"] or row["name"]), "license": lic, "credit": cred, "source_url": row["source_url"],
                                                            "used": list(parts_used), "kind": a.get("kind"), "class": row["class"]}])
        rows.append(row)
    index.save()
    # type: the fonts drawn on screen (their licence files travel in the delivery ZIP)
    fonts = {s.get("font_id") for s in ((t.get("design") or {}).get("typography") or {}).values()} | {l.get("font_id") for l in t.get("layers", [])}
    for fid in sorted(x for x in fonts if x):
        it = design_library.font(fid)
        rows.append({"asset": f"font:{fid}", "name": it["family"], "kind": "font", "origin": fid, "title": it["family"], "license": it["license"],
                     "class": classify(it["license"]), "classes": sorted(classes(it["license"])), "credit": it["family"], "source_url": "", "via": [], "seconds": None, "first_frame": None, "where": ["text"],
                     "works": [{"title": it["family"], "license": it["license"], "credit": it["family"], "source_url": "", "used": ["picture"], "kind": "font",
                                "class": classify(it["license"])}]})
    voice = resources._voice_credit(pid)
    if voice:
        rows.append({"asset": "voice", "name": voice["credit"], "kind": "voice", "origin": None, "title": "narration voice", "license": voice["license"],
                     "class": classify(voice["license"]), "classes": sorted(classes(voice["license"])), "credit": voice["credit"], "source_url": "", "via": [], "seconds": None, "first_frame": None, "where": ["narration"],
                     "works": [{"title": "narration voice", "license": voice["license"], "credit": voice["credit"], "source_url": "", "used": ["audio"], "kind": "voice",
                                "class": classify(voice["license"])}]})
    blockers = [r for r in rows if r["class"] in BLOCKS[use]]
    duties = {}
    for r in rows:  # every part of a composite carries its own duty (a PD + CC BY render still owes the CC BY credit)
        if r not in blockers:
            for k in r["classes"]:
                if k in DUTY:
                    duties.setdefault(k, []).append(r["name"])
    by_class = {}
    for r in rows:
        b = by_class.setdefault(r["class"], {"assets": 0, "seconds": 0.0})
        b["assets"] += 1
        b["seconds"] = round(b["seconds"] + (r["seconds"] or 0), 2)
    works = _works(rows)
    out = {"project": pid, "use": use, "verdict": "blocked" if blockers else "clear", "by_class": by_class,
           "works": works, "work_count": len(works), "works_by_kind": {k: sum(str(w.get("kind")) == k for w in works) for k in sorted({str(w.get("kind")) for w in works})},
           "blockers": [{k: r[k] for k in ("asset", "name", "title", "license", "class", "seconds", "first_frame")} for r in blockers],
           "obligations": {k: {"duty": DUTY[k], "assets": v[:20], "count": len(v)} for k, v in duties.items()},
           "rows": rows,
           "note": "From the library's records (resources.trace_origin); not legal advice. Clear blockers by licensing the material, "
                   "replacing it, or registering a verified licence with register_source/register_cut."}
    if write:
        d = store.folder(pid) / "plan"
        d.mkdir(parents=True, exist_ok=True)
        store.write_json(d / "licence-ledger.json", out)
        with open(d / "licence-ledger.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["asset", "name", "kind", "class", "license", "credit", "seconds", "first_s", "origin", "source_url", "where"])
            for r in rows:
                w.writerow([r["asset"], r["name"], r["kind"], r["class"], r["license"], r["credit"], r["seconds"],
                            None if r["first_frame"] is None else round(r["first_frame"] / FPS, 2), r["origin"], r["source_url"], "; ".join(r["where"])])
        out["paths"] = [str(d / "licence-ledger.json"), str(d / "licence-ledger.csv")]
    return out
