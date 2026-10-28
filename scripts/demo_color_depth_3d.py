"""A complete new Vietnamese narrated film using offline design, depth/LUT and3D."""
import json,math,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import agent,store,media_tasks,design_library as dl,professional,scene3d,agent_interface
from editvideo.audio import restore_display_text,group_words
from editvideo.jobs import Worker
from editvideo.code_engine import scaffold
from editvideo.media import FFMPEG,command,sha256
from editvideo.observe import observe

PARAGRAPHS=[
 'Tại sao một hình ảnh phẳng vẫn có thể khiến ta cảm nhận chiều sâu? Hãy nhìn khoảng cách giữa tiền cảnh, chủ thể và hậu cảnh.',
 'Điều thứ nhất là bố cục. Vật gần có thể che vật xa. Khi camera đổi vị trí, các lớp chuyển động khác nhau. Đồ họa ba chiều giúp minh họa mối quan hệ ấy.',
 'Với ảnh hoặc video, AI có thể ước lượng lớp gần và lớp xa. Đây là chiều sâu tương đối. Bản đồ này không cho ta khoảng cách chính xác bằng mét.',
 'Từ bản đồ đó, ta có thể làm dịu hậu cảnh hoặc chuyển điểm chú ý. Nhưng phải nhìn lại tóc, bàn tay và những vùng bị che. Hiệu ứng chỉ hữu ích khi giữ được điều cần thấy.',
 'Điều thứ hai là màu sắc. Một bảng màu thống nhất giúp cảnh nối tiếp nhau tự nhiên. Bảng tra màu cần đúng không gian màu. Đừng dùng một vẻ đẹp có sẵn để làm sai màu tư liệu.',
 'Vùng sáng cũng cần được giữ đúng. Chuyển hình ảnh có dải sáng rộng sang màn hình thông thường cần ánh xạ tông. Chỉ đổi nhãn xuất file không tạo lại chi tiết đã mất.',
 'Cuối cùng là cách kể. Chữ phải rõ, chuyển động phải có mục đích, và hình ảnh phải giải thích lời nói. Chiều sâu và màu sắc là công cụ. Ý nghĩa mới là điều dẫn dắt người xem.'
]
SCRIPT='\n\n'.join(PARAGRAPHS)

def waittask(task):
 import time
 while True:
  r=media_tasks.get(task['id'])
  if r['state'] in media_tasks.TERMINAL:
   if r['state']!='completed':raise RuntimeError(r['error'])
   return r
  time.sleep(1)

