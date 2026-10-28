"""Local MCP stdio interface: tools for a video-capable coding agent."""
import base64
import json
from pathlib import Path
from typing import Any, Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import AudioContent, TextContent, ToolAnnotations
from mcp.server.fastmcp import Image
from . import agent, store
from .audio import parse_srt
from .code_engine import scaffold
from .jobs import Worker
from .models import ProjectInput
from .observe import observe, extract_clip
from .source_tools import read_source, write_source
from .snapshot import snapshot
from .effects import catalog
from . import perception, media_tasks, subjects, generation, motion, professional, sound, design_library, color_pipeline, depth, scene3d
from . import agent_interface

mcp = FastMCP("editvideo_mcp", instructions="Headless video perception and editable creation. Start bootstrap(task,project_id?,client), discover_tools by purpose for exact schema. Caller AI interprets evidence/directs story; runtime executes. Preserve original image/audio blocks. Index/inspect useful windows then compose/patch/code, render and observe actual output. Latest revision/SHA required for mutations; narration/timebase locked,30fps half-open/localframes. Durable tasks return IDs; poll and attach completed artifacts. Native color transforms outside SDR browser; depth relative,3D authored. No studio, hidden score or approval gate.")
worker = Worker()
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)  # destructive/idempotent hints only mean something when readOnlyHint is false
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


@mcp.tool(annotations=READ)
def editvideo_list_projects(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """List local projects (one compact row each: id, title, profile, renderer, revision, updated), newest first. read_project for detail."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid pagination")
    projects = store.list_projects()
    rows = [{"id":p["id"],"title":p["config"].get("title"),"profile":p["config"].get("profile"),"renderer":p["config"].get("renderer"),
             "revision":p["revision"],"updated":p["updated_at"]} for p in projects[offset:offset+limit]]
    return {"items":rows,"total":len(projects),"next_offset":offset+limit if offset+limit<len(projects) else None}


@mcp.tool(annotations=WRITE)
def editvideo_create_project(config: dict) -> dict[str, Any]:
    """Create a headless video project. config: title, script, spoken_text, profile vertical|landscape|square, style documentary|energetic|calm, renderer remotion|hyperframes|ffmpeg, captions, narration_id, music_id. Vietnamese voice defaults to HoaiMy. Returns project_id as id and revision."""
    return agent.create(config)


@mcp.tool(annotations=READ)
def editvideo_read_project(project_id: str, detail: Literal["summary", "full"] = "summary", page: int = 0) -> dict[str, Any]:
    """Read the current revision before a patch (never guess it). Summary: counts, then shots, layers (id, kind, frames, z, attach, short text, effects) and used assets 60 a page, design, recent jobs. read_layers gives exact JSON to change; detail='full' returns timeline, media records, plan meta."""
    if page < 0:
        raise ValueError("page >= 0")
    return agent.read(project_id) if detail == "full" else agent.summary(project_id, page)


@mcp.tool(annotations=READ)
def editvideo_read_layers(project_id: str, ids: list[str]) -> dict[str, Any]:
    """Exact JSON of the named layers and/or shots plus the current revision — edit these and upsert them, instead of reading the whole timeline."""
    return agent.read_layers(project_id, ids)


@mcp.tool(annotations=WRITE)
def editvideo_configure_project(project_id: str, base_revision: int, changes: dict) -> dict[str, Any]:
    """Change project settings. Narration/script/profile changes require replanning. Renderer/mix/caption visibility preserve voice. Uses revision conflict protection."""
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        project = store.get_project(project_id)
        if project["revision"] != base_revision:
            raise ValueError("Revision conflict; read project again")
        config = ProjectInput.model_validate({**project["config"],**changes}).model_dump()
        # Release read transaction; update_project verifies base again in its write transaction.
    return store.update_project(project_id, config, expected_revision=base_revision)


@mcp.tool(annotations=WRITE)
def editvideo_import_media(project_id: str, path: str, tags: str = "", role: str = "illustration",preserve_plan: bool = False,base_revision: int | None = None) -> dict[str, Any]:
    """Copy/probe local media <=500MB/60min. Default returns asset with id and invalidates plan. preserve_plan=True plus current base_revision returns {asset,revision,plan_preserved}, keeping locked narration/timeline for visual edits. Tags describe visible subject/relevance; inspect footage before selecting it."""
    return agent.import_media(project_id,path,tags,role,preserve_plan,base_revision)


@mcp.tool(annotations=READ, structured_output=False)
def editvideo_observe_media(path: str, timestamps: list[float] | None = None, max_frames: int = 6,
                           width: int = 640, audio_start: float | None = None, audio_duration: float = 12) -> list:
    """Read a LOCAL media file into actual inline image pixels labeled by timestamp, metadata and a contact sheet. Optional inline WAV audio snippet <=30s. This supplies perception to the calling multimodal AI, not automatic descriptions/ASR. max_frames<=12. Use paths from asset or job results."""
    result = observe(path,timestamps,max_frames,width,audio_start,audio_duration)
    content = [TextContent(type="text",text=json.dumps(result,ensure_ascii=False))]
    for frame in result["frames"]:
        content.extend([TextContent(type="text",text=f"Frame {frame['index']} at {frame['timestamp']:.3f}s"),
                        Image(path=frame["path"]).to_image_content()])
    if result["audio"]:
        from pathlib import Path
        content.append(AudioContent(type="audio",data=base64.b64encode(Path(result["audio"]).read_bytes()).decode(),mimeType="audio/wav"))
    return content


@mcp.tool(annotations=WRITE)
def editvideo_extract_clip(path: str, start: float, end: float) -> dict[str, Any]:
    """Extract a playable local MP4 segment <=60s with exact input timestamps, for closer temporal inspection."""
    return extract_clip(path,start,end)


def _patch_receipt(result, operations, return_timeline=False):
    """What a patch did, not the whole timeline (a 70 s montage's timeline is 130k characters, a 29-min film's 1.4M, on
    every patch): revision, history, each operation and its target, and the timeline's counts."""
    if return_timeline:
        return result
    t = result["timeline"]

    def target(op):
        for k in ("id", "layer_id", "shot_id", "audio_id", "clip_id", "cue_id"):
            if isinstance(op.get(k), str):
                return op[k]
        for v in op.values():  # the item an upsert carries ("layer", "overlay", "audio", ...)
            if isinstance(v, dict) and isinstance(v.get("id"), str):
                return v["id"]
        return None
    applied = [{"op": op.get("op"), **({"target": target(op)} if target(op) else {})} for op in operations]
    return {"revision": result["revision"], "history": result["history"], "applied": applied,
            "counts": {k: len(t.get(k) or []) for k in ("shots", "layers", "audio_clips", "cues")} | {"total_frames": t.get("total_frames")},
            "note": "Read changed items with read_edit_context/read_layers; return_timeline=true returns the whole timeline."}


@mcp.tool(annotations=WRITE)
def editvideo_patch_timeline(project_id: str, base_revision: int, operations: list[dict] | None = None, direction_plan: str | None = None, return_timeline: bool = False) -> dict[str, Any]:
    """Atomic edits at current revision: operations (1..100), or a direct_scene direction_plan handle. Keeps authored code. 30fps half-open ranges, local animation frames. Replies with a receipt. Schemas: editvideo://schemas."""
    if direction_plan:
        import re
        from . import narrative
        if operations is not None or not re.fullmatch(r'direction-[0-9a-f]{20}',direction_plan):raise ValueError('Choose operations OR a valid direction_plan')
        plan=store.read_json(store.DATA/'direction-plans'/(direction_plan+'.json'))
        p=agent.read(project_id)
        if plan['project_id']!=project_id or plan['base_revision']!=base_revision or narrative.digest(p['timeline'])!=plan['timeline_hash']:
            raise ValueError('Direction plan is stale or belongs to another project; recompile from current scene')
        operations=plan['operations']
    if operations is None:raise ValueError('Supply operations or direction_plan')
    return _patch_receipt(agent.patch(project_id,base_revision,operations),operations,return_timeline)


@mcp.tool(annotations=READ)
def editvideo_read_narration(project_id: str, offset: int = 0, limit: int = 200, beat_offset: int = 0) -> dict[str, Any]:
    """Locked narration WAV and word timing for caption edits, paged: words [word,start_s,end_s], their cues, meaning beats by beat_offset. TTS word boundaries are actual; uploaded audio may lack word timing (estimated captions or supplied SRT): never invent word accuracy when words is empty."""
    if offset<0 or beat_offset<0 or not 1<=limit<=1000:
        raise ValueError("offset>=0; beat_offset>=0; limit 1..1000")
    plan=store.folder(project_id)/"plan"
    store.get_project(project_id)
    data=store.read_json(plan/"words.json")
    words=data.get("words",[])
    vb=store.read_json(plan/"voice-backend.json") if (plan/"voice-backend.json").exists() else {}
    from . import narrative
    timeline=store.read_json(plan/"timeline.json")
    meaning=narrative.narration(project_id,timeline,beat_offset,40)  # beats page by their own offset (word offsets emptied them)
    page=words[offset:offset+limit]
    lo,hi=(page[0]["start"],page[-1]["end"]) if page else (None,None)
    cues=[c for c in timeline["cues"] if lo is not None and c["start"]<hi and c["end"]>lo] if page else (timeline["cues"] if offset==0 else [])
    sources=sorted({w.get("source") for w in page if w.get("source")})
    return {"voice":str(plan/"voice.wav"),"timing_method":data["method"],**({"word_source":sources[0] if len(sources)==1 else sources} if sources else {}),
            "words":[[w.get("word",w.get("text")),w["start"],w["end"]] for w in page],"word_format":"[word, start_s, end_s]",
            "total_words":len(words),"next_offset":offset+limit if offset+limit<len(words) else None,
            "cues":cues,"meaning":meaning,
            "voice_note":"A source_video_silent carrier is not the final dialogue mix. Use meaning.dialogue_sources for custom narration.",
            **({"backend":vb.get("backend"),"asr_check":vb.get("asr_check")} if vb else {})}


@mcp.tool(annotations=WRITE)
def editvideo_set_captions(project_id: str, base_revision: int, srt: str) -> dict[str, Any]:
    """Attach UTF-8 SRT captions by patching current timeline; protects narration timing. For uploaded narration without ASR, provide real timestamps here. Keeps voice, does not require re-TTS."""
    ops=[{"op":"replace_cues","cues":parse_srt(srt)}]
    return _patch_receipt(agent.patch(project_id,base_revision,ops),[{"op":"replace_cues","cues":len(ops[0]["cues"])}])


@mcp.tool(annotations=WRITE)
def editvideo_export_code(project_id: str, engine: Literal["remotion","hyperframes"] = "remotion", overwrite: bool = False) -> dict[str, Any]:
    """Export editable React/TypeScript or HTML/GSAP source with portable effects and local media, once after planning. Authored code survives data patches; overwrite=True rebuilds (keep custom code first). Does not change the renderer."""
    return scaffold(project_id,engine,overwrite)


@mcp.tool(annotations=WRITE)
def editvideo_snapshot_code(project_id: str, engine: Literal["remotion","hyperframes"], frames: list[int], sheet: bool = True) -> list:
    """Render 1..8 exact code frames (one bundled process, cached per project) before encoding a video. Frames are zero-based 30fps. sheet=true (default) returns ONE labelled contact sheet instead of N images — several times fewer image tokens; use sheet=false only to inspect fine detail."""
    result=snapshot(project_id,engine,frames)
    content=[TextContent(type="text",text=json.dumps({k:v for k,v in result.items() if k!="source"},ensure_ascii=False))]
    if sheet and len(result["frames"])>1:
        from .review import contact_sheet
        content.append(Image(path=contact_sheet([f["path"] for f in result["frames"]],[f"{f['frame']}" for f in result["frames"]])).to_image_content())
        return content
    for frame in result["frames"]:
        content.extend([TextContent(type="text",text=f"Frame {frame['frame']} at {frame['timestamp']:.3f}s"),
                        Image(path=frame["path"]).to_image_content()])
    return content


@mcp.tool(annotations=WRITE)
def editvideo_write_code(project_id: str, engine: Literal["remotion","hyperframes"], relative_path: str,
                        content: str, expected_sha256: str | None = None) -> dict[str, Any]:
    """Write an editable project code file with SHA256 conflict protection and prior-source history. Read code first; use returned hash. New files use null hash. Supports HTML/CSS/JS/TSX/JSON/SVG <=2MB. Source must already be exported; renderer uses exact code snapshot."""
    return write_source(project_id,engine,relative_path,content,expected_sha256)


@mcp.tool(annotations=READ)
def editvideo_read_code(project_id: str, engine: Literal["remotion","hyperframes"], relative_path: str) -> dict[str, Any]:
    """Read current project code and SHA256. Start with index.tsx (Remotion), index.html (Hyperframes), or input.json. Agents may use this without local filesystem tools."""
    return read_source(project_id,engine,relative_path)


@mcp.tool(annotations=WRITE)
def editvideo_submit_job(project_id: str, kind: Literal["plan","preview","final"]) -> dict[str, Any]:
    """Queue voice-first planning or render exported code. Returns job_id as id immediately; use get_job. 'plan' may use online Edge TTS or configured model; uploaded narration works offline. Preview/final use project renderer; render snapshots source so later code edits cannot alter this output."""
    job = store.create_job(project_id,kind)
    worker.submit(job)
    return job


@mcp.tool(annotations=READ)
def editvideo_get_job(job_id: str) -> dict[str, Any]:
    """Read job progress/errors and absolute output artifact paths, including MP4, storyboard, source snapshot, technical file and ZIP."""
    return agent.result(job_id)


@mcp.tool(annotations=WRITE)
def editvideo_cancel_job(job_id: str) -> dict[str, Any]:
    """Request cancellation of this queued/running job."""
    store.cancel(job_id)
    return store.get_job(job_id)


@mcp.resource("editvideo://schemas")
def schemas() -> str:
    from .models import Timeline
    return json.dumps({"ProjectInput":ProjectInput.model_json_schema(),"Timeline":Timeline.model_json_schema(),
        "SubjectRequest":subjects.SubjectRequest.model_json_schema(),"MaskEditRequest":subjects.MaskEditRequest.model_json_schema(),
        "GenerationRequest":generation.GenerationRequest.model_json_schema(),"RecipeRequest":professional.RecipeRequest.model_json_schema(),
        "ApplyDesign":design_library.ApplyDesign.model_json_schema(),"GraphicRequest":design_library.GraphicRequest.model_json_schema(),
        'ColorRequest':color_pipeline.ColorRequest.model_json_schema(),'DepthRequest':depth.DepthRequest.model_json_schema(),'DepthEditRequest':depth.DepthEditRequest.model_json_schema(),'Scene3D':scene3d.Scene3D.model_json_schema(),'CreativeBrief':agent_interface.CreativeBrief.model_json_schema()},ensure_ascii=False)


@mcp.resource('editvideo://schema/{name}')
def one_schema(name: str) -> str:
    """Retrieve just one schema instead of all model definitions."""
    all_schemas=json.loads(schemas());all_schemas['CreativeBrief']=agent_interface.CreativeBrief.model_json_schema()
    if name not in all_schemas:raise ValueError('Choose '+', '.join(all_schemas))
    return json.dumps(all_schemas[name],ensure_ascii=False)


@mcp.resource('editvideo://runtime/{engine}/{filename}')
def runtime_template(engine: str, filename: str) -> str:
    """Current bundled runtime source for explicit hash-protected migration."""
    from .code_engine import ENGINES
    from .media import sha256
    allowed={'remotion':{'effects.cjs':'effects.js','index.tsx':'AgentVideo.tsx','design.cjs':'design.js','Scene3D.tsx':'Scene3D.tsx','scene3d.js':'scene3d.js'},
             'hyperframes':{'effects.js':'effects.js','hyper-runtime.js':'hyper-runtime.js','design.js':'design.js','scene3d.js':'scene3d.js'}}
    if engine not in allowed or filename not in allowed[engine]:raise ValueError('Allowed runtime files: remotion effects.cjs/design.cjs/index.tsx, hyperframes effects.js/design.js/hyper-runtime.js')
    path=ENGINES/allowed[engine][filename]
    return json.dumps({'engine':engine,'filename':filename,'sha256':sha256(path),'content':path.read_text(encoding='utf-8'),
                      'instructions':'Read current project code/hash first. Merge needed functions into customized runtime/entry or use supplied template intentionally. write_code backs up prior source and checks hash. Never silently overwrite authored entry; ordinary data patches preserve it.'},ensure_ascii=False)


_PACKET_DROP={'director_guide'}  # static guidance lives in the prompts/manifest; repeating it cost ~570 tokens per call
def _packet_text(result):
    """Text half of an evidence packet: images travel as image blocks, so per-frame paths/hashes stay in the manifest."""
    slim={k:v for k,v in result.items() if k not in _PACKET_DROP}
    if isinstance(slim.get('frames'),list):
        slim['frames']=[{k:v for k,v in f.items() if k not in ('path','sha256')} if isinstance(f,dict) else f for f in slim['frames']]
    return json.dumps(_lean(slim),ensure_ascii=False,separators=(',',':'),default=str)
def image_packet(result):
    content=[TextContent(type="text",text=_packet_text(result))]
    for f in result.get("frames",[]):
        content.extend([TextContent(type="text",text=f"Evidence {f.get('evidence_id',f['index'])}: {f['timestamp']:.3f}s; displayed size {f.get('display_size')}"),Image(path=f["path"]).to_image_content()])
    if result.get("path"):
        content.append(Image(path=result["path"]).to_image_content())
    if result.get("diagnostic"):
        content.extend([TextContent(type="text",text="Derived diagnostic: flow / aligned residual; inspect limitations and original frames."),
                        Image(path=result["diagnostic"]["path"]).to_image_content()])
    reference=result.get("reference")
    if reference:
        for f in reference["frames"]:
            content.extend([TextContent(type="text",text=f"REFERENCE {f['timestamp']:.3f}s"),Image(path=f["path"]).to_image_content()])
    if result.get("audio"):
        from pathlib import Path
        content.append(AudioContent(type="audio",mimeType="audio/wav",data=base64.b64encode(Path(result["audio"]).read_bytes()).decode()))
    return content


@mcp.tool(annotations=READ)
def editvideo_effect_catalog(query: str = "", family: str | None = None, offset: int = 0, limit: int = 12, detail: Literal["auto", "full"] = "auto") -> dict[str, Any]:
    """Find supported effects by English intent/id/family, ranges, examples, cautions and atlas previews; both engines. Apply via update_shot/upsert_layer; transitions via shot.transition. Query exact id for a full card before inventing parameters."""
    return catalog(query,family,offset,limit,detail)


@mcp.tool(annotations=READ)
def editvideo_design_catalog(kind: Literal['all','font','palette','style','motion','component','pattern','icon'] = 'all', query: str = '', offset: int = 0, limit: int = 12) -> dict[str, Any]:
    """Search bundled design assets (Vietnamese/English terms, paginated): 16 offline Vietnamese font families, 24 palettes with contrast, 16 style kits, 10 type roles, 12 motion directions, 10 components, 12 SVG patterns, 24 icons; preview paths when built. Measurements, not beauty scores."""
    return design_library.catalog(kind,query,offset,limit)


@mcp.tool(annotations=READ)
def editvideo_color_catalog() -> dict[str,Any]:
    """Discover 7 original display-BT709 3D LUTs, explicit input transfer/range choices and float/10bit pipeline limits. Native PQ/HLG conversion/SDR tone-map; browser compositions remain SDR and SDR→PQ is labelled derived, not recovered HDR. See ColorRequest; poll process_color task and inspect tags/linear sampled scope afterward."""
    return color_pipeline.catalog()


@mcp.tool(annotations=WRITE)
def editvideo_process_color(request: dict) -> dict[str,Any]:
    'Durable <=120s colour processing: camera log/HDR to Rec709, display grade/LUT, or scene-referred graph with ACEScct/Cineon looks and tracked windows. Exact grade/graph nodes: ColorRequest schema and COLOR_DEPTH_3D guide. Poll task; verify output with color_scopes.'
    return media_tasks.submit('color',request)


@mcp.tool(annotations=READ, structured_output=False)
def editvideo_color_scopes(path: str, timestamps: list[float] | None = None, skin_region: list[float] | None = None, compare: str | None = None) -> list:
    """Display-code scopes: luma/clipping, shadow/mid/highlight cast, chroma and skin hue. skin_region=[x,y,w,h]; compare=file at the same times. One sheet of thumbnails/waveform/RGB parade/vectorscope plus measured flags. Use before/after process_color."""
    from . import scopes
    r = scopes.scopes(path, timestamps, skin_region, compare)
    return [TextContent(type="text", text=json.dumps({k: v for k, v in r.items() if k != "image"}, ensure_ascii=False)), Image(path=r["image"]).to_image_content()]


@mcp.tool(annotations=WRITE)
def editvideo_compose_globe(project_id: str, base_revision: int, request: dict) -> dict[str,Any]:
    """Textured 3D globe layer: earth_texture asset, optional clouds/bump, markers [{id,lat,lon,label,color,appear}], great-circle arcs [{id,start,end,height,grow,color,traveler}] that grow by frame, camera keys [{frame,lat,lon,altitude,look}] slerped for space-to-place dives. Far-side labels hide. Illustrative geography; inspect snapshots."""
    from .globe import compose_globe
    return compose_globe(project_id,base_revision,request)


@mcp.tool(annotations=WRITE)
def editvideo_retime_footage(request: dict) -> dict[str,Any]:
    """Durable smooth retime task, <=60 s source window: constant speed (.05..8), speed_keys [{at s from start,speed}] ramps, or peaks [source s, e.g. rank_clips peak_at] slowed to peak_speed for hold_s with ramp_s S-curves; interpolation flow (Farneback warp), blend or nearest; motion_blur 0..1, blur_samples; reverse (<=20 s out); fps/max_width/crf. Check occlusions for ghosting. Silent; poll get_media_task, attach_media_result, place at playback_rate 1."""
    return media_tasks.submit('retime',request)


@mcp.tool(annotations=READ,structured_output=False)
def editvideo_inspect_color(path: str, input_space: Literal['auto','bt709','bt601_625','bt601_525','srgb','hdr10','hlg'] = 'auto', input_range: Literal['auto','limited','full'] = 'auto', timestamps: list[float] | None = None) -> list:
    """Read actual color tags/bitdepth and1..8 sampled log-luminance waveform images plus linear luma percentiles. Absolute reference nits only for declared PQ; SDR100nit interpretation is not measured display brightness. Missing tags request a declaration; no filename inference or aesthetic score. Downsampled scope cannot certify whole-film MaxCLL/MaxFALL."""
    return image_packet(color_pipeline.inspect(path,input_space,input_range,timestamps))


@mcp.tool(annotations=WRITE)
def editvideo_install_depth_model(allow_download: bool = False) -> dict[str,Any]:
    """Explicitly install/verify pinned Depth Anything V2 Small HF (~100MB,Apache2.0). Requires optional temporal torch/transformers environment. No download during estimate_depth; model hashes/commit returned. This is a relative inverse-depth image model, not calibrated meters/semantic tracking or video-depth model."""
    return depth.install(allow_download)


@mcp.tool(annotations=WRITE)
def editvideo_estimate_depth(request: dict) -> dict[str,Any]:
    """Relative depth task for a local image/video (<=15 s/450 frames, width 128..960, fps 1..30; cached pinned model; tone-map HDR first): float NPZ + 16-bit maps, per-scene normalised, cut-reset flow stabilisation 0..0.6. Not meters or identity. Poll get_media_task; read_depth before editing."""
    return media_tasks.submit('depth',request)


@mcp.tool(annotations=READ,structured_output=False)
def editvideo_read_depth(task_id: str, offset: int = 0, limit: int = 24, frames: list[int] | None = None) -> list:
    """Read depth records paginated<=60 and1..8 inline original frame + color-depth preview +16bitmap. High/white is predicted near inverse depth, scene-global normalization not meters. Reliability records measure flow support only. Inspect temporal edges/occlusion/reflective details before depth editing."""
    result=depth.read(task_id,offset,limit,frames);content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False))]
    for f in result['frames']:
        for name in ('path','preview_path','depth_path'):content.append(Image(path=f[name]).to_image_content())
    return content


