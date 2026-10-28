"""Discoverable editorial recipes compiled to real, revision-protected edits.

Platform guidance is a starting point, not an automatic beauty/retention score.
Semantic story decisions belong to the calling multimodal AI.
"""
import math
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from . import store,agent,platforms
from .models import Layer,AudioClip,AudioMix

PROFILES={
 'tiktok':{'aspect':'9:16 usually','safe_region':list(platforms.safe_area('tiktok')),'caption_y':.64,'font_size':54,
           'direction':'One clear promise early, native conversational language, demonstration/payoff, natural loop only when meaningful. UI margins are conservative editable defaults, not official pixel specifications. TikTok ad guidance is not an organic-video law.'},
 'reels':{'aspect':'9:16','safe_region':list(platforms.safe_area('reels')),'caption_y':.64,'font_size':54,
          'direction':'Same short-form craft as TikTok: the promise in the first seconds, captions for muted viewing, a payoff before the end; Meta publishes ad safe zones (14% top, 35% bottom, 6% sides).'},
 'youtube_shorts':{'aspect':'9:16 or square','safe_region':list(platforms.safe_area('shorts')),'caption_y':.66,'font_size':54,
                  'direction':'Start with a clear situation/question/result; make each image explain a spoken point; preserve context and leave room for mobile interface. No fixed cut interval.'},
 'youtube_long':{'aspect':'16:9 often','safe_region':[.06,.07,.94,.92],'caption_y':.80,'font_size':48,
                'direction':'Opening fulfills title/thumbnail promise; establish the question and stakes, build evidence/examples, use chapter landmarks, let complex explanations breathe, resolve the opening question. No invented retention prediction.'},
}
RECIPE_INFO={
 'hook_card':('Make the opening proposition visible','text and marker_reveal; one focal motion'),
 'lower_third':('Identify a speaker/place/concept without blocking action','name + secondary text, restrained slide_spring'),
 'chapter_card':('Signal a meaningful section change','large heading, section label, diagonal reveal'),
 'evidence_card':('Show a source image with visible attribution','contain image, caption/source, border and shadow'),
 'pull_quote':('Give one important statement time to read','quote and speaker/source, marker strip'),
 'keyword_callout':('Emphasize one term when it is spoken','short text, fade and rise; never every word'),
 'picture_in_picture':('Keep detail and surrounding explanation visible','contain video/image inset, rounded border'),
 'split_screen':('Show 2-4 clips at once (before/after, steps, angles)','asset_ids + source_starts; layout auto/rows/columns/grid with gutters; panels slide in staggered'),
 'comparison_labels':('Give two alternatives equal visual hierarchy','two clearly named labels; caller supplies actual images/data'),
 'focus_spotlight':('Direct attention to an inspected region','four outside dim panels; does not infer subject/depth'),
 'tracked_callout':('Connect a label to a measured point over time','SVG leader/anchor with target keyframes; source→canvas mapping required'),
 'word_captions':('Highlight spoken words while keeping phrase stable','timed caption layer, real word timestamps only; normal cues suppressed while active'),
 'chapter_progress':('Show progress within a defined section','bounded counter/progress bar; not arbitrary factual statistics'),
 'j_cut_audio':('Introduce selected audio before the visual cut','separate timed audio with verified source lead handle; avoid duplicating locked narration'),
 'l_cut_audio':('Carry selected audio after a visual cut','separate timed audio across boundary; caller chooses what dialogue/ambience to retain'),
 'sound_bridge':('Keep a continuous sound across a visual change','trim/gain/fade/duck audio clip; listen to placement'),
 'audio_finish':('Tune final loudness and dialogue/music relationship','two-pass master settings and configurable sidechain ducking'),
}


