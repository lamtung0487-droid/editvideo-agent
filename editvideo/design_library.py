"""Offline design assets, semantic tokens and executable visual composition.

Choices are art direction starting points. Contrast/glyph evidence is supplied
to the calling multimodal AI; it is never converted into a beauty score.
"""
import copy,json,re,shutil,unicodedata
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from . import store
from .media import sha256

FONT_ROOT=store.ROOT/'assets/fonts'
ROLES=('display','headline','title','body','caption','label','source','data','quote','code')
COLORS=('background','surface','text','muted','accent','secondary','on_accent')
PALETTE_ROWS=[
 ('forest','Rừng sâu / tri thức tự nhiên','#102322','#19362f','#f2f7ef','#b2c9be','#81e6be','#e8bf75'),
 ('ink_gold','Mực và vàng / tài liệu','#101820','#1d2b38','#f6f4ee','#bbc5ce','#e4b866','#8ed5d0'),
 ('paper','Giấy / lịch sử văn hóa','#f4efe4','#e6dece','#292823','#5d594e','#8b3c24','#35655a'),
 ('science','Khoa học / phân tích','#081e32','#142f46','#eef8ff','#afc9db','#65d6ff','#ffd07e'),
 ('studio_white','Trắng / giải thích rõ ràng','#fafaf7','#e9ede8','#1d2c28','#58655e','#176855','#8b492e'),
 ('berry','Văn hóa / sáng tạo','#24142b','#38223f','#faf0ff','#d3bddc','#f7a7dc','#b2d9a3'),
 ('electric','Nhanh / kỹ thuật','#10111e','#25283e','#f5f5ff','#b9bfdf','#a7b5ff','#85e6ce'),
 ('ocean','Bình tĩnh / đại dương','#092832','#15414d','#f0fbfc','#b1d3d7','#78ded8','#f1cb8f'),
 ('terracotta','Ấm / kể chuyện','#30201c','#49352d','#fff4e8','#d9c2b2','#ffbd92','#b6d5b9'),
 ('slate','Trung tính / phóng sự','#1b232b','#2c3844','#f5f8fa','#b7c3ce','#a8d3ec','#e8cb9b'),
 ('citrus','Tươi / kiến thức ngắn','#f9f5df','#eee6b8','#303218','#646341','#586b18','#a4481c'),
 ('rose','Mềm / phỏng vấn','#fbf0ee','#efd9d6','#372d30','#6c555d','#87435b','#346c68'),
 ('noir','Đơn sắc / trọng tâm','#111111','#272727','#fafafa','#bfbfbf','#e6e6e6','#a4cbd5'),
 ('indigo','Dữ liệu / chiều sâu','#191b36','#2e3150','#f5f4ff','#c0bedb','#c1b6ff','#a0e6cf'),
 ('sage','Nhẹ / học tập','#edf2e7','#d9e3d0','#27372a','#556653','#366341','#804a28'),
 ('crimson','Điểm nhấn / lập luận','#28141a','#40242d','#fff4f5','#dbc1ca','#ffb1bf','#b5d7e7'),
 ('blueprint','Bản vẽ / quy trình','#112c53','#214574','#eff7ff','#bbd0ee','#ffda80','#99dcd7'),
 ('sand','Địa lý / du lịch','#f4e8cf','#e4d1a9','#353024','#635b43','#735319','#245d64'),
 ('lavender','Ý tưởng / tư duy','#f2effa','#e0d9ed','#302a42','#61596f','#654591','#326662'),
 ('amber','Tư liệu / ánh sáng ấm','#201c13','#393121','#fff7e4','#d3c6a9','#f6ca72','#a5d1bd'),
 ('arctic','Sạch / công nghệ','#edf6fa','#d8e9f2','#203340','#506875','#265d86','#665389'),
 ('magenta','Sự kiện / tiêu đề mạnh','#261025','#41223f','#fff1fc','#dfbad8','#ffb1ec','#a4e9df'),
 ('moss','Sinh học / thực địa','#222619','#363d25','#f5f6e8','#c4cbaa','#d2df8b','#efc3a1'),
 ('cobalt','Giáo dục / đối chiếu','#f2f4ff','#dde3f6','#202d52','#566181','#284bb5','#865826')]

def luminance(color):
 if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Color requires #RRGGBB')
 v=[int(color[i:i+2],16)/255 for i in (1,3,5)]
 v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v]
 return sum(a*b for a,b in zip(v,(.2126,.7152,.0722)))
def contrast(a,b):
 x,y=sorted((luminance(a),luminance(b)));return (y+.05)/(x+.05)

