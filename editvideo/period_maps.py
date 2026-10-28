"""Period maps draped on terrain (reports/Nâng cấp 3D phim tài liệu.md, P1-6): a wartime topographic sheet laid on real
heights reads as history in a way a modern satellite image cannot. US Army Map Service series L7014 (Vietnam) and
L7015 (Laos), 1:50,000, 1960s, are US federal works (public domain; ANU marks its scans "Copyright Expired"); the USGS
store serves them as TerraGo GeoPDFs (store.usgs.gov/assets/yimages/NGA/<series><sheet>_geo.pdf) whose LGIDict carries
registration points (page coordinates to UTM metres on the sheet's datum, Indian 1960 for these series) and the neatline.

A sheet is rendered once at `dpi` and cached; drape() samples it on a WGS84 lon/lat grid (the grid terrain.elevation
and imagery.satellite use), through the sheet's own datum, so a 1967 airstrip lands on today's."""
import json, math, re
from pathlib import Path
import numpy as np
from . import store

USGS_GEOPDF = "https://store.usgs.gov/assets/yimages/NGA/{series}{sheet}_geo.pdf"
DATUMS = {"IND-I": 3148}  # NGA datum code on these sheets -> EPSG of "Indian 1960 / UTM zone 48N" (central meridian 105)
CREDIT = "Bản đồ: US Army Map Service, loạt {series} 1:50.000, tờ {sheet} ({year}), qua USGS"


