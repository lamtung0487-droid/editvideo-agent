"""Provider-independent footage jobs. No key, model or service is assumed available."""
import base64
import copy
import json
import os
import re
import time
import math
from pathlib import Path
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .media import FFMPEG, Cancelled, command, probe, sha256


class ReferenceFrame(BaseModel):
    model_config=ConfigDict(extra="forbid")
    path: str
    frame_index: int = Field(ge=0,le=160)
    strength: float = Field(default=1,gt=0,le=1)


class GenerationRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    provider: Literal["comfyui","runway","local_ltx"]
    prompt: str = Field(min_length=1,max_length=8000)
    negative_prompt: str = Field(default="",max_length=4000)
    workflow: str | None = None
    model: Literal["gen4.5","gen4_turbo","ltx-2b-distilled"] = "gen4.5"
    reference_image: str | None = None
    reference_mask: str | None = None
    reference_strength: float = Field(default=1,gt=0,le=1)
    reference_fit: Literal["cover","contain","stretch"] = "cover"
    reference_crop: list[float] | None = None
    reference_frames: list[ReferenceFrame] = Field(default_factory=list,max_length=4)
    image_cond_noise_scale: float = Field(default=.15,ge=0,le=.5)
    preset: Literal["draft","standard","detail"] = "standard"
    frame_count: int | None = Field(default=None,ge=1,le=900)
    seed: int = Field(default=42,ge=0,le=4294967295)
    width: int = Field(default=1280,ge=128,le=3840)
    height: int = Field(default=720,ge=128,le=3840)
    duration: int = Field(default=5,ge=2,le=15)
    fps: int = Field(default=30,ge=1,le=60)
    timeout: int = Field(default=1800,ge=30,le=7200)

    @model_validator(mode="before")
    @classmethod
    def provider_defaults(cls,value):
        if isinstance(value,dict) and value.get("provider")=="local_ltx":
            value={**value}
            sizes={"draft":(384,256,49),"standard":(512,320,73),"detail":(768,448,121)}
            w,h,frames=sizes.get(value.get("preset","standard"),sizes["standard"])
            if value.get("preset") in ("draft","detail") and "frame_count" not in value and "duration" not in value:
                value["frame_count"]=frames
            for key,default in (("width",w),("height",h),("fps",24),("duration",3)):
                value.setdefault(key,default)
        return value

    @model_validator(mode="after")
    def backend(self):
        if self.reference_crop is not None:
            r=self.reference_crop
            if len(r)!=4 or not all(math.isfinite(x) for x in r) or not 0<=r[0]<r[2]<=1 or not 0<=r[1]<r[3]<=1:
                raise ValueError("reference_crop must be normalized [left,top,right,bottom]")
        if self.provider!="local_ltx" and (self.reference_frames or self.reference_strength!=1 or self.reference_fit!="cover" or self.reference_crop or self.image_cond_noise_scale!=.15 or self.preset!="standard"):
            raise ValueError("Reference-frame controls and presets currently require local_ltx")
        if self.provider=="local_ltx":
            self.model="ltx-2b-distilled"
            if self.width%32 or self.height%32 or max(self.width,self.height)>768 or self.width*self.height>393216:
                raise ValueError("Local LTX dimensions must be multiples of 32, longest side <=768, area <=393216; use e.g. 512x320")
            if self.frame_count is not None and (self.frame_count%8!=1 or self.frame_count>161):
                raise ValueError("Local LTX frame_count must be 8*n+1 and <=161")
            if self.frame_count is None and self.duration*self.fps>161:
                raise ValueError("Local LTX window <=161 frames; submit multiple shots")
            if self.frame_count is None:
                self.frame_count=(self.duration*self.fps-1+4)//8*8+1
            if self.negative_prompt or self.reference_mask or self.workflow:
                raise ValueError("Local distilled LTX supports prompt and reference frames; no negative prompt, mask or workflow")
            positions=([0] if self.reference_image else [])+[r.frame_index for r in self.reference_frames]
            if len(set(positions))!=len(positions) or any(i>=self.frame_count for i in positions):
                raise ValueError("Reference frame indices must be unique and inside frame_count")
            if not positions and (self.reference_crop or self.reference_strength!=1 or self.reference_fit!="cover" or self.image_cond_noise_scale!=.15):
                raise ValueError("Reference controls require reference_image or reference_frames")
        if self.frame_count is not None and self.frame_count/self.fps>15:
            raise ValueError("frame_count/fps must fit a <=15s generation window")
        if self.reference_mask and not self.reference_image:
            raise ValueError("reference_mask needs a reference_image")
        if self.provider=="comfyui" and not self.workflow:
            raise ValueError("Choose a registered API workflow for ComfyUI")
        if self.provider=="runway":
            if self.model=="ltx-2b-distilled":raise ValueError("Choose a Runway model for provider runway")
            if self.reference_mask or self.frame_count is not None:
                raise ValueError("Runway adapter uses duration and has no mask field; use a suitable ComfyUI workflow")
            if len(self.prompt.encode("utf-16-le"))//2>1000 or self.duration>10:
                raise ValueError("Runway prompt <=1000 UTF-16 units, duration 2..10s")
            if self.negative_prompt:raise ValueError("These Runway models have no negative prompt field; incorporate intent in prompt")
            ratios={(1280,720),(720,1280)}
            if self.reference_image:ratios|={(1104,832),(832,1104),(960,960),(1584,672)}
            if (self.width,self.height) not in ratios:raise ValueError("Resolution unsupported by selected Runway mode")
            if self.model=="gen4_turbo" and (not self.reference_image or self.duration not in (5,10)):
                raise ValueError("gen4_turbo needs an image and duration 5 or 10s")
        return self


