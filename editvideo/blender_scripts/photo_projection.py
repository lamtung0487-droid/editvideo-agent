# Runs inside Blender (bpy + Blender's numpy), started by editvideo.blender.run with params.json beside this file.
# An archive photograph projected on its own geometry (editvideo.archive3d: MoGe-2 points, faces cut where the depth
# jumps), lit by nothing: an emission shader under the Standard view transform shows the photograph's own pixels
# exactly at the original camera. Behind it a plate at the far depth (the photograph with the near objects filled by
# OpenCV, logged by the caller) shows through wherever the moving camera looks behind an edge. The camera moves a
# little along the given keys. Writes frame_####.png (or still_####.png) and done.json.
#
# Coordinates: MoGe's camera space (x right, y down, z forward) becomes Blender's (X = x, Y = z, Z = -y); the original
# camera sits at the origin looking along +Y.
import json, math, sys, time, traceback
from pathlib import Path

import bpy
import numpy as np

JOB = Path(sys.argv[sys.argv.index("--python") + 1]).parent
P = json.loads((JOB / "params.json").read_text(encoding="utf-8"))
T0 = time.time()
report = {}


def emission(name, image_path, extend=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    tex.image.colorspace_settings.name = "sRGB"
    tex.interpolation = "Linear"
    tex.extension = "EXTEND" if extend else "CLIP"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def build():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sc = bpy.context.scene
    d = np.load(P["mesh"])
    V, F, UV = d["verts"].astype(np.float64), d["faces"].astype(np.int64), d["uv"].astype(np.float64)
    me = bpy.data.meshes.new("photo")
    me.from_pydata(V.tolist(), [], F.tolist())
    uv = me.uv_layers.new(name="uv")
    loops = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loops)
    uv.data.foreach_set("uv", UV[loops].ravel())
    me.update()
    ob = bpy.data.objects.new("photo", me)
    sc.collection.objects.link(ob)
    if P.get("check_mask"):  # reveal check: the mesh black, the plate showing where the mesh covered it at frame 0
        blk = bpy.data.materials.new("black")
        blk.use_nodes = True
        nt = blk.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (0, 0, 0, 1)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        me.materials.append(blk)
    else:
        me.materials.append(emission("photo", P["image"]))
    report["faces"] = int(len(F))
    # the plate: the filled photograph on a plane at the far depth, over the original frustum and beyond it
    zp, tx, ty, grow = P["plate_z"], math.tan(P["fov_x"] / 2), math.tan(P["fov_y"] / 2), P.get("plate_grow", 1.35)
    hw, hh = zp * tx * grow, zp * ty * grow
    pm = bpy.data.meshes.new("plate")
    pm.from_pydata([(-hw, zp, -hh), (hw, zp, -hh), (hw, zp, hh), (-hw, zp, hh)], [], [(0, 1, 2, 3)])
    puv = pm.uv_layers.new(name="uv")
    u0, u1 = .5 - grow / 2, .5 + grow / 2
    for li, (u, v) in enumerate(((u0, u0), (u1, u0), (u1, u1), (u0, u1))):
        puv.data[li].uv = (u, v)
    plate = bpy.data.objects.new("plate", pm)
    sc.collection.objects.link(plate)
    pm.materials.append(emission("plate", P.get("check_mask") or P["plate"], extend=True))
    # camera: the original one at the origin, then the keys
    cam_d = bpy.data.cameras.new("cam")
    W, H = P["width"], P["height"]
    if P["fov_x"] / P["fov_y"] >= W / H * .999:  # a panorama: fit the height
        cam_d.sensor_fit = "VERTICAL"
        cam_d.angle_y = P["fov_y"]
    else:
        cam_d.sensor_fit = "HORIZONTAL"
        cam_d.angle_x = P["fov_x"]
    cam_d.clip_start, cam_d.clip_end = max(1e-3, P["near"] * .05), zp * 4
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_mode = "XYZ"
    for k in P["camera"]:
        cam.location = (k.get("x", 0.0), k.get("y", 0.0), k.get("z", 0.0))
        cam.rotation_euler = (math.radians(90 + k.get("pitch", 0.0)), 0.0, math.radians(-k.get("yaw", 0.0)))
        cam.keyframe_insert("location", frame=k["frame"])
        cam.keyframe_insert("rotation_euler", frame=k["frame"])
    if cam.animation_data and cam.animation_data.action:
        for fc in getattr(cam.animation_data.action, "fcurves", []):
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.easing = "EASE_IN_OUT"
    # picture: the photograph's own values, nothing tone-mapped
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = P.get("samples", 16)
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, P.get("percent", 100)
    sc.render.fps = 30
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = str(P.get("color_depth", 16))
    sc.render.use_motion_blur = P.get("shutter", 0) > 0
    if sc.render.use_motion_blur:
        sc.render.motion_blur_shutter = P["shutter"]
    sc.frame_start, sc.frame_end = 0, P["frames"] - 1


def render():
    sc = bpy.context.scene
    frames = P.get("stills") or list(range(P["frames"]))
    t = time.time()
    for f in frames:
        sc.frame_set(f)
        sc.render.filepath = str(JOB / ((f"still_{f:04d}" if P.get("stills") else f"frame_{f:04d}") + ".png"))
        bpy.ops.render.render(write_still=True)
    report["per_frame_s"] = round((time.time() - t) / max(1, len(frames)), 3)


try:
    build()
    render()
    report.update(ok=True, seconds=round(time.time() - T0, 1))
except Exception:
    report.update(error=traceback.format_exc())
(JOB / "done.json").write_text(json.dumps(report), encoding="utf-8")
