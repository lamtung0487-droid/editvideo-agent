"""Expose existing offline 3D templates to MCP clients without arbitrary script execution or hidden downloads."""
import json
import shutil
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .media import sha256


class Render3DRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: Literal["terrain_shot", "globe_shot", "domino_shot", "bloc_map"]
    params: dict
    fps: int = Field(default=30, ge=1, le=30)
    timeout: int = Field(default=1800, ge=60, le=7200)

    @model_validator(mode="after")
    def budget(self):
        p = self.params
        if not isinstance(p.get("frames"), int) or not 1 <= p["frames"] <= 900:
            raise ValueError("params.frames=1..900; compose longer sequences from short cached shots")
        if p.get("engine", "EEVEE") not in ("EEVEE", "CYCLES") or not 1 <= p.get("samples", 32) <= 128 or not 10 <= p.get("percent", 100) <= 100:
            raise ValueError("engine EEVEE|CYCLES, samples1..128, percent10..100")
        stills = p.get("stills") or []
        if len(stills) > 8 or any(not isinstance(f, int) or not 0 <= f < p["frames"] for f in stills):
            raise ValueError("stills: <=8 in-range frames")
        if "out" in p: raise ValueError("Output folder is managed by the task")
        if len(json.dumps(p, allow_nan=False)) > 60000: raise ValueError("Keep params <=60KB")
        if self.template == "domino_shot":  # the camera follows the fall: no keys; the paths and the map are the shot
            paths = p.get("paths") or ([p["path"]] if p.get("path") else [])
            if not paths or len(paths) > 6 or any(not isinstance(q_, list) or len(q_) < 2 or len(q_) > 400 for q_ in paths):
                raise ValueError("domino_shot: paths=[[[lon,lat],...]] (1..6 paths, 2..400 points each)")
            bbox = p.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4 or not bbox[0] < bbox[2] or not bbox[1] < bbox[3]:
                raise ValueError("domino_shot: bbox=[west,south,east,north] of the map image")
            return self
        camera = p.get("camera")
        fields = {"frame", "lat", "lon", "altitude"} if self.template == "globe_shot" else             {"frame", "lat", "lon", "distance"} if self.template == "bloc_map" else {"frame", "lat", "lon", "alt_m", "look_lon", "look_lat"}
        if not isinstance(camera, list) or not camera or len(camera) > 100:
            raise ValueError("camera must contain 1..100 explicit keys")
        previous = -1
        for k in camera:
            if not isinstance(k, dict) or not fields <= k.keys(): raise ValueError(f"camera keys require {sorted(fields)}")
            f = k["frame"]
            if not isinstance(f, int) or not previous < f < p["frames"]: raise ValueError("camera frames must rise inside 0..frames-1")
            previous = f
            if any(not isinstance(k[n], (int, float)) for n in fields - {"frame"}): raise ValueError("camera coordinates must be numbers")
            if not -90 <= k["lat"] <= 90 or not -180 <= k["lon"] <= 180 or k.get("altitude", k.get("alt_m", 0)) <= 0:
                raise ValueError("camera latitude/longitude or positive altitude out of range")
        if p.get("frame_step", 1) != 1: raise ValueError("frame_step must be 1 for exact encoded timing; use stills for sampling")
        if not 16 <= p.get("width", 1920) <= 3840 or not 16 <= p.get("height", 1080) <= 2160:
            raise ValueError("width16..3840, height16..2160")
        if self.template == "terrain_shot":
            bbox = p.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4 or not all(isinstance(x, (int, float)) for x in bbox) or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
                raise ValueError("bbox=[west,south,east,north] requires an increasing local rectangle")
            p.setdefault("sun", {"azimuth": 140, "elevation": 20, "strength": 6.0, "color": "#ffe2bd"})
            p.setdefault("sky", {"horizon": "#d6dfe6", "zenith": "#3f6fa8", "strength": .75})
        return self


