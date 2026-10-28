"""Blender as an offline renderer for the shots a browser cannot make beautiful (round 13: the owner judged the sixth
cut's Three.js terrain "ugly, too simple" and asked whether to bring in Blender, at the least cost for the most quality).

Blender runs headless, once per shot: a job folder holds the script (editvideo/blender_scripts/<name>.py, copied) and its
params.json; the script writes PNG frames and done.json there. The film then plays the encoded clip like footage, so the
3D is computed once, not on every export, and both engines show the same pixels. Jobs are cached by a hash of the
script, the params and every input file, so an unchanged shot is never rendered twice.

Blender is found from EDITVIDEO_BLENDER, the usual install folders, or the Microsoft Store build's
blender-launcher.exe alias (that launcher returns at once and drops stdout, so completion is read from done.json).
Measured on the owner's RTX 3060 (Blender 5.2.2 LTS): EEVEE about 0.65 s a 1080p frame after an 18 s shader warm-up;
Cycles with OptiX, 64 samples and the denoiser, about 12 s. Never render with Blender while a film export runs."""
import hashlib, json, os, shutil, subprocess, time
from pathlib import Path
from . import store

SCRIPTS = Path(__file__).parent / "blender_scripts"


def find():
    """The Blender executable or launcher, or None."""
    env = os.environ.get("EDITVIDEO_BLENDER")
    if env and Path(env).is_file():
        return env
    from . import store
    # the usual install folders, and a tools folder beside the data store (a portable zip unpacked there)
    for base in (Path(r"C:\Program Files\Blender Foundation"), store.DATA.parent / "tools"):
        if base.is_dir():
            for exe in sorted(base.rglob("blender.exe"), reverse=True):
                return str(exe)
    mac = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if mac.is_file():
        return str(mac)
    alias = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "blender-launcher.exe"
    if alias.exists():
        return str(alias)
    on_path = shutil.which("blender")
    return on_path


def _digest(params, script, files):
    h = hashlib.sha256(script.read_bytes())
    from .media import sha256
    hashes = {str(f): sha256(Path(f)) for f in files}
    def content(value):
        if isinstance(value, dict): return {k: content(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)): return [content(v) for v in value]
        if isinstance(value, (str, Path)) and str(value) in hashes:
            return {"file_sha256": hashes[str(value)]}
        return value
    h.update(json.dumps(content(params), sort_keys=True, default=str).encode())
    for digest in sorted(hashes.values()): h.update(digest.encode())
    return h.hexdigest()[:20]


def run(script_name, params, files=(), timeout=3 * 3600, poll=2.0, cancelled=None):
    """Render with blender_scripts/<script_name>.py and `params` (json-able; input paths listed in `files` count toward
    the cache key). Returns the job's done.json plus its folder. A finished job with the same key is returned as is."""
    exe = find()
    if not exe:
        raise RuntimeError("Blender not found: set EDITVIDEO_BLENDER to blender.exe (portable zip from blender.org is fine)")
    script = SCRIPTS / f"{script_name}.py"
    if not script_name.replace("_", "").isalnum() or not script.is_file():  # bundled templates only, never a prompt's Python
        raise ValueError("Choose a bundled 3D template: " + ", ".join(sorted(x.stem for x in SCRIPTS.glob("*.py"))))
    from . import style
    params = {**style.blender_defaults(script_name), **params}  # the series bible under the scene's own values
    key = _digest(params, script, files)
    job = store.DATA / "cache" / "blender" / f"{script_name}-{key}"
    done = job / "done.json"
    if done.is_file():
        r = json.loads(done.read_text(encoding="utf-8"))
        if not r.get("error"):
            return {**r, "job": str(job), "cached": True}
    job.mkdir(parents=True, exist_ok=True)
    done.unlink(missing_ok=True)
    (job / "blender.pid").unlink(missing_ok=True)  # an earlier run's dead pid read as a crash of this one
    # The Store launcher detaches, so record the actual Blender process for cancellation/timeout cleanup.
    prefix = "import os as _ev_os\nfrom pathlib import Path as _ev_Path\n_ev_Path(__file__).with_name('blender.pid').write_text(str(_ev_os.getpid()))\n"
    (job / "job.py").write_text(prefix + script.read_text(encoding="utf-8"), encoding="utf-8")
    (job / "params.json").write_text(json.dumps({**params, "out": str(job)}, ensure_ascii=False, default=str), encoding="utf-8")
    args = [exe, "-b", "--factory-startup", "--python", str(job / "job.py")]
    launcher = Path(exe).name.lower() == "blender-launcher.exe"
    with store.gpu_admission(cancelled, f"Blender {script_name}"):  # never beside a film render or another GPU job
        return _wait(job, done, args, launcher, timeout, poll, cancelled)


def _wait(job, done, args, launcher, timeout, poll, cancelled):
    log = None if launcher else open(job / "blender.log", "w")
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL if launcher else log, stderr=subprocess.STDOUT)
        return _watch(job, done, proc, launcher, timeout, poll, cancelled)
    finally:
        if log:
            log.close()


