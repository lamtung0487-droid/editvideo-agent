"""Explicit transfer/primaries transforms and bounded .cube LUT processing.

Chromium compositions are SDR. Native HDR footage can retain its dynamic range
through this independent float/10-bit media pipeline; SDR→PQ is labelled derived.
"""
import json,math,shutil
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import BaseModel,ConfigDict,Field,model_validator
from . import store
from .media import FFMPEG,command,probe,sha256
from .color_log import LOG_SPACES

LUT_ROOT=store.ROOT/'assets/luts'
SPACES={'bt709':('bt709','bt709','bt709'),'srgb':('bt709','iec61966-2-1','gbr'),
        'hdr10':('bt2020','smpte2084','bt2020nc'),'hlg':('bt2020','arib-std-b67','bt2020nc'),
        # Rec.601 SD, as many web encoders still tag SDR video (PAL 625 / NTSC 525 primaries, the 601 curve)
        'bt601_625':('bt470bg','601','470bg'),'bt601_525':('smpte170m','601','170m')}
SDR_VIDEO=('bt709','bt601_625','bt601_525')
SDR_SPACES=(*SDR_VIDEO,'srgb')
LUTS={'identity':'No creative change / technical identity',
 'documentary':'Soft documentary contrast, restrained saturation',
 'warm_story':'Warm narrative illustration; inspect skin and neutral highlights',
 'cool_science':'Cool restrained graphic/illustration',
 'forest':'Restrained natural green illustration',
 'monochrome':'Luminance-based monochrome, not evidence color matching'}

from functools import lru_cache
@lru_cache(maxsize=1)
def backend_capabilities():
 import re
 try:
  filters=command([FFMPEG,'-hide_banner','-filters'],timeout=15);encoders=command([FFMPEG,'-hide_banner','-encoders'],timeout=15)
  available={name:bool(re.search(r'\s'+name+r'\s',filters)) for name in ('zscale','tonemap','lut3d','exposure')}
  return {'filters':available,'hevc_10bit_encoder':bool(re.search(r'\slibx265\s',encoders)),'native_hdr_media':all(available.values()) and 'libx265' in encoders}
 except Exception as e:return {'native_hdr_media':False,'error':str(e)[:250]}

def build_luts():
 LUT_ROOT.mkdir(parents=True,exist_ok=True);manifest=[];size=17
 for name,description in LUTS.items():
  lines=[f'TITLE "EditVideo {name}"',f'LUT_3D_SIZE {size}','DOMAIN_MIN 0 0 0','DOMAIN_MAX 1 1 1']
  for b in np.linspace(0,1,size):
   for g in np.linspace(0,1,size):
    for r in np.linspace(0,1,size):
     x=np.array([r,g,b]);lum=float(x@np.array([.2126,.7152,.0722]))
     if name=='documentary':x=.94*x+.06*lum;x=.96*x+.02
     elif name=='warm_story':x=x*np.array([1.025,1.005,.965])+np.array([.009,.004,0])*(1-x)
     elif name=='cool_science':x=x*np.array([.97,1.005,1.025])+np.array([0,.003,.009])*(1-x)
     elif name=='forest':x=.96*x+.04*lum;x*=np.array([.985,1.012,.985])
     elif name=='monochrome':x[:]=lum
     lines.append(' '.join(f'{v:.8f}' for v in np.clip(x,0,1)))
  path=LUT_ROOT/(name+'.cube');path.write_text('\n'.join(lines)+'\n',encoding='ascii')
  manifest.append({'id':name,'description':description,'file':path.name,'sha256':sha256(path),'size':size,'domain':'normalized display-referred BT.709 RGB; not scene-linear/HDR','origin':'Original procedural EditVideo transform; no third-party look pack'})
 store.write_json(LUT_ROOT/'manifest.json',{'luts':manifest})
 return manifest

