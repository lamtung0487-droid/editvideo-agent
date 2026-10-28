"""Public-domain moving images for the films, found and recorded with their evidence (step 2 of the montage work: the
licence ledger blocked 34 copyrighted clips of the first sample for online use).

The Internet Archive mirrors thousands of films of the US National Archives (identifiers gov.archives.arc.<NAID>,
marked with the Public Domain Mark) and other federal film collections. search() queries its advanced search by words
and years; item() reads one item's metadata and files; fetch() downloads the best video file into the sources folder
and records it in the library (licence, credit with the NAID, catalog and archive pages, the rights statement as
read on the day, its sha256), so every cut made from it is traced by the ledger.

A Public Domain Mark on the archive is the archive's statement, not a guarantee: NARA also holds donated network
news, foreign and commercial films that are not public domain. check() flags those signs in the item's own text
(a network or newsreel name, "copyright", "restricted", foreign producers) for a person to look at; the clip is then
recorded as "unknown" until a person clears it.

The National Archives' own record is the better evidence and the faster file (its media server gave 830 KB/s where
the mirror gave 25 KB/s): nara_record() reads it through the catalog's public search (no key), nara_fetch() downloads
its digital object and keeps the record itself beside the file. Its use-restriction field can disagree with the
mirror: "The Battle of Ia Drang Valley" carries a Public Domain Mark on the mirror and "Restricted - Possibly" at
NARA. nara_rights() decides picture and sound separately:
- a film of a federal record group (the Navy's RG 428, the Army's RG 111, ...) is a US government work (17 U.S.C.
  105) unless NARA says "Restricted - Possibly/Fully": picture public domain; its sound too, or none if it is silent;
- the Universal Newsreel (the MCA/Universal collection "UN") was given to the Archives, but NARA itself marks its
  reels "Restricted - Possibly" for copyright: unknown until a person clears it; were NARA to lift that, the picture
  would count as public domain and the music and narration still as unknown;
- anything else, or a federal film NARA marks restricted: unknown until a person clears it;
- federal record groups also hold other people's films: the Office of the Secretary of Defense (RG 330) kept 574
  ABC/CBS/NBC newscasts, the USIA (RG 306) North and South Vietnamese productions. A record naming a network, a
  newsreel, a foreign maker or a copyright in its title, description or contributors is unknown; in RG 330 and 306 a
  film is public domain only when its producer is a US government body.
NARA does not certify copyright (36 C.F.R. 1254.62): this is the evidence a clearance reviewer asks for, not a
clearance.
"""
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_META = "https://archive.org/metadata/{id}"
IA_FILE = "https://archive.org/download/{id}/{name}"
UA = "EditVideoAgent/1.0 (archival research)"
NARA_CATALOG = "https://catalog.archives.gov/id/{naid}"
# Internet Archive identifiers of federal record groups (Public.Resource.Org's FedFlix uploads of NARA reels) and of the
# Universal Newsreel library, which Universal gave to the National Archives without restriction
FEDERAL_PREFIX = {"gov.archives.arc.": "US National Archives", "gov.dod.dimoc.": "US Department of Defense (DIMOC)", "111-": "US Army Signal Corps (NARA RG 111)",
                  "428-": "US Navy (NARA RG 428)", "330-": "Office of the Secretary of Defense (NARA RG 330)", "342-": "US Air Force (NARA RG 342)",
                  "127-": "US Marine Corps (NARA RG 127)", "306-": "US Information Agency (NARA RG 306)"}
NEWSREEL_PREFIX = {"un-un-": "Universal Newsreel (NARA RG 200, given without restriction)", "UN-": "Universal Newsreel (NARA RG 200, given without restriction)"}


def origin(identifier):
    """(kind, maker) of an identifier: ("federal", ...), ("newsreel", ...) or (None, None) for anything else (a private
    upload, a broadcaster's channel) whose rights the mirror cannot speak for."""
    for pre, who in FEDERAL_PREFIX.items():
        if identifier.startswith(pre):
            return "federal", who
    for pre, who in NEWSREEL_PREFIX.items():
        if identifier.startswith(pre):
            return "newsreel", who
    return None, None
