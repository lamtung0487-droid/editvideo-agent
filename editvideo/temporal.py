"""Bounded bidirectional inpainting through an external pinned ProPainter checkout.

Only synthesized hole pixels are composited into original-resolution footage.
Scene boundaries prevent propagation between unrelated shots.
"""
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from . import store
from .media import command, sha256

REVISION="e870e79321c31b733e2031af5aa2fb1fe3ac7eec"
WEIGHTS=("raft-things.pth","recurrent_flow_completion.pth","ProPainter.pth")

def root():return store.DATA/"backends/ProPainter"

def ready():return (root()/"inference_propainter.py").is_file() and all((root()/"weights"/n).is_file() for n in WEIGHTS)

def scene_boundaries(images,explicit=()):
    cuts=set(explicit);prior=None;prior_hist=None
    for i,path in enumerate(images):
        small=cv2.resize(np.asarray(Image.open(path).convert("RGB")),(96,64))
        hsv=cv2.cvtColor(small,cv2.COLOR_RGB2HSV)
        hist=cv2.calcHist([hsv],[0,1],None,[24,16],[0,180,0,256]);cv2.normalize(hist,hist)
        if prior is not None and cv2.compareHist(prior_hist,hist,cv2.HISTCMP_BHATTACHARYYA)>.6 and np.abs(small.astype(float)-prior).mean()/255>.18:cuts.add(i)
        prior=small.astype(float);prior_hist=hist
    if any(c<=0 or c>=len(images) for c in cuts):raise ValueError("scene_cuts must be inside the edit window")
    return [0,*sorted(cuts),len(images)]

def windows(start,end,size,overlap):
    if start<0 or end<=start or not 0<overlap<size:raise ValueError("Invalid temporal window/overlap")
    result=[];a=start
    while a<end:
        b=min(end,a+size);result.append((a,b))
        if b==end:break
        a=b-overlap
    return result

def inpaint(task_id,req,manifest,subject_root,source_frames,suffix,out):
    from .media_tasks import check,cancelled,update
    from .subjects import _mask,gpu_lock
    if not ready():raise ValueError("ProPainter missing; install requirements.temporal.txt and run scripts/setup_temporal.py --backend propainter")
    actual_revision=command(["git","rev-parse","HEAD"],cwd=root(),timeout=30).strip()
    if actual_revision!=REVISION:raise ValueError("ProPainter checkout revision changed; rerun pinned setup")
    count=manifest["frames"];files=[source_frames/f"{i:06d}{suffix}" for i in range(count)]
    w,h=Image.open(files[0]).size;scale=min(1,req.temporal_max_size/max(w,h))
    tw=max(64,int(w*scale)//8*8);th=max(64,int(h*scale)//8*8)
    boundaries=scene_boundaries(files,req.scene_cuts)
    jobs=[window for a,b in zip(boundaries,boundaries[1:]) for window in windows(a,b,req.temporal_window,req.temporal_overlap)]
    predictions=out/"temporal-predictions";predictions.mkdir(exist_ok=True)
    accum={};weights={};lock=gpu_lock(task_id)
    try:
        for number,(start,end) in enumerate(jobs):
            check(task_id);work=out/f"temporal-window-{number:03d}";frames=work/"input";masks=work/"masks"
            frames.mkdir(parents=True,exist_ok=True);masks.mkdir(exist_ok=True)
            for local,i in enumerate(range(start,end)):
                check(task_id);Image.open(files[i]).convert("RGB").resize((tw,th),Image.Resampling.LANCZOS).save(frames/f"{local:06d}.png")
                mask=_mask(manifest,subject_root,req.object_ids,i)
                if req.invert:mask=255-mask
                mask=cv2.resize(mask,(tw,th),interpolation=cv2.INTER_NEAREST)
                dilation=round((req.dilation+req.feather)*tw/manifest["mask_dimensions"][0])
                if dilation:mask=cv2.dilate(mask,np.ones((dilation*2+1,dilation*2+1),np.uint8))
                Image.fromarray(mask).save(masks/f"{local:06d}.png")
            if end-start==1:
                # RAFT needs a frame pair. A duplicated frame supplies a zero-motion
                # context without borrowing content from the adjacent shot.
                Image.open(frames/"000000.png").save(frames/"000001.png")
                Image.open(masks/"000000.png").save(masks/"000001.png")
            args=[sys.executable,"-m","editvideo.propainter_runner","--repository",root(),"--video",frames,"--mask",masks,"--output",work/"output","--width",tw,"--height",th,"--mask_dilation",0,"--neighbor_length",req.temporal_neighbors,"--subvideo_length",req.temporal_window,"--ref_stride",10,"--raft_iter",20,"--save_fps",manifest["fps"],"--save_frames","--fp16"]
            update(task_id,progress=.05+.65*number/len(jobs),message=f"Bidirectional inpainting window {number+1}/{len(jobs)}")
            command(args,cwd=store.ROOT,log=work/"worker.log",cancelled=lambda:cancelled(task_id),timeout=3600)
            result=work/"output/input/frames"
            for local,i in enumerate(range(start,end)):
                check(task_id);path=result/f"{local:04d}.png"
                if not path.exists():raise ValueError("ProPainter returned incomplete frames")
                prediction=np.asarray(Image.open(path).convert("RGB"),dtype=np.float32)
                # Smooth overlap only within a shot; never blend across detected cuts.
                weight=min(1,(local+1)/(req.temporal_overlap+1),(end-start-local)/(req.temporal_overlap+1))
                accum[i]=accum.get(i,0)+prediction*weight;weights[i]=weights.get(i,0)+weight
            # Finalize frames that cannot occur in a later window, bounding host RAM.
            later_start=jobs[number+1][0] if number+1<len(jobs) else count
            for i in sorted(list(accum)):
                if i<later_start:
                    Image.fromarray(np.clip(accum.pop(i)/weights.pop(i),0,255).astype(np.uint8)).save(predictions/f"{i:06d}.png")
    finally:lock.release()
    metadata={"backend":"propainter","temporal_model":True,"algorithm":"bidirectional completed optical flow + image propagation + temporal sparse transformer","working_dimensions":[tw,th],"scene_boundaries":boundaries,"windows":[list(x) for x in jobs],"revision":REVISION,"checkpoint_sha256":{n:sha256(root()/"weights"/n) for n in WEIGHTS},"license":"S-Lab 1.0 (non-commercial)","source":"https://github.com/sczhou/ProPainter"}
    store.write_json(out/"temporal-manifest.json",metadata)
    return predictions,metadata