def catalog():
 manifest=store.read_json(LUT_ROOT/'manifest.json')
 atlas=store.atlas_path('color-lut-atlas.json')
 previews={r['id']:r for r in store.read_json(atlas)['entries']} if atlas.exists() else {}
 for lut in manifest['luts']:
  pv=previews.get(lut['id']);lut['preview']={**pv,'path':store.repo_path(pv['path'])} if pv else None
 return {'input_spaces':list(SPACES),'outputs':['sdr','hdr10'],'luts':manifest['luts'],
  'scope':'zscale linear-float primaries/transfer conversion, exposure in linear light, HDR→SDR tonemap; display-BT709 .cube LUT with tetrahedral interpolation. HDR10 uses HEVC10bit/PQ/BT2020. Browser composition remains SDR; an SDR-derived HDR encode cannot recover highlights/gamut absent in the source.'}

def read_cube(path):
 path=Path(path).resolve(strict=True)
 if not path.is_file() or path.stat().st_size>8*1024*1024:raise ValueError('Local .cube <=8MB required')
 size=None;values=[];domain_min=[0,0,0];domain_max=[1,1,1]
 for line in path.read_text(encoding='utf-8-sig').splitlines():
  line=line.split('#')[0].strip()
  if not line:continue
  parts=line.split();key=parts[0]
  if key=='TITLE':continue
  if key=='LUT_3D_SIZE':
   if size is not None or len(parts)!=2:raise ValueError('Invalid LUT size')
   size=int(parts[1]);continue
  if key in ('DOMAIN_MIN','DOMAIN_MAX'):
   if len(parts)!=4:raise ValueError('Invalid LUT domain')
   if key=='DOMAIN_MIN':domain_min=list(map(float,parts[1:]))
   else:domain_max=list(map(float,parts[1:]))
   continue
  if len(parts)!=3:raise ValueError('Only3D .cube is supported; no1D/shaper/unknown directives')
  row=list(map(float,parts))
  if any(not math.isfinite(v) or not 0<=v<=1 for v in row):raise ValueError('This display LUT requires finite outputs0..1')
  values.append(row)
 if size is None or not 2<=size<=65 or len(values)!=size**3 or domain_min!=[0,0,0] or domain_max!=[1,1,1]:raise ValueError('Display .cube requires size 2..65, N^3 rows, normalized 0..1 domain')
 return size,np.asarray(values,dtype=np.float32)

class ColorRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 path:str
 input_space:Literal['auto','bt709','bt601_625','bt601_525','srgb','hdr10','hlg','slog3','logc3','vlog','logc4','log3g10','applelog','flog2','bmdfilm5']='auto'
 input_range:Literal['auto','limited','full']='auto'
 start:float=Field(default=0,ge=0,allow_inf_nan=False)
 end:float|None=Field(default=None,gt=0,allow_inf_nan=False)
 output:Literal['sdr','hdr10']='sdr'
 lut_id:str|None=None
 lut_path:str|None=None
 lut_strength:float=Field(default=1,ge=0,le=1,allow_inf_nan=False)
 exposure:float=Field(default=0,ge=-2,le=2,allow_inf_nan=False)
 tonemap:Literal['hable','mobius','reinhard','linear','clip']='hable'
 source_peak_nits:float=Field(default=1000,ge=100,le=10000,allow_inf_nan=False)
 paper_white_nits:float=Field(default=203,ge=80,le=400,allow_inf_nan=False)
 crf:int=Field(default=18,ge=12,le=28)
 # Primary grade (color_grade.Grade): levels, white balance from a neutral region, contrast/pivot, luma curve, saturation,
 # split tone, sharpen, vignette. Applied in the BT.709 display domain before any creative LUT.
 grade:dict|None=None
 # Scene-referred node graph (color_graph.Graph): input transform → grade nodes in ACEScct → look under the output
 # transform (Cineon print LUTs) → output transform; tracked windows. Replaces grade/log developing; SDR only.
 graph:dict|None=None

 @model_validator(mode='after')
 def options(self):
  if self.graph is not None:
   from .color_graph import Graph
   G=Graph.model_validate(self.graph)
   if self.grade is not None:raise ValueError('Use either graph (scene-referred) or grade (display-referred), not both')
   if self.output=='hdr10' or self.input_space in ('hdr10','hlg'):raise ValueError('The colour graph grades log or SDR sources to SDR; tone-map HDR first')
   ids={l['id']:l for l in catalog()['luts']}
   for n in [*G.nodes,*[m for w in G.nodes for m in w.nodes]]:
    if n.op=='look':
     if n.lut_id:
      if n.lut_id not in ids:raise ValueError(f'Unknown look lut_id {n.lut_id}')
      want=ids[n.lut_id].get('input','display')
      if want!=n.input:raise ValueError(f'LUT {n.lut_id} expects {want} input; set the look input to {want}')
     else:read_cube(n.lut_path)
  if self.grade is not None:
   from .color_grade import Grade
   Grade.model_validate(self.grade)
   if self.output=='hdr10':raise ValueError('The primary grade works on SDR display values; grade before HDR delivery is not supported')
  if self.end is not None and not self.start<self.end<=self.start+120:raise ValueError('Color window0..120s')
  if self.lut_id and self.lut_path:raise ValueError('Choose registry LUT or custom .cube')
  if self.lut_id and self.lut_id not in LUTS:raise ValueError('Unknown display lut_id (Cineon/print looks go in a graph look node)')
  if self.output=='hdr10' and (self.lut_id or self.lut_path):raise ValueError('Creative LUTs have SDR display domain; do not apply them to native HDR output')
  if self.input_space in LOG_SPACES:
   if self.output=='hdr10':raise ValueError('Camera log input is developed to SDR Rec.709 here; HDR delivery from log is not supported')
   if self.input_range=='auto':raise ValueError('Declare input_range for camera log footage (most cameras record full range; check the camera setting)')
  return self