@mcp.tool(annotations=WRITE)
def editvideo_edit_depth(request: dict) -> dict[str,Any]:
    """DepthEditRequest: focus_blur, atmosphere, visualize or still-only parallax from a completed depth session (normalized inverse depth). Screen blur, not optical bokeh; parallax is a small 2.5D warp (±.06), not unseen-surface reconstruction. Silent clip; durable task; inspect frames and edges."""
    return media_tasks.submit('depth_edit',request)


@mcp.tool(annotations=READ)
def editvideo_scene3d_catalog() -> dict[str,Any]:
    """4 editable 3D scene presets, 7 primitives: perspective camera frame keys, ambient/directional/point lights, roughness/metalness materials, ground/shadows; native WebGL in both engines (authored units, radians). No depth reconstruction, glTF rigging or motion blur. Read the Scene3D schema, compose_scene3d, snapshot key poses."""
    return scene3d.catalog()


@mcp.tool(annotations=WRITE)
def editvideo_compose_scene3d(project_id: str, base_revision: int, request: dict) -> dict[str,Any]:
    """Atomic 3D layer (id, preset or scene, frames, box, z) keeping voice/timebase. Scene3D: <=64 objects, <=8 lights, perspective camera pose keys, materials, shadows; radians, frame-local keys. Fresh exports carry the Three runtime; customised source needs a merge. Inspect the render; not recovered real geometry."""
    return scene3d.compose(project_id,base_revision,request)


@mcp.tool(annotations=WRITE)
def editvideo_apply_design(project_id: str, base_revision: int, request: dict) -> dict[str, Any]:
    """Apply font/colour/type tokens atomically: style_id, optional palette_id, heading_font_id, body_font_id, layer_roles {layer_id: role}. Roles set size/family/weight/leading/tracking; colours opt-in via color_role/background_role. Keeps narration/timing/custom code. Inspect wrapping on critical frames."""
    return design_library.apply(project_id,base_revision,request)


@mcp.tool(annotations=WRITE)
def editvideo_compose_graphic(project_id: str, base_revision: int, request: dict) -> dict[str, Any]:
    """Compile one of 10 art-directed components: title, quote, statistic, chapter, source_card, two_column, steps, lower_third, keyword, end_card, using the applied design. Statistics/evidence need a visible source; values stay factual. Same id replaces atomically. Inspect suggested frames."""
    return design_library.compose(project_id,base_revision,request)


