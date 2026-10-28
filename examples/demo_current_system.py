"""A new narrated, original-media demo of the current MCP tools. No old project is edited.
Run: python examples/demo_current_system.py --build, --snapshot, --render, --inspect.
"""
import argparse,json,math,shutil,sys,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
import numpy as np
from editvideo import mcp_server as m,store,agent
from editvideo.audio import restore_display_text,group_words
from editvideo.media import sha256

OUT=store.ROOT/'outputs/demo-current-20261014'
STATE=OUT/'demo.json'
PARAS=[
 'Một điểm sáng đi qua màn hình. Ta nhìn thấy nó chuyển động. Nhưng làm sao để người xem hiểu điều đang xảy ra? Hãy kể cùng một chuyển động bằng ba cách khác nhau.',
 'Cách thứ nhất là nhìn đường đi. Trong ví dụ mô phỏng này, điểm sáng đi bốn đơn vị trong bốn giây. Thước đo và con số cùng thay đổi, để mắt thấy được khoảng cách.',
 'Cách thứ hai là nhìn quan hệ. Khi vị trí tăng đều theo thời gian, đường biểu diễn là một đường thẳng. Đây là dữ liệu do chúng ta tạo, không phải phép đo từ một cảnh quay.',
 'Một quan hệ khác cũng có thể được dựng bằng chuyển động. Bánh xe quay theo quãng đường của thân xe. Cánh tay đổi góc để bám mục tiêu. Các phần liên kết, thay vì chạy độc lập.',
 'Cách thứ ba là nhìn trong không gian. Camera đi cùng điểm sáng, rồi lùi ra để thấy toàn bộ đường đi. Ánh sáng, vật liệu và chiều sâu giúp ta định hướng, nhưng không thay thế ý nghĩa.',
 'Khi cần kiểm tra con số, hãy quay về nguồn. Bảng dữ liệu mô phỏng ghi rõ thời gian và vị trí. Camera chỉ đưa mắt đến dòng cần đọc. Nó không làm thay đổi dữ liệu.',
 'Ba cách kể, cùng một ý. Chọn hình để giải thích, chọn chuyển động để dẫn mắt, và dành khoảng lặng để người xem hiểu. Kỹ thuật mạnh nhất là kỹ thuật phục vụ câu chuyện.'
]
SCRIPT='\n\n'.join(PARAS)
CALLS=[]
def call(name,**kw):
 r=getattr(m,name)(**kw);CALLS.append(name);return r
def save(r):store.write_json(STATE,r)
def revision(pid):return call('editvideo_read_project',project_id=pid)['revision']
def patch(pid,ops):return call('editvideo_patch_timeline',project_id=pid,base_revision=revision(pid),operations=ops)
def job(pid,kind):
 j=store.create_job(pid,kind);print(kind,j['id'],flush=True);m.worker.run(j['id']);r=call('editvideo_get_job',job_id=j['id'])
 if r['state']!='completed':raise RuntimeError(r.get('error'))
 return r