def workflow_path(name):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",name):raise ValueError("Workflow name uses letters/digits/hyphen/underscore")
    return store.DATA/"generation-workflows"/(name+".json")


def register_workflow(name,graph,bindings,description="",output_node=None):
    """Save an API-format graph and explicit semantic parameter bindings."""
    if not isinstance(graph,dict) or not 1<=len(graph)<=500 or len(json.dumps(graph))>2_000_000:
        raise ValueError("API graph must contain 1..500 nodes and fit in 2MB")
    for node in graph.values():
        if not isinstance(node,dict) or not isinstance(node.get("class_type"),str) or not isinstance(node.get("inputs"),dict):
            raise ValueError("Export ComfyUI API format, not the UI canvas JSON")
    allowed={"prompt","negative_prompt","seed","width","height","frames","fps","reference_image","reference_mask"}
    if not isinstance(bindings,dict) or "prompt" not in bindings or set(bindings)-allowed:
        raise ValueError(f"Bindings need prompt and may use {sorted(allowed)}")
    for key,targets in bindings.items():
        if not isinstance(targets,list) or not 1<=len(targets)<=20:raise ValueError("Each binding needs 1..20 targets")
        for target in targets:
            if set(target)!={"node","input"} or str(target["node"]) not in graph or target["input"] not in graph[str(target["node"])]["inputs"]:
                raise ValueError(f"Missing workflow input for {key}")
    if output_node is not None and str(output_node) not in graph:raise ValueError("Output node missing")
    record={"name":name,"graph":graph,"bindings":bindings,"description":description[:2000],"output_node":str(output_node) if output_node is not None else None}
    path=workflow_path(name);store.write_json(path,record)
    return {"name":name,"path":str(path),"sha256":sha256(path),"parameters":sorted(bindings),"nodes":len(graph)}


def comfy_url():
    return os.environ.get("EDITVIDEO_COMFY_URL","http://127.0.0.1:8188").rstrip("/")


def comfy_headers():
    key=os.environ.get("EDITVIDEO_COMFY_API_KEY")
    return {"Authorization":"Bearer "+key} if key else {}


def _json(response):
    # Avoid printing request headers or provider error bodies that could contain credentials.
    if response.status_code>=400:
        raise ValueError(f"Provider HTTP {response.status_code}; check service, model and request parameters")
    return response.json()


