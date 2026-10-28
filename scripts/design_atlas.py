"""Render and inspect the offline typography/color/graphic dictionary in both engines."""
import argparse,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from editvideo import agent,store,design_library as dl
from editvideo.code_engine import scaffold
from editvideo.jobs import Worker
from editvideo.media import FFMPEG,command,sha256
from editvideo.observe import observe
from editvideo.snapshot import snapshot

OUT=store.ROOT/'outputs';OUT.mkdir(exist_ok=True)
PREV=OUT/'design-previews';PREV.mkdir(exist_ok=True)
def font_at(fid,size=36,weight=400):
 face=next(f for f in dl.font(fid)['faces'] if f['style']=='normal' and int(f['weight'].split()[0])<=weight<=int(f['weight'].split()[-1]))
 f=ImageFont.truetype(str(dl.FONT_ROOT/face['file']),size)
 if face['axes']:f.set_variation_by_axes([weight if k=='wght' else a[1] for k,a in face['axes'].items()])
 return f
def swatches():
 previews={}
 for f in dl.font_manifest()['fonts']:
  im=Image.new('RGB',(1440,500),'#f4efe4');draw=ImageDraw.Draw(im)
  for y,text,size in [(28,f['family'],52),(115,'Tiếng Việt cần đủ khoảng thở.',54),(205,'Nguyễn Ánh · Trường học · kỹ thuật · dữ liệu',40),(290,'Ắ Ằ Ẳ Ẵ Ặ · Ế Ề Ể Ễ Ệ · Ứ Ừ Ử Ữ Ự',36),(365,'0123456789 / 48 kHz / 1080 × 1920',32)]:draw.text((45,y),text,font=font_at(f['id'],size),fill='#292823')
  draw.text((45,440),f['license']+' · unchanged bundled font',font=font_at('bevietnampro',24),fill='#5d594e')
  path=PREV/f'font-{f["id"]}.png';im.save(path);previews['font/'+f['id']]={'path':str(path),'method':'FreeType actual bundled font, normal weight400'}
 for row in dl.PALETTE_ROWS:
  p=dl.palette(row[0]);im=Image.new('RGB',(1440,560),p['roles']['background']);draw=ImageDraw.Draw(im)
  draw.text((45,28),p['name'],font=font_at('bevietnampro',42,600),fill=p['roles']['text'])
  for i,(role,color) in enumerate(p['roles'].items()):
   x=45+i*195;draw.rounded_rectangle((x,120,x+172,300),radius=12,fill=color)
   on=max(('#101010','#ffffff'),key=lambda c:dl.contrast(c,color))
   draw.text((x+8,138),color,font=font_at('ibmplexmono',23),fill=on)
   draw.text((x,325),role,font=font_at('bevietnampro',22),fill=p['roles']['text'])
  draw.text((45,420),'Chữ chính rõ. Màu nhấn dành cho một ý.',font=font_at('bevietnampro',35),fill=p['roles']['text'])
  draw.text((45,485),'Opaque swatch contrast: '+str(p['contrast']['text/background'])+':1 (text/background)',font=font_at('bevietnampro',24),fill=p['roles']['muted'])
  path=PREV/f'palette-{p["id"]}.png';im.save(path);previews['palette/'+p['id']]={'path':str(path),'method':'Opaque sRGB swatches with actual bundled font'}
 return previews

