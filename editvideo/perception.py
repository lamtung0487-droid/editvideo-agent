"""Grounded temporal evidence and aesthetic observation packets for the calling AI."""
import json
import math
import re
import uuid
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from . import store
from .media import FFMPEG,command,probe,sha256
from .observe import observe

DIRECTOR_GUIDE = """Read frames in timestamp order and listen to the supplied audio. Separate measured facts from your interpretation. Explain the intended idea, visual hierarchy, focal subject, typography legibility, palette/lighting consistency, negative space, motion continuity, cut motivation, reading time, narration-image alignment, and audio masking. A colorful image is not automatically good design. Describe each useful observation with frame/timestamp/region, its effect on the viewer and one concrete edit. Avoid numeric beauty scores or approval gates. If motion, text or meaning cannot be established from sampled frames, inspect a denser window or a crop before asserting it. Preserve source meaning: overlays are editable; text replacement inside moving footage needs inspected subject masks and inpainting: check media_capabilities, track_subject, read/refine masks and edit_subject before composing exact replacement text. LaMa is framewise and may flicker. ProPainter adds bidirectional temporal inpainting with overlapping windows and scene boundaries; inspect reconstructed background and edges. Use analyze_motion for dense forward/backward correspondence, global affine candidate, aligned residual and ROI/FFT evidence; temporal_lens is a derived color-band view and cannot recover unseen information. Do not interpret numerical residual or correspondence reliability as beauty/identity confidence. Installed local LTX generates prompt/reference-image footage with timed anchors and reusable encoder caches; refine_footage creates a seeded child, not latent video-to-video; configured ComfyUI/Runway are optional adapters. Generated footage is illustration/reconstruction, not source evidence. Choose offline typography/palette/style via design_catalog and actual read_design_preview; layout_text measures glyph bounds, derive_palette generates semantic roles, apply_design and compose_graphic create editable compositions. Inspect Vietnamese diacritics, text wrapping and actual footage contrast; library metadata is not a beauty score. Choose effects by purpose with effect_catalog; use a consistent design direction and fewer simultaneous focal motions. Return: intent, evidence, interpretation with uncertainty, proposed timeline/code edits, frames to inspect after editing."""

def index_video(path,threshold=10.0,offset=0,limit=20):
    from filelock import FileLock,Timeout
    source=Path(path).resolve(strict=True)
    locks=store.DATA/"index-locks";locks.mkdir(parents=True,exist_ok=True)
    key=sha256(source)+f"-{threshold:g}"
    try:
        with FileLock(str(locks/(key+".lock")),timeout=2):
            return _build_video_index(path,threshold,offset,limit)
    except Timeout:
        raise ValueError("This video index is being built by another client; retry later") from None


