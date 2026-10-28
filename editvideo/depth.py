"""Pinned local relative-depth evidence and explicitly approximate depth edits."""
import math,time
from pathlib import Path
from typing import Literal
import cv2,numpy as np
from PIL import Image,ImageOps
from pydantic import BaseModel,ConfigDict,Field,model_validator
from . import store
from .media import FFMPEG,command,probe,sha256

REPO='depth-anything/Depth-Anything-V2-Small-hf'
REVISION='5426e4f0f36572d16453bbda7a8389317b1bef99'
def model_root():return store.models_root('depth-anything-v2-small')/'depth-anything-v2-small'  # the installation's models, wherever the store lives

def install(allow_download=False):
 import httpx
 root=model_root();manifest=root/'install.json'
 if manifest.exists():
  record=store.read_json(manifest)
  if record.get('revision')!=REVISION:raise ValueError('Depth model revision mismatch')
  for name,digest in record['files'].items():
   if not (root/name).exists() or sha256(root/name)!=digest:raise ValueError('Depth model hash changed; restore pinned installation')
  return record
 if not allow_download:raise ValueError('Depth model not installed; install_depth_model(allow_download=true), ~100MB, Apache2.0')
 root.mkdir(parents=True,exist_ok=True)
 with httpx.Client(timeout=120,follow_redirects=True) as client:
  meta=client.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}',params={'blobs':'true'});meta.raise_for_status();meta=meta.json()
  files={}
  for name in ('config.json','preprocessor_config.json','README.md','model.safetensors'):
   response=client.get(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}');response.raise_for_status()
   blob=response.content
   if len(blob)>120*1024*1024:raise ValueError('Unexpected oversized depth asset')
   path=root/name;path.write_bytes(blob);digest=sha256(path)
   remote=next(v for v in meta['siblings'] if v['rfilename']==name).get('lfs',{}).get('sha256')
   if remote and digest!=remote:raise ValueError('Upstream depth weights SHA mismatch')
   files[name]=digest
 record={'repo':REPO,'revision':REVISION,'files':files,'license':'Apache2.0 (upstream model card)','model':'Depth Anything V2 Small HF /24.8M / relative inverse depth'}
 store.write_json(manifest,record);return record

class DepthRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 path:str
 start:float=Field(default=0,ge=0,allow_inf_nan=False)
 end:float|None=Field(default=None,gt=0,allow_inf_nan=False)
 fps:int=Field(default=12,ge=1,le=30)
 width:int=Field(default=512,ge=128,le=960)
 temporal_strength:float=Field(default=.25,ge=0,le=.6,allow_inf_nan=False)
 device:Literal['auto','cpu','cuda']='auto'
 scene_cuts:list[int]=Field(default_factory=list,max_length=100)
 @model_validator(mode='after')
 def bounds(self):
  if self.end is not None and (self.end<=self.start or self.end-self.start>15 or (self.end-self.start)*self.fps>450):raise ValueError('Depth window <=15s/450 frames')
  if any(type(v)!=int or v<=0 for v in self.scene_cuts) or self.scene_cuts!=sorted(set(self.scene_cuts)):raise ValueError('scene_cuts unique increasing frame indices')
  return self

def stabilize(current,previous,gray,previous_gray,strength):
 """Bounded affine scale/shift alignment + reliable flow blend; not a video model."""
 h,w=current.shape;yy,xx=np.mgrid[:h,:w].astype(np.float32)
 backward=cv2.calcOpticalFlowFarneback(gray,previous_gray,None,.5,3,21,3,5,1.2,0)
 forward=cv2.calcOpticalFlowFarneback(previous_gray,gray,None,.5,3,21,3,5,1.2,0)
 mx=xx+backward[:,:,0];my=yy+backward[:,:,1]
 old=cv2.remap(previous,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT101)
 old_gray=cv2.remap(previous_gray,mx,my,cv2.INTER_LINEAR)
 sampled=cv2.remap(forward,mx,my,cv2.INTER_LINEAR)
 reliable=(mx>=0)&(mx<w-1)&(my>=0)&(my<h-1)&(np.linalg.norm(backward+sampled,axis=2)<1.5)&(np.abs(gray.astype(float)-old_gray.astype(float))<24)
 coverage=float(np.mean(reliable));a,b=1.,0.
 if coverage>.3:
  x=current[reliable][::8];y=old[reliable][::8];xm=float(np.median(x));ym=float(np.median(y))
  denom=float(np.mean((x-xm)**2));a=float(np.mean((x-xm)*(y-ym))/max(denom,1e-7))
  if not .5<=a<=2:a=1.
  b=float(np.clip(ym-a*xm,-2*np.std(current),2*np.std(current)))
 aligned=a*current+b
 # Never blend across uncertain occlusions or a detected cut.
 smooth=np.where(reliable,aligned*(1-strength)+old*strength,aligned).astype(np.float32)
 return smooth,{'flow_reliable_fraction':coverage,'scale':a,'shift':b,'blend':strength}

