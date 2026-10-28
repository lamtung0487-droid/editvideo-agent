"""Resource library with licences, open-source media discovery, geography and credits.

The library is a plain JSON catalog (data/library/catalog.json) of files already on disk: textures, models, geodata,
footage, LUTs. Every entry carries licence, credit and source URL so credits are compiled from records, never retyped.
Search of open providers returns candidates only; downloading is a separate call the agent makes after the user has
approved that specific file (name, source, size).
"""
import hashlib
import json
import os
import math
import re
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from . import store

ROOT = store.ROOT
CATALOG = ROOT / "data" / "library" / "catalog.json"
KINDS = ("texture", "model", "geo", "footage", "image", "audio", "lut", "font", "data")
UA = "EditVideoAgent/1.0 (local research tool; contact via project owner)"
MAX_DOWNLOAD = 600 * 1024 * 1024


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load():
    return json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else []


def _atomic(path, text):
    """Write through a temporary file and a rename: the library lives on a nearly full drive, and a write cut short
    there must not leave a half catalog behind."""
    import os
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")  # two writers never share a temp file
    tmp.write_text(text, encoding="utf-8")
    for k in range(20):  # Windows refuses the rename while a reader has the target open
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(.05 * (k + 1))
    tmp.unlink(missing_ok=True)
    raise PermissionError(f"could not replace {path}")


def _save(entries):
    _atomic(CATALOG, json.dumps(entries, ensure_ascii=False, indent=1))


def register_resource(path, kind, title, license, credit, source_url="", tags="", notes="", provider="local"):
    """Add or refresh one library entry for a file inside the project data folder."""
    p = Path(path).resolve()
    if not p.is_file():
        raise ValueError(f"No such file: {p}")
    extra = Path(os.environ["EDITVIDEO_SOURCES"]).resolve() if os.environ.get("EDITVIDEO_SOURCES") else None
    if ROOT.resolve() not in p.parents and not (extra and extra in p.parents):
        raise ValueError("Library files must live inside the EditVideo folder (or EDITVIDEO_SOURCES)")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not license or not credit:
        raise ValueError("license and credit are required (use 'unknown' honestly when not established)")
    entries = _load()
    rel = (str(p.relative_to(ROOT.resolve())) if ROOT.resolve() in p.parents else str(p)).replace("\\", "/")  # outside: absolute
    entry = {"id": re.sub(r"[^a-z0-9]+", "-", Path(rel).stem.lower()).strip("-")[:60], "path": rel, "kind": kind, "title": title,
             "license": license, "credit": credit, "source_url": source_url, "provider": provider, "tags": tags, "notes": notes,
             "bytes": p.stat().st_size, "sha256": _sha(p)}
    if kind in ("texture", "image"):
        try:
            from PIL import Image
            with Image.open(p) as im:
                entry["resolution"] = list(im.size)
        except Exception:
            pass
    entries = [e for e in entries if e["path"] != rel]
    while any(e["id"] == entry["id"] for e in entries):
        entry["id"] += "-2"
    entries.append(entry)
    _save(entries)
    return entry


def register_derived(path, from_id, kind=None, notes=""):
    """Register a file made from a library entry (resized, cropped, graded) with the source's licence and credit."""
    src = next((e for e in _load() if e["id"] == from_id), None)
    if not src:
        raise ValueError(f"Unknown library id {from_id}")
    return register_resource(path, kind or src["kind"], src["title"] + " (derived)", src["license"], src["credit"], src["source_url"],
                             src.get("tags", ""), (notes + " " if notes else "") + f"derived from {from_id}", provider=src.get("provider", "local"))


def library(query="", kind=None, limit=20):
    """Search local resources by words in title/tags/notes/credit; returns absolute paths with licence and credit."""
    words = [w for w in re.split(r"\s+", query.casefold()) if w]
    out = []
    for e in _load():
        if kind and e["kind"] != kind:
            continue
        hay = " ".join(str(e.get(k, "")) for k in ("id", "title", "tags", "notes", "credit", "kind")).casefold()
        score = sum(w in hay for w in words)
        if words and not score:
            continue
        out.append((score, {**e, "absolute_path": str((ROOT / e["path"]).resolve())}))
    out.sort(key=lambda x: -x[0])
    exact = [e for _, e in out if e.get("id") == query.strip()]
    if exact:  # an exact id returns the full record
        return {"count": 1, "entries": exact}
    rows = [{"id": e.get("id"), "kind": e["kind"], "title": e.get("title"), "license": e.get("license"), "credit": e.get("credit"),
             "absolute_path": e["absolute_path"]} for _, e in out[:limit]]
    return {"count": len(out), "entries": rows,
            "note": "Licences are as recorded at download/registration; re-check the source page before commercial use."}