SHORT_FORM={'tiktok','reels','youtube_shorts'}
# Short-form templates. Each beat has a time window (s) and a purpose; 'tools' are the system calls that build it;
# 'evidence' says what backs the structure (P platform research, PR peer-reviewed, H practice only).
SHORT_TEMPLATES={
 'talking_head':{'beats':[('cold_open',0,3,'the strongest line first, its claim as on-screen text'),('points',3,None,'one point per 4-8 s; jump cuts on pauses; B-roll on concrete nouns'),('payoff_cta',-4,None,'answer the opening promise, then a text CTA >= 1.5 s')],
   'tools':['transcribe','condense_dialogue(cover=punch_in)','reframe_footage(focus=faces)','compose_edit word_captions(word_animation=pop)','shortform_audit'],
   'evidence':'P: the speaker addressing the camera is in 33% of top view-through ads; PR: second-person shots go with engagement. Cut pace 0.19-0.52/s (A); faster lowered completion.'},
 'how_to':{'beats':[('result_first',0,2,'show the finished result'),('steps',2,None,'numbered steps (1/3, 2/3...), one action each, <= 8 s'),('result_cta',-4,None,'result again + save/follow CTA')],
   'tools':['stabilize_footage','retime_footage(speed_keys)','compose_title','word_captions','shortform_audit'],'evidence':'P: recipe/demo is a documented TikTok format; key message by 3 s.'},
 'listicle':{'beats':[('promise',0,2.5,'the number and the promise ("3 ...") as text'),('items',2.5,None,'one item per 4-8 s with its number on screen; best item last'),('recap_loop',-3,None,'recap or a line that leads back to the start')],
   'tools':['sequence_plan','compose_title','word_captions','design_sound(whoosh)','shortform_audit'],'evidence':'H: practice only; no platform or academic structure data found.'},
 'before_after':{'beats':[('problem',0,3,'the before state, the problem named'),('turn',3,4.5,'a transition on the beat (whip/match cut)'),('after',4.5,None,'the after state, then how'),('cta',-3,None,'CTA')],
   'tools':['compose_cinematic','snap_cuts_to_beats','word_captions','shortform_audit'],'evidence':'P: problem/solution with a before/after transition is a documented TikTok format; surprising transitions +53% recall.'},
 'pov':{'beats':[('pov_line',0,2,'"POV: ..." line on the first frame, an unexpected premise'),('scene',2,None,'first-person footage that plays the premise out'),('twist_end',-3,None,'a turn or payoff')],
   'tools':['reframe_footage','word_captions','shortform_audit'],'evidence':'P: brand/consumer POV is documented; the consumer version opens with an unexpected line.'},
 'product_demo':{'beats':[('product_hook',0,3,'the product and its key benefit within 3 s'),('use',3,None,'use in hand, benefits as short text, an offer'),('cta',-3,None,'text CTA >= 1.5 s, brand')],
   'tools':['ad_plan','ad_audit','word_captions','shortform_audit(goal=ad)'],'evidence':'P: product/key message within 3 s; text CTA +152%; 21-34 s converted best (ads, correlational).'},
 'sports_velocity':{'beats':[('hook',0,2,'the best play first'),('build',2,8,'velocity runs: fast between beats, slow on the action peak; a riser'),('drop',8,10,'the hero play on the drop: one stacked accent'),('runs',10,-3,'2-bar velocity runs, one slow peak every 2-4 bars'),('outro',-3,None,'freeze frame on the hero, a name, a hit and a tail')],
   'tools':['rank_clips','reframe_footage','retime_footage(peaks)','snap_cuts_to_beats','accent_sync(style=velocity)','patch freeze_frame','shortform_audit'],
   'evidence':'Practice (velocity tutorials): ramps 100->20% around peaks, 1-2 frame white flash, shake decaying over 8-12 frames on impacts only. Study: cutting on motion hides the cut; more audiovisual accent alignment is preferred.'},
 'nature_doc':{'beats':[('exposition',0,8,'the place and the animal'),('tension',8,20,'behaviour builds'),('peak',20,30,'the strike or catch, ramped slow'),('resolution',30,None,'calm, a closing hold')],
   'tools':['rank_clips','retime_footage(peaks) on the strike only','compose_edit lower_third (species)','accent_sync(style=nature) places none'],
   'evidence':'Blue Planet II editor (RTS): exposition-tension-conflict-twist-resolution, ~4.4 s per shot; no flash or glitch; ambience leads, dissolves only for time passing.'},
 'food_short':{'beats':[('beauty',0,2,'the finished dish first'),('steps',2,-6,'overhead steps cut on the contact frame; repetitive steps 2-4x'),('payoff',-6,-2,'the pour or pull ramped slow with a small punch on the beat'),('end',-2,None,'end card')],
   'tools':['rank_clips','retime_footage(peaks)','accent_sync(style=food)','compose_edit split_screen (before/after)','shortform_audit'],
   'evidence':'Practice: cut on contact (knife on the board), 45-60 s recipe videos; no glitch/shake/flash; step text >= 1.5 s.'},
 'city_montage':{'beats':[('title',0,3,'title behind or over the skyline, a low hit'),('places',3,-4,'one location per bar or phrase; whips follow the motion, match cuts on shape'),('climax',-8,-4,'the most kinetic shot on the strongest musical moment'),('end',-4,None,'a calm wide shot')],
   'tools':['rank_clips(match_cuts)','snap_cuts_to_beats','accent_sync(style=travel)','compose_cinematic film_finish','shortform_audit'],
   'evidence':'Practice (Brandon Li, Musicbed): one kinetic climax, orient the viewer; whoosh peaking on the cut; light leak at most once per phrase.'},
}


# Short-form caption pages: words that must stay together (a Vietnamese word is several syllables; a name is a run of
# capitalised ones) and words a page must not end on (function words lead into what follows).
KEEP_TOGETHER={('chợ','sáng'),('trái','cây'),('xe','máy'),('đá','vôi'),('hòn','đảo'),('tận','mắt'),('mặt','trăng'),('tên','lửa'),('nhiên','liệu'),('phi','hành'),('hành','gia'),
 ('thành','phố'),('du','lịch'),('việt','nam'),('ăn','uống'),('bình','luận'),('theo','dõi')}
PAGE_END_NO=set('of the a an to in on at for and or but is are was were be that with as by from into than our your their its this these my'.split())|set(
 'là và nhưng vì nên thì khi để hoặc mà nếu rồi trong của với cho ở hãy các những một mỗi từ về đến tới rất cả'.split())


