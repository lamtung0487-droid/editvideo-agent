"""Discoverable, validated effects implemented by engines/effects.js in both engines."""
import math

# id, family, default amount, valid range, direction/use. Amount has explicit units below.
DEFINITIONS = [
    ("fade_in", "entrance", 1, 0, 1, "Introduce a label without moving the scene"),
    ("fade_out", "exit", 1, 0, 1, "Remove a layer before the next idea"),
    ("rise", "entrance", 80, -1000, 1000, "Lift a heading into the visual hierarchy"),
    ("drop", "entrance", 80, -1000, 1000, "Bring a callout from above"),
    ("slide_left", "entrance", 180, -2000, 2000, "Reveal a comparison from the left"),
    ("slide_right", "entrance", 180, -2000, 2000, "Reveal a comparison from the right"),
    ("pop", "entrance", .2, 0, 1, "Emphasize one short keyword or icon"),
    ("spring", "entrance", .3, 0, 1, "Give a diagram node a soft overshoot"),
    ("blur_in", "entrance", 18, 0, 100, "Resolve a headline into focus"),
    ("rotate_in", "entrance", 15, -180, 180, "Introduce a decorative card"),
    ("flip_x", "entrance", 80, -180, 180, "Turn a card around its horizontal axis"),
    ("flip_y", "entrance", 80, -180, 180, "Turn a card around its vertical axis"),
    ("zoom_in", "camera", .1, -.8, 3, "Slowly move attention toward an image"),
    ("zoom_out", "camera", .1, 0, 3, "Reveal context around a detail"),
    ("pan_x", "camera", 100, -2000, 2000, "Track across a wide still image"),
    ("pan_y", "camera", 100, -2000, 2000, "Track a vertical diagram"),
    ("float", "motion", 12, 0, 300, "Give an isolated object a gentle repeating motion"),
    ("pulse", "motion", .04, 0, .8, "Draw attention to a focal object briefly"),
    ("shake", "motion", 8, 0, 100, "Express impact; avoid shaking explanatory text"),
    ("orbit", "motion", 20, 0, 500, "Move a decorative object around its anchor"),
    ("spin", "motion", 360, -1440, 1440, "Rotate a symbol or mechanism"),
    ("skew", "motion", 10, -60, 60, "Add slant to a fast title beat"),
    ("wipe_left", "reveal", 1, 0, 1, "Reveal a layer left to right"),
    ("wipe_right", "reveal", 1, 0, 1, "Reveal a layer right to left"),
    ("wipe_up", "reveal", 1, 0, 1, "Reveal a layer bottom to top"),
    ("wipe_down", "reveal", 1, 0, 1, "Reveal a layer top to bottom"),
    ("iris", "reveal", 1, 0, 1, "Reveal an object from its center"),
    ("typewriter", "text", 1, 0, 1, "Show a short quotation progressively"),
    ("tracking_in", "text", 16, 0, 80, "Settle a short title from wide letter spacing"),
    ("highlight", "text", .5, 0, 1, "Mark an important statement with a colored background"),
    ("glow", "light", 24, 0, 120, "Emphasize a bright shape on a dark background"),
    ("shadow", "light", 20, 0, 100, "Separate foreground from background"),
    ("brightness", "grade", 1.1, 0, 3, "Match exposure between adjacent footage"),
    ("contrast", "grade", 1.1, 0, 3, "Clarify tonal separation"),
    ("saturate", "grade", 1.2, 0, 3, "Match color intensity to the reference"),
    ("grayscale", "grade", 1, 0, 1, "Distinguish archival or de-emphasized material"),
    ("sepia", "grade", .7, 0, 1, "Give footage a warm historical tone"),
    ("hue", "grade", 20, -360, 360, "Adjust a decorative palette; avoid distorting evidence"),
    ("warm", "grade", .25, 0, 1, "Create a restrained warm palette"),
    ("cool", "grade", .25, 0, 1, "Create a restrained cool palette"),
    ("invert", "grade", 1, 0, 1, "Create a brief graphic inversion"),
    ("blur", "grade", 8, 0, 100, "De-emphasize background while keeping foreground clear"),
    ("rounded", "mask", 32, 0, 500, "Create rounded picture-in-picture cards"),
    ("circle", "mask", 1, 0, 1, "Crop an image to a circular focal region"),
    ("vignette", "texture", .45, 0, 1, "Darken edges without hiding important information"),
    ("scanlines", "texture", .2, 0, 1, "Suggest a screen or technical signal"),
    ("letterbox", "frame", .08, 0, .4, "Reserve cinematic bars inside a shot"),
    ("border", "frame", 4, 0, 100, "Define a comparison or evidence inset"),
    ("progress", "data", 1, 0, 1, "Animate bars, chart paths, counters or particles over time"),
    ("flash", "light", .5, 0, 1, "Add a brief bright accent at an impact"),
    ("white_flash", "light", 1, 0, 1, "Flash to true white on a hit (1-2 frames on a drop; 1 = full white)"),
    ("chroma_split", "light", 9, 0, 32, "Split red/blue channels across a full-frame shot on a drop (2-4 frames)"),
    ("impact_shake", "motion", 24, 0, 160, "Decaying camera shake on an impact (8-12 frames, ~2-3% of the width); graphics and trailers, not archive or live footage"),
    ("impact_zoom", "camera", .08, 0, .5, "Zoom punch on a beat that settles back (4-8 frames)"),
    ("diagonal_reveal", "reveal", 1, 1, 1, "Reveal a chapter or image along a diagonal mask"),
    ("diamond_reveal", "reveal", 1, 1, 1, "Open a graphic window from a diamond center"),
    ("soft_edge_reveal", "reveal", 1, 1, 1, "Reveal an inset with a soft alpha edge"),
    ("slide_spring", "entrance", 120, -1000, 1000, "Bring one lower third into place with damped overshoot"),
    ("focus_zoom", "camera", .08, -.5, 1, "Push toward an explicitly selected focal point"),
    ("defocus_pulse", "motion", 8, 0, 40, "Briefly de-emphasize a graphic before returning to clarity"),
    ("fade_pulse", "motion", .25, 0, 1, "Dim and restore a layer once to direct attention"),
    ("light_sweep", "texture", .2, 0, .8, "Move one soft light accent over a chapter card"),
    ("paper_grain", "texture", .08, 0, .5, "Add static seeded paper-like texture to graphics"),
    ("text_outline", "text", 2, 0, 10, "Keep captions readable over changing footage"),
    ("marker_reveal", "text", .35, 0, 1, "Underline one statement with a growing marker strip"),
    ("exposure", "grade", 0, -2, 2, "Approximate a small exposure adjustment in display-space stops"),
    ('word_reveal','text',24,0,100,'Reveal a short heading word by word while keeping its final layout stable'),
    ('line_reveal','text',24,0,100,'Reveal explicitly authored lines with staggered vertical motion'),
    ('character_reveal','text',12,0,100,'Reveal grapheme clusters on a short decorative title; avoid paragraph text'),
    ('text_gradient','text',1,0,1,'Use a restrained two-color fill for a display heading on a solid background'),
    ('underline_draw','text',.06,.01,.2,'Draw a text-sized underline and hold without moving letters'),
    ('radial_glow','texture',.18,0,1,'Add a static soft colored halo behind a graphic; keep text clear'),
    ('edge_feather','mask',.08,.01,.3,'Soften an inset boundary (CSS mask); params.box fades a contained picture into the canvas'),
    ('mask_reveal','text',110,0,200,'Lines rise into place inside their own clipping mask with a slight overshoot; premium title reveal'),
    ('char_spring','text',.6,0,1.5,'Characters pop in one by one with spring overshoot and motion blur; short punchy titles only'),
    ('handheld','camera',6,0,200,'Organic handheld drift from smooth seeded noise (After Effects wiggle); 2–8 px for documentary, more for action'),
    ('rgb_split','light',4,0,60,'Chromatic red/cyan fringe offset on text/graphics; tech, glitch and lens-flaw looks'),
    ('glitch','motion',18,0,300,'Seeded glitch bursts on random frames: jump, skew, RGB split and band crop; use on accents only'),
    ('decode','text',1,0,1,'Characters scramble through glyphs and settle left to right (seeded); tech/cyber titles, monospace reads best'),
    ('motion_blur','light',180,0,360,'Velocity blur from the layer\'s own movement; amount is shutter angle (180 = film look); smears along the travel axis for straight moves'),
    ('color_to','entrance',1,0,1,'Arrive in params.color and settle on the layer colour (fade-with-colour entrance or a state change); OKLab interpolation'),
    ('text_animate','text',30,-400,400,'After Effects-style range selector: units (char/word/line) arrive, leave or carry a travelling accent in forward/reverse/center/random order, with their own sweep easing'),
    ('gate_weave','camera',1,0,10,'Smooth film-gate wobble with 1% overscan on illustrations or stills; on footage keep <= .5 px (0.1% of 1080); not on reading text'),
    ('boil','texture',4,1,8,'Hand-drawn line boil: displacement that changes every `cycles` frames (4 = 7.5 fps), for illustrated/sketch looks'),
    ('jitter','motion',3,0,40,'Stepped tremble for cut-outs and collage graphics: a new random offset (px), rotation (params.rotation deg) and 1% scale every `cycles` frames; pair with step_frames 2'),
    ('clock_wipe','mask',1,-1,1,'Radial sweep reveal around a pivot (pie build, logo fill, timer); negative amount = counter-clockwise; params.angle start, focus_x/focus_y pivot'),
    ('bloom','light',16,0,120,'Soft filmic glow: three halos of growing radius and falling strength in params.color; neon, light sources, particles'),
    ('tracking','text',.2,-.2,2,'Letter spacing in em that scales with the type: params.from_em → amount over the span (slow trailer expand .05→.25, or collapse into a lockup); centred titles stay centred'),
    ('luma_alpha','mask',1,0,1,'Alpha from brightness (AE Unmult/luma key): fire, smoke, sparks, light leaks or dust shot on black composite without a box; params.clip_black/clip_white, invert keys out whites'),
    ('tint_fill','grade',1,0,1,'Fill the layer with params.color keeping its alpha (AE Fill/Tint): silhouettes, logo colourways, one-frame colour flashes with ramp'),
    ('highlight_glow','light',1,0,4,'Glow only from highlights above params.threshold (Deep Glow): three blur radii up to params.radius; params.anamorphic stretches into horizontal streaks; optional color tint'),
    ('tritone','grade',1,0,1,'Map luminance through shadow_color → color → highlight_color (documentary/map grading, archive unification); amount mixes with the original'),
    ('heat_distortion','texture',6,0,80,'Heat haze / underwater wobble: fractal-noise displacement (px) that morphs every params.cycles frames, feature params.size px; mask it to the hot area'),
    ('halation','light',.7,0,2,'Film halation: orange-red glow scattered around bright areas (practicals, windows, specular edges); params.threshold, radius px (≈2-3 % of frame height), color; pair with film grain by gauge'),
    ('light_wrap','light',.6,0,2,'Backdrop light bleeding into the inside edge of a keyed or cut-out layer; params.color = the plate colour behind the edge, params.radius px'),
]
CATALOG = {}
for name, family, default, low, high, use in DEFINITIONS:
    units = "pixels" if name in {"rise","drop","slide_left","slide_right","pan_x","pan_y","float","shake","impact_shake","chroma_split","orbit","blur_in","tracking_in","glow","shadow","blur","rounded","border"} else "degrees" if name in {"rotate_in","flip_x","flip_y","spin","skew","hue"} else "ratio"
    if name in ('slide_spring','defocus_pulse','text_outline'):units='pixels'
    if name=='exposure':units='display-space stops (CSS brightness, not scene-linear grading)'
    CATALOG[name] = {"id": name, "family": family, "engines": ["remotion","hyperframes"],
        "targets": ["shot","layer"] if family != "text" else ["text layer"],
        "use_when": use, "amount": {"default": default,"min":low,"max":high,"unit":units},
        "parameters": {"amount":default,**({"frequency":.6,"rotation":.24,"seed":7} if name=='handheld' else {}),**({"angle":0} if name=='rgb_split' else {}),**({"rate":.15,"seed":7} if name=='glitch' else {}),**({"seed":7} if name=='decode' else {}),**({"color":"#81e6be"} if name in ("glow","highlight","border","marker_reveal","light_sweep") else {}),**({"color":"#101820"} if name=='text_outline' else {}),**({"cycles":1} if name in ("float","pulse","orbit") else {}),**({"seed":7} if name in ('shake','paper_grain') else {}),**({'focus_x':.5,'focus_y':.5} if name=='focus_zoom' else {})},
        "timing": "Local integer frames relative to shot/layer; end_frame is the final effect state, held afterward. fade_out holds zero. Repeating motion is evaluated from absolute frame, never accumulated.",
        "caution": "Use one focal motion per beat. Check legibility and avoid changing the meaning of evidence footage.",
        "example": {"name":name,"start_frame":0,"end_frame":18,"params":{"amount":default},"easing":"smooth"}}
