"""Real dual-engine rendering of timed captions and moving SVG callouts."""
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import agent,store,professional
from editvideo.media import FFMPEG,command,sha256
from editvideo.audio import group_words
from editvideo.code_engine import scaffold
from editvideo.jobs import Worker
from editvideo.observe import observe

def main():
 store.initialize(recover=False);base=store.folder('2824c0e3-88de-4cf8-8b6b-266bd5d283f6')
 source=store.ROOT/'outputs/widgets-probe-source.mp4'
 command([FFMPEG,'-y','-v','error','-f','lavfi','-i','color=c=0x101820:s=1920x1080:r=30:d=3','-i',base/'plan/voice.wav','-t',3,'-c:v','libx264','-c:a','aac',source])
 p=agent.from_video(str(source),title='Portable professional widgets');pid=p['id']
 words=[{**w,'end':min(3,w['end'])} for w in store.read_json(base/'plan/words.json')['words'] if w['start']<3]
 t=p['timeline'];t['cues']=group_words(words);t['shots'][0].update(asset_id=None,text='')
 t['layers']=[{'id':'background','kind':'shape','start_frame':0,'end_frame':90,'x':0,'y':0,'width':1,'height':1,'color':'#101820','z':5,'data':{'shape':'rectangle','corner_radius':0}},
              {'id':'moving-point','kind':'shape','start_frame':0,'end_frame':90,'x':.4,'y':.42,'width':.05,'height':.08,'z':20,'color':'#e4b866','data':{'shape':'ellipse'},'keyframes':{'x':[{'frame':0,'value':0},{'frame':89,'value':384}]}}]
 agent.patch(pid,p['revision'],[{'op':'replace_timeline','timeline':t}]);p=agent.read(pid)
 professional.compose(pid,p['revision'],{'recipe':'word_captions','id':'spoken','end_frame':90,'word_timings':words,'timing_source':'cropped original TTS times; AAC probe timing approximate'})
 p=agent.read(pid);professional.compose(pid,p['revision'],{'recipe':'tracked_callout','id':'anchor','end_frame':90,'text':'Điểm neo đang chuyển','target':[.425,.46],'label_point':[.08,.18],
    'target_keyframes':[{'frame':0,'x':.425,'y':.46},{'frame':89,'x':.625,'y':.46}],'font_size':36})
 results={}
 for engine in ('remotion','hyperframes'):
  p=store.get_project(pid);store.update_project(pid,{**p['config'],'renderer':engine});scaffold(pid,engine)
  j=store.create_job(pid,'final');Worker().run(j['id']);r=agent.result(j['id']);assert r['state']=='completed',r['error']
  path=store.folder(pid)/'jobs'/j['id']/'final.mp4';dest=store.ROOT/'outputs'/f'professional-widgets-{engine}.mp4';shutil.copyfile(path,dest)
  command([FFMPEG,'-v','error','-xerror','-i',dest,'-f','null','-'])
  packet=observe(dest,timestamps=[.5,1.5,2.8],max_frames=3,width=1280)
  results[engine]={'video':str(dest),'sha256':sha256(dest),'job_id':j['id'],'observation':packet,'report':r['output']['report'],'decoder_errors':0}
  print(engine,'complete',flush=True)
 store.write_json(store.ROOT/'outputs/professional-widgets-verification.json',{'project_id':pid,'engines':results,'notes':'Technical portability probe, real source TTS excerpt; not a complete editorial film or forced-alignment proof. Anchor target is an authored graphic trajectory, not semantic tracking.'})

if __name__=='__main__':main()
