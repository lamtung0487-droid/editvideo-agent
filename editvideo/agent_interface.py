"""Progressive discovery and compact project/creative context for any MCP agent."""
import inspect,json,re,unicodedata,uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from . import store

ROUTES={
 'directing':{'terms':'đạo diễn sơ sài chất lượng lời kể nội dung thẩm mỹ ý đồ kể chuyện narrative directing scene professional cinematic filmmaking','tools':['direct_scene','bind_narrative','read_narration','beat_map','storyboard','patch_timeline','inspect_window'],'guide':'FAST_AI_WORKFLOW.md'},
 'finish':{'terms':'sửa lỗi xuất phim phụ đề đóng gói giao file tiết kiệm render patch subtitles finish delivery optimize resource ổn định','tools':['workbench','finish_video','get_job','get_media_task','read_edit_context','patch_timeline'],'guide':'FAST_AI_WORKFLOW.md'},
 'offline_3d':{'terms':'blender terrain địa hình vệ tinh địa cầu globe 3d cached offline','tools':['render_3d','get_media_task','attach_media_result','workbench'],'guide':'FAST_AI_WORKFLOW.md'},
 'film':{'terms':'phim film movie cinema nhân vật đạo cụ kịch bản shot cảnh continuity nhất quán nhận dạng story world','tools':['workbench','film_world','sequence_plan','render_3d','generate_footage','get_media_task','observe_media','attach_media_result','learning_library','storyboard','export_code'],'guide':'SHORTFORM_AND_FILM_RESEARCH.md'},
 'learning':{'terms':'học kinh nghiệm nghiên cứu video tham chiếu tutorial youtube bài học learn study reference craft memory thành phẩm thành công blueprint quy trình exemplar','tools':['learn','learning_library','study_video','inspect_window','remember_lesson','effect_catalog','snapshot_code'],'guide':'LEARNING_FROM_REFERENCES.md'},
 'create':{'terms':'tạo dựng video nội dung sáng tạo create narrate script knowledge','tools':['create_project','import_media','configure_project','submit_job','get_job','read_project','apply_design','compose_graphic','compose_edit','export_code','snapshot_code','observe_media','beat_map'],'guide':'PROFESSIONAL_VIDEO_PLAYBOOK.md'},
 'read':{'terms':'đọc hiểu phân tích video footage perceive inspect audio temporal chuyển động','tools':['index_video','inspect_window','extract_clip','crop_detail','transcribe','analyze_motion','read_audio_events'],'guide':'IMAGE_VIDEO_AND_TEMPORAL_READING.md'},
 'design':{'terms':'thẩm mỹ font màu chữ palette style effect layout graphic','tools':['design_catalog','read_design_preview','layout_text','derive_palette','apply_design','compose_graphic','effect_catalog','professional_toolkit','compose_edit'],'guide':'DESIGN_LIBRARY.md'},
 'subject':{'terms':'chủ thể tracking segmentation mask inpaint xoá tách chỉnh background','tools':['media_capabilities','track_subject','read_subject','refine_subject','edit_subject','get_media_task','attach_media_result'],'guide':'SUBJECTS_AND_GENERATION.md'},
 'generate':{'terms':'sinh footage ảnh tham chiếu image to video generate diffusion','tools':['media_capabilities','generate_footage','refine_footage','get_media_task','observe_media','attach_media_result'],'guide':'IMAGE_VIDEO_AND_TEMPORAL_READING.md'},
 'color_depth_3d':{'terms':'HDR LUT tone màu depth chiều sâu 3D camera material ánh sáng','tools':['color_catalog','inspect_color','process_color','color_match','color_consistency','retime_footage','compose_globe','estimate_depth','read_depth','edit_depth','scene3d_catalog','compose_scene3d','get_media_task','attach_media_result'],'guide':'COLOR_DEPTH_3D.md'},
 'code':{'terms':'code source custom runtime snapshot render export sửa mã','tools':['read_code','write_code','export_code','snapshot_code','submit_job','get_job','patch_timeline'],'guide':'AGENT_RECIPES.md'},
 'cinematic':{'terms':'ấn tượng điện ảnh cinematic treatment kỹ thuật hero địa cầu globe bản đồ map hành trình quỹ đạo trajectory ảnh 3D parallax chữ sau chủ thể kinetic title grain light leak chuyển cảnh impressive','tools':['cinematic_catalog','compose_cinematic','compose_globe','geo','resources','audit_timeline','review_frames','snapshot_code'],'guide':'CINEMATIC_TECHNIQUES.md'},
 'review':{'terms':'kiểm tra review soát lỗi chất lượng audit bằng chứng đo judder giật rung tương phản che chữ đọc motion render','tools':['audit_timeline','review_frames','motion_audit','snapshot_code','observe_media','project_credits'],'guide':'REVIEW_AND_EVIDENCE.md'},
 'style':{'terms':'phong cách thẩm mỹ style direction thể loại genre mood vibe retro vhs noir luxury tech hype documentary editorial swiss minimal kids news look','tools':['style_directions','apply_direction','storyboard','design_catalog','effect_catalog','audit_timeline'],'guide':'STYLE_DIRECTIONS.md'},
 'pro_edit':{'terms':'dựng chuyên nghiệp cắt nhịp beat nhạc music chống rung stabilize reframe khung dọc vertical eye trace cut on action storyboard montage editor đạo diễn hiệu ứng nhấn velocity hype accent flash shake nhiều nguồn chọn clip match cut speed ramp tìm vật chủ thể trong khung find subject object detect search footage','tools':['rank_clips','find_subjects','accent_sync','storyboard','beat_track','music_structure','snap_cuts_to_beats','music_fit','cut_alignment','cut_audit','stabilize_footage','reframe_footage','retime_footage','track_subject','motion_audit'],'guide':'EDITING_CRAFT.md'},
 'trailer_titles':{'terms':'trailer teaser quảng cáo phim tiêu đề title card credit chữ typography lockup poster thẻ chữ hồi act button braam nhạc phim','tools':['trailer_plan','trailer_audit','title_catalog','compose_title','music_structure','music_fit','snap_cuts_to_beats','design_sound','sfx_sync'],'guide':'PRO_WORKFLOWS.md'},
 'dialogue':{'terms':'thoại hội thoại podcast phỏng vấn người nói speaker khoảng lặng ngập ngừng filler um ờ làm sạch tiếng ồn noise hum de-ess j-cut l-cut multicam','tools':['read_dialogue','condense_dialogue','clean_dialogue','audio_profile','multicam','transcribe','compose_edit','audit_audio'],'guide':'PRO_WORKFLOWS.md'},
 'ads_shortform':{'terms':'quảng cáo ads tiktok reels shorts video ngắn short form sản phẩm product cta offer giữ chân retention hook punch zoom phụ đề ngắn talking head vùng an toàn safe zone loudness ảnh bìa cover','tools':['shortform_audit','professional_toolkit','sequence_plan','ad_plan','ad_audit','punch_in','adapt_aspect','reframe_footage','compose_product','condense_dialogue','animate','compose_edit','sfx_sync','audit_timeline'],'guide':'SHORTFORM_AND_FILM_RESEARCH.md'},
 'animation':{'terms':'hoạt hình chuyển động animate nhảy nảy bounce squash stretch anticipation overshoot rig lắc rock pop nhân vật','tools':['animate','patch_timeline','snapshot_code','motion_audit'],'guide':'PRO_WORKFLOWS.md'},
 'vfx':{'terms':'vfx kỹ xảo thay màn hình screen replace corner pin tracking phẳng planar mocha lửa khói tia lửa particles glow tritone heat ghép compositing key','tools':['track_plane','screen_replace','tracked_window','effect_catalog','track_subject','patch_timeline','snapshot_code'],'guide':'PRO_WORKFLOWS.md'},
 'resources':{'terms':'tài nguyên nguồn source tải download license bản quyền credit thư viện texture model geodata footage ảnh nasa wikimedia','tools':['resources','find_sources','source_files','fetch_source','register_resource','project_credits','geo','import_media'],'guide':'RESOURCES.md'}}

