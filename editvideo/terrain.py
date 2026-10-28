"""Terrain flyover: a landscape in 3D from real elevation data, for places whose shape is the story (round 13: the valley
of Điện Biên Phủ, a "bowl" ringed by hills the artillery was hauled onto; the Trường Sơn range the trail crossed).

Elevation comes from SRTM 1 arc-second tiles (NASA, public domain; served free by the AWS Terrain Tiles open dataset),
cached in the store. A bounding box becomes two images: a height map (the scene's displacement texture) and a colour
map (elevation tint times hillshade from a north-west sun), and a Scene3D request: a displaced plane, small markers
with place labels, a sun and an ambient light, depth fog, and a camera flying through authored keys given in
longitude, latitude and metres. The relief is exaggerated (say so on screen); labels sit where their coordinates are,
which is as precise as the coordinates given. It is an illustration of the ground, not a survey.
"""
import gzip
import math
import urllib.request
from pathlib import Path
import numpy as np
from PIL import Image
from . import store

SKADI = "https://elevation-tiles-prod.s3.amazonaws.com/skadi/{ns}{alat:02d}/{ns}{alat:02d}{ew}{alon:03d}.hgt.gz"
# Copernicus GLO-30 DSM (ESA; free incl. commercial use with the notice below): newer and with fewer voids than SRTM,
# but a surface model, so forest canopy is in the heights. Cloud-optimised GeoTIFFs on AWS, no account needed.
COP30 = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{alat:02d}_00_{ew}{alon:03d}_00_DEM/Copernicus_DSM_COG_10_{ns}{alat:02d}_00_{ew}{alon:03d}_00_DEM.tif"
DEM_LICENSE = {"srtm": "Public domain (NASA SRTM)", "cop30": "Copernicus DEM GLO-30 licence (free use with attribution)"}
DEM_CREDIT = {"srtm": "Độ cao: SRTM (NASA)", "cop30": "Độ cao: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 và © Airbus Defence and Space GmbH 2014-2018, do ESA cung cấp trong chương trình Copernicus"}
VOID = -32768
RAMP = [(0.00, (62, 92, 54)), (.18, (92, 116, 64)), (.38, (139, 140, 92)), (.58, (150, 124, 88)), (.80, (122, 98, 78)), (1.0, (214, 206, 190))]


def _cache():
    d = store.DATA / "cache" / "dem"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tile(lat, lon, source="srtm"):
    """The elevation tile whose south-west corner is (lat, lon), whole degrees, north row first: SRTM as int16 (VOID
    marks gaps), Copernicus GLO-30 as float32 (an all-sea tile does not exist: zeros)."""
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    name = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"
    if source == "cop30":
        f = _cache() / f"{name}.cop30.npy"
        if not f.is_file():
            import io
            import tifffile
            try:
                with urllib.request.urlopen(COP30.format(ns=ns, alat=abs(lat), ew=ew, alon=abs(lon)), timeout=300) as r:
                    a = tifffile.imread(io.BytesIO(r.read())).astype(np.float32)
            except urllib.error.HTTPError as e:
                if e.code not in (403, 404):
                    raise
                a = np.zeros((3601, 3601), np.float32)  # open sea: Copernicus publishes no tile
            np.save(f, a)
        return np.load(f)
    f = _cache() / f"{name}.hgt"
    if not f.is_file():
        url = SKADI.format(ns=ns, alat=abs(lat), ew=ew, alon=abs(lon))
        with urllib.request.urlopen(url, timeout=180) as r:
            data = gzip.decompress(r.read())
        tmp = f.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(f)
    a = np.frombuffer(f.read_bytes(), ">i2")
    n = int(round(math.sqrt(a.size)))
    return a.reshape(n, n)