CATALOG['text_animate']['parameters'].update(unit='word',order='forward',mode='in',shape='smooth',window=.35,opacity=0,scale=1,rotate=0,blur=0,x=0,color='#81e6be',seed=7)
CATALOG['gate_weave']['parameters'].update(frequency=12,seed=7)
CATALOG['boil']['parameters'].update(cycles=4)
CATALOG['bloom']['parameters'].update(color='#ffffff')
CATALOG['jitter']['parameters'].update(cycles=4,rotation=.5,seed=7)
CATALOG['jitter']['amount']['unit']='pixels'
CATALOG['clock_wipe']['parameters'].update(angle=0,focus_x=.5,focus_y=.5)
CATALOG['clock_wipe']['amount']['unit']='direction (+1 clockwise, -1 counter-clockwise)'
CATALOG['color_to']['parameters'].update(color='#81e6be')
CATALOG['text_animate']['parameters'].update(shutter=0,target=None)
CATALOG['focus_zoom']['parameters'].update(cut=False)
CATALOG['edge_feather']['parameters'].update(box=None,shape=None)  # box: [x0,y0,x1,y1] element shares where a contained picture sits; shape 'rect': a box fades on all four sides (a dark field under type)
CATALOG['typewriter']['parameters'].update(cursor=False,cursor_color='#ffd166',blink=16,script=None,cps=20,hold=None)  # hold None: reading time (0.5 s + 0.32 s/word, >= 24 frames)  # script: phrases typed, deleted at 2x back to the shared prefix, retyped  # cut=True: hard punch-in held from start_frame (measured emphasis punch about x1.14 at the eye line)
CATALOG['tracking']['parameters'].update(from_em=0,center=True)
CATALOG['tracking']['amount']['unit']='em (target letter spacing)'
CATALOG['tracking']['timing']='Spacing moves from params.from_em to amount between start_frame and end_frame (easing applies) and holds; use linear easing across a whole shot for the slow trailer drift.'
CATALOG['luma_alpha']['parameters'].update(clip_black=.05,clip_white=.6,invert=False,ramp=False)
CATALOG['tint_fill']['parameters'].update(color='#ffffff',ramp=False)
CATALOG['highlight_glow']['parameters'].update(threshold=.75,radius=24,anamorphic=0,color=None,ramp=False)
CATALOG['tritone']['parameters'].update(shadow_color='#0d1b2a',color='#7d8b99',highlight_color='#f4ead5',ramp=False)
CATALOG['heat_distortion']['parameters'].update(size=40,cycles=8,seed=7,ramp=False)
CATALOG['heat_distortion']['amount']['unit']='pixels of displacement'
CATALOG['light_wrap']['parameters'].update(color='#ffffff',radius=12,ramp=False)
CATALOG['halation']['parameters'].update(threshold=.78,radius=18,color='#ff5a1f',ramp=False)
for _n in ('luma_alpha','tint_fill','highlight_glow','tritone','heat_distortion','light_wrap','halation'):
    CATALOG[_n]['engines_note']='SVG filter built per layer by composite(); applied after a chroma key and before CSS filters in both engines.'
