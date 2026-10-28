"""Cached-only local LTX-Video text/image generation, isolated from MCP lifetime."""
import importlib.util
import os
import sys
import time
from pathlib import Path
from . import store
from .media import command,sha256

MODEL="ltxv-2b-0.9.8-distilled.safetensors"

def root():return store.models_root("ltx")/"ltx"

def installation():
    manifest=store.models_root("temporal-models.json")/"temporal-models.json"
    return store.read_json(manifest).get("ltx",{}) if manifest.is_file() else {}

def verified_artifacts():
    data=installation()
    return {str(Path(r["path"]).resolve()):r for r in data.get("artifacts",[])}

def ready():
    names=[MODEL,"text_encoder/config.json","tokenizer/spiece.model","tokenizer/added_tokens.json","tokenizer/special_tokens_map.json","tokenizer/tokenizer_config.json","config/transformer/config.json","config/vae/config.json","config/scheduler/scheduler_config.json"]
    data=installation();records=verified_artifacts()
    text_names=["t5xxl_fp8_e4m3fn.safetensors"] if data.get("text_encoder_precision")=="fp8" else ["text_encoder/model.safetensors.index.json","text_encoder/model-00001-of-00002.safetensors","text_encoder/model-00002-of-00002.safetensors"]
    for name in names+text_names:
        path=root()/name;r=records.get(str(path.resolve()))
        if not path.is_file() or not r:return False
        stat=path.stat()
        if stat.st_size!=r["bytes"] or stat.st_mtime_ns!=r.get("mtime_ns"):return False
    return all(importlib.util.find_spec(n) for n in ("diffusers","transformers","accelerate"))

def run(task_id,req,out):
    from .subjects import gpu_lock
    from .media_tasks import cancelled,update
    if not ready():raise ValueError("Local LTX artifacts missing; install requirements.temporal.txt and run scripts/setup_temporal.py --backend ltx")
    store.write_json(out/"local-request.json",req.model_dump())
    slot=store.acquire_gpu(lambda:cancelled(task_id))  # never beside a film render or a Blender job
    lock=gpu_lock(task_id)
    try:
        update(task_id,progress=.02,message="Loading local LTX and text encoder")
        started=time.monotonic()
        command([sys.executable,"-m","editvideo.local_footage_runner",task_id],cwd=store.ROOT,log=out/"local-worker.log",cancelled=lambda:cancelled(task_id),timeout=req.timeout,env={**os.environ,"EDITVIDEO_DATA":str(store.DATA),"HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1"})
    finally:
        lock.release();slot.release()
    metadata=store.read_json(out/"local-generation.json")
    metadata['worker_wall_seconds']=round(time.monotonic()-started,3)
    if not ready():raise ValueError("Local model artifacts changed during inference; rerun pinned setup")
    records=verified_artifacts()
    metadata["checkpoint_sha256"]=records[str((root()/MODEL).resolve())]["sha256"]
    text=(root()/"t5xxl_fp8_e4m3fn.safetensors")
    metadata["text_encoder_sha256"]={text.name:records[str(text.resolve())]["sha256"]} if installation().get("text_encoder_precision")=="fp8" else {p.name:records[str(p.resolve())]["sha256"] for p in sorted((root()/"text_encoder").glob("*.safetensors"))}
    metadata["config_sha256"]={str(p.relative_to(root())):sha256(p) for p in sorted((root()/"config").rglob("*.json"))}
    metadata["weight_hash_verification"]="setup verified full hashes; size/mtime unchanged before and after inference"
    store.write_json(out/"local-generation.json",metadata)
    return out/"provider-output.mp4",metadata