def _watch(job, done, proc, launcher, timeout, poll, cancelled):
    t0, gone = time.time(), None
    while not done.is_file():
        stopped = cancelled and cancelled()
        pidfile = job / "blender.pid"
        if launcher:  # the Store launcher detaches: watch the Blender process itself, or a crash waits out the whole timeout
            if pidfile.is_file():
                try:
                    alive = store.process_alive(int(pidfile.read_text()))
                except ValueError:
                    alive = True
                gone = None if alive else (gone or time.time())
                if gone and time.time() - gone > 5 and not done.is_file():
                    raise RuntimeError(f"Blender exited without finishing job {job.name} (crash or out of memory)")
            elif time.time() - t0 > 180:
                raise RuntimeError(f"Blender did not start job {job.name} within 3 minutes")
        if stopped or time.time() - t0 > timeout:
            pidfile = job / "blender.pid"
            if pidfile.is_file():
                try:
                    import signal
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)
                except (OSError, ValueError): pass
            if proc.poll() is None: proc.kill()
            if stopped:
                from .media import Cancelled
                raise Cancelled()
            raise TimeoutError(f"Blender job {job.name} ran past {timeout} s")
        if not launcher and proc.poll() is not None and not done.is_file():
            raise RuntimeError(f"Blender exited without finishing; see {job / 'blender.log'}")
        time.sleep(poll)
    time.sleep(.5)
    r = json.loads(done.read_text(encoding="utf-8"))
    if r.get("error"):
        raise RuntimeError(f"Blender job {job.name} failed:\n{r['error'][-1500:]}")
    return {**r, "job": str(job), "cached": False}


def encode(job, fps=30, crf=16, name=None, finish=False):
    """The job's frames (frame_0001.png ..., 8 or 16 bit) as an H.264 clip beside them, tagged BT.709. finish=True (or a
    dict of finish values) runs editvideo.finish first: the bible's softening, halation, grain, gate weave, vignette."""
    from .media import FFMPEG
    from . import finish as fin
    job = Path(job)
    out = job / (name or ("shot-finished.mp4" if finish else "shot.mp4"))
    if not out.is_file():  # encoded beside it and checked first: a partial clip was otherwise reused (and credited) for good
        tmp = out.with_name(out.stem + ".part.mp4")
        frames = len(list(job.glob("frame_*.png")))
        src = ["-framerate", str(fps), "-i", str(job / "frame_%04d.png")]
        if finish:
            graph = fin.filter_graph(finish=finish if isinstance(finish, dict) else None)
            subprocess.run([FFMPEG, "-v", "error", "-y", *src, "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264", "-crf", str(crf),
                            "-preset", "slow", *fin.encode_args(), "-movflags", "+faststart", str(tmp)], check=True, timeout=3600)
        else:
            subprocess.run([FFMPEG, "-v", "error", "-y", *src, "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264",
                            "-crf", str(crf), "-preset", "slow", *fin.encode_args(), "-movflags", "+faststart", str(tmp)], check=True, timeout=3600)
        from .media import probe
        got = int(next(x for x in probe(tmp)["streams"] if x["codec_type"] == "video").get("nb_frames") or 0)
        if frames and got and got != frames:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"encode of {job.name} wrote {got} of {frames} frames")
        tmp.replace(out)
    return str(out)