for _n in ('text_animate','gate_weave','boil','bloom'):CATALOG[_n]['amount']['unit']='pixels'
CATALOG['text_animate']['timing']='The sweep runs start_frame to end_frame with its own easing/bezier; mode in holds the rest state after, out holds the start state (exit), sweep returns to rest.'
CATALOG["progress"]["targets"]=["counter","bar_chart","line_chart","flow","particles","callout"]
CATALOG['text_outline']['targets']=['text layer','caption layer']
for name in ("wipe_left","wipe_right","wipe_up","wipe_down","iris","circle","typewriter","progress"):
    CATALOG[name]["amount"].update(min=1,max=1)
for item in CATALOG.values():
    if item["family"] in ("grade","mask","texture","frame") or item["id"] in ("glow","shadow","highlight","bloom","highlight_glow","light_wrap","halation"):
        item["timing"]="Static appearance begins at start_frame and remains active. end_frame is a valid local bound, not a fade-out. Animate transform/opacity/blur with keyframes; use separate entrance/exit effects."
CATALOG['light_sweep']['timing']='One frame-addressed sweep start→end, then leaves the layer; no repeating flash.'
CATALOG['marker_reveal']['timing']='Marker strip grows start→end and holds; text stays laid out and readable.'
CATALOG['exposure']['example']['params']['amount']=.5
CATALOG['clock_wipe']['timing']='Sweep runs start_frame to end_frame (easing/bezier apply), then the layer stays fully revealed.'
for name in ('word_reveal','line_reveal','character_reveal'):
    CATALOG[name]['amount']['unit']='pixels of local text rise'