def capabilities(probe_local=False):
    import importlib.util
    from . import temporal,local_footage
    workflows=[]
    root=store.DATA/"generation-workflows"
    if root.exists():
        for path in sorted(root.glob("*.json")):
            r=store.read_json(path)
            workflows.append({"name":r["name"],"parameters":sorted(r["bindings"]),"description":r["description"],"sha256":sha256(path)})
    connected=None;reason="Not probed"
    if probe_local:
        try:
            with httpx.Client(timeout=3,headers=comfy_headers()) as client:
                _json(client.get(comfy_url()+"/system_stats"))
            connected=True;reason="Server responds; a matching video model/workflow is still required"
        except (httpx.HTTPError,ValueError):connected=False;reason="ComfyUI server unavailable"
    return {"subject_tracking":{"backend":"sam2.1-hiera-tiny","installed":bool(importlib.util.find_spec("sam2")),"model_ready":(store.models_root("sam2.1_hiera_tiny.pt")/"sam2.1_hiera_tiny.pt").exists(),"max_window_seconds":15,"max_frames":450,"prompts":"normalized boxes + positive/negative points; corrections on any frame"},
        "inpainting":{"lama_ready":bool(importlib.util.find_spec("torch")) and (store.models_root("big-lama.pt")/"big-lama.pt").exists(),"lama_temporal_model":False,"propainter":{"ready":temporal.ready(),"temporal_model":True,"scene_aware":True,"working_size_default":512,"license":"S-Lab 1.0 (non-commercial)"},"other_backends":["telea (classical)","aligned clean_plate"],"operations":["remove","blur","replace_background","foreground","color_grade","spotlight","outline","reframe"]},
        "generation":{"comfyui":{"url":comfy_url(),"connected":connected,"reason":reason,"workflows":workflows},
        "runway":{"configured":bool(os.environ.get("EDITVIDEO_RUNWAY_API_KEY")),"key_variable":"EDITVIDEO_RUNWAY_API_KEY","models":["gen4.5","gen4_turbo"],"modes":["text_to_video","image_to_video"],"live_generation_verified":False},
        "local_ltx":{"ready":local_footage.ready(),"model":"ltxv-2b-0.9.8-distilled","modes":["text_to_video","image_to_video","multi_reference_frames"],"default_request":{"provider":"local_ltx","width":512,"height":320,"fps":24,"duration":3,"frame_count":73},"presets":{"draft":[384,256,49],"standard":[512,320,73],"detail":[768,448,121]},"reference_controls":["strength","cover/contain/stretch","normalized crop","up to 4 additional frame anchors","image_cond_noise_scale"],"iteration":"refine_footage preserves parent and seed, creates a new task","caches":{"prompt":"verified encoder/tokenizer + prompt hash; <=128MB, skips T5 load on hit","reference":"prepared pixels + VAE/model hash; posterior before RNG sampling, <=128 entries; encoder omitted when all references hit"},"max_frames":161,"frame_rule":"8*n+1","cached_only":True,"requires":"CUDA GPU + requirements.temporal.txt + scripts/setup_temporal.py --backend ltx"}},
        "perception":{"analyze_motion":{"cpu_only":True,"max_samples":240,"max_seconds":15,"signals":["dense forward/backward flow","robust camera affine candidate","motion-compensated residual","fixed ROI luma/sharpness/clipping","temporal FFT","adaptive event evidence"]},"temporal_lens":"derived RGB frequency-band amplification with original comparison; not new evidence"},
        "workflow":"inspect footage → subject prompts → inspect masks → correct → masked edit → attach with current revision → patch timeline/source → render → inspect",
        "notes":"Installed/configured is not proof of model quality or provider availability. External generation runs only when explicitly submitted with a configured provider; no keys are returned."}


def discover_nodes(query="",offset=0,limit=12):
    if offset<0 or not 1<=limit<=40:raise ValueError("Invalid pagination")
    with httpx.Client(timeout=20,headers=comfy_headers()) as client:
        nodes=_json(client.get(comfy_url()+"/object_info"))
    chosen=[(k,v) for k,v in nodes.items() if query.lower() in (k+" "+v.get("category","")+" "+v.get("description","")).lower()]
    return {"items":[{"class_type":k,"definition":v} for k,v in chosen[offset:offset+limit]],"total":len(chosen),"next_offset":offset+limit if offset+limit<len(chosen) else None}


