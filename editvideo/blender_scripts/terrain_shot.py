# Runs inside Blender (bpy + Blender's numpy), started by editvideo.blender.run with params.json beside this file.
# A terrain shot: the real heights as a mesh (exact, no displacement), satellite imagery on it, a sun from the given
# azimuth and elevation, a gradient sky, aerial haze as a thin volume, mist lying in the valleys, glowing zones draped on
# the ground, strikes, pins, routes that grow along the ground (dashed or fading, with a bright head), depth of field, and a
# camera keyed in longitude, latitude and metres. Labels are drawn by the film, not here: with labels_2d the screen position
# of every place, each frame, and whether a ridge hides it, goes to tracks.json. Writes frame_####.png and done.json.
import json, math, sys, time, traceback
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

JOB = Path(sys.argv[sys.argv.index("--python") + 1]).parent
P = json.loads((JOB / "params.json").read_text(encoding="utf-8"))
T0 = time.time()
report = {}


def km_xy(lon, lat):
    w, s, e, n = P["bbox"]
    lon_c, lat_c = (w + e) / 2, (s + n) / 2
    return (lon - lon_c) * 111.32 * math.cos(math.radians(lat_c)), (lat - lat_c) * 110.57


def ground(lon, lat):
    """Height in scene units (km, exaggerated) under a point, bilinear on the height grid."""
    w, s, e, n = P["bbox"]
    rows, cols = H.shape
    c = (lon - w) / (e - w) * (cols - 1)
    r = (n - lat) / (n - s) * (rows - 1)
    c0, r0 = int(max(0, min(cols - 2, math.floor(c)))), int(max(0, min(rows - 2, math.floor(r))))
    fc, fr = c - c0, r - r0
    h = (H[r0, c0] * (1 - fc) * (1 - fr) + H[r0, c0 + 1] * fc * (1 - fr) + H[r0 + 1, c0] * (1 - fc) * fr + H[r0 + 1, c0 + 1] * fc * fr)
    return float(h) / 1000 * P.get("exaggeration", 1.0)


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


def hexrgb(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in srgb)  # linear for Blender