def seed_library():
    """Register the resources already on disk (idempotent). Commons records come from credits.jsonl."""
    src = ROOT / "data" / "sources"
    known = [
        ("textures/earth_bluemarble_5400.jpg", "texture", "Earth Blue Marble, equirectangular 5400x2700", "NASA media (no copyright in the US; follow NASA media guidelines)",
         "NASA Visible Earth – Blue Marble", "https://visibleearth.nasa.gov/collection/1484/blue-marble", "earth globe planet equirect day", "2:1 equirect; soft below ~1 radius altitude in 1080p (audit_timeline reports magnification)"),
        ("textures/earth_clouds_2048.jpg", "texture", "Earth clouds, equirectangular 2048", "NASA media (no copyright in the US; follow NASA media guidelines)",
         "NASA Visible Earth", "https://visibleearth.nasa.gov/", "earth clouds alpha globe", "Use as alpha_texture on a slightly larger sphere"),
        ("generated/moon_procedural_2048.jpg", "texture", "Moon albedo (procedural, illustrative)", "Generated locally by EditVideo (no third-party rights)",
         "EditVideo procedural texture", "", "moon lunar surface illustrative", "Not a real lunar map; label as illustration"),
        ("generated/moon_procedural_bump_2048.jpg", "texture", "Moon height (procedural, illustrative)", "Generated locally by EditVideo (no third-party rights)",
         "EditVideo procedural texture", "", "moon bump height", "Use as bump_texture with moon_procedural_2048"),
        ("models/apollo_lunar_module.glb", "model", "Apollo Lunar Module (Draco glb)", "NASA 3D Resources (no copyright in the US; NASA guidelines)",
         "NASA 3D Resources", "https://nasa3d.arc.nasa.gov/", "apollo lunar module lm spacecraft model", "Draco compressed; decoder bundled"),
        ("geo/ne_50m_admin_0_countries.geojson", "geo", "Natural Earth 1:50m admin-0 countries", "Public domain (Natural Earth)",
         "Made with Natural Earth", "https://www.naturalearthdata.com/", "map country border outline geojson world", "Use geo_outline(name) for globe outlines / SVG maps"),
        ("nasa/rollout_aerials.mp4", "footage", "Artemis I rollout aerials", "NASA media (no copyright in the US; NASA guidelines)", "NASA", "", "artemis sls rollout aerial rocket", "Source page URL not recorded at download"),
        ("nasa/launch_tracking.mp4", "footage", "Artemis I launch tracking", "NASA media (no copyright in the US; NASA guidelines)", "NASA", "", "artemis launch liftoff rocket", "Source page URL not recorded at download"),
        ("nasa/earthrise_cma1.mp4", "footage", "Orion camera Earthrise", "NASA media (no copyright in the US; NASA guidelines)", "NASA", "", "earthrise orion moon earth", "Source page URL not recorded at download"),
        ("nasa/earthrise_saw4.mp4", "footage", "Orion camera Earthrise (2)", "NASA media (no copyright in the US; NASA guidelines)", "NASA", "", "earthrise orion moon earth", "Source page URL not recorded at download"),
    ]
    done = []
    for rel, kind, title, lic, credit, url, tags, notes in known:
        p = src / rel
        if p.exists():
            done.append(register_resource(p, kind, title, lic, credit, url, tags, notes, provider="nasa" if "NASA" in credit else "local")["id"])
    credits = src / "commons" / "credits.jsonl"
    if credits.exists():
        files = {f.name: f for f in (src / "commons").iterdir() if f.is_file()}
        for line in credits.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            c = json.loads(line)
            stem = urllib.parse.unquote(c["url"].split("?")[0].rsplit("/", 1)[-1])
            match = _match_local(stem, files)
            if match:
                kind = "image" if match.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else "footage"
                done.append(register_resource(match, kind, c["title"].removeprefix("File:"), c["license"], f"{c['artist']} / Wikimedia Commons",
                                              c["page"], c["title"].removeprefix("File:"), "", provider="wikimedia")["id"])
    return {"registered": done, "catalog": str(CATALOG)}