def input_color(q,stream,image=False):
 space=q.input_space
 if space in LOG_SPACES:  # declared camera log: decode RGB only, the log LUT does the rest
  matrix='gbr' if stream.get('pix_fmt','').startswith(('rgb','gbr','rgba')) else 'bt709'
  return space,None,None,matrix,q.input_range
 if space=='auto':
  p,trc=stream.get('color_primaries'),stream.get('color_transfer')
  if p=='bt2020' and trc=='smpte2084':space='hdr10'
  elif p=='bt2020' and trc=='arib-std-b67':space='hlg'
  elif p=='bt709' and trc=='bt709':space='bt709'
  elif p=='bt709' and trc=='iec61966-2-1':space='srgb'
  elif p in ('bt470bg','smpte170m') and trc in ('smpte170m','bt709','bt470bg','bt470m'):space='bt601_625' if p=='bt470bg' else 'bt601_525'
  else:raise ValueError('Source color tags missing/unsupported; declare input_space and range from known source. Never infer HDR from filename or bit depth.')
 range=q.input_range
 if range=='auto':
  if image or stream.get('color_range')=='pc':range='full'
  elif stream.get('color_range')=='tv':range='limited'
  else:raise ValueError('Source range untagged; declare input_range limited/full from source, not filename')
 primaries,trc,matrix=SPACES[space]
 tagged={'bt709':'bt709','bt470bg':'470bg','smpte170m':'170m'}.get(stream.get('color_space'))
 if tagged and space in SDR_VIDEO:matrix=tagged  # the stream's own YUV matrix (HD primaries over a 601 matrix happen)
 if stream.get('pix_fmt','').startswith(('rgb','gbr','rgba')):matrix='gbr'
 return space,primaries,trc,matrix,range

