# Runs inside Blender (bpy + Blender's numpy), started by editvideo.blender.run with params.json beside this file.
# A domino shot: identical tiles stand along paths over a table-top map and fall one into the next by rigid-body
# physics (nothing is keyed but the first tile's tilt); a path that starts beside another's last tile is a branch the
# falling tile knocks down too. The camera follows the front of the fall along the longest path and rises to show the
# whole chain. Writes frame_####.png (or still_####.png), tracks.json (the screen position of every named tile, each
# frame, so the film draws crisp labels over the picture) and done.json.
#
# Map units: one unit is one degree of longitude; latitude is scaled by 1 (a regular lon/lat image, as
# editvideo.imagery.satellite returns it). The tiles are a table-top model, far larger than the map's scale.
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


def xy(lon, lat):
    w, s, e, n = P["bbox"]
    return lon - (w + e) / 2, lat - (s + n) / 2


def principled(name, color, rough=.5, coat=0.0, spec=.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*hexrgb(color), 1)
    b.inputs["Roughness"].default_value = rough
    for k, v in (("Coat Weight", coat), ("Specular IOR Level", spec)):
        if k in b.inputs:
            b.inputs[k].default_value = v
    return m


def resample(points, step):
    """Points every `step` units along a polyline, with the direction of travel at each."""
    out = []
    carry = 0.0
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        seg = math.hypot(bx - ax, by - ay)
        if seg <= 1e-9:
            continue
        d = carry
        while d <= seg:
            u = d / seg
            out.append(((ax + (bx - ax) * u, ay + (by - ay) * u), math.atan2(by - ay, bx - ax)))
            d += step
        carry = d - seg
    return out