def validate_request(request):
    req=GenerationRequest.model_validate(request)
    for reference in (req.reference_image,req.reference_mask,*[r.path for r in req.reference_frames]):
        if not reference:continue
        path=Path(reference).resolve(strict=True)
        if path.suffix.lower() not in (".png",".jpg",".jpeg",".webp") or path.stat().st_size>5_000_000:
            raise ValueError("Reference must be a local image <=5MB")
        from PIL import Image
        with Image.open(path) as im:
            if im.width*im.height>40_000_000:raise ValueError("Reference image <=40MP")
            im.verify()
    if req.provider=="runway" and not os.environ.get("EDITVIDEO_RUNWAY_API_KEY"):
        raise ValueError("Runway not configured: set EDITVIDEO_RUNWAY_API_KEY locally")
    if req.provider=="local_ltx":
        from .local_footage import ready
        if not ready():raise ValueError("Local LTX not installed; run scripts/setup_temporal.py --backend ltx")
    if req.provider=="comfyui":
        wf=store.read_json(workflow_path(req.workflow))
        if req.reference_image and "reference_image" not in wf["bindings"]:
            raise ValueError("Workflow has no reference image binding")
        if "reference_image" in wf["bindings"] and not req.reference_image:
            raise ValueError("Workflow requires reference_image")
        if req.reference_mask and "reference_mask" not in wf["bindings"]:
            raise ValueError("Workflow has no reference_mask binding")
        if "reference_mask" in wf["bindings"] and not req.reference_mask:
            raise ValueError("Workflow requires reference_mask")
        # Parameters absent from bindings stay as authored in the workflow, explicitly reported.
    return req


def _download(url,path,task_id,client=None,params=None):
    from .media_tasks import check
    own=client is None
    if own:client=httpx.Client(timeout=120,follow_redirects=True) # Storage downloads never receive provider API headers.
    total=0
    try:
        with client.stream("GET",url,params=params) as r:
            if r.status_code>=400:raise ValueError(f"Artifact download HTTP {r.status_code}")
            with path.open("wb") as f:
                for chunk in r.iter_bytes(1024*1024):
                    check(task_id);total+=len(chunk)
                    if total>500*1024*1024:raise ValueError("Generated artifact exceeds 500MB")
                    f.write(chunk)
    finally:
        if own:client.close()


def _pause(task_id):
    from .media_tasks import check
    for _ in range(10):check(task_id);time.sleep(.2)


