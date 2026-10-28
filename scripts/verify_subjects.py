"""Real CUDA SAM2/LaMa, immutable correction and alpha composition in both engines."""
import json
import shutil
import sys
import time
import argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from editvideo import store,agent,media_tasks,subjects
from editvideo.media import FFMPEG,command,sha256,probe
from editvideo.code_engine import scaffold
from editvideo.jobs import Worker
from editvideo.observe import observe

def wait(task):
    start=time.monotonic()
    while True:
        r=media_tasks.get(task['id'])
        if r['state'] in media_tasks.TERMINAL:
            assert r['state']=='completed',r
            print(json.dumps({'kind':r['kind'],'id':r['id'],'elapsed':round(time.monotonic()-start,2),'result':r['result']}),flush=True)
            return r
        assert time.monotonic()-start<600,r
        time.sleep(1)

store.initialize(recover=False)
parser=argparse.ArgumentParser();parser.add_argument('--resume-subject');parser.add_argument('--initial-subject');args=parser.parse_args()
output=store.ROOT/'outputs';output.mkdir(exist_ok=True)
source=output/'subject-source.mp4'
command([FFMPEG,'-y','-v','error','-framerate',24,'-i',store.DATA/'verification-footage/bedroom/%05d.jpg','-frames:v',48,'-c:v','libx264','-crf',18,'-pix_fmt','yuv420p',source])
if args.resume_subject:
    refined=media_tasks.get(args.resume_subject)
    initial=media_tasks.get(args.initial_subject) if args.initial_subject else refined
    assert sha256(Path(initial['result']['manifest']))==initial['result']['manifest_sha256']
else:
    initial=wait(media_tasks.submit('subject',{'path':str(source),'end':2,'fps':30,'width':640,'prompts':[
    {'object_id':1,'label':'girl in blue dress','box':[.32,.01,.55,.76]},
    {'object_id':2,'label':'boy at left','box':[.14,.24,.33,.77]}]}))
    initial_hash=initial['result']['manifest_sha256']
    refined=wait(subjects.refine(initial['id'],[{'object_id':1,'label':'girl in blue dress','frame':0,'box':[.32,.01,.55,.76],'points':[[.42,.43],[.24,.5]],'labels':[1,0]}]))
    assert sha256(media_tasks.folder(initial['id'])/'subjects.json')==initial_hash
read=subjects.read_session(refined['id'],1,frames=[0,30,59])
for f in read['frames']:shutil.copyfile(f['path'],output/f"subject-overlay-{f['index']}.png")
manifest=store.read_json(Path(refined['result']['manifest']));assert manifest['device']=='cuda'
assert all(len(track)==60 for track in manifest['tracks'].values())
assert manifest['tracks']['1'][0]['area_fraction']>.02
foreground=wait(media_tasks.submit('mask_edit',{'subject_task_id':refined['id'],'object_ids':[1,2],'operation':'foreground','dilation':0,'feather':1}))
inpaint=wait(media_tasks.submit('mask_edit',{'subject_task_id':refined['id'],'object_ids':[2],'operation':'remove','backend':'lama','dilation':5,'feather':2}))
reframe=wait(media_tasks.submit('mask_edit',{'subject_task_id':refined['id'],'object_ids':[1],'operation':'reframe','dilation':0,'feather':0,'output_width':360,'output_height':640}))
shutil.copyfile(reframe['result']['artifacts']['video'],output/'subject-reframe.mp4')
assert inpaint['result']['checkpoint_sha256']==sha256(store.DATA/'models/big-lama.pt')
shutil.copyfile(foreground['result']['artifacts']['video'],output/'subjects-foreground.webm')
shutil.copyfile(inpaint['result']['artifacts']['video'],output/'subject-inpaint.mp4')
blue=output/'subject-background.mp4'
command([FFMPEG,'-y','-v','error','-f','lavfi','-i','color=c=0x1b2642:s=640x360:r=30:d=2','-c:v','libx264',blue])
p=agent.from_video(str(blue));pid=p['id']
before=sha256(store.folder(pid)/'plan/voice.wav')
attached=media_tasks.attach(foreground['id'],pid,p['revision'],tags='tracked subjects with transparent background')
assert attached['plan_preserved'] and attached['asset']['alpha']
assert sha256(store.folder(pid)/'plan/voice.wav')==before
agent.patch(pid,attached['revision'],[{'op':'update_shot','shot_id':'source-001','changes':{'motion':'hold'}},{'op':'upsert_layer','layer':{
    'id':'subjects','kind':'video','asset_id':attached['asset']['id'],'start_frame':0,'end_frame':60,'x':0,'y':0,'width':1,'height':1,'fit':'contain'}}])
reports={}
for engine in ('remotion','hyperframes'):
    scaffold(pid,engine)
    p=store.get_project(pid);store.update_project(pid,{**p['config'],'renderer':engine})
    j=store.create_job(pid,'preview');Worker().run(j['id']);r=agent.result(j['id']);assert r['state']=='completed',r
    video=output/f'subject-composite-{engine}.mp4';shutil.copyfile(store.folder(pid)/'jobs'/j['id']/'preview.mp4',video)
    obs=observe(str(video),[0,.9,1.8],3,640)
    corners=[]
    for f in obs['frames']:
        arr=np.asarray(Image.open(f['path']));corner=arr[:15,:15].mean((0,1));corners.append(corner.tolist())
        assert np.max(np.abs(corner-np.array([27,38,66])))<12,(engine,corner)
        assert arr[50:300,100:340].std()>20,'Subjects missing or alpha flattened'
    reports[engine]={'video':str(video),'job_id':j['id'],'sha256':sha256(video),'corner_rgb':corners,'full_decode':True}
    print(json.dumps({'engine':engine,'alpha_composite_passed':True}),flush=True)
store.write_json(output/'subject-verification.json',{'source':str(source),'source_origin':'https://github.com/facebookresearch/sam2/tree/2b90b9f5ceec907a1c18123530e92e794ad901a4/notebooks/videos/bedroom','subject_tasks':[initial['id'],refined['id']],'correction_verified':initial['id']!=refined['id'],'foreground_task':foreground['id'],'inpaint_task':inpaint['id'],'reframe_task':reframe['id'],'project_id':pid,'mask_frames':60,'cuda':True,'engines':reports,'limits':'LaMa framewise; manual mask inspection required. No claim of perfect occlusion/re-ID or temporal neural inpainting.'})