def short_pages(timed,max_words=3,max_frames=60):
 """Split timed words into 1-3 word caption pages of <= 2 s, never between the syllables of a known word or a
 capitalised name, never ending a page on a function word (a page may then run to 5 words / 3 s)."""
 from .audio import PROTECTED_PAIRS,_clean
 def glue(a,b):
  if re.search(r'[.!?,;:]$',a['text']):return False
  pair=(_clean(a['text']),_clean(b['text']))
  if pair in KEEP_TOGETHER or pair in PROTECTED_PAIRS:return True
  if a['text'][:1].isupper() and b['text'][:1].isupper() and not re.fullmatch(r'\d+',_clean(b['text'])):return True
  return pair[0] in PAGE_END_NO
 chunks,chunk=[],[]
 for tw in timed:
  if chunk:
   span=tw['end_frame']-chunk[0]['start_frame']
   soft=len(chunk)>=max_words or span>max_frames or bool(re.search(r'[.!?]$',chunk[-1]['text']))
   if len(chunk)>=5 or span>90 or (soft and not glue(chunk[-1],tw)):chunks.append(chunk);chunk=[]
  chunk.append(tw)
 if chunk:chunks.append(chunk)
 return chunks


class RecipeRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 recipe: Literal['hook_card','lower_third','chapter_card','evidence_card','pull_quote','keyword_callout','picture_in_picture','split_screen','comparison_labels','focus_spotlight','tracked_callout','word_captions','chapter_progress','j_cut_audio','l_cut_audio','sound_bridge','audio_finish']
 platform: Literal['tiktok','reels','youtube_shorts','youtube_long']='youtube_long'
 id: str=Field(default='professional',pattern=r'^[a-zA-Z0-9_-]{1,70}$')
 start_frame: int=Field(default=0,ge=0)
 end_frame: int=Field(gt=0)
 text: str=Field(default='',max_length=500)
 secondary_text: str=Field(default='',max_length=500)
 source_text: str=Field(default='',max_length=500)
 asset_id: str | None=None
 source_start: float=Field(default=0,ge=0,allow_inf_nan=False)
 target: list[float] | None=None
 label_point: list[float] | None=None
 label_width: float | None=Field(default=None,ge=.05,le=.8)
 target_keyframes: list[dict]=Field(default_factory=list,max_length=100)
 safe_region: list[float] | None=None
 font_size: int | None=Field(default=None,ge=20,le=140)
 color: str=Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
 accent: str=Field(default='#e4b866',pattern=r'^#[0-9a-fA-F]{6}$')
 background: str=Field(default='#101820',pattern=r'^#[0-9a-fA-F]{6}$')
 mode: Literal['box','color','underline']='box'
 cut_frame: int | None=Field(default=None,ge=0)
 lead_frames: int=Field(default=12,ge=1,le=150)  # measured: conversational overlaps 15-20, reaction holds 45-123, scene pre-laps 43-102
 # Short-form caption styles: karaoke (words light up), build (words appear on their timestamps), keyword (only the
 # emphasis words, 1-2 per page). emphasis/negative words take the accent / a saturated red (#e80004 measured).
 caption_style: Literal['karaoke','build','keyword']='karaoke'
 emphasis: list[str]=Field(default_factory=list,max_length=200)
 negative: list[str]=Field(default_factory=list,max_length=200)
 uppercase: bool=False
 # Word motion of short-form captions (rendered identically by both engines), outline in em, caption block centre y.
 word_animation: Literal['none','pop','bounce','rise']='none'
 outline: float=Field(default=0,ge=0,le=.2)
 outline_color: str=Field(default='#000000',pattern=r'^#[0-9a-fA-F]{6}$')
 caption_y: float | None=Field(default=None,ge=.05,le=.95)
 # Bilingual captions: caller-written translations [{start,end,text}] (timeline seconds), one line under the spoken
 # words for viewers of another language. Written by the calling AI; nothing is machine-translated here.
 translations: list[dict] | None=Field(default=None,max_length=2000)
 # split_screen: 2-4 assets with their source start seconds
 asset_ids: list[str] | None=Field(default=None,max_length=4)
 source_starts: list[float] | None=Field(default=None,max_length=4)
 layout: Literal['auto','rows','columns','grid']='auto'
 # lower_third: a subject to keep clear of ("gorilla"): detected on the shot's footage, the card takes the clearer side
 avoid: str | None=Field(default=None,max_length=60)
 volume: float=Field(default=.35,ge=0,le=2)
 audio_mix: AudioMix=Field(default_factory=AudioMix)
 word_timings: list[dict] | None=Field(default=None,max_length=20000)
 timing_source: str=Field(default='caller supplied estimates',max_length=200)

 @model_validator(mode='after')
 def coordinates(self):
  for point in (self.target,self.label_point):
   if point is not None and (len(point)!=2 or any(not math.isfinite(v) or not 0<=v<=1 for v in point)):raise ValueError('Points normalized [x,y]')
  if self.safe_region is not None:
   r=self.safe_region
   if len(r)!=4 or not all(math.isfinite(v) for v in r) or not 0<=r[0]<r[2]<=1 or not 0<=r[1]<r[3]<=1:raise ValueError('safe_region normalized [left,top,right,bottom]')
  if self.end_frame<=self.start_frame:raise ValueError('end_frame follows start_frame')
  return self