def estimate(task_id,request):
 from .media_tasks import folder,update,check,cancelled
 from .subjects import gpu_lock
 q=DepthRequest.model_validate(request);installed=install(False);source=Path(q.path).resolve(strict=True);digest=sha256(source)
 info=probe(source);s=next(v for v in info['streams'] if v['codec_type']=='video')
 if s.get('color_transfer') in ('smpte2084','arib-std-b67'):raise ValueError('Depth model needs display-referred RGB; tone-map HDR first with process_color')
 image=source.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.tif','.tiff')
 duration=0 if image else float(info['format'].get('duration',0));end=0 if image else q.end or min(duration,q.start+15)
 if not image and (end>duration+.001 or end<=q.start or (end-q.start)*q.fps>450):raise ValueError('Depth source window out of bounds')
 count=1 if image else math.floor((end-q.start)*q.fps+1e-6)
 if count<1 or any(i>=count for i in q.scene_cuts):raise ValueError('Depth window/cut indices invalid')
 out=folder(task_id);frames=out/'frames';frames.mkdir(exist_ok=True);maps=out/'depth';maps.mkdir(exist_ok=True)
 if image:
  rgb=ImageOps.exif_transpose(Image.open(source)).convert('RGB');h=round(rgb.height*q.width/rgb.width);rgb.resize((q.width,h)).save(frames/'000000.jpg',quality=98)
 else:command([FFMPEG,'-y','-v','error','-ss',q.start,'-i',source,'-t',end-q.start,'-vf',f'fps={q.fps},scale={q.width}:-2','-frames:v',count,'-q:v','2','-start_number','0',frames/'%06d.jpg'],cancelled=lambda:cancelled(task_id))
 files=sorted(frames.glob('*.jpg'))
 if len(files)!=count or sha256(source)!=digest:raise ValueError('Depth source changed / incomplete decode')
 update(task_id,progress=.1,message='Loading pinned relative-depth model')
 import torch
 from transformers import AutoImageProcessor,AutoModelForDepthEstimation
 device='cuda' if q.device=='auto' and torch.cuda.is_available() else 'cpu' if q.device=='auto' else q.device
 if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA unavailable')
 lock=gpu_lock(task_id) if device=='cuda' else None;started=time.monotonic();predictions=[];measurements=[];cuts=set(q.scene_cuts);previous_gray=None;scene=0;scenes=[]
 try:
  torch.set_num_threads(4)
  processor=AutoImageProcessor.from_pretrained(str(model_root()),local_files_only=True,use_fast=False)
  model=AutoModelForDepthEstimation.from_pretrained(str(model_root()),local_files_only=True,torch_dtype=torch.float32).to(device).eval()
  with torch.inference_mode():
   for i,file in enumerate(files):
    check(task_id);rgb=Image.open(file).convert('RGB');gray=cv2.cvtColor(np.asarray(rgb),cv2.COLOR_RGB2GRAY)
    inputs=processor(images=rgb,return_tensors='pt').to(device)
    predicted=model(**inputs).predicted_depth
    raw=torch.nn.functional.interpolate(predicted.unsqueeze(1),size=(rgb.height,rgb.width),mode='bicubic',align_corners=False).squeeze().float().cpu().numpy()
    if not np.isfinite(raw).all():raise ValueError('Nonfinite predicted depth')
    # Pixel cut detector complements authored cuts; no cross-cut temporal blend.
    cut=bool(i in cuts or (i>0 and np.mean(np.abs(gray.astype(float)-previous_gray.astype(float)))>45))
    if cut:scene+=1;cuts.add(i)
    metrics={'frame':i,'scene':scene,'cut':cut,'flow_reliable_fraction':None,'scale':1.,'shift':0.,'blend':0.}
    if i and not cut and q.temporal_strength:raw,m=stabilize(raw,predictions[-1],gray,previous_gray,q.temporal_strength);metrics.update(m)
    predictions.append(raw);measurements.append(metrics);scenes.append(scene);previous_gray=gray
    update(task_id,progress=.15+.65*(i+1)/count,message=f'Relative depth frame{i+1}/{count}')
  del model
 finally:
  if lock:lock.release()
  if device=='cuda':torch.cuda.empty_cache()
 array=np.stack(predictions);np.savez_compressed(out/'relative-depth.npz',depth=array,scene=np.asarray(scenes,dtype=np.int32))
 ranges={}
 for scene in sorted(set(scenes)):
  values=array[np.array(scenes)==scene];lo,hi=np.percentile(values,[2,98]);ranges[str(scene)]=[float(lo),float(max(hi,lo+1e-6))]
 records=[]
 for i,raw in enumerate(predictions):
  lo,hi=ranges[str(scenes[i])];normalized=np.clip((raw-lo)/(hi-lo),0,1);path=maps/f'{i:06d}.png';Image.fromarray((normalized*65535).round().astype(np.uint16)).save(path)
  color=cv2.applyColorMap((normalized*255).astype(np.uint8),cv2.COLORMAP_TURBO);cv2.imwrite(str(out/f'depth-preview-{i:06d}.jpg'),color)
  records.append({**measurements[i],'timestamp':q.start+i/q.fps if not image else 0,'source_frame':str(files[i]),'depth_map':str(path),'preview':str(out/f'depth-preview-{i:06d}.jpg'),'mean_normalized_inverse_depth':float(normalized.mean()),'source_frame_sha256':sha256(files[i]),'depth_sha256':sha256(path)})
 fps=1 if image else q.fps;video=out/'depth.mp4'
 command([FFMPEG,'-y','-v','error','-framerate',fps,'-i',out/'depth-preview-%06d.jpg','-frames:v',count,'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-pix_fmt','yuv420p',video],cancelled=lambda:cancelled(task_id))
 manifest={'model':installed,'device':device,'source':str(source),'source_sha256':digest,'is_image':image,'window':[q.start,end],'fps':fps,'frames':count,'dimensions':[array.shape[2],array.shape[1]],'scene_cuts':sorted(cuts),'scene_ranges':ranges,'records':records,'raw_depth_npz':str(out/'relative-depth.npz'),'raw_depth_sha256':sha256(out/'relative-depth.npz'),'elapsed_inference_seconds':time.monotonic()-started,
  'semantics':'Relative inverse depth: high/white is model-estimated near. Scene-global percentile mapping, not per-frame normalization. No meters, calibrated camera or hidden-surface reconstruction. Cut-reset flow/affine alignment/blending is a stabilizer around an image model, not a video-depth neural model. Occlusion/reflective/transparent/thin details require inspection.'}
 store.write_json(out/'depth.json',manifest)
 return {'video':str(video),'manifest':str(out/'depth.json'),'artifacts':{'video':str(video),'manifest':str(out/'depth.json'),'depth_map':records[0]['depth_map']},'summary':{k:manifest[k] for k in ('model','device','frames','dimensions','semantics','elapsed_inference_seconds')}}

