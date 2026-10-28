import shutil
import uuid
from . import store
from .code_engine import ENGINES,engine_env,refresh_payload,ensure_free,fit_tracking
from .media import command,sha256

READY_TIMEOUT_MS=60000  # how long a HyperFrames snapshot waits for its page to be ready; a ready page goes on at once


def snapshot(pid,engine,frames,timeline_variant=None):
    """timeline_variant: internal evidence renders (e.g. one layer isolated) of the current plan; never persisted."""
    if engine not in ("remotion","hyperframes") or not frames or len(frames)>8:
        raise ValueError("engine remotion|hyperframes; 1..8 integer frames")
    project=store.get_project(pid)
    plan=store.folder(pid)/"plan"
    meta=store.read_json(plan/"plan-meta.json")
    timeline=store.read_json(plan/"timeline.json")
    if timeline_variant is not None:
        if engine!="remotion":
            raise ValueError("Isolated evidence renders use the remotion runtime")
        timeline=timeline_variant
    if meta["revision"]!=project["revision"]:
        raise ValueError("Plan stale; replan first")
    if any(not isinstance(f,int) or f<0 or f>=timeline["total_frames"] for f in frames):
        raise ValueError("Frame outside timeline")
    source=store.folder(pid)/"code"/engine
    source_meta=store.read_json(source/"source-meta.json")
    authored_timeline=store.read_json(source/"input.json")["timeline"]
    if engine=="hyperframes" and any(authored_timeline.get(k)!=timeline[k] for k in ("width","height","total_frames","fps")):
        raise ValueError("Hyperframes root timebase/profile changed; preserve custom source and export again")
    if source_meta.get("runtime_version",1)<2 and source_meta["timeline_hash"]!=meta["timeline_hash"]:
        raise ValueError("Timeline changed; export code again")
    ensure_free(store.DATA, 1.0)
    work=store.DATA/"observations"/str(uuid.uuid4())
    work.mkdir(parents=True)
    render_temp=store.engine_temp()  # short: the browser profile below it stays under Windows' 260-character limit
    render_env={**engine_env(pid),'TEMP':str(render_temp),'TMP':str(render_temp)}
    copied=work/"source"
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.get_project(pid)["revision"]!=project["revision"]:
            raise ValueError("Revision conflict")
        from .code_engine import link_media_copy
        shutil.copytree(source,copied,copy_function=link_media_copy)  # media hardlinked: an evidence render must not duplicate GBs
    if source_meta.get("runtime_version",1)>=2:
        refresh_payload(pid,copied,timeline,project["config"])
    if engine=="remotion":
        payload=store.read_json(copied/"input.json")
        # refresh_payload wrote the render timeline (off-speed shots on their pre-timed clips); older exports get the project's
        payload.update(config=project["config"],**({} if source_meta.get("runtime_version",1)>=2 else {"timeline":fit_tracking(timeline)}))
        store.write_json(copied/"input.json",payload)
        # One process for all frames: bundle (cached per project/code version) once, then render each still.
        try:
            command(["node",ENGINES/"render-remotion.mjs",copied,work,"preview",",".join(str(f) for f in frames)],cwd=ENGINES,
                    log=work/"snapshot.log",env=render_env,timeout=120+60*len(frames))
        finally:
            # Remotion downloads every video it decodes into this run's own temp folder; drop the run's temp copies.
            shutil.rmtree(render_temp,ignore_errors=True)
        paths=[]
        for frame in frames:
            output=work/f"frame-{frame:06}.png"
            paths.append({"frame":frame,"timestamp":frame/30,"path":str(output),"sha256":sha256(output)})
    else:
        payload=store.read_json(copied/"input.json")
        if any(payload["config"].get(k)!=project["config"].get(k) for k in ("title","captions")):
            raise ValueError("Hyperframes visual settings changed; export code again")
        try:
            # --timeout: the page is ready once hyper-runtime.js has built its timeline. The CLI's 5 s default was shorter
            # than a 104-shot film's build, and its first seek captured an empty (black) page.
            command(["node",ENGINES/"node_modules"/"hyperframes"/"bin"/"hyperframes.mjs","snapshot",copied,
                     "--at",",".join(str(f/30) for f in frames),"--no-end","--describe","false","--timeout",str(READY_TIMEOUT_MS),
                     "--output",work/"frames"],cwd=ENGINES,env=render_env,log=work/"snapshot.log",timeout=240)
        finally:
            shutil.rmtree(render_temp,ignore_errors=True)
        if "did not become render-ready" in (work/"snapshot.log").read_text(encoding="utf-8",errors="replace"):
            raise ValueError(f"HyperFrames page not ready within {READY_TIMEOUT_MS//1000} s, so its frames would not show "
                             "the timeline; inspect snapshot.log")
        files=sorted((work/"frames").glob("*.png"))
        if len(files)!=len(frames):
            raise ValueError("Snapshot did not return all requested frames; inspect snapshot.log")
        from PIL import Image
        for path in files:  # portrait/square pages carry a capture margin on the right (code_engine.capture_margin)
            with Image.open(path) as im:
                if im.width>timeline["width"]:
                    im.crop((0,0,timeline["width"],timeline["height"])).save(path)
        paths=[{"frame":frame,"timestamp":frame/30,"path":str(path),"sha256":sha256(path)}
               for frame,path in zip(frames,files)]
    result={"engine":engine,"revision":project["revision"],"frames":paths,"source":str(copied)}
    store.write_json(work/"snapshot.json",result)
    return result
