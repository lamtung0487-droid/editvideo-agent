"""Real color/3D probes; relative-depth tasks are launched separately."""
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from editvideo import agent,store,media_tasks,scene3d,color_pipeline
from editvideo.media import FFMPEG,command,sha256
from editvideo.code_engine import scaffold
from editvideo.jobs import Worker
from editvideo.observe import observe

def hdr_fixture():
 out=store.ROOT/'outputs';w,h=256,144
 # Physical declared radiance fixture: gray bars20/100/400/1000 nits,100nit NPL.
 values=np.array([.2,1,4,10],np.float32);plane=np.repeat(values,w//4)[None,:].repeat(h,axis=0)
 raw=np.stack([plane]*3).astype('<f4');rawpath=out/'hdr-linear-fixture.gbr';rawpath.write_bytes(raw.tobytes())
 path=out/'hdr-native-fixture.mp4'
 command([FFMPEG,'-y','-v','error','-f','rawvideo','-pixel_format','gbrpf32le','-video_size',f'{w}x{h}','-framerate','30','-i',rawpath,'-vf','loop=loop=29:size=1:start=0,zscale=pin=bt2020:tin=linear:min=gbr:rin=full:p=bt2020:t=smpte2084:m=bt2020nc:r=limited:npl=100,format=yuv420p10le','-frames:v','30','-c:v','libx265','-x265-params','pools=2:frame-threads=1','-pix_fmt','yuv420p10le','-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv',path])
 return path

def color_probe():
 source=hdr_fixture();tasks={}
 for name,q in [('native_hdr',{'path':str(source),'output':'hdr10'}),('tonemap',{'path':str(source),'output':'sdr','tonemap':'hable'}),('sdr_derived',{'path':str(store.ROOT/'outputs/subject-source.mp4'),'input_space':'bt709','input_range':'full','output':'hdr10'})]:
  t=media_tasks.submit('color',q,launch=False);media_tasks.run(t['id']);r=media_tasks.get(t['id']);assert r['state']=='completed',r['error']
  path=Path(r['result']['video']);dest=store.ROOT/'outputs'/f'color-{name}.mp4';shutil.copyfile(path,dest)
  command([FFMPEG,'-v','error','-xerror','-i',dest,'-f','null','-'])
  scope=color_pipeline.inspect(dest,timestamps=[.2]);tasks[name]={'task_id':t['id'],'path':str(dest),'result':r['result'],'scope':scope}
  print(name,scope['scopes'][0]['linear_luma_reference_nits_percentiles'],flush=True)
 store.write_json(store.ROOT/'outputs/color-live-verification.json',tasks)

def three_probe():
 p=agent.from_video(str(store.ROOT/'outputs/widgets-probe-source.mp4'),title='Native3D geometry proof');pid=p['id'];t=p['timeline'];t['shots'][0].update(asset_id=None,text='')
 agent.patch(pid,p['revision'],[{'op':'replace_timeline','timeline':t}]);p=agent.read(pid)
 scene3d.compose(pid,p['revision'],{'id':'depth-planes','preset':'depth_layers','end_frame':t['total_frames']})
 results={}
 for engine in ('remotion','hyperframes'):
  p=store.get_project(pid);store.update_project(pid,{**p['config'],'renderer':engine});scaffold(pid,engine)
  j=store.create_job(pid,'final');Worker().run(j['id']);r=agent.result(j['id']);assert r['state']=='completed',r['error']
  path=store.folder(pid)/'jobs'/j['id']/'final.mp4';dest=store.ROOT/'outputs'/f'scene3d-{engine}.mp4';shutil.copyfile(path,dest)
  packet=observe(dest,timestamps=[.2,1.5,2.8],max_frames=3,width=1280)
  results[engine]={'job_id':j['id'],'video':str(dest),'sha256':sha256(dest),'observation':packet,'report':r['output']['report']};print('three',engine,'complete',flush=True)
 store.write_json(store.ROOT/'outputs/scene3d-live-verification.json',{'project_id':pid,'engines':results})

if __name__=='__main__':
 store.initialize(recover=False)
 if '--3d' in sys.argv:three_probe()
 else:color_probe()