def elevation(bbox, width=1024, source="cop30"):
    if source == "cop30":
        try:
            import tifffile  # noqa: F401  (the geo extra: pip install -r requirements.geo.txt)
        except ImportError:
            source = "srtm"
    """Heights in metres over bbox [lon0, lat0, lon1, lat1] (north row first), `width` samples across and as many down as
    keep ground distances square. Voids are filled from their neighbours."""
    from scipy.ndimage import map_coordinates, distance_transform_edt
    lon0, lat0, lon1, lat1 = bbox
    if not (lon0 < lon1 and lat0 < lat1 and lon1 - lon0 <= 4 and lat1 - lat0 <= 4):
        raise ValueError("bbox is [lon0, lat0, lon1, lat1], at most 4 degrees a side")
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    height = max(2, int(round(width * (lat1 - lat0) / ((lon1 - lon0) * kx))))
    lons = np.linspace(lon0, lon1, width)
    lats = np.linspace(lat1, lat0, height)
    out = np.full((height, width), np.nan, np.float32)
    for la in range(math.floor(lat0), math.ceil(lat1)):
        for lo in range(math.floor(lon0), math.ceil(lon1)):
            t = tile(la, lo, source).astype(np.float32)
            t[t == VOID] = np.nan
            ny, nx = t.shape[0] - 1, t.shape[1] - 1  # Copernicus tiles narrow toward the poles
            ry = (lats >= la) & (lats <= la + 1)
            rx = (lons >= lo) & (lons <= lo + 1)
            if not ry.any() or not rx.any():
                continue
            yy, xx = np.meshgrid((la + 1 - lats[ry]) * ny, (lons[rx] - lo) * nx, indexing="ij")
            vals = map_coordinates(np.nan_to_num(t, nan=-9999), [yy.ravel(), xx.ravel()], order=1, mode="nearest").reshape(yy.shape)
            vals[vals < -1000] = np.nan
            out[np.ix_(ry, rx)] = vals
    bad = np.isnan(out)
    if bad.all():
        raise ValueError("no elevation in that box")
    if bad.any():
        idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
        out = out[tuple(idx)]
    return out


def hillshade(h, cell_m, azimuth=315.0, altitude=45.0, exaggeration=1.0):
    gy, gx = np.gradient(h * exaggeration, cell_m)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(azimuth), math.radians(altitude)
    s = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(s, 0, 1)


def imagery_light(texture, h, bbox, altitude=35.0):
    """The light already baked into satellite imagery: the sun azimuth whose hillshade of the heights best matches the
    image's relief shading (luminance, broad land cover removed). (azimuth, correlation). A 3D sun far from it fights
    the photograph: on the Điện Biên Phủ texture the shading matched light from 150 deg (r=.32) and the bible's 330 deg
    worst (r=-.28)."""
    import hashlib
    import json
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    key = hashlib.sha1(h.tobytes() + str(Path(texture).resolve()).encode() + str(Path(texture).stat().st_size).encode() + str(bbox).encode()).hexdigest()[:16]
    memo = _cache() / f"light-{key}.json"  # 16 s on a 1650 x 1536 grid: measured once
    if memo.is_file():
        m = json.loads(memo.read_text(encoding="utf-8"))
        return m["azimuth"], m["r"]
    rows, cols = h.shape
    im = np.asarray(Image.open(texture).convert("L").resize((cols, rows), Image.BILINEAR), np.float64)
    from scipy.ndimage import gaussian_filter
    detail = im - gaussian_filter(im, max(2.0, cols / 64))  # relief shading, not forest against field
    lat = (bbox[1] + bbox[3]) / 2
    cell = (bbox[2] - bbox[0]) * 111320 * math.cos(math.radians(lat)) / cols
    best = (0.0, -1.0)
    for az in range(0, 360, 15):
        hs = hillshade(h, cell, az, altitude)
        hs = hs - gaussian_filter(hs, max(2.0, cols / 64))
        r = float(np.corrcoef(detail.ravel(), hs.ravel())[0, 1])
        if np.isfinite(r) and r > best[1]:
            best = (float(az), r)
    memo.write_text(json.dumps({"azimuth": best[0], "r": best[1]}), encoding="utf-8")
    return best


def _turn(a, b):
    """Signed smallest turn from azimuth a to b, degrees in (-180, 180]."""
    return (b - a + 180) % 360 - 180


def maps(h, bbox, out_dir, name, exaggeration=2.0, smooth=1.0):
    """The colour map (elevation tint x hillshade) and the height map (8-bit, lightly smoothed so 256 levels do not step)
    as PNG files. Returns their paths and the height range in metres."""
    from scipy.ndimage import gaussian_filter
    lon0, lat0, lon1, lat1 = bbox
    H, W = h.shape
    cell = (lon1 - lon0) * 111320 * math.cos(math.radians((lat0 + lat1) / 2)) / (W - 1)
    lo, hi = float(np.percentile(h, .5)), float(np.percentile(h, 99.8))
    t = np.clip((h - lo) / max(1.0, hi - lo), 0, 1)
    rgb = np.zeros((H, W, 3), np.float32)
    for (a, ca), (b, cb) in zip(RAMP, RAMP[1:]):
        m = (t >= a) & (t <= b)
        f = ((t[m] - a) / (b - a))[:, None]
        rgb[m] = np.array(ca) * (1 - f) + np.array(cb) * f
    shade = hillshade(h, cell, exaggeration=exaggeration)
    rgb = rgb * (.45 + .75 * shade[..., None])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    color = out_dir / f"{name}-color.png"
    height = out_dir / f"{name}-height.png"
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(color)
    Image.fromarray((np.clip(gaussian_filter(t, smooth), 0, 1) * 255 + .5).astype(np.uint8)).save(height)
    return {"color": str(color), "height": str(height), "min_m": round(lo, 1), "max_m": round(hi, 1), "cell_m": round(cell, 2), "size": [W, H]}