def derive_palette(seed='#81e6be',harmony='analogous',tone='dark'):
 import colorsys
 luminance(seed)
 if harmony not in ('analogous','complementary','split_complementary','triadic','monochrome') or tone not in ('dark','light'):raise ValueError('Invalid harmony/tone')
 rgb=[int(seed[i:i+2],16)/255 for i in (1,3,5)];h,l,s=colorsys.rgb_to_hls(*rgb)
 def rgbhex(h,l,s):return '#'+''.join(f'{round(c*255):02x}' for c in colorsys.hls_to_rgb(h%1,l,s))
 shift={'analogous':1/12,'complementary':.5,'split_complementary':5/12,'triadic':1/3,'monochrome':0}[harmony]
 roles={'background':rgbhex(h,.075 if tone=='dark' else .965,min(s,.25)),
  'surface':rgbhex(h,.14 if tone=='dark' else .91,min(s,.22)),
  'text':rgbhex(h,.96 if tone=='dark' else .13,min(s,.1)),
  'muted':rgbhex(h,.75 if tone=='dark' else .35,min(s,.18)),
  'accent':seed,'secondary':rgbhex(h+shift,.7 if tone=='dark' else .36,min(max(s,.3),.7))}
 roles['on_accent']=max(('#101010','#ffffff'),key=lambda c:contrast(c,seed))
 return {'harmony':harmony,'tone':tone,'roles':roles,'contrast':{f'{a}/{b}':round(contrast(roles[a],roles[b]),3) for a,b in [('text','background'),('muted','surface'),('on_accent','accent'),('accent','background')]},'apply':'set_design.color_roles/background/palette; consider using accent as a fill with on_accent text if accent/background contrast is low. Geometry in HSL is an option generator, not perceptual uniformity, color-vision simulation or automatic grading.'}

def pick_face(item,weight,italic=False):
 """The bundled face a browser would use for a weight: the one whose range holds it, else the nearest (CSS font
 matching). A 500 asked of a 400/600/700 family had raised here while every browser simply drew the nearest."""
 faces=[f for f in item['faces'] if f['style']==('italic' if italic else 'normal')] or item['faces']
 rng=lambda f:(int(f['weight'].split()[0]),int(f['weight'].split()[-1]))
 hit=next((f for f in faces if rng(f)[0]<=weight<=rng(f)[1]),None)
 if hit or not faces:return hit
 up=sorted((f for f in faces if rng(f)[0]>weight),key=lambda f:rng(f)[0]);down=sorted((f for f in faces if rng(f)[1]<weight),key=lambda f:-rng(f)[1])
 if 400<=weight<=500:  # CSS Fonts 4: heavier up to 500, then lighter, then heavier still
  order=[f for f in up if rng(f)[0]<=500]+down+[f for f in up if rng(f)[0]>500]
 else:order=down+up if weight<400 else up+down
 return order[0]


def face_weight(item,weight,italic=False):
 """The weight to draw with: the asked one inside the picked face's range, else its nearest bound."""
 f=pick_face(item,weight,italic);lo,hi=int(f['weight'].split()[0]),int(f['weight'].split()[-1])
 return min(hi,max(lo,weight))
def layout_text(font_id,text,size=54,width=800,weight=400,italic=False,variation_axes=None):
 """Exact bundled glyph advance probe in FreeType; browser wrapping can differ."""
 text=text.replace('**','').replace('==','')  # inline emphasis markup is not drawn as glyphs
 from PIL import ImageFont
 from fontTools.ttLib import TTFont
 if not isinstance(text,str) or not 1<=len(text)<=2000 or not 12<=size<=300 or not 100<=width<=4000:raise ValueError('Text1..2000 chars, size12..300, width100..4000px')
 item=font(font_id);face=pick_face(item,weight,italic)
 if not face:raise ValueError('Requested weight/style not bundled')
 weight=face_weight(item,weight,italic)  # measured with the face a browser draws
 from .models import TypeStyle
 axes=TypeStyle(font_id=font_id,size=size,weight=weight,italic=italic,variation_axes=variation_axes or {}).variation_axes
 path=FONT_ROOT/face['file'];text=unicodedata.normalize('NFC',text)
 glyph=ImageFont.truetype(str(path),round(size))
 if face['axes']:glyph.set_variation_by_axes([weight if k=='wght' else axes.get(k,a[1]) for k,a in face['axes'].items()])
 with TTFont(path) as font_file:cmap=font_file.getBestCmap()
 missing=sorted({c for c in text if not c.isspace() and ord(c) not in cmap})
 lines=[];overlong=[]
 for paragraph in text.split('\n'):
  line=''
  for word in paragraph.split():
   trial=(line+' '+word).strip()
   if line and glyph.getlength(trial)>width:lines.append(line);line=word
   else:line=trial
   if glyph.getlength(word)>width:overlong.append(word)
  lines.append(line)
 ascent,descent=glyph.getmetrics()
 return {'font_id':font_id,'font_sha256':face['sha256'],'variation_axes':axes,'normalization':'NFC','lines':lines,'line_widths':[round(glyph.getlength(s),2) for s in lines],
  'glyph_bounds':[list(glyph.getbbox(s)) for s in lines],'ascent':ascent,'descent':descent,'line_count':len(lines),
  'suggested_height':round(max(ascent+descent,size*1.45)*len(lines)),'missing_glyphs':missing,'overlong_tokens':overlong,
  'limits':'FreeType advance/bounds with bundled weight; browser shaping, tracking, actual CSS width, motion overshoot and line height can differ. Use this to plan explicit newlines; inspect actual engine snapshot. No semantic segmentation or reading-time prediction.'}