def _comfy(task_id,req,out):
    from .media_tasks import check,update
    wf=store.read_json(out/"workflow.json");graph=copy.deepcopy(wf["graph"])
    values={"prompt":req.prompt,"negative_prompt":req.negative_prompt,"seed":req.seed,"width":req.width,"height":req.height,"frames":req.frame_count or req.duration*req.fps,"fps":req.fps}
    with httpx.Client(timeout=30,headers=comfy_headers()) as client:
        definitions=_json(client.get(comfy_url()+"/object_info"))
        missing=sorted({node["class_type"] for node in graph.values()}-set(definitions))
        if missing:raise ValueError(f"Missing ComfyUI node classes: {missing}")
        for binding,reference in (("reference_image",req.reference_image),("reference_mask",req.reference_mask)):
            if not reference:continue
            p=Path(reference)
            with p.open("rb") as f:
                uploaded=_json(client.post(comfy_url()+"/upload/image",files={"image":(p.name,f)},data={"type":"input","overwrite":"false"}))
            values[binding]=(uploaded.get("subfolder","").rstrip("/")+"/" if uploaded.get("subfolder") else "")+uploaded["name"]
        for key,targets in wf["bindings"].items():
            for t in targets:graph[str(t["node"])]["inputs"][t["input"]]=values[key]
        store.write_json(out/"submitted-workflow.json",graph)
        response=_json(client.post(comfy_url()+"/prompt",json={"prompt":graph,"client_id":"editvideo-"+task_id}))
        if response.get("node_errors") or response.get("error") or not response.get("prompt_id"):
            raise ValueError("ComfyUI rejected workflow; inspect node inputs and model names")
        remote={"provider":"comfyui","id":response["prompt_id"],"workflow":req.workflow,"workflow_sha256":sha256(out/"workflow.json")}
        store.write_json(out/"remote.json",remote);start=time.monotonic()
        try:
            while True:
                check(task_id)
                history=_json(client.get(comfy_url()+"/history/"+remote["id"]))
                item=history.get(remote["id"])
                if item:
                    if item.get("status",{}).get("status_str")=="error":raise ValueError("ComfyUI execution failed; check server node/model logs")
                    if item.get("status",{}).get("completed",True):break
                if time.monotonic()-start>req.timeout:raise TimeoutError("ComfyUI generation timeout")
                update(task_id,progress=.2,message="ComfyUI generating footage");_pause(task_id)
            outputs=item.get("outputs",{})
            if wf["output_node"]:outputs={wf["output_node"]:outputs.get(wf["output_node"],{})}
            videos=[x for node in outputs.values() for key in ("videos","gifs","images") for x in node.get(key,[]) if Path(x.get("filename","")).suffix.lower() in (".mp4",".webm",".mov",".mkv")]
            if not videos:raise ValueError("Workflow returned no video artifact; select a video-saving output node")
            artifact=videos[0];target=out/("provider-output"+Path(artifact["filename"]).suffix.lower())
            _download(comfy_url()+"/view",target,task_id,client,params={"filename":artifact["filename"],"subfolder":artifact.get("subfolder",""),"type":artifact.get("type","output")})
            return target,{**remote,"bound_parameters":sorted(wf["bindings"]),"unbound_parameters":sorted(set(values)-set(wf["bindings"])),"output":artifact}
        except (Cancelled,TimeoutError):
            # Queue deletion is scoped. Old ComfyUI versions ignore interrupt prompt_id;
            # targeted interrupt must be enabled explicitly after verifying server support.
            targeted=os.environ.get("EDITVIDEO_COMFY_TARGETED_INTERRUPT")=="1"
            cancellation_error=None
            try:
                deleted=client.post(comfy_url()+"/queue",json={"delete":[remote["id"]]},timeout=5)
                if deleted.status_code>=400:cancellation_error=f"Queue cancellation HTTP {deleted.status_code}"
                if targeted:
                    stopped=client.post(comfy_url()+"/interrupt",json={"prompt_id":remote["id"]},timeout=5)
                    if stopped.status_code>=400:cancellation_error=f"Interrupt HTTP {stopped.status_code}"
            except httpx.HTTPError:cancellation_error="Provider unreachable during cancellation"
            store.write_json(out/"remote.json",{**remote,"cancel_requested":True,"targeted_interrupt":targeted,"cancellation_error":cancellation_error,"note":"Active remote execution may continue when targeted interrupt is disabled or cancellation could not reach server"})
            raise


def _runway(task_id,req,out):
    from .media_tasks import check,update
    headers={"Authorization":"Bearer "+os.environ["EDITVIDEO_RUNWAY_API_KEY"],"X-Runway-Version":"2024-11-06"}
    base="https://api.dev.runwayml.com"
    body={"model":req.model,"promptText":req.prompt,"duration":req.duration,"ratio":f"{req.width}:{req.height}","seed":req.seed}
    endpoint="text_to_video"
    if req.reference_image:
        import mimetypes
        p=Path(req.reference_image);mime=mimetypes.guess_type(p.name)[0] or "image/png"
        body["promptImage"]="data:"+mime+";base64,"+base64.b64encode(p.read_bytes()).decode()
        endpoint="image_to_video"
    # Store only local path/hash of reference, never the huge data URI or API key.
    with httpx.Client(timeout=30,headers=headers) as client:
        response=_json(client.post(base+"/v1/"+endpoint,json=body));remote={"provider":"runway","id":response["id"],"model":req.model,"mode":endpoint}
        store.write_json(out/"remote.json",remote);start=time.monotonic()
        try:
            while True:
                check(task_id);result=_json(client.get(base+"/v1/tasks/"+remote["id"]))
                if result["status"]=="SUCCEEDED":break
                if result["status"] in ("FAILED","CANCELLED"):raise ValueError("Runway task "+result["status"])
                if time.monotonic()-start>req.timeout:raise TimeoutError("Runway generation timeout")
                update(task_id,progress=min(.9,float(result.get("progress",.2))),message="Runway generating footage");_pause(task_id)
            if not result.get("output"):raise ValueError("Runway returned no output")
            target=out/"provider-output.mp4";_download(result["output"][0],target,task_id)
            return target,remote
        except (Cancelled,TimeoutError):
            status=None
            try:status=client.delete(base+"/v1/tasks/"+remote["id"],timeout=5).status_code
            except httpx.HTTPError:pass
            store.write_json(out/"remote.json",{**remote,"cancel_requested":True,"cancel_http_status":status,"note":"Remote cancellation unconfirmed" if status is None or status>=400 else "Cancellation sent"})
            raise