@mcp.tool(annotations=READ)
def editvideo_read_design_preview(kind: Literal['font','palette','style','component','pattern','icon','lut','effect','combo'], id: str, engine: Literal['remotion','hyperframes'] = 'remotion') -> list:
    """Return an actual library preview inline for multimodal aesthetic reasoning. Font/palette sheets use bundled glyphs/opaque swatches; style/component/pattern/icon images are observed Remotion atlas frames. Source and Hyperframes comparisons remain in design-atlas.json. Build scripts/design_atlas.py if previews absent; do not infer unknown visual output from catalog names."""
    if kind in ('effect','combo'):  # the effect's own stage: source | t+10 | t+30 | t+52
        from .effects import catalog as fx_catalog
        r=fx_catalog(id,detail='full');card=r.get('combo') or next((x for x in r.get('effects',[]) if x['id']==id),None)
        if not card or not card.get('preview'):raise ValueError('Unknown effect/combo or preview not built (scripts/effect_atlas.py)')
        path=card['preview']['strip'].get(engine) or next(iter(card['preview']['strip'].values()))
        brief={k:card.get(k) for k in ('id','family','use_when','purpose','pairs_with','avoid','stack') if card.get(k) is not None}
        return [TextContent(type='text',text=json.dumps({**brief,'panels':card['preview']['panels'],'engine':engine},ensure_ascii=False)),Image(path=path).to_image_content()]
    result={'items':color_pipeline.catalog()['luts']} if kind=='lut' else design_library.catalog(kind,id,limit=50)
    item=next((x for x in result['items'] if x['id']==id),None)
    if not item:raise ValueError('Unknown library item')
    preview=item.get('preview')
    if not preview:raise ValueError('Preview not built; run scripts/design_atlas.py or snapshot an authored project')
    return [TextContent(type='text',text=json.dumps(item,ensure_ascii=False)),Image(path=preview['path']).to_image_content()]


@mcp.tool(annotations=READ)
def editvideo_layout_text(font_id: str, text: str, size: float = 54, width: float = 800, weight: int = 400, italic: bool = False, variation_axes: dict[str,float] | None = None) -> dict[str, Any]:
    """FreeType glyph advances/bounds of a bundled font at a weight: line proposals, metrics, missing Vietnamese/other glyphs, overlong tokens (NFC). size 12..300 px, width 100..4000 px, text <= 2000. Estimate before composing; inspect the Chromium output after (tracking/shaping/wrapping can differ)."""
    return design_library.layout_text(font_id,text,size,width,weight,italic,variation_axes)


@mcp.tool(annotations=READ)
def editvideo_derive_palette(seed: str = '#81e6be', harmony: Literal['analogous','complementary','split_complementary','triadic','monochrome'] = 'analogous', tone: Literal['dark','light'] = 'dark') -> dict[str, Any]:
    """Editable semantic colour roles from a #RRGGBB seed (5 HSL harmonies, dark/light) with real sRGB contrast ratios: background/surface/text/muted/accent/secondary/on_accent. An option generator, not a footage grade; check against real footage."""
    return design_library.derive_palette(seed,harmony,tone)


@mcp.tool(annotations=READ)
def editvideo_professional_toolkit(platform: Literal['tiktok','reels','youtube_shorts','youtube_long'] = 'youtube_long', query: str = '') -> dict[str, Any]:
    """17 editorial recipes (hook/payoff, captions, evidence, split screen, chapters, composition, audio bridges, finishing); short-form platforms add templates (talking head, how-to, listicle, before/after, POV, product, sports velocity, nature, food, city), UI zones, delivery spec, evidence. Query intent/id; compose_edit; inspect output."""
    return professional.toolkit(platform,query)


@mcp.tool(annotations=WRITE)
def editvideo_compose_edit(project_id: str, base_revision: int, request: dict, dry_run: bool = False) -> dict[str, Any]:
    """Apply one professional recipe atomically: hook_card, lower_third (avoid: a subject to keep clear), chapter_card, evidence_card (source_text required), pull_quote, keyword_callout, picture_in_picture, split_screen, comparison_labels, focus_spotlight, tracked_callout, word_captions (real word timings only), chapter_progress, j_cut_audio, l_cut_audio, sound_bridge, audio_finish. dry_run optional. Fields: professional_toolkit."""
    return professional.compose(project_id,base_revision,request,dry_run)


@mcp.tool(annotations=WRITE)
def editvideo_read_audio_events(path: str, start: float = 0, end: float | None = None, max_events: int = 24) -> list:
    """Read <=120 s of audio: spectral-flux onsets, quiet intervals, LUFS/true peak/range on chosen channels (20 ms hop); acoustic change is not beat, meaning or a cut order. Inline WAV when <=30 s, else a path. Pair with transcript/frames for motivated cuts, J/L bridges, SFX timing."""
    result=sound.read_events(path,start,end,max_events)
    if result['window'][1]-result['window'][0]>30:
        result={**result,'listen_path':result['audio'],'audio':None}
    return image_packet(result)


@mcp.tool(annotations=WRITE)
def editvideo_design_sound(kind: Literal['whoosh','impact','tick','riser','ambient','pop','shutter','drone','room_tone','wind','chime','sub_drop','reverse_cymbal','crunch','braam','suck_out','beat','rain','forest','shepard','heartbeat','tinnitus','siren','clock'] = 'whoosh', duration: float = .6, seed: int = 7, gain_db: float = -18, bpm: float = 124, end_bpm: float | None = None) -> dict[str, Any]:
    'Procedural 48kHz accents and beds, no model. Supported kinds/fields in schema; accents .08..12s, beds <=60s, gain_db -48..-3. Pulse beds support bpm/end_bpm and beat_times. Returns onset/peak anchors: place sound so its peak lands on the intended event.'
    return sound.design(kind,duration,seed,gain_db,bpm,end_bpm)


@mcp.tool(annotations=WRITE)
def editvideo_project_from_video(path: str, profile: Literal["vertical","landscape","square","portrait45"] = "landscape", engine: Literal["remotion","hyperframes"] = "remotion", title: str | None = None,
                                 segments: list[list[float]] | None = None) -> dict[str, Any]:
    """Open actual footage as a directly editable project, retaining original audio (or silence), without script/TTS. Creates a locked 30fps timeline, one source shot, local media/voice. segments=[[start,end],...] source seconds in any order: a selects cut (one shot per range, their audio joined with micro-fades; time_map in the result). Import <=500MB, <=1h."""
    if segments:
        r=agent.from_segments(path,segments,profile,engine,title)
        return {"id":r.get("project_id"),**r}  # same key as the single-source result
    return agent.from_video(path,profile,engine,title)


@mcp.tool(annotations=WRITE)
def editvideo_create_silent_project(profile: Literal["vertical","landscape","square","portrait45"] = "vertical", seconds: float = 30,
                                   engine: Literal["remotion","hyperframes"] = "remotion", title: str | None = None) -> dict[str, Any]:
    """Silent exact-length project (30 fps) for picture-and-text edits (reels, ads); replace its carrier shot with footage."""
    return agent.create_silent(profile,round(seconds*30),engine,title)


@mcp.tool(annotations=WRITE)
def editvideo_index_video(path: str, scene_threshold: float = 10, offset: int = 0, limit: int = 20) -> dict[str, Any]:
    """Build/reuse a local temporal index: candidate cuts, segment ranges, suggested inspection times, sampled palette/luminance/pixel change, audio energy. <=1h. Pagination avoids flooding model context. Does not infer semantic scenes, optical flow, beat/BPM or aesthetics. Use inspect_window for actual visual evidence."""
    return perception.index_video(path,scene_threshold,offset,limit)


@mcp.tool(annotations=WRITE)
def editvideo_inspect_window(path: str, start: float, end: float, frames: int = 8, width: int = 960, listen: bool | None = None) -> list:
    """Read motion through 2..12 time-ordered inline frames plus audio (only for clients declaring it at bootstrap) from a <=30s window. Returns evidence IDs, dimensions, sample spacing. Narrow the window for rapid action; sampled frames cannot establish unseen events. Pair with index_video for long footage."""
    return image_packet(perception.inspect_window(path,start,end,frames,width,listen))


@mcp.tool(annotations=WRITE)
def editvideo_crop_detail(path: str, timestamp: float, region: list[float], width: int = 1280) -> list:
    """Inspect fine text, subject or visual artifact at full source detail. region=[left,top,right,bottom] normalized 0..1. Returns pixels plus original crop/display coordinate mapping. Use coordinates of the supplied image, accounting for resizing."""
    return image_packet(perception.crop_detail(path,timestamp,region,width))


@mcp.tool(annotations=WRITE)
def editvideo_aesthetic_packet(path: str, start: float = 0, end: float | None = None, frames: int = 8, reference_path: str | None = None) -> list:
    """Provide actual video frames/audio, local measurements and optional visual reference to the calling multimodal AI. Director guide covers hierarchy, palette, typography, framing, temporal continuity, narration alignment and actionable edits with evidence. No numeric beauty score, hidden aesthetic model or approval workflow."""
    return image_packet(perception.aesthetics_packet(path,start,end,frames,reference_path))


@mcp.tool(annotations=WRITE)
def editvideo_transcribe(path: str, model: Literal["tiny","base","small"] = "small", language: Literal["vi","en","auto"] = "vi", allow_download: bool = False, vocabulary_hint: str = "") -> dict[str, Any]:
    """Local CPU Whisper ASR for video/audio <=1h; returns words, estimated times, cues and SRT. First use needs allow_download=True (~75/145/465MB model), later works offline. May take minutes. ASR is not verified text or forced alignment. Apply corrected cues through patch/replace_cues or set_captions."""
    return perception.transcribe(path,model,language,allow_download,vocabulary_hint)


@mcp.resource("editvideo://director-guide")
def director_guide() -> str:
    return perception.DIRECTOR_GUIDE


@mcp.tool(annotations=WRITE)
def editvideo_track_region(path: str, start: float, end: float, region: list[float], sampling_fps: int = 8, output_width: int = 1920, output_height: int = 1080) -> dict[str, Any]:
    """Track a textured region locally using optical flow in a <=30s window. region = source-normalised [left, top, right, bottom]. Returns temporal boxes, loss status and x/y keyframes; pin_to_track maps it onto layers through the shot. No semantic identity; inspect after loss."""
    return perception.track_region(path,start,end,region,sampling_fps,output_width,output_height)


@mcp.tool(annotations=WRITE)
def editvideo_track_plane(path: str, corners: list[list[float]], start: float, end: float, fps: int = 30, work_width: int = 960,
                          exclude: list[list[float]] | None = None, smooth: int = 2, refine: bool = True, detail: Literal["summary", "full"] = "summary") -> dict[str, Any]:
    """Planar (Mocha-style) track of a flat surface in perspective (screen, sign, poster, wall). corners TL,TR,BR,BL source-normalised at start. KLT + MAGSAC homography + drift-free ECC with occluder rejection; stops when lost. Returns a summary and track_id for screen_replace (full per-frame corners on disk; detail=full inlines them). ≤1.2 px on a synthetic move with an occluder."""
    from . import planar
    r = planar.track_plane(path, corners, start, end, fps, work_width, exclude, smooth, refine)
    return r if detail == "full" else planar.summary(r)


@mcp.tool(annotations=WRITE)
def editvideo_screen_replace(project_id: str, base_revision: int, track: str | dict, layer: dict, timeline_start_frame: int, source_box: list[float] | None = None,
                             fit: Literal["cover", "contain"] = "cover", dry_run: bool = False) -> dict[str, Any]:
    """Pin a layer (image/video/text/svg/scene3d) onto a tracked plane: track = track_id from track_plane; layer = layer fields (id, kind, asset_id/text, z, effects like light_wrap/tint_fill to match the plate); timeline_start_frame = where the tracked window starts in the edit; source_box/fit = how the plate sits in the frame. Writes a per-frame corner_pin."""
    from . import planar
    return planar.screen_replace(project_id, base_revision, track, layer, timeline_start_frame, tuple(source_box or (0, 0, 1, 1)), fit, dry_run)


@mcp.tool(annotations=WRITE)
def editvideo_analyze_motion(path: str, start: float, end: float, region: list[float] | None = None, sampling_fps: int = 12, width: int = 384, evidence_frames: int = 6) -> list:
    """Dense motion reading of ≤15 s (≤240 samples): forward/backward flow, camera affine, motion-compensated residual, ROI luma/sharpness/clipping traces, temporal FFT. Returns event frames + flow/residual images inline and a paged manifest. CPU only. width 160..640, fps 2..30 (low fps aliases)."""
    return image_packet(motion.analyze(path,start,end,region,sampling_fps,width,evidence_frames))


@mcp.tool(annotations=READ)
def editvideo_read_motion(manifest: str, offset: int = 0, limit: int = 24) -> dict[str, Any]:
    """Page measured per-interval flow/camera/residual and ROI trace from analyze_motion. limit1..60. Use this to select exact source times for crop_detail, masks, cuts or effects. No automatic semantic/quality decision."""
    return motion.read(manifest,offset,limit)


@mcp.tool(annotations=WRITE)
def editvideo_temporal_lens(path: str, start: float, end: float, region: list[float] | None = None, sampling_fps: int = 24, width: int = 256, low_hz: float = .5, high_hz: float = 4., gain: float = 4.) -> list:
    """Expose subtle temporal RGB variation in a derived original/amplified split video + inline frames. FFT bandpass in a fixed ROI; no learned model or stabilization. 0<low<high<fps/2, gain 1..10, width 160..384, 16..240 samples. Camera motion, codec noise and ringing amplify too; a derived view, not evidence. Run analyze_motion first."""
    return image_packet(motion.temporal_lens(path,start,end,region,sampling_fps,width,low_hz,high_hz,gain))


@mcp.tool(annotations=WRITE)
def editvideo_refine_footage(task_id: str, changes: dict) -> dict[str, Any]:
    """New generation from a completed local_ltx task, keeping seed/prompt/reference snapshots unless changed (changes: prompt, seed, size, frame_count, fps, references, strength, fit, crop, noise, timeout). A full new diffusion pass, parent kept. Inspect the flaw first; poll, then observe/analyze_motion and attach the chosen version."""
    return generation.refine(task_id,changes)