# names that mean the film is not the government's own work, whatever mark the mirror carries
NOT_FEDERAL = r"\b(nbc|cbs|abc news|cnn|pathe|pathé|movietone|hearst|paramount news|fox movietone|telenews|metro-goldwyn|copyright|copyrighted|" \
              r"all rights reserved|restricted|restriction|courtesy of|foreign|soviet|french|japanese|german|british)\b"


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        if "json" not in (r.headers.get("Content-Type") or "json") or not body.lstrip().startswith(("{", "[")):
            # NARA's catalog answers a call it will not serve (no key, a changed route) with its web page and HTTP 200
            raise ValueError(f"{url.split('?')[0]} answered with a web page, not JSON: the route changed or needs an API key")
        return json.loads(body)


def _download(url, path, size=None, tries=4, timeout=900):
    """Download url to path, resuming a partial file (path + ".part") with a Range request; the server's own length
    decides when it is complete (NARA's catalog gave 106599072 bytes for a file its server sends as 106599071).
    A refusal (4xx) is raised at once; a dropped stream is resumed after a pause. Returns the length."""
    import http.client
    import time
    path = Path(path)
    part = path.with_name(path.name + ".part")
    total, last = None, None
    for i in range(tries):
        try:
            if total is None:
                head = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
                with urllib.request.urlopen(head, timeout=60) as r:
                    total = int(r.headers.get("Content-Length") or 0) or size or 0
            if path.is_file() and (not total or path.stat().st_size == total):
                return path.stat().st_size
            have = part.stat().st_size if part.is_file() else 0
            if total and have > total:
                part.unlink()
                have = 0
            if not total or have < total:
                req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": f"bytes={have}-"} if have else {})})
                with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "ab" if have and r.status == 206 else "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
            if not total or part.stat().st_size == total:
                part.replace(path)
                return path.stat().st_size
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code not in (408, 416, 429):
                raise ValueError(f"{url} refused: HTTP {e.code}") from e
            last = e
        except (OSError, urllib.error.URLError, http.client.HTTPException) as e:  # a dropped stream (IncompleteRead, reset, timeout)
            last = e
        time.sleep(min(30, 2 ** i))
    have = part.stat().st_size if part.is_file() else 0
    raise ValueError(f"short download ({have} of {total} bytes) from {url}: {last}")


def search(words, years=None, collection="nara", rows=50, page=1):
    """Films matching `words` (any of them, in title, description or subject), optionally shot in `years`
    [first, last]. collection: "nara" (gov.archives.arc.*), "fedflix" (Public.Resource.Org's federal films), "federal"
    (both, plus the Universal Newsreel items) or "any". Returns [{"identifier", "title", "year", "rights", "page",
    "naid", "origin"}]; "origin" is None for uploads that are not a federal record group or the Universal Newsreel."""
    words = [w for w in (words if isinstance(words, (list, tuple)) else [words]) if w]
    q = ["mediatype:movies"]
    if collection == "nara":
        q.append("identifier:gov.archives.arc.*")
    elif collection == "fedflix":
        q.append("collection:FedFlix")
    elif collection == "federal":
        q.append("(identifier:gov.archives.arc.* OR collection:FedFlix OR identifier:un-un-* OR identifier:gov.dod.dimoc.*)")
    if words:
        q.append("(" + " OR ".join(f'"{w}"' if " " in w else w for w in words) + ")")
    if years:
        q.append(f"year:[{int(years[0])} TO {int(years[1])}]")
    params = [("q", " AND ".join(q)), ("rows", rows), ("page", page), ("output", "json")] + [("fl[]", f) for f in
              ("identifier", "title", "year", "date", "licenseurl", "rights", "description", "subject")]
    d = _get(IA_SEARCH + "?" + urllib.parse.urlencode(params))
    out = []
    for x in d["response"]["docs"]:
        ident = x["identifier"]
        naid = ident.rsplit(".", 1)[-1] if ident.startswith("gov.archives.arc.") else None
        title = x.get("title") or ""
        year = x.get("year") or (re.search(r"\b(19[0-9]\d)\b", title) or [None])[0] or (re.match(r"(19[0-9]\d)", str(x.get("date") or "")) or [None])[0]
        out.append({"identifier": ident, "title": title, "year": int(year) if year else None, "rights": x.get("licenseurl") or x.get("rights") or "",
                    "page": f"https://archive.org/details/{ident}", "naid": naid,
                    "catalog": NARA_CATALOG.format(naid=naid) if naid else None, "origin": origin(ident)[1],
                    "description": (x.get("description") if isinstance(x.get("description"), str) else " ".join(x.get("description") or []))[:600]})
    return out


