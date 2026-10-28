# Runs inside Blender (bpy), started by editvideo.blender.run with params.json beside this file.
# A bloc map: every country is a tile standing on a table-top board (the oceans), with a thin gap between neighbours.
# Named countries rise and take their colour at their frame (a side taken, a recognition, an alliance); flows are
# streams of light that travel along an arc from one place to another (aid, troops, money), so their direction reads
# without arrowheads; small islands can be marked. The camera is keyed in map coordinates. Like the terrain template,
# labels are left to the film: the screen position of every label anchor, each frame, goes to tracks.json.
# Writes frame_####.png (or still_####.png), tracks.json and done.json.
#
# Board units: one unit is one degree of latitude; longitude is scaled by cos(lat_c) (the projection of
# editvideo.resources.MapProjection), centred on the bbox.
import json, math, sys, time, traceback
from pathlib import Path

import bpy
from mathutils import Vector

JOB = Path(sys.argv[sys.argv.index("--python") + 1]).parent
P = json.loads((JOB / "params.json").read_text(encoding="utf-8"))
T0 = time.time()
report = {}


def hexrgb(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in srgb)


W_, S_, E_, N_ = P["bbox"]
LAT_C = P.get("lat_c", (S_ + N_) / 2)
K = math.cos(math.radians(LAT_C))


def xy(lon, lat):
    return (lon - (W_ + E_) / 2) * K, lat - (S_ + N_) / 2