def label_layers(tracks, start_frame, labels, width=1920, height=1080, z=640, role="label", color="#f4ead8", typography=None, safe=.03):
    """Labels for a rendered 3D clip, drawn by the film over it (crisp type, editable text) and moved with the place they
    name: tracks.json from a template (each place's screen position every frame and whether the ground hides it) becomes
    x/y keyframes on a text layer beside the point: `side` above (default: bottom centre on the point), below, left or
    right, or auto (the side that stays inside the frame longest). labels: [{"id", "text", "at", "until"?, "side"?, "pin"?}] with frames local to the clip; pin draws a dot on the
    place and a leader to the words (use it instead of the template's 3D stems, so a pin never stands without its label). A label shows from `at` while
    its place stays on screen and unhidden, fading in and out; one never visible after `at` is reported, not drawn.
    typography: the role's {font_id, size, weight, tracking} from the project's design, so the box is measured on the
    real face and the words stay on one line (an estimate wrapped "Mường Thanh" in two). Returns {"ops", "shown",
    "skipped"}."""
    import math
    tr = json.loads(Path(tracks).read_text(encoding="utf-8")) if not isinstance(tracks, dict) else tracks
    ops, shown, skipped = [], [], []
    for lb in labels:
        rows = tr["tracks"].get(lb["id"])
        if not rows:
            skipped.append({"id": lb["id"], "why": "no track"})
            continue
        end = lb.get("until", len(rows))
        if typography is None:
            from . import style
            typography = style.typography(role)  # the series bible's type for this role
        ty = typography
        from .design_library import fit_width
        bw = fit_width(ty["font_id"], lb["text"], ty["size"], width, ty.get("weight", 400), tracking=ty.get("tracking", 0)) + .01
        bh = ty["size"] * ty.get("line_height", 1.3) * 1.25 / height
        lift = lb.get("lift", .012)
        offsets = {"above": (-bw / 2, -bh - lift), "below": (-bw / 2, lift), "left": (-bw - lift * .6, -bh / 2), "right": (lift * .6, -bh / 2)}
        m_ = safe  # the whole label inside the safe area, not just its point (round 13 showcase: labels cut by the frame edge)

        def first_run(sd):  # the first stretch from `at` on which the place is visible and the label, on side sd, fits the frame
            ox_, oy_ = offsets[sd]
            out = []
            for f, x, y, vis in rows[lb.get("at", 0):end]:
                if vis and m_ <= x + ox_ and x + ox_ + bw <= 1 - m_ and m_ <= y + oy_ and y + oy_ + bh <= 1 - m_:
                    out.append((f, x, y))
                elif out:
                    break
            return out
        # side "auto": the side on which the label stays readable longest (a place near the frame edge keeps its name
        # on the side facing in)
        sides = ["above", "right", "left", "below"] if lb.get("side", "above") == "auto" else [lb.get("side", "above")]
        side, run = max(((sd, first_run(sd)) for sd in sides), key=lambda t_: (len(t_[1]), -sides.index(t_[0])))
        ox, oy = offsets[side]
        if len(run) < 24:
            skipped.append({"id": lb["id"], "why": f"visible and inside the frame {len(run)} frames after frame {lb.get('at', 0)}"})
            continue
        f0, f1 = run[0][0], run[-1][0] + 1
        x0, y0 = run[0][1] * width, run[0][2] * height
        keys = []
        step = max(1, math.ceil(len(run) / 99))
        for i, (f, x, y) in enumerate(run):
            if i % step == 0 or i == len(run) - 1:
                keys.append((f - f0, round(x * width - x0, 1), round(y * height - y0, 1)))
        lid = f"{lb.get('prefix', 'lab3d')}-{lb['id']}"
        d = f1 - f0
        fade = min(10, d // 4)
        ops.append({"op": "upsert_layer", "layer": {
            "id": lid, "kind": "text", "text": lb["text"], "start_frame": start_frame + f0, "end_frame": start_frame + f1,
            "x": round(run[0][1] + ox, 4), "y": round(run[0][2] + oy, 4), "width": round(bw, 4), "height": round(bh, 4),
            "z": z, "typography_role": role, "color": lb.get("color", color),
            "data": {"align": {"left": "right", "right": "left"}.get(side, "center")},
            "keyframes": {"x": [{"frame": k, "value": x, "easing": "linear"} for k, x, _ in keys],
                          "y": [{"frame": k, "value": y, "easing": "linear"} for k, _, y in keys]},
            "effects": [{"name": "fade_in", "start_frame": 0, "end_frame": fade}, {"name": "fade_out", "start_frame": d - fade, "end_frame": d - 1},
                        {"name": "text_outline", "start_frame": 0, "end_frame": 1, "params": {"amount": 2, "color": "#0b0b0b"}},
                        {"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 12}}]}})
        if lb.get("pin"):  # a dot on the place and a leader up to the words, drawn with them: no pin is ever left without its label
            kf = ops[-1]["layer"]["keyframes"]
            px, py = run[0][1], run[0][2]
            fx_ = [{"name": "fade_in", "start_frame": 0, "end_frame": fade}, {"name": "fade_out", "start_frame": d - fade, "end_frame": d - 1}]
            dot = 12
            lead = max(0.0, (lift if side == "above" else 0) * height - 2)
            for sid, x_, y_, w_, h_, col, r_ in (("dot", px - dot / 2 / width, py - dot / 2 / height, dot / width, dot / height, lb.get("pin_color", "#ffd48a"), dot / 2),
                                                 ("lead", px - 1 / width, py - lead / height, 2 / width, lead / height, lb.get("color", color), 0)):
                if h_ <= 0:
                    continue
                ops.append({"op": "upsert_layer", "layer": {
                    "id": f"{lid}-{sid}", "kind": "shape", "start_frame": start_frame + f0, "end_frame": start_frame + f1, "x": round(x_, 5), "y": round(y_, 5),
                    "width": round(w_, 5), "height": round(h_, 5), "z": z - 1, "color": col, "data": {"shape": "rectangle", "corner_radius": r_},
                    "keyframes": kf, "effects": fx_ + [{"name": "shadow", "start_frame": 0, "end_frame": 1, "params": {"amount": 6}}]}})
        shown.append({"id": lb["id"], "frames": [start_frame + f0, start_frame + f1]})
    return {"ops": ops, "shown": shown, "skipped": skipped}