def filter_graph(q,stream,image=False,lut_name=None,grade_name=None,spatial=(),log_name=None):
 space,p,t,m,r=input_color(q,stream,image);npl=100
 if space in LOG_SPACES:
  f=[f'zscale=min={m}:rin={r}:m=gbr:r=full','format=gbrpf32le',f'lut3d=file={log_name}:interp=tetrahedral']
  if grade_name:f.append(f'lut3d=file={grade_name}:interp=tetrahedral')
  if lut_name:f.append(f'lut3d=file={lut_name}:interp=tetrahedral')
  f+=['zscale=pin=bt709:tin=bt709:min=gbr:rin=full:p=bt709:t=bt709:m=bt709:r=limited:dither=error_diffusion','format=yuv420p',*spatial]
  return ','.join(f),space
 filters=[f'zscale=pin={p}:tin={t}:min={m}:rin={r}:p={"bt2020" if q.output=="hdr10" else "bt709"}:t=linear:m=gbr:r=full:npl={npl}','format=gbrpf32le']
 if q.exposure:filters.append(f'exposure=exposure={q.exposure}')
 if q.output=='hdr10' and space in SDR_SPACES:
  filters.append(f'exposure=exposure={math.log2(q.paper_white_nits/100)}')
 if q.output=='sdr':
  if space in ('hdr10','hlg'):filters.append(f'tonemap=tonemap={q.tonemap}:desat=0:peak={q.source_peak_nits*2**q.exposure/100}')
  filters.append('zscale=p=bt709:t=bt709:m=gbr:r=full')
  if grade_name:filters.append(f"lut3d=file={grade_name}:interp=tetrahedral")
  if lut_name:filters.append(f"lut3d=file={lut_name}:interp=tetrahedral")
  filters.extend(['zscale=p=bt709:t=bt709:m=bt709:r=limited:dither=error_diffusion','format=yuv420p',*spatial])
 else:filters.extend([f'zscale=p=bt2020:t=smpte2084:m=bt2020nc:r=limited:npl={npl}:dither=error_diffusion','format=yuv420p10le'])
 return ','.join(filters),space