def toolkit(platform='youtube_long',query=''):
 if platform not in PROFILES:raise ValueError('platform tiktok|reels|youtube_shorts|youtube_long')
 words=query.lower().replace('_',' ').split()
 entries=[{'id':name,'intent':intent,'implementation':detail,'engines':['remotion','hyperframes']} for name,(intent,detail) in RECIPE_INFO.items() if not words or any(w in (name+' '+intent+' '+detail).lower().replace('_',' ') for w in words)]
 short={}
 if platform in SHORT_FORM:
  key={'tiktok':'tiktok','reels':'reels','youtube_shorts':'shorts'}[platform]
  tpl={k:{'beats':[{'beat':b,'from_s':a,'to_s':e,'purpose':u} for b,a,e,u in v['beats']],'tools':v['tools'],'evidence':v['evidence']} for k,v in SHORT_TEMPLATES.items()
       if not words or any(w in (k+' '+str(v)).lower().replace('_',' ') for w in words)}
  short={'templates':tpl,'ui_zones':platforms.zones(key),'safe_area':{'organic':platforms.safe_area(key),'ads_all_platforms':platforms.safe_area('all','ads')},
         'delivery':platforms.ENCODE,'audit':'shortform_audit (rendered MP4)','evidence':{k:'%s: %s'%v for k,v in platforms.EVIDENCE.items()},
         'beat_times':'negative from_s counts from the end; to_s None = until the next beat'}
 return {'platform':platform,'guide':PROFILES[platform],'recipes':entries,'total':len(entries),**({'short_form':short} if short else {}),
         'skills':['story/promise/payoff','visual evidence and references','motivated cuts and continuity','composition/typography/mobile legibility','timed captions','color/light consistency','dialogue/music/SFX hierarchy','chapter structure','platform adaptation','observe/refine real pixels and audio'],
         'workflow':'Define intent → inspect footage/audio → select recipe/effect by purpose → compose_edit with current revision → snapshot/render → inspect and refine. Creative interpretation is supplied by the calling AI.',
         'research_guide':str(store.ROOT/'docs/PROFESSIONAL_VIDEO_PLAYBOOK.md'),
         'limitations':'Recipes do not infer content, predict virality, guarantee identity or automatically crop subjects. Safe-region defaults are adjustable heuristics; check actual platform UI. Existing custom source must implement new caption/callout widgets or migrate explicitly.'}


def _clear_side(p,t,q,left,right,cw,y0,y1):
 """Left or right for a card spanning [y0,y1]: the side whose box overlaps the detected subject less, over the card's
 frames on the shot under it (source boxes mapped through the shot's fit and focus to canvas shares)."""
 from .semantic import detect
 f=(q.start_frame+q.end_frame)//2;sh=next((s for s in t['shots'] if s['start_frame']<=f<s['end_frame']),None)
 a=next((x for x in p['assets'] if sh and x['id']==sh.get('asset_id')),None)
 if not a or a['kind'] not in ('video','image') or not a.get('width'):return left,'avoid: no footage under the card'
 W,H=t['width'],t['height'];sw,shh=a['width'],a['height']
 rate=sh.get('playback_rate',1);t0=sh.get('source_start',0)+(q.start_frame-sh['start_frame'])*rate/30;t1=sh.get('source_start',0)+(q.end_frame-sh['start_frame'])*rate/30
 track=detect([a['path']],[q.avoid],fps=1.0)['clips']
 boxes=[b for tt,b in next(iter(track.values()))[q.avoid.strip().lower()].get('track',[]) if t0-1<=tt<=t1+1]
 if not boxes:return left,f'avoid: no {q.avoid} found under the card; kept left'
 from .semantic import to_canvas
 canvas=[to_canvas(b,sw,shh,W,H,sh.get('fit','cover'),sh.get('focus_x',.5),sh.get('focus_y',.5)) for b in boxes]
 for e in sh.get('effects') or []:  # held punch-ins (focus_zoom cut) scale the picture about their origin, as the engines draw it
  P=e.get('params') or {}
  if e.get('name')=='focus_zoom' and P.get('cut'):
   z,ox,oy=1+float(P.get('amount',.08)),float(P.get('focus_x',.5)),float(P.get('focus_y',.5))
   canvas=[[ox+(c[0]-ox)*z,oy+(c[1]-oy)*z,ox+(c[2]-ox)*z,oy+(c[3]-oy)*z] for c in canvas]
 over=lambda x0,x1:sum(max(0,min(x1,c[2])-max(x0,c[0]))*max(0,min(y1,c[3])-max(y0,c[1])) for c in canvas)
 lo,ro=over(left,left+cw),over(right-cw,right)
 return (left if lo<=ro else right-cw),f'avoid {q.avoid}: overlap left {lo:.4f}, right {ro:.4f} ({len(boxes)} detections)'