def item(identifier):
    """An item's metadata and its video files, best first: the tallest picture, the original before a derivative."""
    d = _get(IA_META.format(id=identifier))
    md = d.get("metadata", {})
    vids = []
    for f in d.get("files", []):
        name, fmt = f.get("name", ""), (f.get("format") or "").lower()
        if not re.search(r"\.(mp4|mpeg|mpg|mov|avi|m4v|ogv)$", name, re.I):
            continue
        # the tallest picture first (the 512 kb MPEG-4 is a 240-line derivative of a 480-line MPEG-2 original), then the
        # original over a derivative, then size
        rank = (int(f.get("height") or 0), f.get("source") == "original", int(f.get("size") or 0))
        vids.append({"name": name, "format": f.get("format"), "size": int(f.get("size") or 0), "source": f.get("source"),
                     "height": int(f.get("height") or 0), "url": IA_FILE.format(id=identifier, name=urllib.parse.quote(name)), "_rank": rank})
    vids.sort(key=lambda v: v["_rank"], reverse=True)
    for v in vids:
        v.pop("_rank")
    return {"identifier": identifier, "metadata": md, "videos": vids}


def check(meta):
    """Signs in an item's own text that it may not be the government's own work: {"ok", "flags"}. A clean result is
    not a clearance: it means nothing in the record contradicts the public-domain mark."""
    text = " ".join(str(meta.get(k) or "") if not isinstance(meta.get(k), list) else " ".join(map(str, meta[k]))
                    for k in ("title", "description", "subject", "creator", "contributor", "publisher", "rights", "notes"))
    flags = sorted({m.group(0).lower() for m in re.finditer(NOT_FEDERAL, text, re.I)})
    kind, _ = origin(str(meta.get("identifier") or ""))
    mark = str(meta.get("licenseurl") or "")
    if kind == "newsreel":  # a newsreel names other newsreels and foreign places in its own stories: only rights words count
        flags = [f for f in flags if f in ("copyright", "copyrighted", "all rights reserved", "restricted", "restriction")]
    if "publicdomain" not in mark and not kind:
        flags.append("not a federal record group, no public-domain mark")
    return {"ok": not flags, "flags": flags, "origin": kind}