try:
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    w, s, e, n = P["bbox"]
    # --- the table: the map image on a plane, darkened toward the edges by the light, slightly rough like paper
    bpy.ops.mesh.primitive_plane_add(size=1)
    table = bpy.context.active_object
    table.name = "table"
    table.scale = (e - w, n - s, 1)
    mt = bpy.data.materials.new("map")
    mt.use_nodes = True
    nt = mt.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(P["map"])
    tex.extension = "EXTEND"
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = P.get("map_saturation", .55)
    hsv.inputs["Value"].default_value = P.get("map_value", .8)
    nt.links.new(tex.outputs["Color"], hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = .62
    table.data.materials.append(mt)
    # the map lies on a larger dark table, so a wide frame shows its edge on wood, not a void
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -.004))
    under = bpy.context.active_object
    under.name = "under"
    under.scale = ((e - w) * P.get("table_margin", 2.2), (n - s) * P.get("table_margin", 2.2), 1)
    under.data.materials.append(principled("table", P.get("table_color", "#120d0a"), rough=.85, spec=.2))  # matte: no glare of the lamps
    bpy.ops.rigidbody.world_add()
    rbw = sc.rigidbody_world
    rbw.time_scale = P.get("time_scale", 1.0)
    rbw.substeps_per_frame = 20
    rbw.solver_iterations = 20
    rbw.point_cache.frame_start, rbw.point_cache.frame_end = 1, P["frames"]
    sc.frame_start, sc.frame_end = 1, P["frames"]
    bpy.context.view_layer.objects.active = table
    bpy.ops.rigidbody.object_add(type="PASSIVE")
    table.rigid_body.friction = .8
    # --- the tiles: one mesh (a bevelled box with a groove across the middle and a pip each side on both faces)
    h = P.get("tile_height", 1.2)
    tw, tt = h * .5, h * .16
    body = principled("tile", P.get("tile_color", "#16181b"), rough=.22, coat=.6)
    ivory = principled("pip", P.get("pip_color", "#e9dfc9"), rough=.35)
    bpy.ops.mesh.primitive_cube_add(size=1)
    proto = bpy.context.active_object
    proto.name = "tile_proto"
    proto.scale = (tt, tw, h)
    bpy.ops.object.transform_apply(scale=True)
    bev = proto.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments = h * .035, 3
    bpy.ops.object.modifier_apply(modifier="bevel")
    proto.data.materials.append(body)
    proto.data.materials.append(ivory)
    parts = [proto]
    for side in (1, -1):  # both broad faces: the groove and two pips
        bpy.ops.mesh.primitive_cube_add(size=1, location=(side * (tt / 2 + .002), 0, 0))
        g = bpy.context.active_object
        g.scale = (.004, tw * .78, h * .018)
        parts.append(g)
        for zz in (h * .25, -h * .25):
            bpy.ops.mesh.primitive_cylinder_add(radius=h * .055, depth=.008, location=(side * (tt / 2 + .002), 0, zz), rotation=(0, math.pi / 2, 0))
            parts.append(bpy.context.active_object)
    for p_ in parts[1:]:
        p_.data.materials.clear()
        p_.data.materials.append(ivory)
    bpy.ops.object.select_all(action="DESELECT")
    for p_ in parts:
        p_.select_set(True)
    bpy.context.view_layer.objects.active = proto
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    mesh = proto.data
    bpy.data.objects.remove(proto)
    paths = P.get("paths") or [P["path"]]
    spots, owner = [], []  # every tile's (position, heading), and the path it stands on
    for j, path in enumerate(paths):
        for sp_ in resample([xy(lo, la) for lo, la in path], h * P.get("spacing", .6)):
            spots.append(sp_)
            owner.append(j)
    tiles = []
    for i, ((x, y), ang) in enumerate(spots):
        ob = bpy.data.objects.new(f"tile{i:03d}", mesh)
        sc.collection.objects.link(ob)
        ob.location = (x, y, h / 2 + .001)
        ob.rotation_euler = (0, 0, ang)  # thin axis (local x) along the path: it falls forward along it
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.rigidbody.object_add(type="ACTIVE")
        ob.rigid_body.collision_shape = "BOX"
        ob.rigid_body.mass = 1.0
        ob.rigid_body.friction = .55
        ob.rigid_body.restitution = .05
        ob.rigid_body.linear_damping, ob.rigid_body.angular_damping = .04, .12
        ob.select_set(False)
        tiles.append(ob)
    # the push: the first tile leans past its balance point at frame 1 (gravity does the rest)
    first = tiles[0]
    lean = math.radians(P.get("lean_deg", 14))
    fx, fy = math.cos(spots[0][1]), math.sin(spots[0][1])
    first.rotation_mode = "QUATERNION"
    from mathutils import Quaternion
    q0 = Quaternion((0, 0, 1), spots[0][1])
    axis = Vector((-fy, fx, 0))  # tipping forward along the path
    first.rotation_quaternion = Quaternion(axis, lean) @ q0
    first.location.z = h / 2 * math.cos(lean) + .02
    # named tiles: the one nearest each named place
    named = []
    for pl in P.get("names", []):
        px, py = xy(pl["lon"], pl["lat"])
        k = min(range(len(spots)), key=lambda i: (spots[i][0][0] - px) ** 2 + (spots[i][0][1] - py) ** 2)
        named.append({"id": pl["id"], "label": pl.get("label", pl["id"]), "tile": k})
    # --- light: a warm soft key from one side as over a planning table, a cool rim, a dark room
    sc.world = bpy.data.worlds.new("room")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (*hexrgb(P.get("room", "#05070a")), 1)
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .3
    for name, loc, energy, color, size in (("key", P.get("key_pos", (-14, -10, 16)), P.get("key_w", 9000), P.get("key_color", "#ffd9a8"), 10),
                                           ("rim", (16, 18, 9), 2500, "#9fb6d6", 6)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size, ld.color = energy, size, hexrgb(color)
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    # --- simulate once, frame by frame, recording where the front of the fall is (on the followed path)
    follow = P.get("follow", max(range(len(paths)), key=lambda j: owner.count(j)))
    on_path = [i for i in range(len(tiles)) if owner[i] == follow]
    tilt = []  # per frame: index of the furthest tile of the followed path that has tipped past 30 degrees
    fell_at = [None] * len(tiles)
    for f in range(1, P["frames"] + 1):
        sc.frame_set(f)
        front = on_path[0]
        for i, ob in enumerate(tiles):
            up = ob.matrix_world.to_3x3() @ Vector((0, 0, 1))
            if up.z < math.cos(math.radians(30)):
                if owner[i] == follow:
                    front = max(front, i)
                if fell_at[i] is None:
                    fell_at[i] = f - 1
        tilt.append(front)
    # where a chain stops (a branch the falling tile only grazed, a tile knocked sideways): tip the first standing tile a
    # moment after the one before it falls, and simulate again; at most `rescues` passes
    from mathutils import Quaternion
    pushed = []

    def simulate():
        tl, fa = [], [None] * len(tiles)
        for f in range(1, P["frames"] + 1):
            sc.frame_set(f)
            front = on_path[0]
            for i, ob in enumerate(tiles):
                up = ob.matrix_world.to_3x3() @ Vector((0, 0, 1))
                if up.z < math.cos(math.radians(30)):
                    if owner[i] == follow:
                        front = max(front, i)
                    if fa[i] is None:
                        fa[i] = f - 1
            tl.append(front)
        return tl, fa
    for _ in range(P.get("rescues", 3) if P.get("push_branches", True) else 0):
        stuck = []
        for j in range(len(paths)):
            idx = [i for i in range(len(tiles)) if owner[i] == j]
            first_up = next((i for i in idx if fell_at[i] is None), None)
            if first_up is None or first_up == idx[0] and j == 0:
                continue
            if first_up != idx[0]:
                before = fell_at[first_up - 1]
            else:  # a branch's first tile: timed from the nearest tile of another path, the one meant to knock it down
                (bx_, by_), _ = spots[first_up]
                near = min((i for i in range(len(tiles)) if owner[i] != j), key=lambda i: (spots[i][0][0] - bx_) ** 2 + (spots[i][0][1] - by_) ** 2)
                before = fell_at[near]
            if before is not None and before + 6 < P["frames"]:
                stuck.append((first_up, before + P.get("branch_delay", 4)))
        if not stuck:
            break
        for i0, hit in stuck:
            ob = tiles[i0]
            ob.rotation_mode = "QUATERNION"
            ang = spots[i0][1]
            q0 = Quaternion((0, 0, 1), ang)
            ax_ = Vector((-math.sin(ang), math.cos(ang), 0))
            for f, lean_, kin in ((1, 0.0, True), (hit, 0.0, True), (hit + 2, math.radians(18), True), (hit + 3, math.radians(18), False)):
                ob.rotation_quaternion = Quaternion(ax_, lean_) @ q0
                ob.location.z = h / 2 * math.cos(lean_) + .001
                ob.keyframe_insert("rotation_quaternion", frame=f)
                ob.keyframe_insert("location", frame=f)
                ob.rigid_body.kinematic = kin
                ob.rigid_body.keyframe_insert("kinematic", frame=f)
            pushed.append({"tile": i0, "path": owner[i0], "at": hit})
        try:
            bpy.ops.ptcache.free_bake_all()
        except Exception:
            pass
        rbw.point_cache.frame_end = P["frames"]
        tilt, fell_at = simulate()
    report["pushed"] = pushed
    report["tiles"] = len(tiles)
    report["fell_at"] = fell_at
    report["chain_complete"] = all(fell_at[i] is not None for i in range(len(tiles)) if i + 1 == len(tiles) or owner[i + 1] != owner[i])
    report["paths"] = [{"tiles": owner.count(j), "last_falls_at": fell_at[max(i for i in range(len(tiles)) if owner[i] == j)]} for j in range(len(paths))]
    for nm in named:
        nm["falls_at"] = fell_at[nm["tile"]]
    report["named"] = named
    # --- camera: follows the front, close and low at the start, high and wide at the end
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = P.get("lens", 50)
    cam_d.clip_start, cam_d.clip_end = .05, 500
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tgt = bpy.data.objects.new("look", None)
    sc.collection.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    cam_d.dof.use_dof = P.get("dof", True)
    cam_d.dof.focus_object = tgt
    cam_d.dof.aperture_fstop = P.get("fstop", 2.8)
    N = P["frames"]
    step = P.get("camera_step", 12)
    keys = list(range(0, N, step)) + [N - 1]
    smooth = []
    for f in keys:  # the front, a little ahead of the falling tile, averaged over a second to calm the follow
        win = [tilt[min(N - 1, max(0, g))] for g in range(f - 15, f + 16)]
        k = min(on_path[-1], int(sum(win) / len(win)) + P.get("lead_tiles", 3))
        smooth.append(Vector((*spots[k][0], 0)))
    for i, f in enumerate(keys):
        u = f / max(1, N - 1)
        ease = u * u * (3 - 2 * u)
        start, end = P.get("camera_start", {}), P.get("camera_end", {})
        dist = start.get("distance", 6) + (end.get("distance", 40) - start.get("distance", 6)) * ease
        elev = math.radians(start.get("elevation", 12) + (end.get("elevation", 55) - start.get("elevation", 12)) * ease)
        azim = math.radians(start.get("azimuth", -120) + (end.get("azimuth", -95) - start.get("azimuth", -120)) * ease)
        c = smooth[i]
        if end.get("center") and ease > .5:  # the end frames frame the whole chain, not its last tile
            cx, cy = xy(*end["center"])
            c = c.lerp(Vector((cx, cy, 0)), (ease - .5) * 2)
        tgt.location = c + Vector((0, 0, h * .4))
        tgt.keyframe_insert("location", frame=f + 1)
        cam.location = c + Vector((math.cos(azim) * math.cos(elev), math.sin(azim) * math.cos(elev), math.sin(elev))) * dist
        cam.keyframe_insert("location", frame=f + 1)
    for ob in (cam, tgt):
        if ob.animation_data and ob.animation_data.action:
            try:
                for fc in ob.animation_data.action.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "BEZIER"
                        kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
            except Exception:
                pass
    # --- where each named tile is on screen, every frame (its standing top, so a label stays put as the tile falls)
    from bpy_extras.object_utils import world_to_camera_view
    tracks = {nm["id"]: [] for nm in named}
    for f in range(1, N + 1):
        sc.frame_set(f)
        for nm in named:
            (x, y), _ = spots[nm["tile"]]
            co = world_to_camera_view(sc, cam, Vector((x, y, h * 1.05)))
            tracks[nm["id"]].append([f - 1, round(co.x, 5), round(1 - co.y, 5), int(co.z > 0 and 0 <= co.x <= 1 and 0 <= co.y <= 1)])
    (JOB / "tracks.json").write_text(json.dumps({"fps": 30, "width": P.get("width", 1920), "height": P.get("height", 1080),
                                                  "named": named, "tracks": tracks}), encoding="utf-8")
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
        report["frames"] = N
    report.update(engine=sc.render.engine, setup_s=round(t1 - T0, 1), render_s=round(time.time() - t1, 1),
                  per_frame_s=round((time.time() - t1) / max(1, report["frames"]), 2))
except Exception:
    report["error"] = traceback.format_exc()
(JOB / "done.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
