"""Validate structured infographic inputs before they reach renderers."""
import re as _re
import math

FILM_TYPES=('grain','light_leak','scanlines','vhs','dust','speed_lines','flare')
PARTICLE_MODES=('burst','bunch','stream','drift','tracks','system')
PARTICLE_PRESETS=('fire','embers','sparks','smoke','bokeh')
PHYSICS_KEYS={'rate','burst','life','speed','angle','spread','gravity','drag','wind','turb','size','sizeVar','opacity','colors','emitter','soft','flicker','streak'}


def decimal_mark(data):
    """The decimal mark a number widget uses: as given, else ',' when thousands are grouped with '.' (4.717 and 57,5 in
    Vietnamese), else '.'. engines/effects.js applies the same rule."""
    dm=data.get('decimal_mark')
    if dm is not None and dm not in ('.',','):
        return dm  # reported by the caller's check (a falsy 0 or False must not fall through to the inferred mark)
    return dm or (',' if data.get('group')=='.' else '.')


def _point(data,key,label):
    v=data.get(key)
    if v is not None and (not isinstance(v,list) or len(v)!=2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) or not -1<=x<=2 for x in v)):
        raise ValueError(f'{label} is a normalized [x, y]')

def validate_data(kind,data):
    if kind=='scene3d':
        from .scene3d import Scene3D
        validated=Scene3D.model_validate(data).model_dump();data.clear();data.update(validated);return
    if kind=='svg':
        from .svg_graphics import SvgGraphic
        validated=SvgGraphic.model_validate(data).model_dump(exclude_none=True);data.clear();data.update(validated);return
    allowed={"text":{"accent","strong_weight","align","same_subject"},"image":set(),"video":set(),"null":{"intent"},"shape":{"shape","stroke_width","corner_radius"},
        "counter":{"from","to","decimals","prefix","suffix","group","decimal_mark","style","spins","seed","align"},
        "bar_chart":{"values","labels","min","max","colors","group","decimal_mark"},
        "line_chart":{"values","labels","min","max","stroke_width"},
        "flow":{"labels"},"particles":{"count","seed","radius","mode","angle","speed","spread","length","origin","secondary_color","glow","twinkle","curvature","mix","stroke_width","preset","physics","max_particles"},
        "caption":{"words","pages","active_color","active_background","future_opacity","mode","animation","outline","outline_color","active_scale"},
        "callout":{"target","label_point","target_keyframes","label_width","stroke_width"},
        "pattern":{"pattern","spacing","stroke_width","seed","secondary_color"},
        "icon":{"icon","stroke_width"},
        "film":{"type","intensity","seed","color","secondary_color","speed","scale","center","gauge","color_grain"},
        "adjust":{"exposure","contrast","saturation","temperature","hue","grayscale","sepia","blur","vignette","mix","ramp"}}
    if set(data)-allowed[kind]:
        raise ValueError(f"Unknown {kind} data fields: {sorted(set(data)-allowed[kind])}")
    if kind=='adjust':
        for key,lo,hi in (('exposure',-3,3),('contrast',0,3),('saturation',0,3),('temperature',-1,1),('hue',-180,180),('grayscale',0,1),('sepia',0,1),('blur',0,60),('vignette',0,1),('mix',0,1)):
            v=data.get(key)
            if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi):raise ValueError(f'adjust {key} {lo}..{hi}')
        r=data.get('ramp')
        if r is not None and (not isinstance(r,list) or len(r)!=2 or any(type(x)!=int or x<0 for x in r)):raise ValueError('adjust ramp [in_frames,out_frames]')
    if kind=='null' and data.get('intent') not in (None,'deliberate_black','deliberate_still'):
        raise ValueError('null intent is deliberate_black or deliberate_still: a silence before a hit, a held end card')
    if kind=='film':
        if data.get('type') not in FILM_TYPES:raise ValueError('film type must be '+'|'.join(FILM_TYPES))
        _point(data,'center','film center')
        if 'gauge' in data and data['gauge'] not in (8,16,35,65):raise ValueError('film gauge is 8, 16, 35 or 65 (mm)')
        if 'color_grain' in data and not isinstance(data['color_grain'],bool):raise ValueError('film color_grain is true/false')
        for key,lo,hi in (('intensity',0,1),('speed',0,10),('scale',.05,4)):
            v=data.get(key)
            if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi):raise ValueError(f'film {key} {lo}..{hi}')
        for key in ('color','secondary_color'):
            if key in data:
                from .design_library import luminance
                luminance(data[key])
    if kind in ('pattern','icon'):
        from .design_library import PATTERNS,ICONS,luminance
        if data.get(kind) not in (PATTERNS if kind=='pattern' else ICONS):raise ValueError('Unknown procedural '+kind)
        spacing=data.get('spacing',60)
        if not isinstance(spacing,(int,float)) or not math.isfinite(spacing) or not 12<=spacing<=300:raise ValueError('Pattern spacing12..300px')
        if 'secondary_color' in data:luminance(data['secondary_color'])
    if kind=="caption":
        pages=data.get('pages')
        if (pages is None)==('words' not in data):raise ValueError('Caption requires either words or pages')
        if pages is not None and (not isinstance(pages,list) or not 1<=len(pages)<=2000):raise ValueError('Caption pages1..2000')
        previous_page=-1
        for page in pages or [{'words':data.get('words',[])}]:
            if not isinstance(page,dict):raise ValueError('Invalid caption page')
            if pages is not None:
                if set(page)!={'start_frame','end_frame','words'} or type(page['start_frame'])!=int or type(page['end_frame'])!=int or not 0<=page['start_frame']<page['end_frame'] or page['start_frame']<previous_page:raise ValueError('Caption pages must be ordered/nonoverlapping')
                previous_page=page['end_frame']
            words=page.get('words',[])
            if not isinstance(words,list) or not 1<=len(words)<=80:raise ValueError('Caption page requires1..80 timed words')
            previous=-1
            for word in words:
                if not isinstance(word,dict) or not {'text','start_frame','end_frame'}<=set(word)<={'text','start_frame','end_frame','color'} or not isinstance(word['text'],str) or not 1<=len(word['text'])<=120:raise ValueError('Caption words require text/start_frame/end_frame (+ optional color)')
                if 'color' in word and not (isinstance(word['color'],str) and _re.fullmatch(r'#[0-9a-fA-F]{6}',word['color'])):raise ValueError('Caption word color #RRGGBB')
                a,b=word['start_frame'],word['end_frame']
                if type(a)!=int or type(b)!=int or not previous<=a<b or a<0:raise ValueError('Caption words must be sorted integer ranges')
                if pages is not None and not page['start_frame']<=a<b<=page['end_frame']:raise ValueError('Word outside caption page')
                previous=a
        if data.get('mode','box') not in ('box','color','underline'):raise ValueError('Caption mode box|color|underline')
        if not isinstance(data.get('future_opacity',.65),(int,float)) or not 0<=data.get('future_opacity',.65)<=1:raise ValueError('future_opacity0..1')
        import re
        for key in ('active_color','active_background','outline_color'):
            if key in data and (not isinstance(data[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',data[key])):raise ValueError('Caption colors use #RRGGBB')
        if data.get('animation','none') not in ('none','pop','bounce','rise'):raise ValueError('Caption animation none|pop|bounce|rise')
        for key,lo,hi in (('outline',0,.2),('active_scale',1,1.4)):
            if key in data and (not isinstance(data[key],(int,float)) or not lo<=data[key]<=hi):raise ValueError(f'Caption {key} {lo}..{hi}')
    if kind=='callout':
        for key in ('target','label_point'):
            point=data.get(key)
            if not isinstance(point,list) or len(point)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in point):raise ValueError('Callout target/label_point normalized [x,y]')
        previous=-1
        if not isinstance(data.get('target_keyframes',[]),list):raise ValueError('target_keyframes requires list')
        for k in data.get('target_keyframes',[]):
            if not isinstance(k,dict) or set(k)!={'frame','x','y'} or type(k['frame'])!=int or k['frame']<=previous or any(not isinstance(k[v],(int,float)) or not math.isfinite(k[v]) or not 0<=k[v]<=1 for v in ('x','y')):raise ValueError('Invalid target_keyframes')
            previous=k['frame']
        if len(data.get('target_keyframes',[]))>100:raise ValueError('At most100 target keyframes')
        if not isinstance(data.get('label_width',.25),(int,float)) or not .05<=data.get('label_width',.25)<=.8:raise ValueError('label_width.05..0.8')
    for key in ("from","to","min","max","stroke_width","radius","corner_radius"):
        if key in data and (not isinstance(data[key],(int,float)) or not math.isfinite(data[key]) or abs(data[key])>1e12):
            raise ValueError(f"Invalid numeric {key}")
    if 'corner_radius' in data and not 0<=data['corner_radius']<=250:raise ValueError('corner_radius0..250')
    if 'radius' in data and not 0<=data['radius']<=100:raise ValueError('radius0..100')
    if 'stroke_width' in data and not 0<=data['stroke_width']<=100:raise ValueError('stroke_width0..100')
    if kind in ("bar_chart","line_chart"):
        values=data.get("values",[])
        if not 1<=len(values)<=50 or any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in values):
            raise ValueError("Chart requires 1..50 finite values")
        low=data.get("min",0); high=data.get("max",max(max(values),low+1))
        if high<=low or any(v<low or v>high for v in values):
            raise ValueError("Chart values outside explicit axis range")
        if kind=="bar_chart":
            if decimal_mark(data) not in (".",","):raise ValueError("bar_chart decimal_mark is '.' or ','")
            if not isinstance(data.get("group",""),str) or len(data.get("group",""))>3:raise ValueError("bar_chart group is a separator of up to 3 characters")
            if data.get("group") and data.get("group")==decimal_mark(data):raise ValueError("bar_chart group and decimal_mark must differ")
        if "labels" in data and len(data["labels"])!=len(values):
            raise ValueError("Chart labels must match values")
    if "labels" in data and (not isinstance(data["labels"],list) or any(not isinstance(x,str) or len(x)>100 for x in data["labels"])):
        raise ValueError("Labels require short strings")
    if kind=="flow" and not 2<=len(data.get("labels",[]))<=8:
        raise ValueError("Flow requires 2..8 labels")
    if "shape" in data and data["shape"] not in ("rectangle","ellipse","triangle","arrow","ring"):
        raise ValueError("Unknown shape")
    if kind=='particles':
        mode=data.get('mode','burst')
        if mode not in PARTICLE_MODES:raise ValueError('particles mode must be '+'|'.join(PARTICLE_MODES))
        limit=200 if mode=='burst' else 300 if mode=='tracks' else 1500
        if mode=='system':
            if data.get('preset','fire') not in PARTICLE_PRESETS:raise ValueError('particles system preset '+'|'.join(PARTICLE_PRESETS))
            ph=data.get('physics',{})
            if not isinstance(ph,dict) or set(ph)-PHYSICS_KEYS:raise ValueError('particles physics keys: '+', '.join(sorted(PHYSICS_KEYS)))
            for key,lo,hi in (('rate',0,2000),('burst',0,1500),('angle',-360,360),('spread',0,360),('gravity',-5000,5000),('drag',0,20),('soft',0,1),('flicker',0,1),('streak',0,720),('sizeVar',0,2)):
                v=ph.get(key)
                if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi):raise ValueError(f'particles physics {key} {lo}..{hi}')
            for key in ('life','speed','size'):
                v=ph.get(key)
                if v is not None and (not isinstance(v,list) or len(v)!=2 or any(not isinstance(x,(int,float)) or x<0 for x in v)):raise ValueError(f'particles physics {key} is [min,max]')
            if 'colors' in ph:
                from .design_library import luminance
                if not isinstance(ph['colors'],list) or not 1<=len(ph['colors'])<=8:raise ValueError('physics colors: 1..8 hex colours over life')
                for c in ph['colors']:luminance(c)
            mp=data.get('max_particles',900)
            if not isinstance(mp,int) or not 10<=mp<=1500:raise ValueError('max_particles 10..1500')
        if 'count' in data and (not isinstance(data['count'],int) or not 1<=data['count']<=limit):raise ValueError(f'particles {mode} count 1..{limit}')
        for key,lo,hi in (('angle',-360,360),('speed',0,10),('spread',0,1),('length',0,3),('glow',1,8),('twinkle',0,1),('curvature',0,10),('mix',0,1)):
            v=data.get(key)
            if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi):raise ValueError(f'particles {key} {lo}..{hi}')
        _point(data,'origin','particles origin')
        if 'secondary_color' in data:
            from .design_library import luminance
            luminance(data['secondary_color'])
    if data.get('align','left') not in ('left','center','right'):raise ValueError('align left|center|right')
    if kind=='counter':
        if data.get('style','count') not in ('count','roll','scramble'):raise ValueError('counter style count|roll|scramble')
        if not isinstance(data.get('group',''),str) or len(data.get('group',''))>3:raise ValueError('counter group is a separator of up to 3 characters')
        if decimal_mark(data) not in ('.',','):raise ValueError("counter decimal_mark is '.' or ','")
        if data.get('group') and data.get('group')==decimal_mark(data):raise ValueError('counter group and decimal_mark must differ')
        if not isinstance(data.get('spins',2),int) or not 0<=data.get('spins',2)<=6:raise ValueError('counter spins 0..6')
        if data.get('style')=='roll' and (data.get('to',100)<0 or data.get('from',0)<0):raise ValueError('roll counters show non-negative numbers')
    if kind=='text':
        if 'accent' in data:
            from .design_library import luminance
            luminance(data['accent'])
        if not isinstance(data.get('strong_weight',800),int) or not 100<=data.get('strong_weight',800)<=900:raise ValueError('strong_weight 100..900')
    for key,lo,hi in (("count",1,1500),("seed",0,2147483647),("decimals",0,4)):
        if key in data and (not isinstance(data[key],int) or not lo<=data[key]<=hi):
            raise ValueError(f"Invalid {key}")
    for key in ("prefix","suffix"):
        if key in data and (not isinstance(data[key],str) or len(data[key])>100):
            raise ValueError(f"Invalid {key}")