def fit_width(font_id,text,size,canvas_width,weight=400,pad_px=24,tracking=0):
 """Layer width (canvas share) that wraps one line of text plus padding: a label's background plate then hugs its
 words instead of spanning a wide box (measured on the bundled font; browsers differ by a few pixels). tracking: the
 widest letter spacing the text reaches (em, CSS letter-spacing after every character, e.g. a `tracking` effect)."""
 m=layout_text(font_id,text,max(12,min(300,round(size))),4000,weight)
 return round(min(1.0,(max(m['line_widths'] or [0])+max(0,tracking)*size*len(text)+2*pad_px+4)/canvas_width),4)
def fit_size(font_id,text,width,canvas_width=1080,weight=400,start=120,minimum=24,tracking=0):
 """Largest size (<= start, step 2) at which every authored line of text fits a text layer `width` (canvas share) on
 ONE line, the engines' 24 px padding each side included, at its widest tracking (em). A typography_role overrides
 font_size: set font_id instead."""
 size=start
 while size>minimum and any(fit_width(font_id,line,size,canvas_width,weight,tracking=tracking)>width for line in str(text).splitlines() if line.strip()):size-=2
 return size
def glyph_mask(font_id,lines,size,weight=400,tracking=0,line_height=1.2,italic=False):
 """Rasterize text lines with the bundled face (same face/axes choice as layout_text) into a boolean mask.
 Lines are left-aligned; tracking in em is applied per character like CSS letter-spacing. Returns (mask, line_px)."""
 import numpy as np
 from PIL import Image,ImageDraw,ImageFont
 item=font(font_id);face=pick_face(item,weight,italic)
 if not face:raise ValueError('Requested weight/style not bundled')
 g=ImageFont.truetype(str(FONT_ROOT/face['file']),round(size))
 if face['axes']:g.set_variation_by_axes([weight if k=='wght' else a[1] for k,a in face['axes'].items()])
 lines=[unicodedata.normalize('NFC',l) for l in lines];ascent,descent=g.getmetrics();line_px=size*line_height
 adv=lambda l:sum(g.getlength(c) for c in l)+tracking*size*max(0,len(l)-1)
 W=int(max(adv(l) for l in lines))+8;H=int(line_px*len(lines))+8
 img=Image.new('L',(W,H),0);d=ImageDraw.Draw(img)
 for i,l in enumerate(lines):
  x=0.0;base=i*line_px+(line_px-(ascent+descent))/2+ascent
  for c in l:
   d.text((x,base),c,font=g,fill=255,anchor='ls');x+=g.getlength(c)+tracking*size
 return np.asarray(img)>127,line_px
def _mark_gaps(m, base, size, cap_top):
 """Per column: the true 2D gap between a detached mark and the nearest ink of its own letter, for marks wholly under
 the baseline (dot below) and wholly above the capital height (hat, breve, hook, acute); 0 where there is none."""
 import numpy as np
 from scipy import ndimage
 lab, n = ndimage.label(m)
 below, above = np.zeros(m.shape[1]), np.zeros(m.shape[1])
 if n < 2:
  return below, above
 sl = ndimage.find_objects(lab)
 marks = [k + 1 for k, s_ in enumerate(sl) if s_[0].start > base + .02 * size or s_[0].stop - 1 < cap_top - .01 * size]
 if not marks:
  return below, above
 for k in marks:  # nearest other ink: its letter, or the mark it is stacked on (acute over circumflex)
  s_ = sl[k - 1]
  pad = int(.5 * size)
  win = (slice(max(0, s_[0].start - pad), s_[0].stop + pad), slice(max(0, s_[1].start - pad), s_[1].stop + pad))
  other = m[win] & (lab[win] != k)
  if not other.any():
   continue
  dist = ndimage.distance_transform_edt(~other)
  gap = float(dist[lab[win] == k].min()) - 1
  tgt = below if s_[0].start > base else above
  tgt[s_[1]] = np.maximum(tgt[s_[1]], gap)
 return below, above