class Ground:
    """Scene coordinates for a bbox laid out as a plane `width` units across (x east, z south, y up)."""
    def __init__(self, bbox, width, depth, min_m, max_m, scale):
        self.bbox, self.width, self.depth, self.min_m, self.max_m, self.scale = bbox, width, depth, min_m, max_m, scale

    def xz(self, lon, lat):
        lon0, lat0, lon1, lat1 = self.bbox
        return (lon - lon0) / (lon1 - lon0) * self.width - self.width / 2, (lat1 - lat) / (lat1 - lat0) * self.depth - self.depth / 2

    def y(self, metres):
        return (metres - self.min_m) / max(1.0, self.max_m - self.min_m) * self.scale

    def point(self, lon, lat, metres):
        x, z = self.xz(lon, lat)
        return {"x": round(x, 4), "y": round(self.y(metres), 4), "z": round(z, 4)}


def ground_height(h, bbox, lon, lat):
    lon0, lat0, lon1, lat1 = bbox
    H, W = h.shape
    j = int(round((lon - lon0) / (lon1 - lon0) * (W - 1)))
    i = int(round((lat1 - lat) / (lat1 - lat0) * (H - 1)))
    return float(h[min(H - 1, max(0, i)), min(W - 1, max(0, j))])


def flyover(bbox, color_asset, height_asset, h, rng, places, camera, frames, exaggeration=2.0, width=10.0, sky="#b9c3c6", fog=True):
    """A Scene3D request. places: [{"lon", "lat", "label", "color"?}]; camera: [{"frame", "lon", "lat", "alt_m",
    "look_lon", "look_lat", "look_m"?}] (alt_m above sea level). The relief is `exaggeration` times true height."""
    lon0, lat0, lon1, lat1 = bbox
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    span_x = (lon1 - lon0) * 111320 * kx
    depth = width * (lat1 - lat0) * 111320 / span_x
    scale = (rng["max_m"] - rng["min_m"]) / span_x * width * exaggeration
    g = Ground(bbox, width, depth, rng["min_m"], rng["max_m"], scale)
    objects = [{"id": "terrain", "geometry": "plane", "segments": 512, "size": [width, round(depth, 4), 1], "rotation": {"x": -math.pi / 2},
                "texture": color_asset, "displacement_texture": height_asset, "displacement_scale": round(scale, 4), "roughness": .95, "metalness": 0,
                "color": "#ffffff"}]
    for k, p in enumerate(places):
        m = ground_height(h, bbox, p["lon"], p["lat"]) + (rng["max_m"] - rng["min_m"]) * .02
        objects.append({"id": f"place{k}", "geometry": "sphere", "size": [width * .006] * 3, "position": g.point(p["lon"], p["lat"], m),
                        "color": p.get("color", "#e8b04a"), "emissive": p.get("color", "#e8b04a"), "emissive_intensity": 1.5, "label": p["label"][:80]})
    keys = []
    for c in camera:
        tgt_m = c.get("look_m", ground_height(h, bbox, c["look_lon"], c["look_lat"]))
        keys.append({"frame": int(c["frame"]), "position": g.point(c["lon"], c["lat"], c["alt_m"]), "target": g.point(c["look_lon"], c["look_lat"], tgt_m)})
    for k_ in keys:
        for pt in (k_["position"], k_["target"]):
            for ax in ("x", "y", "z"):
                pt[ax] = max(-100.0, min(100.0, pt[ax]))
    scene = {"objects": objects, "lights": [{"kind": "directional", "position": {"x": -width, "y": width * .8, "z": -width * .6}, "intensity": 2.4},
                                             {"kind": "ambient", "intensity": .9}],
             "camera_keyframes": keys, "camera_position": keys[0]["position"], "camera_target": keys[0]["target"], "fov": 40,
             "background": sky, "ground": False, "shadows": False, "label_font_size": 30, "label_color": "#fbf6ec"}
    if fog:
        scene["fog"] = {"color": sky, "near": round(width * .6, 2), "far": round(width * 2.2, 2)}
    return scene


