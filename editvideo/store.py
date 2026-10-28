import json
import os
import sqlite3
import sys
import time
import uuid
import ctypes
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("EDITVIDEO_DATA", str(ROOT / "data"))).resolve()


SHARED_MODELS = ROOT / "data" / "models"  # the installation's models, found from a store on any drive


def models_root(probe=None):
    """Where installed models live: DATA/models, else the repository's data/models when `probe` (a model's folder or
    file name) is only there. Models belong to the installation; a project store on another drive (EDITVIDEO_DATA) must
    still find them (round 13: SigLIP, Whisper and Piper were reported missing with the store on G:)."""
    own = DATA / "models"
    if probe and not (own / probe).exists() and (SHARED_MODELS / probe).exists():
        return SHARED_MODELS
    return own


def now():
    return datetime.now(timezone.utc).isoformat()


def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "studio.db", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize(recover=True):
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, config TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, metadata TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
            kind TEXT NOT NULL, state TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
            message TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        """)
        columns = {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
        if "owner_pid" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN owner_pid INTEGER")
        if recover:
            # Recover only jobs whose process actually ended; preserve other clients.
            for job in db.execute("SELECT id,owner_pid FROM jobs WHERE state IN ('running','queued','cancelling')").fetchall():
                if not job["owner_pid"] or not process_alive(job["owner_pid"]):
                    db.execute("UPDATE jobs SET state='interrupted', message='Worker process stopped; resubmit job', updated_at=? WHERE id=?", (now(),job["id"]))


def folder(project_id):
    # IDs are generated internally; never accept paths here.
    uuid.UUID(project_id)
    p = DATA / "projects" / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def project(row):
    return {**dict(row), "config": json.loads(row["config"])}


def get_project(pid):
    with connection() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        raise KeyError("Không tìm thấy dự án")
    return project(row)


def list_projects():
    with connection() as db:
        return [project(r) for r in db.execute("SELECT * FROM projects ORDER BY updated_at DESC")]


def create_project(config):
    pid = str(uuid.uuid4())
    with connection() as db:
        db.execute("INSERT INTO projects VALUES (?,?,1,?,?)", (pid, json.dumps(config, ensure_ascii=False), now(), now()))
    folder(pid)
    return get_project(pid)


def busy(db, pid):
    # A closed/crashed stdio client must not strand a shared project forever.
    for job in db.execute("SELECT id,owner_pid FROM jobs WHERE project_id=? AND state IN ('queued','running','cancelling')",(pid,)).fetchall():
        if not job["owner_pid"] or not process_alive(job["owner_pid"]):
            db.execute("UPDATE jobs SET state='interrupted',message='Worker process stopped; resubmit job',updated_at=? WHERE id=?",(now(),job["id"]))
    return db.execute("SELECT id FROM jobs WHERE project_id=? AND state IN ('queued','running','cancelling')", (pid,)).fetchone()


import threading as _threading
_GPU = _threading.local()


class _GpuSlot:
    """The heavy-media slot held by this thread; release() gives it back (the outermost holder releases the file lock)."""
    def __init__(self, lock):
        self.lock, self.released = lock, False

    def release(self):
        if self.released or getattr(_GPU, "depth", 0) <= 0:  # twice would leave the next holder without the lock
            return
        self.released = True
        _GPU.depth -= 1
        if _GPU.depth == 0 and self.lock is not None:
            self.lock.release()


def gpu_holder():
    """Who holds the heavy slot ({"pid", "what", "since"}), or None: a waiting script can say what it waits for."""
    try:
        h = json.loads((DATA / "media-heavy.holder.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return h if h.get("pid") and process_alive(int(h["pid"])) else None


def acquire_gpu(cancelled=None, what="", wait_s=None):
    """The one heavy GPU/media slot across processes (film renders, Blender, MoGe, LTX, Torch tasks), polling
    cancellation while waiting; re-entrant in a thread that already holds it (a task that renders with Blender inside
    it must not wait for itself). Returns a slot to release(). A wait over 30 s is reported on stderr with the holder;
    wait_s raises TimeoutError instead of waiting longer."""
    from filelock import FileLock, Timeout
    if getattr(_GPU, "depth", 0):
        _GPU.depth += 1
        return _GpuSlot(None)
    lock = FileLock(str(DATA / "media-heavy.lock"))
    t0, told = time.monotonic(), False
    while True:
        if cancelled and cancelled():
            from .media import Cancelled
            raise Cancelled()
        try:
            lock.acquire(timeout=.5)
            break
        except Timeout:
            waited = time.monotonic() - t0
            if wait_s is not None and waited >= wait_s:
                raise TimeoutError(f"the GPU slot stayed busy for {wait_s:g} s (held by {gpu_holder() or 'an unknown process'})")
            if waited >= 30 and not told:  # an interactive caller would otherwise wait in silence behind a long render
                told = True
                print(f"[editvideo] {what or 'GPU work'} waits for the GPU slot, held by {gpu_holder() or 'an unknown process'}",
                      file=sys.stderr, flush=True)
    _GPU.depth = 1
    try:
        (DATA / "media-heavy.holder.json").write_text(json.dumps({"pid": os.getpid(), "what": what, "since": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                                                      encoding="utf-8")
    except OSError:
        pass
    return _GpuSlot(lock)


class gpu_admission:
    """`with store.gpu_admission(cancelled):` around any heavy GPU work (see acquire_gpu)."""
    def __init__(self, cancelled=None, what="", wait_s=None):
        self.cancelled, self.what, self.wait_s = cancelled, what, wait_s

    def __enter__(self):
        self.slot = acquire_gpu(self.cancelled, self.what, self.wait_s)
        return self.slot

    def __exit__(self, *exc):
        self.slot.release()


def process_alive(pid):
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        try:
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def update_project(pid, config, expected_revision=None):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if busy(db, pid):
            raise ValueError("Tác vụ đang chạy. Hãy hủy trước khi đổi dự án.")
        row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError("Không tìm thấy dự án")
        previous = json.loads(row["config"])
        if expected_revision is not None and row["revision"] != expected_revision:
            raise ValueError("Revision conflict; read project again")
        changes = {k for k in set(previous) | set(config) if previous.get(k) != config.get(k)}
        compatible = {"title", "music_id", "music_volume", "captions", "use_stock", "renderer"}
        meta_path = folder(pid)/"plan"/"plan-meta.json"
        if changes <= compatible and meta_path.exists():
            meta = read_json(meta_path)
            if meta["revision"] == row["revision"]:
                meta["revision"] = row["revision"] + 1
                write_json(meta_path, meta)
        db.execute("UPDATE projects SET config=?, revision=revision+1, updated_at=? WHERE id=?", (json.dumps(config, ensure_ascii=False), now(), pid))
    return get_project(pid)


def assets(pid):
    with connection() as db:
        return [json.loads(r["metadata"]) for r in db.execute("SELECT metadata FROM assets WHERE project_id=?", (pid,))]


def add_asset(pid, metadata, internal=False):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if busy(db, pid) and not internal:
            raise ValueError("Chờ tác vụ hoàn thành trước khi thêm tư liệu")
        db.execute("INSERT INTO assets VALUES (?,?,?)", (metadata["id"], pid, json.dumps(metadata, ensure_ascii=False)))
        if not internal:
            db.execute("UPDATE projects SET revision=revision+1, updated_at=? WHERE id=?", (now(), pid))


def find_asset(pid, aid):
    a = next((a for a in assets(pid) if a["id"] == aid), None)
    if not a:
        raise ValueError("Tư liệu không thuộc dự án hoặc đã bị xóa")
    return a


def update_asset(pid, aid, changes):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if busy(db, pid):
            raise ValueError("Chờ tác vụ hoàn thành trước khi sửa tư liệu")
        row = db.execute("SELECT metadata FROM assets WHERE id=? AND project_id=?", (aid, pid)).fetchone()
        if not row:
            raise KeyError("Không tìm thấy tư liệu")
        meta = json.loads(row["metadata"])
        meta.update(changes)
        db.execute("UPDATE assets SET metadata=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), aid))
        db.execute("UPDATE projects SET revision=revision+1, updated_at=? WHERE id=?", (now(), pid))
    return meta


def create_job(pid, kind):
    jid = str(uuid.uuid4())
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if busy(db, pid):
            raise ValueError("Dự án đã có tác vụ đang chạy")
        row = db.execute("SELECT revision FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError("Không tìm thấy dự án")
        db.execute("INSERT INTO jobs (id,project_id,revision,kind,state,progress,message,error,created_at,updated_at,owner_pid) VALUES (?,?,?,?,?,0,?,NULL,?,?,?)", (jid, pid, row["revision"], kind, "queued", "Đang xếp hàng", now(), now(),os.getpid()))
    return get_job(jid)


def get_job(jid):
    with connection() as db:
        r = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    if not r:
        raise KeyError("Không tìm thấy tác vụ")
    job = dict(r)
    if job["state"] in ("running", "queued", "cancelling") and job.get("owner_pid") and not process_alive(job["owner_pid"]):
        # A dead render can have finished the MP4 but stopped while writing credits/package. Require the actual
        # technical evidence and hash; file existence alone must never promote a partial encode to completed.
        recovered = False
        work = folder(job["project_id"]) / "jobs" / jid
        if job["state"] != "cancelling" and job["kind"] in ("final", "preview"):
            try:
                from .media import sha256, probe
                report = read_json(work / "technical.json")
                video = work / ("final.mp4" if job["kind"] == "final" else "preview.mp4")
                timeline = read_json(work / "timeline.json")
                stream = next(s for s in probe(video)["streams"] if s["codec_type"] == "video")
                recovered = bool(report.get("decoded") and report.get("sha256") == sha256(video)
                                 and int(stream.get("nb_frames", -1)) == timeline["total_frames"] == report["frames"])
                if recovered:
                    write_json(work / "output.json", {"video": video.name, "revision": job["revision"], "report": report,
                               "recovery": "Worker ended after verified video; package/credits may require completion"})
            except (OSError, ValueError, KeyError, StopIteration, RuntimeError):
                recovered = False
        state = "completed" if recovered else "cancelled" if job["state"] == "cancelling" else "interrupted"
        message = "Recovered verified video; check delivery package" if recovered else "Worker stopped; partial artifacts are not a completed render"
        with connection() as db:
            db.execute("UPDATE jobs SET state=?,progress=?,message=?,updated_at=? WHERE id=? AND state=? AND owner_pid=?",
                       (state, 100 if recovered else job["progress"], message, now(), jid, job["state"], job["owner_pid"]))
            fresh = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return dict(fresh)
    return job


def jobs(pid):
    with connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 20", (pid,))]


def job_progress(jid, state="running", progress=0, message="", error=None):
    with connection() as db:
        db.execute("UPDATE jobs SET state=?, progress=?, message=?, error=?, updated_at=? WHERE id=? AND state NOT IN ('cancelled','cancelling')", (state, progress, message, error, now(), jid))


def cancel(jid):
    with connection() as db:
        db.execute("UPDATE jobs SET state=CASE WHEN state='queued' THEN 'cancelled' ELSE 'cancelling' END, message='Đang hủy', updated_at=? WHERE id=? AND state IN ('queued','running')", (now(), jid))


def finish_cancel(jid):
    with connection() as db:
        db.execute("UPDATE jobs SET state='cancelled',message='Đã hủy',updated_at=? WHERE id=?",(now(),jid))


def atlas_path(name):
    """Library atlas JSON: the vendored copy in assets/previews (shipped, repo-relative paths) unless a fresh build in
    outputs/ is newer (atlas build scripts write there)."""
    vendored, built = ROOT / "assets" / "previews" / name, ROOT / "outputs" / name
    if built.exists() and (not vendored.exists() or built.stat().st_mtime > vendored.stat().st_mtime):
        return built
    return vendored


def repo_path(p):
    """Absolute path for a stored path that may be repo-relative (vendored previews)."""
    if not p:
        return p
    q = Path(p)
    return str(q if q.is_absolute() else ROOT / q)
