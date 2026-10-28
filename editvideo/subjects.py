"""Promptable subject masks, correction sessions and masked footage operations."""
import math
from pathlib import Path
from typing import Literal
import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store
from .media import FFMPEG, command, probe, sha256, Cancelled

SAM_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"


def model_path(name):
    return store.models_root(name)/name


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_id: int = Field(ge=1,le=32)
    label: str = Field(default="subject",max_length=120)
    frame: int = Field(default=0,ge=0)
    box: list[float] | None = None
    points: list[list[float]] = Field(default_factory=list,max_length=100)
    labels: list[Literal[0,1]] = Field(default_factory=list,max_length=100)

    @model_validator(mode="after")
    def coordinates(self):
        if not self.box and not self.points:
            raise ValueError("Give a normalized box or positive/negative points")
        if self.box is not None and (len(self.box)!=4 or not all(math.isfinite(x) and 0<=x<=1 for x in self.box) or self.box[0]>=self.box[2] or self.box[1]>=self.box[3]):
            raise ValueError("box=[left,top,right,bottom] normalized to source frame")
        if len(self.points)!=len(self.labels) or any(len(p)!=2 or not all(math.isfinite(x) and 0<=x<=1 for x in p) for p in self.points):
            raise ValueError("Normalized [x,y] points need one label each (1 subject, 0 exclusion)")
        return self


class SubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start: float = Field(default=0,ge=0,allow_inf_nan=False)
    end: float = Field(gt=0,allow_inf_nan=False)
    fps: int = Field(default=30,ge=1,le=30)
    width: int = Field(default=640,ge=256,le=1024)
    prompts: list[Prompt] = Field(min_length=1,max_length=100)
    source_sha256: str | None = None

    @model_validator(mode="after")
    def timing(self):
        frames = math.floor((self.end-self.start)*self.fps+1e-6)
        if not 1 <= frames <= 450 or self.end-self.start>15:
            raise ValueError("Choose 1..450 frames in a window <=15 seconds")
        keys=[(p.object_id,p.frame) for p in self.prompts]
        if len(keys)!=len(set(keys)) or any(p.frame>=frames for p in self.prompts):
            raise ValueError("One complete prompt per object/frame; frame must be in window")
        if any(not any(p.object_id==oid and p.frame==0 for p in self.prompts) for oid in {p.object_id for p in self.prompts}):
            raise ValueError("Each object needs an initial prompt on window frame 0")
        return self


class MaskEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_task_id: str
    object_ids: list[int] = Field(min_length=1,max_length=32)
    operation: Literal["remove","blur","replace_background","foreground","color_grade","spotlight","outline","reframe"]
    backend: Literal["lama","propainter","telea","clean_plate"] = "lama"
    background_path: str | None = None
    clean_plate_path: str | None = None
    invert: bool = False
    dilation: int = Field(default=3,ge=0,le=40)
    feather: int = Field(default=3,ge=0,le=30)
    blur_radius: int = Field(default=17,ge=1,le=101)
    brightness: float = Field(default=1,ge=0,le=3,allow_inf_nan=False)
    saturation: float = Field(default=1,ge=0,le=3,allow_inf_nan=False)
    tint: str = Field(default="#ffc65c",pattern=r"^#[0-9a-fA-F]{6}$")
    strength: float = Field(default=.5,ge=0,le=1,allow_inf_nan=False)
    temporal_strength: float = Field(default=0,ge=0,le=.6,allow_inf_nan=False)
    output_width: int = Field(default=720,ge=128,le=2048)
    output_height: int = Field(default=1280,ge=128,le=2048)
    zoom: float = Field(default=1,ge=1,le=4,allow_inf_nan=False)
    follow_smoothing: float = Field(default=.85,ge=0,le=.99,allow_inf_nan=False)
    resolution: Literal["source","mask"] = "source"
    inpaint_max_size: int = Field(default=1024,ge=256,le=1536)
    temporal_max_size: int = Field(default=512,ge=256,le=960)
    temporal_window: int = Field(default=60,ge=24,le=120)
    temporal_overlap: int = Field(default=12,ge=4,le=24)
    temporal_neighbors: int = Field(default=6,ge=4,le=12)
    scene_cuts: list[int] = Field(default_factory=list,max_length=100)

    @model_validator(mode="after")
    def inputs(self):
        if self.temporal_overlap>=self.temporal_window//2 or self.temporal_neighbors%2:
            raise ValueError("Temporal overlap must be below half the window; neighbors must be even")
        if self.backend=="propainter" and self.temporal_strength:
            raise ValueError("ProPainter already uses temporal propagation; leave temporal_strength=0")
        if self.output_width%2 or self.output_height%2:
            raise ValueError("Output dimensions must be even")
        if self.operation=="replace_background" and not self.background_path:
            raise ValueError("replace_background needs a local image or video")
        if self.operation=="remove" and self.backend=="clean_plate" and not self.clean_plate_path:
            raise ValueError("clean_plate requires an aligned source-sized background image")
        return self