def stack_line_height(font_id,lines,weight=400,tracking=0,clearance_em=.06,italic=False,size=200):
 """Smallest CSS line height (x font size) at which stacked lines stay apart AND every mark still reads as belonging to
 its own letter: a dot below on one line versus a hat, breve or hook above on the next (Vietnamese stacks). Ink is
 measured from the bundled glyphs for centred and left-aligned lines. The gap between lines must be at least
 clearance_em and at least 2.5x the mark's own gap to its letter (grouping by proximity): a dot exactly between Ạ and
 the breve of Ă belongs to neither, and TRĂNG reads TRẮNG even though nothing touches."""
 import numpy as np
 from PIL import ImageFont
 item=font(font_id);face=pick_face(item,weight,italic)
 if not face:raise ValueError('Requested weight/style not bundled')
 g=ImageFont.truetype(str(FONT_ROOT/face['file']),size)
 if face['axes']:g.set_variation_by_axes([weight if k=='wght' else a[1] for k,a in face['axes'].items()])
 ascent,descent=g.getmetrics();lh=3.0;base=(size*lh-(ascent+descent))/2+ascent
 cap_top=base-ascent+g.getbbox('H')[1]  # top of a capital (PIL bounds are measured from the ascender line)
 lines=[unicodedata.normalize('NFC',l.replace('**','').replace('==','')) for l in lines]
 if len(lines)<2:return {'line_height':0.0,'pairs':[]}
 prof=[]
 for l in lines:
  m,_=glyph_mask(font_id,[l],size,weight,tracking,lh,italic);cols=m.any(0)
  top=np.where(cols,m.argmax(0),10**6)-base;bottom=np.where(cols,m.shape[0]-1-m[::-1].argmax(0),-10**6)-base
  gb,ga=_mark_gaps(m,base,size,cap_top)
  w=int(np.nonzero(cols)[0].max()+1) if cols.any() else 0;prof.append((top[:w],bottom[:w],w,gb[:w],ga[:w]))
 c=max(1,round(clearance_em*size));width=max(p[2] for p in prof)+2*c;need=[];pairs=[]
 for i in range(len(prof)-1):
  (t0,b0,w0,gb0,_),(t1,b1,w1,_,ga1)=prof[i],prof[i+1];worst=0.0
  for align in ('center','left'):
   o0,o1=((width-w0)//2,(width-w1)//2) if align=='center' else (c,c)
   B=np.full(width,-10**6,float);T=np.full(width,10**6,float);GB=np.zeros(width);GA=np.zeros(width)
   B[o0:o0+len(b0)]=b0;T[o1:o1+len(t1)]=t1;GB[o0:o0+len(gb0)]=gb0;GA[o1:o1+len(ga1)]=ga1
   near=lambda a:np.max(np.stack([np.roll(a,k) for k in range(-c,c+1)]),0)  # neighbouring columns count (diagonal proximity)
   Bd,GBd=near(B),near(GB)
   ok=(Bd>-10**5)&(T<10**5)
   if ok.any():
    gap=np.maximum(c,2.5*np.maximum(GBd,GA))  # proximity grouping: clearly farther from the other line than from its own letter
    worst=max(worst,float(np.max((Bd-T+gap)[ok])))
  need.append(worst/size);pairs.append({'lines':[i,i+1],'line_height':round(worst/size,3)})
 return {'line_height':round(max(need),3),'pairs':pairs,'clearance_em':clearance_em,'rule':'gap >= max(clearance, 2.5 x a mark own gap)'}
def palette(fid):
 row=next((r for r in PALETTE_ROWS if r[0]==fid),None)
 if not row:raise ValueError('Unknown palette_id; discover design_catalog')
 roles=dict(zip(COLORS[:-1],row[2:]));a=roles['accent']
 roles['on_accent']=max(('#101010','#ffffff'),key=lambda c:contrast(c,a))
 return {'id':row[0],'name':row[1],'roles':roles,'contrast':{f'{a}/{b}':round(contrast(roles[a],roles[b]),3) for a,b in [('text','background'),('text','surface'),('muted','background'),('muted','surface'),('on_accent','accent')]},'usage':'Use accent for one focal claim; secondary for a different category. Keep text on a solid surface over busy footage. Numeric contrast applies to opaque swatches only; inspect real rendered footage/size/compression.'}

MOTIONS={
 'quiet':{'purpose':'Tài liệu, suy ngẫm','effects':['fade_in','rise'],'frames':18,'amount':18,'avoid':['shake','flash','orbit']},
 'clean':{'purpose':'Giải thích rõ ràng','effects':['line_reveal'],'frames':22,'amount':24,'avoid':['tracking_in','glow']},
 'punch':{'purpose':'Một ý ngắn nổi bật','effects':['word_reveal'],'frames':18,'amount':32,'avoid':['shake','flash']},
 'editorial':{'purpose':'Trích dẫn, chương','effects':['fade_in','marker_reveal'],'frames':24,'amount':.12,'avoid':['spin','flip_x']},
 'diagram':{'purpose':'Quy trình, sơ đồ','effects':['progress','fade_in'],'frames':30,'amount':1,'avoid':['orbit','shake']},
 'reference':{'purpose':'Ảnh tư liệu','effects':['focus_zoom'],'frames':90,'amount':.04,'avoid':['hue','invert']},
 'inset':{'purpose':'Chi tiết bằng chứng','effects':['fade_in','rounded','border'],'frames':16,'amount':1,'avoid':['flash']},
 'section':{'purpose':'Đổi chương','effects':['wipe_left'],'frames':16,'amount':1,'avoid':['light_sweep']},
 'label':{'purpose':'Nhãn chủ thể','effects':['fade_in','slide_spring'],'frames':18,'amount':28,'avoid':['float','tracking_in']},
 'numeric':{'purpose':'Con số có đơn vị','effects':['progress'],'frames':30,'amount':1,'avoid':['shake']},
 'texture':{'purpose':'Trang giấy nhẹ','effects':['paper_grain'],'frames':1,'amount':.035,'avoid':['scanlines']},
 'single_sweep':{'purpose':'Một điểm nhấn sáng','effects':['light_sweep'],'frames':30,'amount':.12,'avoid':['flash','glow']}}
STYLE_ROWS=[
 ('vietnam_knowledge','Tri thức Việt','bevietnampro','bevietnampro','forest','clean'),
 ('documentary','Tư liệu điện ảnh','notoserif','sourcesans3','ink_gold','quiet'),
 ('editorial_paper','Bài luận trên giấy','lora','sourcesans3','paper','editorial'),
 ('science_lab','Khoa học và bằng chứng','robotoslab','notosans','science','diagram'),
 ('minimal_explainer','Giải thích tối giản','manrope','inter','studio_white','clean'),
 ('short_bold','Kiến thức ngắn mạnh','archivo','bevietnampro','electric','punch'),
 ('culture_story','Văn hóa và câu chuyện','vollkorn','notosans','terracotta','quiet'),
 ('friendly_learning','Học tập thân thiện','comfortaa','lexend','sage','clean'),
 ('technical_blueprint','Giải thích kỹ thuật','oswald','sourcesans3','blueprint','diagram'),
 ('data_report','Phân tích dữ liệu','inter','notosans','slate','numeric'),
 ('ocean_calm','Nhịp điệu nhẹ','bitter','manrope','ocean','quiet'),
 ('creative_essay','Luận điểm sáng tạo','montserrat','lora','berry','editorial'),
 ('history_archive','Lịch sử và tư liệu','notoserif','bevietnampro','amber','reference'),
 ('bright_education','Giáo dục sáng','lexend','sourcesans3','arctic','clean'),
 ('nature_field','Thiên nhiên thực địa','bitter','notosans','moss','reference'),
 ('monochrome_focus','Đơn sắc có trọng tâm','archivo','inter','noir','label'),
 ('cinema_documentary','Phim tài liệu điện ảnh','montserrat','bevietnampro','ink_gold','quiet')]
# Cinema type: sans serif only, light wide-tracked capitals for titles (film title cards), a medium tracked face for
# years and places, a highly legible Vietnamese sans for subtitles and context; sizes for a 1080 px short side.
TYPE_OVERRIDES={'cinema_documentary':{'display':(None,150,200,1.1,.2),'headline':(None,84,300,1.15,.1),'title':(None,60,300,1.2,.06),
  'label':(None,32,500,1.3,.18),'caption':('body',38,400,1.35,0),'body':('body',40,400,1.45,0),'source':('body',24,400,1.4,.04),
  'data':(None,72,300,1.2,.02),'quote':(None,56,300,1.35,.02)}}
PATTERNS=('grid','dots','stripes','diagonal','checker','crosshatch','hexagons','rings','waves','contour','speckles','gradient')
ICONS=('play','pause','check','close','arrow_right','arrow_up','info','question','lightbulb','book','eye','camera','mic','clock','link','chart','code','location','star','heart','volume','search','target','spark')
COMPONENTS=('title','quote','statistic','chapter','source_card','two_column','steps','lower_third','keyword','end_card')

def font_manifest():return json.loads((FONT_ROOT/'manifest.json').read_text(encoding='utf-8'))
def font(fid):
 item=next((f for f in font_manifest()['fonts'] if f['id']==fid),None)
 if not item:raise ValueError('Unknown bundled font_id; discover design_catalog')
 return item
def font_family(fid):return f'"EV {font(fid)["id"]}", sans-serif'
def tokens(style_id,palette_id=None,heading_font_id=None,body_font_id=None):
 row=next((r for r in STYLE_ROWS if r[0]==style_id),None)
 if not row:raise ValueError('Unknown style_id')
 _,name,heading,body,pal,motion=row;heading=heading_font_id or heading;body=body_font_id or body
 font(heading);font(body);color=palette(palette_id or pal)
 specs={
 'display':(heading,112,700,1.18,-.02),'headline':(heading,84,700,1.25,-.015),
 'title':(heading,64,600,1.28,-.01),'body':(body,42,400,1.5,0),
 'caption':(body,54,700,1.45,0),'label':(body,32,600,1.4,.02),
 'source':(body,28,400,1.45,0),'data':('ibmplexmono',64,600,1.25,0),
 'quote':('lora',66,400,1.45,0),'code':('ibmplexmono',34,400,1.5,0)}
 for k,(f,sz,w,lh,ls) in TYPE_OVERRIDES.get(style_id,{}).items():specs[k]=(body if f=='body' else heading if f is None else f,sz,w,lh,ls)
 return {'style_id':style_id,'intent':name,'font_family':font_family(body),'background':color['roles']['background'],
  'palette':list(color['roles'].values()),'color_roles':color['roles'],
  'typography':{k:{'font_id':f,'size':s,'weight':w,'line_height':lh,'tracking':ls} for k,(f,s,w,lh,ls) in specs.items()},
  'notes':f'Motion direction: {motion}. Sizes authored for 1080px short side. Apply roles explicitly; preserve meaningful source colors. One focal motion per beat; inspect reading time, diacritics and occupied bounds.'}

def _brief_entry(e):
 """Listing row: what the AI chooses by. File hashes, source URLs and full token tables return for an exact id query."""
 drop={'license_file','license_sha256','faces','coverage','source','sha256','pairing','combination','css_family','language'}
 b={k:v for k,v in e.items() if k not in drop and v is not None}
 if isinstance(b.get('preview'),dict):b['preview']=b['preview'].get('path')
 if e.get('kind')=='font':b['weights']=sorted({f.get('weight') for f in e.get('faces',[])} - {None});b['italic']=any(f.get('style')=='italic' for f in e.get('faces',[]))
 if e.get('kind')=='style':
  t=e.get('tokens') or {};ty=t.get('typography') or {}
  b['tokens']={'heading':(ty.get('display') or {}).get('font_id'),'body':(ty.get('body') or {}).get('font_id'),'palette':t.get('palette'),'intent':t.get('intent')}
 return b

def catalog(kind='all',query='',offset=0,limit=12):
 if kind not in ('all','font','palette','style','motion','component','pattern','icon') or not 0<=offset or not 1<=limit<=50:raise ValueError('Invalid kind/page; limit1..50')
 entries=[]
 if kind in ('all','font'):
  tags={'sans':'không chân rõ ràng phụ đề nội dung kiến thức','serif':'có chân tài liệu trích dẫn văn hóa','condensed':'hẹp cô đọng tiêu đề nhãn ngắn','mono':'đơn cách mã code số liệu đơn vị','rounded':'bo tròn thân thiện học tập','slab':'chân vuông vững tiêu đề khoa học'}
  entries.extend({'kind':'font',**f,'css_family':font_family(f['id']),'language':'tiếng Việt / Vietnamese','tags':tags[f['category']]} for f in font_manifest()['fonts'])
 if kind in ('all','palette'):entries.extend({'kind':'palette',**palette(r[0])} for r in PALETTE_ROWS)
 if kind in ('all','style'):entries.extend({'kind':'style','id':r[0],'name':r[1],'tokens':tokens(r[0]),'motion_id':r[-1],'pairing':'Expressive heading + stable readable body; data uses mono, quote uses serif. Swap a role deliberately, not every shot.'} for r in STYLE_ROWS)
 if kind in ('all','motion'):entries.extend({'kind':'motion','id':k,**v,'combination':'Suggested choices, not a command to stack every listed effect. Use measured beat boundaries; hold after entrance.'} for k,v in MOTIONS.items())
 for category,items in [('component',COMPONENTS),('pattern',PATTERNS),('icon',ICONS)]:
  if kind in ('all',category):entries.extend({'kind':category,'id':k,'usage':'compose_graphic' if category=='component' else f'upsert_layer kind={category}, data.{category}={k}; normalized bounds, procedural original SVG; not a fetched stock asset'} for k in items)
 terms=unicodedata.normalize('NFC',query).casefold().replace('_',' ').split()
 if terms:entries=[e for e in entries if all(t in unicodedata.normalize('NFC',json.dumps(e,ensure_ascii=False)).casefold().replace('_',' ') for t in terms)]
 atlas=store.atlas_path('design-atlas.json')
 previews=store.read_json(atlas).get('previews',{}) if atlas.exists() else {}
 for e in entries:
  pv=previews.get(f'{e["kind"]}/{e["id"]}')
  e['preview']={**pv,'path':store.repo_path(pv['path'])} if pv else None
 page=entries[offset:offset+limit]
 exact=[e for e in page if e['id']==query.strip()]
 if exact:page=exact
 elif len(page)>1:page=[_brief_entry(e) for e in page]
 return {'kind':kind,'total':len(entries),'offset':offset,'items':page,'next_offset':offset+limit if offset+limit<len(entries) else None,'guide':str(store.ROOT/'docs/DESIGN_LIBRARY.md'),'scope':'Font files and licenses bundled/offline. Swatch contrast is evidence, not a beauty score. Components compile editable layers; icons/patterns are procedural SVG.'}

def embed_fonts(source,timeline):
 """Data-only refresh: never modifies authored runtime/entry."""
 design=timeline.get('design',{});ids=set(design.get('bundled_font_ids',[]))
 ids.update(s['font_id'] for s in design.get('typography',{}).values())
 ids.update(l['font_id'] for l in timeline.get('layers',[]) if l.get('font_id'))
 ids.update(re.findall(r'EV ([a-z0-9]+)',design.get('font_family','')))
 root=source/'public/fonts';root.mkdir(parents=True,exist_ok=True);faces=[];used=[]
 for fid in sorted(ids):
  item=font(fid);used.append(item)
  for face in item['faces']:
   path=FONT_ROOT/face['file'];target=root/face['file'];target.parent.mkdir(exist_ok=True)
   if sha256(path)!=face['sha256']:raise ValueError(f'Bundled font changed: {fid}; restore verified font asset')
   if not target.exists() or sha256(target)!=face['sha256']:shutil.copyfile(path,target)
   faces.append({'family':'EV '+fid,'src':'fonts/'+face['file'],'weight':face['weight'],'style':face['style'],'sha256':face['sha256']})
  license=FONT_ROOT/item['license_file']
  if sha256(license)!=item['license_sha256']:raise ValueError('Font license hash changed')
  shutil.copyfile(license,root/item['license_file'])
  copyright=FONT_ROOT/fid/'COPYRIGHT.txt'
  if copyright.exists():shutil.copyfile(copyright,root/fid/'COPYRIGHT.txt')
 store.write_json(root/'manifest.json',{'revision':font_manifest()['revision'],'fonts':used})
 return faces

class ApplyDesign(BaseModel):
 model_config=ConfigDict(extra='forbid')
 style_id:str
 palette_id:str|None=None
 heading_font_id:str|None=None
 body_font_id:str|None=None
 layer_roles:dict[str,Literal['display','headline','title','body','caption','label','source','data','quote','code']]=Field(default_factory=dict,max_length=100)

def apply(pid,base_revision,request):
 from . import agent
 q=ApplyDesign.model_validate(request);p=agent.read(pid)
 if not p['timeline']:raise ValueError('Apply design requires a current locked plan; plan first')
 design=tokens(q.style_id,q.palette_id,q.heading_font_id,q.body_font_id)
 ops=[{'op':'set_design','design':design}];layers={l['id']:l for l in p['timeline']['layers']}
 for lid,role in q.layer_roles.items():
  if lid not in layers:raise ValueError(f'Layer missing: {lid}')
  layer=copy.deepcopy(layers[lid]);layer['typography_role']=role
  if layer['kind'] not in ('text','caption','counter','callout'):raise ValueError('Type role requires text/caption/counter/callout layer')
  ops.append({'op':'upsert_layer','layer':layer})
 result=agent.patch(pid,base_revision,ops)
 return {'revision':result['revision'],'design':design,'changed_layers':list(q.layer_roles),'runtime':'Fresh exports support role/font loading. Existing customized source must deliberately merge design.cjs/design.js and entry integration; ordinary patches preserve source. Effects are suggestions, not automatically stacked.'}

class GraphicRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 component:Literal['title','quote','statistic','chapter','source_card','two_column','steps','lower_third','keyword','end_card']='title'
 id:str=Field(default='graphic',pattern=r'^[A-Za-z0-9_-]{1,60}$')
 start_frame:int=Field(default=0,ge=0)
 end_frame:int=Field(gt=0)
 text:str=Field(default='',max_length=300)
 detail:str=Field(default='',max_length=600)
 labels:list[str]=Field(default_factory=list,max_length=8)
 value:float=Field(default=0,allow_inf_nan=False,ge=-1e12,le=1e12)
 unit:str=Field(default='',max_length=30)
 source:str=Field(default='',max_length=300)
 pattern:Literal['grid','dots','stripes','diagonal','checker','crosshatch','hexagons','rings','waves','contour','speckles','gradient']|None=None

def compose(pid,base_revision,request):
 from . import agent
 from .models import Layer
 q=GraphicRequest.model_validate(request);p=agent.read(pid);t=p['timeline'];d=q.end_frame-q.start_frame
 if not t or not t['design'].get('typography'):raise ValueError('Apply a design style to the locked plan first')
 if d<=0 or q.end_frame>t['total_frames']:raise ValueError('Graphic range outside locked timeline')
 if not q.text.strip():raise ValueError('Meaningful heading required')
 if q.component in ('statistic','source_card') and not q.source.strip():raise ValueError('Visible source required; caller verifies actual data/claim')
 if q.component in ('steps','two_column') and not (2<=len(q.labels)<= (2 if q.component=='two_column' else 8)):raise ValueError('Provide2 labels for comparison or2..8 steps')
 if any(len(label)>120 for label in q.labels):raise ValueError('Graphic labels <=120 chars')
 prefix=q.id+'-';ops=[{'op':'delete_layer','id':l['id']} for l in t['layers'] if l['id'].startswith(prefix)]
 vertical=t['height']>t['width'];left=.09;w=.82;top=.17 if vertical else .14
 enter=min(24,max(1,d-1));effects=[{'name':'line_reveal','end_frame':enter,'params':{'amount':24}}] if d>1 else []
 def block(text,role,fraction=w):
  token=t['design']['typography'][role];scale=min(t['width'],t['height'])/1080
  measured=layout_text(token['font_id'],text,token['size']*scale,fraction*t['width'],token['weight'],token.get('italic',False),token.get('variation_axes'))
  if measured['overlong_tokens'] or measured['missing_glyphs']:raise ValueError('Graphic text has an overlong token/missing glyph; choose font/size or explicit custom layout')
  return '\n'.join(measured['lines']),max(token['size']*scale*token['line_height'],measured['ascent']+measured['descent'])*len(measured['lines'])/t['height']
 def add(suffix,**kw):
  item={'id':prefix+suffix,'kind':'text','start_frame':q.start_frame,'end_frame':q.end_frame,'x':left,'y':top,'width':w,'height':.25,'z':120,'color_role':'text','typography_role':'headline',**kw}
  layer=Layer.model_validate(item).model_dump();ops.append({'op':'upsert_layer','layer':layer})
 # A controlled solid canvas; subject-overlay lower thirds intentionally omit it.
 if q.component not in ('lower_third','keyword'):
  add('surface',kind='shape',x=0,y=0,width=1,height=1,z=90,typography_role=None,color_role='background',data={'shape':'rectangle','corner_radius':0})
  if q.pattern:add('pattern',kind='pattern',x=0,y=0,width=1,height=1,z=92,opacity=.09,typography_role=None,color_role='accent',data={'pattern':q.pattern,'spacing':60,'seed':7})
 if q.component=='lower_third':
  heading,hh=block(q.text,'title',w-.04);detail,dh=block(q.detail,'label',w-.04) if q.detail else ('',0)
  gap=.012 if q.detail else 0;plate_h=hh+dh+gap+.04
  if plate_h>.32:raise ValueError('Lower-third text exceeds reserved region; shorten or reduce type sizes before composing')
  y=.86-plate_h
  add('plate',kind='shape',y=y,height=plate_h,z=100,typography_role=None,color_role='surface',data={'corner_radius':12})
  add('heading',text=heading,x=left+.02,width=w-.04,y=y+.02,height=hh,typography_role='title',effects=effects)
  if q.detail:add('detail',text=detail,x=left+.02,width=w-.04,y=y+.02+hh+gap,height=dh,typography_role='label',color_role='muted')
 elif q.component=='keyword':
  heading,hh=block(q.text,'display')
  if hh>.45:raise ValueError('Keyword exceeds reserved region; use a shorter phrase or smaller display size')
  add('heading',text=heading,y=.38,height=hh,typography_role='display',effects=[{'name':'word_reveal','end_frame':enter,'params':{'amount':28}}] if d>1 else [])
 else:
  heading,hh=block('“'+q.text+'”' if q.component=='quote' else q.text,'quote' if q.component=='quote' else 'headline')
  detail,dh=block(q.detail,'body') if q.detail else ('',0)
  source,sh=block(q.source,'source') if q.source else ('',0)
  source_y=min(.84 if vertical else .87,.96-sh)
  content_y=top+hh+.06
  if hh>.45 or source_y<.72 or content_y+ (dh if q.component not in ('statistic','steps','two_column') else .16) >source_y-.025:raise ValueError('Graphic text exceeds reserved layout; shorten text/reduce type sizes or author a custom composition')
  add('label',text={'title':'GIẢI THÍCH','chapter':'CHƯƠNG','quote':'TRÍCH DẪN','statistic':'DỮ LIỆU','source_card':'NGUỒN TƯ LIỆU','two_column':'ĐỐI CHIẾU','steps':'QUY TRÌNH','end_card':'ĐIỂM CẦN NHỚ'}[q.component],y=top-.065,height=.06,typography_role='label',color_role='accent')
  add('heading',text=heading,height=hh,typography_role='quote' if q.component=='quote' else 'headline',effects=effects)
  if q.component=='statistic':add('value',kind='counter',y=content_y,height=.16,typography_role='display',color_role='accent',data={'from':q.value,'to':q.value,'suffix':' '+q.unit})
  elif q.component in ('two_column','steps'):
   cols=2 if q.component=='two_column' or not vertical else 1;rows=(len(q.labels)+cols-1)//cols
   measured=[block(f'{i+1:02d}  '+label,'body',w/cols-.025) for i,label in enumerate(q.labels)];height=max(h for _,h in measured)
   if content_y+rows*height+(rows-1)*.025>source_y-.035:raise ValueError('Steps/comparison labels exceed layout; shorten/reduce type sizes or use multiple scenes')
   for i,(label,_) in enumerate(measured):
    add('item-'+str(i),text=label,x=left+(i%cols)*w/cols,y=content_y+(i//cols)*(height+.025),width=w/cols-.025,height=height,typography_role='body',color_role='text',effects=[{'name':'fade_in','start_frame':min(i*3,max(0,d-2)),'end_frame':min(enter+i*3,d-1)}] if d>2 else [])
  elif q.detail:add('detail',text=detail,y=content_y,height=dh,typography_role='body',color_role='muted')
  if q.source:add('source',text=source,y=source_y,height=sh,typography_role='source',color_role='muted')
 if len(ops)>100:raise ValueError('Component edit batch too large')
 result=agent.patch(pid,base_revision,ops)
 return {'revision':result['revision'],'operations':ops,'inspect_frames':[q.start_frame+min(enter,d-1),q.start_frame+d//2],'notes':'Editable typography/role layers, original SVG texture, stable data. Bounds are authored defaults; inspect actual text wrapping, duration, screen UI and subject collisions. No fabricated word timing/data/source.'}
