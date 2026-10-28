"""Persistent, process-isolated media work; survives closure of the MCP client."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from . import store
from .media import Cancelled

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
HEAVY_KINDS = {"subject", "mask_edit", "depth", "delivery", "blender"}  # local LTX takes the GPU slot itself (cloud providers need none)


def heavy_admission(task_id):
    """One heavy GPU/media worker at a time (store.acquire_gpu); polls cancellation while waiting."""
    update(task_id,message="Waiting for shared media/render slot")
    return store.acquire_gpu(lambda: cancelled(task_id))


def initialize():
    with store.connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS media_tasks (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, request TEXT NOT NULL,
          state TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL,
          result TEXT, error TEXT, owner_pid INTEGER, cancel INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")


def folder(task_id):
    uuid.UUID(task_id)
    return store.DATA / "media-tasks" / task_id


def get(task_id):
    uuid.UUID(task_id)
    initialize()
    with store.connection() as db:
        row = db.execute("SELECT * FROM media_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("Media task not found")
        r = dict(row)
        if r["state"] not in TERMINAL and r["owner_pid"] and not store.process_alive(r["owner_pid"]):
            r["state"] = "cancelled" if r["cancel"] else "interrupted"
            db.execute("UPDATE media_tasks SET state=?,message='Worker stopped',updated_at=? WHERE id=?", (r["state"],store.now(),task_id))
    r["request"] = json.loads(r["request"])
    r["result"] = json.loads(r["result"]) if r["result"] else None
    r["log_path"] = str(folder(task_id)/"worker.log")
    return r


def update(task_id, state="running", progress=0, message="", result=None, error=None):
    with store.connection() as db:
        db.execute("UPDATE media_tasks SET state=?,progress=?,message=?,result=?,error=?,updated_at=? WHERE id=?",
                   (state,progress,message,json.dumps(result,ensure_ascii=False) if result is not None else None,error,store.now(),task_id))


def cancelled(task_id):
    with store.connection() as db:
        r = db.execute("SELECT cancel FROM media_tasks WHERE id=?",(task_id,)).fetchone()
    return bool(r and r[0])


def check(task_id):
    if cancelled(task_id):
        raise Cancelled()


def cancel(task_id):
    get(task_id)
    with store.connection() as db:
        db.execute("UPDATE media_tasks SET cancel=1,message='Cancellation requested',updated_at=? WHERE id=? AND state NOT IN ('completed','failed','cancelled','interrupted')",(store.now(),task_id))
    return get(task_id)


def _launch_windows(task_id, env):
    """WMI creates a hidden user process outside the stdio client's cleanup job.

    MCP's Windows client puts its server AND descendants in a kill-on-close
    Job Object. A plain Popen child therefore cannot outlive a closed session.
    This launches no service, scheduler entry or shell; worker logs itself.
    """
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    service=startup=process=args=result=None
    try:
        service=win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".","root\\cimv2")
        startup=service.Get("Win32_ProcessStartup").SpawnInstance_()
        startup.ShowWindow=0
        startup.CreateFlags=getattr(subprocess,"CREATE_NO_WINDOW",0)|getattr(subprocess,"CREATE_UNICODE_ENVIRONMENT",1024)
        startup.EnvironmentVariables=[key+"="+value for key,value in env.items()]
        process=service.Get("Win32_Process")
        args=process.Methods_("Create").InParameters.SpawnInstance_()
        args.CommandLine=subprocess.list2cmdline([sys.executable,"-m","editvideo.media_task_runner",task_id])
        args.CurrentDirectory=str(store.ROOT)
        args.ProcessStartupInformation=startup
        result=process.ExecMethod_("Create",args)
        if result.ReturnValue:
            raise RuntimeError(f"Windows media worker launch failed (WMI {result.ReturnValue})")
        return int(result.ProcessId)
    finally:
        result=args=process=startup=service=None
        pythoncom.CoUninitialize()


def submit(kind, request, launch=True):
    from .subjects import SubjectRequest, MaskEditRequest
    from .generation import GenerationRequest, validate_request
    from .color_pipeline import ColorRequest
    from .depth import DepthRequest,DepthEditRequest
    from .retime import RetimeRequest
    from .footage_pro import StabilizeRequest, ReframeRequest
    from .delivery import DeliveryRequest
    from .render3d import Render3DRequest
    validators = {"subject":SubjectRequest,"mask_edit":MaskEditRequest,"generate":GenerationRequest,'color':ColorRequest,'depth':DepthRequest,'depth_edit':DepthEditRequest,'retime':RetimeRequest,'stabilize':StabilizeRequest,'reframe':ReframeRequest,'delivery':DeliveryRequest,'blender':Render3DRequest}
    if kind not in validators:
        raise ValueError("Unknown media operation")
    body = validators[kind].model_validate(request).model_dump()
    from .code_engine import ensure_free
    ensure_free(store.DATA, 2.0)
    if kind == "generate":
        validate_request(body)
    if kind=='depth':
        from .depth import install
        install(False)
    task_id = str(uuid.uuid4())
    out = folder(task_id); out.mkdir(parents=True)
    if kind == 'delivery':
        from .delivery import prepare
        body = prepare(body, out)
    if kind == 'blender':
        from .render3d import prepare
        body = prepare(body, out)
    if kind=='color' and body.get('lut_path'):
        import shutil
        from .color_pipeline import read_cube
        read_cube(body['lut_path']);shutil.copyfile(body['lut_path'],out/'custom.cube');body['lut_path']=str(out/'custom.cube')
    if kind == "generate" and body["provider"] == "comfyui":
        from .generation import workflow_path
        store.write_json(out/"workflow.json",store.read_json(workflow_path(body["workflow"])))
    if kind == "generate":
        import shutil
        for key in ("reference_image","reference_mask"):
            if body.get(key):
                reference=Path(body[key]).resolve(strict=True)
                snapshot=out/(key+reference.suffix.lower())
                shutil.copyfile(reference,snapshot)
                body[key]=str(snapshot)
        for i,anchor in enumerate(body.get("reference_frames",[])):
            reference=Path(anchor["path"]).resolve(strict=True)
            snapshot=out/(f"reference-frame-{i:02}"+reference.suffix.lower())
            shutil.copyfile(reference,snapshot)
            anchor["path"]=str(snapshot)
    initialize()
    with store.connection() as db:
        db.execute("INSERT INTO media_tasks (id,kind,request,state,message,created_at,updated_at,owner_pid) VALUES (?,?,?,'queued','Queued',?,?,?)",(task_id,kind,json.dumps(body,ensure_ascii=False),store.now(),store.now(),os.getpid()))
    if launch:
        return launch_task(task_id)
    return get(task_id)


def launch_task(task_id):
    """Launch an already snapshotted queued task (e.g. generation refinement)."""
    if get(task_id)['state']!='queued':
        raise ValueError('Only queued media tasks can launch')
    out=folder(task_id)
    # Child needs its own explicit DATA root, including when caller is configured differently.
    tmp = store.DATA/"tmp"/task_id
    tmp.mkdir(parents=True, exist_ok=True)  # keep worker temp files on the data volume, not the (often full) system drive
    env = {**os.environ,"EDITVIDEO_DATA":str(store.DATA),"PYTHONUTF8":"1","TEMP":str(tmp),"TMP":str(tmp)}
    try:
        if os.name=="nt":
            owner_pid=_launch_windows(task_id,env)
        else:
            with (out/"worker.log").open("wb") as log:
                proc=subprocess.Popen([sys.executable,"-m","editvideo.media_task_runner",task_id],
                    cwd=store.ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            owner_pid=proc.pid
        with store.connection() as db:
            db.execute("UPDATE media_tasks SET owner_pid=? WHERE id=?",(owner_pid,task_id))
    except Exception:
        update(task_id,"failed",message="Could not start media worker",error="Worker launch failed")
        raise
    return get(task_id)


def run(task_id):
    from .subjects import segment, edit_mask
    from .generation import generate
    from .color_pipeline import process as color_process
    from .depth import estimate as depth_estimate,edit as depth_edit
    from .retime import process as retime_process
    from .footage_pro import stabilize as stabilize_process, reframe as reframe_process
    from .delivery import process as delivery_process
    from .render3d import process as blender_process
    r = get(task_id)
    if r["state"] in TERMINAL:
        return r
    with store.connection() as db:
        claimed=db.execute("UPDATE media_tasks SET state='running',owner_pid=?,updated_at=? WHERE id=? AND state='queued'",(os.getpid(),store.now(),task_id))
        acquired=claimed.rowcount==1
    if not acquired:
        return get(task_id)
    try:
        check(task_id)
        update(task_id,message="Preparing media")
        fn = {"subject":segment,"mask_edit":edit_mask,"generate":generate,'color':color_process,'depth':depth_estimate,'depth_edit':depth_edit,'retime':retime_process,'stabilize':stabilize_process,'reframe':reframe_process,'delivery':delivery_process,'blender':blender_process}[r["kind"]]
        # Torch-backed kinds import multi-GB runtimes inside fn. Queue them here first so waiting
        # workers do not each hold Torch commit memory while blocked on the GPU lock.
        admission=heavy_admission(task_id) if r["kind"] in HEAVY_KINDS else None
        try:
            if admission:update(task_id,message="Preparing media")
            result = fn(task_id,r["request"])
        finally:
            if admission:admission.release()
        check(task_id)
        update(task_id,"completed",1,"Media ready",result=result)
    except Cancelled:
        update(task_id,"cancelled",message="Cancelled; partial files are not published")
    except Exception as ex:
        message = str(ex)
        for name in ("EDITVIDEO_RUNWAY_API_KEY", "EDITVIDEO_COMFY_API_KEY"):
            if os.environ.get(name):
                message = message.replace(os.environ[name],"[redacted]")
        update(task_id,"failed",message="Media operation failed",error=message[-3000:])
    return get(task_id)


def attach(task_id, project_id, base_revision, output="video", tags="", role="reconstruction"):
    """Attach an immutable result without changing locked narration or timeline."""
    import shutil
    from .media import register
    if role not in ("illustration","evidence","metaphor","reconstruction","decoration"):
        raise ValueError("Invalid media role")
    r = get(task_id)
    if r["state"] != "completed":
        raise ValueError("Only completed media can be attached")
    files = r["result"].get("artifacts",{})
    if output not in files:
        raise ValueError(f"Choose artifact from {list(files)}")
    src = Path(files[output]).resolve(strict=True)
    if not src.is_relative_to(folder(task_id).resolve()):
        raise ValueError("Artifact outside task folder")
    return attach_file(src,project_id,base_revision,tags,role,{"media_task_id":task_id,"operation":r["kind"],"request":r["request"]})


def attach_file(src,project_id,base_revision,tags="",role="illustration",provenance=None):
    """Share the revision-checked import transaction with completed task results."""
    import shutil
    from .media import register
    src=Path(src).resolve(strict=True)
    if role not in ("illustration","evidence","metaphor","reconstruction","decoration"):
        raise ValueError("Invalid media role")
    if (store.get_project(project_id) or {}).get("revision")!=base_revision:  # before a working copy's encode, not after it
        raise ValueError("Revision conflict; read project again")
    from .media import working_copy
    name=src.name  # the asset keeps the original's name, not the cache file's
    src,origin=working_copy(src)  # archival TIFF / oversized scans, rotated or anamorphic pictures: a working copy, provenance on the original
    if origin and provenance is None:provenance={"operation":"import working copy","source_sha256":origin}
    if not src.is_file() or src.stat().st_size>500*1024*1024:raise ValueError("Media file must be <=500MB")
    target = store.folder(project_id)/"assets"/(str(uuid.uuid4())+src.suffix)
    target.parent.mkdir(exist_ok=True)
    from .code_engine import place_file
    place_file(src,target)  # task artifacts are immutable results: hardlink instead of a second copy
    old=None;mp=None;meta_written=False
    try:
        # Probe once without inserting. Registration returns its metadata.
        meta = register(project_id,target,name,tags,role,persist=False)
        meta["provenance"] = provenance or {"operation":"import","source_sha256":meta["sha256"]}
        plan = store.folder(project_id)/"plan"; mp = plan/"plan-meta.json"
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            p = db.execute("SELECT revision FROM projects WHERE id=?",(project_id,)).fetchone()
            if not p or p[0] != base_revision:
                raise ValueError("Revision conflict; read project again")
            if store.busy(db,project_id):
                raise ValueError("Project render is running")
            old = store.read_json(mp) if mp.exists() else None
            db.execute("INSERT INTO assets VALUES (?,?,?)",(meta["id"],project_id,json.dumps(meta,ensure_ascii=False)))
            db.execute("UPDATE projects SET revision=revision+1,updated_at=? WHERE id=?",(store.now(),project_id))
            if old and old["revision"] == base_revision:
                store.write_json(mp,{**old,"revision":base_revision+1})
                meta_written=True
        return {"asset":meta,"revision":base_revision+1,"plan_preserved":bool(old and old["revision"]==base_revision)}
    except Exception:
        if meta_written and old is not None and mp is not None:
            store.write_json(mp,old)
        target.unlink(missing_ok=True);target.with_suffix(".thumb.jpg").unlink(missing_ok=True)
        raise
