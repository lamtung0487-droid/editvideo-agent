import queue
import shutil
import threading
import traceback
import os
from pathlib import Path
from . import store
from .audio import prepare_audio
from .media import Cancelled, sha256
from .models import Timeline
from .planner import plan
from .renderer import render


class Worker:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self.loop, name="editvideo-render", daemon=True)

    def start(self):
        if not self.thread.is_alive() and self.thread.ident is None:  # idempotent: a second start is a no-op
            self.thread.start()

    def submit(self,job):
        self.queue.put(job["id"])

    def stop(self):
        with store.connection() as db:
            owned=[r["id"] for r in db.execute("SELECT id FROM jobs WHERE owner_pid=? AND state IN ('queued','running','cancelling')",(os.getpid(),))]
        for jid in owned:
            store.cancel(jid)
        self.queue.put(None)
        if self.thread.is_alive():
            self.thread.join(timeout=10)

    def loop(self):
        while True:
            jid = self.queue.get()
            if jid is None:
                self.queue.task_done()
                return
            try:
                self.run(jid)
            except Exception as e:  # never let one job kill the worker thread (later jobs would sit 'queued' forever)
                try:
                    store.job_progress(jid,"failed",message="Tác vụ chưa hoàn thành",error=(traceback.format_exc() or str(e))[-4000:])
                except Exception:
                    pass
            finally:
                self.queue.task_done()

    def run(self,jid):
        job = store.get_job(jid)
        pid = job["project_id"]
        work = store.folder(pid)/"jobs"/jid
        work.mkdir(parents=True,exist_ok=True)
        def cancelled():
            return store.get_job(jid)["state"] in ("cancelled","cancelling")
        def progress(n,message):
            if cancelled():
                raise Cancelled()
            store.job_progress(jid,progress=n,message=message)
        try:
            progress(1,"Đang chuẩn bị")
            project = store.get_project(pid)
            if project["revision"] != job["revision"]:
                raise ValueError("Dự án đã thay đổi. Hãy chạy lại tác vụ.")
            config = project["config"]
            plan_dir = store.folder(pid)/"plan"
            if job["kind"] == "plan":
                if not config["script"].strip():
                    raise ValueError("Hãy nhập kịch bản trước khi lập cảnh")
                voice,cues,method = prepare_audio(pid,config,work,cancelled,progress)
                timeline,note = plan(config,voice,cues,method,store.assets(pid),progress)
                store.write_json(work/"timeline.json",timeline.model_dump())
                meta = {"revision":job["revision"],"timeline_hash":sha256(work/"timeline.json"),
                        "audio_hash":sha256(voice),"planner":note,"job_id":jid}
                store.write_json(work/"plan-meta.json",meta)
                # Publish only after the entire plan succeeds; keep the previous one on failure.
                if cancelled():
                    raise Cancelled()
                plan_dir.mkdir(exist_ok=True)
                for name in ("voice.wav","words.json","timeline.json","plan-meta.json","voice-backend.json"):
                    if name == "voice-backend.json" and not (work/name).exists():
                        (plan_dir/name).unlink(missing_ok=True)  # an uploaded narration: no synthetic voice to credit
                        continue
                    temp = plan_dir/(name + ".tmp")
                    shutil.copyfile(work/name,temp)
                    temp.replace(plan_dir/name)
                store.job_progress(jid,"completed",100,"Đã lập cảnh. Có thể chỉnh hoặc xuất video.")
            else:
                if not (plan_dir/"plan-meta.json").exists():
                    raise ValueError("Hãy lập cảnh trước khi xuất video")
                meta = store.read_json(plan_dir/"plan-meta.json")
                if meta["revision"] != job["revision"]:
                    raise ValueError("Dự án hoặc tư liệu đã đổi. Hãy lập cảnh lại.")
                if sha256(plan_dir/"voice.wav") != meta["audio_hash"] or sha256(plan_dir/"timeline.json") != meta["timeline_hash"]:
                    raise ValueError("File kế hoạch đã thay đổi ngoài ứng dụng. Hãy lập lại cảnh.")
                for name in ("voice.wav","words.json","timeline.json"):
                    shutil.copyfile(plan_dir/name,work/name)
                from . import narrative
                meaning,meaning_status=narrative.document(pid,store.read_json(work/'timeline.json'))
                if meaning_status=='ready':store.write_json(work/'meaning.json',meaning)
                timeline = Timeline.model_validate(store.read_json(work/"timeline.json"))
                renderer = render
                if config.get("renderer", "ffmpeg") != "ffmpeg":
                    from .code_engine import render as renderer
                elif timeline.overlays or timeline.layers or any(s.effects or s.keyframes or s.transition or s.playback_rate!=1 for s in timeline.shots):
                    raise ValueError("Advanced composition requires Remotion or Hyperframes renderer")
                progress(5,"Waiting for shared media/render slot")
                admission = store.acquire_gpu(cancelled, "film render")
                try:
                    final,report = renderer(pid,timeline,config,work,job["kind"],cancelled,progress)
                finally:
                    admission.release()
                if cancelled():
                    raise Cancelled()
                store.write_json(work/"output.json",{"video":final.name,"revision":job["revision"],"report":report})
                store.job_progress(jid,"completed",100,"Video đã sẵn sàng")
        except Cancelled:
            store.finish_cancel(jid)
        except Exception as e:
            (work/"error.log").write_text(traceback.format_exc(),encoding="utf-8")
            store.job_progress(jid,"failed",message="Tác vụ chưa hoàn thành",error=str(e)[-4000:])