def read(task_id,offset=0,limit=24,frames=None):
 from .media_tasks import get
 task=get(task_id)
 if task['kind']!='depth' or task['state']!='completed':raise ValueError('Completed depth task required')
 m=store.read_json(Path(task['result']['manifest']))
 if offset<0 or not 1<=limit<=60:raise ValueError('Depth page invalid')
 indices=frames if frames is not None else [min(offset,m['frames']-1)]
 if not 1<=len(indices)<=8 or any(type(i)!=int or not 0<=i<m['frames'] for i in indices):raise ValueError('Depth frames1..8 inside session')
 return {'manifest':task['result']['manifest'],'total':m['frames'],'records':m['records'][offset:offset+limit],'next_offset':offset+limit if offset+limit<m['frames'] else None,'semantics':m['semantics'],
  'frames':[{'index':i,'timestamp':m['records'][i]['timestamp'],'path':m['records'][i]['source_frame'],'depth_path':m['records'][i]['depth_map'],'preview_path':m['records'][i]['preview']} for i in indices]}

class DepthEditRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 depth_task_id:str
 operation:Literal['focus_blur','atmosphere','parallax','visualize']='focus_blur'
 focus_depth:float=Field(default=.65,ge=0,le=1,allow_inf_nan=False)
 focus_end:float|None=Field(default=None,ge=0,le=1,allow_inf_nan=False)
 focus_width:float=Field(default=.12,ge=.02,le=.5,allow_inf_nan=False)
 blur_sigma:float=Field(default=12,ge=1,le=30,allow_inf_nan=False)
 strength:float=Field(default=.35,ge=0,le=1,allow_inf_nan=False)
 fog_color:str=Field(default='#c5dce8',pattern=r'^#[0-9a-fA-F]{6}$')
 shift_x:float=Field(default=.025,ge=-.06,le=.06,allow_inf_nan=False)
 shift_y:float=Field(default=0,ge=-.06,le=.06,allow_inf_nan=False)
 duration:float=Field(default=4,ge=.5,le=15,allow_inf_nan=False)
 fps:int=Field(default=30,ge=12,le=30)