def build():
 store.initialize(recover=False);previews=swatches();styles=len(dl.STYLE_ROWS);components=len(dl.COMPONENTS)
 pages=styles+components+4;total=pages*60
 source=OUT/'design-probe-source.mp4'
 command([FFMPEG,'-y','-v','error','-f','lavfi','-i',f'color=c=0x101820:s=1920x1080:r=30:d={pages*2}','-c:v','libx264','-preset','ultrafast',source])
 p=agent.from_video(str(source),title='Thư viện thiết kế / design dictionary');pid=p['id'];t=p['timeline'];t['design']=dl.tokens('vietnam_knowledge');t['design']['bundled_font_ids']=[f['id'] for f in dl.font_manifest()['fonts']]
 t['shots'][0].update(asset_id=None,text='');t['layers']=[];entries=[]
 def layer(page,suffix,**kw):
  return {'id':f'page-{page}-{suffix}','kind':'text','start_frame':page*60,'end_frame':(page+1)*60,'x':.08,'y':.1,'width':.82,'height':.12,'z':120,'font_size':42,'color':'#ffffff',**kw}
 for page,row in enumerate(dl.STYLE_ROWS):
  style,name,heading,body,pal,motion=row;color=dl.palette(pal)['roles']
  t['layers'].extend([
   layer(page,'bg',kind='shape',x=0,y=0,width=1,height=1,z=90,color=color['background'],data={'shape':'rectangle','corner_radius':0}),
   layer(page,'pattern',kind='pattern',x=0,y=0,width=1,height=1,z=92,color=color['accent'],opacity=.025 if page==4 else .06,data={'pattern':'dots' if page==4 else dl.PATTERNS[page%len(dl.PATTERNS)],'spacing':64}),
   layer(page,'label',text=name+' / '+style,font_id=body,font_size=30,color=color['accent']),
   layer(page,'accent',kind='shape',y=.185,width=.14,height=.008,color=color['accent'],data={'shape':'rectangle','corner_radius':0}),
   layer(page,'heading',text='Để hình ảnh\nkể rõ câu chuyện.',font_id=heading,typography_role='headline',y=.24,height=.3,color=color['text'],effects=[{'name':'line_reveal','end_frame':22,'params':{'amount':24}}]),
   layer(page,'body',text='Rõ thứ bậc. Đủ khoảng thở.\nMột điểm nhấn cho mỗi nhịp.',font_id=body,typography_role='body',y=.57,height=.2,color=color['muted']),
   layer(page,'icon',kind='icon',data={'icon':'lightbulb'},x=.83,y=.265,width=.08,height=.14,color=color['accent']),
   layer(page,'source',text=f'{dl.font(heading)["family"]} + {dl.font(body)["family"]} / {pal} / {motion}',font_id=body,font_size=27,y=.88,height=.08,color=color['muted'])])
  entries.append({'kind':'style','id':style,'page':page,'timestamp':page*2+1.2})
 agent.patch(pid,p['revision'],[{'op':'replace_timeline','timeline':t}])
 for i,component in enumerate(dl.COMPONENTS):
  page=styles+i;p=agent.read(pid)
  request={'component':component,'id':'component-'+component,'start_frame':page*60,'end_frame':(page+1)*60,'text':'Một ý rõ ràng' if component!='quote' else 'Thấy chi tiết, hiểu toàn cảnh.','detail':'Chọn hình ảnh có mục đích.\nGiữ lời giải thích dễ theo dõi.','labels':['Quan sát','Lý giải','Minh họa','Kết luận'] if component=='steps' else ['Cách thứ nhất','Cách thứ hai'],'value':48,'unit':'kHz','source':'Ví dụ bố cục — không phải kết quả nghiên cứu.','pattern':'dots'}
  dl.compose(pid,p['revision'],request);entries.append({'kind':'component','id':component,'page':page,'timestamp':page*2+1.2})
 p=agent.read(pid);t=p['timeline']
 for n in range(2):
  page=styles+components+n;t['layers'].append(layer(page,'bg',kind='shape',x=0,y=0,width=1,height=1,z=90,color='#102322',data={'shape':'rectangle','corner_radius':0}))
  for i,pattern in enumerate(dl.PATTERNS[n*6:(n+1)*6]):
   x=.06+(i%3)*.31;y=.19+(i//3)*.35
   t['layers'].extend([layer(page,'pattern-'+pattern,kind='pattern',x=x,y=y,width=.27,height=.25,color='#81e6be',data={'pattern':pattern,'spacing':38,'secondary_color':'#24524b'}),layer(page,'label-'+pattern,text=pattern,x=x,y=y+.26,width=.28,height=.055,font_size=27)])
   entries.append({'kind':'pattern','id':pattern,'page':page,'timestamp':page*2+1.2})
 page=styles+components+2;t['layers'].append(layer(page,'bg',kind='shape',x=0,y=0,width=1,height=1,z=90,color='#102322',data={'shape':'rectangle','corner_radius':0}))
 for i,icon in enumerate(dl.ICONS):
  x=.045+(i%8)*.12;y=.13+(i//8)*.27
  t['layers'].extend([layer(page,'icon-'+icon,kind='icon',data={'icon':icon},x=x,y=y,width=.07,height=.12,color='#81e6be'),layer(page,'label-'+icon,text=icon,x=x-.015,y=y+.13,width=.115,height=.05,font_size=19)])
  entries.append({'kind':'icon','id':icon,'page':page,'timestamp':page*2+1.2})
 page+=1;t['layers'].append(layer(page,'bg',kind='shape',x=0,y=0,width=1,height=1,z=90,color='#102322',data={'shape':'rectangle','corner_radius':0}))
 for i,name in enumerate(('word_reveal','line_reveal','character_reveal','text_gradient','underline_draw','radial_glow','edge_feather')):
  from editvideo.effects import CATALOG
  x=.05+(i%4)*.24;y=.22+(i//4)*.4
  t['layers'].extend([layer(page,'fx-'+name,text='Tiếng Việt\nrõ một ý',font_id='bevietnampro',font_size=38,x=x,y=y,width=.21,height=.23,effects=[{**CATALOG[name]['example'],'end_frame':40}]),layer(page,'label-'+name,text=name,x=x,y=y-.06,width=.23,height=.04,font_size=23)])
  entries.append({'kind':'effect','id':name,'page':page,'timestamp':page*2+1.2})
 agent.patch(pid,p['revision'],[{'op':'replace_timeline','timeline':t}])
 record={'project_id':pid,'pages':pages,'duration':pages*2,'entries':entries,'previews':previews,'engines':{},'scope':'Silent visual dictionary, not a narrated film. Font/swatch PNGs FreeType; all composition pages actually rendered. Sources editable, no generated semantic/aesthetic score.'}
 store.write_json(OUT/'design-atlas.json',record);print('built project',pid,flush=True);return record

def render(record,probe_only=False):
 pid=record['project_id']
 for engine in ('remotion','hyperframes'):
  p=store.get_project(pid);store.update_project(pid,{**p['config'],'renderer':engine})
  if not (store.folder(pid)/'code'/engine).exists():scaffold(pid,engine)
  if probe_only:
   report=snapshot(pid,engine,[36,3*60+36]);record.setdefault('probes',{})[engine]=report
   print(engine,'snapshots',json.dumps(report['frames']),flush=True);store.write_json(OUT/'design-atlas.json',record);continue
  job=store.create_job(pid,'final');Worker().run(job['id']);result=agent.result(job['id']);assert result['state']=='completed',result['error']
  path=store.folder(pid)/'jobs'/job['id']/'final.mp4';video=OUT/f'design-library-{engine}.mp4';shutil.copyfile(path,video)
  command([FFMPEG,'-v','error','-xerror','-i',video,'-f','null','-'])
  frames=[]
  # Observe chunks because perception intentionally caps a packet at12 frames.
  for offset in range(0,record['pages'],12):
   packet=observe(video,timestamps=[i*2+1.2 for i in range(offset,min(record['pages'],offset+12))],max_frames=12,width=1280)
   for frame in packet['frames']:frames.append(frame)
  for entry in record['entries']:
   frame=frames[entry['page']];dest=PREV/f'{engine}-page-{entry["page"]:02d}.jpg'
   shutil.copyfile(frame['path'],dest)
   if engine=='remotion':record['previews'][f'{entry["kind"]}/{entry["id"]}']={'path':str(dest),'method':'Actual rendered Remotion frame','timestamp':entry['timestamp']}
  record['engines'][engine]={'video':str(video),'sha256':sha256(video),'job_id':job['id'],'report':result['output']['report'],'frames':frames,'decoder_errors':0}
  store.write_json(OUT/'design-atlas.json',record);print(engine,'complete',flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--reuse',action='store_true');parser.add_argument('--probe',action='store_true');args=parser.parse_args()
 record=store.read_json(OUT/'design-atlas.json') if args.reuse else build();render(record,args.probe)
