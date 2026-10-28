"""Install pinned public temporal inpainting and footage model artifacts."""
import argparse
import concurrent.futures
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from editvideo import store
from editvideo.media import sha256

PROPAINTER_REV="e870e79321c31b733e2031af5aa2fb1fe3ac7eec"
LTX_REV="8984fa25007f376c1a299016d0957a37a2f797bb"
TEXT_REV="b89adadeccd9ead2adcb9fa2825d3fabec48d404"
FP8_REV="6af2a98e3f615bdfa612fbd85da93d1ed5f69ef5"
CONFIG_REV="e58e28c39631af4d1468ee57a853764e11c1d37e"

def download(url,path,expected=None,size=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    digest=None
    if not path.exists():
        temp=path.with_suffix(path.suffix+".download")
        if size and size>64*1024*1024:
            chunk=8*1024*1024;state_path=temp.with_suffix(".download-state.json");guard=threading.Lock()
            done=set(json.loads(state_path.read_text())["done"]) if state_path.exists() else set(range((temp.stat().st_size if temp.exists() else 0)//chunk))
            with temp.open("r+b" if temp.exists() else "wb") as f:f.truncate(size)
            def part(index):
                if index in done:return
                start=index*chunk;end=min(size,start+chunk)-1
                for attempt in range(5):
                    try:
                        with httpx.Client(timeout=90,follow_redirects=True) as client:
                            r=client.get(url+f"?download=true&part={index}",headers={"Range":f"bytes={start}-{end}"});r.raise_for_status()
                        if r.status_code!=206 or r.headers.get("content-range")!=f"bytes {start}-{end}/{size}" or len(r.content)!=end-start+1:raise ValueError("Server did not honor artifact byte range")
                        with temp.open("r+b") as f:f.seek(start);f.write(r.content)
                        with guard:
                            done.add(index);state_temp=state_path.with_suffix(".tmp");state_temp.write_text(json.dumps({"done":sorted(done),"url":url,"bytes":size,"expected_sha256":expected}));state_temp.replace(state_path)
                            if len(done)%100==0:print(f"Downloading {path.name}: {len(done)*chunk/size:.0%}",flush=True)
                        return
                    except (httpx.HTTPError,ValueError):
                        if attempt==4:raise
                        time.sleep(1+attempt)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(part,range((size+chunk-1)//chunk)))
            digest=sha256(temp)
            if expected and digest!=expected:raise ValueError(f"Checksum mismatch: {path.name}")
            temp.replace(path);state_path.unlink(missing_ok=True)
        else:
            digest=_sequential_download(url,temp,path,expected)
    digest=digest or sha256(path)
    if expected and digest!=expected:raise ValueError(f"Cached checksum mismatch: {path.name}")
    print(f"Ready: {path.name} ({path.stat().st_size//1024//1024} MiB)",flush=True)
    return {"path":str(path),"bytes":path.stat().st_size,"mtime_ns":path.stat().st_mtime_ns,"sha256":digest,"source":url}

def _sequential_download(url,temp,path,expected):
        offset=temp.stat().st_size if temp.exists() else 0
        with httpx.stream("GET",url,headers={"Range":f"bytes={offset}-"} if offset else {},follow_redirects=True,timeout=180) as r:
            r.raise_for_status()
            if offset and r.status_code!=206:offset=0
            with temp.open("ab" if offset else "wb") as f:
                for block in r.iter_bytes(4*1024*1024):f.write(block)
        digest=sha256(temp)
        if expected and digest!=expected:raise ValueError(f"Checksum mismatch: {path.name}")
        temp.replace(path)
        return digest

def hf_files(repo,revision,paths,dest):
    with httpx.Client(timeout=60) as client:
        metadata=client.get(f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true");metadata.raise_for_status()
    files={f["rfilename"]:f for f in metadata.json()["siblings"]}
    return [(f"https://huggingface.co/{repo}/resolve/{revision}/{p}",dest/p,files[p].get("lfs",{}).get("sha256"),files[p].get("size")) for p in paths]

def main():
    p=argparse.ArgumentParser();p.add_argument("--backend",choices=["propainter","ltx","all"],default="all");p.add_argument("--text-encoder",choices=["fp8","fp32"],default="fp8");p.add_argument("--artifact-workers",type=int,choices=[1,2,3],default=1);args=p.parse_args()
    jobs=[];records={}
    if args.backend in ("propainter","all"):
        repo=store.DATA/"backends/ProPainter"
        if not repo.exists():subprocess.run(["git","clone","https://github.com/sczhou/ProPainter.git",str(repo)],check=True)
        subprocess.run(["git","checkout",PROPAINTER_REV],cwd=repo,check=True)
        jobs += [("https://github.com/sczhou/ProPainter/releases/download/v0.1.0/"+n,repo/"weights"/n,None) for n in ("raft-things.pth","recurrent_flow_completion.pth","ProPainter.pth")]
        records["propainter"]={"revision":PROPAINTER_REV,"repository":str(repo),"license":"S-Lab 1.0 (non-commercial)","source":"https://github.com/sczhou/ProPainter"}
    if args.backend in ("ltx","all"):
        root=store.DATA/"models/ltx"
        jobs += hf_files("Lightricks/LTX-Video",LTX_REV,["ltxv-2b-0.9.8-distilled.safetensors"],root)
        text_paths=["text_encoder/config.json","tokenizer/added_tokens.json","tokenizer/special_tokens_map.json","tokenizer/spiece.model","tokenizer/tokenizer_config.json"]
        if args.text_encoder=="fp32":text_paths += ["text_encoder/model.safetensors.index.json","text_encoder/model-00001-of-00002.safetensors","text_encoder/model-00002-of-00002.safetensors"]
        jobs += hf_files("PixArt-alpha/PixArt-XL-2-1024-MS",TEXT_REV,text_paths,root)
        if args.text_encoder=="fp8":jobs += hf_files("comfyanonymous/flux_text_encoders",FP8_REV,["t5xxl_fp8_e4m3fn.safetensors"],root)
        revision=CONFIG_REV
        jobs += hf_files("Lightricks/LTX-Video-0.9.5",revision,["transformer/config.json","vae/config.json","scheduler/scheduler_config.json"],root/"config")
        records["ltx"]={"model_revision":LTX_REV,"text_encoder_revision":TEXT_REV,"text_encoder_precision":args.text_encoder,"fp8_revision":FP8_REV if args.text_encoder=="fp8" else None,"config_revision":revision,"model":"ltxv-2b-0.9.8-distilled","root":str(root),"source":"https://huggingface.co/Lightricks/LTX-Video"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.artifact_workers) as pool:
        artifacts=list(pool.map(lambda x:download(*x),jobs))
    path=store.DATA/"models/temporal-models.json"
    existing=store.read_json(path) if path.exists() else {}
    for key,value in records.items():
        value["artifacts"]=[a for a in artifacts if ("ProPainter" in a["path"])==(key=="propainter")]
        existing[key]=value
    store.write_json(path,existing)

if __name__=="__main__":main()