def process(task_id,request):
 from .media_tasks import folder,check,cancelled,update
 q=ColorRequest.model_validate(request);source=Path(q.path).resolve(strict=True);digest=sha256(source);out=folder(task_id)
 info=probe(source);stream=next(s for s in info['streams'] if s['codec_type']=='video')
 image=source.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.tif','.tiff')
 duration=1 if image else float(info['format'].get('duration',0));end=q.end or duration
 if not image and (end>duration+.01 or end-q.start>120 or end<=q.start):raise ValueError('Color window outside source / max120s')
 lut_name=None
 if q.lut_id or q.lut_path:
  lut=Path(q.lut_path) if q.lut_path else LUT_ROOT/(q.lut_id+'.cube');size,values=read_cube(lut)
  if q.lut_id:
   spec=next(s for s in catalog()['luts'] if s['id']==q.lut_id)
   if sha256(lut)!=spec['sha256']:raise ValueError('Registry LUT hash changed')
  # Identity blending is evaluated in the declared display domain.
  identity=np.array([[r,g,b] for b in np.linspace(0,1,size) for g in np.linspace(0,1,size) for r in np.linspace(0,1,size)])
  values=identity*(1-q.lut_strength)+values*q.lut_strength
  (out/'look.cube').write_text(f'LUT_3D_SIZE {size}\n'+'\n'.join(' '.join(f'{v:.8f}' for v in row) for row in values)+'\n',encoding='ascii');lut_name='look.cube'
 grade_name,spatial,grade_report=None,(),None
 if q.grade is not None:
  from .color_grade import Grade,cube,neutral_gains,spatial_filters
  g=Grade.model_validate(q.grade)
  if g.neutral_region:
   if input_color(q,stream,image)[0] not in SDR_SPACES:raise ValueError('neutral_region white balance needs an SDR (Rec.709/601, sRGB) source; develop log/HDR first, then grade that file')
   from .scopes import _frame
   g.neutral_gains=neutral_gains(_frame(source,q.start if not image else 0),g.neutral_region)
  (out/'grade.cube').write_text(cube(g),encoding='ascii');grade_name='grade.cube';spatial=tuple(spatial_filters(g));grade_report=g.model_dump()
 if q.graph is not None:
  return _process_graph(task_id,q,source,digest,out,info,stream,image,end,lut_name)
 log_name=None
 if q.input_space in LOG_SPACES:
  from .color_log import cube as log_cube
  (out/'log_to_709.cube').write_text(log_cube(q.input_space,q.exposure),encoding='ascii');log_name='log_to_709.cube'
 vf,space=filter_graph(q,stream,image,lut_name,grade_name,spatial,log_name);update(task_id,progress=.15,message='Converting declared color through linear float RGB')
 target=out/'color.mp4';input_args=['-loop','1','-framerate','30'] if image else ['-ss',q.start]
 video_args=['-c:v','libx264','-crf',q.crf,'-preset','fast','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv']
 if q.output=='hdr10':video_args=['-c:v','libx265','-crf',q.crf,'-preset','fast','-pix_fmt','yuv420p10le','-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv','-x265-params','colorprim=9:transfer=16:colormatrix=9:range=limited:pools=4:frame-threads=2']
 command([FFMPEG,'-y','-v','error',*input_args,'-i',source,'-t',1 if image else end-q.start,'-map','0:v:0','-map','0:a?','-vf',vf,*video_args,'-c:a','aac','-b:a','192k','-movflags','+faststart',target],cwd=out,cancelled=lambda:cancelled(task_id),log=out/'ffmpeg.log')
 if sha256(source)!=digest:raise ValueError('Source changed during color processing')
 actual=probe(target);vs=next(s for s in actual['streams'] if s['codec_type']=='video')
 if q.output=='hdr10' and not (vs.get('color_primaries')=='bt2020' and vs.get('color_transfer')=='smpte2084' and vs.get('pix_fmt')=='yuv420p10le'):raise ValueError('HDR10 output precision/tags verification failed')
 report={'source':str(source),'source_sha256':digest,'request':q.model_dump(),'resolved_input':space,'filter_graph':vf,'actual_stream':vs,'grade':grade_report,
  'hdr_origin':'native_HDR_transform' if q.output=='hdr10' and space in ('hdr10','hlg') else 'SDR_derived_PQ_container' if q.output=='hdr10' else 'SDR_display_output',
  'limits':'No invented MaxCLL/mastering-display metadata. PQ/BT2020/10bit stream does not prove display brightness or new recovered highlights. Browser composition is SDR; tone-map native HDR for authoring. LUTs apply to normalized display BT709 RGB only. source_peak_nits is a declared tone-map setting, not a measurement.'}
 store.write_json(out/'color.json',report);check(task_id)
 return {'video':str(target),'manifest':str(out/'color.json'),'artifacts':{'video':str(target),'manifest':str(out/'color.json')},'report':report}

def _process_graph(task_id,q,source,digest,out,info,stream,image,end,lut_name):
 from fractions import Fraction
 from .media_tasks import cancelled,update,check
 from . import color_graph as cg
 G=cg.Graph.model_validate(q.graph);space,p,t,m,r=input_color(q,stream,image)
 cubes,wins,checks=cg.bake(G,space,q.exposure);names=[]
 for k,text in enumerate(cubes):
  name='graph.cube' if k==0 else f'window{k}.cube';(out/name).write_text(text,encoding='ascii');names.append(name)
 W,H=int(stream['width']),int(stream['height']);rate='30' if image else stream.get('r_frame_rate','30/1');fps=float(Fraction(rate))
 n_frames=30 if image else max(1,round((end-q.start)*fps));masks=[]
 for k,w in enumerate(wins,1):
  update(task_id,progress=.1,message=f'Rendering window mask {k}')
  masks.append(cg.write_mask(w,out/f'mask{k}.mkv',n_frames,rate,q.start,W,H,FFMPEG))
 fc=cg.filter_complex(m,r,names,list(range(1,len(names))),W,H,lut_name)
 update(task_id,progress=.2,message='Grading through the scene-referred graph')
 target=out/'color.mp4';input_args=['-loop','1','-framerate','30'] if image else ['-ss',q.start]
 mask_args=[a for k in range(len(masks)) for a in ('-i',out/f'mask{k+1}.mkv')]
 command([FFMPEG,'-y','-v','error',*input_args,'-i',source,*mask_args,'-t',1 if image else end-q.start,'-filter_complex',fc,'-map','[out]','-map','0:a?',
  '-c:v','libx264','-crf',q.crf,'-preset','fast','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv','-c:a','aac','-b:a','192k','-movflags','+faststart',target],
  cwd=out,cancelled=lambda:cancelled(task_id),log=out/'ffmpeg.log')
 if sha256(source)!=digest:raise ValueError('Source changed during color processing')
 vs=next(s for s in probe(target)['streams'] if s['codec_type']=='video')
 report={'source':str(source),'source_sha256':digest,'request':q.model_dump(),'resolved_input':space,'filter_graph':fc,'actual_stream':vs,'graph_checks':checks,'windows':masks,
  'hdr_origin':'SDR_display_output','limits':'Scene-referred maths on Rec.709 primaries (ACEScct curve, not AP1). Window merge happens after the chain: exact inside/outside, feather zone mixes final results. Masks render at quarter resolution (feather >= 6 px).'}
 store.write_json(out/'color.json',report);check(task_id)
 return {'video':str(target),'manifest':str(out/'color.json'),'artifacts':{'video':str(target),'manifest':str(out/'color.json')},'report':report}

