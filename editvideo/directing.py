"""Scene decisions compiled into real, editable layers, with cached audiovisual evidence for the host AI."""
import math
import uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store, narrative


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=75)
    detail: str = Field(default="", max_length=200)
    value: str = Field(default="", max_length=35)
    source: str = Field(default="", max_length=180)
    at: float = Field(default=0, ge=0, allow_inf_nan=False)
    percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


class SceneDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    technique: Literal["chapter_route", "quantity_focus", "evidence_compare"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    base_revision: int = Field(ge=1)
    viewer_question: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=1200)
    heading: str = Field(min_length=1, max_length=100)
    items: list[Item] = Field(min_length=1, max_length=6)
    source: str = Field(default="", max_length=220)
    background: str = Field(default="#10171d", pattern=r"^#[0-9a-fA-F]{6}$")
    ink: str = Field(default="#f3eee4", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#e7ad61", pattern=r"^#[0-9a-fA-F]{6}$")
    muted: str = Field(default="#a6b4bd", pattern=r"^#[0-9a-fA-F]{6}$")
    font_id: str = "bevietnampro"
    footage_asset_id: str | None = None
    footage_source_start: float = Field(default=0, ge=0, allow_inf_nan=False)
    footage_fit: Literal['contain','cover'] = 'contain'
    replace_layer_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def counts(self):
        lo, hi = {"chapter_route": (2,6), "quantity_focus": (1,3), "evidence_compare": (2,2)}[self.technique]
        if not lo <= len(self.items) <= hi: raise ValueError(f"{self.technique} needs {lo}..{hi} items")
        if self.technique == "quantity_focus" and any(not i.value for i in self.items): raise ValueError("Quantities require explicit values/units; no invented numbers")
        if any(b.at < a.at for a,b in zip(self.items,self.items[1:])): raise ValueError("Item reveal times must rise")
        return self


def craft(roles=()):
    doc = store.read_json(store.ROOT / "assets/craft/directing.json")
    wanted = set(roles)
    return sorted(doc["cards"], key=lambda c: -len(wanted.intersection(c["roles"])))


def compile_scene(project, start, end, request):
    """Dry-run only. Caller inspects the result and applies exact operations through the ordinary revision API."""
    from .models import Layer
    from .design_library import layout_text
    q = SceneDecision.model_validate(request); t = project["timeline"]
    if q.base_revision != project["revision"]: raise ValueError("Scene decision revision conflict; reread scene")
    if not all(math.isfinite(x) for x in (start,end)) or not 0 <= start < end <= min(start + 60, t["total_frames"] / 30):
        raise ValueError("Compile a finite scene inside timeline, <=60 seconds")
    a,b=round(start*30),round(end*30); span=b-a
    if span < 30 or any(i.at*30 >= span-8 for i in q.items): raise ValueError("Scene/item reveal leaves insufficient visible frames")
    existing={l["id"]:l for l in t["layers"]}
    footage=None
    if q.footage_asset_id:
        footage=next((x for x in project['assets'] if x['id']==q.footage_asset_id),None)
        if q.technique!='quantity_focus' or len(q.items)!=1 or not footage or footage['kind'] not in ('image','video'):
            raise ValueError('Footage panel requires one quantity and an existing image/video asset')
        if footage['kind']=='video' and q.footage_source_start+(b-a)/30>float(footage.get('duration') or 0)+.02:
            raise ValueError('Footage panel exceeds the actual source duration')
    ops=[]
    for identity in q.replace_layer_ids:
        l=existing.get(identity)
        if not l or l["start_frame"] < a or l["end_frame"] > b:
            raise ValueError("Replacement layers must exist and be wholly inside this window")
        ops.append({"op":"delete_layer","id":identity})
    # Typography is fitted using actual bundled font metrics, not character counts. Layout scales with canvas.
    H=t["height"]; W=t["width"]; scale=min(W,H)/1080; portrait=W<H
    measurements=[]; layers=[]
    def layer(suffix,kind,x,y,w,h,begin=a,finish=b,**extra):
        identity=q.id+"-"+suffix
        if identity in existing and identity not in q.replace_layer_ids and not (existing[identity]["start_frame"]>=a and existing[identity]["end_frame"]<=b):
            raise ValueError("Layer id collides outside this scene; choose another id")
        v={"id":identity,"kind":kind,"start_frame":begin,"end_frame":finish,"x":x,"y":y,"width":w,"height":h,"z":950,
           "effects":[{"name":"fade_in","start_frame":0,"end_frame":min(9,finish-begin-1)}],**extra}
        layers.append(Layer.model_validate(v).model_dump())
    def text(suffix,content,x,y,w,h,size,color=None,begin=a,weight=500):
        if not content: return
        size=max(18,round(size*scale))
        for fitted in range(min(300,size),max(17,round(size*.70))-1,-2):
            m=layout_text(q.font_id,content,size=fitted,width=max(100,round(w*W)-8),weight=weight)
            height=m['ascent']+m['descent']+max(0,m['line_count']-1)*fitted*1.25
            if not m['missing_glyphs'] and not m['overlong_tokens'] and height<=h*H:break
        else:
            raise ValueError(f"{suffix}: text does not fit; shorten it or change the scene layout")
        size=fitted; content='\n'.join(m['lines'])
        measurements.append({"id":q.id+"-"+suffix,"font_size":size,"box_px":[round(w*W),round(h*H)],"fit":m})
        layer(suffix,"text",x,y,w,h,begin=begin,text=content,font_id=q.font_id,font_size=size,font_weight=weight,line_height=1.25,color=color or q.ink,data={"align":"left"})
    layer("ground","shape",0,0,1,1,background=q.background,color=q.background)
    layer("rule","shape",.055,.10,.075,.006,background=q.accent,color=q.accent)
    text("heading",q.heading,.055,.135,.89,.15,58,weight=650)
    if q.technique=="chapter_route":
        cols=(2 if len(q.items)>3 else 1) if portrait else (3 if len(q.items)>4 else 2); rows=math.ceil(len(q.items)/cols)
        gap=.022; cw=(.89-gap*(cols-1))/cols; ch=min(.24,(.52-gap*(rows-1))/rows)
        for n,it in enumerate(q.items):
            x=.055+(n%cols)*(cw+gap); y=.33+(n//cols)*(ch+gap); begin=a+round(it.at*30)
            layer(f"card{n}","shape",x,y,cw,ch,begin=begin,background="#1c2a34",color="#1c2a34")
            text(f"num{n}",f"{n+1:02d}",x+.018,y+.015,cw-.035,.043,27,q.accent,begin=begin)
            text(f"label{n}",it.label,x+.018,y+.064,cw-.035,ch*.35,40,begin=begin,weight=650)
            text(f"detail{n}",it.detail,x+.018,y+ch*.64,cw-.035,ch*.29,27,q.muted,begin=begin)
            finish=a+round(q.items[n+1].at*30) if n+1<len(q.items) else b
            if finish>begin:layer(f'active{n}','shape',x,y,.0035,ch,begin=begin,finish=finish,background=q.accent,color=q.accent)
    elif q.technique=="quantity_focus":
        count=len(q.items); cw=.43 if footage else .89/count
        if footage and portrait:cw=.89
        if footage:
            box=(.055,.67,.89,.23) if portrait else (.51,.35,.435,.44)
            layer('footage',footage['kind'],*box,asset_id=footage['id'],source_start=q.footage_source_start,fit=q.footage_fit)
        for n,it in enumerate(q.items):
            x=.055+n*cw; begin=a+round(it.at*30)
            paired=footage and portrait
            text(f"value{n}",it.value,x,.29 if paired else .32,cw-.025,.15 if paired else .17,126,q.accent,begin=begin,weight=700)
            text(f"label{n}",it.label,x,.46 if paired else .52,cw-.025,.08 if paired else .10,40,begin=begin)
            text(f"detail{n}",it.detail,x,.56 if paired else .65,cw-.025,.08 if paired else .12,29,q.muted,begin=begin)
            if it.percent is not None:
                bar_y=.64 if paired else .81
                layer(f"bar-base{n}","shape",x,bar_y,cw-.04,.018 if paired else .025,begin=begin,background="#33434e",color="#33434e")
                if it.percent>0:layer(f"bar{n}","shape",x,bar_y,(cw-.04)*it.percent/100,.018 if paired else .025,begin=begin,background=q.accent,color=q.accent)
    else:
        for n,it in enumerate(q.items):
            x=.055 if portrait else .055+n*.46; y=.32+n*.27 if portrait else .33; w=.89 if portrait else .43; h=.245 if portrait else .48
            begin=a+round(it.at*30)
            layer(f"panel{n}","shape",x,y,w,h,begin=begin,background="#1c2a34",color="#1c2a34")
            text(f"label{n}",it.label,x+.02,y+.02,w-.04,h*.15,31,q.accent,begin=begin,weight=650)
            text(f"record{n}",it.detail,x+.02,y+h*.23,w-.04,h*.49,40,begin=begin)
            text(f"source{n}",it.source,x+.02,y+h*.80,w-.04,h*.17,23,q.muted,begin=begin)
    text("source",q.source,.055,.915,.89,.045,22,q.muted)
    ops += [{"op":"upsert_layer","layer":l} for l in layers]
    if len(ops)>100: raise ValueError("Scene exceeds one atomic edit batch")
    plan={"id":"direction-"+uuid.uuid4().hex[:20],"project_id":project["id"],"base_revision":q.base_revision,
          "window_frames":[a,b],"request":q.model_dump(),"operations":ops,"measurements":measurements,
          "timeline_hash":narrative.digest(t),"narrative":narrative.context(project["id"],t,start,end),
          "preview_frames":sorted(set([a+min(12,span-1),(a+b)//2,b-1]+[min(b-1,a+round(i.at*30)+10) for i in q.items])),
          "next":"Apply operations with patch_timeline at base_revision, preview these frames and listen to the moving scene. No project was changed."}
    f=store.DATA/"direction-plans"/(plan["id"]+".json");store.write_json(f,plan)
    return {**plan,"measurement_path":str(f),"path":str(f)}


def sample_frames(t,start,end,budget=6):
    """Bounded event-aware sampling with endpoints and coverage. A schedule, not a claim to understand action."""
    a,b=round(start*30),round(end*30)-1
    if not all(math.isfinite(x) for x in (start,end)) or a<0 or b<a or b>=t['total_frames'] or not 2<=budget<=8:
        raise ValueError('Sampling requires an in-range window of at least one frame, budget2..8')
    candidates={a,b,(a+b)//2}
    for s in t["shots"]:
        for f in (s["start_frame"]-1,s["start_frame"]+2):
            if a<=f<=b:candidates.add(f)
    for l in t["layers"]:
        f=l["start_frame"]+10
        if a<=f<=b:candidates.add(f)
    candidates.update(round(a+(b-a)*k/(budget-1)) for k in range(budget))
    selected={a,b}
    cuts=[s['start_frame'] for s in t['shots'] if a+1<s['start_frame']<b-2]
    if cuts:
        middle=min(cuts,key=lambda f:abs(f-(a+b)/2))
        for f in (middle-1,middle+2):
            if len(selected)<budget:selected.add(f)
    while len(selected)<min(budget,len(candidates)):
        selected.add(max(candidates-selected,key=lambda f:(min(abs(f-s) for s in selected),-f)))
    return sorted(selected)


def evidence(path,t,start,end,frames=6,width=640,listen=False):
    from PIL import Image,ImageDraw
    from .study import _grab
    from .media import probe,sha256,command,FFMPEG
    source=Path(path).resolve(strict=True);info=probe(source)
    if end>float(info["format"]["duration"])+.001:raise ValueError("Evidence range exceeds supplied video")
    st=source.stat();times=[f/30 for f in sample_frames(t,start,end,frames)]
    key=narrative.digest(['evidence-v2',str(source),st.st_size,st.st_mtime_ns,times,width,listen])[:24]
    out=store.DATA/"direction-evidence"/key;manifest=out/"evidence.json"
    from filelock import FileLock
    out.mkdir(parents=True,exist_ok=True)
    with FileLock(str(out/"build.lock"),timeout=120):
        if manifest.exists():
            saved=store.read_json(manifest)
            if all(Path(f).is_file() for f in [saved['sheet'],*saved['frames'],*([saved['audio']] if saved.get('audio') else [])]):
                return {**saved,"cached":True}
        cells=[];frame_paths=[]
        for i,second in enumerate(times):
            # _grab seeks at millisecond precision; round slightly down so the final frame isn't skipped.
            pixels=_grab(source,max(0,second-.001),width)
            if pixels is None:raise ValueError(f"Could not decode {second}; no empty frame substituted")
            im=Image.fromarray(pixels);f=out/f"frame-{i}.png";im.save(f);frame_paths.append(str(f))
            cell=Image.new("RGB",(im.width,im.height+26),"#10171d");cell.paste(im,(0,26))
            ImageDraw.Draw(cell).text((8,6),f"{second:08.3f}s",fill="white");cells.append(cell)
        sheet=Image.new("RGB",(cells[0].width*2,cells[0].height*math.ceil(len(cells)/2)),"#10171d")
        for i,im in enumerate(cells):sheet.paste(im,((i%2)*im.width,(i//2)*im.height))
        sheet_path=out/"sheet.jpg";sheet.save(sheet_path,quality=88)
        audio=None
        if listen and any(s["codec_type"]=="audio" for s in info["streams"]):
            audio=out/"audio.wav"
            command([FFMPEG,"-y","-v","error","-ss",start,"-i",source,"-t",min(30,end-start),"-vn","-ac","1","-ar","16000",audio],timeout=120)
        result={"sheet":str(sheet_path),"frames":frame_paths,"times":times,"audio":str(audio) if audio else None,
                "audio_window":[start,min(end,start+30)] if audio else None,
                "source_sha256":sha256(source),"source_path":str(source),"sample_method":"Endpoints, cut/reveal candidates and temporal coverage; not exhaustive motion observation",
                "source_correspondence":"Caller supplied video. Use matching revision/render hash before treating it as current project output.",
                "cached":False}
        store.write_json(manifest,result)
    return result