def _subsequence(small, big):
    it = iter(big)
    return all(c in it for c in small)


def _match_local(remote_name, files):
    """Local files were renamed at download (halong_dec2024.webm for 'Ha Long Bay, Vietnam - Dec 2024.webm'):
    accept a local compact name that is a subsequence of the remote one, longest first."""
    key = re.sub(r"[^a-z0-9]", "", Path(remote_name).stem.lower())
    best, best_len = None, 0
    for name, f in files.items():
        if name == "credits.jsonl" or name.endswith(".part"):
            continue
        k = re.sub(r"[^a-z0-9]", "", Path(name).stem.lower())
        if len(k) >= 6 and (k in key or key in k or _subsequence(k, key)) and len(k) > best_len:
            best, best_len = f, len(k)
    if best is None:  # names chosen at download time, e.g. halong_cruise.webm for "Ha Long cruise 2022…"
        words = set(re.findall(r"[a-z]+", Path(remote_name).stem.lower()))
        scored = sorted(((len(words & set(re.findall(r"[a-z]+", Path(n).stem.lower()))), f) for n, f in files.items() if n != "credits.jsonl"),
                        key=lambda x: -x[0])
        if scored and scored[0][0] >= 2 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
            best = scored[0][1]
    return best


# ---------------------------------------------------------------- geography
def _geo_file():
    for e in _load():
        if e["kind"] == "geo" and e["path"].endswith(".geojson"):
            return ROOT / e["path"]
    p = ROOT / "data" / "sources" / "geo" / "ne_50m_admin_0_countries.geojson"
    if p.exists():
        return p
    bundled = ROOT / "assets" / "geo" / "ne_50m_admin_0_countries.min.geojson.gz"  # public domain, names only
    if bundled.exists():
        return bundled
    raise ValueError("No country geodata in the library; find_sources/fetch_source Natural Earth admin-0 after user approval")


_GEO = {}


def _rings(name):
    f_ = _geo_file()
    if f_ not in _GEO:  # parsed once a process: a map draws several outlines
        import gzip
        raw = gzip.decompress(f_.read_bytes()) if f_.suffix == ".gz" else f_.read_bytes()
        _GEO.clear()
        _GEO[f_] = json.loads(raw.decode("utf-8"))
    g = _GEO[f_]
    key = name.casefold()
    for f in g["features"]:
        props = f["properties"]
        names = {str(props.get(k, "")).casefold() for k in ("ADMIN", "NAME", "NAME_LONG", "NAME_VI", "SOVEREIGNT", "ISO_A3", "ADM0_A3")}
        if key in names:
            geo = f["geometry"]
            polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
            return props.get("ADMIN"), [p[0] for p in polys]
    raise ValueError(f"Country not found in Natural Earth: {name} (use the English ADMIN name or ISO_A3)")


def _area(ring):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2


def geo_outline(name, max_points=480, islands=False, min_island_area=.05):
    """Country border as [lon, lat] rings (largest first). islands=True keeps other polygons above min_island_area (deg²)."""
    from .globe import simplify
    admin, rings = _rings(name)
    rings = sorted(rings, key=_area, reverse=True)
    keep = rings[:1] + ([r for r in rings[1:] if _area(r) >= min_island_area] if islands else [])
    total = sum(len(r) for r in keep)
    out = [simplify([[round(x, 5), round(y, 5)] for x, y in r], max(12, int(max_points * len(r) / total))) for r in keep]
    xs = [p[0] for r in out for p in r]
    ys = [p[1] for r in out for p in r]
    return {"name": admin, "rings": out, "bbox": [min(xs), min(ys), max(xs), max(ys)], "points": sum(len(r) for r in out),
            "source": "Natural Earth 1:50m admin-0 (public domain)"}