def inspect(path,input_space='auto',input_range='auto',timestamps=None):
 import uuid
 from PIL import Image,ImageDraw
 source=Path(path).resolve(strict=True);info=probe(source);s=next(v for v in info['streams'] if v['codec_type']=='video')
 tags={k:s.get(k) for k in ('codec_name','pix_fmt','bits_per_raw_sample','color_range','color_space','color_transfer','color_primaries','side_data_list')}
 q=ColorRequest(path=str(source),input_space=input_space,input_range=input_range)
 try:space,p,t,m,r=input_color(q,s,source.suffix.lower() in ('.png','.jpg','.jpeg','.webp'))
 except ValueError as e:return {'source_sha256':sha256(source),'metadata':tags,'scopes':[],'needs_declaration':str(e)}
 duration=float(info['format'].get('duration',1));times=timestamps or [min(.2,duration/2)]
 if not 1<=len(times)<=8 or any(not math.isfinite(v) or not 0<=v<duration for v in times):raise ValueError('Scopes require1..8 timestamps inside source')
 out=store.DATA/'observations'/str(uuid.uuid4());out.mkdir(parents=True);records=[]
 for i,at in enumerate(times):
  raw=out/f'linear-{i}.bin'
  # Resize encoded samples before linear float conversion: swscale float resize
  # can clamp highlights above1 and falsely report a100nit maximum.
  vf=f'zscale=w=256:h=144:filter=bilinear:pin={p}:tin={t}:min={m}:rin={r}:p=bt2020:t=linear:m=gbr:r=full:npl=100,format=gbrpf32le'
  command([FFMPEG,'-y','-v','error','-ss',at,'-i',source,'-frames:v','1','-vf',vf,'-pix_fmt','gbrpf32le','-f','rawvideo',raw])
  planes=np.fromfile(raw,dtype='<f4').reshape(3,144,256);rgb=planes[[2,0,1]];y=np.einsum('i,ihw->hw',[.2627,.678,.0593],rgb)
  # Absolute nits only for declared PQ; SDR is interpreted at100nit reference.
  samples=np.maximum(y,0)*100
  rec={'timestamp':at,'linear_luma_reference_nits_percentiles':{str(k):float(np.percentile(samples,k)) for k in (0,1,50,95,99,100)},'max_RGB_reference_nits':float(np.max(rgb)*100),
       'scale':'PQ absolute nits' if space=='hdr10' else 'HLG scene-relative interpreted by zscale at100nit NPL' if space=='hlg' else 'SDR linear relative to100nit reference, not measured display output'}
  im=Image.new('RGB',(768,320),'#101820');draw=ImageDraw.Draw(im);norm=np.clip(np.log1p(samples)/np.log1p(10000),0,1)
  for x in range(256):
   for v in norm[:,x]:draw.point((x*3,280-int(v*240)),fill='#81e6be')
  draw.text((12,12),f'{at:.2f}s | log luminance waveform | source declared {space}',fill='white');draw.text((12,295),f'Max Y reference nits {samples.max():.2f} / max RGB {rgb.max()*100:.2f}',fill='white')
  image=out/f'scope-{i}.png';im.save(image);rec['path']=str(image);records.append(rec)
 return {'source':str(source),'source_sha256':sha256(source),'metadata':tags,'resolved_input':space,'scopes':records,'frames':[{'index':i,'timestamp':r['timestamp'],'path':r['path']} for i,r in enumerate(records)],'limits':'Sampled/downscaled scope, not whole-film MaxCLL/MaxFALL certification or aesthetic score. Transfer interpretation requires trustworthy source declaration/tags.'}