@mcp.tool(annotations=READ)
def editvideo_media_capabilities(probe_local: bool = False) -> dict[str, Any]:
    """Discover actual installed subject/mask models and configured footage providers/workflows. Optional local ComfyUI probe. Never returns API keys; configured does not mean live generation tested."""
    result=generation.capabilities(probe_local)
    result['depth']={'model':'Depth Anything V2 Small HF','revision':depth.REVISION,'cached':(depth.model_root()/'install.json').exists(),'scope':'Relative inverse depth, image model with cut-reset flow stabilizer; hash checked before inference, no meters'}
    result['color_pipeline']={'backend':'FFmpeg zscale/tonemap/lut3d','luts':len(color_pipeline.LUTS),**color_pipeline.backend_capabilities(),'browser_composition':'SDR','hdr_output':'HEVC10bit/PQ/BT2020; source origin recorded, SDR-derived explicitly labelled'}
    from . import voices
    result['narration']=voices.capabilities()
    result['scene3d']={'backend':'ThreeCanvas/Three.js WebGL','presets':len(scene3d.PRESETS),'three_installed':(store.ROOT/'engines/node_modules/three/package.json').exists(),'scope':'Authored primitives/materials/lights/frame camera, not calibrated reconstruction'}
    return result


@mcp.tool(annotations=WRITE)
def editvideo_track_subject(request: dict) -> dict[str, Any]:
    """Durable SAM2 segmentation/tracking (window ≤15 s, fps 1..30, width 256..1024). prompts [{object_id,label,frame,box,points,labels}] in source-normalised coordinates, frames local; each object needs a frame-0 prompt, later prompts fix occlusion. Poll get_media_task, then read_subject. Masks are not identity verification."""
    return media_tasks.submit("subject",request)


@mcp.tool(annotations=WRITE)
def editvideo_refine_subject(task_id: str, prompts: list[dict]) -> dict[str, Any]:
    """Correct a completed subject session with complete prompts on selected object/frame. Replaces prompt at same object/frame, preserves other corrections, creates a new immutable task. Include all desired points/labels and box on each replaced frame; inspect masks before applying edits."""
    return subjects.refine(task_id,prompts)


@mcp.tool(annotations=READ, structured_output=False)
def editvideo_read_subject(task_id: str, object_id: int, offset: int = 0, limit: int = 60, frames: list[int] | None = None) -> list:
    """Read paginated temporal boxes/visible mask areas and 1..8 inline subject-overlay AND grayscale mask images. Visible means nonempty predicted mask, not confidence. Frame indices start at window 0. Source coordinates, duration/fps and paths are provided for tracking overlays, crops and subject edits."""
    result=subjects.read_session(task_id,object_id,offset,limit,frames)
    content=[TextContent(type="text",text=json.dumps(result,ensure_ascii=False))]
    for f in result["frames"]:
        content.extend([TextContent(type="text",text=f"Frame {f['index']} at source {f['timestamp']:.3f}s: subject overlay, then mask"),Image(path=f["path"]).to_image_content(),Image(path=f["mask_path"]).to_image_content()])
    return content


@mcp.tool(annotations=WRITE)
def editvideo_edit_subject(request: dict) -> dict[str, Any]:
    """Durable masked edit from a track_subject task: operation remove|blur|replace_background|foreground|color_grade|spotlight|outline|reframe on object_ids. remove uses ProPainter (temporal, cut-aware; non-commercial licence) or lama/telea/clean_plate; replace_background needs background_path; foreground returns alpha. Key params: dilation, feather, blur_radius, strength, output size for reframe. Keeps window audio. Poll, inspect edges, attach."""
    return media_tasks.submit("mask_edit",request)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True,openWorldHint=True))
def editvideo_generation_nodes(query: str = "", offset: int = 0, limit: int = 12) -> dict[str, Any]:
    """Discover actual ComfyUI node classes and input/output definitions, paginated/filterable (e.g. Wan, SaveVideo, inpaint). Requires configured/running server. Build API workflow using installed classes/model names; do not invent unavailable nodes."""
    return generation.discover_nodes(query,offset,limit)


@mcp.tool(annotations=WRITE)
def editvideo_register_generation_workflow(name: str, graph: dict, bindings: dict, description: str = "", output_node: str | None = None) -> dict[str, Any]:
    """Register a ComfyUI API-format graph (not UI JSON). bindings map prompt/negative_prompt/seed/width/height/frames/fps/reference_image/reference_mask to [{node,input}]; prompt required, unbound inputs keep graph values. output_node picks the saver. Node classes are checked at submit."""
    return generation.register_workflow(name,graph,bindings,description,output_node)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=False,openWorldHint=True))
def editvideo_generate_footage(request: dict) -> dict[str, Any]:
    """Durable footage generation (check media_capabilities first). local_ltx: prompt and/or reference image plus ≤4 reference_frames {path,frame_index,strength}; reference_strength/fit/crop, image_cond_noise_scale; presets draft/standard/detail or explicit size/frames. Other providers need real configuration. Output is illustration, not evidence: inspect pixels before attaching."""
    return media_tasks.submit("generate",request)


@mcp.tool(annotations=READ)
def editvideo_get_media_task(task_id: str) -> dict[str, Any]:
    """Read persistent subject/masked-edit/generation state, progress/error, actual artifact paths and provenance. Tasks survive closure of MCP session. Poll at sensible intervals, then inspect pixels/audio. A failed/cancelled task publishes no usable result."""
    result=media_tasks.get(task_id)
    remote=media_tasks.folder(task_id)/"remote.json"
    if remote.exists():result["remote"]=store.read_json(remote)
    return result


@mcp.tool(annotations=WRITE)
def editvideo_cancel_media_task(task_id: str) -> dict[str, Any]:
    """Request cooperative cancellation of the selected task. Local work stops at frame/decoder boundary. Provider cancellation is scoped by remote ID; active old ComfyUI jobs may continue remotely when safe targeted interrupt is unavailable. No global queue clearing/interruption."""
    return media_tasks.cancel(task_id)


@mcp.tool(annotations=WRITE)
def editvideo_attach_media_result(task_id: str, project_id: str, base_revision: int, output: str = "video", tags: str = "", role: Literal["illustration","evidence","metaphor","reconstruction","decoration"] = "reconstruction") -> dict[str, Any]:
    """Attach a completed immutable task artifact into project with measured media metadata and provenance. Preserves current locked narration/timeline/plan, increments revision, returns asset id for update_shot/upsert_layer. output video (edit/generation) or overlay (subject diagnostic). Read project revision first. Attachment itself does not replace any shot."""
    return media_tasks.attach(task_id,project_id,base_revision,output,tags,role)


@mcp.prompt()
def video_director(task: str) -> str:
    """Aesthetic and editing workflow for a multimodal coding agent."""
    return f"Task: {task}\n{perception.DIRECTOR_GUIDE}\nRead project/schema. Index footage, inspect selected windows and references, set_design, search effect_catalog, patch or edit source, snapshot critical frames, render and inspect output. Preserve uncertainty about unsampled footage. No studio or approval gates."


@mcp.tool(annotations=READ)
def editvideo_bootstrap(task: str = '', project_id: str | None = None, client: Literal['claude','codex','openai','generic'] = 'generic') -> dict[str,Any]:
    """Start with task routing and optional project revision/counts, then discover_tools for exact schemas. Calling AI interprets pixels and directs story; runtime supplies evidence/edits. Includes client transport/modality limits, not a full timeline."""
    out=agent_interface.bootstrap(task,project_id,client)
    perception.CLIENT_HEARS = client == 'openai'  # Claude and unknown hosts take no audio blocks: measurements instead
    from . import __version__
    out['server']={'version':__version__,'tools':len(TOOL_REGISTRY)}  # a stale client connection shows fewer tools than this
    return out


@mcp.tool(annotations=READ)
def editvideo_beat_map(project_id: str, offset: int = 0, limit: int = 20, strips: bool = False):
    """Sentence-level shots, text lag, events, rhythm and motifs. Lexical/timing clues, not semantics. strips=true adds start/middle/end pictures for <=8 sentences, using a matching render or fresh snapshot."""
    from . import beatmap
    r = beatmap.beat_map(project_id, offset, limit, strips)
    if not r.get("strip"):
        return r
    return [TextContent(type='text', text=json.dumps(r, ensure_ascii=False)), Image(path=r["strip"]).to_image_content()]


@mcp.tool(annotations=READ)
def editvideo_discover_tools(query: str = '', offset: int = 0, limit: int = 8, include_schema: bool = False) -> dict[str,Any]:
    """Progressively discover actual tools from the live registry by Vietnamese/English intent/name;1..20/page. Return descriptions and optional exact input schemas so AI does not invent parameters. Works in compact and full modes. Literal normalized term ranking, not an embedding accuracy claim. Avoid loading every tool/schema if a narrow route answers the task."""
    return agent_interface.discover(TOOL_REGISTRY,query,offset,limit,include_schema)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=False,openWorldHint=True),structured_output=False)
async def editvideo_execute_tool(tool: str, arguments: dict) -> list:
    """Compact-host dispatch: run one discovered EditVideo tool with its exact schema (SDK validation), keeping image/audio blocks. Not a shell; unknown or recursive tool names are refused. Errors return type, message and recovery hints. Poll long tasks separately."""
    from mcp.types import CallToolResult
    if tool not in TOOL_REGISTRY or tool in ('editvideo_execute_tool','editvideo_discover_tools'):raise ValueError('Discover a callable EditVideo tool first')
    try:
        value=await TOOL_REGISTRY[tool].run(arguments,convert_result=True)
        # SDK conversion already retains Image/Audio/MCP content.
        if isinstance(value,tuple):value=value[0]
        return value if isinstance(value,list) else [TextContent(type='text',text=json.dumps(value,ensure_ascii=False,default=str))]
    except Exception as error:
        return CallToolResult(isError=True,content=[TextContent(type='text',text=json.dumps({'ok':False,'tool':tool,'error_type':type(error).__name__,'message':str(error)[:1800],
          'recover':'Check discovered schema; reread current revision/source SHA on conflicts, installed capability on missing model/provider, task error/log on failed media. No changes presumed successful.'},ensure_ascii=False))])


@mcp.tool(annotations=WRITE)
def editvideo_creative_brief(request: dict | None = None) -> dict[str,Any]:
    """Read schema or persist an AI-authored brief/script: audience,promise,payoff,tone,style,visual beats,sources and alternatives. No LLM call or semantic verification. Map beats to actual narration times before composing."""
    return agent_interface.creative_packet(request)


@mcp.tool(annotations=READ)
def editvideo_read_edit_context(project_id: str, start: float = 0, end: float = 8, layer_offset: int = 0, layer_limit: int = 20) -> dict[str,Any]:
    """Read <=15s edit context: revision/canvas, shots, paged layers, cues/audio, used assets, design and narration-to-source mappings. Window must fit locked plan. Inspect mapped pixels before interpreting content."""
    return agent_interface.edit_context(project_id,start,end,layer_offset,layer_limit)


@mcp.tool(annotations=READ)
def editvideo_audit_timeline(project_id: str, verbose: bool = False) -> dict[str, Any]:
    """Pre-render evidence: technique inventory, pacing/holds, text load/size/collisions/safe regions, transition repeats, hook checks, and 3D risks computed like the runtime (judder, magnified textures, plane borders, label collisions, haze, leak coverage). Findings: level, measurement, threshold, next step. Not a score; verify named frames with review_frames/snapshot_code."""
    from . import review
    r = review.audit_timeline(project_id)
    for row in r["scenes3d"]:
        row["camera"].pop("positions", None)
    if not verbose:  # lean: drop the shot table and collapse info-level findings to counts
        r.pop("shots", None)
        info = [f for f in r["findings"] if f["level"] == "info"]
        r["findings"] = [f for f in r["findings"] if f["level"] != "info"]
        r["info_counts"] = {c: sum(1 for f in info if f["code"] == c) for c in sorted({f["code"] for f in info})}
    return r


@mcp.tool(annotations=READ)
def editvideo_review_frames(project_id: str, frames: list[int], layer_ids: list[str] | None = None) -> list:
    """Glyph-level evidence on 1..4 frames via isolated renders: per text layer the glyph box, visible/covered fraction, same-as-background fraction, WCAG contrast against the real plate, safe-region overlap; overlay per frame (cyan visible, red covered, yellow < 3:1). Several renders: pass layer_ids (≤6) to focus."""
    from . import review
    r = review.review_frames(project_id, frames, layer_ids)
    lean = {"frames": [{"frame": f["frame"], "texts": [{k: v for k, v in x.items() if k not in ("text_rgb",)} for x in f["texts"]]} for f in r["frames"]],
            "method": r["method"]}
    content = [TextContent(type="text", text=json.dumps(lean, ensure_ascii=False))]
    content.append(Image(path=review.contact_sheet([f["overlay"] for f in r["frames"]], [f"review {f['frame']}" for f in r["frames"]])).to_image_content())
    return content


@mcp.tool(annotations=WRITE)
def editvideo_accent_sync(project_id: str, base_revision: int, style: Literal["velocity", "travel", "food", "product", "nature"] = "velocity",
                          music_path: str | None = None, drops: list[float] | None = None, start_frame: int = 0, end_frame: int | None = None,
                          sfx: bool = True, dry_run: bool = False, music_clip: str | None = None) -> dict[str, Any]:
    """Visual accents from the music's structure (music_clip: one cue's clip id), by genre: a drop (music-file seconds; default: loud peak entries) gets one stacked hit (white flash, decaying shake, RGB split + impact/riser), a phrase a flash or light leak, beats a zoom punch at most once per bar in energetic sections; on cut frames when close, 8+ frames apart; re-run replaces. nature places none."""
    from . import accents
    return accents.sync(project_id, base_revision, {"style": style, "music_path": music_path, "drops": drops, "start_frame": start_frame,
                                                    "end_frame": end_frame if end_frame is not None else 10 ** 9, "sfx": sfx, "dry_run": dry_run,
                                                    "music_clip": music_clip})