def blender_shot(name, bbox, frames, camera, places=(), routes=(), width=1024, exaggeration=1.7, imagery_zoom=14,
                 sun=None, sky=None, haze=None, engine="EEVEE", samples=32, stills=None, percent=100, lens=30,
                 font=None, clearance_m=180.0, options=None, imagery_source="s2c2016", dem="cop30", texture_px=None, finish=True,
                 period_map=None, period_raster=None, raster_license="", sun_from_imagery=True, sun_tolerance=10.0):
    """A terrain flyover rendered by Blender (editvideo.blender) on real heights and 2016 satellite imagery: returns
    {"mp4" | "stills", "job", "per_frame_s", "credit"}. camera: [{frame, lon, lat, alt_m, look_lon, look_lat}] in metres
    above sea level; any key lower than the ground under it plus `clearance_m` is raised. stills=[frames] renders those
    frames only (a cheap look check); percent < 100 renders a proxy. options: the template's other parameters (mist, zones,
    strikes, dof, labels_2d, saturation, value, exposure...; see blender_scripts/terrain_shot.py). With labels_2d the
    result carries "tracks", for blender.label_layers. imagery_source: "s2c2016" (10 m, publishable with credit) or
    "esri" (sub-metre, internal only); texture_px caps the texture's long side (default three pixels a height sample; a
    camera 2 km up wants ~2 m a pixel). period_map: [(series, sheet), ...] of AMS GeoPDF sheets (editvideo.period_maps)
    draped over the imagery where they lie, e.g. [("L7014", "56514"), ("L7015", "55511")] for Điện Biên Phủ in 1967.
    dem: "cop30" (Copernicus GLO-30) or "srtm". The bible (editvideo.style) supplies
    sun, sky, haze, view and bit depth unless given; finish=True passes the clip through editvideo.finish.
    sun_from_imagery keeps the sun within sun_tolerance degrees of the light baked into the imagery."""
    from . import blender, imagery
    out = store.DATA / "cache" / "terrain"
    out.mkdir(parents=True, exist_ok=True)
    h = elevation(bbox, width, dem)
    import hashlib
    hp = out / f"{name}-h{width}-{hashlib.sha1(h.tobytes()).hexdigest()[:12]}.npy"  # named by content: a rerun keeps the job's cache key
    if not hp.is_file():
        np.save(hp, h)
    rows, cols = h.shape
    tw, th = cols * 3, rows * 3
    # texel density: the texture should be about as fine as the ground one screen pixel covers at the nearest camera
    # key (Trường Sơn's 3072 px over 351 km, 114 m a texel, was seen at ~24 m a pixel: magnified ~4.8x)
    lat0 = (bbox[1] + bbox[3]) / 2
    ext_m = (bbox[2] - bbox[0]) * 111320 * math.cos(math.radians(lat0))
    sensor = 36.0
    near = []
    for k in camera:
        lx, ly = k.get("look_lon", k["lon"]), k.get("look_lat", k["lat"])
        dx = (lx - k["lon"]) * 111320 * math.cos(math.radians(lat0))
        dy = (ly - k["lat"]) * 111320
        dz = k["alt_m"] - ground_height(h, bbox, lx, ly)
        near.append(math.sqrt(dx * dx + dy * dy + dz * dz) * sensor / lens / 1920)
    screen_mpp = min(near) if near else ext_m / (cols * 3)
    source_mpp = 156543.03 * math.cos(math.radians(lat0)) / 2 ** imagery_zoom  # what the imagery zoom can give at most
    if texture_px:
        k_ = texture_px / max(cols, rows)
        tw, th = int(cols * k_), int(rows * k_)
    else:
        want = int(ext_m / max(screen_mpp, source_mpp))
        if want > tw:
            k_ = min(want / tw, 16384 / max(tw, th))  # the long side, not the width, stays within 16k
            tw, th = int(tw * k_), int(th * k_)
    texel = {"texture_m_per_px": round(ext_m / tw, 1), "screen_m_per_px_nearest": round(screen_mpp, 1),
             "magnification": round(ext_m / tw / max(screen_mpp, .01), 2), "imagery_m_per_px": round(source_mpp, 1)}
    if texel["magnification"] > 2:
        texel["note"] = (f"the texture is seen {texel['magnification']}x magnified at the nearest camera key: lower the texture extent, "
                         f"raise imagery_zoom (now {imagery_zoom}, {source_mpp:.0f} m a pixel) or keep the camera higher")
    tag = "-" + "-".join(f"{a}{b}" for a, b in period_map) if period_map else ""
    if period_raster:  # a georeferenced period image (a KH-9 mosaic) over the ground: the "then" of a then-and-now pair
        import hashlib
        tag += "-r" + hashlib.sha1("|".join(str(Path(r).resolve()) + str(Path(r).stat().st_size) for r in period_raster).encode()).hexdigest()[:10]
    tp = out / f"{name}-{imagery_source}-z{imagery_zoom}-{tw}{tag}.jpg"
    map_credit = ""
    if period_map:
        from . import period_maps as pm
        map_credit = " · Bản đồ: US Army Map Service " + ", ".join(f"{a} {b}" for a, b in period_map) + " (1:50.000, thập niên 1960), qua USGS"
    if not tp.is_file():
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        base = imagery.satellite(bbox, tw, th, imagery_zoom, source=imagery_source)
        if period_map:
            base, _ = pm.drape(bbox, tw, th, [pm.sheet(pm.fetch(a, b)) for a, b in period_map], base=base)
        if period_raster:
            from . import period_maps as pm2
            for r_ in period_raster:
                base, _ = pm2.drape_raster(bbox, tw, th, r_, base=base)
        Image.fromarray(base).save(tp, quality=94)
    cam = []
    for k in camera:
        g = ground_height(h, bbox, k["lon"], k["lat"])
        cam.append({**k, "alt_m": max(k["alt_m"], g + clearance_m)})
    sun_note = None
    if sun_from_imagery:  # keep the 3D sun near the light the satellite photo already carries
        from . import style
        want_sun = {**style.blender_defaults("terrain_shot").get("sun", {}), **(sun or {})}
        baked, r_ = imagery_light(tp, h, bbox)
        turn = _turn(baked, want_sun.get("azimuth", 330))
        if r_ > .12 and abs(turn) > sun_tolerance:  # Điện Biên Phủ: 45 deg off drew every ridge as a dark contour line
            sun = {**want_sun, "azimuth": round((baked + math.copysign(sun_tolerance, turn)) % 360, 1)}
            sun_note = f"sun moved from {want_sun.get('azimuth')} to {sun['azimuth']} deg: the imagery is lit from {baked:.0f} deg (r={r_:.2f})"
    font = font or str(Path(__file__).resolve().parents[1] / "assets" / "fonts" / "bevietnampro" / "BeVietnamPro-SemiBold.ttf")
    params = {"heights": str(hp), "texture": str(tp), "bbox": list(bbox), "exaggeration": exaggeration, "frames": frames, "camera": cam,
              "places": list(places), "routes": list(routes), "lens": lens, "font": font, "engine": engine, "samples": samples,
              "percent": percent, "saturation": 1.0, "value": 1.2, **({"sun": sun} if sun else {}), **({"sky": sky} if sky else {}),
              **({"haze": haze} if haze is not None else {}), **(options or {})}
    if stills:
        params["stills"] = list(stills)
    r = blender.run("terrain_shot", params, files=[hp, tp, font])
    res = {"job": r["job"], "per_frame_s": r.get("per_frame_s"), "cached": r.get("cached"), "texel": texel,
           **({"sun_note": sun_note} if sun_note else {}), **({"settings_failed": r["settings_failed"]} if r.get("settings_failed") else {}),
           "credit": imagery.SOURCES[imagery_source]["credit"] + " · " + DEM_CREDIT[dem] + map_credit,
           "internal_only": imagery.SOURCES[imagery_source]["internal_only"]}
    if (Path(r["job"]) / "tracks.json").is_file():
        res["tracks"] = str(Path(r["job"]) / "tracks.json")
    if stills:
        res["stills"] = [str(Path(r["job"]) / f"still_{f:04d}.png") for f in stills]
    else:
        res["mp4"] = blender.encode(r["job"], finish=finish)
        # the clip carries its inputs' licences into every project that imports it (editvideo.ledger)
        from . import ledger
        parts = [(imagery.SOURCES[imagery_source]["license"], imagery.SOURCES[imagery_source]["credit"]), (DEM_LICENSE[dem], DEM_CREDIT[dem])]
        if period_map:
            parts.append(("Public domain (US Army Map Service, US federal work)", map_credit.strip(" ·")))
        if period_raster:  # KH-9/CORONA scans are US federal (USGS); a georeferenced derivative carries its own licence
            parts.append((raster_license or "unknown (georeferenced period raster: record its licence)", "period raster: " + ", ".join(Path(r).name for r in period_raster)))
        res["license"] = ledger.register_render(res["mp4"], f"Terrain flyover {name} (3D illustration)", parts)["license"]
    return res
