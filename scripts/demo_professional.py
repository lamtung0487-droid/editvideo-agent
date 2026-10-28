"""Professional recipes in portrait and landscape; real narration, no studio."""
import asyncio,json,os,shutil,sys,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store,media_tasks
from editvideo.media import sha256,FFMPEG,command,probe
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

REFINE='--refine-existing' in sys.argv
BASE='2824c0e3-88de-4cf8-8b6b-266bd5d283f6'
BOUNDS=[0,205,419,672,932,1264,1585]

async def main():
 params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/'run.py')],env={**os.environ,'PYTHONIOENCODING':'utf-8'})
 base=store.folder(BASE);previous=store.read_json(base/'plan/timeline.json');words=store.read_json(base/'plan/words.json')
 async with stdio_client(params) as (reader,writer):
  async with ClientSession(reader,writer) as client:
   await client.initialize()
   async def call(name,args):
    r=await client.call_tool('editvideo_'+name,args)
    if r.isError:raise RuntimeError(str(r.content))
    return r.structuredContent or r.content
   async def job(pid,kind):
    j=await call('submit_job',{'project_id':pid,'kind':kind});print('job',kind,j['id'],flush=True)
    while True:
     r=await call('get_job',{'job_id':j['id']})
     if r['state'] not in ('queued','running'):
      assert r['state']=='completed',r['error'];return r
     await asyncio.sleep(4)
   records=store.read_json(store.ROOT/'outputs/professional-demo-projects.json') if REFINE else {}
   formats=[('tiktok','vertical')] if '--tiktok-only' in sys.argv else [('tiktok','vertical'),('youtube_long','landscape')]
   for platform,profile in formats:
    if REFINE:
     rec=records[platform];pid=rec['project_id'];ids=rec['assets'];voice=store.folder(pid)/'plan/voice.wav'
    else:
     p=await call('create_project',{'config':{'title':'AI dựng video: chuyển động cần liền mạch','script':store.get_project(BASE)['config']['script'],'profile':profile,'renderer':'remotion','captions':True}});pid=p['id']
     audio=await call('import_media',{'project_id':pid,'path':str(base/'plan/voice.wav'),'tags':'verified existing Vietnamese narration'})
     p=await call('read_project',{'project_id':pid})
     await call('configure_project',{'project_id':pid,'base_revision':p['revision'],'changes':{'narration_id':audio['id']}})
     await job(pid,'plan')
     voice=store.folder(pid)/'plan/voice.wav'
     with wave.open(str(voice)) as a,wave.open(str(base/'plan/voice.wav')) as b:
      assert (a.getframerate(),a.getnchannels(),a.getsampwidth())==(b.getframerate(),b.getnchannels(),b.getsampwidth())
      assert a.readframes(a.getnframes())==b.readframes(b.getnframes())
     store.write_json(store.folder(pid)/'plan/words.json',words)
     ids={}
     for name,tid in [('temporal','fe6af504-2de7-49f3-a5e8-d2e38d153f1c'),('generated','f287193b-2ed6-4a71-90ce-330653dc5b87')]:
      p=await call('read_project',{'project_id':pid});r=await call('attach_media_result',{'project_id':pid,'base_revision':p['revision'],'task_id':tid,'tags':name,'role':'reconstruction'});ids[name]=r['asset']['id']
     for name,path in [('source',store.ROOT/'outputs/subject-source.mp4'),('lama',store.ROOT/'outputs/subject-inpaint.mp4'),('overlay',store.DATA/'media-tasks/d5b21324-eb7f-4140-bedb-e2ba48562df3/subject-overlay.mp4')]:
      p=await call('read_project',{'project_id':pid});r=await call('import_media',{'project_id':pid,'base_revision':p['revision'],'preserve_plan':True,'path':str(path),'tags':name,'role':'illustration'});ids[name]=r['asset']['id']
     accent=await call('design_sound',{'kind':'whoosh','duration':.5,'gain_db':-24,'seed':18})
     p=await call('read_project',{'project_id':pid});r=await call('import_media',{'project_id':pid,'base_revision':p['revision'],'preserve_plan':True,'path':accent['path'],'tags':'quiet original whoosh'});ids['sound']=r['asset']['id']
     p=await call('read_project',{'project_id':pid});timeline=p['timeline'];assert timeline['total_frames']==1585
     names=['generated','source','lama','temporal','overlay','generated'];rates=[.4,.25,.2,.2,.15,.25]
     timeline['shots']=[{'id':f'scene-{i}','beat_id':f'idea-{i}','start_frame':a,'end_frame':b,'asset_id':ids[names[i]],'source_start':0,'playback_rate':rates[i],
                        'motion':'hold','fit':'contain','role':'reconstruction' if names[i] in ('generated','lama','temporal') else 'illustration'} for i,(a,b) in enumerate(zip(BOUNDS,BOUNDS[1:]))]
     timeline['cues']=previous['cues'];timeline['design']={'intent':'Explain temporal continuity with real before/after examples, readable mobile typography and restrained motion','font_family':'Arial, sans-serif','background':'#101820','palette':['#101820','#ffffff','#e4b866']}
     await call('patch_timeline',{'project_id':pid,'base_revision':p['revision'],'operations':[{'op':'replace_timeline','timeline':timeline}]})
    p=await call('read_project',{'project_id':pid});timeline=p['timeline']
    names=['generated','source','lama','temporal','overlay','generated'];rates=[.4,.25,.2,.2,.15,.25]
    timeline['shots']=[{**s,'asset_id':None,'text':''} for s in timeline['shots']]
    timeline['layers']=[l for l in timeline['layers'] if not l['id'].startswith(('portrait-','framing-'))]
    timeline['layers'].append({'id':'framing-background','kind':'shape','start_frame':0,'end_frame':1585,'x':0,'y':0,'width':1,'height':1,'z':1,'color':'#101820','data':{'shape':'rectangle','corner_radius':0}})
    for i,(a,b) in enumerate(zip(BOUNDS,BOUNDS[1:])):
     timeline['layers'].append({'id':f'framing-video-{i}','kind':'video','start_frame':a,'end_frame':b,'x':0,'y':.22,'width':1,'height':.44 if profile=='vertical' else .60,'z':10,'asset_id':ids[names[i]],'source_start':0,'playback_rate':rates[i],'fit':'cover' if profile=='vertical' else 'contain'})
    await call('patch_timeline',{'project_id':pid,'base_revision':p['revision'],'operations':[{'op':'replace_timeline','timeline':timeline}]})
    async def recipe(recipe,id,start,end,**kwargs):
     p=await call('read_project',{'project_id':pid})
     return await call('compose_edit',{'project_id':pid,'base_revision':p['revision'],'request':{'recipe':recipe,'id':id,'platform':platform,'start_frame':start,'end_frame':end,**kwargs}})
    await recipe('word_captions','voice-captions',0,1585)
    for i,(a,b) in enumerate(zip(BOUNDS,BOUNDS[1:])):
     title=['Ảnh đẹp chưa đủ','Chuyển động và che khuất','Tái tạo từng frame','Giữ liên hệ theo thời gian','AI quan sát rồi tinh chỉnh','Dựng rõ ý, giữ nhịp'][i]
     # Keep titles outside the vertically contained footage and mobile captions.
     await recipe('hook_card' if i==0 else 'keyword_callout','heading'+str(i),a,b,text=title,font_size=62 if profile=='vertical' else 64,
                  safe_region=[.08,.10,.82,.36] if profile=='vertical' else [.06,.07,.94,.38])
    manifest=store.read_json(store.DATA/'media-tasks/d5b21324-eb7f-4140-bedb-e2ba48562df3/subjects.json')
    d=BOUNDS[2]-BOUNDS[1];target=[]
    tracks=manifest['tracks']['1']
    for row in tracks[::6]:
     f=round(row['frame']/.25)
     if f>=d or not row['box']:continue
     x=(row['box'][0]+row['box'][2])/2;y=(row['box'][1]+row['box'][3])/2
     if profile=='vertical':
      source_fraction=((1080/(1920*.44))/(960/540));x=(x-(1-source_fraction)/2)/source_fraction;y=.22+y*.44
     else:x=.2+x*.6;y=.22+y*.6
     target.append({'frame':f,'x':x,'y':y})
    await recipe('tracked_callout','subject-label',BOUNDS[1],BOUNDS[2],text='Chủ thể phía trước' if profile=='vertical' else 'Chủ thể\nphía trước',target=[target[0]['x'],target[0]['y']],target_keyframes=target,
                 label_point=[.08,.205] if profile=='vertical' else [.05,.34],label_width=.407 if profile=='vertical' else .15,font_size=30 if profile=='vertical' else 36)
    await recipe('lower_third','reconstruction-note',BOUNDS[5],1585,text='Minh họa do AI tạo',secondary_text='Không phải tư liệu quay thực tế',font_size=28,
                 safe_region=[.08,.48,.82,.64] if profile=='vertical' else [.06,.60,.52,.83])
    for i,cut in enumerate([BOUNDS[2],BOUNDS[3]]):
     await recipe('sound_bridge','sfx'+str(i),cut-5,cut+10,asset_id=ids['sound'],source_start=0,volume=.5)
    await recipe('audio_finish','master',0,1585,audio_mix={'target_lufs':-16,'true_peak_db':-1.5,'music_ducking':{'ratio':6,'attack_ms':30,'release_ms':450}})
    if REFINE:
     for name,template in [('index.tsx','AgentVideo.tsx'),('effects.cjs','effects.js'),('effects.js','effects.js')]:
      existing=await call('read_code',{'project_id':pid,'engine':'remotion','relative_path':name})
      await call('write_code',{'project_id':pid,'engine':'remotion','relative_path':name,'expected_sha256':existing['sha256'],'content':(store.ROOT/'engines'/template).read_text(encoding='utf-8')})
    else:await call('export_code',{'project_id':pid,'engine':'remotion'})
    snaps=await call('snapshot_code',{'project_id':pid,'engine':'remotion','frames':[70,300,600,800,1150,1450]}) if '--no-snapshots' not in sys.argv else None
    record={'project_id':pid,'platform':platform,'assets':ids,'snapshots':json.loads(snaps[0].text) if snaps is not None else None,'narration_pcm_identical':True,'voice_sha256':sha256(voice)}
    records[platform]=record;store.write_json(store.ROOT/'outputs/professional-demo-projects.json',records)
    final=await job(pid,'final');record['job']=final
    prefix='professional-tiktok' if profile=='vertical' else 'professional-youtube'
    for artifact in final['artifacts']:
     names={'final.mp4':prefix+'.mp4','delivery.zip':prefix+'.zip','audio-master.json':prefix+'-audio.json'}
     if artifact['name'] in names:shutil.copyfile(artifact['path'],store.ROOT/'outputs'/names[artifact['name']])
    assert sha256(voice)==record['voice_sha256']
    video=store.ROOT/'outputs'/(prefix+'.mp4');command([FFMPEG,'-v','error','-xerror','-i',video,'-f','null','-'])
    record.update(output=str(video),sha256=sha256(video),probe=probe(video),decoder_errors=0)
    store.write_json(store.ROOT/'outputs/professional-demo-projects.json',records);print('complete',platform,pid,flush=True)

if __name__=='__main__':asyncio.run(main())