class MapProjection:
    """Equirectangular projection scaled by cos(mid latitude), fitted into a view box with padding."""

    def __init__(self, bbox, width=1000, pad=.06):
        lon0, lat0, lon1, lat1 = bbox
        self.k = math.cos(math.radians((lat0 + lat1) / 2))
        w, h = (lon1 - lon0) * self.k, lat1 - lat0
        self.scale = width * (1 - 2 * pad) / w
        self.width, self.height = width, h * self.scale + 2 * pad * width
        self.lon0, self.lat1, self.pad = lon0, lat1, pad * width

    def __call__(self, lat, lon):
        return (round(self.pad + (lon - self.lon0) * self.k * self.scale, 1), round(self.pad + (self.lat1 - lat) * self.scale, 1))

    def path(self, rings):
        return " ".join("M" + " L".join(f"{x} {y}" for x, y in (self(lat, lon) for lon, lat in r)) + " Z" for r in rings)


def relief_crop(extent, out, source, source_bbox, width=2400):
    """Crop an equirectangular image (source covering source_bbox [west, south, east, north] in degrees) to a map extent
    [west, north, east, south] (cinematic.map_extent) and resize it to the map's view box aspect; returns the path. The
    film's maps use NASA Blue Marble with topography and bathymetry (public domain), tiles C1 and D1 at 240 px a degree:
    `source` and `source_bbox` may be lists of tiles at one resolution, assembled where the extent crosses their seams."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    w, n, e, s_ = extent
    tiles = list(zip(source, source_bbox)) if isinstance(source, (list, tuple)) else [(source, source_bbox)]
    canvas, px = None, None
    for path, (W0, S0, E0, N0) in tiles:
        if W0 >= e or E0 <= w or S0 >= n or N0 <= s_:
            continue
        with Image.open(path) as im:
            px, py = im.width / (E0 - W0), im.height / (N0 - S0)
            if canvas is None:
                canvas = Image.new("RGB", (round((e - w) * px), round((n - s_) * py)))
                covered = 0
            box = (round((max(w, W0) - W0) * px), round((N0 - min(n, N0)) * py), round((min(e, E0) - W0) * px), round((N0 - max(s_, S0)) * py))
            canvas.paste(im.crop(box), (round((max(w, W0) - w) * px), round((n - min(n, N0)) * py)))
            covered += (box[2] - box[0]) * (box[3] - box[1])
    if canvas is None or covered < canvas.width * canvas.height * .999:
        raise ValueError(f"map extent {extent} reaches beyond the source tiles {[b for _, b in tiles]}")
    h = round(width * canvas.height / canvas.width * (1 / math.cos(math.radians((n + s_) / 2))))  # x shrinks by cos(lat)
    canvas.resize((width, h), Image.LANCZOS).save(out, quality=92)
    return out


def geo_map(name, cities=(), width=1000, islands=True, extra_countries=()):
    """SVG-ready map of one country (plus optional neighbours) with projected cities; feeds the svg layer/map_journey."""
    main = geo_outline(name, islands=islands)
    proj = MapProjection(main["bbox"], width)
    paths = {main["name"]: proj.path(main["rings"])}
    for other in extra_countries:
        o = geo_outline(other, max_points=300, islands=False)
        paths[o["name"]] = proj.path(o["rings"])
    return {"view_box": [proj.width, round(proj.height, 1)], "paths": paths, "cities": {c["name"]: proj(c["lat"], c["lon"]) for c in cities},
            "bbox": main["bbox"], "source": main["source"]}


# ---------------------------------------------------------------- open providers (search only)
def safe_url(url):
    """Percent-encode path/query characters (spaces, curly quotes, Vietnamese) that providers leave raw in their manifests."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(urllib.parse.unquote(p.path), safe="/:@!$&'()*+,;=~-._"),
                                    urllib.parse.quote(p.query, safe="=&/:?+,;%~-._"), p.fragment))