try:
    sc = bpy.context.scene
    try:  # drifts (clouds, mist) are linear: Blender 5 removed action.fcurves, so set it before any key is made
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except Exception:
        pass
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    H = np.load(P["heights"]).astype(np.float32)
    rows, cols = H.shape
    w, s, e, n = P["bbox"]
    x0, y1 = km_xy(w, n)
    x1, y0 = km_xy(e, s)
    ex = P.get("exaggeration", 1.0)
    # --- terrain mesh: one vertex per height sample, written straight from numpy
    xs = np.linspace(x0, x1, cols, dtype=np.float32)
    ys = np.linspace(y1, y0, rows, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    Z = H / 1000 * ex
    verts = np.stack([X, Y, Z], -1).reshape(-1, 3)
    r_, c_ = np.meshgrid(np.arange(rows - 1), np.arange(cols - 1), indexing="ij")
    v0 = (r_ * cols + c_).ravel()
    quads = np.stack([v0, v0 + cols, v0 + cols + 1, v0 + 1], -1).astype(np.int32)
    me = bpy.data.meshes.new("terrain")
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    try:
        me.polygons.foreach_set("loop_total", np.full(len(quads), 4, np.int32))
    except Exception:
        pass
    uvl = me.uv_layers.new(name="uv")
    vi = quads.ravel()
    uv = np.stack([(vi % cols) / (cols - 1), 1 - (vi // cols) / (rows - 1)], -1).astype(np.float32)
    uvl.data.foreach_set("uv", uv.ravel())
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    me.update()
    terrain = bpy.data.objects.new("terrain", me)
    sc.collection.objects.link(terrain)
    mat = bpy.data.materials.new("ground")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(P["texture"])
    img.extension = "EXTEND"
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = P.get("saturation", .9)
    hsv.inputs["Value"].default_value = P.get("value", 1.05)
    nt.links.new(img.outputs["Color"], hsv.inputs["Color"])
    base = hsv.outputs["Color"]
    cl = P.get("clouds", {"shadow": .28, "cell_km": 9.0, "drift_km": [3.0, 1.2]})
    if cl and cl.get("shadow", 0) > 0:
        # cloud shadows drifting over the ground (computed in the shader, no render cost): large soft patches darken
        # the albedo, the cheapest cue of a living landscape under a real sky
        cg = nt.nodes.new("ShaderNodeNewGeometry")
        cmap = nt.nodes.new("ShaderNodeMapping")
        cnoise = nt.nodes.new("ShaderNodeTexNoise")
        cnoise.inputs["Scale"].default_value = 1.0 / cl.get("cell_km", 9.0)
        cnoise.inputs["Detail"].default_value = 3.0
        cnoise.inputs["Roughness"].default_value = .5
        nt.links.new(cg.outputs["Position"], cmap.inputs["Vector"])
        nt.links.new(cmap.outputs["Vector"], cnoise.inputs["Vector"])
        dk = cl.get("drift_km", [3.0, 1.2])
        cmap.inputs["Location"].default_value = (0, 0, 0)
        cmap.inputs["Location"].keyframe_insert("default_value", frame=1)
        cmap.inputs["Location"].default_value = (dk[0], dk[1], 0)
        cmap.inputs["Location"].keyframe_insert("default_value", frame=P["frames"])
        try:
            for fc in mat.node_tree.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
        except Exception:
            pass
        cramp = nt.nodes.new("ShaderNodeMapRange")
        cramp.inputs["From Min"].default_value, cramp.inputs["From Max"].default_value = .5, .66
        cramp.inputs["To Min"].default_value, cramp.inputs["To Max"].default_value = 1.0, 1.0 - cl["shadow"]
        nt.links.new(cnoise.outputs["Fac"], cramp.inputs["Value"])
        shade = nt.nodes.new("ShaderNodeVectorMath")
        shade.operation = "SCALE"
        nt.links.new(base, shade.inputs[0])
        nt.links.new(cramp.outputs["Result"], shade.inputs["Scale"])
        base = shade.outputs["Vector"]
    nt.links.new(base, bsdf.inputs["Base Color"])
    # roughness by brightness: dark forest and water a little glossier at grazing light than bare bright ground
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["From Min"].default_value, rr.inputs["From Max"].default_value = .02, .35
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = P.get("roughness_dark", .78), .95
    nt.links.new(img.outputs["Color"], bw.inputs["Color"])
    nt.links.new(bw.outputs["Val"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], bsdf.inputs["Roughness"])
    for k in ("Specular IOR Level", "Specular"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = .15
            break
    me.materials.append(mat)
    zones = P.get("zones") or []
    if zones:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        flat = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(geo.outputs["Position"], sep.inputs[0])
        nt.links.new(sep.outputs[0], flat.inputs[0])
        nt.links.new(sep.outputs[1], flat.inputs[1])
        glow = None
        for k, zn in enumerate(zones):
            cx, cy = km_xy(zn["lon"], zn["lat"])
            dist = nt.nodes.new("ShaderNodeVectorMath")
            dist.operation = "DISTANCE"
            dist.inputs[1].default_value = (cx, cy, 0)
            nt.links.new(flat.outputs[0], dist.inputs[0])
            fall = nt.nodes.new("ShaderNodeMapRange")
            r = zn.get("radius_km", 2.0)
            fall.inputs["From Min"].default_value = r * zn.get("core", .3)
            fall.inputs["From Max"].default_value = r
            fall.inputs["To Min"].default_value, fall.inputs["To Max"].default_value = 1.0, 0.0
            nt.links.new(dist.outputs["Value"], fall.inputs["Value"])
            amp = nt.nodes.new("ShaderNodeValue")
            a0, n0 = zn.get("at", 0) + 1, zn.get("frames", 24)
            amp.outputs[0].default_value = 0.0
            amp.outputs[0].keyframe_insert("default_value", frame=a0)
            amp.outputs[0].default_value = 1.0
            amp.outputs[0].keyframe_insert("default_value", frame=a0 + n0)
            for j, f in enumerate(range(a0 + n0 + 15, P["frames"] + 1, 15) if zn.get("pulse") else []):
                amp.outputs[0].default_value = .62 if j % 2 == 0 else 1.0
                amp.outputs[0].keyframe_insert("default_value", frame=f)
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            nt.links.new(fall.outputs["Result"], mul.inputs[0])
            nt.links.new(amp.outputs[0], mul.inputs[1])
            tint = nt.nodes.new("ShaderNodeVectorMath")
            tint.operation = "SCALE"
            tint.inputs[0].default_value = hexrgb(zn.get("color", "#ff5a3c"))
            nt.links.new(mul.outputs[0], tint.inputs["Scale"])
            if glow is None:
                glow = tint.outputs["Vector"]
            else:
                add = nt.nodes.new("ShaderNodeVectorMath")
                add.operation = "ADD"
                nt.links.new(glow, add.inputs[0])
                nt.links.new(tint.outputs["Vector"], add.inputs[1])
                glow = add.outputs["Vector"]
        lit = nt.nodes.new("ShaderNodeVectorMath")
        lit.operation = "MULTIPLY"
        nt.links.new(glow, lit.inputs[0])
        nt.links.new(hsv.outputs["Color"], lit.inputs[1])
        nt.links.new(lit.outputs["Vector"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = P.get("zone_strength", 3.0)
    # --- aerial perspective in the ground's own shader: distance from the camera fades the ground toward the horizon's
    # colour (a compositor mix on the mist pass painted far ridges black in Blender 5.2); the sky stays as drawn
    aerial = P.get("aerial", {"strength": .32, "curve": 1.6})
    if aerial and aerial.get("strength", 0) > 0:
        span_ = max(x1 - x0, y1 - y0)
        start_ = aerial.get("start_km", span_ * .08)
        cdat = nt.nodes.new("ShaderNodeCameraData")
        ar = nt.nodes.new("ShaderNodeMapRange")
        ar.inputs["From Min"].default_value, ar.inputs["From Max"].default_value = start_, start_ + aerial.get("depth_km", span_ * .9)
        nt.links.new(cdat.outputs["View Distance"], ar.inputs["Value"])
        apw = nt.nodes.new("ShaderNodeMath")
        apw.operation = "POWER"
        apw.inputs[1].default_value = aerial.get("curve", 1.6)
        nt.links.new(ar.outputs["Result"], apw.inputs[0])
        afac = nt.nodes.new("ShaderNodeMath")
        afac.operation = "MULTIPLY"
        afac.use_clamp = True
        afac.inputs[1].default_value = aerial["strength"]
        nt.links.new(apw.outputs[0], afac.inputs[0])
        hcol = hexrgb(aerial.get("color", P["sky"].get("horizon", (P.get("haze") or {}).get("color", "#cdd6de"))))
        aem = nt.nodes.new("ShaderNodeEmission")
        aem.inputs["Color"].default_value = (*hcol, 1)
        aem.inputs["Strength"].default_value = aerial.get("emit", 1.0)
        amix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(afac.outputs[0], amix.inputs["Fac"])
        nt.links.new(bsdf.outputs["BSDF"], amix.inputs[1])
        nt.links.new(aem.outputs["Emission"], amix.inputs[2])
        surface = amix.outputs["Shader"]
        if zones:  # a zone is the story, not the landscape: its glow is added after the haze (it faded at 18 s)
            for lk in list(nt.links):
                if lk.to_socket == bsdf.inputs["Emission Color"]:
                    src = lk.from_socket
                    nt.links.remove(lk)
                    bsdf.inputs["Emission Strength"].default_value = 0.0  # unlinked, its colour is white: the whole ground glowed
                    zem = nt.nodes.new("ShaderNodeEmission")
                    nt.links.new(src, zem.inputs["Color"])
                    zem.inputs["Strength"].default_value = P.get("zone_strength", 3.0)
                    add = nt.nodes.new("ShaderNodeAddShader")
                    nt.links.new(surface, add.inputs[0])
                    nt.links.new(zem.outputs["Emission"], add.inputs[1])
                    surface = add.outputs["Shader"]
                    break
        nt.links.new(surface, nt.nodes["Material Output"].inputs["Surface"])
        report["aerial"] = "shader"
    # --- sun and sky
    az, el = math.radians(P["sun"]["azimuth"]), math.radians(P["sun"]["elevation"])
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = P["sun"].get("strength", 4.0)
    sun_data.angle = math.radians(P["sun"].get("angle", 1.5))
    sun_data.color = hexrgb(P["sun"].get("color", "#fff1dc"))
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    sc.collection.objects.link(sun)
    fill_w = P.get("fill", .55)
    if fill_w > 0:
        fd = bpy.data.lights.new("fill", "SUN")
        fd.energy = fill_w
        fd.angle = math.radians(40)
        fd.color = hexrgb(P.get("shadow_tint", "#5a6a80"))
        try:
            fd.use_shadow = False
        except Exception:
            pass
        fo_ = bpy.data.objects.new("fill", fd)
        fo_.rotation_mode = "QUATERNION"
        back = Vector((-d.x, -d.y, max(.35, d.z * 2)))
        fo_.rotation_quaternion = (-back.normalized()).to_track_quat("-Z", "Y")
        sc.collection.objects.link(fo_)
    world = bpy.data.worlds.new("sky")
    sc.world = world
    world.use_nodes = True
    wn = world.node_tree
    bg = wn.nodes["Background"]
    sky_model = P["sky"].get("model", "physical")
    if sky_model == "physical":
        st_ = wn.nodes.new("ShaderNodeTexSky")
        try:
            st_.sky_type = "MULTIPLE_SCATTERING"
        except Exception:
            st_.sky_type = "NISHITA"
        st_.sun_elevation = el
        st_.sun_rotation = az  # measured: rotation 0 puts the sun at +Y (north), +90 deg at +X (east), as `d` below
        st_.sun_disc = False  # the sun lamp lights; a disc would burn a spot into wide shots
        for k_, v_ in (("altitude", max(100.0, min(60000.0, min(c_["alt_m"] for c_ in P["camera"]) * .5))), ("air_density", P["sky"].get("air", 1.0)),
                       ("aerosol_density", P["sky"].get("dust", 1.4))):  # a little haze: tropical air is never alpine-clear
            try:
                setattr(st_, k_, v_)
            except Exception as e_:  # the Nishita fallback names its dust differently
                report.setdefault("settings_failed", []).append(f"sky.{k_}: {type(e_).__name__}")
        # below the horizon the physical sky is black ground: where the camera saw past the terrain's edge it showed a
        # dark hole, so a direction below the horizon reads the sky mirrored across it (a continuous haze)
        tcw = wn.nodes.new("ShaderNodeTexCoord")
        sepw = wn.nodes.new("ShaderNodeSeparateXYZ")
        absz = wn.nodes.new("ShaderNodeMath")
        absz.operation = "ABSOLUTE"
        comb = wn.nodes.new("ShaderNodeCombineXYZ")
        wn.links.new(tcw.outputs["Generated"], sepw.inputs[0])
        wn.links.new(sepw.outputs["Z"], absz.inputs[0])
        for i_ in (0, 1):
            wn.links.new(sepw.outputs[i_], comb.inputs[i_])
        wn.links.new(absz.outputs[0], comb.inputs[2])
        wn.links.new(comb.outputs["Vector"], st_.inputs["Vector"])
        wn.links.new(st_.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = P["sky"].get("physical_strength", .08)  # .22 washed a low warm sun out in blue fill
    tc = wn.nodes.new("ShaderNodeTexCoord")
    sep = wn.nodes.new("ShaderNodeSeparateXYZ")
    rng = wn.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = -.05, .32
    ramp = wn.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*hexrgb(P["sky"]["horizon"]), 1)
    ramp.color_ramp.elements[1].color = (*hexrgb(P["sky"]["zenith"]), 1)
    wn.links.new(tc.outputs["Generated"], sep.inputs[0])
    wn.links.new(sep.outputs["Z"], rng.inputs["Value"])
    wn.links.new(rng.outputs["Result"], ramp.inputs["Fac"])
    if sky_model != "physical":
        wn.links.new(ramp.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = P["sky"].get("strength", 1.0)
    # --- aerial haze: a thin scattering volume over the whole box (the far ridges fade toward the sky colour)
    hz = P.get("haze") or {}
    if hz.get("density", 0) > 0 and not (aerial and aerial.get("strength", 0) > 0 and not hz.get("volume")):
        bpy.ops.mesh.primitive_cube_add(size=1)
        box = bpy.context.active_object
        box.name = "haze"
        span = max(x1 - x0, y1 - y0) * 3
        top = max([hz.get("top_km", 6.0)] + [k_["alt_m"] / 1000 * ex + 2 for k_ in P["camera"]])
        box.scale = (span, span, top * 2)
        box.location = (0, 0, 0)
        vm = bpy.data.materials.new("haze")
        vm.use_nodes = True
        vn = vm.node_tree
        for n_ in list(vn.nodes):
            vn.nodes.remove(n_)
        vo = vn.nodes.new("ShaderNodeOutputMaterial")
        pv = vn.nodes.new("ShaderNodeVolumePrincipled")
        pv.inputs["Density"].default_value = hz["density"]
        pv.inputs["Color"].default_value = (*hexrgb(hz.get("color", "#c9d3dc")), 1)
        pv.inputs["Anisotropy"].default_value = hz.get("anisotropy", .35)
        vn.links.new(pv.outputs["Volume"], vo.inputs["Volume"])
        box.data.materials.append(vm)
    mi = P.get("mist") or {}
    if mi.get("density", 0) > 0:
        zb = float(Z.min()) - .02
        zt = mi.get("top_m", 900) / 1000 * ex
        bpy.ops.mesh.primitive_cube_add(size=1)
        mbox = bpy.context.active_object
        mbox.name = "mist"
        mbox.scale = (x1 - x0, y1 - y0, zt - zb)
        mbox.location = ((x0 + x1) / 2, (y0 + y1) / 2, (zt + zb) / 2)
        mm = bpy.data.materials.new("mist")
        mm.use_nodes = True
        mn = mm.node_tree
        for n_ in list(mn.nodes):
            mn.nodes.remove(n_)
        mo = mn.nodes.new("ShaderNodeOutputMaterial")
        pv = mn.nodes.new("ShaderNodeVolumePrincipled")
        pv.inputs["Color"].default_value = (*hexrgb(mi.get("color", "#e4e8ea")), 1)
        pv.inputs["Anisotropy"].default_value = mi.get("anisotropy", .5)
        g_ = mn.nodes.new("ShaderNodeNewGeometry")
        mp = mn.nodes.new("ShaderNodeMapping")
        nt_ = mn.nodes.new("ShaderNodeTexNoise")
        nt_.inputs["Scale"].default_value = 1.0 / mi.get("cell_km", 1.6)
        nt_.inputs["Detail"].default_value = 5.0
        nt_.inputs["Roughness"].default_value = .55
        mn.links.new(g_.outputs["Position"], mp.inputs["Vector"])
        mn.links.new(mp.outputs["Vector"], nt_.inputs["Vector"])
        drift = mi.get("drift_km", [.6, .2])  # over the whole shot
        mp.inputs["Location"].default_value = (0, 0, 0)
        mp.inputs["Location"].keyframe_insert("default_value", frame=1)
        mp.inputs["Location"].default_value = (drift[0], drift[1], 0)
        mp.inputs["Location"].keyframe_insert("default_value", frame=P["frames"])
        try:
            for fc in mm.node_tree.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
        except Exception:
            pass
        cr = mn.nodes.new("ShaderNodeValToRGB")
        cr.color_ramp.elements[0].position, cr.color_ramp.elements[1].position = mi.get("gaps", .46), mi.get("solid", .72)
        mn.links.new(nt_.outputs["Fac"], cr.inputs["Fac"])
        sz = mn.nodes.new("ShaderNodeSeparateXYZ")
        mn.links.new(g_.outputs["Position"], sz.inputs[0])
        hf = mn.nodes.new("ShaderNodeMapRange")
        hf.inputs["From Min"].default_value, hf.inputs["From Max"].default_value = zb, zt
        hf.inputs["To Min"].default_value, hf.inputs["To Max"].default_value = 1.0, 0.0
        mn.links.new(sz.outputs[2], hf.inputs["Value"])
        pw = mn.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = mi.get("falloff", 1.6)
        mn.links.new(hf.outputs["Result"], pw.inputs[0])
        m1 = mn.nodes.new("ShaderNodeMath")
        m1.operation = "MULTIPLY"
        mn.links.new(cr.outputs["Color"], m1.inputs[0])
        mn.links.new(pw.outputs[0], m1.inputs[1])
        m2 = mn.nodes.new("ShaderNodeMath")
        m2.operation = "MULTIPLY"
        m2.inputs[1].default_value = mi["density"]
        mn.links.new(m1.outputs[0], m2.inputs[0])
        mn.links.new(m2.outputs[0], pv.inputs["Density"])
        mn.links.new(pv.outputs["Volume"], mo.inputs["Volume"])
        mbox.data.materials.append(mm)
    # --- pins with labels
    font = bpy.data.fonts.load(P["font"]) if P.get("font") else None
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = P.get("lens", 30)
    cam_data.clip_start, cam_data.clip_end = .01, 400
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    plate = emission("plate", hexrgb("#0b0e12"), 1.0)
    rigs = []
    for k, pl in enumerate(P.get("places", [])):  # a pin in "pin units": the rig's scale makes one unit a share of the frame
        x, y = km_xy(pl["lon"], pl["lat"])
        z = ground(pl["lon"], pl["lat"])
        rig = bpy.data.objects.new(f"pin{k}", None)
        rig.location = (x, y, z)
        sc.collection.objects.link(rig)
        rigs.append(rig)
        col = hexrgb(pl.get("color", "#e8b04a"))
        mstem = emission(f"stem{k}", col, 2.0)
        if pl.get("stem", True) is False:
            continue
        bpy.ops.mesh.primitive_cylinder_add(radius=.045, depth=1.6, location=(0, 0, .8))
        stem = bpy.context.active_object
        stem.data.materials.append(mstem)
        stem.parent = rig
        bpy.ops.mesh.primitive_uv_sphere_add(radius=.13, location=(0, 0, 1.6))
        head = bpy.context.active_object
        head.data.materials.append(mstem)
        head.parent = rig
        if pl.get("label") and not P.get("labels_2d"):
            cu = bpy.data.curves.new(f"lab{k}", "FONT")
            cu.body = pl["label"]
            if font:
                cu.font = font
            cu.size = 1.0
            cu.align_x, cu.align_y = "CENTER", "BOTTOM"
            txt = bpy.data.objects.new(f"lab{k}", cu)
            sc.collection.objects.link(txt)
            txt.parent = rig
            txt.location = (0, 0, 1.85)
            txt.data.materials.append(emission(f"ink{k}", hexrgb(pl.get("ink", "#f4ead8")), 1.6))
            con = txt.constraints.new("TRACK_TO")
            con.target, con.track_axis, con.up_axis = cam, "TRACK_Z", "UP_Y"
            bpy.context.view_layer.update()
            dw, dh = txt.dimensions.x / max(1e-6, txt.matrix_world.to_scale().x), txt.dimensions.y / max(1e-6, txt.matrix_world.to_scale().y)
            bpy.ops.mesh.primitive_plane_add(size=1, location=(0, dh / 2 - .05, -.02))
            pb = bpy.context.active_object
            pb.scale = (dw + .5, dh + .35, 1)
            pb.data.materials.append(plate)
            pb.parent = txt
    for o in sc.collection.objects:  # pins, labels and their plates light the map but cast no shadow on it
        if o.name.startswith(("Cylinder", "Sphere", "lab", "Plane", "pin")):
            o.visible_shadow = False
            for slot in o.material_slots:
                if slot.material and hasattr(slot.material, "shadow_method"):
                    slot.material.shadow_method = "NONE"
    try:  # light linking: under the sun only the ground casts shadows (EEVEE and Cycles, Blender 4+)
        blockers = bpy.data.collections.new("sun_blockers")
        blockers.objects.link(terrain)
        sun.light_linking.blocker_collection = blockers
    except Exception:
        pass
    # --- routes grow along the ground
    for k, rt in enumerate(P.get("routes", [])):
        cd = bpy.data.curves.new(f"route{k}", "CURVE")
        cd.dimensions = "3D"
        sp = cd.splines.new("POLY")
        dense = []  # resampled about every 300 m so the line follows the ground instead of cutting through ridges
        for (lo0, la0), (lo1, la1) in zip(rt["points"], rt["points"][1:]):
            xa, ya = km_xy(lo0, la0)
            xb, yb = km_xy(lo1, la1)
            n_ = max(1, int(math.hypot(xb - xa, yb - ya) / rt.get("step_km", .3)))
            dense += [(lo0 + (lo1 - lo0) * u / n_, la0 + (la1 - la0) * u / n_) for u in range(n_)]
        dense.append(tuple(rt["points"][-1]))
        runs = [dense]
        if rt.get("dash_km"):  # alternate drawn and empty stretches, each its own spline
            on, off = rt["dash_km"]
            per = max(1, int(round(on / rt.get("step_km", .3)))), max(1, int(round(off / rt.get("step_km", .3))))
            runs, i = [], 0
            while i < len(dense) - 1:
                runs.append(dense[i:i + per[0] + 1])
                i += per[0] + per[1]
            cd.splines.remove(sp)
        for j, run in enumerate(runs):
            sp_ = sp if not rt.get("dash_km") else cd.splines.new("POLY")
            sp_.points.add(len(run) - 1)
            for i, (lo, la) in enumerate(run):
                x, y = km_xy(lo, la)
                sp_.points[i].co = (x, y, ground(lo, la) + rt.get("lift_km", .03), 1)
        cd.bevel_depth = rt.get("width_km", .035)
        cd.bevel_resolution = 3
        cd.use_fill_caps = True
        ob = bpy.data.objects.new(f"route{k}", cd)
        sc.collection.objects.link(ob)
        rmat = emission(f"routem{k}", hexrgb(rt.get("color", "#e8b04a")), rt.get("glow", 3.0))
        ob.data.materials.append(rmat)
        ob.visible_shadow = False
        for f, v in rt.get("glow_keys", []):  # [[frame, strength], ...]: flare a line
            em_ = rmat.node_tree.nodes["Emission"]
            em_.inputs["Strength"].default_value = v
            em_.inputs["Strength"].keyframe_insert("default_value", frame=f + 1)
        if rt.get("fade"):  # [first, last]: the line dissolves to nothing (emission at strength 0 would draw it black)
            rn = rmat.node_tree
            tb = rn.nodes.new("ShaderNodeBsdfTransparent")
            mx = rn.nodes.new("ShaderNodeMixShader")
            rn.links.new(tb.outputs[0], mx.inputs[1])
            rn.links.new(rn.nodes["Emission"].outputs[0], mx.inputs[2])
            rn.links.new(mx.outputs[0], rn.nodes["Material Output"].inputs["Surface"])
            try:
                rmat.surface_render_method = "BLENDED"
            except Exception:
                pass
            mx.inputs["Fac"].default_value = 1.0
            mx.inputs["Fac"].keyframe_insert("default_value", frame=rt["fade"][0] + 1)
            mx.inputs["Fac"].default_value = 0.0
            mx.inputs["Fac"].keyframe_insert("default_value", frame=rt["fade"][1] + 1)
            ob.hide_render = False
            ob.keyframe_insert("hide_render", frame=1)
            ob.hide_render = True
            ob.keyframe_insert("hide_render", frame=rt["fade"][1] + 2)
        if rt.get("head") and rt.get("grow") and not rt.get("dash_km"):
            cd.use_path = True
            bpy.ops.mesh.primitive_uv_sphere_add(radius=rt.get("width_km", .035) * 2.6)
            hd = bpy.context.active_object
            hd.name = f"head{k}"
            hd.data.materials.append(emission(f"headm{k}", hexrgb(rt.get("head_color", "#fff3d6")), rt.get("glow", 3.0) * 3))
            hd.visible_shadow = False
            fp = hd.constraints.new("FOLLOW_PATH")
            fp.target, fp.use_fixed_location = ob, True
            fp.offset_factor = 0.0
            fp.keyframe_insert("offset_factor", frame=rt["grow"][0] + 1)
            fp.offset_factor = 1.0
            fp.keyframe_insert("offset_factor", frame=rt["grow"][1] + 1)
            hd.hide_render = True
            hd.keyframe_insert("hide_render", frame=1)
            hd.hide_render = False
            hd.keyframe_insert("hide_render", frame=rt["grow"][0] + 1)
        if rt.get("grow"):
            cd.bevel_factor_mapping_end = "SPLINE"
            cd.bevel_factor_end = 0.0
            cd.keyframe_insert("bevel_factor_end", frame=rt["grow"][0] + 1)
            cd.bevel_factor_end = 1.0
            cd.keyframe_insert("bevel_factor_end", frame=rt["grow"][1] + 1)
    for k, st in enumerate(P.get("strikes", [])):
        x, y = km_xy(st["lon"], st["lat"])
        z = ground(st["lon"], st["lat"])
        bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=.06, location=(x, y, z + st.get("lift_km", .25)))
        ring = bpy.context.active_object
        ring.name = f"strike{k}"
        smat = emission(f"strikem{k}", hexrgb(st.get("color", "#ff4b2b")), 0.0)
        ring.data.materials.append(smat)
        ring.visible_shadow = False
        a0, n0, r = st["at"] + 1, st.get("frames", 36), st.get("radius_km", 1.5)
        em_ = smat.node_tree.nodes["Emission"]
        for f, sc_, v in ((a0 - 1, .02, 0.0), (a0, .05, 12.0), (a0 + n0 // 3, r * .7, 6.0), (a0 + n0, r, 0.0)):
            ring.scale = (sc_, sc_, max(.3, sc_ * .5))
            ring.keyframe_insert("scale", frame=max(1, f))
            em_.inputs["Strength"].default_value = v
            em_.inputs["Strength"].keyframe_insert("default_value", frame=max(1, f))
        for f, hid in ((1, True), (max(1, a0 - 1), False), (a0 + n0 + 1, True)):  # only while it burns
            ring.hide_render = hid
            ring.keyframe_insert("hide_render", frame=f)
        ld = bpy.data.lights.new(f"flash{k}", "POINT")
        ld.color = hexrgb(st.get("color", "#ff6a3c"))
        lo_ = bpy.data.objects.new(f"flash{k}", ld)
        sc.collection.objects.link(lo_)
        lo_.location = (x, y, z + .4)
        for f, v in ((a0 - 1, 0.0), (a0, st.get("flash_w", 4000.0)), (a0 + n0 // 2, 0.0)):
            ld.energy = v
            ld.keyframe_insert("energy", frame=max(1, f))
    # --- camera keyed in lon/lat/metres, looking at a keyed target
    tgt = bpy.data.objects.new("look", None)
    sc.collection.objects.link(tgt)
    for k_ in P["camera"]:
        f = k_["frame"] + 1
        x, y = km_xy(k_["lon"], k_["lat"])
        cam.location = (x, y, k_["alt_m"] / 1000 * ex if k_.get("alt_exaggerated", True) else k_["alt_m"] / 1000)
        cam.keyframe_insert("location", frame=f)
        lx, ly = km_xy(k_["look_lon"], k_["look_lat"])
        tgt.location = (lx, ly, ground(k_["look_lon"], k_["look_lat"]) + k_.get("look_up_m", 0) / 1000)
        tgt.keyframe_insert("location", frame=f)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    if P.get("dof"):
        cam_data.dof.use_dof = True
        cam_data.dof.focus_object = tgt
        cam_data.dof.aperture_fstop = P["dof"].get("fstop", 8.0)
    if rigs:
        W_, H_ = P.get("width", 1920), P.get("height", 1080)
        hfov = 2 * math.atan(cam_data.sensor_width / 2 / cam_data.lens)
        vfov = 2 * math.atan(math.tan(hfov / 2) * H_ / W_)
        share = P.get("label_screen", .034)
        step = 5
        appear = [pl.get("appear", 0) + 1 for pl in P.get("places", [])]  # a pin grows when its label comes, not from frame 1
        for f in sorted(set(list(range(1, P["frames"] + 1, step)) + [P["frames"]] + [a_ for a_ in appear if a_ > 1] + [a_ + 9 for a_ in appear if a_ > 1])):
            sc.frame_set(f)
            cpos = cam.matrix_world.translation
            for rig, a_ in zip(rigs, appear):
                d = (cpos - rig.location).length
                grow = 1.0 if a_ <= 1 else min(1.0, max(1e-3, (f - a_) / 9))
                sz = max(1e-3, 2 * d * math.tan(vfov / 2) * share) * grow
                rig.scale = (sz, sz, sz)
                rig.keyframe_insert("scale", frame=f)
    if P.get("places"):  # screen position of every place each frame; hidden when the ground stands between it and the camera
        from bpy_extras.object_utils import world_to_camera_view
        from mathutils.bvhtree import BVHTree
        bvh = BVHTree.FromObject(terrain, bpy.context.evaluated_depsgraph_get())
        rig_of = {k: rigs[k] for k, pl in enumerate(P["places"]) if pl.get("stem", True) is not False}  # one rig per place
        tracks = {pl.get("id", f"p{k}"): [] for k, pl in enumerate(P["places"])}
        for f in range(1, P["frames"] + 1):
            sc.frame_set(f)
            cpos = cam.matrix_world.translation.copy()
            for k, pl in enumerate(P["places"]):
                if k in rig_of:
                    anchor = rig_of[k].matrix_world @ Vector((0, 0, 1.75))
                else:
                    x, y = km_xy(pl["lon"], pl["lat"])
                    anchor = Vector((x, y, ground(pl["lon"], pl["lat"]) + .01))
                co = world_to_camera_view(sc, cam, anchor)
                d = anchor - cpos
                hit = bvh.ray_cast(cpos, d.normalized(), max(0.0, d.length - .05))[0]
                vis = co.z > 0 and 0 <= co.x <= 1 and 0 <= co.y <= 1 and hit is None
                tracks[pl.get("id", f"p{k}")].append([f - 1, round(co.x, 5), round(1 - co.y, 5), int(vis)])
        (JOB / "tracks.json").write_text(json.dumps({"fps": 30, "width": P.get("width", 1920), "height": P.get("height", 1080),
                                                      "places": [{"id": pl.get("id", f"p{k}"), "label": pl.get("label", "")} for k, pl in enumerate(P["places"])],
                                                      "tracks": tracks}, ensure_ascii=False), encoding="utf-8")
    # --- render
    engines = [e_.identifier for e_ in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    want = P.get("engine", "EEVEE")
    sc.render.engine = "CYCLES" if want == "CYCLES" else next(x for x in engines if "EEVEE" in x)
    if sc.render.engine == "CYCLES":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = dv.type == "OPTIX"
        sc.cycles.device = "GPU"
        sc.cycles.samples = P.get("samples", 64)
        sc.cycles.use_denoising = True
    else:
        for k, v in (("taa_render_samples", P.get("samples", 32)), ("volumetric_end", 400.0),
                     ("volumetric_tile_size", P.get("volume_tile", "4")), ("volumetric_samples", P.get("volume_samples", 64)), ("use_shadows", True),
                     ("use_volumetric_shadows", bool(P.get("mist"))), ("use_raytracing", bool(P.get("raytracing", False))),
                     ("shadow_resolution_scale", P.get("shadow_resolution", 1.0))):
            try:
                setattr(sc.eevee, k, v)
                report.setdefault("settings", []).append(k)
            except Exception as e_:  # said, not swallowed: nobody knew which settings Blender 5 had dropped
                report.setdefault("settings_failed", []).append(f"{k}: {type(e_).__name__}")
    sc.render.use_motion_blur = P.get("motion_blur", True)
    sc.render.motion_blur_shutter = P.get("shutter", .5)  # a fast flyover smears its foreground at .5
    sc.render.resolution_x, sc.render.resolution_y = P.get("width", 1920), P.get("height", 1080)
    sc.render.resolution_percentage = P.get("percent", 100)
    try:
        sc.view_settings.view_transform = P.get("view", "AgX")  # map colours: "Khronos PBR Neutral" keeps the hues the bible set
        sc.view_settings.look = P.get("look", "AgX - Medium High Contrast") if sc.view_settings.view_transform == "AgX" else P.get("look", "None")
    except Exception:
        pass
    sc.view_settings.exposure = P.get("exposure", 0.0)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = str(P.get("color_depth", "8"))  # 16: no banding in sky, mist and dark seas
    sc.frame_start, sc.frame_end = 1, P["frames"]
    sc.frame_step = P.get("frame_step", 1)
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
        report["frames"] = len(range(1, P["frames"] + 1, P.get("frame_step", 1)))
    report.update(engine=sc.render.engine, setup_s=round(t1 - T0, 1), render_s=round(time.time() - t1, 1),
                  per_frame_s=round((time.time() - t1) / max(1, report["frames"]), 2), vertices=len(verts))
except Exception:
    report["error"] = traceback.format_exc()
(JOB / "done.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