def build():
 store.initialize(recover=False);tasks=store.read_json(store.ROOT/'outputs/advanced-task-ids.json')
 brief=agent_interface.creative_packet({'title':'Chiều sâu giúp hình ảnh kể chuyện thế nào?','audience':'Người xem kiến thức bằng tiếng Việt','promise':'Giải thích chiều sâu, màu và sự chú ý qua ví dụ có thể nhìn thấy.','payoff':'Chọn kỹ thuật vì ý nghĩa hình ảnh, không vì số lượng hiệu ứng.','style_id':'vietnam_knowledge','factual_sources':['Depth Anything V2 Small model card','FFmpeg zscale/tonemap/lut3d documentation'],
  'alternatives':['Một ý rõ, ví dụ trực quan, diễn giải giới hạn','Cấu trúc trước/sau kỹ thuật; dễ sa vào giới thiệu công cụ'],
  'beats':[{'id':f'beat-{i}','narration':text,'visual_idea':idea,'shot_choice':choice,'evidence_status':'authored_graphic' if choice in ('3d','diagram') else 'illustration'} for i,(text,idea,choice) in enumerate(zip(PARAGRAPHS,['Tiền cảnh và hậu cảnh rừng với chuyển động2.5D nhẹ','Ba lớp3D lit perspective','Nguồn và depth preview đặt cạnh','Nguồn và blur depth đặt cạnh','Ảnh màu trước/sau LUT','Mẫu HDR luminance chuẩn và tonemap SDR','Ba ý chốt rõ ràng'],['image','3d','split_screen','split_screen','split_screen','diagram','diagram']))]})
 if '--project-id' in sys.argv:
  pid=sys.argv[sys.argv.index('--project-id')+1];p=agent.read(pid)
  if p['config']['script']!=SCRIPT or not p['timeline']:raise ValueError('Resume requires identical script and locked plan')
 else:
  p=agent.create({'title':brief['brief']['title'],'script':SCRIPT,'profile':'landscape','renderer':'remotion','captions':True});pid=p['id']
  j=store.create_job(pid,'plan');Worker().run(j['id']);assert store.get_job(j['id'])['state']=='completed',store.get_job(j['id'])['error']
 p=agent.read(pid);plan=store.folder(pid)/'plan';words=store.read_json(plan/'words.json')['words'];display=restore_display_text(words,SCRIPT)
 if not display:raise ValueError('Real narration words do not match full script; inspect narration before authoring boundaries')
 store.write_json(plan/'words.json',{'method':'real_edge_tts_display_restored','words':display})
 total=p['timeline']['total_frames'];bounds=[0];cursor=0;word_count=0
 for paragraph in PARAGRAPHS[:-1]:
  goal=word_count+len(paragraph.split())
  while cursor<len(display) and word_count<goal:word_count+=len(display[cursor]['text'].split());cursor+=1
  if word_count!=goal:raise ValueError('Paragraph boundary crosses a word-unit; inspect actual words instead of estimated timing')
  bounds.append(math.ceil(display[cursor]['start']*30))
 bounds.append(total)
 t=p['timeline'];t['cues']=group_words(display);t['shots']=[{'id':f'beat-{i}','beat_id':f'beat-{i}','start_frame':a,'end_frame':b,'text':'','motion':'hold'} for i,(a,b) in enumerate(zip(bounds,bounds[1:]))];t['layers']=[]
 agent.patch(pid,p['revision'],[{'op':'replace_timeline','timeline':t}]);p=agent.read(pid);dl.apply(pid,p['revision'],{'style_id':'vietnam_knowledge','palette_id':'forest'})
 assets={}
 def attach(name,path):
  p=agent.read(pid);r=agent.import_media(pid,str(path),tags=name,role='illustration',preserve_plan=True,base_revision=p['revision']);assets[name]=r['asset']['id'];return r['asset']['id']
 for name,key in [('parallax','parallax'),('focus','focus'),('lut_video','color_lut')]:attach(name,media_tasks.get(tasks[key])['result']['video'])
 attach('source',store.ROOT/'outputs/subject-source.mp4')
 manifest=store.read_json(Path(media_tasks.get(tasks['depth'])['result']['manifest']))
 attach('depth',media_tasks.get(tasks['depth'])['result']['video'])
 forest=store.DATA/'media-tasks/5347e3e0-2388-4394-854c-5672e8731755/generated-frames/000060.png';attach('forest',forest)
 color=waittask(media_tasks.submit('color',{'path':str(forest),'input_space':'srgb','input_range':'full','lut_id':'warm_story','lut_strength':.65}))
 for name,path in [('forest_lut',color['result']['video']),('hdr_proxy',store.ROOT/'outputs/color-tonemap.mp4')]:
  target=store.folder(pid)/(name+'.png')
  command([FFMPEG,'-y','-v','error','-i',path,'-frames:v','1','-vf','zscale=pin=bt709:tin=bt709:min=bt709:rin=limited:p=bt709:t=iec61966-2-1:m=gbr:r=full,format=gbrp,format=rgb24',target])
  attach(name,target)
 def add(layer):
  p=agent.read(pid);agent.patch(pid,p['revision'],[{'op':'upsert_layer','layer':layer}])
 def text(i,id,text,y,role='title',x=.07,width=.86,color_role='text',height=.12):
  a,b=bounds[i:i+2];add({'id':id,'kind':'text','start_frame':a,'end_frame':b,'text':text,'x':x,'y':y,'width':width,'height':height,'z':400,'typography_role':role,'color_role':color_role,'effects':[{'name':'line_reveal','end_frame':min(20,b-a-1),'params':{'amount':16}}]})
 def media(i,id,asset,x,y,width,height,rate=1):
  a,b=bounds[i:i+2];add({'id':id,'kind':'image' if next(v for v in agent.read(pid)['assets'] if v['id']==asset)['kind']=='image' else 'video','asset_id':asset,'start_frame':a,'end_frame':b,'x':x,'y':y,'width':width,'height':height,'z':100,'fit':'cover','playback_rate':rate})
 for i in range(7):
  a,b=bounds[i:i+2];add({'id':f'bg-{i}','kind':'shape','start_frame':a,'end_frame':b,'x':0,'y':0,'width':1,'height':1,'z':10,'color_role':'background','data':{'shape':'rectangle','corner_radius':0}})
 text(0,'hook','Một hình ảnh phẳng.\nVì sao vẫn có chiều sâu?',.075,'headline',width=.68,height=.2)
 media(0,'forest-start',assets['parallax'],.06,.32,.88,.42,rate=min(1,3.99/((bounds[1]-bounds[0])/30)))
 text(0,'origin','Rừng: footage AI minh họa · chuyển động2.5D từ ảnh',.755,'source',color_role='muted',height=.045)
 text(1,'layers-title','01 / Ba lớp trong một khung hình',.08,'title')
 p=agent.read(pid);scene3d.compose(pid,p['revision'],{'id':'native-3d','preset':'depth_layers','start_frame':bounds[1],'end_frame':bounds[2],'x':.05,'y':.19,'width':.9,'height':.55})
 # Native projected labels follow their3D objects/camera; no static misleading labels.
 text(2,'depth-title','AI ước lượng lớp gần và xa',.08,'title');media(2,'depth-source',assets['source'],.06,.25,.43,.43,rate=min(1,1.99/((bounds[3]-bounds[2])/30)));media(2,'depth-map',assets['depth'],.51,.25,.43,.43,rate=min(1,1.99/((bounds[3]-bounds[2])/30)))
 text(2,'depth-note','Depth tương đối · màu nóng≈gần, màu lạnh≈xa · không phải mét',.715,'source',color_role='muted',height=.045)
 text(3,'focus-title','Chuyển sự chú ý có mục đích',.08,'title');media(3,'before-focus',assets['source'],.06,.25,.43,.43,rate=min(1,1.99/((bounds[4]-bounds[3])/30)));media(3,'after-focus',assets['focus'],.51,.25,.43,.43,rate=min(1,1.99/((bounds[4]-bounds[3])/30)))
 text(3,'focus-before','NGUỒN',.70,'label',width=.4,color_role='accent',height=.04);text(3,'focus-after','BLUR THEO DEPTH',.70,'label',x=.51,width=.4,color_role='accent',height=.04)
 text(4,'color-title','02 / Màu thống nhất, nguồn giữ đúng',.08,'title');media(4,'color-before',assets['forest'],.06,.25,.43,.43);media(4,'color-after',assets['forest_lut'],.51,.25,.43,.43)
 text(4,'look-note','Minh họa AI · LUT65% trong màu display BT.709',.715,'source',color_role='muted',height=.045)
 text(5,'hdr-title','Ánh xạ tông giữ hình đọc được',.08,'title')
 # Explicit technical fixture: authored luminance values, not inferred footage facts.
 text(5,'hdr-explanation','Mẫu PQ:20 /100 /400 /1000 nit',.235,'body',color_role='muted',height=.09)
 media(5,'hdr-bars',assets['hdr_proxy'],.08,.39,.46,.22)
 text(5,'hdr-proxy-label','Tonemap SDR để xem trên màn hình thường',.64,'source',width=.55,color_role='muted',height=.08)
 text(5,'hdr-truth','Đổi nhãn file\n≠\nKhôi phục vùng sáng',.37,'body',x=.62,width=.30,height=.26)
 text(6,'payoff','03 / Ý nghĩa dẫn dắt kỹ thuật',.08,'headline',width=.85,height=.15)
 for n,label in enumerate(['Chữ rõ','Chuyển động có lý do','Hình giải thích lời']):
  text(6,'principle-'+str(n),f'0{n+1}  '+label,.34+n*.12,'body',color_role='text',height=.09)
  a,b=bounds[6:8];add({'id':'icon-'+str(n),'kind':'icon','start_frame':a,'end_frame':b,'x':.82,'y':.34+n*.12,'width':.065,'height':.085,'z':400,'color_role':'accent','data':{'icon':['eye','target','lightbulb'][n]}})
 p=agent.read(pid);professional.compose(pid,p['revision'],{'recipe':'word_captions','id':'spoken','platform':'youtube_long','start_frame':0,'end_frame':total,'word_timings':display,'timing_source':'Real new Edge TTS word boundaries, display restored to script','font_size':42,'safe_region':[.06,.06,.94,.97],'color':'#f2f7ef','accent':'#81e6be','background':'#102322'})
 p=agent.read(pid);layers=p['timeline']['layers'];cap=next(l for l in layers if l['kind']=='caption');cap.update(y=.84,height=.13,typography_role='caption',font_size=42)
 design=p['timeline']['design'];design['typography']['caption']['size']=42
 agent.patch(pid,p['revision'],[{'op':'set_design','design':design},{'op':'upsert_layer','layer':cap}])
 from editvideo import sound
 accent=sound.design('whoosh',.5,seed=29,gain_db=-26);p=agent.read(pid);asset=agent.import_media(pid,accent['path'],tags='restrained chapter accent',preserve_plan=True,base_revision=p['revision'])['asset'];p=agent.read(pid)
 agent.patch(pid,p['revision'],[{'op':'upsert_audio','audio':{'id':'chapter-accent-'+str(i),'asset_id':asset['id'],'start_frame':frame,'end_frame':frame+15,'volume':.35,'fade_in':.04,'fade_out':.2,'duck_under_voice':True}} for i,frame in enumerate([bounds[1],bounds[4]])])
 scaffold(pid,'remotion')
 record={'project_id':pid,'bounds':bounds,'assets':assets,'brief':brief['brief_path'],'voice_sha256':sha256(plan/'voice.wav'),'actual_words':len(display),'script':SCRIPT,'duration':total/30};store.write_json(store.ROOT/'outputs/advanced-narrated-demo.json',record);print('built',record['project_id'],'duration',record['duration'],flush=True);return record

def render(record):
 pid=record['project_id'];j=store.create_job(pid,'final');print('render job',j['id'],flush=True);Worker().run(j['id']);r=agent.result(j['id']);assert r['state']=='completed',r['error']
 out=store.folder(pid)/'jobs'/j['id'];dest=store.ROOT/'outputs/advanced-narrated-video.mp4';shutil.copyfile(out/'final.mp4',dest);shutil.copyfile(out/'delivery.zip',store.ROOT/'outputs/advanced-narrated-video.zip')
 times=[(a+b)/60 for a,b in zip(record['bounds'],record['bounds'][1:])];packet=observe(dest,timestamps=times,max_frames=8,width=1280)
 record.update(job_id=j['id'],video=str(dest),sha256=sha256(dest),report=r['output']['report'],observation=packet)
 assert sha256(store.folder(pid)/'plan/voice.wav')==record['voice_sha256']
 store.write_json(store.ROOT/'outputs/advanced-narrated-demo.json',record);print('video complete',str(dest),flush=True)

if __name__=='__main__':
 record=store.read_json(store.ROOT/'outputs/advanced-narrated-demo.json') if '--reuse' in sys.argv else build()
 if '--build-only' not in sys.argv:render(record)