def _cache():
    d = store.DATA / "cache" / "period_maps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch(series, sheet):
    """The GeoPDF of a sheet (e.g. "L7014", "56514" for 5651 IV), downloaded once."""
    import urllib.request
    f = _cache() / f"{series}{sheet}_geo.pdf"
    if not f.is_file():
        req = urllib.request.Request(USGS_GEOPDF.format(series=series, sheet=sheet), headers={"User-Agent": "EditVideoAgent/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            b = r.read()
        if len(b) < 10000:
            raise ValueError(f"No GeoPDF for {series} {sheet}")
        f.write_bytes(b)
    return f


def sheet(pdf, dpi=250):
    """A GeoPDF sheet: its page rendered to PNG (cached), registration points and neatline in page units, its CRS."""
    import pymupdf
    pdf = Path(pdf)
    meta_f = _cache() / f"{pdf.stem}-{dpi}.json"
    png = _cache() / f"{pdf.stem}-{dpi}.png"
    if meta_f.is_file() and png.is_file():
        return {**json.loads(meta_f.read_text(encoding="utf-8")), "png": str(png)}
    doc = pymupdf.open(str(pdf))
    page = doc[0]
    o = doc.xref_object(page.xref)
    nums = lambda s_: [float(x) for x in s_.replace("(", " ").replace(")", " ").split()]
    reg = re.search(r"/Registration \[(.*?)\] \]", o, re.S)
    pts = [nums(m) for m in re.findall(r"\[ ([^\[\]]+) \]", reg.group(1) + " ]")]
    pts = [p for p in pts if len(p) == 4]
    neat = nums(re.search(r"/Neatline \[ ([^\]]+) \]", o).group(1))
    datum = re.search(r"/Datum \(([^)]+)\)", o).group(1)
    cm = float(re.search(r"/CentralMeridian \(([^)]+)\)", o).group(1))
    if datum not in DATUMS or abs(cm - 105) > 1e-6:
        raise ValueError(f"Unknown sheet datum/zone {datum} {cm}: add it to period_maps.DATUMS")
    page.get_pixmap(dpi=dpi).save(str(png))
    meta = {"pdf": str(pdf), "dpi": dpi, "page": [page.rect.width, page.rect.height], "registration": pts,
            "neatline": [neat[i:i + 2] for i in range(0, 8, 2)], "epsg": DATUMS[datum]}
    meta_f.write_text(json.dumps(meta), encoding="utf-8")
    return {**meta, "png": str(png)}


def _affine(src, dst):
    """Least-squares affine from src [[x, y], ...] to dst [[u, v], ...]: (A 2x2, t 2)."""
    S = np.c_[np.asarray(src, float), np.ones(len(src))]
    M, *_ = np.linalg.lstsq(S, np.asarray(dst, float), rcond=None)
    return M[:2].T, M[2]


def _inside(poly, pts):
    """Points inside a polygon (even-odd ray casting, vectorised over the points)."""
    x, y = pts[:, 0], pts[:, 1]
    hit = np.zeros(len(pts), bool)
    for (x0, y0), (x1, y1) in zip(poly, np.roll(poly, -1, 0)):
        crosses = (y0 > y) != (y1 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        hit ^= crosses & (x < xc)
    return hit


def drape(bbox, width, height, sheets, base=None, feather_px=6):
    """An RGB image (height, width, 3) of bbox [west, south, east, north] on a regular WGS84 lon/lat grid, north up:
    each sheet where it lies, `base` (an RGB array of the same grid, e.g. satellite imagery) elsewhere, the seam
    feathered. Returns (image, report) with each sheet's registration residual in metres."""
    from PIL import Image
    from pyproj import Transformer
    from scipy.ndimage import map_coordinates, distance_transform_edt
    Image.MAX_IMAGE_PIXELS = None
    w, s, e, n = bbox
    lon, lat = np.meshgrid(np.linspace(w, e, width), np.linspace(n, s, height))
    out = np.zeros((height, width, 3), np.float32) if base is None else np.asarray(base, np.float32).copy()
    cover = np.zeros((height, width), np.float32)
    report = []
    for sh in sheets:
        pts = np.asarray(sh["registration"], float)
        A, t = _affine(pts[:, 2:], pts[:, :2])  # UTM metres -> page units
        back_A, back_t = _affine(pts[:, :2], pts[:, 2:])
        resid = float(np.sqrt(((pts[:, :2] @ back_A.T + back_t - pts[:, 2:]) ** 2).sum(1)).max())
        # the best published datum shift (Indian 1960 -> WGS 84, ~44 m): a plain Transformer.from_crs fell back to the
        # "ballpark" no-shift path and put the 1967 airstrip 400 m east of today's
        from pyproj.transformer import TransformerGroup
        tr = next(t_ for t_ in TransformerGroup(4326, sh["epsg"], always_xy=True).transformers if "Ballpark" not in t_.description)
        x, y = tr.transform(lon.ravel(), lat.ravel())
        pu = np.c_[x, y] @ A.T + t  # page units, origin bottom-left
        k = sh["dpi"] / 72.0
        col, row = pu[:, 0] * k, (sh["page"][1] - pu[:, 1]) * k
        inside = _inside(np.asarray(sh["neatline"], float), pu).reshape(height, width)
        if not inside.any():
            report.append({"sheet": Path(sh["pdf"]).stem, "covered": 0.0})
            continue
        img = np.asarray(Image.open(sh["png"]).convert("RGB"), np.float32)
        vals = np.stack([map_coordinates(img[..., c], [row, col], order=1, mode="nearest") for c in range(3)], -1).reshape(height, width, 3)
        a = np.clip(distance_transform_edt(inside) / max(1, feather_px), 0, 1) * inside
        a = np.maximum(a, 0) * (1 - cover)
        out = out * (1 - a[..., None]) + vals * a[..., None]
        cover = np.clip(cover + a, 0, 1)
        report.append({"sheet": Path(sh["pdf"]).stem, "covered": round(float(inside.mean()), 3), "registration_residual_m": round(resid, 2)})
    return np.clip(out, 0, 255).astype(np.uint8), report


# ---------------------------------------------------------------- georeferenced rasters (KH-9, CORONA, aerial mosaics)
# Barthelme et al.'s georeferenced KH-9 HEXAGON mosaics (University of Edinburgh DataShare: Quảng Trị 20.3.1973,
# doi:10.7488/ds/7682; the Vietnam-Laos-Cambodia tri-border 4.11.1972, doi:10.7488/ds/7683) are GeoTIFFs at 1 m and
# 8 m a pixel: the 1 m file of a province is several gigabytes, so a drape reads only the tiles under its bbox.

def geotiff(path):
    """A GeoTIFF's georeferencing: {"epsg", "affine" (a, b, c, d, e, f: x = a*col + b*row + c, y = d*col + e*row + f),
    "size": [width, height], "tiled"}. Reads the tags only."""
    import tifffile
    with tifffile.TiffFile(str(path)) as tf:
        page = tf.pages[0]
        tags = page.tags
        tie = tags.get(33922)
        scale = tags.get(33550)
        trans = tags.get(34264)
        if trans is not None:
            m = list(trans.value)
            aff = (m[0], m[1], m[3], m[4], m[5], m[7])
        elif tie is not None and scale is not None:
            i, j, _, x, y, _ = list(tie.value)[:6]
            sx, sy = list(scale.value)[:2]
            aff = (sx, 0.0, x - i * sx, 0.0, -sy, y + j * sy)
        else:
            raise ValueError(f"{path} carries no GeoTIFF georeferencing (tags 33922/33550 or 34264)")
        gk = tf.geotiff_metadata or {}
        epsg = gk.get("ProjectedCSTypeGeoKey") or gk.get("GeographicTypeGeoKey")
        epsg = int(getattr(epsg, "value", epsg)) if epsg is not None else None
        if not epsg or epsg == 32767:
            raise ValueError(f"{path}: user-defined CRS; add its EPSG code")
        return {"epsg": epsg, "affine": [float(v) for v in aff], "size": [page.imagewidth, page.imagelength], "tiled": page.is_tiled}


def read_window(path, x0, y0, x1, y1, step=1):
    """Pixels [y0:y1:step, x0:x1:step] of the first page (single band or RGB), decoding only the tiles or strips it
    covers and keeping every step-th sample of each as it goes (a full-resolution window of a province never sits in
    memory)."""
    import tifffile
    with tifffile.TiffFile(str(path)) as tf:
        page = tf.pages[0]
        W, H = page.imagewidth, page.imagelength
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        spp = page.samplesperpixel
        out = np.zeros((len(range(y0, y1, step)), len(range(x0, x1, step))) + ((spp,) if spp > 1 else ()), page.dtype)
        if out.size == 0:
            return out
        if page.is_tiled:
            th, tw = page.tilelength, page.tilewidth
            per_row = (W + tw - 1) // tw
            rows, cols = range(y0 // th, (y1 - 1) // th + 1), range(x0 // tw, (x1 - 1) // tw + 1)
            idx = [r * per_row + c for r in rows for c in cols]
        else:
            rps = page.rowsperstrip
            th, tw, per_row = rps, W, 1
            idx = list(range(y0 // rps, (y1 - 1) // rps + 1))
        fh = tf.filehandle
        for k in idx:
            fh.seek(page.dataoffsets[k])
            seg, (_, _, ty, tx, _), shape = page.decode(fh.read(page.databytecounts[k]), k, jpegtables=page.jpegtables)
            if seg is None:
                continue
            seg = seg.reshape(shape[1], shape[2], shape[3]) if spp > 1 else seg.reshape(shape[1], shape[2])
            ty, tx = (k // per_row) * th, (k % per_row) * tw
            a0, b0 = max(y0, ty), max(x0, tx)
            a1, b1 = min(y1, ty + seg.shape[0]), min(x1, tx + seg.shape[1])
            # the samples on the output grid (rows/cols y0 + k*step) that fall in this tile
            ra = range(y0 + -(-(a0 - y0) // step) * step, a1, step)
            ca = range(x0 + -(-(b0 - x0) // step) * step, b1, step)
            if len(ra) and len(ca):
                out[(ra.start - y0) // step:(ra.start - y0) // step + len(ra), (ca.start - x0) // step:(ca.start - x0) // step + len(ca)] = \
                    seg[ra.start - ty:ra.stop - ty:step, ca.start - tx:ca.stop - tx:step][:len(ra), :len(ca)]
        return out


def drape_raster(bbox, width, height, path, base=None, feather_px=8):
    """A georeferenced raster on the WGS84 lon/lat grid of bbox (north up), over `base` where it has data, the seam
    feathered; returns (image uint8 RGB, report). Only the tiles under the bbox are decoded, decimated to about the
    output's resolution before any conversion (a 1 m province mosaic is gigabytes). No-data is the file's GDAL_NODATA
    tag when it has one (0 is a real black otherwise: shadows stay); 16-bit samples scale by the type's range."""
    from pyproj import Transformer
    from scipy.ndimage import map_coordinates, distance_transform_edt
    import tifffile
    info = geotiff(path)
    with tifffile.TiffFile(str(path)) as tf:
        tag = tf.pages[0].tags.get(42113)
        nodata = float(str(tag.value).strip("\x00 ")) if tag is not None and str(tag.value).strip("\x00 ") else None
    a, b, c, d, e, f = info["affine"]
    w, s, e_, n = bbox
    lon, lat = np.meshgrid(np.linspace(w, e_, width), np.linspace(n, s, height))
    x, y = Transformer.from_crs(4326, info["epsg"], always_xy=True).transform(lon.ravel(), lat.ravel())
    det = a * e - b * d
    col = (e * (x - c) - b * (y - f)) / det
    row = (-d * (x - c) + a * (y - f)) / det
    c0, c1 = int(np.floor(col.min())) - 2, int(np.ceil(col.max())) + 3
    r0, r1 = int(np.floor(row.min())) - 2, int(np.ceil(row.max())) + 3
    k = max(1, int(min((c1 - c0) / width, (r1 - r0) / height) / 1.5))  # ~1.5 samples per output pixel, read strided
    raw = read_window(path, c0, r0, c1, r1, step=k)
    flat = raw.reshape(raw.shape[0], raw.shape[1], -1)
    valid = ~np.isnan(flat).any(-1) if np.issubdtype(raw.dtype, np.floating) else np.ones(raw.shape[:2], bool)
    if nodata is not None:
        valid &= (flat != nodata).any(-1)
    valid_src = valid.astype(np.float32)
    raw = np.nan_to_num(raw)
    if np.issubdtype(raw.dtype, np.integer) and raw.dtype.itemsize > 1:  # 12-bit scans stored in 16 bits stay 12-bit
        top = float(raw.max()) if raw.size else 1.0
        scale = 255.0 / (4095.0 if top <= 4095 else np.iinfo(raw.dtype).max)
    else:
        scale = 1.0
    win = raw.astype(np.float32) * scale
    if win.ndim == 2:
        win = win[..., None]
    rr, cc = (row - max(0, r0)) / k, (col - max(0, c0)) / k  # the window's first sample is at its clipped origin
    vals = np.stack([map_coordinates(win[..., ch], [rr, cc], order=1, mode="constant", cval=0) for ch in range(win.shape[-1])], -1)
    vals = vals.reshape(height, width, -1)
    if vals.shape[-1] == 1:
        vals = np.repeat(vals, 3, -1)
    vals = vals[..., :3]
    inside = map_coordinates(valid_src, [rr, cc], order=0, mode="constant", cval=0).reshape(height, width) > .5
    out = np.zeros((height, width, 3), np.float32) if base is None else np.asarray(base, np.float32).copy()
    alpha = np.clip(distance_transform_edt(inside) / max(1, feather_px), 0, 1)[..., None]
    out = out * (1 - alpha) + vals * alpha
    return np.clip(out, 0, 255).astype(np.uint8), {"raster": Path(path).name, "covered": round(float(inside.mean()), 3), "epsg": info["epsg"],
                                                  "pixel_m": round(abs(a), 3), "window": [c0, r0, c1, r1], "decimation": k, "nodata": nodata}
