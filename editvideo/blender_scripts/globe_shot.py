# Runs inside Blender, started by editvideo.blender.run with params.json beside it. The globe of a diplomatic board:
# NASA Blue Marble mapped by longitude and latitude (computed in the shader, so the seam and the texture's origin never
# drift), a thin glowing atmosphere, a sun that draws the day and night, great-circle arcs that grow, pins and labels of
# one size on screen, a camera keyed in latitude, longitude and altitude (globe radii). Writes frame_####.png, done.json.
import json, math, sys, time, traceback
from pathlib import Path

import bpy
from mathutils import Vector

JOB = Path(sys.argv[sys.argv.index("--python") + 1]).parent
P = json.loads((JOB / "params.json").read_text(encoding="utf-8"))
T0 = time.time()
report = {}


def xyz(lat, lon, r=1.0):
    la, lo = math.radians(lat), math.radians(lon)
    return Vector((r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)))


def hexrgb(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in srgb)


def emission(name, rgb, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n_ in list(nt.nodes):
        nt.nodes.remove(n_)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def slerp(a, b, t):
    om = a.angle(b)
    if om < 1e-6:
        return a.copy()
    return (a * math.sin((1 - t) * om) + b * math.sin(t * om)) / math.sin(om)


try:
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    # --- the earth
    bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, radius=1.0)
    earth = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    mat = bpy.data.materials.new("earth")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    lon = nt.nodes.new("ShaderNodeMath")
    lon.operation = "ARCTAN2"
    u = nt.nodes.new("ShaderNodeMath")
    u.operation = "MULTIPLY_ADD"
    u.inputs[1].default_value, u.inputs[2].default_value = 1 / (2 * math.pi), .5
    lat = nt.nodes.new("ShaderNodeMath")
    lat.operation = "ARCSINE"
    v = nt.nodes.new("ShaderNodeMath")
    v.operation = "MULTIPLY_ADD"
    v.inputs[1].default_value, v.inputs[2].default_value = 1 / math.pi, .5
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(P["texture"])
    img.interpolation = "Cubic"
    nt.links.new(tc.outputs["Object"], nrm.inputs[0])
    nt.links.new(nrm.outputs["Vector"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], lon.inputs[0])
    nt.links.new(sep.outputs["X"], lon.inputs[1])
    nt.links.new(lon.outputs[0], u.inputs[0])
    nt.links.new(sep.outputs["Z"], lat.inputs[0])
    nt.links.new(lat.outputs[0], v.inputs[0])
    nt.links.new(u.outputs[0], comb.inputs["X"])
    nt.links.new(v.outputs[0], comb.inputs["Y"])
    nt.links.new(comb.outputs[0], img.inputs["Vector"])
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = P.get("saturation", .85)
    hsv.inputs["Value"].default_value = P.get("value", 1.1)
    nt.links.new(img.outputs["Color"], hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = .75
    earth.data.materials.append(mat)
    # --- atmosphere: a shell a little larger, glowing at the limb only
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.012)
    atm = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    am = bpy.data.materials.new("atmo")
    am.use_nodes = True
    an = am.node_tree
    for n_ in list(an.nodes):
        an.nodes.remove(n_)
    ao = an.nodes.new("ShaderNodeOutputMaterial")
    lw = an.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = .42
    ramp = an.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .5
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    em = an.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*hexrgb(P.get("atmosphere", "#6aa7ff")), 1)
    em.inputs["Strength"].default_value = P.get("atmosphere_strength", 1.6)
    tr = an.nodes.new("ShaderNodeBsdfTransparent")
    mix = an.nodes.new("ShaderNodeMixShader")
    an.links.new(lw.outputs["Facing"], ramp.inputs["Fac"])
    an.links.new(ramp.outputs["Color"], mix.inputs["Fac"])
    an.links.new(tr.outputs[0], mix.inputs[1])
    an.links.new(em.outputs[0], mix.inputs[2])
    an.links.new(mix.outputs[0], ao.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(am, attr, val)
        except Exception:
            pass
    am.use_backface_culling = True  # only the near limb glows, not the inside of the far shell
    atm.data.materials.append(am)
    atm.visible_shadow = False
    # --- the sun and space
    sd = P.get("sun", {})
    d = xyz(sd.get("lat", 10), sd.get("lon", 60))
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = sd.get("strength", 4.0)
    sun_data.angle = math.radians(2)
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("space")
    sc.world = world
    world.use_nodes = True
    wn = world.node_tree
    bg = wn.nodes["Background"]
    bg.inputs["Color"].default_value = (*hexrgb(P.get("space", "#05070c")), 1)
    bg.inputs["Strength"].default_value = P.get("ambient", .35)
    # --- camera keyed in latitude, longitude, altitude (radii above the surface)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = P.get("lens", 35)
    cam_data.clip_start, cam_data.clip_end = .001, 200
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt = bpy.data.objects.new("look", None)
    sc.collection.objects.link(tgt)
    for k in P["camera"]:
        f = k["frame"] + 1
        cam.location = xyz(k["lat"], k["lon"], 1 + k["altitude"])
        cam.keyframe_insert("location", frame=f)
        tgt.location = xyz(k["lat"], k["lon"], 1.0) * k.get("look", 0.0)
        tgt.keyframe_insert("location", frame=f)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    # --- places: pins standing on the surface, labels facing the camera, one size on screen
    font = bpy.data.fonts.load(P["font"]) if P.get("font") else None
    plate = emission("plate", hexrgb("#0b0e12"), 1.0)
    rigs, where = [], {}
    for k, pl in enumerate(P.get("places", [])):
        pos = xyz(pl["lat"], pl["lon"], 1.0)
        where[pl["id"]] = pos
        rig = bpy.data.objects.new(f"pin{k}", None)
        rig.location = pos
        rig.rotation_mode = "QUATERNION"
        rig.rotation_quaternion = pos.to_track_quat("Z", "Y")
        sc.collection.objects.link(rig)
        rigs.append((rig, pl.get("appear", 0)))
        col = hexrgb(pl.get("color", "#e8b04a"))
        ms = emission(f"stem{k}", col, 2.5)
        bpy.ops.mesh.primitive_cylinder_add(radius=.05, depth=1.4, location=(0, 0, .7))
        st = bpy.context.active_object
        st.data.materials.append(ms)
        st.parent = rig
        bpy.ops.mesh.primitive_uv_sphere_add(radius=.16, location=(0, 0, 1.4))
        hd = bpy.context.active_object
        hd.data.materials.append(ms)
        hd.parent = rig
        if pl.get("label"):
            cu = bpy.data.curves.new(f"lab{k}", "FONT")
            cu.body = pl["label"]
            if font:
                cu.font = font
            cu.size = 1.0
            cu.align_x, cu.align_y = "CENTER", "BOTTOM"
            txt = bpy.data.objects.new(f"lab{k}", cu)
            sc.collection.objects.link(txt)
            txt.parent = rig
            txt.location = (0, 0, 1.7)
            txt.data.materials.append(emission(f"ink{k}", hexrgb("#f4ead8"), 1.6))
            c2 = txt.constraints.new("TRACK_TO")
            c2.target, c2.track_axis, c2.up_axis = cam, "TRACK_Z", "UP_Y"
            bpy.context.view_layer.update()
            dw, dh = txt.dimensions.x, txt.dimensions.y
            bpy.ops.mesh.primitive_plane_add(size=1, location=(0, dh / 2 - .05, -.02))
            pb = bpy.context.active_object
            pb.scale = (dw + .5, dh + .35, 1)
            pb.data.materials.append(plate)
            pb.parent = txt
    # --- arcs: great circles lifted by `height` at their middle, growing over their frames
    for k, a in enumerate(P.get("arcs", [])):
        A, B = where[a["start"]], where[a["end"]]
        cd = bpy.data.curves.new(f"arc{k}", "CURVE")
        cd.dimensions = "3D"
        spl = cd.splines.new("POLY")
        n = 96
        spl.points.add(n)
        for i in range(n + 1):
            t = i / n
            pt = slerp(A, B, t).normalized() * (1.003 + a.get("height", .18) * math.sin(math.pi * t))
            spl.points[i].co = (*pt, 1)
        cd.bevel_depth = a.get("radius", .0045)
        cd.bevel_resolution = 3
        ob = bpy.data.objects.new(f"arc{k}", cd)
        sc.collection.objects.link(ob)
        ob.data.materials.append(emission(f"arcm{k}", hexrgb(a.get("color", "#e8b04a")), 4.0))
        ob.visible_shadow = False
        cd.bevel_factor_mapping_end = "SPLINE"
        cd.bevel_factor_end = 0.0
        cd.keyframe_insert("bevel_factor_end", frame=a["grow"][0] + 1)
        cd.bevel_factor_end = 1.0
        cd.keyframe_insert("bevel_factor_end", frame=a["grow"][1] + 1)
    for o in sc.collection.objects:
        if o.name.startswith(("Cylinder", "Sphere.", "lab", "Plane", "pin")):
            o.visible_shadow = False
    try:
        blockers = bpy.data.collections.new("sun_blockers")
        blockers.objects.link(earth)
        sun.light_linking.blocker_collection = blockers
    except Exception:
        pass
    # pins keep one size on screen and appear at their frame
    W_, H_ = P.get("width", 1920), P.get("height", 1080)
    vfov = 2 * math.atan(math.tan(2 * math.atan(cam_data.sensor_width / 2 / cam_data.lens) / 2) * H_ / W_)
    share = P.get("label_screen", .032)
    for f in list(range(1, P["frames"] + 1, 4)) + [P["frames"]]:
        sc.frame_set(f)
        cpos = cam.matrix_world.translation
        for rig, ap in rigs:
            dd = (cpos - rig.location).length
            facing = rig.location.normalized().dot((cpos - rig.location).normalized())  # a place behind the limb hides
            seen = max(0.0, min(1.0, (facing - .05) / .15))
            sz = max(1e-4, 2 * dd * math.tan(vfov / 2) * share) * (0.0 if f < ap + 1 else min(1.0, (f - ap) / 8)) * seen
            rig.scale = (max(sz, 1e-5),) * 3
            rig.keyframe_insert("scale", frame=f)
    # --- render
    engines = [e_.identifier for e_ in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "CYCLES" if P.get("engine") == "CYCLES" else next(x for x in engines if "EEVEE" in x)
    if sc.render.engine == "CYCLES":
        sc.cycles.samples = P.get("samples", 32)
        sc.cycles.use_denoising = True
    try:
        sc.eevee.taa_render_samples = P.get("samples", 32)
    except Exception:
        pass
    sc.render.use_motion_blur = True
    sc.render.resolution_x, sc.render.resolution_y = W_, H_
    sc.render.resolution_percentage = P.get("percent", 100)
    try:
        sc.view_settings.view_transform = P.get("view", "AgX")  # map colours: "Khronos PBR Neutral" keeps the hues the bible set
        sc.view_settings.look = P.get("look", "AgX - Medium High Contrast") if sc.view_settings.view_transform == "AgX" else P.get("look", "None")
    except Exception:
        pass
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = str(P.get("color_depth", "8"))  # 16: no banding in sky, mist and dark seas
    sc.frame_start, sc.frame_end = 1, P["frames"]
    sc.render.fps = 30
    sc.render.filepath = str(JOB / "frame_")
    t1 = time.time()
    if P.get("stills"):
        for f in P["stills"]:
            sc.frame_set(f + 1)
            sc.render.filepath = str(JOB / f"still_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
        report["frames"] = len(P["stills"])
    else:
        bpy.ops.render.render(animation=True)
        report["frames"] = P["frames"]
    report.update(engine=sc.render.engine, setup_s=round(t1 - T0, 1), render_s=round(time.time() - t1, 1),
                  per_frame_s=round((time.time() - t1) / max(1, report["frames"]), 2))
except Exception:
    report["error"] = traceback.format_exc()
(JOB / "done.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