def generate(task_id,request):
    from .media_tasks import folder,cancelled,check
    req=GenerationRequest.model_validate(request);out=folder(task_id)
    if req.provider=="local_ltx":
        from .local_footage import run
        source,remote=run(task_id,req,out)
    else:source,remote=(_comfy if req.provider=="comfyui" else _runway)(task_id,req,out)
    check(task_id);info=probe(source)
    video_stream=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
    duration=float(info["format"].get("duration",0))
    if not video_stream or not 0<duration<=60 or video_stream["width"]*video_stream["height"]>40_000_000:
        raise ValueError("Provider output must be a decodable video <=60s, <=40MP")
    dest=out/"generated.mp4"
    command([FFMPEG,"-y","-v","error","-xerror","-i",source,"-map","0:v:0","-map","0:a:0?","-vf",f"fps={req.fps}","-c:v","libx264","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-ar","48000",dest],cancelled=lambda:cancelled(task_id))
    command([FFMPEG,"-v","error","-xerror","-i",dest,"-f","null","-"],cancelled=lambda:cancelled(task_id))
    actual=probe(dest)
    report={"provider":req.provider,"remote":remote,"request":request,"artifacts":{"video":str(dest)},"video_sha256":sha256(dest),
        "actual_duration":float(actual["format"]["duration"]),"actual_dimensions":[video_stream["width"],video_stream["height"]],"fps":req.fps,"source_kind":"AI-generated reconstruction",
        "notes":"Provider output is synthesized, not factual evidence. Actual dimensions/duration are measured; inspect continuity, subject identity and narration relevance."}
    if req.reference_image:report["reference_sha256"]=sha256(req.reference_image)
    if req.reference_mask:report["mask_sha256"]=sha256(req.reference_mask)
    if req.reference_frames:report["reference_frames_sha256"]=[{"frame_index":r.frame_index,"sha256":sha256(r.path)} for r in req.reference_frames]
    lineage=out/"refinement.json"
    if lineage.exists():report["refinement"]=store.read_json(lineage)
    store.write_json(out/"generation-manifest.json",report)
    return {**report,"manifest":str(out/"generation-manifest.json")}


def refine(task_id,changes):
    """A new immutable local generation, preserving parent seed unless changed."""
    from . import media_tasks
    parent=media_tasks.get(task_id)
    if parent["kind"]!="generate" or parent["state"]!="completed" or parent["request"]["provider"]!="local_ltx":
        raise ValueError("Refinement requires a completed local_ltx generation")
    allowed={"prompt","seed","width","height","frame_count","fps","reference_image","reference_frames","reference_strength","reference_fit","reference_crop","image_cond_noise_scale","timeout"}
    if not isinstance(changes,dict) or not changes or set(changes)-allowed:
        raise ValueError(f"changes needs one or more of {sorted(allowed)}")
    request={**parent["request"],**changes}
    if "reference_image" not in changes and request.get("reference_image"):
        if sha256(request["reference_image"])!=parent["result"].get("reference_sha256"):
            raise ValueError("Parent reference changed; explicitly supply a new reference")
    if "reference_frames" not in changes:
        expected=parent["result"].get("reference_frames_sha256",[])
        if any(sha256(r["path"])!=expected[i]["sha256"] for i,r in enumerate(request.get("reference_frames",[]))):
            raise ValueError("Parent anchor changed; explicitly supply new reference_frames")
    # Snapshot lineage before launch, avoiding a worker/metadata race.
    child=media_tasks.submit("generate",request,launch=False)
    store.write_json(media_tasks.folder(child["id"])/"refinement.json",{
        "parent_task_id":task_id,"parent_video_sha256":parent["result"]["video_sha256"],
        "changed_parameters":sorted(changes),"seed_preserved":request["seed"]==parent["request"]["seed"],
        "note":"New full diffusion pass; same prompt can reuse embeddings. Not latent video-to-video editing."})
    return media_tasks.launch_task(child["id"])