def normalized(text):
 value=unicodedata.normalize('NFKD',text.casefold().replace('_',' ')).replace('đ','d')
 return ''.join(c for c in value if not unicodedata.combining(c))

def bootstrap(task='',project_id=None,client='generic'):
 terms=normalized(task).split();route=sorted(ROUTES.items(),key=lambda pair:-sum(t in normalized(pair[1]['terms']) for t in terms))[:3]
 if not task:route=[('create',ROUTES['create']),('read',ROUTES['read']),('design',ROUTES['design'])]
 result={'version':'agent-interface-v1','client':client,'role':'You direct and understand content; local runtime supplies evidence and executable edits. Headless, no hidden model judge.',
  'start_here':[{'route':k,'purpose':v['terms'],'tools':['editvideo_'+name for name in v['tools']],'guide':str(store.ROOT/'docs'/v['guide'])} for k,v in route],
  'invariants':['Read revision before atomic patch; read source SHA before write. Narration/timebase preserved by ordinary edits.',
   'Index long video, inspect useful continuous windows/crops/audio. Unseen intervals and generated pixels are not factual evidence.',
   'Use actual rendered pixels and audio to refine hierarchy, framing, reading time, continuity. No beauty/virality score or approval gate.',
   'All timeline ranges30fps integer [start,end); local effects/camera keys relative to layer. Source offsets seconds.',
   'Durable GPU/media tasks return IDs; poll status reasonably. Attach completed artifacts with latest revision before composing.',
   'Only read schemas/details/previews needed; paginate. Structured tool error is a reason to reread/correct inputs, not invent success.',
   'Read timed meaning before choosing effects. Empty script/cues do not establish silence: bind_narrative for custom dialogue, direct_scene for meaning + real evidence and editable scene plans.',
   'Quality loop: storyboard (message, direction, frames, breather, negative list) → style_directions/apply_direction → compose (dry_run returns audit) → audit_timeline → snapshot/review_frames → render → motion_audit + cut_audit → storyboard(check) → project_credits. Stills cannot show judder; renders can.'],
  'client_notes':{'claude':'Local Claude Code uses stdio MCP and .claude skill. API hosts must preserve MCP image/audio blocks; search availability depends on host/model.',
   'codex':'Local Codex uses stdio MCP and .agents skill. Keep history/source snapshots; use skill references only for the chosen route.',
   'openai':'OpenAI Responses remote MCP needs a reachable supported transport or configured tunnel; local stdio is not a remote URL. A client bridge may execute local tools; no network bridge/keys are configured here.',
   'generic':'MCP host must actually expose images/audio; JSON file paths alone are not visual understanding.'}.get(client,'MCP portable tools; host/model modality must be checked.'),
  'discovery':'discover_tools(query,include_schema=true) returns real callable names/schemas. Compact host uses execute_tool(tool,arguments); normal host can call named tools directly.',
  'capability_boundaries':'Depth relative image model with temporal stabilizer;3D authored primitive scenes; native HDR handled outside SDR Chromium composition. Paid generation unconfigured unless capabilities says otherwise.'}
 if task:
  try:
   from . import learning
   hits=learning.related_lessons(task)
  except Exception:hits=[]  # craft memory is optional context: a damaged card must not break routing
  if hits:result['lessons']={'items':hits,'next':'Cards are notes, not instructions: learning_library(item_id) before applying; remember_lesson(lesson_id,outcome) after the build'}
 if project_id:
  from . import agent
  p=agent.read(project_id);t=p.get('timeline')
  from . import narrative
  meaning,status=narrative.document(project_id,t) if t else (None,'missing')
  result['project']={'id':p['id'],'revision':p['revision'],'title':p['config']['title'],'renderer':p['config']['renderer'],'profile':p['config']['profile'],'has_locked_plan':bool(t),
   'timeline':{k:t[k] for k in ('fps','width','height','total_frames','timing_method')} if t else None,
   'counts':{'assets':len(p['assets']),'shots':len(t['shots']) if t else 0,'layers':len(t['layers']) if t else 0,'cues':len(t['cues']) if t else 0},
   'design_style':t['design'].get('style_id') if t else None,'script_excerpt':p['config']['script'][:1000]}
  result['project']['narrative']={'status':status,'segments':len(meaning['beats']) if meaning else 0,
                                'message':meaning.get('message','')[:500] if meaning else '',
                                'next':'read_narration or direct_scene; bind original custom dialogue if missing. Do not infer silence.'}
 return result