CATALOG['mask_reveal']['amount']['unit']='percent of line height travelled inside the mask'
CATALOG['char_spring']['amount']['unit']='overshoot strength'
for name in ('mask_reveal','char_spring'):
    CATALOG[name]['parameters']['stagger']=.35 if name=='mask_reveal' else .6
    CATALOG[name]['timing']='Frame-addressed stagger across authored lines (mask_reveal) or graphemes (char_spring); final layout reserved, all units settled by end_frame.'
    CATALOG[name]['parameters']['stagger']=.12
    CATALOG[name]['timing']='Frame-addressed stagger; full final text layout reserved before reveal. end_frame holds all units visible. Not ASR/word timing.'
for name in ('text_gradient','underline_draw','radial_glow'):
    CATALOG[name]['parameters']['color']='#81e6be'
CATALOG['text_gradient']['parameters']['secondary_color']='#e4b866'
CATALOG['underline_draw']['timing']='Text-sized line grows start→end and holds.'
CATALOG['text_gradient']['amount'].update(min=1,max=1)

RECIPES = {
    "knowledge_callout": {"intent":"Explain one concept with restrained motion", "kind":"text", "effects":["fade_in","rise"], "notes":"Use 12–18 frames for entrance; hold long enough to read; position away from captions and the subject."},
    "evidence_inset": {"intent":"Show a source or detail while retaining surrounding context", "kind":"image", "effects":["rounded","border","shadow","fade_in"], "notes":"Use contain, keep source attribution visible, crop only after inspecting detail."},
    "number_reveal": {"intent":"Explain a quantity and its unit", "kind":"counter", "effects":["progress","fade_in"], "notes":"State source and unit; animation interpolates the provided number and does not invent data."},
    "comparison": {"intent":"Compare two alternatives", "kind":"bar_chart", "effects":["progress"], "notes":"Use consistent scale, explicit labels, and separate bars with enough space."},
    "process_flow": {"intent":"Explain causal steps", "kind":"flow", "effects":["progress","fade_in"], "notes":"Align node reveals with narration boundaries; keep arrows from crossing labels."},
    "chart_trace": {"intent":"Explain a trend", "kind":"line_chart", "effects":["progress"], "notes":"Provide measured values and axis range; distinguish interpolation from observations."},
    "section_change": {"intent":"Mark a change in topic", "transition":"wipe_left", "notes":"Use 8–18 frames; push/whip/zoom_through move both sides; mode live keeps the outgoing shot playing from its source handle, mode freeze holds its last frame. Preserves total narration duration."},
    "calm_reference": {"intent":"Let an important image breathe", "kind":"image", "effects":["zoom_in"], "notes":"Set amount about 0.03–0.08 across the full shot; avoid adding simultaneous pan and shake."},
}