def cast(path, start=0.0, seconds=None, samples=10):
    """A clip's colour cast: the mean R, G, B of its mid-tone pixels (luma 40-220) over `samples` frames, relative to
    their luma. {"gains": [r, g, b] that would make the mid-tones neutral, "offset": red-minus-luma, "chroma": how
    coloured the clip is}. Archive reels swing from green-cyan to magenta between shots (a montage measured -34.8 to
    +35.5 red-vs-luma)."""
    d = float(probe(Path(path))["format"].get("duration", 0))
    seconds = d - start if seconds is None else min(seconds, d - start)
    import subprocess
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(.1, seconds):.3f}", "-i", str(path), "-vf",
                          f"fps={max(.2, samples / max(seconds, .1)):.4f},scale=160:-2,format=rgb24", "-frames:v", str(samples), "-f", "rawvideo", "-"],
                         capture_output=True, timeout=600).stdout
    px = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.float64)
    y = px @ np.array([.2126, .7152, .0722])
    mid = px[(y > 40) & (y < 220)]
    if len(mid) < 100:
        return {"gains": [1.0, 1.0, 1.0], "offset": 0.0, "chroma": 0.0}
    m, ym = mid.mean(0), float((mid @ np.array([.2126, .7152, .0722])).mean())
    return {"gains": [round(float(ym / max(c, 1)), 4) for c in m], "offset": round(float(m[0] - ym), 2),
            "chroma": round(float(np.abs(mid - (mid @ np.array([.2126, .7152, .0722]))[:, None]).mean()), 2)}


def neutral(path, strength=.6, out_dir=None):
    """A copy of a clip with its colour cast taken out at `strength` (0..1) before a shared look: per-channel gains
    toward neutral mid-tones, clamped to 0.8..1.25, luma kept. A black-and-white reel stays as it is. Cached by the
    clip's bytes and strength; returns the path (the original when there is nothing to correct)."""
    c = cast(path)
    g = [min(1.25, max(.8, v ** strength)) for v in c["gains"]]
    if max(abs(v - 1) for v in g) < .015:
        return str(path)
    out_dir = Path(out_dir) if out_dir else store.DATA / "cache" / "neutral"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{sha256(Path(path))[:20]}-n{int(strength * 100)}{Path(path).suffix}"
    if not out.is_file():
        tmp = out.with_name(out.stem + ".part" + out.suffix)
        info = probe(Path(path))
        has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
        command([FFMPEG, "-v", "error", "-y", "-i", str(path), "-vf", f"colorchannelmixer=rr={g[0]:.4f}:gg={g[1]:.4f}:bb={g[2]:.4f}",
                 "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-pix_fmt", "yuv420p", *(["-c:a", "copy"] if has_audio else ["-an"]),
                 "-movflags", "+faststart", str(tmp)])
        tmp.replace(out)
    from . import ledger
    if ledger.find_entry(path) and not ledger.find_entry(out):  # the corrected copy keeps its source's licence and credit
        ledger.register_cut(out, path, notes=f"colour cast neutralised at {strength:.0%} (gains {g[0]:.3f}/{g[1]:.3f}/{g[2]:.3f})")
    return str(out)