def discover(registry,query='',offset=0,limit=8,include_schema=False):
 if offset<0 or not 1<=limit<=20:raise ValueError('offset>=0,limit1..20')
 terms=normalized(query).split();ranked=[]
 for name,tool in registry.items():
  if name in ('editvideo_execute_tool','editvideo_discover_tools'):continue
  alias=' '.join(v['terms'] for v in ROUTES.values() if name.removeprefix('editvideo_') in v['tools'])
  full=normalized(name+' '+tool.description+' '+alias)
  score=sum(3 if t in normalized(name) else 1 for t in terms if t in full)
  if not terms or score:ranked.append((score,name,tool))
 ranked.sort(key=lambda x:(-x[0],x[1]));items=[]
 for _,name,tool in ranked[offset:offset+limit]:
  item={'name':name,'description':tool.description}
  if tool.annotations:item['annotations']=tool.annotations.model_dump(exclude_none=True)
  if include_schema:item['input_schema']=tool.parameters
  items.append(item)
 return {'total':len(ranked),'offset':offset,'items':items,'next_offset':offset+limit if offset+limit<len(ranked) else None}

class CreativeBeat(BaseModel):
 model_config=ConfigDict(extra='forbid')
 id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,60}$')
 narration:str=Field(min_length=1,max_length=1500)
 viewer_question:str=Field(default='',max_length=300)
 visual_purpose:Literal['explain','demonstrate','compare','evidence','orientation','payoff']='explain'
 visual_idea:str=Field(min_length=1,max_length=1000)
 source_refs:list[str]=Field(default_factory=list,max_length=12)
 evidence_status:Literal['verified_source','needs_inspection','illustration','authored_graphic']='needs_inspection'
 shot_choice:Literal['footage','image','diagram','chart','3d','generated','split_screen','quote']='footage'
 continuity_note:str=Field(default='',max_length=500)
 motif:str=Field(default='',max_length=300)
 # documentary structure (script_audit): the chapter, what the beat does in it, who speaks, what the music does
 chapter:str=Field(default='',max_length=60)
 role:Literal['','hook','context','cause','decision','event','consequence','witness','link','breath','payoff']=''
 voice:str=Field(default='',max_length=120)
 music:str=Field(default='',max_length=120)