def gpu_lock(task_id):
    from filelock import FileLock, Timeout
    from .media_tasks import check
    lock=FileLock(str(store.DATA/"media-gpu.lock"))
    while True:
        check(task_id)
        try:
            lock.acquire(timeout=.5)
            return lock
        except Timeout:
            continue


def segment(task_id, request):
    from .media_tasks import folder, check, update, cancelled
    import torch
    from sam2.build_sam import build_sam2_video_predictor
    req=SubjectRequest.model_validate(request)
    ckpt=model_path("sam2.1_hiera_tiny.pt")
    if not ckpt.exists():
        raise ValueError("SAM2 checkpoint missing; run scripts/setup_vision.py first")
    source=Path(req.path).resolve(strict=True);digest=sha256(source)
    if req.source_sha256 and digest!=req.source_sha256:
        raise ValueError("Source changed since subject session; create a new session")
    info=probe(source);stream=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
    if not stream or req.end>float(info["format"].get("duration",0))+.001:
        raise ValueError("Window exceeds source video")
    out=folder(task_id);frames=out/"frames";frames.mkdir(exist_ok=True)
    count=math.floor((req.end-req.start)*req.fps+1e-6)
    command([FFMPEG,"-y","-v","error","-ss",req.start,"-i",source,"-t",req.end-req.start,
        "-vf",f"fps={req.fps},scale={req.width}:-2","-frames:v",count,"-q:v","2","-start_number","0",frames/"%06d.jpg"],cancelled=lambda:cancelled(task_id))
    files=sorted(frames.glob("*.jpg"))
    if sha256(source)!=digest:
        raise ValueError("Source changed while decoding")
    if len(files)!=count:
        raise ValueError(f"Decoded {len(files)} frames, expected {count}; choose a shorter window")
    w,h=Image.open(files[0]).size
    ids=sorted({p.object_id for p in req.prompts})
    dirs={oid:out/f"masks-{oid}" for oid in ids}
    for d in dirs.values():d.mkdir(exist_ok=True)
    device="cuda" if torch.cuda.is_available() else "cpu"
    tracks={str(i):[] for i in ids};mask_hashes={};preview=out/"overlay-frames";preview.mkdir(exist_ok=True)
    colors=[(255,184,42),(38,210,255),(240,92,164),(126,235,137)]
    lock=gpu_lock(task_id)
    try:
        predictor=build_sam2_video_predictor(SAM_CONFIG,str(ckpt),device=device,apply_postprocessing=False)
        predictor.fill_hole_area=0  # Optional CUDA extension is not required on Windows.
        with torch.inference_mode():
            state=predictor.init_state(video_path=str(frames),offload_video_to_cpu=True,offload_state_to_cpu=True)
            for p in sorted(req.prompts,key=lambda p:(p.frame,p.object_id)):
                check(task_id)
                kwargs={"inference_state":state,"frame_idx":p.frame,"obj_id":p.object_id}
                if p.box is not None:kwargs["box"]=np.array(p.box,dtype=np.float32)*[w,h,w,h]
                if p.points:kwargs.update(points=np.array(p.points,dtype=np.float32)*[w,h],labels=np.array(p.labels,dtype=np.int32))
                predictor.add_new_points_or_box(**kwargs)
            for idx,obj_ids,logits in predictor.propagate_in_video(state,start_frame_idx=0):
                check(task_id)
                rgb=np.asarray(Image.open(files[idx]).convert("RGB")).copy()
                for j,oid in enumerate(obj_ids):
                    binary=(logits[j].detach().cpu().numpy().squeeze()>0).astype(np.uint8)*255
                    mask_file=dirs[oid]/f"{idx:06d}.png";Image.fromarray(binary).save(mask_file)
                    mask_hashes[mask_file.relative_to(out).as_posix()]=sha256(mask_file)
                    yy,xx=np.nonzero(binary)
                    bbox=[float(xx.min()/w),float(yy.min()/h),float((xx.max()+1)/w),float((yy.max()+1)/h)] if len(xx) else None
                    tracks[str(oid)].append({"frame":idx,"source_time":round(req.start+idx/req.fps,6),"box":bbox,"visible":bool(len(xx)),"area_fraction":round(len(xx)/(w*h),6)})
                    color=np.array(colors[ids.index(oid)%len(colors)])
                    active=binary>0;rgb[active]=(rgb[active]*.6+color*.4).astype(np.uint8)
                    contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(rgb,contours,-1,tuple(int(x) for x in color),2)
                Image.fromarray(rgb).save(preview/f"{idx:06d}.png")
                update(task_id,progress=.1+.8*(idx+1)/count,message=f"Tracking subjects {idx+1}/{count}")
            del state,predictor
        if device=="cuda":torch.cuda.empty_cache()
    finally:
        lock.release()
    if any(len(v)!=count for v in tracks.values()):
        raise ValueError("Incomplete mask propagation; partial masks are not published")
    overlay=out/"subject-overlay.mp4"
    command([FFMPEG,"-y","-v","error","-framerate",req.fps,"-i",preview/"%06d.png","-c:v","libx264","-crf","19","-pix_fmt","yuv420p",overlay],cancelled=lambda:cancelled(task_id))
    manifest={"schema":"editvideo.subject.v1","task_id":task_id,"source":str(source),"source_sha256":digest,
        "source_dimensions":[stream["width"],stream["height"]],"mask_dimensions":[w,h],"start":req.start,
        "fps":req.fps,"frames":count,"end":req.start+count/req.fps,"backend":"sam2.1-hiera-tiny","device":device,
        "checkpoint_sha256":sha256(ckpt),"prompts":[p.model_dump() for p in req.prompts],"tracks":tracks,"mask_hashes":mask_hashes,
        "notes":"Labels are supplied by the calling AI. Visible means nonempty predicted mask, not verified identity or confidence. Inspect occlusions and correct prompts."}
    manifest_path=out/"subjects.json";store.write_json(manifest_path,manifest)
    store.write_json(out/"request.json",{**req.model_dump(),"source_sha256":digest})
    return {"manifest":str(manifest_path),"manifest_sha256":sha256(manifest_path),"frames":count,"fps":req.fps,
        "dimensions":[w,h],"objects":[{"object_id":i,"label":next(p.label for p in req.prompts if p.object_id==i),"empty_frames":sum(not t["visible"] for t in tracks[str(i)])} for i in ids],
        "artifacts":{"overlay":str(overlay)},"backend":manifest["backend"],"device":device}