@mcp.tool(annotations=READ)
def editvideo_rank_clips(paths: list[str], window_s: float = 3.0, top: int = 12, match_cuts: bool = True, subject: str | None = None,
                         min_look: Literal["A", "B"] | None = None) -> list:
    """Rank windows across many clips for a multi-source edit: motion, sharpness, colour, one take, action peak (for ramps/accents) and direction (for whips); match_cuts pairs out/in by shape or motion; audio flags silent clips; subject ("rally car") ranks by its presence and size (find_subjects); min_look A/B passes over shaky, upscaled, noisy pictures. Windows + contact sheet; an aid, not taste."""
    from . import clips
    r = clips.rank(paths, window_s, top, match_cuts, subject, min_look)
    lab = {w["path"]: w["label"] for w in r["windows"]}  # labels in the rows, each absolute path once (it was 43% of the JSON)
    for w in r["windows"]:
        w.pop("path")
    for pair in r["match_cuts"]:
        for side in ("out", "in"):
            pair[side]["clip"] = lab.get(pair[side].pop("path"))
    r["paths"] = {v: k for k, v in lab.items()}
    content = [TextContent(type="text", text=json.dumps({k: v for k, v in r.items() if k != "sheet"}, ensure_ascii=False))]
    content.append(Image(path=r["sheet"]).to_image_content())
    return content


@mcp.tool(annotations=WRITE, structured_output=False)
def editvideo_find_subjects(paths: list[str], queries: list[str] | None = None, text: str | None = None, image: dict | None = None,
                            fps: float = 1.0, top: int = 10, allow_download: bool = False, frame_for: str | None = None) -> list:
    """What is in the footage, offline (OWLv2 + SigLIP, Apache-2.0; ~1.4 GB, installed once with allow_download after the user agrees). queries ["rally car","bird"]: per clip spans, share, best {at,score,box,area}; best.box seeds track_subject; frame_for a profile adds shot framing keeping it whole. text, or image {path,at}: windows ranked by similarity (scores relative within the query). Returns a sheet. Presence, not meaning: a hand is a person; no actions, relations or identity."""
    from . import semantic
    if allow_download:
        semantic.install(True)
    from .clips import _labels
    def labels(keys):  # the part of each name that tells clips apart; a folder or a number when names repeat
        lab, seen = _labels(list(keys)), {}
        for k in keys:
            n = seen[lab[k]] = seen.get(lab[k], 0) + 1
            lab[k] = lab[k] if n == 1 else f"{lab[k]}#{n}"
        return lab
    if queries:
        r = semantic.detect(paths, queries, fps)
        lab = labels(r["clips"])
        cap = lambda v: {**{x: v[x] for x in ("share", "best") if x in v}, "spans": v["spans"][:8], **({"spans_total": len(v["spans"])} if len(v["spans"]) > 8 else {})}
        out = {"clips": {lab[k]: {q: cap(v) for q, v in per.items()} for k, per in r["clips"].items()},
               "paths": {v: k for k, v in lab.items()}, "method": r["method"]}
        if frame_for:
            from .models import PROFILES
            from .media import display_size
            cw, ch = PROFILES[frame_for]
            for k, per in r["clips"].items():
                sw, sh = display_size(k)
                for q, d in per.items():
                    if d.get("track"):  # the union over the clip: the subject stays whole wherever it moves
                        bs = [b for _, b in d["track"]]
                        u = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
                        out["clips"][lab[k]][q]["framing"] = semantic.frame_subject(u, sw, sh, cw, ch)
    else:
        r = semantic.search(paths, text, image, top=top, fps=fps)
        lab = labels(dict.fromkeys(w["path"] for w in r["windows"]))
        out = {"windows": [{**{k: v for k, v in w.items() if k != "path"}, "clip": lab[w["path"]]} for w in r["windows"]],
               "paths": {v: k for k, v in lab.items()}, "method": r["method"]}
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False)), Image(path=r["sheet"]).to_image_content()]


@mcp.tool(annotations=READ)
def editvideo_shortform_audit(path: str | None = None, project_id: str | None = None, platform: Literal["tiktok", "reels", "shorts"] = "tiktok",
                              goal: Literal["organic", "ad"] = "organic", key_layer: str | None = None, cta_layer: str | None = None) -> list:
    """Audit a rendered 9:16 short (any MP4; project_id adds timeline checks or uses its last final render): first frame/change, cut pace, stills, bars, loudness, delivery spec, UI-covered text, first text/key message, caption coverage/sync, contrast, CTA. Findings cite evidence grades. Returns cover candidates and 5 frames with the platform UI drawn over."""
    from . import shortform
    r = shortform.audit(path, project_id, platform, goal, key_layer, cta_layer)
    content = [TextContent(type="text", text=json.dumps({k: v for k, v in r.items() if k != "ui_sheet"}, ensure_ascii=False))]
    content.append(Image(path=r["ui_sheet"]).to_image_content())
    return content


@mcp.tool(annotations=READ)
def editvideo_motion_audit(path: str, start: float = 0, end: float | None = None, project_id: str | None = None, series: bool = False,
                           gates: bool = False) -> dict[str, Any]:
    """Read an encoded video (render/preview/source) for felt motion: near-static spans, duplicated frames (24/25p cadence, missed frames), judder, brightness jumps; with project_id per-shot motion energy and calm shots. Low-passed (grain ignored). gates=true adds delivery gates: legal levels, flashes, banding, stills, blacks, text contrast/holds. Measurements with thresholds, not a verdict."""
    from . import agent, review
    r = review.motion_audit(path, start, end, project_id)
    if not series:  # per-frame series cost tokens; findings + per-shot speed are usually enough
        r.pop("diff_series", None)
        r.pop("speed_series", None)
    if gates:  # the gates read the whole file; with the project, text holds and contrast are read from its timeline
        r["delivery_gates"] = review.delivery_gates(path, agent.read(project_id)["timeline"] if project_id else None)
    return r


@mcp.tool(annotations=READ)
def editvideo_cinematic_catalog(query: str = "", project_id: str | None = None) -> dict[str, Any]:
    """Thinking material for treatment design: directing principles plus a technique atlas — viewer purpose, use/avoid, needs, recipe/tool, parameters that held up in renders, failure modes and how to verify; readiness against the library/project. Choose one hero technique per film that carries its idea."""
    from . import cinematic
    return cinematic.catalog(query, project_id)


@mcp.tool(annotations=WRITE)
def editvideo_compose_cinematic(project_id: str, base_revision: int, request: dict, dry_run: bool = False) -> dict[str, Any]:
    'Compile an exact cinematic recipe into editable layers. dry_run returns ops plus touched findings. Catalog/workbench supplies recipe fields: titles, maps, chapters, sourced figures/documents, news montage, night log, credibility gap and depth/3D treatments.'
    from . import cinematic
    r = cinematic.compose(project_id, base_revision, request, dry_run)
    return _read_only_ops(r) if dry_run else r


def _read_only_ops(r):
    """A dry run's ops for reading, not applying: long SVG element lists and keyframe tracks summarised (a map_matte
    dry run returned 140 KB, most of it map paths and camera keys). Compose without dry_run to apply."""
    import json as _json
    from collections import Counter
    out = []
    for op in r.get("ops") or []:
        lay = op.get("layer")
        if not isinstance(lay, dict):
            out.append(op)
            continue
        lay = dict(lay)
        d = lay.get("data")
        if isinstance(d, dict) and isinstance(d.get("elements"), list) and len(_json.dumps(d["elements"])) > 600:
            lay["data"] = {**{k: v for k, v in d.items() if k != "elements"},
                           "elements": {"count": len(d["elements"]), "types": dict(Counter(e.get("type") for e in d["elements"] if isinstance(e, dict)))}}
        kf = lay.get("keyframes")
        if isinstance(kf, dict) and any(isinstance(v, list) and len(v) > 6 for v in kf.values()):
            lay["keyframes"] = {k: ({"keys": len(v), "first": v[0], "last": v[-1]} if isinstance(v, list) and len(v) > 6 else v) for k, v in kf.items()}
        out.append({**op, "layer": lay})
    if "ops" in r:
        r = {**r, "ops": out, "ops_note": "summarised for reading; compose without dry_run to apply"}
    return r