def paper(m, b, cell):
    """Printed paper on a tile: a fine fibre bump, roughness that varies a little and a faint mottle of the ink, so a
    country reads as a printed, handled object instead of flat plastic (peak luma 95/255, roughness .6 everywhere)."""
    nt = m.node_tree
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    fib = nt.nodes.new("ShaderNodeTexNoise")
    fib.inputs["Scale"].default_value = 1.0 / cell
    fib.inputs["Detail"].default_value = 8.0
    fib.inputs["Roughness"].default_value = .62
    nt.links.new(geo.outputs["Position"], fib.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = P.get("paper_bump", .22)
    bump.inputs["Distance"].default_value = cell * .02
    nt.links.new(fib.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = .48, .72
    nt.links.new(fib.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    mot = nt.nodes.new("ShaderNodeTexNoise")
    mot.inputs["Scale"].default_value = 1.0 / (cell * 30)
    mot.inputs["Detail"].default_value = 2.0
    nt.links.new(geo.outputs["Position"], mot.inputs["Vector"])
    mm = nt.nodes.new("ShaderNodeMapRange")
    mm.inputs["To Min"].default_value, mm.inputs["To Max"].default_value = .93, 1.05
    nt.links.new(mot.outputs["Fac"], mm.inputs["Value"])
    return mm.outputs["Result"]


def material(name, color, rough=.55, emit=None, strength=0.0, cell=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*hexrgb(color), 1)
    b.inputs["Roughness"].default_value = rough
    if cell:  # the mottle multiplies whatever base colour the tile is given later (a keyed rise to its bloc colour too)
        mott = paper(m, b, cell)
        m["mottle"] = True
        rgb = m.node_tree.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (*hexrgb(color), 1)
        mul = m.node_tree.nodes.new("ShaderNodeVectorMath")
        mul.operation = "SCALE"
        m.node_tree.links.new(rgb.outputs[0], mul.inputs[0])
        m.node_tree.links.new(mott, mul.inputs["Scale"])
        m.node_tree.links.new(mul.outputs["Vector"], b.inputs["Base Color"])
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = .25
            break
    if emit:
        b.inputs["Emission Color"].default_value = (*hexrgb(emit), 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def emission(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n_ in list(nt.nodes):
        nt.nodes.remove(n_)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*hexrgb(color), 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def smooth_keys(ob):
    ad = ob.animation_data if hasattr(ob, "animation_data") else None
    if not ad or not ad.action:
        return
    try:
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
    except Exception:
        pass


try:
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    shapes = json.loads(Path(P["shapes"]).read_text(encoding="utf-8"))  # {name: [[[lon, lat], ...], ...]}
    span_x, span_y = (E_ - W_) * K, N_ - S_
    # --- the board: the oceans, a matte surface a little larger than the map, on a darker table
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    board = bpy.context.active_object
    board.scale = (span_x * P.get("board_margin", 1.8), span_y * P.get("board_margin", 1.8), 1)  # the sea runs past the frame edge
    board.data.materials.append(material("sea", P.get("sea", "#16222e"), rough=.8))
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -.02))
    table = bpy.context.active_object
    table.scale = (span_x * 3, span_y * 3, 1)
    table.data.materials.append(material("table", P.get("table", "#0c0a09"), rough=.9))
    # --- the tiles
    base_h = P.get("tile_height", .12)
    gap = P.get("gap", .06)
    named = P.get("countries", {})
    tiles = {}
    land = P.get("land", "#4a463f")
    for name, rings in shapes.items():
        spec = named.get(name, {})
        mat = material(f"m_{name}", land, rough=.6, cell=max(span_x, span_y) * P.get("paper_cell", .004))
        parts = []
        for ring in rings:
            pts = [xy(lo, la) for lo, la in ring]
            if len(pts) < 3:
                continue
            cu = bpy.data.curves.new(f"c_{name}_{len(parts)}", "CURVE")
            cu.dimensions = "2D"
            cu.fill_mode = "BOTH"
            sp = cu.splines.new("POLY")
            sp.points.add(len(pts) - 1)
            for i, (x, y) in enumerate(pts):
                sp.points[i].co = (x, y, 0, 1)
            sp.use_cyclic_u = True
            cu.extrude = base_h / 2
            ob = bpy.data.objects.new(f"t_{name}_{len(parts)}", cu)
            sc.collection.objects.link(ob)
            ob.location.z = base_h / 2
            ob.data.materials.append(mat)
            parts.append(ob)
        if not parts:
            continue
        # one object per country: the curves become one mesh whose origin is on the board, so a rise (scale z) lifts its
        # top and keeps its foot; bevelled top edges leave a thin dark crease between neighbours
        bpy.ops.object.select_all(action="DESELECT")
        for ob in parts:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.convert(target="MESH")
        if len(parts) > 1:
            bpy.ops.object.join()
        ob = bpy.context.active_object
        ob.name = f"tile_{name}"
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width, bev.segments, bev.limit_method = min(gap, base_h * .45), 2, "ANGLE"
        tiles[name] = {"ob": ob, "mat": mat}
    # --- named countries rise and take their colour; a pulse can mark one later
    for name, spec in named.items():
        t = tiles.get(name)
        if not t:
            continue
        ob, mat = t["ob"], t["mat"]
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        a, n = spec.get("at", 0) + 1, spec.get("frames", 18)
        rise = spec.get("rise", 4.0)
        ob.scale = (1, 1, 1)
        ob.keyframe_insert("scale", frame=max(1, a - 1))
        ob.scale = (1, 1, rise)
        ob.keyframe_insert("scale", frame=a + n)
        smooth_keys(ob)
        col = spec.get("color", land)
        rgbn = next((nd for nd in mat.node_tree.nodes if nd.bl_idname == "ShaderNodeRGB"), None)
        target = rgbn.outputs[0] if rgbn else bsdf.inputs["Base Color"]
        target.default_value = (*hexrgb(land), 1)
        target.keyframe_insert("default_value", frame=max(1, a - 1))
        target.default_value = (*hexrgb(col), 1)
        target.keyframe_insert("default_value", frame=a + n // 2)
        if spec.get("glow"):
            bsdf.inputs["Emission Color"].default_value = (*hexrgb(spec.get("glow_color", col)), 1)
            for f, v in ((max(1, a - 1), 0.0), (a + n // 2, spec["glow"] * 2.2), (a + n + 20, spec["glow"])):
                bsdf.inputs["Emission Strength"].default_value = v
                bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
            for f in range(a + n + 40, P["frames"] + 1, 40) if spec.get("pulse") else []:
                for df, v in ((0, spec["glow"]), (20, spec["glow"] * 1.8)):
                    bsdf.inputs["Emission Strength"].default_value = v
                    bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=min(P["frames"], f + df))
    # --- islands: small raised dots (the archipelagos a country's map carries)
    for k, isl in enumerate(P.get("islands", [])):
        x, y = xy(isl["lon"], isl["lat"])
        bpy.ops.mesh.primitive_cylinder_add(radius=isl.get("r", .22), depth=base_h * isl.get("rise", 3.0), location=(x, y, base_h * isl.get("rise", 3.0) / 2))
        o = bpy.context.active_object
        o.data.materials.append(material(f"isl{k}", isl.get("color", land), rough=.5, emit=isl.get("color", land), strength=isl.get("glow", 0.0)))
    # --- flows: an arc lifted over the board, a faint trail growing along it, and beads of light travelling it
    flow_objs = []  # (trail curve data, its width, [beads]) to keep one size on screen as the camera moves
    for k, fl in enumerate(P.get("flows", [])):
        (x0, y0), (x1, y1) = xy(*fl["from"]), xy(*fl["to"])
        dist = math.hypot(x1 - x0, y1 - y0)
        hgt = fl.get("height", .18) * dist + base_h * 5
        n_pts = 64
        cu = bpy.data.curves.new(f"flow{k}", "CURVE")
        cu.dimensions = "3D"
        sp = cu.splines.new("POLY")
        sp.points.add(n_pts - 1)
        for i in range(n_pts):
            u = i / (n_pts - 1)
            sp.points[i].co = (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, base_h * fl.get("lift", 4.5) + hgt * math.sin(math.pi * u), 1)
        cu.bevel_depth = fl.get("width", .05)
        cu.bevel_resolution = 2
        cu.use_path = True
        trail = bpy.data.objects.new(f"flow{k}", cu)
        sc.collection.objects.link(trail)
        trail.data.materials.append(emission(f"trail{k}", fl.get("color", "#e8b04a"), fl.get("trail_glow", P.get("flow_glow", .8))))
        trail.visible_shadow = False
        a, g = fl["at"] + 1, fl.get("frames", 30)
        cu.bevel_factor_mapping_end = "SPLINE"
        cu.bevel_factor_end = 0.0
        cu.keyframe_insert("bevel_factor_end", frame=a)
        cu.bevel_factor_end = 1.0
        cu.keyframe_insert("bevel_factor_end", frame=a + g)
        flow_objs.append((cu, fl.get("width", .05), []))
        if P.get("flow_style") == "draw" or fl.get("arrow"):
            # drawn like a cartographer's arrow: thin at its source, full at its head, an arrowhead riding the drawing
            # end and staying at the destination (the bible's flow_style; glowing streams alone read as tech explainer)
            tc = bpy.data.curves.new(f"taper{k}", "CURVE")
            tsp = tc.splines.new("POLY")
            tsp.points.add(1)
            tsp.points[0].co, tsp.points[1].co = (0, .3, 0, 1), (1, 1.0, 0, 1)
            taper = bpy.data.objects.new(f"taper{k}", tc)
            sc.collection.objects.link(taper)
            taper.hide_render = True
            cu.taper_object = taper
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=fl.get("width", .05) * 3.2, radius2=0, depth=fl.get("width", .05) * 7)
            head = bpy.context.active_object
            head.data.materials.append(emission(f"head{k}", fl.get("color", "#e8b04a"), fl.get("trail_glow", P.get("flow_glow", .8)) * 1.3))
            head.visible_shadow = False
            fp = head.constraints.new("FOLLOW_PATH")
            fp.target, fp.use_fixed_location, fp.use_curve_follow = trail, True, True
            fp.forward_axis = "FORWARD_Z"
            fp.offset_factor = 0.0
            fp.keyframe_insert("offset_factor", frame=a)
            fp.offset_factor = 1.0
            fp.keyframe_insert("offset_factor", frame=a + g)
            head.hide_render = True
            head.keyframe_insert("hide_render", frame=1)
            head.hide_render = False
            head.keyframe_insert("hide_render", frame=a)
            flow_objs[-1][2].append(head)
        beads = fl.get("beads", 9)
        lap = fl.get("lap", 45)  # frames for one bead to travel the arc
        bmat = emission(f"bead{k}", fl.get("bead_color", fl.get("color", "#ffd48a")), fl.get("glow", P.get("bead_glow", 6.0)))
        for j in range(beads):
            bpy.ops.mesh.primitive_uv_sphere_add(radius=fl.get("bead", .11), segments=12, ring_count=8)
            bd = bpy.context.active_object
            flow_objs[-1][2].append(bd)
            bd.data.materials.append(bmat)
            bd.visible_shadow = False
            fp = bd.constraints.new("FOLLOW_PATH")
            fp.target, fp.use_fixed_location = trail, True
            start = a + g // 2 + j * lap // beads
            fp.offset_factor = 0.0
            fp.keyframe_insert("offset_factor", frame=start)
            fp.offset_factor = 1.0
            fp.keyframe_insert("offset_factor", frame=start + lap)
            try:
                fc = bd.animation_data.action.fcurves.find('constraints["Follow Path"].offset_factor')
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
                fc.modifiers.new("CYCLES")
            except Exception:
                pass
            bd.hide_render = True
            bd.keyframe_insert("hide_render", frame=1)
            bd.hide_render = False
            bd.keyframe_insert("hide_render", frame=start)
            if fl.get("until"):
                bd.hide_render = True
                bd.keyframe_insert("hide_render", frame=fl["until"] + 1)
    # --- light: a warm soft key from the south-west as over a planning table, a cool rim, a dark room
    sc.world = bpy.data.worlds.new("room")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (*hexrgb(P.get("room", "#06080b")), 1)
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = P.get("room_strength", .35)
    big = max(span_x, span_y)
    for name, loc, energy, color, size in (("key", (-.35 * big, -.45 * big, .55 * big), P.get("key_w", 44.0), P.get("key_color", "#ffe2c0"), .5 * big),
                                           ("rim", (.45 * big, .5 * big, .3 * big), P.get("rim_w", 8.0), "#a9c0e0", .3 * big)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy * big * big  # watts scale with the board so the light reads the same at any map size
        ld.size, ld.color = size, hexrgb(color)
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    # --- camera: keys in map coordinates (target lon/lat, distance, elevation, azimuth)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = P.get("lens", 40)
    cam_d.clip_start, cam_d.clip_end = .05, 5000
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt = bpy.data.objects.new("look", None)
    sc.collection.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    for k_ in P["camera"]:
        f = k_["frame"] + 1
        x, y = xy(k_["lon"], k_["lat"])
        el, az = math.radians(k_.get("elevation", 60)), math.radians(k_.get("azimuth", -90))
        d = k_["distance"]
        tgt.location = (x, y, 0)
        tgt.keyframe_insert("location", frame=f)
        cam.location = (x + d * math.cos(el) * math.cos(az), y + d * math.cos(el) * math.sin(az), d * math.sin(el))
        cam.keyframe_insert("location", frame=f)
    smooth_keys(cam)
    smooth_keys(tgt)
    # flows keep their size on screen: widths and beads scale with the camera's distance (a bead sized for the whole
    # board filled Saigon when the camera came in)
    ref = P.get("size_ref", 120.0)
    if flow_objs:
        for f in list(range(1, P["frames"] + 1, 5)) + [P["frames"]]:
            sc.frame_set(f)
            k_ = max(.08, (cam.matrix_world.translation - tgt.matrix_world.translation).length / ref)
            for cu_, w0, beads_ in flow_objs:
                cu_.bevel_depth = w0 * k_
                cu_.keyframe_insert("bevel_depth", frame=f)
                for bd in beads_:
                    bd.scale = (k_, k_, k_)
                    bd.keyframe_insert("scale", frame=f)
    if P.get("dof"):
        cam_d.dof.use_dof = True
        cam_d.dof.focus_object = tgt
        cam_d.dof.aperture_fstop = P["dof"].get("fstop", 8.0)
    # --- where each label anchor is on screen, every frame (on top of its tile, which may be rising)
    from bpy_extras.object_utils import world_to_camera_view
    labels = P.get("labels", [])
    tracks = {lb["id"]: [] for lb in labels}
    for f in range(1, P["frames"] + 1):
        sc.frame_set(f)
        for lb in labels:
            x, y = xy(lb["lon"], lb["lat"])
            t = tiles.get(lb.get("country", ""))
            z = base_h * (t["ob"].scale.z if t else 1.0) + .02
            co = world_to_camera_view(sc, cam, Vector((x, y, z)))
            tracks[lb["id"]].append([f - 1, round(co.x, 5), round(1 - co.y, 5), int(co.z > 0 and 0 <= co.x <= 1 and 0 <= co.y <= 1)])
    (JOB / "tracks.json").write_text(json.dumps({"fps": 30, "width": P.get("width", 1920), "height": P.get("height", 1080),
                                                  "labels": labels, "tracks": tracks}, ensure_ascii=False), encoding="utf-8")
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
        for k, v in (("taa_render_samples", P.get("samples", 48)), ("use_gtao", True), ("use_shadows", True), ("use_raytracing", True)):
            try:
                setattr(sc.eevee, k, v)
            except Exception:
                pass
    sc.render.use_motion_blur = P.get("motion_blur", True)
    sc.render.motion_blur_shutter = P.get("shutter", .3)
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
    report.update(engine=sc.render.engine, tiles=len(tiles), setup_s=round(t1 - T0, 1), render_s=round(time.time() - t1, 1),
                  per_frame_s=round((time.time() - t1) / max(1, report["frames"]), 2))
except Exception:
    report["error"] = traceback.format_exc()
(JOB / "done.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