def load_session(task_id):
    from .media_tasks import get, folder
    task=get(task_id)
    if task["state"]!="completed" or task["kind"]!="subject":
        raise ValueError("Completed subject task required")
    path=folder(task_id)/"subjects.json"
    if sha256(path)!=task["result"]["manifest_sha256"]:
        raise ValueError("Subject manifest changed")
    manifest=store.read_json(path)
    if sha256(manifest["source"])!=manifest["source_sha256"]:
        raise ValueError("Source media changed")
    return manifest,folder(task_id)


def refine(task_id,prompts):
    from .media_tasks import submit
    manifest,out=load_session(task_id)
    request=store.read_json(out/"request.json")
    new=[Prompt.model_validate(p).model_dump() for p in prompts]
    if not new:raise ValueError("Give at least one correction")
    keys={(p["object_id"],p["frame"]) for p in new}
    request["prompts"]=[p for p in request["prompts"] if (p["object_id"],p["frame"]) not in keys]+new
    return submit("subject",request)


def read_session(task_id,object_id,offset=0,limit=60,frames=None):
    manifest,out=load_session(task_id)
    track=manifest["tracks"].get(str(object_id))
    if track is None or not 0<=offset or not 1<=limit<=120:
        raise ValueError("Unknown object or invalid pagination")
    chosen=frames if frames is not None else sorted({0,manifest["frames"]//2,manifest["frames"]-1})
    if not 1<=len(chosen)<=8 or any(not isinstance(f,int) or not 0<=f<manifest["frames"] for f in chosen):
        raise ValueError("Choose 1..8 window frames")
    return {"task_id":task_id,"object_id":object_id,"start":manifest["start"],"fps":manifest["fps"],"dimensions":manifest["mask_dimensions"],
        "tracks":track[offset:offset+limit],"total":len(track),"next_offset":offset+limit if offset+limit<len(track) else None,
        "frames":[{"index":i,"timestamp":manifest["start"]+i/manifest["fps"],"path":str(out/"overlay-frames"/f"{i:06d}.png"),"mask_path":str(out/f"masks-{object_id}"/f"{i:06d}.png")} for i in chosen]}


def _mask(manifest,out,ids,frame):
    masks=[]
    for oid in ids:
        if str(oid) not in manifest["tracks"]:raise ValueError(f"Object {oid} missing")
        path=out/f"masks-{oid}"/f"{frame:06d}.png"
        if sha256(path)!=manifest["mask_hashes"][path.relative_to(out).as_posix()]:
            raise ValueError("Mask changed; use a correction session")
        masks.append(np.asarray(Image.open(path).convert("L")))
    return np.maximum.reduce(masks)


def _lama(model,image,mask,device,max_size=1024):
    import torch
    original_h,original_w=image.shape[:2]
    factor=min(1,max_size/max(original_h,original_w))
    if factor<1:
        size=(max(8,round(original_w*factor)),max(8,round(original_h*factor)))
        image=cv2.resize(image,size,interpolation=cv2.INTER_AREA)
        mask=cv2.resize(mask,size,interpolation=cv2.INTER_NEAREST)
    h,w=image.shape[:2];ph=(-h)%8;pw=(-w)%8
    rgb=np.pad(image,((0,ph),(0,pw),(0,0)),mode="reflect")
    m=np.pad(mask,((0,ph),(0,pw)),mode="constant")
    x=torch.from_numpy(rgb.astype(np.float32).transpose(2,0,1)/255).unsqueeze(0).to(device)
    y=torch.from_numpy((m>0).astype(np.float32)[None,None]).to(device)
    with torch.inference_mode():result=model(x,y)[0].permute(1,2,0).cpu().numpy()
    output=np.clip(result[:h,:w]*255,0,255).astype(np.uint8)
    return cv2.resize(output,(original_w,original_h),interpolation=cv2.INTER_CUBIC) if factor<1 else output


def edit_mask(task_id,request):
    from .media_tasks import folder,check,update,cancelled
    req=MaskEditRequest.model_validate(request);manifest,source_out=load_session(req.subject_task_id)
    out=folder(task_id);dest_frames=out/"edited-frames";dest_frames.mkdir(exist_ok=True)
    w,h=manifest["mask_dimensions"];fps=manifest["fps"];count=manifest["frames"]
    source_frames=source_out/"frames";source_suffix=".jpg"
    mask_width=w
    if req.resolution=="source":
        source_frames=out/"source-frames";source_frames.mkdir(exist_ok=True);source_suffix=".png"
        command([FFMPEG,"-y","-v","error","-ss",manifest["start"],"-i",manifest["source"],"-t",count/fps,"-vf",f"fps={fps}","-frames:v",count,"-start_number",0,source_frames/"%06d.png"],cancelled=lambda:cancelled(task_id))
        if len(list(source_frames.glob("*.png")))!=count:raise ValueError("Source-resolution frame coverage incomplete")
        w,h=Image.open(source_frames/"000000.png").size
    pixel_scale=w/mask_width
    dilation=round(req.dilation*pixel_scale);feather=round(req.feather*pixel_scale)
    lock=None;model=None;device=None;bg=None;plate=None;previous=None;prior_mask=None;prior_gray=None
    crop_track=[];center=None
    predictions=None;temporal_metadata=None
    blend_cuts=set(req.scene_cuts)
    if req.temporal_strength:
        from .temporal import scene_boundaries
        blend_cuts=set(scene_boundaries([source_frames/f"{i:06d}{source_suffix}" for i in range(count)],req.scene_cuts)[1:-1])
    if req.operation=="remove" and req.backend=="propainter":
        from .temporal import inpaint
        predictions,temporal_metadata=inpaint(task_id,req,manifest,source_out,source_frames,source_suffix,out)
    if req.operation=="remove" and req.backend=="lama":
        import torch
        checkpoint=model_path("big-lama.pt")
        if not checkpoint.exists():raise ValueError("LaMa missing; run scripts/setup_vision.py first")
        lock=gpu_lock(task_id);device="cuda" if torch.cuda.is_available() else "cpu"
        try:model=torch.jit.load(str(checkpoint),map_location=device).eval()
        except Exception:lock.release();raise
    if req.clean_plate_path:
        plate=np.asarray(Image.open(Path(req.clean_plate_path).resolve(strict=True)).convert("RGB"))
        if plate.shape[:2]!=(h,w):
            if lock:lock.release()
            raise ValueError("Clean plate must match edit dimensions (source by default, or resolution=mask) and be aligned")
    if req.background_path:
        p=Path(req.background_path).resolve(strict=True)
        if p.suffix.lower() in (".png",".jpg",".jpeg",".webp"):
            bg=np.asarray(Image.open(p).convert("RGB").resize((w,h)))
        else:
            bg=cv2.VideoCapture(str(p))
            if not bg.isOpened():raise ValueError("Background video cannot be decoded")
    tint=np.array([int(req.tint[i:i+2],16) for i in (1,3,5)])
    try:
        for i in range(count):
            check(task_id)
            image=np.asarray(Image.open(source_frames/f"{i:06d}{source_suffix}").convert("RGB"))
            mask=_mask(manifest,source_out,req.object_ids,i)
            if mask.shape!=(h,w):mask=cv2.resize(mask,(w,h),interpolation=cv2.INTER_NEAREST)
            if req.invert:mask=255-mask
            if dilation:mask=cv2.dilate(mask,np.ones((dilation*2+1,dilation*2+1),np.uint8))
            alpha=mask.astype(np.float32)/255
            if feather:alpha=cv2.GaussianBlur(alpha,(feather*2+1,feather*2+1),0)
            a=alpha[:,:,None]
            if req.operation=="reframe":
                ys,xs=np.nonzero(mask)
                target=np.array([(xs.min()+xs.max())/2,(ys.min()+ys.max())/2]) if len(xs) else (center if center is not None else np.array([w/2,h/2]))
                center=target if center is None else center*req.follow_smoothing+target*(1-req.follow_smoothing)
                ratio=req.output_width/req.output_height
                cw=min(w,h*ratio)/req.zoom;ch=cw/ratio
                left=int(np.clip(center[0]-cw/2,0,w-cw));top=int(np.clip(center[1]-ch/2,0,h-ch))
                right=min(w,left+max(2,int(cw)));bottom=min(h,top+max(2,int(ch)))
                result=cv2.resize(image[top:bottom,left:right],(req.output_width,req.output_height),interpolation=cv2.INTER_CUBIC)
                crop_track.append({"frame":i,"box":[left/w,top/h,right/w,bottom/h],"subject_visible":bool(len(xs))})
            elif req.operation=="remove":
                if not np.any(mask):changed=image.copy()
                elif req.backend=="lama":changed=_lama(model,image,mask,device,req.inpaint_max_size)
                elif req.backend=="propainter":changed=np.asarray(Image.open(predictions/f"{i:06d}.png").convert("RGB").resize((w,h),Image.Resampling.LANCZOS))
                elif req.backend=="telea":changed=cv2.inpaint(image,mask,3,cv2.INPAINT_TELEA)
                else:changed=plate
                gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
                cut=i in blend_cuts
                if req.temporal_strength and previous is not None and not cut:
                    flow=cv2.calcOpticalFlowFarneback(gray,prior_gray,None,.5,3,15,3,5,1.2,0)
                    xx,yy=np.meshgrid(np.arange(w,dtype=np.float32),np.arange(h,dtype=np.float32))
                    warp=cv2.remap(previous,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_LINEAR)
                    overlap=(cv2.remap(prior_mask,xx+flow[:,:,0],yy+flow[:,:,1],cv2.INTER_NEAREST)>0)&(mask>0)
                    mix=req.temporal_strength*overlap[:,:,None]
                    changed=np.clip(changed*(1-mix)+warp*mix,0,255).astype(np.uint8)
                result=np.clip(image*(1-a)+changed*a,0,255).astype(np.uint8)
                previous=result;prior_mask=mask;prior_gray=gray
            elif req.operation=="blur":
                k=req.blur_radius*2+1;changed=cv2.GaussianBlur(image,(k,k),0)
                result=np.clip(image*(1-a)+changed*a,0,255).astype(np.uint8)
            elif req.operation=="replace_background":
                if isinstance(bg,np.ndarray):background=bg
                else:
                    duration=bg.get(cv2.CAP_PROP_FRAME_COUNT)/max(1,bg.get(cv2.CAP_PROP_FPS))
                    bg.set(cv2.CAP_PROP_POS_MSEC,((i/fps)%max(duration,.001))*1000)
                    ok,b=bg.read()
                    if not ok:raise ValueError("Background frame decode failed")
                    background=cv2.resize(cv2.cvtColor(b,cv2.COLOR_BGR2RGB),(w,h))
                result=np.clip(image*a+background*(1-a),0,255).astype(np.uint8)
            elif req.operation=="foreground":
                result=np.dstack((image,np.clip(alpha*255,0,255).astype(np.uint8)))
            elif req.operation=="color_grade":
                hsv=cv2.cvtColor(image,cv2.COLOR_RGB2HSV).astype(np.float32)
                hsv[:,:,1]*=req.saturation;hsv[:,:,2]*=req.brightness
                changed=cv2.cvtColor(np.clip(hsv,0,255).astype(np.uint8),cv2.COLOR_HSV2RGB)
                result=np.clip(image*(1-a)+changed*a,0,255).astype(np.uint8)
            elif req.operation=="spotlight":
                result=np.clip(image*(a+(1-a)*(1-req.strength)),0,255).astype(np.uint8)
            else:
                edge=cv2.morphologyEx(mask,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))[:,:,None]/255*req.strength
                result=np.clip(image*(1-edge)+tint*edge,0,255).astype(np.uint8)
            Image.fromarray(result).save(dest_frames/f"{i:06d}.png")
            update(task_id,progress=(.7+.2*(i+1)/count) if predictions else .9*(i+1)/count,message=f"Masked edit {i+1}/{count}")
    finally:
        if bg is not None and not isinstance(bg,np.ndarray):bg.release()
        if model is not None:
            del model
            import torch
            if device=="cuda":torch.cuda.empty_cache()
        if lock:lock.release()
    alpha_output=req.operation=="foreground"
    video=out/("foreground.webm" if alpha_output else "edited.mp4")
    args=[FFMPEG,"-y","-v","error","-framerate",fps,"-i",dest_frames/"%06d.png"]
    if not alpha_output:
        args += ["-ss",manifest["start"],"-t",count/fps,"-i",manifest["source"],"-map","0:v:0","-map","1:a:0?","-c:a","aac","-ar","48000"]
    args += ["-c:v","libvpx-vp9","-pix_fmt","yuva420p","-auto-alt-ref","0","-b:v","0","-crf","23"] if alpha_output else ["-c:v","libx264","-crf","18","-pix_fmt","yuv420p"]
    command([*args,"-frames:v",count,video],cancelled=lambda:cancelled(task_id))
    command([FFMPEG,"-v","error","-i",video,"-f","null","-"],cancelled=lambda:cancelled(task_id))
    artifacts={"video":str(video)}
    notes={"remove":"LaMa is framewise neural inpainting; optional flow blending reduces some flicker but is not a temporal generative model. Inspect large holes and camera cuts.","foreground":"VP9 alpha WebM plus RGBA frame sequence. Use transparent decoding in Remotion."}
    report={"subject_task_id":req.subject_task_id,"request":request,"source_sha256":manifest["source_sha256"],"frames":count,"fps":fps,"dimensions":[req.output_width,req.output_height] if req.operation=="reframe" else [w,h],"video_sha256":sha256(video),"alpha":alpha_output,"notes":notes.get(req.operation,"Edit applied to selected masks; inspect edges and continuity."),"artifacts":artifacts}
    if crop_track:
        store.write_json(out/"crop-track.json",crop_track)
        report["crop_track"]=str(out/"crop-track.json")
    if req.operation=="remove" and req.backend=="lama":report["checkpoint_sha256"]=sha256(model_path("big-lama.pt"))
    if temporal_metadata:
        report["temporal"]=temporal_metadata
        report["notes"]="ProPainter uses earlier/later frames within each shot. Only hole pixels are composited at source resolution; inspect reconstructed details and occlusion edges."
    store.write_json(out/"edit-manifest.json",report)
    return {**report,"manifest":str(out/"edit-manifest.json"),"frames_directory":str(dest_frames)}