@mcp.tool(annotations=WRITE)
def editvideo_sfx_sync(project_id: str, base_revision: int, request: dict | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Place procedural accents on picture events with the right anchor: whoosh peaking mid-transition, crunch on glitch cuts, pop on graphic entrances, plus hits [{frame, kind}] (impact/sub_drop start on it; riser/reverse_cymbal/suck_out end on it). Density limits, seed variants, one import per sound, editable clips sfx-NNN-kind (replace=true). dry_run lists the plan."""
    from . import audiofx
    return audiofx.sync(project_id, base_revision, request or {}, dry_run)


@mcp.tool(annotations=READ)
def editvideo_audit_audio(project_id: str | None = None, path: str | None = None) -> dict[str, Any]:
    """Audio audit. project_id: accent density, a sample repeated within 10 s, risers that do not resolve on a cut or hit, a weak sound or short gap 30-500 ms before a hit (dampens the startle). Rendered path: integrated loudness, range, true peak (> -1 dBFS flagged), dead air (< -45 LUFS for 0.5 s). Targets: speech ~-16 LUFS; music 10-18 dB and ambience 20-30 dB under speech."""
    from . import audiofx
    return audiofx.audit(project_id, path)


@mcp.tool(annotations=WRITE)
def editvideo_study_video(path: str, subtitles: str | None = None, sheet_frames: int = 30, strips: list[list[float]] | None = None, beats: bool = True) -> list:
    """Study local reference: rhythm, look, caption technique mentions, music/cut alignment, text/UI, transitions. Returns study_id, report path, one overview; strips add 8 frames/window (<=60s). Mentions need visual inspection; no download."""
    from . import study
    r = study.study_video(path, subtitles, sheet_frames, strips, beats)
    blocks = [TextContent(type="text", text=json.dumps(r, ensure_ascii=False))]
    for p in [r.get("sheet"), *(r.get("strips") or [])]:
        if p:
            blocks.append(Image(path=p).to_image_content())
    return blocks


@mcp.tool(annotations=READ)
def editvideo_learning_library(query: str = "", kind: Literal["all", "study", "lesson"] = "all", offset: int = 0,
                               limit: int = 5, item_id: str | None = None, include_retired: bool = False,
                               view: Literal["card", "segments", "candidates"] = "card") -> dict[str, Any]:
    """Recall studies and craft lessons (VI/EN) with timecoded windows, lesson levels and uses. item_id reads one; view=candidates: windows to distill (no item_id: undistilled studies). Lexical."""
    from . import learning
    return learning.library(query, kind, offset, limit, item_id, include_retired, view)


@mcp.tool(annotations=WRITE)
def editvideo_learn(action: Literal["", "register", "signals", "anatomy", "evidence", "compare", "distill", "conform", "apply", "library"] = "",
                    request: dict | None = None) -> list:
    """Learn from successful finished work of any kind (video/image/audio/web/text) behind evidence gates. Empty action: contract."""
    from learnkit import api
    from . import learn_video
    learn_video.install()
    r = api.learn(action, request)
    blocks = [TextContent(type="text", text=json.dumps(r, ensure_ascii=False))]
    if action == "evidence":
        from pathlib import Path
        for x in r.get("items", [])[:8]:
            if x.get("type") == "image":
                blocks.append(Image(path=x["path"]).to_image_content())
            elif x.get("type") == "audio":  # a clip to listen to, not a path to guess from
                blocks.append(AudioContent(type="audio", data=base64.b64encode(Path(x["path"]).read_bytes()).decode(), mimeType="audio/wav"))
    return blocks


@mcp.tool(annotations=WRITE)
def editvideo_remember_lesson(request: dict | None = None, lesson_id: str | None = None, base_revision: int | None = None,
                              outcome: dict | None = None) -> dict[str, Any]:
    """Save a craft card (own words) or log a use. No args: schema+level gates. request={title,principle,when_to_use,avoid,steps,tags,sources,parameters?,examples?,check?,level?}; edit: lesson_id+base_revision. lesson_id+outcome={project_id,revision,kept,note,job_id} logs a rendered use. Examples never run."""
    from . import learning
    return learning.remember(request, lesson_id, base_revision, TOOL_REGISTRY, outcome)


@mcp.tool(annotations=WRITE)
def editvideo_sequence_plan(request: dict | None = None, plan_id: str | None = None, build: bool = False) -> dict[str, Any]:
    """Short-form multi-source selects under a duration budget. No args: schema. AI supplies beats/windows/relevance; bounded search saves a plan. plan_id+build creates a NEW editable project with source audio. No automatic semantics or retention prediction."""
    from . import sequence
    return sequence.run(request, plan_id, build)


@mcp.tool(annotations=WRITE)
def editvideo_film_world(request: dict | None = None, world_id: str | None = None, base_revision: int | None = None,
                        shot_id: str | None = None, detail: bool = False, offset: int = 0, limit: int = 12) -> dict[str, Any]:
    """Film continuity memory: no args gives schema; save entities/shots/state, update with revision. Paged shots; shot_id returns state and a validated generate_footage packet. detail reads full world. No model call, identity lock or layout guarantee."""
    from . import film_world
    return film_world.run(request, world_id, base_revision, shot_id, detail, offset, limit)


@mcp.tool(annotations=READ)
def editvideo_explainer_catalog() -> dict[str, Any]:
    """Science-explainer recipes (measure, diagram, unit_grid, plot, annotate, chips, number_wall, hud_card, stat_line, particles): purpose and request fields, plus the runtime features they use (inline **strong**/==accent== text, grouped/rolling counters, particle modes, svg arrows and ripples, speed_lines/flare film layers). Read docs/EXPLAINER_KIT.md for craft guidance."""
    from . import explainer
    return explainer.catalog()


@mcp.tool(annotations=WRITE)
def editvideo_compose_explainer(project_id: str, base_revision: int, request: dict, dry_run: bool = False) -> dict[str, Any]:
    """One explainer recipe into layers (identical in both engines): measure, diagram, unit_grid, plot, annotate, chips, number_wall, hud_card, stat_line, particles, camera_stage (log-zoom), pie, columns, text_window_zoom, doc_timecard, motif_progress, evidence_3d. request={recipe,id,start_frame,end_frame,...}; fields in explainer_catalog; dry_run returns layers + audit. Snapshot inspect_frames."""
    from . import explainer
    return explainer.compose(project_id, base_revision, request, dry_run)


@mcp.tool(annotations=READ)
def editvideo_color_match(path: str, times: list[float], reference: str | None = None, reference_times: list[float] | None = None, strength: float = 1) -> dict[str, Any]:
    """Balance a shot (no reference: neutral mids, black ~2 %, white ~90 %) or match it to a reference shot: per-channel gain/offset from channel percentiles, a 5-point luma curve, saturation from the chroma ratio and a skin secondary when skin hues differ. Returns a grade for process_color plus before/after/target readouts and residuals measured by applying it (no images). 1..6 sample times per shot."""
    from . import color_match
    return color_match.match(path, times, reference, reference_times, strength)


@mcp.tool(annotations=READ)
def editvideo_color_consistency(project_id: str, samples: int = 3, groups: list[list[str]] | None = None) -> dict[str, Any]:
    """Timeline colour audit: samples each picture shot and flags exposure (mid ±6 pts), black point (±2), white-balance cast (> 2 % chroma), saturation (ratio outside .85-1.15) and skin-hue (±8°) drift against the group median. groups = lists of shot ids per scene (default: all shots). Returns only flagged shots + medians."""
    from . import color_match
    return color_match.consistency(project_id, samples, 320, groups)


@mcp.tool(annotations=WRITE)
def editvideo_animate(project_id: str, base_revision: int, request: dict, dry_run: bool = False) -> dict[str, Any]:
    """Animate a layer by intent: request={layer_id, material: ui|stiff|rubber|soft, exaggerate, beats:[{verb: hop|drop|slide_to|turn|rock|pop|hit|enter|exit, at, height, to [dx,dy], deg, frames, side, anticipation}]}. Compiles anticipation, arcs, contact stretch, volume-preserving squash, bounce decay and settle into keyframes + track_mods."""
    from . import animation
    return animation.apply(project_id, base_revision, request, dry_run)


@mcp.tool(annotations=READ)
def editvideo_audio_profile(path: str, start: float = 0, end: float | None = None, compare_to: str | None = None) -> dict[str, Any]:
    """Ears for dialogue: noise floor (p5 of 20 ms RMS), speech level (p90), SNR, 50/60 Hz hum, band balance (low, mud, presence, air), sibilance index, clipped samples, LUFS/true peak. compare_to=another file returns only the deltas (after - before) with warnings (floor rose more than speech, sibilance up)."""
    from . import dialogue
    a = dialogue.profile(path, start, end)
    return dialogue.compare(dialogue.profile(compare_to), a) if compare_to else a


@mcp.tool(annotations=READ)
def editvideo_read_dialogue(path: str, start: float = 0, end: float | None = None, speakers: int | None = None) -> dict[str, Any]:
    """Who speaks when, compactly: speech regions from an adaptive floor, pause statistics (per minute, median, p90, max, silence share) against measured targets, speakers by pitch + spectral clustering (no identity; pass speakers=N when known), turns, and filler candidates (flat-pitch steady vowels). Full region/pause/filler lists go to manifest."""
    from . import dialogue
    return dialogue.read(path, start, end, speakers)


@mcp.tool(annotations=WRITE)
def editvideo_condense_dialogue(path: str, max_pause_s: float = .5, target_pause_s: float = .3, remove_fillers: bool = True, cover: Literal["none", "punch_in"] = "none",
                                punch_scale: float = 1.12, clean_preset: Literal["auto", "light", "medium", "strong"] | None = None, profile: Literal["vertical", "landscape", "square", "portrait45"] = "landscape",
                                title: str | None = None, dry_run: bool = True, windows: list[list[float]] | None = None, transcript: str | None = None) -> dict[str, Any]:
    """Tighten talking footage into a NEW project: pauses over max_pause_s become target_pause_s, fillers go, picture and sound cut together, optional punch_in jump-cut cover and cleanup. windows: ordered [start,end] selects kept in that order (cold open). transcript: transcribe manifest of path; words carry into the cut for word_captions. Returns time_map."""
    from . import dialogue
    return dialogue.condense(path, max_pause_s, target_pause_s, remove_fillers, cover, punch_scale, (.51, .31), profile, "remotion", title, clean_preset, dry_run,
                             windows=windows, transcript=transcript)


@mcp.tool(annotations=WRITE)
def editvideo_clean_dialogue(path: str, preset: Literal["auto", "light", "medium", "strong"] = "auto", start: float = 0, end: float | None = None) -> dict[str, Any]:
    """Measured dialogue cleanup: HPF, de-hum (if measured), denoise at the measured floor, mud cut, presence (<= +4 dB), de-ess, 2.5:1 compression, an expander if the floor rose. Returns the WAV and before/after deltas (floor, speech, SNR, hum, sibilance, bands); import as a dialogue clip or pass clean_preset to condense_dialogue."""
    from . import dialogue
    return dialogue.clean(path, preset, start, end)


@mcp.tool(annotations=READ)
def editvideo_ad_plan(duration_seconds: float, structure: Literal["hook_demo_offer_cta", "brand_promo"] = "hook_demo_offer_cta", music_path: str | None = None, bpm_range: list[float] | None = None) -> dict[str, Any]:
    """Short ad / promo structure with per-section required elements (hook by 3 s and first change by 2.6 s, product by 1-3 s, offer after a music drop, CTA card >= 2.5-3 s with logo and a ducked bed); with music_path section starts snap to beats. Measured on one commercial + two retention edits: starting points, not laws."""
    from . import ads
    return ads.plan(duration_seconds, structure, music_path, tuple(bpm_range) if bpm_range else None)


@mcp.tool(annotations=READ)
def editvideo_ad_audit(project_id: str, product_layers: list[str] | None = None, cta_layer: str | None = None, logo_layer: str | None = None, offer_layer: str | None = None,
                       platform: Literal["tiktok", "reels", "shorts"] | None = None) -> dict[str, Any]:
    """Audit a short ad/retention edit: brand at open and end, product by 3 s, CTA hold >= 2.5 s and last, offer before CTA, text density (<= 4 words/line, <= 7 on screen), visual events per minute (measured 10.8-14.7), first change by ~2.6 s, long holds, and platform UI zones for vertical. Findings + rates only."""
    from . import ads
    return ads.audit(project_id, None, product_layers, cta_layer, logo_layer, offer_layer, platform)


@mcp.tool(annotations=WRITE)
def editvideo_punch_in(project_id: str, base_revision: int, words: list[dict] | None = None, frames: list[int] | None = None, scale: float = 1.14,
                       anchor: list[float] | None = None, min_pause_s: float = .35, min_gap_s: float = 15, ladder: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Emphasis punch-ins as hard cuts (measured x1.14 about the eye line (.51,.31), on the first word after a pause >= 0.35 s, held to the next cut, ~0.5/min): pass word timings [{word,start,end}] in timeline seconds (transcribe/read_narration) or explicit frames. ladder=true alternates in/out for jump-cut talking edits. Splits shots and returns placed/skipped frames."""
    from . import ads
    return ads.punch_in(project_id, base_revision, words, frames, scale, tuple(anchor or (.51, .31)), min_pause_s, min_gap_s, ladder, dry_run)


@mcp.tool(annotations=READ)
def editvideo_event_profile(path: str, start: float = 0, end: float | None = None) -> dict[str, Any]:
    """Read an edit's visual pacing like a retention editor: every abrupt event classified as cut, punch_in/punch_out (with scale and fixed point) or overlay_pop (a graphic/text appearing), with per-minute rates, gap median/p90/max and punch scales. Works on references and on your own renders. Event list on disk."""
    from . import study
    return study.event_profile(path, start, end)


@mcp.tool(annotations=READ)
def editvideo_motion_quality(project_id: str, layer_ids: list[str] | None = None) -> dict[str, Any]:
    """Animation audit sampled from the shared runtime (what both engines draw): mechanical (linear) moves, abrupt stops without overshoot, straight paths for organic moves, squash that changes area, twin layers moving identically. Findings + one line per layer."""
    from . import motion_quality
    return motion_quality.audit(project_id, layer_ids)


@mcp.tool(annotations=WRITE)
def editvideo_compose_product(project_id: str, base_revision: int, start_frame: int, end_frame: int, model: str | None = None, primitive: Literal["cylinder", "box", "sphere", "capsule"] = "cylinder",
                              texture: str | None = None, color: str = "#d8d2c4", id: str = "product", x: float = 0, y: float = 0, width: float = 1, height: float = 1,
                              turn_deg_per_s: float = 40, sweep: bool = True, light: float = 1.0, ground: bool = True, studio: bool = True, bloom: bool = True,
                              size: float | None = None, reveal: Literal["slide", "dark"] = "slide", reveal_at: int | None = None) -> dict[str, Any]:
    """3D product shot (Scene3D layer). slide: slide in, rock-and-settle, turntable, highlight sweep, slow push. dark: from black, a rim light rises, key light lands at reveal_at (frame), slow orbit and push. Camera fits size. model = .glb asset id, or a primitive with a texture. light scales all lights (metallic glTF .3-.5); studio adds reflections. Returns beats, inspect frames."""
    from . import scene3d
    if size is not None and not .2 <= size <= 20:
        raise ValueError("size is the product's largest dimension, .2..20 scene units")
    dims = None if size is None else ([size, 1, 1] if model else [size * .55, size, size * .55] if primitive in ("cylinder", "capsule") else [size] * 3)
    t = agent.read(project_id)["timeline"]
    aspect = width * t["width"] / max(1e-6, height * t["height"])  # the layer's shape on the canvas
    scene, beats = scene3d.product_scene(end_frame - start_frame, model, primitive, texture, color, dims, "#0e0f12", "#ffffff", 40, 5.0, turn_deg_per_s, sweep,
                                         True, bloom, light, ground, studio, reveal, reveal_at, aspect)
    r = scene3d.compose(project_id, base_revision, {"id": id, "scene": scene, "start_frame": start_frame, "end_frame": end_frame, "x": x, "y": y, "width": width, "height": height})
    key = beats["reveal"] + 12 if reveal == "dark" else beats["rock_settle"][1]
    return {"revision": r["revision"], "layer": id, "beats": beats, "inspect_frames": [start_frame + 20, start_frame + key, start_frame + (beats["light_sweep"] or [0, 0])[0] + 20, end_frame - 1]}


@mcp.tool(annotations=WRITE)
def editvideo_pin_to_track(project_id: str, base_revision: int, track: str | dict, shot_id: str, layer_ids: list[str], dry_run: bool = False) -> dict[str, Any]:
    """Pin labels/marks to a track_region result (manifest path or dict): x/y keyframes mapped through the shot (offset, rate, fit/focus, zoom). Place each layer at its first tracked frame; translation only."""
    from . import pin
    return pin.pin_to_track(project_id, base_revision, track, shot_id, layer_ids, dry_run)


@mcp.tool(annotations=WRITE)
def editvideo_tracked_window(project_id: str, base_revision: int, track: str | dict, start_frame: int, mode: Literal["color", "blur", "spotlight"] = "color",
                             shape: Literal["ellipse", "rect"] = "ellipse", pad: float = .15, feather_px: float = 40, adjust: dict | None = None,
                             layer_id: str = "window", source_box: list[float] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Power window that follows a track: an adjust layer whose feathered mask rides a track_region result or a track_plane track_id. mode color (gentle exposure/saturation lift inside; override with adjust {exposure, saturation, temperature, ...}), blur (anonymise a face/plate/screen), spotlight (darken + desaturate outside). start_frame = timeline frame of the track's first sample; source_box = where the tracked clip sits in the frame."""
    from . import windows
    return windows.tracked_window(project_id, base_revision, track, start_frame, mode, shape, pad, feather_px, adjust, layer_id, tuple(source_box or (0, 0, 1, 1)), dry_run)


@mcp.tool(annotations=WRITE)
def editvideo_multicam(angles: list[dict], master: str | None = None, speakers: int | None = None, profile: Literal["vertical", "landscape", "square", "portrait45"] = "landscape",
                       title: str | None = None, dry_run: bool = True, turn_lead_frames: int = 12, min_shot_frames: int = 75) -> dict[str, Any]:
    """Multicam interview/podcast edit: angles=[{path, kind: wide|single, speaker?}]. Syncs angles to the master audio, maps speakers to angles, switches with measured rules (cut ~12 frames before a turn, ignore backchannels, wide for crosstalk, shots >= 2.5 s, listener reactions in long monologues). dry_run: offsets, mapping, shot stats; apply: new project over the master audio."""
    from . import multicam
    return multicam.build(angles, master, speakers, profile, "remotion", title, dry_run, lead=turn_lead_frames, min_shot=min_shot_frames)


@mcp.tool(annotations=WRITE)
def editvideo_adapt_aspect(project_id: str, profile: Literal["vertical", "landscape", "square", "portrait45"], title: str | None = None) -> dict[str, Any]:
    """Clone a project to another canvas (9:16, 4:5 = portrait45, 1:1, 16:9): shots cover at their focus point, layers keep relative placement in the target safe area, type scales by the short side and shrinks to fit its longest word, pixel keyframes scale per axis. Returns the new id, clamped layers and serious findings; snapshot before rendering."""
    from . import aspect
    return aspect.adapt(project_id, profile, title)


@mcp.tool(annotations=READ)
def editvideo_title_catalog() -> dict[str, Any]:
    """Title recipes and measured presets: title_card (impact, minimal_wide, atmospheric, two_tone, integrated), type_lockup (poster stack / credit), word_cards (one-word cards on hits), sound_first (hit on black, picture later), plus the readability rules."""
    from . import titles
    return titles.catalog()


@mcp.tool(annotations=WRITE)
def editvideo_compose_title(project_id: str, base_revision: int, request: dict, dry_run: bool = False) -> dict[str, Any]:
    """Compile one title recipe into layers (font_id/font_weight, tracking in em, full-frame plates; identical in both engines): request={'recipe': title_card|type_lockup|word_cards|sound_first, 'id', ...}; fields: title_catalog. Sizes from FreeType metrics so caps centre and fit. dry_run returns layers + audit; snapshot inspect_frames."""
    from . import titles
    return titles.compose(project_id, base_revision, request, dry_run)


@mcp.tool(annotations=READ)
def editvideo_trailer_plan(duration_seconds: float, music_path: str | None = None, bpm_range: list[float] | None = None, bumper: bool = True, logos: bool = True) -> dict[str, Any]:
    """Trailer structure from measured practice: bumper, cold open 8-15 s, logos, three acts (median shot ~0.73/0.65/1.0 s), title on the last hit (~2.3 s), 5-10 s button. With music_path acts move to section entries/hits, the title to the strongest hit, dips to real quiet gaps."""
    from . import trailer
    return trailer.plan(duration_seconds, music_path, tuple(bpm_range) if bpm_range else None, bumper, logos)


@mcp.tool(annotations=READ)
def editvideo_trailer_audit(project_id: str, sections: list[dict], music_path: str | None = None, title_layer: str | None = None, bpm_range: list[float] | None = None,
                            music_start: float = 0, timeline_offset_frames: int = 0) -> dict[str, Any]:
    """Audit a trailer cut against measured practice: per-act median shot length, acceleration into act 2, a climax burst, title hold, button, dialogue per act; with music_path: act changes and title on a hit (±2 f), a cut per act change, a dip before the climax, ≥6 s loud climax. sections from trailer_plan or [{section,start_frame,end_frame}]."""
    from . import trailer
    return trailer.audit(project_id, sections, music_path, title_layer, tuple(bpm_range) if bpm_range else None, music_start, timeline_offset_frames)


@mcp.tool(annotations=READ)
def editvideo_resources(query: str = "", kind: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Search the local resource library (textures, models, geodata, footage, images, LUTs) with licence, credit, source page, resolution and notes. Absolute paths are importable with import_media. Run seed via register_resource(seed=true) once if empty."""
    from . import resources
    if not resources.CATALOG.exists():
        resources.seed_library()
    return resources.library(query, kind, limit)


@mcp.tool(annotations=WRITE)
def editvideo_register_resource(path: str = "", kind: str = "image", title: str = "", license: str = "", credit: str = "", source_url: str = "", tags: str = "", notes: str = "", derived_from: str | None = None, seed: bool = False) -> dict[str, Any]:
    """Record a local file in the library with licence and credit (use 'unknown' honestly when not established), or derived_from=<library id> for a resized/cropped/graded copy that inherits the source licence. seed=true registers known files already under data/sources (NASA, Natural Earth, Commons credits.jsonl)."""
    from . import resources
    if seed:
        return resources.seed_library()
    if derived_from:
        return resources.register_derived(path, derived_from, kind or None, notes)
    return resources.register_resource(path, kind, title, license, credit, source_url, tags, notes)


@mcp.tool(annotations=READ)
def editvideo_geo(name: str, cities: list[dict] | None = None, neighbors: list[str] | None = None, islands: bool = True, outline_only: bool = False, max_points: int = 480) -> dict[str, Any]:
    """Country geography from Natural Earth (public domain): outline_only → [lon, lat] rings for compose_globe outlines; otherwise an SVG-ready map (view_box, path d per country, projected city points from [{name, lat, lon}]) for svg layers or map_journey. English ADMIN name or ISO_A3."""
    from . import resources
    if outline_only:
        return resources.geo_outline(name, max_points, islands)
    return resources.geo_map(name, cities or [], 1000, islands, neighbors or [])


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def editvideo_find_sources(query: str, provider: Literal["wikimedia", "nasa"] = "wikimedia", media: Literal["image", "video", "audio"] = "image", limit: int = 10) -> dict[str, Any]:
    """Search open media providers (Wikimedia Commons, NASA Image and Video Library) and return candidates with licence, author, size, resolution/duration, thumbnail and source page. Nothing is downloaded. Show the user the exact file, source, licence and size and get explicit approval before fetch_source. For NASA items call source_files(asset_manifest) to choose a rendition."""
    from . import resources
    return resources.find_sources(query, provider, media, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def editvideo_source_files(asset_manifest: str) -> dict[str, Any]:
    """List downloadable renditions (URL and byte size when the server reports it) of a NASA library item from find_sources."""
    from . import resources
    return resources.nasa_files(asset_manifest)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def editvideo_fetch_source(url: str, provider: Literal["wikimedia", "nasa", "naturalearth", "other"], title: str, license: str, credit: str, source_page: str, kind: str, file_name: str | None = None, expected_bytes: int | None = None, tags: str = "") -> dict[str, Any]:
    """Download ONE file the user has explicitly approved in this conversation (state file name, source page, licence and size first; approval does not carry over to other files). Stores under data/sources/<provider>/, refuses size mismatches with expected_bytes and files over 600 MB, and registers licence/credit in the library and credits.jsonl."""
    from . import resources
    return resources.fetch_source(url, provider, title, license, credit, source_page, kind, file_name, expected_bytes, tags)


@mcp.tool(annotations=READ)
def editvideo_project_credits(project_id: str) -> dict[str, Any]:
    """Compile credits for every asset the timeline uses by following provenance (imports, retime/colour/subject/depth tasks, copies between projects) back to library records. Returns grouped credit lines, a ready text line, the trace per asset and unrecorded assets that need register_resource or a question — never invent a credit."""
    from . import resources
    return resources.project_credits(project_id)


@mcp.tool(annotations=READ)
def editvideo_style_directions(query: str = "", energy: Literal["calm", "medium", "high"] | None = None) -> dict[str, Any]:
    """20 creative directions (documentary, travel, premium product, tech launch, editorial, Swiss minimal, kinetic hype, data journalism, flat explainer, retro VHS, CRT, noir, nature calm, corporate, code tutorial, collage zine, action trailer, luxury fashion, kids, breaking news), each with look, motion language, pacing, transitions, titles, finish and a negative list. Pick, then apply_direction."""
    from . import directions
    return directions.catalog(query, energy)


@mcp.tool(annotations=WRITE)
def editvideo_apply_direction(project_id: str, base_revision: int, direction_id: str, overrides: dict | None = None, restyle: bool = False, finish: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Apply a creative direction: design tokens plus design.direction (recipes and audit follow it). restyle=true retimes entrances/exits to its motion language, staggers simultaneous entrances, adds idle to hero titles; finish=true adds its grain/looks and leaks on accent transitions. Returns per-seam guidance. overrides patch any section."""
    from . import directions
    return directions.apply(project_id, base_revision, direction_id, overrides, restyle, finish, dry_run)


@mcp.tool(annotations=READ)
def editvideo_beat_track(path: str, start: float = 0, end: float | None = None, bpm_range: list[float] | None = None) -> dict[str, Any]:
    """Music tempo (BPM), beat and downbeat times from an audio/video file. Beat times are calibrated to the attack (±2 ms on click tracks); pulse clear/moderate/weak from periodicity. Half/double time is common: check bpm against the music and pin it with bpm_range [low, high]."""
    from . import music
    return music.beats(path, start, end, tuple(bpm_range) if bpm_range else None)


@mcp.tool(annotations=READ)
def editvideo_music_structure(path: str, start: float = 0, end: float | None = None, bpm_range: list[float] | None = None, detail: Literal["summary", "full"] = "summary") -> dict[str, Any]:
    """Read a track like an editor: beats with bar position, bars, 4/8-bar phrases, sections (intro/build/peak/breakdown/body/outro), hits (>=15 dB jumps), quiet gaps, pulse strength and the snap mode to use (weak pulse: hits and section entries, not beats). detail=summary writes every beat to full_path. Listen to boundaries before relying on labels."""
    from . import music
    st = music.structure(path, start, end, tuple(bpm_range) if bpm_range else None)
    if detail == "full":
        return st
    full = store.DATA / "cache" / "music" / f"structure-{music._cache_key(path, start, end, tuple(bpm_range) if bpm_range else None)}.json"
    store.write_json(full, st)
    return music.summary(st, full)


@mcp.tool(annotations=WRITE)
def editvideo_music_fit(path: str, target_seconds: float, ending: Literal["natural", "fade", "hit"] = "natural", start: float = 0, end: float | None = None,
                        crossfade_beats: float = .5, bpm_range: list[float] | None = None, project_id: str | None = None, base_revision: int | None = None,
                        asset_id: str | None = None, timeline_start_frame: int = 0, volume: float = .5, dry_run: bool = True,
                        max_joins: int = 1, exact: bool = False, duck_lu: float | None = None) -> dict[str, Any]:
    """Fit music to a length: drop/repeat whole bars between similar bar lines (max_joins>1: joins a phrase apart), crossfaded; ending natural|fade|hit; exact: <=3% tempo hits the frame. Join cost <1 usually seamless. dry_run=false + project_id/base_revision/asset_id writes clips; duck_lu: LU under each narration phrase."""
    from . import music
    plan = music.fit(path, target_seconds, start, end, ending, crossfade_beats, tuple(bpm_range) if bpm_range else None, max(1, min(8, max_joins)), exact)
    if not dry_run:
        if not (project_id and base_revision is not None and asset_id):
            raise ValueError("Pass project_id, base_revision and asset_id to place the edit")
        plan["placed"] = music.apply_fit(project_id, base_revision, asset_id, plan, timeline_start_frame, volume)
        if duck_lu is not None:  # measured ducking replaces the sidechain on these clips; the placed revision stands if it fails
            try:
                plan["ducked"] = music.apply_duck(project_id, plan["placed"]["revision"], "music-fit", max(6.0, min(24.0, duck_lu)))
            except ValueError as e:
                plan["duck_error"] = str(e)
    return plan


@mcp.tool(annotations=READ)
def editvideo_cut_alignment(path: str, cuts: list[float], start: float = 0, end: float | None = None, bpm_range: list[float] | None = None) -> dict[str, Any]:
    """How an edit sits on its music (reference study or self-check): per 30 s window, each cut's signed offset to the nearest beat in frames and its position in the bar; the editor's habitual lead (peak of the offset histogram), on-beat share against chance, and the downbeat share. cuts are seconds in the same file (from study_video or index_video)."""
    from . import music
    return music.cut_alignment(path, cuts, start, end, bpm_range=tuple(bpm_range) if bpm_range else None)


@mcp.tool(annotations=WRITE)
def editvideo_snap_cuts_to_beats(project_id: str, base_revision: int, music_path: str | None = None, beat_times: list[float] | None = None,
                                 use: Literal["beats", "downbeats", "priority", "hits", "phrases", "against"] = "beats", tolerance_frames: int = 6,
                                 lead_frames: int = 2, music_start: float = 0, timeline_offset_frames: int = 0, dry_run: bool = False,
                                 protect: list[list[int]] | None = None, bpm_range: list[float] | None = None) -> dict[str, Any]:
    """Move shot boundaries onto the music (lead_frames early, default 2) within tolerance. use: beats | downbeats | priority (downbeat > beat 3 > others) | hits (weak-pulse beds) | phrases | against (off-beats). protect: dialogue frame ranges that never move. Reports section entries without a cut. Each move is a revision-protected patch."""
    from . import music
    return music.snap_cuts(project_id, base_revision, music_path, beat_times, use, tolerance_frames, lead_frames, music_start, timeline_offset_frames, dry_run,
                           protect, tuple(bpm_range) if bpm_range else None)


@mcp.tool(annotations=READ)
def editvideo_cut_audit(path: str, project_id: str, start: float = 0) -> list:
    """Editing-craft evidence on a render: per cut the focal point before/after, eye-trace jump, motion around it (cut on action), shot-length rhythm, with a contact sheet of cut pairs. Heuristic (Murch's eye-trace and rhythm); story ranks first."""
    from . import review
    r = review.cut_audit(path, project_id, start)
    content = [TextContent(type="text", text=json.dumps(r, ensure_ascii=False))]
    if r.get("contact_sheet"):
        content.append(Image(path=r["contact_sheet"]).to_image_content())
    return content


@mcp.tool(annotations=WRITE)
def editvideo_stabilize_footage(request: dict) -> dict[str, Any]:
    """Durable stabilization task (≤60 s): KLT camera path, smoothed (mode smooth) or locked (mode lock, drift-free), with the smallest zoom hiding borders (max_zoom). region [l,t,r,b]: a RIGID part (not water, screens, people). Reports residual motion on the output; attach_media_result, inspect edges and wobble."""
    return media_tasks.submit('stabilize', request)


@mcp.tool(annotations=WRITE)
def editvideo_reframe_footage(request: dict) -> dict[str, Any]:
    """Durable subject-aware reframe task (≤120 s): crop to a new aspect (e.g. 9:16 from 16:9) following tracked focus points [{t,x,y}] from track_subject/track_region, or automatic focus (saliency+motion, or auto_focus faces: the main face, for talking heads); a dead zone holds the camera until the subject leaves the centre. Keeps source audio. Pass tracked points for products; automatic focus can pick the wrong object."""
    return media_tasks.submit('reframe', request)


@mcp.tool(annotations=WRITE)
def editvideo_storyboard(project_id: str, storyboard: dict | None = None, check: bool = False, render_path: str | None = None) -> dict[str, Any]:
    """Plan → validate → check a whole film. Pass storyboard {message, arc, audience, mood, direction_id, direction_block, frames[{id,start_s,end_s,type,beat,focal,reveals,technique}], callback} to save; check=true compares the timeline with it (gaps, missing reveals/techniques, negative-list hits, callback, breather calmest with render_path). No args: returns the saved plan."""
    from . import storyboard as sbm
    if storyboard is not None:
        return sbm.save(project_id, storyboard)
    if check:
        return sbm.check(project_id, render_path)
    return sbm.read(project_id)


@mcp.tool(annotations=READ)
def editvideo_workbench(project_id: str, start: float = 0, end: float = 8, purpose: str = "", recipe: str | None = None) -> dict[str, Any]:
    """Compact <=15s scene meaning, craft cards, frame requests and resource budget; recipe gives one schema. No model load. direct_scene adds real visual/audio evidence."""
    from .workbench import scene
    return scene(project_id, start, end, purpose, recipe)


@mcp.tool(annotations=WRITE)
def editvideo_bind_narrative(request: dict | None = None) -> dict[str, Any]:
    """Bind authored words, intent and sources to real shot/audio windows; schema if empty. Revision checked; stale timing rejected. No TTS or word timing invented."""
    from .narrative import BindNarrative,bind
    return {"schema":BindNarrative.model_json_schema()} if request is None else bind(request)


@mcp.tool(annotations=READ, structured_output=False)
def editvideo_direct_scene(project_id: str | None = None, start: float = 0, end: float = 10, request: dict | None = None,
                          inspect: bool = False, render_path: str | None = None, frames: int = 6, listen: bool = False) -> list:
    """Timed meaning + craft + optional real frames/audio; compile an editable scene plan. Empty: schema. Apply plan handle with patch_timeline. No model/API call or beauty score."""
    import math
    from . import directing,narrative
    if project_id is None:
        return [TextContent(type='text',text=json.dumps({'schema':directing.SceneDecision.model_json_schema(),
                'workflow':'bind_narrative -> direct_scene(inspect=true) -> choose a motivated technique -> direct_scene(request=...) -> patch_timeline(direction_plan=id) -> render and inspect moving output',
                'craft':directing.craft()},ensure_ascii=False))]
    p=agent.read(project_id);t=p.get('timeline')
    if not t or not all(math.isfinite(x) for x in (start,end)) or not 0<=start<end<=min(start+60,t['total_frames']/30) or not 2<=frames<=8:
        raise ValueError('Scene inside locked timeline, <=60s; frames2..8')
    meaning=narrative.context(project_id,t,start,end)
    result={'project_id':project_id,'revision':p['revision'],'window':[start,end],'meaning':meaning,
            'craft':directing.craft([b.get('role') for b in meaning['beats']])[:3],
            'inspect_frames':directing.sample_frames(t,start,end,frames),
            'limits':'AI interprets actual evidence and chooses direction. Craft patterns are suggestions; no semantic or aesthetic verdict is inferred.'}
    assets={a['id']:a for a in p['assets']};materials=[]
    for row in [*t['shots'],*t['layers']]:
        asset=assets.get(row.get('asset_id'))
        if not asset or row['start_frame']>=end*30 or row['end_frame']<=start*30:continue
        first=max(start*30,row['start_frame']);last=min(end*30,row['end_frame']);rate=row.get('playback_rate',1)
        static=bool(row.get('freeze')) or asset['kind']=='image'
        source_at=row.get('source_start',0)
        window=[source_at,source_at] if static else [source_at+(first-row['start_frame'])*rate/30,source_at+(last-row['start_frame'])*rate/30]
        materials.append({'id':row['id'],'asset_id':asset['id'],'name':asset.get('name','')[:100],
                          'kind':asset['kind'],'duration':asset.get('duration'),'role':asset.get('role'),
                          'source_window':window,'static_frame':static})
    result['materials']={'items':materials[:12],'total':len(materials),'next':'read_edit_context for additional exact mappings; names are metadata, inspect actual source pixels.'}
    from . import learning
    query=' '.join([meaning.get('message',''),*[b.get('visual_goal','') or b.get('purpose','') for b in meaning['beats']],
                    (request or {}).get('viewer_question',''),(request or {}).get('technique','')])
    try:
        result['related_lessons']={'items':learning.related_lessons(query),
              'next':'Read a related learning_library card and its timestamped reference before adapting it; retrieval is not proof of applying the lesson.'}
    except (OSError,ValueError,KeyError,TypeError):
        result['related_lessons']={'items':[],'warning':'Optional craft library unavailable; scene evidence remains usable.'}
    if request is not None:
        plan=directing.compile_scene(p,start,end,request)
        result['plan']={k:v for k,v in plan.items() if k not in ('operations','narrative','measurements')}
        result['plan']['operation_count']=len(plan['operations'])
        result['plan']['apply']={'tool':'editvideo_patch_timeline','arguments':{'project_id':project_id,'base_revision':p['revision'],'direction_plan':plan['id']}}
    extra=[]
    if inspect:
        reference=meaning.get('reference_render') or {}
        video=render_path or (reference.get('path') if reference.get('matches_current_picture') else None)
        if not video:raise ValueError('Supply render_path or bind a matching reference_render; stale pictures are not current evidence')
        width=(320 if frames>6 else 384) if t['width']<t['height'] else (480 if frames>6 else 640)
        e=directing.evidence(video,t,start,end,frames,width,listen)
        result['evidence']=e;extra.append(Image(path=e['sheet']).to_image_content())
        if e.get('audio'):
            from pathlib import Path
            extra.append(AudioContent(type='audio',mimeType='audio/wav',data=base64.b64encode(Path(e['audio']).read_bytes()).decode()))
    return [TextContent(type='text',text=json.dumps(result,ensure_ascii=False)),*extra]


@mcp.tool(annotations=WRITE)
def editvideo_finish_video(request: dict | None = None) -> dict[str, Any]:
    """Finish a verified base job: optional bounded layer-repair section, readable selectable subtitles, measured AAC peaks and ZIP. Empty: schema. Durable task; poll get_media_task. Originals retained, only changed picture rendered."""
    from .delivery import DeliveryRequest
    if request is None:
        return {"schema": DeliveryRequest.model_json_schema(), "workflow": "read revision -> patch layers -> submit verified base_job_id + caption_path + covering patch_frames if needed -> poll task; inspect final MP4/subtitles"}
    return media_tasks.submit('delivery', request)


@mcp.tool(annotations=WRITE)
def editvideo_render_3d(request: dict | None = None) -> dict[str, Any]:
    """Offline Blender terrain/globe templates as durable cached media tasks. Empty: exact contract. Supply prepared local textures/heights/camera; preview <=8 stills at percent25 before full render. No downloads or arbitrary scripts; poll and attach video."""
    from .render3d import contract
    return contract() if request is None else media_tasks.submit('blender', request)


@mcp.tool(annotations=READ)
def editvideo_storage_report() -> dict[str, Any]:
    """Disk use by area (sources, project assets, exported code, render jobs, evidence renders, bundle cache, media tasks, models), free space per drive, and orphaned records (projects in the database whose folders are gone). Lists what is temporary and safe to clear; it deletes nothing — clearing is the user's decision."""
    import shutil as _sh
    from pathlib import Path as _P
    def size(p):
        p = _P(p)
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    D = store.DATA
    areas = {"sources": D / "sources", "media_tasks": D / "media-tasks", "evidence_renders (temporary)": D / "observations", "bundle_cache (temporary)": D / "cache",
             "worker_tmp (temporary)": D / "tmp", "models": D / "models"}
    out = {k: round(size(v) / 1024**3, 2) for k, v in areas.items()}
    proj = {"assets": 0, "code": 0, "render_job_copies (temporary)": 0, "render_outputs": 0}
    orphans = []
    for p in store.list_projects():
        f = D / "projects" / p["id"]
        if not f.exists():
            orphans.append(p["id"])
            continue
        proj["assets"] += size(f / "assets")
        proj["code"] += size(f / "code")
        for j in (f / "jobs").glob("*") if (f / "jobs").exists() else []:
            proj["render_job_copies (temporary)"] += size(j / "source") + size(j / "engine-temp")
            proj["render_outputs"] += sum(x.stat().st_size for x in j.glob("*") if x.is_file())
    out.update({"projects_" + k: round(v / 1024**3, 2) for k, v in proj.items()})
    drives = {}
    for root in {_P(store.DATA).anchor, _P.home().anchor}:
        u = _sh.disk_usage(root)
        drives[root] = {"free_gb": round(u.free / 1024**3, 1), "total_gb": round(u.total / 1024**3, 1)}
    return {"gb_by_area": out, "drives": drives, "orphaned_projects": orphans,
            "note": "Media are hardlinked between sources, assets, exports, bundles and render copies, so per-area sizes overlap and the real total is lower. "
                    "Areas marked temporary can be cleared by the user; never clear sources, assets or outputs."}


@mcp.tool(annotations=WRITE)
def editvideo_package_source(job_id: str, include_media: bool = True) -> dict[str, Any]:
    """Build the portable source package for a finished render: delivery-full.zip with code, timeline and every media file (stored, not re-compressed). Renders already include a lean delivery.zip (code + timeline + media manifest with sha256 and credits); call this only when the project must move to another machine."""
    from .code_engine import package
    job = store.get_job(job_id)
    if job["state"] != "completed":
        raise ValueError("Job is not completed")
    work = store.folder(job["project_id"]) / "jobs" / job_id
    p = package(job["project_id"], work, work / "source", include_media)
    return {"path": str(p), "bytes": p.stat().st_size}


# ---------------------------------------------------------------- token economy for the calling AI
# FastMCP serialises dict results as indent=2 JSON *and* repeats them as structuredContent; floats carry 16 digits and
# input schemas repeat a "title" per property. For a model every character is context, so tool I/O is compacted at the
# protocol edge (in-process calls to editvideo_* functions are untouched): compact JSON, floats rounded to 4 decimals
# (0.0001 of a normalised coordinate is 0.2 px at 1920), no duplicate structured copy, schemas without titles and with
# `anyOf [X, null]` collapsed to X (the default stays visible, validation still uses the Python signature).
def _lean(o):
    if hasattr(o, 'item') and type(o).__module__ == 'numpy' and getattr(o, 'ndim', 1) == 0:
        o = o.item()  # numpy scalar → Python number/bool (default=str would print "0.5")
    if isinstance(o, float):
        if o != o or o in (float('inf'), float('-inf')):
            return None  # NaN/inf are not JSON
        return round(o, 4) if abs(o) < 1e4 else round(o, 1)
    if isinstance(o, dict):
        return {k: _lean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_lean(v) for v in o]
    return o


def compact_result(result):
    if isinstance(result, dict):
        return json.dumps(_lean(result), ensure_ascii=False, separators=(',', ':'), default=str)
    if isinstance(result, list):
        return [compact_result(x) if isinstance(x, dict) else x for x in result]
    return result


def _slim_schema(o):
    if isinstance(o, dict):
        o = {k: _slim_schema(v) for k, v in o.items() if not (k == 'title' and isinstance(v, str))}  # a property named title stays
        a = o.get('anyOf')
        if isinstance(a, list) and len(a) == 2 and {'type': 'null'} in a:
            other = next(x for x in a if x != {'type': 'null'})
            o.pop('anyOf')
            o.update(other)
            if 'default' in o and o['default'] is None:
                o.pop('default')  # optional stays optional (not in required); a null default on a non-null type misleads strict clients
        return o
    if isinstance(o, list):
        return [_slim_schema(v) for v in o]
    return o


def economize_tools():
    """EDITVIDEO_STRUCTURED=1 keeps MCP structuredContent for programmatic clients (text stays compact either way)."""
    import os
    keep_structured = os.environ.get('EDITVIDEO_STRUCTURED') == '1'
    for t in mcp._tool_manager._tools.values():
        if getattr(t, '_economized', False):
            continue
        t.parameters = _slim_schema(t.parameters)
        if keep_structured:
            object.__setattr__(t, '_economized', True)
            continue
        fn = t.fn
        if t.is_async:
            async def wrapped(*a, __fn=fn, **k):
                return compact_result(await __fn(*a, **k))
        else:
            def wrapped(*a, __fn=fn, **k):
                return compact_result(__fn(*a, **k))
        t.fn = wrapped
        t.fn_metadata.output_schema = None  # text JSON only: no second structured copy of the same data
        object.__setattr__(t, '_economized', True)


economize_tools()
TOOL_REGISTRY=dict(mcp._tool_manager._tools)
def configure_toolset(mode='full'):
    if mode not in ('full','compact'):raise ValueError('EDITVIDEO_TOOLSET=full|compact')
    names={'editvideo_bootstrap','editvideo_discover_tools','editvideo_execute_tool','editvideo_get_job','editvideo_get_media_task','editvideo_read_design_preview','editvideo_observe_media'}
    mcp._tool_manager._tools={k:v for k,v in TOOL_REGISTRY.items() if mode=='full' or k in names}


def keep_stdin_for_transport():
    """FFmpeg reads keyboard commands from its stdin. A child that inherits the MCP pipe can block on it or take a
    client's message (FFmpeg 6.1 hung read_audio_events this way). The transport keeps a private copy of the pipe;
    every child process (FFmpeg, Node, Blender) gets the null device as its stdin."""
    import io, os, sys
    private = os.dup(0)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)  # on Windows this also sets the process's standard input handle, which subprocess hands down
    os.close(null)
    sys.stdin = io.TextIOWrapper(io.BufferedReader(io.FileIO(private, "rb")), encoding="utf-8")


def main():
    # Multiple MCP clients share the database. Starting a client must never cancel another client's jobs.
    store.initialize(recover=False)
    import os
    configure_toolset(os.environ.get('EDITVIDEO_TOOLSET','full'))
    keep_stdin_for_transport()
    worker.start()
    try:
        mcp.run(transport="stdio")
    finally:
        worker.stop()