class CreativeBrief(BaseModel):
 model_config=ConfigDict(extra='forbid')
 title:str=Field(min_length=1,max_length=200)
 audience:str=Field(min_length=1,max_length=500)
 promise:str=Field(min_length=1,max_length=1000)
 payoff:str=Field(min_length=1,max_length=1000)
 tone:str=Field(default='clear, curious, grounded',max_length=300)
 style_id:str=Field(default='vietnam_knowledge',max_length=100)
 factual_sources:list[str]=Field(default_factory=list,max_length=50)
 beats:list[CreativeBeat]=Field(min_length=1,max_length=80)
 alternatives:list[str]=Field(default_factory=list,max_length=8)

def creative_packet(request=None):
 structure=CreativeBrief.model_json_schema()
 if request is None:return {'schema':structure,'thinking_prompts':[
  'What one question does the viewer want answered? Connect opening promise to concluding payoff.',
  'For each beat choose a visual that explains the spoken claim. Source footage, diagram and generated metaphor carry different evidence status.',
  'Offer2..3 meaningful alternatives in premise/structure/visual metaphor, choose based on actual references and audience. Style-kit names are not creative concepts.',
  'Write narration as speakable meaningful units; preserve numerals/captions separately where needed. Avoid generic filler visuals.',
  'Design recurring motif/type/palette; choose variation in framing/diagram, one focal motion per beat. Source attribution/readability/continuity matter.',
  'Map final beat boundaries from real narration words after planning; this packet has no invented duration or word timing.',
  'Documentary: give beats a chapter and role (context, cause, decision, event, consequence, witness, breath); each chapter says why, what it led to, and who lived it. script_audit reports what is missing.'],
  'next_tools':['create_project','submit_job(plan)','read_narration','design_catalog','apply_design','compose_graphic','compose_scene3d','patch_timeline','snapshot_code','observe_media']}
 brief=CreativeBrief.model_validate(request)
 from .design_library import tokens
 tokens(brief.style_id)
 if len({b.id for b in brief.beats})!=len(brief.beats):raise ValueError('Creative beat IDs unique')
 out=store.DATA/'creative-briefs'/str(uuid.uuid4());out.mkdir(parents=True)
 store.write_json(out/'brief.json',brief.model_dump());(out/'script.txt').write_text('\n\n'.join(b.narration for b in brief.beats),encoding='utf-8')
 from .script_audit import audit as script_audit
 # the documentary audit runs when the brief is structured as one (chapters or roles): a product explainer is not judged
 # for causes and witnesses
 documentary=any(x.chapter or x.role for x in brief.beats)
 return {'brief_path':str(out/'brief.json'),'script_path':str(out/'script.txt'),'brief':brief.model_dump(),'script_audit':script_audit(brief) if documentary else None,'scope':'Authored by caller AI/human, validated structure. Does not automatically verify sources, read footage semantics, generate ideas or predict retention. Use it as persistent creative memory then inspect/render.'}

