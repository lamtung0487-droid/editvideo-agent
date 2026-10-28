"""Satellite imagery under a terrain (round 13: the owner found the sixth cut's 3D "ugly, too simple"; the height-tinted
relief read as green felt with snow on 1,600 m hills). Sentinel-2 cloudless by EOX IT Services, the 2016 mosaic, was
published as CC BY 4.0 ("Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus
Sentinel data 2016)"); later years are CC BY-NC-SA. Licence to verify before a commercial release: in 2026 EOX's current
pages could not confirm the 2016 terms (research notes, reports/Nâng cấp 3D phim tài liệu.md). For publication, build a
cloud-free composite from Copernicus Sentinel-2 L2A itself (free for any use, credited "Contains modified Copernicus
Sentinel data [year]"). Tiles (Web Mercator, 256 px) are cached in the store and
resampled onto the same longitude/latitude grid as terrain.elevation, so pixel (row, col) of the image sits over the same
ground as the height sample."""
import io, math, os, time, urllib.request
import numpy as np
from . import store

S2C_2016 = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
CREDIT = "Ảnh vệ tinh: Sentinel-2 cloudless 2016, EOX IT Services GmbH (dữ liệu Copernicus Sentinel 2016 đã xử lý)"  # licence: see above
# Esri World Imagery: sub-metre aerial and satellite mosaics (Maxar, Earthstar Geographics...). Esri's terms do not clear
# offline export or video use: internal research cuts only (the owner's decision, 2026-10-27), never a release.
ESRI_WI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
SOURCES = {"s2c2016": {"url": S2C_2016, "credit": CREDIT, "max_zoom": 15, "internal_only": False,
                       "license": "Sentinel-2 cloudless 2016 (EOX): CC BY 4.0 claimed for the 2016 mosaic, unverified (EOX now lists CC BY-NC-SA 4.0)"},
           "esri": {"url": ESRI_WI, "credit": "Ảnh vệ tinh: Esri World Imagery (Esri, Maxar, Earthstar Geographics) · chỉ dùng nội bộ",
                    "max_zoom": 18, "internal_only": True, "license": "Esri World Imagery: internal research use only (Esri terms)"}}


def _tile_xy(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(z, x, y, retries=3, source="s2c2016"):
    src = SOURCES[source]
    if source == "esri" and os.environ.get("EDITVIDEO_ESRI_INTERNAL") != "1":
        raise ValueError("Esri World Imagery's terms do not clear offline export or video use: it is for internal research only, "
                         "switched on with EDITVIDEO_ESRI_INTERNAL=1 (its renders stay internal in the licence ledger)")
    d = store.DATA / "cache" / source / str(z) / str(x)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{y}.jpg"
    if f.is_file() and f.stat().st_size > 500:
        return f.read_bytes()
    for k in range(retries):
        try:
            req = urllib.request.Request(src["url"].format(z=z, x=x, y=y), headers={"User-Agent": "EditVideoAgent/1.0 (documentary terrain)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
            f.write_bytes(b)
            time.sleep(.05)  # gentle on a free service
            return b
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"{source} tile {z}/{x}/{y} could not be fetched")


def satellite(bbox, width, height, zoom=14, source="s2c2016"):
    """An RGB image (height, width, 3, uint8) of bbox [west, south, east, north], north up, on a regular lon/lat grid,
    from `source` at `zoom` (14: about 9 m a pixel at 21° N; Sentinel-2 holds no more than 10 m, Esri goes to 18)."""
    if zoom > SOURCES[source]["max_zoom"]:
        raise ValueError(f"{source} stops at zoom {SOURCES[source]['max_zoom']}")
    from PIL import Image
    w, s, e, n = bbox
    x0, y0 = _tile_xy(w, n, zoom)
    x1, y1 = _tile_xy(e, s, zoom)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            im = Image.open(io.BytesIO(_tile(zoom, tx, ty, source=source))).convert("RGB")
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = np.asarray(im)
    lons = np.linspace(w, e, width)
    lats = np.linspace(n, s, height)
    px = np.array([(_tile_xy(lo, n, zoom)[0] - tx0) * 256 for lo in lons])
    py = np.array([(_tile_xy(w, la, zoom)[1] - ty0) * 256 for la in lats])
    from scipy.ndimage import map_coordinates
    yy, xx = np.meshgrid(py, px, indexing="ij")
    out = np.stack([map_coordinates(mosaic[..., c].astype(np.float32), [yy, xx], order=1, mode="nearest") for c in range(3)], -1)
    return np.clip(out, 0, 255).astype(np.uint8)