def build():
 OUT.mkdir(parents=True,exist_ok=True);store.initialize(recover=False)
 if STATE.exists():
  record=store.read_json(STATE);pid=record['project_id']
  if agent.read(pid)['config']['script']!=SCRIPT:raise ValueError('Demo state belongs to a different script')
 else:
  p=call('editvideo_create_project',config={'title':'Một chuyển động, ba cách kể','script':SCRIPT,'renderer':'remotion','profile':'landscape','voice_rate':8,'captions':True})
  pid=p['id'];record={'project_id':pid,'script':SCRIPT};save(record)
 p=agent.read(pid)
 if not p.get('timeline'):job(pid,'plan')
 p=agent.read(pid);plan=store.folder(pid)/'plan';words=store.read_json(plan/'words.json')['words']
 display=restore_display_text(words,SCRIPT)
 if not display:raise ValueError('Actual narration timing does not match the new script')
 bounds=[0];cursor=0;count=0
 for text in PARAS[:-1]:
  target=count+len(text.split())
  while cursor<len(display) and count<target:count+=len(display[cursor]['text'].split());cursor+=1
  if count!=target:raise ValueError('A paragraph splits a real TTS unit')
  bounds.append(math.ceil(display[cursor]['start']*30))
 bounds.append(p['timeline']['total_frames']);total=bounds[-1]
 store.write_json(plan/'words.json',{'method':'real_edge_tts_display_restored','words':display})
 t=p['timeline'];t['cues']=group_words(display);t['layers']=[];t['audio']=[]
 t['shots']=[{'id':f's{i}','beat_id':f'b{i}','start_frame':a,'end_frame':b,'text':'','motion':'hold'} for i,(a,b) in enumerate(zip(bounds,bounds[1:]))]
 patch(pid,[{'op':'replace_timeline','timeline':t}])
 call('editvideo_apply_direction',project_id=pid,base_revision=revision(pid),direction_id='flat_vector_explainer')
 colors={'bg':'#081320','white':'#edf3fb','cyan':'#4ad9f1','gold':'#ffc56b','muted':'#8fa3bb'}
 ops=[]
 def layer(i,id,kind,**kw):
  a,b=bounds[i:i+2];ops.append({'op':'upsert_layer','layer':{'id':id,'kind':kind,'start_frame':a,'end_frame':b,'z':80,**kw}})
 def text(i,id,txt,x=.065,y=.075,w=.88,h=.12,size=56,color=None,weight=600):
  layer(i,id,'text',text=txt,x=x,y=y,width=w,height=h,font_id='bevietnampro',font_size=size,font_weight=weight,typography_role=None,color=color or colors['white'],line_height=1.45,z=300,
   effects=[{'name':'fade_in','end_frame':12}])
 for i in range(7):
  layer(i,f'bg{i}','shape',x=0,y=0,width=1,height=1,color=colors['bg'],data={'shape':'rectangle','corner_radius':0},z=1)
  if i!=5:text(i,f'chapter{i}',f'{i+1:02d} / EDITVIDEO · MỘT CHUYỂN ĐỘNG',y=.033,h=.04,size=26,color=colors['muted'],weight=400)
 titles=['Một chuyển động.\nBa cách kể.','01 / Nhìn đường đi','02 / Nhìn quan hệ','Các phần phải liên kết','03 / Nhìn trong không gian','Con số phải trở về nguồn','Cùng một ý. Ba cách kể.']
 for i,title in enumerate(titles):
  if i!=5:text(i,f'title{i}',title,y=.105,h=.24 if i==0 else .1,size=88 if i==0 else 56)
 # Opening / closing callback: one cyan traveller, smooth seekable motion.
 for i in [0,6]:
  a,b=bounds[i:i+2];d=b-a
  layer(i,f'rail{i}','shape',x=.12,y=.56 if i==0 else .65,width=.76,height=.003,color='#23374d',data={'shape':'rectangle','corner_radius':0},z=40)
  layer(i,f'traveller{i}','shape',x=.12,y=.534 if i==0 else .624,width=.03,height=.0533,color=colors['cyan'],data={'shape':'ellipse'},z=90,
   keyframes={'x':[{'frame':0,'value':0},{'frame':d-1,'value':(.36 if i==6 else .72)*1920,'easing':'ease_in_out'}]})
  if i==6:text(i,'payoff','ĐƯỜNG ĐI  /  QUAN HỆ  /  KHÔNG GIAN',y=.38,h=.12,size=44,color=colors['cyan'])
 # Measured linear movement is exactly four seconds, then holds for reading.
 a,b=bounds[1:3];duration=b-a;begin=18;end=138
 layer(1,'measured-orb','shape',x=.195,y=.40,width=.025,height=.0444,color=colors['cyan'],data={'shape':'ellipse'},
  keyframes={'x':[{'frame':begin,'value':0},{'frame':end,'value':.60*1920,'easing':'linear'},{'frame':duration-1,'value':.60*1920}]})
 text(1,'model-label','MÔ PHỎNG · x(t) = t · 1 đơn vị/giây',y=.70,h=.06,size=28,color=colors['muted'],weight=400)
 for batch in range(0,len(ops),80):patch(pid,ops[batch:batch+80])
 call('editvideo_compose_explainer',project_id=pid,base_revision=revision(pid),request={'recipe':'measure','id':'distance','start_frame':a,'end_frame':b,'start':[.2075,.54],'end':[.8075,.54],'value_to':4,'suffix':' đơn vị','delay':begin,'grow_frames':120,'grow':'start','color':colors['cyan'],'role':'title'})
 # Plot the exact authored data, with axes and units rather than a decorative curve.
 a,b=bounds[2:4]
 call('editvideo_compose_explainer',project_id=pid,base_revision=revision(pid),request={'recipe':'plot','id':'plot','start_frame':a,'end_frame':b,'box':[.16,.29,.68,.45],'x_range':[0,4],'y_range':[0,4],'x_ticks':[0,1,2,3,4],'y_ticks':[0,1,2,3,4],'x_label':'Thời gian (s)','y_label':'Vị trí (đv)','font_size':29,'grid':True,'axis_color':colors['muted'],'series':[{'type':'line','points':[[i,i] for i in range(5)],'color':colors['cyan'],'at':24,'frames':120,'width':5},{'type':'scatter','points':[[i,i] for i in range(5)],'color':colors['gold'],'at':24,'frames':120,'size':9}]})
 # Actual driver + two-bone IK, using shared runtime rather than baked custom animation.
 a,b=bounds[3:5];d=b-a
 rig=[]
 def R(id,**kw):rig.append({'op':'upsert_layer','layer':{'id':id,'kind':'shape','start_frame':a,'end_frame':b,'z':100,**kw}})
 R('shoulder',x=.27,y=.31,width=.02,height=.035,color=colors['gold'],data={'shape':'ellipse'},z=110)
 R('upper',x=.274,y=.33,width=.018,height=.2,color=colors['white'],anchor=[.5,0],data={'shape':'rectangle','corner_radius':8})
 R('lower',x=.274,y=.53,width=.014,height=.2,color=colors['cyan'],anchor=[.5,0],parent='upper',data={'shape':'rectangle','corner_radius':8},ik={'target':'goal','tip':[.5,1],'bend':'cw'})
 R('hand',x=.27,y=.72,width=.022,height=.039,color=colors['gold'],parent='lower',data={'shape':'ellipse'})
 keys=[{'frame':round(k*(d-1)/12),'value':round(130*math.sin(k*math.pi/6)),'easing':'linear'} for k in range(13)]
 keys_y=[{'frame':round(k*(d-1)/12),'value':round(-110-85*math.cos(k*math.pi/6)),'easing':'linear'} for k in range(13)]
 R('goal',x=.43,y=.61,width=.022,height=.039,color=colors['gold'],data={'shape':'ellipse'},keyframes={'x':keys,'y':keys_y})
 R('car',x=.61,y=.54,width=.11,height=.06,color=colors['cyan'],data={'shape':'rectangle','corner_radius':10},keyframes={'x':[{'frame':0,'value':0},{'frame':d-1,'value':220,'easing':'ease_in_out'}]})
 for j in range(2):R(f'wheel{j}',x=.625+j*.055,y=.588,width=.022,height=.039,color=colors['gold'],data={'shape':'rectangle','corner_radius':4},drivers={'x':{'source':'car'},'rotate':{'source':'car','track':'x','mul':180/math.pi/21}})
 patch(pid,rig)
 patch(pid,[{'op':'upsert_layer','layer':{'id':'rig-note','kind':'text','text':'IK: bám mục tiêu                 Driver: dịch chuyển → góc quay','start_frame':a,'end_frame':b,'x':.14,'y':.73,'width':.74,'height':.07,'z':300,'font_id':'bevietnampro','font_size':28,'font_weight':400,'typography_role':None,'color':colors['muted']}}])
 # Hero: an authored spatial path, smoothly chasing and then revealing the whole route.
 a,b=bounds[4:6]
 path=[[round(-2+4*k/40,4),round(.3*math.sin(k*math.pi/20),4),round(.75*math.sin(k*math.pi/40),4)] for k in range(41)]
 req={'recipe':'trajectory_3d','id':'hero3d','start_frame':a,'end_frame':b,'path':path,'stars':24,'background':colors['bg'],'route_color':colors['cyan'],'milestones':[{'label':'A','fraction':.05},{'label':'B','fraction':.95}],'overview_from':.3,'travel':[12,b-a-30],'label_hold':90}
 dry=call('editvideo_compose_cinematic',project_id=pid,base_revision=revision(pid),request=req,dry_run=True)
 store.write_json(OUT/'hero-dry-run.json',dry)
 call('editvideo_compose_cinematic',project_id=pid,base_revision=revision(pid),request=req)
 # Original data card: truthful synthetic provenance, using evidence_3d's projected mark.
 doc=OUT/'simulation-data.png';im=Image.new('RGB',(1500,1000),'#e8eef6');draw=ImageDraw.Draw(im)
 font=store.ROOT/'assets/fonts/bevietnampro/BeVietnamPro-Regular.ttf'
 if not font.exists():font=next((store.ROOT/'assets/fonts/bevietnampro').glob('*Regular*.ttf'))
 f=ImageFont.truetype(str(font),44);small=ImageFont.truetype(str(font),31)
 draw.text((110,65),'DỮ LIỆU MÔ PHỎNG · x(t) = t',font=f,fill='#132437')
 draw.text((110,155),'Thời gian (s)                 Vị trí (đơn vị)',font=small,fill='#334b63')
 for i in range(5):
  y=255+i*110;draw.line((110,y-22,1350,y-22),fill='#b3c4d6',width=2);draw.text((170,y),str(i),font=f,fill='#132437');draw.text((850,y),str(i),font=f,fill='#132437')
 draw.text((110,900),'Tự tạo cho demo · không phải số đo từ footage',font=small,fill='#526a82');im.save(doc)
 asset=call('editvideo_import_media',project_id=pid,path=str(doc),tags='Original synthetic data table x(t)=t',role='illustration',preserve_plan=True,base_revision=revision(pid))['asset']['id']
 a,b=bounds[5:7]
 call('editvideo_compose_explainer',project_id=pid,base_revision=revision(pid),request={'recipe':'evidence_3d','id':'data-card','start_frame':a,'end_frame':b,'asset_id':asset,'focus':[.08,.65,.91,.76],'caption':'Dòng cuối: 4 giây → 4 đơn vị','source':'Dữ liệu mô phỏng tự tạo cho demo','push':.45,'tilt_deg':7,'background':colors['bg'],'accent':colors['cyan'],'font_id':'bevietnampro'})
 # Keep recipe source and narration captions in separate readable regions.
 p=agent.read(pid);ls=[l for l in p['timeline']['layers'] if l['id']=='data-card-source']
 if ls:
  ls[0].update(y=.74,font_size=28,z=302);patch(pid,[{'op':'upsert_layer','layer':ls[0]}])
 cap_source=next(l for l in agent.read(pid)['timeline']['layers'] if l['id']=='data-card-caption');cap_source['z']=303
 patch(pid,[{'op':'upsert_layer','layer':cap_source}])
 patch(pid,[{'op':'upsert_layer','layer':{'id':'source-plate','kind':'shape','start_frame':a,'end_frame':b,'x':0,'y':.735,'width':1,'height':.11,'color':colors['bg'],'z':301,'data':{'shape':'rectangle','corner_radius':0}}}])
 call('editvideo_compose_edit',project_id=pid,base_revision=revision(pid),request={'recipe':'word_captions','id':'spoken','platform':'youtube_long','start_frame':0,'end_frame':total,'word_timings':display,'timing_source':'Actual new Vietnamese TTS word boundaries','font_size':42,'safe_region':[.06,.06,.94,.98],'color':colors['white'],'accent':colors['cyan'],'background':colors['bg']})
 p=agent.read(pid);cap=next(l for l in p['timeline']['layers'] if l['kind']=='caption');cap.update(y=.85,height=.12,typography_role=None,font_id='bevietnampro',font_size=42,z=980)
 patch(pid,[{'op':'upsert_layer','layer':cap}])
 patch(pid,[{'op':'upsert_layer','layer':{'id':'close-black','kind':'shape','start_frame':total-24,'end_frame':total,'x':0,'y':0,'width':1,'height':1,'color':'#000000','z':1000,'data':{'shape':'rectangle','corner_radius':0},'effects':[{'name':'fade_in','end_frame':23,'easing':'linear'}]}}])
 for n,frame in enumerate([bounds[1],bounds[4],bounds[6]]):
  effect=call('editvideo_design_sound',kind='chime' if n==2 else 'whoosh',duration=.5,seed=21+n,gain_db=-24)
  asset=call('editvideo_import_media',project_id=pid,path=effect['path'],tags='Original procedural chapter accent',preserve_plan=True,base_revision=revision(pid))['asset']['id']
  patch(pid,[{'op':'upsert_audio','audio':{'id':f'sfx{n}','asset_id':asset,'start_frame':frame,'end_frame':frame+15,'volume':.35,'fade_out':.12,'duck_under_voice':True,'role':'sfx'}}])
 sb={'message':'Cùng một chuyển động có thể được giải thích bằng đường đi, quan hệ và không gian.','arc':['hook','đo','biểu đồ','liên kết','không gian','nguồn','payoff'],'audience':'Người xem kiến thức và người dùng hệ thống AI dựng video','mood':'Rõ ràng, tò mò, tiết chế','direction_id':'flat_vector_explainer','direction_block':{'ground':colors['bg'],'ink':colors['white'],'accent':colors['cyan'],'breather_frame':'b6','negative':['glitch','shake'],'hold_rule':'ambient'},'frames':[{'id':f'b{i}','start_s':a/30,'end_s':b/30,'type':'hook' if i==0 else 'breather' if i==6 else 'context','beat':PARAS[i],'focal':titles[i],'technique':'trajectory_3d' if i==4 else None} for i,(a,b) in enumerate(zip(bounds,bounds[1:]))],'callback':{'motif':'Điểm sáng cyan trên đường đi','plant_frame':'b0','return_frame':'b6','layer_ids':['traveller0','traveller6']}}
 call('editvideo_storyboard',project_id=pid,storyboard=sb)
 record.update(bounds=bounds,duration=total/30,voice_sha256=sha256(plan/'voice.wav'),words=len(display),tool_calls=CALLS,hero_inspect_frames=dry.get('inspect_frames',[]));save(record)
 store.write_json(OUT/'timeline-audit.json',call('editvideo_audit_timeline',project_id=pid,verbose=True))
 call('editvideo_export_code',project_id=pid,engine='remotion',overwrite=True)
 print('built',pid,'duration',total/30,flush=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--build',action='store_true');parser.add_argument('--snapshot',action='store_true');parser.add_argument('--render',action='store_true');parser.add_argument('--inspect',action='store_true');args=parser.parse_args()
 store.initialize(recover=False)
 if args.build:build()
 record=store.read_json(STATE);pid=record['project_id']
 if args.snapshot:
  frames=[(a+b)//2 for a,b in zip(record['bounds'],record['bounds'][1:])];blocks=call('editvideo_snapshot_code',project_id=pid,engine='remotion',frames=frames)
  (OUT/'snapshot-packet.json').write_text(json.dumps([b.model_dump() for b in blocks if b.type=='text'],ensure_ascii=False,indent=2),encoding='utf-8')
  print('snapshots',[(b.text[:800] if b.type=='text' else b.type) for b in blocks],flush=True)
 if args.render:
  result=job(pid,'final');jid=result['id'];work=store.folder(pid)/'jobs'/jid
  shutil.copyfile(work/'final.mp4',OUT/'demo.mp4');shutil.copyfile(work/'delivery.zip',OUT/'delivery.zip')
  source=call('editvideo_package_source',job_id=jid,include_media=True);shutil.copyfile(source['path'],OUT/'editable-source.zip')
  record.update(job_id=jid,video=str(OUT/'demo.mp4'),video_sha256=sha256(OUT/'demo.mp4'),report=result.get('output'));save(record)
 if args.inspect:
  from editvideo.observe import observe
  observation=observe(record['video'],timestamps=[(a+b)/60 for a,b in zip(record['bounds'],record['bounds'][1:])],max_frames=8,width=1280)
  store.write_json(OUT/'observation.json',observation);shutil.copyfile(observation['contact_sheet'],OUT/'storyboard.jpg')
  for name,kwargs,file in [('editvideo_motion_audit',{'path':record['video'],'project_id':pid},'motion-audit.json'),('editvideo_storyboard',{'project_id':pid,'check':True,'render_path':record['video']},'storyboard-check.json'),('editvideo_project_credits',{'project_id':pid},'credits.json'),('editvideo_audit_audio',{'path':record['video']},'audio-audit.json')]:store.write_json(OUT/file,call(name,**kwargs))
 assert sha256(store.folder(pid)/'plan/voice.wav')==record['voice_sha256']

if __name__=='__main__':main()