def validate_effect(name, params):
    if name not in CATALOG:
        raise ValueError(f"Unknown effect {name}; search editvideo_effect_catalog")
    unknown = set(params)-set(CATALOG[name]["parameters"])-{"accent"}  # accent: metadata of accent_sync (level), ignored by engines
    if unknown:
        raise ValueError(f"Unknown effect parameters: {sorted(unknown)}")
    spec = CATALOG[name]["amount"]
    amount = params.get("amount",spec["default"])
    if not isinstance(amount,(int,float)) or not math.isfinite(amount) or not spec["min"]<=amount<=spec["max"]:
        raise ValueError(f"{name}.amount requires {spec['min']}..{spec['max']} {spec['unit']}")
    for key, low, high in (("cycles",.1,100),("seed",0,2147483647),('stagger',0,.45),('frequency',.05,12),('rotation',-30,30),('angle',-360,360),('rate',0,1)):
        value=params.get(key,{"cycles":1,"seed":7,"stagger":.12,"frequency":.6,"rotation":0,"angle":0,"rate":.15}[key])
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f"Invalid {key}")
    if name=='edge_feather' and params.get('shape') not in (None,'ellipse','rect'):
        raise ValueError("edge_feather shape is 'ellipse' or 'rect'")
    if name=='edge_feather' and params.get('box') is not None:
        bx=params['box']
        if not (isinstance(bx,(list,tuple)) and len(bx)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) and -1<=v<=2 for v in bx) and bx[0]<bx[2] and bx[1]<bx[3]):
            raise ValueError('edge_feather box is [x0,y0,x1,y1] element shares with x0<x1, y0<y1')
    for key in ('focus_x','focus_y'):
        if key in params and (not isinstance(params[key],(int,float)) or not math.isfinite(params[key]) or not 0<=params[key]<=1):raise ValueError(f'{key} must be0..1')
    if name=='text_animate':
        for key,allowed in (('unit',('char','word','line')),('order',('forward','reverse','center','random')),('mode',('in','out','sweep')),('shape',('smooth','ramp','square'))):
            if key in params and params[key] not in allowed:raise ValueError(f"text_animate {key} must be one of {allowed}")
        for key,low,high in (('window',.02,1),('opacity',0,1),('scale',0,4),('rotate',-360,360),('blur',0,60),('x',-2000,2000)):
            if key in params and (not isinstance(params[key],(int,float)) or not math.isfinite(params[key]) or not low<=params[key]<=high):raise ValueError(f"text_animate {key} {low}..{high}")
    if name=='typewriter':
        sc=params.get('script')
        if sc is not None and (not isinstance(sc,list) or not 1<=len(sc)<=20 or not all(isinstance(x,str) and 1<=len(x)<=200 for x in sc)):raise ValueError('typewriter script is 1..20 phrases of 1..200 characters')
        for key,low,high in (('cps',2,80),('hold',0,300),('blink',4,60)):
            if key in params and params[key] is not None and (isinstance(params[key],bool) or not isinstance(params[key],(int,float)) or not low<=params[key]<=high):raise ValueError(f'typewriter {key} {low}..{high}')
        if 'cursor' in params and not isinstance(params['cursor'],bool):raise ValueError('typewriter cursor true/false')
    if name=='text_animate' and params.get('target') is not None and (not isinstance(params['target'],list) or not 1<=len(params['target'])<=200 or not all(isinstance(v,int) and not isinstance(v,bool) and 0<=v<=2000 for v in params['target'])):
        raise ValueError("text_animate target is a list of unit numbers (0-based)")
    if name=='text_animate' and 'shutter' in params and not (isinstance(params['shutter'],(int,float)) and 0<=params['shutter']<=360):
        raise ValueError("text_animate shutter is 0..360 degrees")
    for key,low,high in (('from_em',-.2,2),('clip_black',0,.95),('clip_white',.02,1),('threshold',0,.98),('radius',0,200),('anamorphic',0,1),('size',4,400)):
        if key in params and (isinstance(params[key],bool) or not isinstance(params[key],(int,float)) or not math.isfinite(params[key]) or not low<=params[key]<=high):
            raise ValueError(f"{name} {key} must be {low}..{high}")
    for key in ('center','invert','ramp','cut'):
        if key in params and not isinstance(params[key],bool):raise ValueError(f"{name} {key} must be true/false")
    if name=='luma_alpha' and params.get('clip_white',.6)<=params.get('clip_black',.05)+.02:
        raise ValueError("luma_alpha clip_white must exceed clip_black by .02")
    for color_key in ('color','secondary_color','shadow_color','highlight_color','cursor_color'):
      if color_key in params:
        import re
        if not isinstance(params[color_key],str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",params[color_key]):
            raise ValueError("effect color requires #RRGGBB")

def _brief(v):
    """One catalog row for listings: what it is for, its amount range and parameter defaults (no repeated prose)."""
    a=v["amount"]
    return {"id":v["id"],"family":v["family"],"use_when":v["use_when"],"amount":[a["default"],a["min"],a["max"],a["unit"]],
            "params":{k:p for k,p in v["parameters"].items() if k!="amount"},**({"targets":v["targets"]} if v["targets"]!=["shot","layer"] else {})}


CONVENTIONS={"engines":["remotion","hyperframes"],
    "timing":"Effects use layer/shot-local integer frames; end_frame is the final state, held afterwards. Repeating motion is evaluated from the absolute frame. Static looks (grade, mask, texture, glow) begin at start_frame and stay.",
    "apply":"effects=[{name, start_frame, end_frame, params:{amount,...}, easing|bezier}] on a layer or shot (≤16); query an exact id for its timing note, caution, example, pairs_with/avoid and preview strip (read_design_preview kind=effect shows it)."}


def catalog(query="", family=None, offset=0, limit=12, detail="auto"):
    """detail auto: full rows for an exact id, compact rows for listings (the shared conventions are sent once)."""
    if offset<0 or not 1<=limit<=50:
        raise ValueError("offset >=0, limit 1..50")
    terms=[w for w in query.lower().replace("_"," ").split() if w not in {"the","a","an","of","for","to","with","and","in","out"}]
    items=[v for v in CATALOG.values() if (not family or v["family"]==family)]
    exact=query.strip().lower().replace(" ","_")
    if exact in CATALOG:
        items=[v for v in items if v["id"]==exact]
    elif terms:
        def relevance(v):
            haystack=(v["id"]+" "+v["use_when"]+" "+v["family"]).lower().replace("_"," ")
            return sum(w in haystack for w in terms)
        items=sorted([v for v in items if relevance(v)],key=relevance,reverse=True)
    from . import store
    from .effect_guide import COMBOS, combos, guide
    atlas_path=store.ROOT/"assets/previews/effect-atlas.json"  # v2 strips live in the repository (scripts/effect_atlas.py)
    if not atlas_path.exists():
        atlas_path=store.atlas_path("effect-atlas.json")
    atlas=store.read_json(atlas_path) if atlas_path.exists() else {}
    if exact in COMBOS:  # a combination recipe asked for by id: the full card with its rendered strip
        c={"id":exact,**COMBOS[exact]}
        if atlas.get("version")==2 and exact in atlas.get("combos",{}):
            c["preview"]={"strip":{k:store.repo_path(v) for k,v in atlas["combos"][exact]["strip"].items()},"panels":atlas["panels"]}
        return {"combo":c,**CONVENTIONS}
    selected=[dict(v) for v in items[offset:offset+limit]]
    full=detail=="full" or (detail=="auto" and exact in CATALOG)
    if full:
        for item in selected:
            item.update(guide(item["id"],item["family"]))
            entry=(atlas.get("effects") or {}).get(item["id"]) if atlas.get("version")==2 else None
            if entry:  # source | t+10 | t+30 | t+52 of the effect's own stage, both engines
                item["preview"]={"strip":{k:store.repo_path(v) for k,v in entry["strip"].items()},"panels":atlas["panels"]}
    out={"effects":selected if full else [_brief(v) for v in selected],"total":len(items),"next_offset":offset+limit if offset+limit<len(items) else None,
        **CONVENTIONS}
    if not query and offset==0:
        out["families"]=sorted({v["family"] for v in CATALOG.values()})
        out["recipes"]={k:v["intent"] for k,v in RECIPES.items()}
        out["custom_code"]="effects.js is editable, frame-deterministic source bundled with every project; extend it for techniques beyond the catalog."
        out["combos"]=combos()  # rendered stacks that agree; query a combo id for parameters, avoid notes and its strip
    return out