def file_fields(template):
    return {"terrain_shot": ("heights", "texture", "font"), "domino_shot": ("map",), "bloc_map": ("shapes",)}.get(template, ("texture", "font"))


def prepare(request, out):
    q = Render3DRequest.model_validate(request)
    body = q.model_dump()
    if not q.params.get("camera"): raise ValueError("Explicit camera keys required; read template contract")
    for name in file_fields(q.template):
        if not q.params.get(name):
            if name == "font": continue
            raise ValueError(f"Local {name} file required; acquire/prepare assets separately")
        p = Path(q.params[name]).resolve(strict=True)
        target = Path(out) / (name + p.suffix)
        from .code_engine import place_file
        place_file(p, target)
        body["params"][name] = str(target)
    return body


def contract():
    from .blender import find
    return {"schema": Render3DRequest.model_json_schema(), "installed": bool(find()),
            "terrain_shot": {"required_params": ["frames", "bbox", "heights (.npy)", "texture (local satellite image)", "camera[{frame,lon,lat,alt_m,look_lon,look_lat}]"],
                             "optional": ["places[{id,lon,lat,label,stem}]", "routes[{points,grow,head,fade,dash_km}]", "exaggeration", "sun", "sky", "haze", "lens", "font",
                                          "mist{density,top_m}", "zones[{lon,lat,radius_km,at,pulse}]", "strikes[{lon,lat,at}]", "labels_2d (tracks.json; blender.label_layers)", "shutter"]},
            "bloc_map": {"required_params": ["frames", "bbox", "shapes (local json {country: [[[lon,lat],...]]})", "camera[{frame,lon,lat,distance,elevation,azimuth}]"],
                         "optional": ["countries{name:{at,frames,rise,color,glow,pulse}}", "flows[{from,to,at,color,beads,lap}]", "islands[{lon,lat}]",
                                      "labels[{id,lon,lat,country}] (tracks.json)", "land", "sea", "lens"]},
            "domino_shot": {"required_params": ["frames", "bbox", "map (local image of bbox)", "paths[[[lon,lat],...]] (a path starting beside another's end is a branch)"],
                            "optional": ["names[{id,label,lon,lat}] (tracks.json)", "tile_height", "spacing", "lean_deg", "lens", "fstop", "camera_start/camera_end{distance,elevation,azimuth,center}"]},
            "globe_shot": {"required_params": ["frames", "texture (local equirectangular image)", "camera[{frame,lat,lon,altitude above unit sphere}]"], "optional": ["places[{id,lat,lon,label}]", "arcs[{start,end,grow:[frame,frame],height}]", "font", "sun", "lens"]},
            "workflow": "Use percent=25 and stills=[...] first. Inspect real pixels, then submit full frames. Cached template rendering, no source code or model download. Poll get_media_task; attach_media_result(video)."}


def process(task_id, request):
    from . import blender, media_tasks
    q = Render3DRequest.model_validate(request)
    out = media_tasks.folder(task_id)
    files = [q.params[k] for k in file_fields(q.template) if q.params.get(k)]
    media_tasks.update(task_id, message="Rendering cached 3D template (use stills for cheap previews)")
    result = blender.run(q.template, q.params, files=files, timeout=q.timeout, cancelled=lambda: media_tasks.cancelled(task_id))
    artifacts = {}
    if q.params.get("stills"):
        for i, frame in enumerate(q.params["stills"]):
            target = out / f"still-{frame}.png"
            shutil.copyfile(Path(result["job"]) / f"still_{frame:04d}.png", target)
            artifacts[f"still_{i}"] = str(target)
    else:
        video = blender.encode(result["job"], q.fps)
        from .code_engine import place_file
        place_file(video, out / "video.mp4")
        artifacts["video"] = str(out / "video.mp4")
    return {"artifacts": artifacts, "cached": result.get("cached"), "job": result["job"],
            "source_sha256": {Path(f).name: sha256(Path(f)) for f in files}, "note": "Authored illustration, not recovered historical camera geometry."}