def _sparse(d,model):
 """An item without the fields still at the schema default (a layer carries ~44 keys, ~25 of them default): 61 % of a
 context window's characters. Omitted means the Timeline schema's default; read_layers returns the exact JSON."""
 out={}
 for k,v in d.items():
  f=model.model_fields.get(k)
  if v is None or (f is not None and not f.is_required() and v==f.get_default(call_default_factory=True)):continue
  out[k]=v
 return out


def edit_context(pid,start=0,end=8,layer_offset=0,layer_limit=20):
 from . import agent
 import math
 if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end<=start+15 or layer_offset<0 or not 1<=layer_limit<=40:raise ValueError('Edit context window<=15s,offset>=0,limit1..40')
 p=agent.read(pid);t=p['timeline']
 if not t or end>t['total_frames']/30+.001:raise ValueError('Context window needs locked plan and in-range narration time')
 a,b=math.floor(start*30),math.ceil(end*30)
 shots=[s for s in t['shots'] if s['start_frame']<b and s['end_frame']>a]
 all_layers=[l for l in t['layers'] if l['start_frame']<b and l['end_frame']>a];layers=all_layers[layer_offset:layer_offset+layer_limit]
 mapping=[]
 for l in [*shots,*layers]:
  if not l.get('asset_id'):continue
  f=max(a,l['start_frame']);last=min(b,l['end_frame']);rate=l.get('playback_rate',1)
  mapping.append({'id':l['id'],'asset_id':l['asset_id'],'narration_frame_range':[f,last],
   'source_seconds':[l.get('source_start',0)+(f-l['start_frame'])*rate/30,l.get('source_start',0)+(last-l['start_frame'])*rate/30]})
 ids={m['asset_id'] for m in mapping};assets=[{k:v.get(k) for k in ('id','name','kind','width','height','duration','tags','role')} for v in p['assets'] if v['id'] in ids]
 from .models import AudioClip,Layer,Shot
 return {'project_id':pid,'revision':p['revision'],'window_seconds':[start,end],'frame_range':[a,b],'canvas':{k:t[k] for k in ('width','height','fps','total_frames')},
  'shots':[_sparse(x,Shot) for x in shots],'layers':[_sparse(x,Layer) for x in layers],'total_intersecting_layers':len(all_layers),'next_layer_offset':layer_offset+layer_limit if layer_offset+layer_limit<len(all_layers) else None,
  'cues':[c for c in t['cues'] if c['start']<end and c['end']>start],'audio_clips':[_sparse(c,AudioClip) for c in t['audio_clips'] if c['start_frame']<b and c['end_frame']>a],
  'omitted':'Fields at their Timeline schema default are left out; read_layers gives exact JSON to edit. Source mappings: half-open end, rate-linear; media fit/crop and layer bounds need a separate source-to-canvas transform.',
  'design':t['design'],'assets':assets,'source_mappings':mapping,'voice_hash':p['plan_meta']['audio_hash'],
  'next':'For meaning inspect the actual source_mappings windows with inspect_window/crop_detail, then snapshot_code for composition. This is edit metadata, not proof of what the pixels depict; only selected layers returned.'}