def _get_json(url, timeout=20):
    req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _strip(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def find_sources(query, provider="wikimedia", media="image", limit=10):
    """Search an open provider and return candidates with licence/author/size. Nothing is downloaded."""
    limit = max(1, min(30, limit))
    out = []
    if provider == "wikimedia":
        extra = {"video": " filetype:video", "image": " filetype:bitmap", "audio": " filetype:audio"}.get(media, "")
        q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": limit,
                                    "gsrsearch": query + extra, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 640})
        data = _get_json("https://commons.wikimedia.org/w/api.php?" + q)
        for page in (data.get("query") or {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            out.append({"provider": "wikimedia", "title": page.get("title"), "url": info.get("url"), "page": info.get("descriptionurl"),
                        "thumbnail": info.get("thumburl"), "mime": info.get("mime"), "bytes": info.get("size"),
                        "width": info.get("width"), "height": info.get("height"), "duration": info.get("duration"),
                        "license": _strip((meta.get("LicenseShortName") or {}).get("value")), "artist": _strip((meta.get("Artist") or {}).get("value")),
                        "credit": _strip((meta.get("Credit") or {}).get("value"))[:200], "usage_terms": _strip((meta.get("UsageTerms") or {}).get("value"))})
    elif provider == "nasa":
        q = urllib.parse.urlencode({"q": query, "media_type": "video" if media == "video" else "image", "page_size": limit})
        data = _get_json("https://images-api.nasa.gov/search?" + q)
        for item in data.get("collection", {}).get("items", [])[:limit]:
            d = (item.get("data") or [{}])[0]
            links = item.get("links") or []
            out.append({"provider": "nasa", "title": d.get("title"), "nasa_id": d.get("nasa_id"), "date": d.get("date_created"),
                        "center": d.get("center"), "page": f"https://images.nasa.gov/details/{d.get('nasa_id')}",
                        "thumbnail": next((l["href"] for l in links if l.get("rel") == "preview"), None), "asset_manifest": item.get("href"),
                        "license": "NASA media (generally not copyrighted in the US; check page for third-party material)",
                        "artist": d.get("photographer") or d.get("secondary_creator") or "NASA", "description": (d.get("description") or "")[:300]})
    else:
        raise ValueError("provider wikimedia|nasa")
    return {"query": query, "provider": provider, "candidates": out,
            "next": "Show the user the chosen file name, source page, licence and size; only after explicit approval call fetch_source. "
                    "For NASA items, read asset_manifest (list of file URLs) to pick a resolution and learn its size first."}


def nasa_files(asset_manifest_url):
    """List the downloadable renditions of a NASA item (URLs only; sizes via HEAD)."""
    urls = _get_json(asset_manifest_url)
    rows = []
    for u in urls[:20]:
        size = None
        try:
            req = urllib.request.Request(safe_url(u), method="HEAD", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                size = int(r.headers.get("Content-Length") or 0) or None
        except Exception:
            pass
        rows.append({"url": u, "bytes": size})
    return {"files": rows}


def fetch_source(url, provider, title, license, credit, source_page, kind, file_name=None, expected_bytes=None, tags="", max_bytes=None):
    """Download ONE file the user has explicitly approved, store it under data/sources/<provider>/ and register it
    in the library with its licence and credit. max_bytes raises the 600 MB cap for a file the user approved at its
    stated size (archival MPEG-2 masters run 1-1.7 GB), never past 4 GB."""
    if provider not in ("wikimedia", "nasa", "naturalearth", "other"):
        raise ValueError("provider wikimedia|nasa|naturalearth|other")
    kind = {"video": "footage", "music": "audio", "photo": "image"}.get(kind, kind)
    if kind not in KINDS:  # checked before downloading: a bad kind used to fail after the whole file had arrived
        raise ValueError(f"kind must be one of {KINDS}")
    if not url.startswith("https://"):
        raise ValueError("https URL required")
    name = file_name or urllib.parse.unquote(url.split("?")[0].rsplit("/", 1)[-1])
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]
    # EDITVIDEO_SOURCES moves downloads to another drive (round 13: 4K stock on G: when the repo drive had 2 GB free)
    folder = Path(os.environ.get("EDITVIDEO_SOURCES") or ROOT / "data" / "sources") / ("commons" if provider == "wikimedia" else provider)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if dest.exists():
        raise ValueError(f"Already downloaded: {dest}")
    cap = min(int(max_bytes), 4 * 1024 ** 3) if max_bytes else MAX_DOWNLOAD
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA})
    total = 0
    import time
    waited = 0.0
    for attempt in range(4):  # servers rate-limit bursts (Wikimedia answered 429 after six files): wait as asked, briefly
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 3:
                raise
            ra = e.headers.get("Retry-After")
            wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else 15.0 * (attempt + 1)
            if waited + wait > 60:  # one tool call does not hang for minutes: report when to try again
                raise ValueError(f"Rate limited by the server (HTTP {e.code}); try this file again in about {int(max(wait, 60))} s, one file at a time")
            time.sleep(wait)
            waited += wait
    try:
      with resp as r, open(tmp, "wb") as f:
        size = int(r.headers.get("Content-Length") or 0)
        if size > cap:
            raise ValueError(f"File is {size} bytes, above the {cap} limit")
        if expected_bytes and size and abs(size - expected_bytes) > max(1024, expected_bytes * .02):
            raise ValueError(f"Server size {size} differs from the approved size {expected_bytes}; ask the user again")
        for chunk in iter(lambda: r.read(1 << 20), b""):
            total += len(chunk)
            if total > cap:
                raise ValueError("Download exceeded size limit")
            f.write(chunk)
        # A CDN that closes the connection early (an expiring signed URL mid-transfer) ends the stream cleanly: the
        # file keeps its header's duration but stops decoding where the bytes stop. Never keep or register that.
        if size and total < size:
            raise ValueError(f"Short download: {total} of {size} bytes arrived; fetch the file again")
    except BaseException:
        tmp.unlink(missing_ok=True)  # a partial file is never left behind
        raise
    tmp.replace(dest)
    entry = register_resource(dest, kind, title, license, credit, source_page, tags, "", provider=provider)
    with open(folder / "credits.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"title": title, "url": url, "page": source_page, "size": total, "license": license, "artist": credit}, ensure_ascii=False) + "\n")
    return {"path": str(dest), "bytes": total, "library_entry": entry}


# ---------------------------------------------------------------- provenance
SHA_CACHE = ROOT / "data" / "library" / "sha-cache.json"


def _sha_cached(path, cache):
    p = Path(path)
    st = p.stat()
    key = f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    if key not in cache:
        cache[key] = _sha(p)
        cache["_new"] = cache.get("_new", 0) + 1
        if cache["_new"] >= 25:  # a long trace keeps what it has hashed even if it is stopped
            cache["_new"] = 0
            SHA_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _atomic(SHA_CACHE, json.dumps(cache))
    return cache[key]


class _Index:
    """sha256 -> origin, over library files, every project's assets and media-task artifacts (built once per call)."""

    def __init__(self):
        self.cache = json.loads(SHA_CACHE.read_text(encoding="utf-8")) if SHA_CACHE.exists() else {}
        self.library = {e["sha256"]: e for e in _load()}
        self.assets, self.by_path = {}, {}
        for proj in store.list_projects():
            for a in store.assets(proj["id"]):
                if a.get("sha256"):
                    self.assets.setdefault(a["sha256"], []).append(a)
                if a.get("path"):
                    self.by_path[str(Path(a["path"]).resolve()).casefold()] = a
        self._artifacts = None
        self._artifact_paths = None
        self.tasks = {}  # media task id -> record, read once per index
        self.seen = set()  # assets already followed in the current trace: rebuilt projects hold 100+ copies of one file

    def task(self, task_id):
        from . import media_tasks
        if task_id not in self.tasks:
            try:
                self.tasks[task_id] = media_tasks.get(task_id)
            except Exception:
                self.tasks[task_id] = None
        return self.tasks[task_id]

    @property
    def artifact_paths(self):
        """resolved path -> media task id for every completed task's result files: found without hashing anything."""
        if self._artifact_paths is None:
            self._artifact_paths = {}
            import sqlite3
            try:
                with store.connection() as db:
                    rows = db.execute("SELECT id,result FROM media_tasks WHERE state='completed' AND result IS NOT NULL").fetchall()
            except sqlite3.OperationalError:
                rows = []
            for task_id, result in rows:
                try:
                    arts = (json.loads(result) or {}).get("artifacts") or {}
                except Exception:
                    continue
                for v in arts.values():
                    if isinstance(v, str):
                        self._artifact_paths[str(Path(v).resolve()).casefold()] = task_id
        return self._artifact_paths

    def artifact(self, sha, size):
        """media task id whose result file has these bytes; only artifacts of the same size are hashed."""
        if self._artifacts is None:
            self._artifacts = {}
            for path, task_id in self.artifact_paths.items():
                p = Path(path)
                if p.is_file():
                    self._artifacts.setdefault(p.stat().st_size, []).append((p, task_id))
        for p, task_id in self._artifacts.get(size, []):
            if _sha_cached(p, self.cache) == sha:
                return task_id
        return None

    def save(self):
        SHA_CACHE.parent.mkdir(parents=True, exist_ok=True)
        self.cache.pop("_new", None)
        _atomic(SHA_CACHE, json.dumps(self.cache))


def trace_origin(asset, index=None, depth=0, chain=None):
    """Follow provenance (imports, media tasks, copies across projects) back to a library record."""
    index = index or _Index()
    chain = chain if chain is not None else []
    if depth == 0:
        index.seen = set()
    if depth > 8 or asset is None or asset.get("id") in index.seen:  # an asset already followed in this trace adds nothing
        return None, chain
    index.seen.add(asset.get("id"))
    sha = asset.get("sha256")
    if sha in index.library:
        return index.library[sha], chain
    prov = asset.get("provenance") or {}
    def from_task(task_id, d):
        task = index.task(task_id)
        if task is None:
            return None
        chain.append(f"{task['kind']} task {task_id[:8]}")
        req = task.get("request") or {}
        for k in ("subject_task_id", "depth_task_id"):
            if req.get(k):
                hit = from_task(req[k], d + 1)
                if hit:
                    return hit
        if req.get("path") and Path(req["path"]).is_file():
            return from_file(req["path"], d + 1)
        return None
    def from_file(path, d):
        rp = str(Path(path).resolve()).casefold()
        if rp in index.by_path:
            chain.append(f"asset {index.by_path[rp]['id'][:8]}")
            return trace_origin(index.by_path[rp], index, d, chain)[0]
        if rp in index.artifact_paths:  # a task's own result file: follow the task without hashing the store
            return from_task(index.artifact_paths[rp], d + 1)
        f_sha = _sha_cached(path, index.cache)
        if f_sha in index.library:
            return index.library[f_sha]
        for other in index.assets.get(f_sha, []):
            hit = trace_origin(other, index, d, chain)[0]
            if hit:
                return hit
        return None  # a copy of an artifact under another path is not searched by hash: that meant hashing every artifact
    if prov.get("media_task_id"):
        hit = from_task(prov["media_task_id"], depth + 1)
        if hit:
            return hit, chain
    # An import copies bytes, so the asset's own sha equals its source's: look for the same bytes elsewhere —
    # a library file, another project's asset with richer provenance, or a media task's result artifact.
    for src in {prov.get("source_sha256"), sha} - {None}:
        if src in index.library:
            return index.library[src], chain
        copies = [] if ("sha", src) in index.seen else index.assets.get(src, [])  # the trace that first reached these bytes walks their copies
        index.seen.add(("sha", src))
        for other in sorted(copies, key=lambda a: a.get("created_at", "")):
            if other.get("id") not in index.seen and (other.get("provenance") or {}) != prov:
                n = len(chain)
                chain.append(f"copy of asset {other['id'][:8]}")
                hit, _ = trace_origin(other, index, depth + 1, chain)
                if hit:
                    return hit, chain
                del chain[n:]  # the trace shows the path that led somewhere, not every copy that did not
        if src == sha and asset.get("path") and Path(asset["path"]).is_file():
            task_id = index.artifact(sha, Path(asset["path"]).stat().st_size)
            hit = from_task(task_id, depth + 1) if task_id else None
            if hit:
                return hit, chain
    return None, chain


# ---------------------------------------------------------------- credits
def _voice_credit(pid):
    """Credit for an offline synthetic narration voice (Piper model card licence), from the plan's voice-backend.json."""
    import re
    vb = store.folder(pid) / "plan" / "voice-backend.json"
    if not vb.exists() or store.read_json(vb).get("backend") != "piper":
        return None
    from . import voices
    model = voices.piper_model(voices.language(store.get_project(pid)["config"]))
    if not model:
        return None
    card = next(iter(model.parent.glob(model.name.removesuffix(".onnx") + "*MODEL_CARD*")), None)
    text = card.read_text(encoding="utf-8") if card else ""
    url = (re.search(r"License:\s*(\S+)", text) or [None, ""])[1]
    lic = "CC BY 4.0" if "creativecommons.org/licenses/by/4.0" in url else (url or "see the voice's model card")
    dataset = (re.search(r"URL:\s*(\S+)", text) or [None, ""])[1]
    return {"credit": f"Piper voice {model.stem}" + (f" (dataset: {dataset})" if dataset else ""), "license": lic}


def license_url(license):
    """Canonical deed URL for a Creative Commons licence name ("CC BY-SA 4.0" → creativecommons.org/licenses/by-sa/4.0/)."""
    m = re.match(r"CC (BY(?:-[A-Z]{2})*) (\d\.\d)", str(license or "").strip(), re.I)
    return f"https://creativecommons.org/licenses/{m.group(1).lower()}/{m.group(2)}/" if m else None


def project_credits(pid):
    """Match every asset used by the project's timeline to library records (by sha256) and compile credit lines.
    Assets without a record are listed so the agent can ask or register them instead of guessing."""
    from . import agent
    t = agent.read(pid).get("timeline") or {}
    used = set()
    for s in t.get("shots", []):
        if s.get("asset_id"):
            used.add(s["asset_id"])
    for l in t.get("layers", []):
        if l.get("asset_id"):
            used.add(l["asset_id"])
        data = l.get("data") or {}
        for o in data.get("objects", []):
            for k in ("texture", "bump_texture", "emissive_texture", "alpha_texture", "displacement_texture", "model"):
                if o.get(k):
                    used.add(o[k])
        for k in ("background_texture", "environment_texture"):
            if data.get(k):
                used.add(data[k])
    # sound too: music beds and effects are works with licences (they had been left out of every credit list)
    used.update(c["asset_id"] for c in t.get("audio_clips", []) if c.get("asset_id"))
    cfg = store.get_project(pid).get("config") or {}
    used.update(cfg[k] for k in ("music_id", "narration_id") if cfg.get(k))  # the voice track is credited like any sound
    procedural = {store.read_json(f).get("sha256") for f in (store.DATA / "sound-design").glob("*/sound.json")}  # EditVideo's own synthesis
    index = _Index()
    lines, missing, traced, sources = {}, [], [], {}
    for aid in sorted(used):
        try:
            a = store.find_asset(pid, aid)
        except Exception:
            continue
        if a.get("sha256") in procedural or a.get("name") == "silent-carrier.mp4" or (a.get("provenance") or {}).get("operation") == "generated silence":
            traced.append({"asset": aid, "name": a.get("name"), "origin": "procedural (design_sound), no third-party licence", "via": []})
            continue
        e, chain = trace_origin(a, index)
        if e:
            lines.setdefault((e["credit"], e["license"]), []).append(e["title"])
            if e.get("source_url"):
                sources.setdefault((e["credit"], e["license"]), set()).add(e["source_url"])
            traced.append({"asset": aid, "name": a.get("name"), "origin": e["id"], "via": chain})
        else:
            missing.append({"asset": aid, "name": a.get("name"), "tags": a.get("tags"), "via": chain})
    index.save()
    voice = _voice_credit(pid)
    if voice:
        lines.setdefault((voice["credit"], voice["license"]), []).append("narration voice")
    credits = [{"credit": c, "license": l, "works": sorted(set(w)), **({"sources": sorted(sources[(c, l)])} if (c, l) in sources else {}),
                **({"license_url": license_url(l)} if license_url(l) else {})} for (c, l), w in sorted(lines.items())]
    text = " · ".join(f"{c['credit']} ({c['license']})" for c in credits)
    return {"credits": credits, "text": text, "traced_assets": traced, "unrecorded_assets": missing,
            "note": "Origins follow provenance through imports, media tasks (retime, colour, subject masks, depth) and copies between "
                    "projects. Unrecorded assets need register_resource (with the licence of their real source) or a question to the user; "
                    "do not invent credits."}