def fetch(identifier, dest=None, max_bytes=2 * 1024 ** 3):
    """Download an item's best video from the Internet Archive mirror into dest (default the store's sources/pd folder)
    and record it in the library. When the identifier names a NARA record (gov.archives.arc.<NAID>, 428-npc-...,
    un-un-...), the licence is NARA's, per part (nara_rights): the mirror's mark is the uploader's word, and the record
    wins (Ia Drang: CC0 on the mirror, "Restricted - Possibly" at NARA). Otherwise a clean check() gives "Unverified
    public domain", which the ledger blocks until a person clears it. Returns the library entry plus "path" and
    "check"."""
    from . import ledger, store
    it = item(identifier)
    md = it["metadata"]
    vids = [v for v in it["videos"] if v["size"] <= max_bytes] or it["videos"][-1:]
    if not vids:
        raise ValueError(f"{identifier}: no video file")
    v = vids[0]  # item() ranks them: the tallest picture, the original before a derivative
    dest = Path(dest) if dest else store.DATA.parent / "sources" / "pd" / identifier
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / Path(v["name"]).name
    _download(v["url"], path, v["size"], timeout=600)
    ck = check(md)
    naid = identifier.rsplit(".", 1)[-1] if identifier.startswith("gov.archives.arc.") else None
    mark = md.get("licenseurl") or ""
    kind, who = origin(identifier)
    key = nara_local_id(identifier)
    rec = None
    if key:
        try:
            rec = nara_record(*((key, None) if isinstance(key, int) else (None, key)))
        except (OSError, ValueError, KeyError):  # the catalog is down or answers a page: fall back to "unverified" below
            rec = None
    if rec:
        lic, reasons = nara_rights(rec)
        ck = {**ck, "nara": {"naid": rec["naid"], "use": rec["use"], "reasons": reasons}}
        naid = str(rec["naid"])
    elif ck["ok"] and kind:
        lic = f"Unverified public domain ({who}; Public Domain Mark on the Internet Archive item, no NARA record read)"
    elif ck["ok"]:
        lic = "Unverified public domain (Public Domain Mark on the Internet Archive item; the maker is not a federal record group)"
    else:
        lic = f"unknown (flags in the record: {', '.join(ck['flags'])})"
    credit = (who or "Internet Archive upload") + (f" (NAID {naid})" if naid else "") + " via the Internet Archive"
    (dest / "rights.json").write_text(json.dumps({"identifier": identifier, "naid": naid, "catalog": NARA_CATALOG.format(naid=naid) if naid else None,
                                                  "page": f"https://archive.org/details/{identifier}", "licenseurl": mark, "check": ck,
                                                  "title": md.get("title"), "date": md.get("date"), "file": v}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    e = ledger.register_source(path, lic, credit, f"https://archive.org/details/{identifier}", md.get("title") or identifier,
                               notes=(f"catalog {NARA_CATALOG.format(naid=naid)}; " if naid else "") + f"mark {mark}; checked flags: {ck['flags']}")
    return {**e, "path": str(path), "check": ck}


# ---------------------------------------------------------------- the National Archives' own record
NARA_SEARCH = "https://catalog.archives.gov/proxy/records/search"
_REGISTER = threading.Lock()
AGENCY_RG = {111: "US Army Signal Corps", 127: "US Marine Corps", 286: "Agency for International Development", 306: "US Information Agency",
             330: "Office of the Secretary of Defense", 342: "US Air Force", 428: "US Navy", 80: "US Navy (General Records)"}
NEWSREEL_RG = {"UN": "Universal Newsreel (MCA/Universal Pictures collection, given to NARA)"}  # RG 200 is the Gift Collection: anyone's films
MIXED_RG = {330, 306}  # federal groups that also hold networks' and foreign governments' films
OTHERS = r"\b(abc|nbc|cbs|cnn|newscast|evening news|news special|television news|newsreel|movietone|pathe|pathé|hearst|march of time|telenews|" \
         r"paramount|universal pictures|copyright(?:ed)?|all rights reserved|courtesy of|produced by (?:the )?(?:government|republic|democratic)|" \
         r"north vietnamese (?:film|production)|liberation (?:film|studio)|soviet|french|japanese)\b"
# a US government producer names the United States (or one of its own bodies); "Department of Information" or "Army
# Film Studio" alone could be Saigon's or Hanoi's
FEDERAL_MAKER = r"(\bu\.\s?s\.|\bunited states\b|\bdepartment of defense\b|\bdepartment of the (?:army|navy|air force)\b|\bnaval photographic center\b|" \
                r"\barmy pictorial center\b|\binformation agency\b|\busia\b|\boffice of the secretary of defense\b)"
FOREIGN_MAKER = r"\b(viet ?nam|republic of|people'?s|liberation|soviet|chin(?:a|ese)|korea|french|france|japan)"


def nara_local_id(identifier):
    """The NARA local identifier or NAID behind an Internet Archive identifier: 428-npc-38421 -> "428-NPC-38421",
    un-un-v38-r24 -> "UN-UN-38-24", gov.archives.arc.653177 -> 653177."""
    if identifier.startswith("gov.archives.arc."):
        return int(identifier.rsplit(".", 1)[-1].split("_")[0])
    m = re.match(r"un-un-v(\d+)-r(\d+)", identifier, re.I)
    if m:
        return f"UN-UN-{m.group(1)}-{m.group(2)}"
    m = re.match(r"(\d+)-([a-z]+)-(\d+[a-z]?)$", identifier, re.I)
    return f"{m.group(1)}-{m.group(2).upper()}-{m.group(3).upper()}" if m else None


def _nara_summary(r):
    """The parts of a catalog record that decide rights and use; "record_group" is the record group number, or the
    collection identifier of a donated collection ("UN" for the Universal Newsreel)."""
    rg = next((a.get("recordGroupNumber") for a in r.get("ancestors") or [] if a.get("levelOfDescription") == "recordGroup"), None)
    rg = rg or next((a.get("collectionIdentifier") for a in r.get("ancestors") or [] if a.get("levelOfDescription") == "collection"), None)
    year = next((d.get("year") for d in r.get("productionDates") or [] if d.get("year")), None)
    return {"naid": r.get("naId"), "local_id": r.get("localIdentifier"), "title": r.get("title"), "dates": r.get("productionDates"), "year": year,
            "record_group": rg, "use": (r.get("useRestriction") or {}), "access": (r.get("accessRestriction") or {}),
            "sound": r.get("soundType"), "shot_list": r.get("shotList") or r.get("scopeAndContentNote") or "",
            "about": " ".join(str(x) for x in (r.get("title"), r.get("subtitle"), r.get("scopeAndContentNote")) if x),
            "makers": [(c.get("contributorType") or "", c.get("heading") or "") for c in (r.get("contributors") or []) + (r.get("creators") or [])],
            "objects": [{"name": o.get("objectFilename"), "type": o.get("objectType"), "size": o.get("objectFileSize"),
                         "url": o.get("objectUrl")} for o in r.get("digitalObjects") or []],
            "catalog": NARA_CATALOG.format(naid=r.get("naId"))}


def nara_record(naid=None, local_id=None):
    """The catalog record of a NARA item (by NAID or local identifier), with its record group, use restriction,
    sound type, shot list and digital objects; None when the catalog has no such item."""
    q = urllib.parse.urlencode({"naId": naid} if naid else {"q": local_id, "limit": 10})
    hits = _get(NARA_SEARCH + "?" + q)["body"]["hits"]["hits"]
    for h in hits:
        r = h["_source"]["record"]
        if (naid and int(r.get("naId", 0)) == int(naid)) or (local_id and str(r.get("localIdentifier", "")).upper() == str(local_id).upper()):
            return {**_nara_summary(r), "raw": r}
    return None


def nara_search(words, record_group=None, years=None, rows=50, page=1, sound=None):
    """Films in the National Archives catalog with a file to download: [summary as nara_record gives it, plus "mb"
    (size of the largest object) and "licence"], federal and unrestricted first. record_group: 428 (Navy), 127 (Marine
    Corps), 111 (Army), 342 (Air Force), ...; years: (first, last) of production; sound: "Silent" or "Sound". The
    shot list NARA wrote for most reels ("15) LS MS A-4C taxiing onto catapult ... VG") names each shot and grades it,
    so a search can be read before anything is downloaded."""
    q = {"q": words, "typeOfMaterials": "Moving Images", "availableOnline": "true", "limit": rows, "page": page}
    if record_group:
        q["recordGroupNumber"] = record_group
    out = []
    for h in _get(NARA_SEARCH + "?" + urllib.parse.urlencode(q))["body"]["hits"]["hits"]:
        x = _nara_summary(h["_source"]["record"])
        objs = [o for o in x["objects"] if str(o.get("name") or "").lower().endswith((".mp4", ".mov", ".mpg", ".mpeg", ".wmv"))]
        if not objs or (years and not (x["year"] and years[0] <= int(x["year"]) <= years[1])) or (sound and str(x["sound"] or "").lower() != sound.lower()):
            continue
        lic, _ = nara_rights(x)
        out.append({**x, "objects": objs, "mb": round(max(o.get("size") or 0 for o in objs) / 1e6), "licence": lic})
    return sorted(out, key=lambda x: (x["licence"].startswith("unknown"), x["year"] or 9999))


def nara_rights(rec):
    """(licence string, reasons) with picture and sound decided separately (see the module notes)."""
    status = str(rec["use"].get("status") or "Undetermined")
    restricted = status.lower().startswith("restricted")
    rg = rec.get("record_group")
    silent = str(rec.get("sound") or "").lower() == "silent"
    ref = f"NARA {rec.get('local_id') or ''} NAID {rec['naid']}, use restriction: {status}".replace("  ", " ")
    makers = rec.get("makers") or []
    others = sorted({m.group(0).lower() for m in re.finditer(OTHERS, " ".join([rec.get("about") or "", *(h for _, h in makers)]), re.I)})
    if rg in AGENCY_RG and not restricted and others:
        return f"unknown (NARA record group {rg}; {ref}; the record names {', '.join(others)}): a person must clear it", ["another maker named in the record"]
    if rg in MIXED_RG and not restricted and not any(re.search(FEDERAL_MAKER, h, re.I) and not re.search(FOREIGN_MAKER, h, re.I)
                                                     for t, h in makers if t.lower() in ("producer", "creator", "")):
        return f"unknown (NARA record group {rg}; {ref}; no US government producer in the record): a person must clear it", ["mixed record group, maker not shown"]
    if rg in NEWSREEL_RG and not restricted:
        sound = "none (silent)" if silent else f"unknown (the newsreel's music and narration may belong to others; {ref})"
        return f"picture: Public domain ({NEWSREEL_RG[rg]}; {ref}); audio: {sound}", ["donated newsreel"]
    if rg in AGENCY_RG and not restricted:
        sound = "none (silent)" if silent else f"Public domain (US federal government work, {AGENCY_RG[rg]})"
        return f"picture: Public domain (US federal government work, {AGENCY_RG[rg]}, 17 U.S.C. 105; {ref}); audio: {sound}", ["federal record group"]
    why = "NARA marks it restricted" if restricted and (rg in AGENCY_RG or rg in NEWSREEL_RG) else "not a federal record group"
    return f"unknown (NARA record group {rg}; {ref}): a person must clear it", [why]


def nara_fetch(identifier=None, naid=None, local_id=None, dest=None, max_bytes=3 * 1024 ** 3):
    """Download a NARA item's best digital object from NARA itself and record it with its catalog record as evidence.
    identifier: an Internet Archive identifier to resolve (or give naid / local_id). Returns the library entry plus
    "path", "record" (without the raw JSON) and "reasons"."""
    import hashlib
    from . import ledger, store
    if identifier and not (naid or local_id):
        key = nara_local_id(identifier)
        naid, local_id = (key, None) if isinstance(key, int) else (None, key)
    rec = nara_record(naid, local_id)
    if not rec:
        raise ValueError(f"No NARA record for {identifier or naid or local_id}")
    rank = lambda o: ({"mp4": 3, "mov": 2, "mpeg": 1, "mpg": 1}.get(str(o["name"]).rsplit(".", 1)[-1].lower(), 0), o.get("size") or 0)
    objs = sorted([o for o in rec["objects"] if o.get("url") and (not o.get("size") or o["size"] <= max_bytes)], key=rank, reverse=True)
    if not objs:
        raise ValueError(f"NARA {rec['naid']}: no downloadable object")
    o = objs[0]
    dest = Path(dest) if dest else store.DATA.parent / "sources" / "pd" / f"nara-{rec['naid']}"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / Path(urllib.parse.urlparse(o["url"]).path).name
    o = {**o, "server_bytes": _download(o["url"], path, o.get("size"))}  # the catalog's size can be a byte off the server's
    lic, reasons = nara_rights(rec)
    raw = json.dumps(rec["raw"], ensure_ascii=False, indent=1)
    (dest / "nara-record.json").write_text(raw, encoding="utf-8")  # the catalog record as read, the clearance evidence
    evidence = {"catalog": rec["catalog"], "record_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "object": o, "licence": lic,
                "reasons": reasons, "read_at": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    (dest / "rights.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    credit = f"US National Archives, {rec.get('local_id') or ''} (NAID {rec['naid']})".replace(", (", " (")
    with _REGISTER:  # the library index is read, changed and written whole: one writer at a time when fetches run in threads
        e = ledger.register_source(path, lic, credit, rec["catalog"], rec.get("title") or str(rec["naid"]),
                                   notes=f"use restriction {rec['use'].get('status')}; sound {rec.get('sound')}; evidence {dest / 'rights.json'}")
    rec = {k: v for k, v in rec.items() if k != "raw"}
    return {**e, "path": str(path), "record": rec, "reasons": reasons}
