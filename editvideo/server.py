import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from . import store
from .jobs import Worker
from .media import probe, register, sha256, safe_asset_path, FFMPEG, FFPROBE
from .models import ProjectInput, TimelineUpdate
from .planner import validate_sources
from .audio import parse_srt

worker = Worker()


@asynccontextmanager
async def lifespan(app):
    global worker
    store.initialize(recover=False)
    worker = Worker()
    worker.start()
    yield


app = FastAPI(title="EditVideo Studio",lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","testserver"])


@app.middleware("http")
async def local_requests(request: Request,call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET","HEAD","OPTIONS") and origin:
        o = urlparse(origin)
        if o.netloc != request.headers.get("host") or o.scheme not in ("http","https"):
            return JSONResponse({"detail":"Chỉ nhận thao tác từ giao diện local"},status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error(request,exc):
    return JSONResponse({"detail":str(exc)},status_code=409)


@app.exception_handler(KeyError)
async def missing(request,exc):
    return JSONResponse({"detail":str(exc)},status_code=404)


@app.exception_handler(RuntimeError)
async def media_error(request,exc):
    return JSONResponse({"detail":"Không đọc được media: " + str(exc)[-1500:]},status_code=422)


@app.exception_handler(httpx.HTTPError)
async def provider_error(request,exc):
    return JSONResponse({"detail":"Không kết nối được nguồn tư liệu. Kiểm tra khóa API, hạn mức và Internet."},status_code=502)


def public_asset(a):
    return {k:v for k,v in a.items() if k not in ("path","thumbnail")}


def check_audio_ids(pid,config):
    for key in ("narration_id","music_id"):
        if config.get(key):
            asset = store.find_asset(pid,config[key])
            if asset["kind"] != "audio":
                raise ValueError("Giọng đọc và nhạc nền phải là file âm thanh")


@app.get("/api/health")
def health():
    import shutil
    return {"ok":True,"ffmpeg":bool(shutil.which(FFMPEG)),"ffprobe":bool(shutil.which(FFPROBE)),
            "planner_ai":bool(os.environ.get("EDITVIDEO_LLM_API_KEY") and os.environ.get("EDITVIDEO_LLM_MODEL") and os.environ.get("EDITVIDEO_LLM_BASE_URL")),
            "pexels":bool(os.environ.get("PEXELS_API_KEY")),"version":__import__("editvideo").__version__}


@app.get("/api/projects")
def projects():
    return store.list_projects()


@app.post("/api/projects")
def create(config:ProjectInput):
    if config.narration_id or config.music_id:
        raise ValueError("Tạo dự án rồi tải audio lên trước")
    return store.create_project(config.model_dump())


@app.get("/api/projects/{pid}")
def get(pid:str):
    project = store.get_project(pid)
    project["assets"] = [public_asset(a) for a in store.assets(pid)]
    project["jobs"] = store.jobs(pid)
    plan = store.folder(pid)/"plan"
    if (plan/"timeline.json").exists() and (plan/"plan-meta.json").exists():
        project["timeline"] = store.read_json(plan/"timeline.json")
        project["plan_meta"] = store.read_json(plan/"plan-meta.json")
        project["plan_current"] = project["plan_meta"]["revision"] == project["revision"]
    else:
        project["timeline"] = None
        project["plan_current"] = False
    project["has_srt"] = (store.folder(pid)/"captions-input.srt").exists()
    return project


@app.put("/api/projects/{pid}")
def update(pid:str,config:ProjectInput):
    check_audio_ids(pid,config.model_dump())
    return store.update_project(pid,config.model_dump())


ALLOWED = {".png",".jpg",".jpeg",".webp",".mp4",".mov",".mkv",".webm",".wav",".mp3",".m4a",".aac",".flac",".ogg"}


@app.post("/api/projects/{pid}/assets")
async def upload(pid:str,file:UploadFile=File(...),tags:str=Form("")):
    store.get_project(pid)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("Định dạng file chưa hỗ trợ")
    dest = store.folder(pid)/"assets"/(str(uuid.uuid4())+ext)
    dest.parent.mkdir(exist_ok=True)
    try:
        size = 0
        with dest.open("wb") as f:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > 500*1024*1024:
                    raise ValueError("File vượt 500 MB")
                f.write(chunk)
        return public_asset(register(pid,dest,Path(file.filename or dest.name).name,tags[:1000]))
    except Exception:
        dest.unlink(missing_ok=True)
        dest.with_suffix(".thumb.jpg").unlink(missing_ok=True)
        raise
    finally:
        await file.close()


class AssetLabels(BaseModel):
    tags:str=Field(max_length=1000)
    role:Literal["illustration","evidence","metaphor","reconstruction","decoration"]="illustration"


@app.patch("/api/projects/{pid}/assets/{aid}")
def labels(pid:str,aid:str,body:AssetLabels):
    return public_asset(store.update_asset(pid,aid,body.model_dump()))


@app.get("/api/projects/{pid}/assets/{aid}/file")
def asset_file(pid:str,aid:str,thumbnail:bool=False):
    a = store.find_asset(pid,aid)
    path = Path(a["thumbnail"]) if thumbnail and a.get("thumbnail") else safe_asset_path(pid,aid)
    return FileResponse(path)


@app.post("/api/projects/{pid}/captions")
async def captions(pid:str,file:UploadFile=File(...)):
    store.get_project(pid)
    raw = await file.read(1024*1024+1)
    await file.close()
    if len(raw)>1024*1024:
        raise ValueError("SRT vượt 1 MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("SRT phải dùng mã UTF-8")
    cues = parse_srt(content)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.busy(db,pid):
            raise ValueError("Tác vụ đang chạy")
        (store.folder(pid)/"captions-input.srt").write_text(content,encoding="utf-8")
        db.execute("UPDATE projects SET revision=revision+1, updated_at=? WHERE id=?",(store.now(),pid))
    return {"cues":len(cues)}


@app.delete("/api/projects/{pid}/captions")
def clear_captions(pid:str):
    store.get_project(pid)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.busy(db,pid):
            raise ValueError("Tác vụ đang chạy")
        (store.folder(pid)/"captions-input.srt").unlink(missing_ok=True)
        db.execute("UPDATE projects SET revision=revision+1, updated_at=? WHERE id=?",(store.now(),pid))
    return {"ok":True}


@app.put("/api/projects/{pid}/timeline")
def update_timeline(pid:str,body:TimelineUpdate):
    library = store.assets(pid)
    validate_sources(pid,body.timeline,library)
    plan = store.folder(pid)/"plan"
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.busy(db,pid):
            raise ValueError("Tác vụ đang chạy")
        row = db.execute("SELECT revision FROM projects WHERE id=?",(pid,)).fetchone()
        if not row:
            raise KeyError("Không tìm thấy dự án")
        if row["revision"] != body.base_revision:
            raise ValueError("Dự án đã đổi ở cửa sổ khác. Hãy tải lại trước khi lưu timeline.")
        if not (plan/"plan-meta.json").exists():
            raise ValueError("Hãy lập cảnh trước")
        meta = store.read_json(plan/"plan-meta.json")
        old = store.read_json(plan/"timeline.json")
        if meta["revision"] != row["revision"]:
            raise ValueError("Kế hoạch cũ; hãy lập cảnh lại sau khi đổi đầu vào")
        if body.timeline.audio_samples != old["audio_samples"] or (body.timeline.width,body.timeline.height)!=(old["width"],old["height"]):
            raise ValueError("Đổi giọng hoặc kích thước phải lập cảnh lại")
        store.write_json(plan/"timeline.json",body.timeline.model_dump())
        meta.update(revision=row["revision"]+1,timeline_hash=sha256(plan/"timeline.json"))
        store.write_json(plan/"plan-meta.json",meta)
        db.execute("UPDATE projects SET revision=revision+1, updated_at=? WHERE id=?",(store.now(),pid))
    return get(pid)


@app.get("/api/projects/{pid}/voice")
def voice(pid:str):
    store.get_project(pid)
    path = store.folder(pid)/"plan"/"voice.wav"
    if not path.exists():
        raise KeyError("Chưa có giọng đọc")
    return FileResponse(path)


class JobRequest(BaseModel):
    kind:Literal["plan","preview","final"]


@app.post("/api/projects/{pid}/jobs")
def submit(pid:str,body:JobRequest):
    project = get(pid)
    check_audio_ids(pid,project["config"])
    if body.kind != "plan" and not project["plan_current"]:
        raise ValueError("Hãy lập cảnh cho phiên bản dự án hiện tại")
    job = store.create_job(pid,body.kind)
    worker.submit(job)
    return job


@app.get("/api/jobs/{jid}")
def job(jid:str):
    return store.get_job(jid)


@app.post("/api/jobs/{jid}/cancel")
def cancel(jid:str):
    store.get_job(jid)
    store.cancel(jid)
    return store.get_job(jid)


@app.get("/api/projects/{pid}/jobs/{jid}/{filename}")
def output(pid:str,jid:str,filename:str):
    job = store.get_job(jid)
    if job["project_id"] != pid:
        raise KeyError("File không thuộc dự án")
    if filename not in {"final.mp4","preview.mp4","delivery.zip","timeline.json","captions.srt","storyboard.jpg","technical.json","render.log","error.log"}:
        raise KeyError("File không được cung cấp")
    path = store.folder(pid)/"jobs"/jid/filename
    if not path.is_file() or (filename in {"final.mp4","preview.mp4","delivery.zip"} and job["state"] != "completed"):
        raise KeyError("File chưa sẵn sàng")
    return FileResponse(path,filename=filename if filename.endswith((".zip",".srt",".json",".log")) else None)


@app.get("/api/stock")
def stock_search(query:str):
    from .stock import search
    if not query.strip() or len(query)>200:
        raise ValueError("Nhập từ khóa từ 1 đến 200 ký tự")
    return search(query)


class StockImport(BaseModel):
    photo_id:int=Field(gt=0)
    tags:str=Field(default="",max_length=1000)


@app.post("/api/projects/{pid}/stock")
def stock_import(pid:str,body:StockImport):
    from .stock import import_photo
    store.get_project(pid)
    return public_asset(import_photo(pid,body.photo_id,body.tags))


app.mount("/",StaticFiles(directory=store.ROOT/"web",html=True),name="studio")