def compose(pid,base_revision,request,dry_run=False):
 q=RecipeRequest.model_validate(request);p=agent.read(pid);t=p['timeline']
 if not t or p['revision']!=base_revision:raise ValueError('Read current project revision/locked plan before composing')
 if q.end_frame>t['total_frames']:raise ValueError('Recipe range outside locked timeline')
 guide=PROFILES[q.platform];r=q.safe_region or guide['safe_region'];left,top,right,bottom=r;w=right-left;h=bottom-top
 vertical=t['height']>t['width'];fs=q.font_size or (guide['font_size'] if vertical else 48)
 d=q.end_frame-q.start_frame;enter=min(14,max(1,d-1));ops=[];notes=[]
 def layer(suffix,kind='text',**kw):
  value={'id':q.id+'-'+suffix,'kind':kind,'start_frame':q.start_frame,'end_frame':q.end_frame,
         'x':left,'y':top,'width':w,'height':min(.18,h),'font_size':fs,'color':q.color,'z':800,**kw}
  value=Layer.model_validate(value).model_dump();ops.append({'op':'upsert_layer','layer':value});return value
 def text_required():
  if not q.text.strip():raise ValueError('Recipe needs meaningful text')
 def entrance(name='rise'):
  # in, then out: a card that vanishes on its last frame reads as a glitch; 8 frames of fade on cards held >= 36 frames
  return ([{'name':'fade_in','end_frame':enter},{'name':name,'end_frame':enter,'params':{'amount':22 if name=='rise' else 70}}] if d>1 else [])+(
   [{'name':'fade_out','start_frame':d-9,'end_frame':d-1}] if d>=36 else [])
 if q.recipe in ('hook_card','chapter_card','keyword_callout','pull_quote'):
  text_required();heading=q.text
  if q.recipe=='pull_quote':heading='“'+heading+'”'
  heading_fs=q.font_size or (66 if vertical else 70)
  heading_lines=max(1,math.ceil(len(heading)*heading_fs*.55/(w*t['width'])))
  heading_height=min(.3,heading_lines*heading_fs*1.4/t['height']+.015)
  layer('heading',text=heading,y=top+.04,height=heading_height,font_size=heading_fs,background=q.background,
        effects=entrance()+([{'name':'marker_reveal','end_frame':min(24,max(1,d-1)),'params':{'amount':.12,'color':q.accent}}] if d>1 else []))
  detail=q.secondary_text or q.source_text
  if detail:layer('detail',text=detail,y=top+.24,height=.1,font_size=max(24,fs-10),color=q.accent,effects=entrance())
  if q.recipe=='chapter_card':layer('section',text='CHƯƠNG / '+(q.secondary_text or 'NỘI DUNG'),y=top,height=.035,font_size=max(22,fs-20),color=q.accent)
 elif q.recipe=='lower_third':
  text_required();y=bottom-.23
  name_height=fs*1.5/t['height']+.012
  nw=min(w,max(.2,len(q.text)*fs*.6/t['width']+.04));rw=min(w,max(.2,len(q.secondary_text)*max(22,fs-14)*.6/t['width']+.04)) if q.secondary_text else 0
  cw=max(nw,rw);cx=left
  if q.avoid:
   cx,why=_clear_side(p,t,q,left,right,cw,y,y+name_height+(.06 if q.secondary_text else 0))
   notes.append(why)
  layer('name',text=q.text,x=cx if cx==left else right-nw,y=y,width=nw,height=name_height,background=q.background,effects=entrance('slide_spring'))
  if q.secondary_text:layer('role',text=q.secondary_text,x=cx if cx==left else right-rw,y=y+name_height+.01,width=rw,height=max(22,fs-14)*1.5/t['height']+.012,font_size=max(22,fs-14),color=q.accent,background=q.background,effects=entrance())
 elif q.recipe in ('evidence_card','picture_in_picture'):
  asset=next((a for a in p['assets'] if a['id']==q.asset_id),None)
  if not asset or asset['kind'] not in ('image','video'):raise ValueError('Image/video asset required')
  if q.recipe=='evidence_card' and not q.source_text.strip():raise ValueError('Evidence card requires visible source_text; caller verifies its claim')
  iw=w if q.recipe=='evidence_card' else w*.48;ih=min(h*.5,iw*t['width']/t['height']/(asset['width']/asset['height']))
  layer('media',kind=asset['kind'],asset_id=q.asset_id,source_start=q.source_start,width=iw,height=ih,y=top+.08,
        effects=[{'name':'rounded','end_frame':max(1,d-1),'params':{'amount':16}},{'name':'border','end_frame':max(1,d-1),'params':{'amount':2,'color':q.accent}},*entrance()])
  label=q.source_text if q.recipe=='evidence_card' else q.text
  if label:layer('source',text=label,y=top+.09+ih,height=.09,font_size=max(22,fs-12),background=q.background)
 elif q.recipe=='split_screen':
  ids=q.asset_ids or []
  if not 2<=len(ids)<=4:raise ValueError('split_screen needs 2-4 asset_ids')
  starts=list(q.source_starts or [0.0]*len(ids))
  if len(starts)!=len(ids):raise ValueError('source_starts: one per asset')
  assets={a['id']:a for a in p['assets']}
  if any(assets.get(i,{}).get('kind') not in ('video','image') for i in ids):raise ValueError('split_screen panels are video/image assets')
  lay=q.layout if q.layout!='auto' else ('grid' if len(ids)==4 else 'rows' if vertical else 'columns')
  g=.012
  if lay=='grid':cells=[(c*.5,r*.5,.5,.5) for r in range(2) for c in range(2)][:len(ids)]
  elif lay=='rows':cells=[(0,i/len(ids),1,1/len(ids)) for i in range(len(ids))]
  else:cells=[(i/len(ids),0,1/len(ids),1) for i in range(len(ids))]
  layer('backdrop',kind='shape',x=0,y=0,width=1,height=1,z=780,color=q.background,data={'shape':'rectangle','corner_radius':0})
  for i,(aid,(cx,cy,cw,ch)) in enumerate(zip(ids,cells)):
   delay=min(d-2,i*4) if d>2 else 0
   slide=[{'name':'slide_left' if i%2==0 else 'slide_right','start_frame':delay,'end_frame':min(d-1,delay+10),'params':{'amount':140}}] if d>12 else []
   layer(f'panel{i+1}',kind=assets[aid]['kind'],asset_id=aid,source_start=starts[i],fit='cover',x=cx+g/2,y=cy+g/2,width=cw-g,height=ch-g,z=790+i,
         effects=[{'name':'rounded','end_frame':max(1,d-1),'params':{'amount':14}},*slide])
  notes.append(f'Split screen {lay} with {len(ids)} panels; each panel is a video/image layer (fit cover) over a backdrop.')
 elif q.recipe=='comparison_labels':
  text_required()
  if not q.secondary_text:raise ValueError('Two comparison labels required')
  for i,text in enumerate((q.text,q.secondary_text)):layer(str(i),text=text,x=left+i*w*.52,width=w*.48,height=.1,background=q.background,effects=entrance())
 elif q.recipe=='focus_spotlight':
  if q.safe_region is None:raise ValueError('Provide inspected target rectangle in safe_region for spotlight')
  for i,(x,y,width,height) in enumerate(((0,0,1,top),(0,bottom,1,1-bottom),(0,top,left,h),(right,top,1-right,h))):
   if width>0 and height>0:layer('dim'+str(i),kind='shape',x=x,y=y,width=width,height=height,color=q.background,opacity=.6,data={'shape':'rectangle','corner_radius':0},z=700)
  notes.append('Only outside rectangle is dimmed; not semantic segmentation. safe_region here denotes spotlight rectangle.')
 elif q.recipe=='tracked_callout':
  text_required()
  if q.target is None:raise ValueError('Explicit inspected canvas target required')
  lw=q.label_width or min(.42,w*.55);lp=list(q.label_point or [left,top+.08])
  if not left<=lp[0]<=right-lw:  # the label plate stays inside the safe area (a plate at .66 + .42 had run off the frame)
   notes.append(f'label_point x {lp[0]:.3f} moved to keep its {lw:.2f}-wide plate inside the safe area');lp[0]=round(min(max(lp[0],left),right-lw),4)
  layer('leader',kind='callout',text=q.text,x=0,y=0,width=1,height=1,background='transparent',font_size=q.font_size or (32 if vertical else 36),color=q.accent,
        data={'target':q.target,'label_point':lp,'target_keyframes':q.target_keyframes,'label_width':lw,'stroke_width':3},
        effects=([{'name':'progress','end_frame':enter}] if d>1 else [])+([{'name':'fade_out','start_frame':d-9,'end_frame':d-1}] if d>=36 else []))
  notes.append('Target/target_keyframes are normalized canvas coordinates, local frame times; map fit/crop/source speed first. A measured tracking point is not semantic identity.')
 elif q.recipe=='chapter_progress':
  layer('progress',kind='counter',y=top,height=.045,font_size=24,color=q.accent,data={'from':0,'to':100,'suffix':'% chương','decimals':0},effects=[{'name':'progress','end_frame':max(1,d-1)}] if d>1 else [])
  notes.append('Percentage denotes elapsed section time, not a factual data series.')
 elif q.recipe=='word_captions':
  from .audio import restore_display_text
  record=store.read_json(store.folder(pid)/'plan/words.json');words=q.word_timings if q.word_timings is not None else record.get('words',[])
  for word in words:
   if not isinstance(word,dict) or not isinstance(word.get('text'),str) or not all(isinstance(word.get(k),(int,float)) and math.isfinite(word[k]) for k in ('start','end')) or not 0<=word['start']<word['end']<=t['total_frames']/30+.05:raise ValueError('Word timings need text/start/end seconds inside narration')
  if any(b['start']<a['start'] for a,b in zip(words,words[1:])):raise ValueError('Word timings must be sorted')
  if not words:raise ValueError('Word timestamps required; transcribe source and import corrected timing first. Do not estimate karaoke from text length.')
  cues=[c for c in t['cues'] if c['end']*30>q.start_frame and c['start']*30<q.end_frame]
  if not cues:raise ValueError('Timed cues required in this window')
  if len(cues)>2000:raise ValueError('At most2000 caption pages per track')
  pages=[]
  for index,cue in enumerate(cues):
   start=max(q.start_frame,math.ceil(cue['start']*30));end=min(q.end_frame,math.ceil(cue['end']*30))
   if end<=start:continue
   spoken=[w for w in words if w['end']>cue['start']+.001 and w['start']<cue['end']-.001]
   mapped=restore_display_text(spoken,cue['text'])
   if mapped is None:raise ValueError('Display cue differs from word timing transcript; correct mapping before word_captions')
   timed=[]
   for word in mapped:
    a=max(start-q.start_frame,math.ceil(word['start']*30)-q.start_frame);b=min(end-q.start_frame,math.ceil(word['end']*30)-q.start_frame)
    if b>a:timed.append({'text':word['text'],'start_frame':a,'end_frame':b})
   if not timed:continue
   if q.platform in SHORT_FORM:
    # Short-form captions: 1-3 words and at most 2 s per page (measured in short-form editing practice), so the eye
    # reads each page at a glance; long cues become several pages.
    chunks=short_pages(timed)
    for k,c in enumerate(chunks):
     ps=c[0]['start_frame'] if k else start-q.start_frame
     pe=chunks[k+1][0]['start_frame'] if k+1<len(chunks) else end-q.start_frame
     ws=[{**w,'end_frame':min(w['end_frame'],pe)} for w in c if w['start_frame']<pe]
     ws=[w for w in ws if w['end_frame']>w['start_frame']]
     if pe>ps and ws:pages.append({'start_frame':ps,'end_frame':pe,'words':ws})
   else:pages.append({'start_frame':start-q.start_frame,'end_frame':end-q.start_frame,'words':timed})
  norm=lambda s:re.sub(r'[^\w]','',s.casefold())
  emph,neg={norm(x) for x in q.emphasis},{norm(x) for x in q.negative}
  styled=[]
  for pg in pages:
   ws=[]
   for wd in pg['words']:
    key=norm(wd['text']);wd={**wd,'text':wd['text'].upper() if q.uppercase else wd['text']}
    if key in neg:wd['color']='#e80004'
    elif key in emph:wd['color']=q.accent
    if q.caption_style!='keyword' or key in emph or key in neg:ws.append(wd)
   if q.caption_style=='keyword':
    for k in range(0,len(ws),2):
     chunk=ws[k:k+2];styled.append({'start_frame':chunk[0]['start_frame'],'end_frame':max(chunk[-1]['end_frame'],chunk[0]['start_frame']+12),'words':chunk})
   elif ws:styled.append({**pg,'words':ws})
  if q.caption_style=='keyword':
   styled.sort(key=lambda p:p['start_frame'])
   for a,b in zip(styled,styled[1:]):a['end_frame']=min(a['end_frame'],b['start_frame'])
   styled=[p for p in styled if p['end_frame']>p['start_frame']]
   for pg2 in styled:pg2['words']=[{**x,'end_frame':min(x['end_frame'],pg2['end_frame'])} for x in pg2['words'] if x['start_frame']<pg2['end_frame']]
  pages=styled
  if pages:layer('caption',kind='caption',y=(q.caption_y-.075) if q.caption_y is not None else min(guide['caption_y'],bottom-.15),height=.15,
         font_size=q.font_size or (54 if vertical else 48),background='transparent' if q.outline>0 and q.mode!='box' and 'background' not in q.model_fields_set else q.background,
         data={'pages':pages,'active_color':q.background if q.mode=='box' else q.accent,'active_background':q.accent,'mode':q.mode,
               'future_opacity':0 if q.caption_style=='build' or q.word_animation=='rise' else .8,'animation':q.word_animation,
               'outline':q.outline,'outline_color':q.outline_color},z=950)
  if q.translations:
   rows=[]
   for r_ in sorted(q.translations,key=lambda r_:r_.get('start',0)):
    if not isinstance(r_,dict) or not isinstance(r_.get('text'),str) or not 1<=len(r_['text'].strip())<=120 or not all(isinstance(r_.get(k),(int,float)) for k in ('start','end')) or r_['end']<=r_['start']:raise ValueError('translations are [{start,end,text<=120 chars}] in seconds')
    a_=max(0,math.ceil(r_['start']*30)-q.start_frame);b_=min(q.end_frame-q.start_frame,math.ceil(r_['end']*30)-q.start_frame)
    if rows:a_=max(a_,rows[-1]['end_frame'])
    if b_>a_:rows.append({'start_frame':a_,'end_frame':b_,'words':[{'text':r_['text'].strip(),'start_frame':a_,'end_frame':b_}]})
   if rows:
    cy=(q.caption_y if q.caption_y is not None else min(guide['caption_y'],bottom-.15)+.075)
    layer('caption-tr',kind='caption',y=cy+.055,height=.1,font_size=max(26,round((q.font_size or (54 if vertical else 48))*.55)),background='transparent',color='#ffffff',
          data={'pages':rows,'active_color':'#ffffff','active_background':'#ffffff','mode':'color','future_opacity':1,'animation':'none','outline':q.outline or .06,'outline_color':q.outline_color},z=949)
    notes.append('Translation line: '+str(len(rows))+' pages under the spoken words (caller-written).')
  notes.append('Caption timing method: '+(q.timing_source if q.word_timings is not None else record.get('method','unknown'))+'. TTS/ASR word boundaries are quantized to30fps; no forced alignment or certainty claim. New timed layers suppress default captions only while active.')
 elif q.recipe in ('j_cut_audio','l_cut_audio','sound_bridge'):
  if not q.asset_id:raise ValueError('Selected audio/video asset required')
  from .media import probe
  source_asset=next((a for a in p['assets'] if a['id']==q.asset_id),None)
  if not source_asset or not any(s['codec_type']=='audio' for s in probe(source_asset['path'])['streams']):raise ValueError('Selected source needs an actual audio track')
  start=q.start_frame;source=q.source_start
  if q.recipe=='j_cut_audio':
   if q.cut_frame is None or q.start_frame!=q.cut_frame:raise ValueError('J-cut start_frame must name visual cut; supply cut_frame and pre-roll lead_frames')
   start=q.cut_frame-q.lead_frames;source=q.source_start-q.lead_frames/30
   if start<0 or source<0:raise ValueError('J-cut needs timeline and source pre-roll handles; do not fabricate audio')
  if q.recipe=='l_cut_audio' and (q.cut_frame is None or not q.start_frame<q.cut_frame<q.end_frame):raise ValueError('L-cut range must span visual cut_frame')
  audio=AudioClip(id=q.id+'-audio',asset_id=q.asset_id,start_frame=start,end_frame=q.end_frame,source_start=source,volume=q.volume,fade_in=.05,fade_out=.15,duck_under_voice=True).model_dump()
  ops.append({'op':'upsert_audio','audio':audio});notes.append('Separate selected audio bed; existing locked narration remains. Do not add dialogue already present in narration or it will double. Inspect actual source audio track/handles.')
 elif q.recipe=='audio_finish':
  mix=q.audio_mix.model_dump()
  if q.platform in SHORT_FORM and 'audio_mix' not in q.model_fields_set:  # phones play loud: the short-form delivery level
   mix.update(target_lufs=platforms.ENCODE['loudness_lufs'],true_peak_db=platforms.ENCODE['master_true_peak_dbtp'])
   notes.append('Short-form master: -14 LUFS integrated, -2 dBTP (headroom so the AAC encode stays under -1 dBTP; no published TikTok/Reels target, -14 is the measured norm).')
  ops.append({'op':'set_audio_mix','audio_mix':mix})
 if not ops:raise ValueError('Recipe produced no applicable edits')
 # Reusing an id replaces the entire recipe namespace, including optional
 # detail/role layers removed in this version. No stale caption/card fragments.
 own=re.compile(re.escape(q.id)+r'-(backdrop|caption|caption-tr|detail|dim\d|heading|leader|media|name|progress|role|section|source|panel\d|\d|audio)$')
 deletes=[{'op':'delete_layer','id':l['id']} for l in t.get('layers',[]) if own.match(l['id'])]
 deletes += [{'op':'delete_audio','id':a['id']} for a in t.get('audio_clips',[]) if own.match(a['id'])]
 ops=deletes+ops
 if len(ops)>100:raise ValueError('Batch too large; narrow recipe window')
 # Validate source handles and the complete result even for dry-run.
 if dry_run:
  import copy
  from .models import Timeline
  from .planner import validate_sources
  candidate=copy.deepcopy(t)
  for op in ops:
   if op['op']=='set_audio_mix':candidate['audio_mix']=op['audio_mix']
   elif op['op'] in ('delete_layer','delete_audio'):
    key='layers' if op['op']=='delete_layer' else 'audio_clips';candidate[key]=[x for x in candidate.get(key,[]) if x['id']!=op['id']]
   else:
    key='layers' if op['op']=='upsert_layer' else 'audio_clips';item=op.get('layer',op.get('audio'))
    candidate[key]=[x for x in candidate.get(key,[]) if x['id']!=item['id']]+[item]
  validate_sources(pid,Timeline.model_validate(candidate),p['assets']);result={'revision':base_revision}
 else:result=agent.patch(pid,base_revision,ops)
 return {'recipe':q.recipe,'platform':q.platform,'revision':result['revision'],'applied':not dry_run,'operations':ops,'notes':notes,
         'inspect_frames':sorted({q.start_frame,min(q.end_frame-1,q.start_frame+enter),q.end_frame-1}),
         'safe_region':r,'limitations':'Layout and rhythm defaults require visual/audio inspection; no automatic aesthetic score or retention prediction. Custom source must use widgets or be explicitly migrated.'}