def edit(task_id,request):
 from .media_tasks import get,folder,check,cancelled,update
 q=DepthEditRequest.model_validate(request);parent=get(q.depth_task_id)
 if parent['kind']!='depth' or parent['state']!='completed':raise ValueError('Completed depth session required')
 m=store.read_json(Path(parent['result']['manifest']));out=folder(task_id);frames=out/'frames';frames.mkdir(exist_ok=True)
 if q.operation=='parallax' and not m['is_image']:raise ValueError('Parallax currently takes a still depth session; real video camera reconstruction is not implemented')
 count=round(q.duration*q.fps) if m['is_image'] else m['frames'];fps=q.fps if m['is_image'] else m['fps'];records=[]
 for i in range(count):
  check(task_id);record=m['records'][0 if m['is_image'] else i]
  if i==0 or not m['is_image']:
   if sha256(record['source_frame'])!=record['source_frame_sha256'] or sha256(record['depth_map'])!=record['depth_sha256']:raise ValueError('Depth/source session artifact changed')
   rgb=np.asarray(Image.open(record['source_frame']).convert('RGB'),dtype=np.float32)/255
   depth=np.asarray(Image.open(record['depth_map']),dtype=np.float32)/65535
  p=i/max(1,count-1);focus=q.focus_depth if q.focus_end is None else q.focus_depth+(q.focus_end-q.focus_depth)*(.5-.5*math.cos(p*math.pi))
  if q.operation=='focus_blur':
   amount=np.clip((np.abs(depth-focus)-q.focus_width)/max(.01,1-q.focus_width),0,1)*q.strength
   # Continuous mixture of three screen blur radii; not an optical bokeh simulator.
   mid=cv2.GaussianBlur(rgb,(0,0),q.blur_sigma*.4);far=cv2.GaussianBlur(rgb,(0,0),q.blur_sigma)
   a=np.minimum(amount*2,1)[:,:,None];b=np.maximum(amount*2-1,0)[:,:,None];result=(rgb*(1-a)+mid*a)*(1-b)+far*b
  elif q.operation=='atmosphere':
   amount=((1-depth)**2*q.strength)[:,:,None];color=np.array([int(q.fog_color[j:j+2],16)/255 for j in (1,3,5)])
   result=rgb*(1-amount)+color*amount
  elif q.operation=='parallax':
   h,w=depth.shape;yy,xx=np.mgrid[:h,:w].astype(np.float32);phase=.5-.5*math.cos(p*math.pi)
   mx=xx+(phase-.5)*q.shift_x*w*(depth-.5)*2;my=yy+(phase-.5)*q.shift_y*h*(depth-.5)*2
   result=cv2.remap(rgb,mx,my,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT101)
  else:result=cv2.cvtColor(cv2.applyColorMap((depth*255).astype(np.uint8),cv2.COLORMAP_TURBO),cv2.COLOR_BGR2RGB)/255
  Image.fromarray((np.clip(result,0,1)*255).round().astype(np.uint8)).save(frames/f'{i:06d}.png')
  records.append({'frame':i,'focus_depth':focus});update(task_id,progress=.1+.75*(i+1)/count,message=f'Depth edit frame{i+1}/{count}')
 video=out/'depth-edit.mp4';command([FFMPEG,'-y','-v','error','-framerate',fps,'-i',frames/'%06d.png','-frames:v',count,'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',video],cancelled=lambda:cancelled(task_id))
 report={'parent_task_id':q.depth_task_id,'request':q.model_dump(),'frames':count,'fps':fps,'records':records,'semantics':'Screen-space depth-guided blur/fog or2.5D still warp. Relative inverse-depth units, not meters/physical DOF/true unseen viewpoint. Parallax uses edge reflection; inspect stretched contours/occlusions and keep motion small. Color/source audio separate; this operation outputs a silent visual clip.'}
 store.write_json(out/'depth-edit.json',report)
 return {'video':str(video),'manifest':str(out/'depth-edit.json'),'artifacts':{'video':str(video),'manifest':str(out/'depth-edit.json')},'report':report}