def _build_video_index(path,threshold=10.0,offset=0,limit=20):
    if not 1<=threshold<=100 or offset<0 or not 1<=limit<=100:
        raise ValueError("threshold 1..100 percent; offset >=0; limit 1..100")
    source=Path(path).resolve(strict=True);info=probe(source)
    duration=float(info["format"].get("duration",0));video=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
    if not video or not 0<duration<=3600:
        raise ValueError("Video required; index supports up to 1 hour")
    digest=sha256(source);out=store.DATA/"indexes"/(digest[:24]+f"-{threshold:g}")
    manifest=out/"index.json"
    if not manifest.exists():
        out.mkdir(parents=True,exist_ok=True)
        log=command([FFMPEG,"-v","info","-i",source,"-an","-vf",f"scale=160:-2,scdet=t={threshold}","-f","null","-"],timeout=1800)
        cuts=sorted({float(x) for x in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)",log) if .04<float(x)<duration-.04})
        boundaries=[0.0,*cuts,duration]
        shots=[{"id":f"segment-{i:04}","start":a,"end":b,"duration":b-a,"inspect_at":[a+(b-a)*p for p in (.1,.5,.9)]} for i,(a,b) in enumerate(zip(boundaries,boundaries[1:]))]
        raw=out/"samples.rgb"
        command([FFMPEG,"-y","-v","error","-i",source,"-vf","fps=1,scale=80:45","-an","-pix_fmt","rgb24","-f","rawvideo",raw],timeout=900)
        pixels=np.fromfile(raw,dtype=np.uint8).reshape(-1,45,80,3)
        metrics=[];prior=None
        for i,p in enumerate(pixels):
            luminance=np.mean(p.astype(np.float32)*np.array([.2126,.7152,.0722]),axis=2)
            sample=Image.fromarray(p).quantize(colors=5).convert("RGB").getcolors(3600)
            colors=["#%02x%02x%02x"%rgb for _,rgb in sorted(sample,reverse=True)[:5]]
            metrics.append({"timestamp":min(i+.5,duration-.001),"mean_luminance":round(float(luminance.mean())/255,4),"dark_pixel_fraction":round(float((luminance<25).mean()),4),"bright_pixel_fraction":round(float((luminance>235).mean()),4),"sampled_pixel_change":None if prior is None else round(float(np.abs(p.astype(float)-prior).mean())/255,4),"palette":colors})
            prior=p.astype(float)
        audio=None
        if any(s["codec_type"]=="audio" for s in info["streams"]):
            raw_audio=out/"audio.f32"
            command([FFMPEG,"-y","-v","error","-i",source,"-vn","-ar","8000","-ac","1","-f","f32le",raw_audio],timeout=900)
            values=np.fromfile(raw_audio,dtype="<f4")
            audio=[]
            for start in range(0,len(values),8000):
                block=values[start:start+8000];rms=float(np.sqrt(np.mean(block*block)))
                audio.append({"start":start/8000,"end":min((start+8000)/8000,duration),"rms_dbfs":round(20*math.log10(max(rms,1e-9)),2),"peak":round(float(np.abs(block).max()),4)})
            raw_audio.unlink()
        raw.unlink()
        store.write_json(manifest,{"source":str(source),"sha256":digest,"duration":duration,"source_size":[video["width"],video["height"]],"scene_threshold":threshold,"segments":shots,"visual_samples":metrics,"audio_energy":audio,
            "limitations":"Scene changes are pixel-change candidates, not semantic scenes. Metrics sample at 1 Hz; sampled_pixel_change mixes camera/object/lighting changes and is not optical flow. Palette is a low resolution observation, not an aesthetic judgment. Inspect dense windows for actions and continuity."})
    data=store.read_json(manifest)
    segments=data.pop("segments");samples=data.pop("visual_samples");audio=data.pop("audio_energy")
    data.update(index_path=str(manifest),segments=segments[offset:offset+limit],total_segments=len(segments),next_offset=offset+limit if offset+limit<len(segments) else None,
        metrics_path=str(manifest),visual_sample_count=len(samples),audio_energy_available=audio is not None)
    return data

# Audio blocks go only to a client that said it can hear them (bootstrap client): a window's audio is ~340k base64
# characters, and a host that drops it leaves the model believing it listened.
CLIENT_HEARS = False


def inspect_window(path,start,end,frames=8,width=960,listen=None):
    listen=CLIENT_HEARS if listen is None else listen
    info=probe(Path(path));duration=float(info["format"].get("duration",0))
    if not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end<=duration or end-start>30 or not 2<=frames<=12:
        raise ValueError("Window inside video, <=30s, frames 2..12")
    times=np.linspace(start,min(end-1/1000,duration-.001),frames).tolist()
    has_audio=any(s["codec_type"]=="audio" for s in info["streams"])
    result=observe(path,times,frames,width,start if listen and has_audio else None,min(30,end-start))
    for frame in result["frames"]:
        with Image.open(frame["path"]) as im:
            frame["display_size"]=[im.width,im.height]
        frame["evidence_id"]=f"{result['sha256'][:12]}@{frame['timestamp']:.3f}"
    result.update(window={"start":start,"end":end,"sample_spacing_seconds":(end-start)/(frames-1)},director_guide=DIRECTOR_GUIDE,
        coverage="Sampled frames, not exhaustive action recognition. Request narrower windows when fast motion falls between samples.")
    store.write_json(Path(result["manifest"]),result)
    return result

def crop_detail(path,timestamp,region,width=1280):
    if len(region)!=4 or any(not math.isfinite(v) for v in region) or not 0<=region[0]<region[2]<=1 or not 0<=region[1]<region[3]<=1 or not 160<=width<=1920:
        raise ValueError("region [left,top,right,bottom] normalized 0..1; width 160..1920")
    source=Path(path).resolve(strict=True);info=probe(source);video=next(s for s in info["streams"] if s["codec_type"]=="video")
    w,h=video["width"],video["height"];left,top,right,bottom=region
    x,y=round(left*w),round(top*h);cw,ch=max(1,round(right*w)-x),max(1,round(bottom*h)-y)
    out=store.DATA/"observations"/str(uuid.uuid4());out.mkdir(parents=True)
    target=out/"detail.png"
    if source.suffix.lower() in (".png",".jpg",".jpeg",".webp"):
        with Image.open(source) as im:
            im=ImageOps.exif_transpose(im).convert("RGB");w,h=im.size
            x,y=round(left*w),round(top*h);cw,ch=max(1,round(right*w)-x),max(1,round(bottom*h)-y)
            im=im.crop((x,y,x+cw,y+ch));im.thumbnail((width,width));im.save(target)
    else:
        duration=float(info["format"]["duration"])
        if not math.isfinite(timestamp) or not 0<=timestamp<duration:
            raise ValueError("Timestamp outside video")
        command([FFMPEG,"-y","-v","error","-ss",timestamp,"-i",source,"-frames:v","1","-vf",f"crop={cw}:{ch}:{x}:{y},scale={width}:{width}:force_original_aspect_ratio=decrease",target],timeout=90)
    with Image.open(target) as im: size=[im.width,im.height]
    return {"path":str(target),"sha256":sha256(target),"timestamp":timestamp,"source_size":[w,h],"source_crop_pixels":[x,y,cw,ch],"display_size":size,
        "coordinate_mapping":"For displayed crop pixel (u,v), source pixel = (x+u*cw/display_width,y+v*ch/display_height). Interpret model coordinates relative to supplied image, not original video.","director_guide":DIRECTOR_GUIDE}

def aesthetics_packet(path,start=0,end=None,frames=8,reference_path=None):
    duration=float(probe(Path(path))["format"].get("duration",0));end=min(duration,start+12) if end is None else end
    observed=inspect_window(path,start,end,frames,960,None)
    indexed=index_video(path)
    data=store.read_json(Path(indexed["index_path"]))
    observed["measurements"]=[s for s in data["visual_samples"] if start<=s["timestamp"]<end]
    observed["audio_energy"]=[s for s in data["audio_energy"] or [] if s["end"]>start and s["start"]<end]
    if not CLIENT_HEARS:
        observed["audio_note"]="No audio block sent (the client did not declare audio input at bootstrap): audio_energy is measured; audit_audio and the audio events tools read the rest."
    observed["reference"]=observe(reference_path,max_frames=3,width=960) if reference_path else None
    observed["analysis_status"]="Evidence ready for calling multimodal AI. No hidden model, semantic labels or aesthetic score has been computed."
    store.write_json(Path(observed["manifest"]),observed)
    return observed

def transcribe(path,model="small",language="vi",allow_download=False,vocabulary_hint=""):
    if model not in ("tiny","base","small") or language not in ("vi","en","auto"):
        raise ValueError("model tiny|base|small, language vi|en|auto")
    if len(vocabulary_hint)>4000:
        raise ValueError("vocabulary_hint <=4000 characters")
    source=Path(path).resolve(strict=True);info=probe(source);duration=float(info["format"].get("duration",0))
    if not any(s["codec_type"]=="audio" for s in info["streams"]) or not 0<duration<=3600:
        raise ValueError("Audio track required, <=1 hour")
    from faster_whisper import WhisperModel
    out=store.DATA/"transcripts"/str(uuid.uuid4());out.mkdir(parents=True,exist_ok=True)
    engine=WhisperModel(model,device="cpu",compute_type="int8",download_root=str(store.models_root(f"models--Systran--faster-whisper-{model}")),local_files_only=not allow_download)
    segments,info=engine.transcribe(str(source),language=None if language=="auto" else language,word_timestamps=True,beam_size=5,initial_prompt=vocabulary_hint or None)
    cues=[];words=[]
    for s in segments:
        cues.append({"start":s.start,"end":s.end,"text":s.text.strip()})
        words.extend({"start":w.start,"end":w.end,"text":w.word,"probability":w.probability} for w in s.words or [])
    from .audio import write_srt,group_words
    segment_cues=cues
    if words:
        cues=group_words([{**w,"text":w["text"].strip()} for w in words if w["end"]>w["start"]])
    for compound in re.findall(r"\w+(?:-\w+)+",vocabulary_hint):
        pattern=r"\b"+r"\s*-\s*".join(re.escape(part) for part in compound.split("-"))+r"\b"
        for cue in cues:
            cue["text"]=re.sub(pattern,lambda match:re.sub(r"\s*-\s*","-",match.group(0)),cue["text"],flags=re.I)
    write_srt(out/"captions.srt",cues)
    result={"source":str(source),"source_sha256":sha256(source),"language":info.language,"model":model,"method":"local-faster-whisper-cpu-int8","cues":cues,"segments":segment_cues,"words":words,"srt":str(out/"captions.srt"),
        "limitations":"ASR text and word timestamps are estimates; inspect unclear Vietnamese terms against audio. This is not forced alignment or verified transcription."}
    store.write_json(out/"transcript.json",result);result["manifest"]=str(out/"transcript.json")
    return result


def track_region(path,start,end,region,sampling_fps=8,output_width=1920,output_height=1080):
    """Sparse Lucas-Kanade translation tracker; no semantic object detector."""
    import cv2
    source=Path(path).resolve(strict=True);info=probe(source);duration=float(info["format"].get("duration",0))
    video=next((s for s in info["streams"] if s["codec_type"]=="video"),None)
    if not video or not all(math.isfinite(x) for x in (start,end)) or not 0<=start<end<=duration or end-start>30 or not 2<=sampling_fps<=12:
        raise ValueError("Video window <=30s; sampling_fps 2..12")
    if len(region)!=4 or not all(math.isfinite(v) for v in region) or not 0<=region[0]<region[2]<=1 or not 0<=region[1]<region[3]<=1:
        raise ValueError("Normalized region [left,top,right,bottom] required")
    if not 160<=output_width<=4096 or not 160<=output_height<=4096:
        raise ValueError("Output dimensions 160..4096")
    scale=640/max(video["width"],video["height"]);w=max(2,round(video["width"]*scale/2)*2);h=max(2,round(video["height"]*scale/2)*2)
    out=store.DATA/"tracks"/str(uuid.uuid4());out.mkdir(parents=True)
    raw=out/"frames.rgb"
    # Start anchored frame cadence: frame zero represents the requested source start.
    command([FFMPEG,"-y","-v","error","-ss",start,"-i",source,"-t",end-start,"-vf",f"setpts=PTS-STARTPTS,fps={sampling_fps}:round=down,scale={w}:{h}","-an","-pix_fmt","rgb24","-f","rawvideo",raw],timeout=180)
    pixels=np.memmap(raw,dtype=np.uint8,mode="r").reshape(-1,h,w,3)
    if len(pixels)<2:
        raise ValueError("Tracking window too short")
    gray=cv2.cvtColor(pixels[0],cv2.COLOR_RGB2GRAY);mask=np.zeros((h,w),np.uint8)
    left,top,right,bottom=region;mask[round(top*h):round(bottom*h),round(left*w):round(right*w)]=255
    points=cv2.goodFeaturesToTrack(gray,maxCorners=100,qualityLevel=.01,minDistance=4,mask=mask)
    if points is None or len(points)<4:
        raise ValueError("Region lacks trackable texture; inspect a different region")
    initial=len(points);dx=dy=0.;tracks=[{"timestamp":start,"local_frame":0,"region":region,"retained_feature_fraction":1.,"delta_pixels":[0.,0.]}];lost=None
    for i in range(1,len(pixels)):
        next_gray=cv2.cvtColor(pixels[i],cv2.COLOR_RGB2GRAY)
        moved,status,error=cv2.calcOpticalFlowPyrLK(gray,next_gray,points,None,winSize=(25,25),maxLevel=3)
        if moved is None:
            lost=start+i/sampling_fps;break
        back,back_status,_=cv2.calcOpticalFlowPyrLK(next_gray,gray,moved,None,winSize=(25,25),maxLevel=3)
        valid=(status.ravel()==1)&(back_status.ravel()==1)&(np.linalg.norm(points[:,0]-back[:,0],axis=1)<1.5)&(error.ravel()<30)
        if valid.sum()<4 or valid.sum()/initial<.2:
            lost=start+i/sampling_fps;break
        old=points[valid,0];new=moved[valid,0];delta=np.median(new-old,axis=0)
        if np.linalg.norm(delta)>max(w,h)*.2:
            lost=start+i/sampling_fps;break
        dx+=float(delta[0]);dy+=float(delta[1]);points=moved[valid];gray=next_gray
        bbox=[left+dx/w,top+dy/h,right+dx/w,bottom+dy/h]
        if min(bbox)<0 or max(bbox)>1:
            lost=start+i/sampling_fps;break
        tracks.append({"timestamp":start+i/sampling_fps,"local_frame":round(i*30/sampling_fps),"region":bbox,"retained_feature_fraction":round(float(valid.sum()/initial),3),"delta_pixels":[dx/w*output_width,dy/h*output_height]})
    result={"source":str(source),"sha256":sha256(source),"window":[start,end],"sampling_fps":sampling_fps,"tracks":tracks,"lost_at":lost,
        "keyframes":{"x":[{"frame":t["local_frame"],"value":t["delta_pixels"][0]} for t in tracks],"y":[{"frame":t["local_frame"],"value":t["delta_pixels"][1]} for t in tracks]},
        "keyframe_target_size":[output_width,output_height],"manifest":str(out/"track.json"),
        "limitations":"Sparse feature translation only. Not semantic identity, segmentation, affine scale/rotation or inpainting. Occlusion, cuts and low texture may lose tracking; retained_feature_fraction is surviving features, not confidence in object identity. Keyframes start at layer frame zero; set layer start to this window's timeline position, account for source speed/contain crop and inspect output."}
    store.write_json(out/"track.json",result)
    del pixels
    raw.unlink()
    return result
