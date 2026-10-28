import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Composition, Freeze, Img, OffthreadVideo, Sequence, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig, delayRender, continueRender, cancelRender} from 'remotion';
const FX = require('./effects.cjs');
const DS = require('./design.cjs');
import {Scene3D} from './Scene3D';

type Props = {timeline: any; config: any; fonts?:any[]; media: Record<string, {src:string; kind:string; alpha?:boolean}>};

const Shot = ({shot, media, title, background}: any) => {
  const frame = useCurrentFrame();
  const p = Math.min(1, frame/Math.max(1, shot.end_frame-shot.start_frame-1));
  const eased = .5-.5*Math.cos(p*Math.PI);
  const scale = shot.fit === 'contain' || shot.motion === 'hold' ? 1 : shot.motion === 'pull' ? 1.075-.075*eased : 1+.075*eased;
  const asset = media[shot.asset_id];
  const visualStyle: React.CSSProperties = {width:'100%', height:'100%', objectFit:shot.fit,
    objectPosition:`${shot.focus_x*100}% ${shot.focus_y*100}%`, transform:`scale(${scale}) translateX(${shot.motion==='pan' ? (eased-.5)*3 : 0}%)`};
  const px=FX.pixelFilters(shot,frame),shotStyle=FX.withPixel({...FX.styleAt(shot,frame)},px);  // tritone, halation... on the picture
  return <AbsoluteFill style={{overflow:'hidden', background:background||'#102322'}}>{px.defs&&<div style={{position:'absolute',width:0,height:0}} dangerouslySetInnerHTML={{__html:px.defs}}/>}<AbsoluteFill style={shotStyle}>
    {asset ? asset.kind === 'video' ? (shot.freeze ? <Freeze frame={0}><OffthreadVideo src={staticFile(asset.src)} transparent={asset.alpha||false} muted trimBefore={Math.round(shot.source_start*30)} style={visualStyle}/></Freeze>
      : <OffthreadVideo src={staticFile(asset.src)} transparent={asset.alpha||false} muted playbackRate={shot.playback_rate||1} trimBefore={Math.round(shot.source_start*30)} style={visualStyle}/>)
      : <Img src={staticFile(asset.src)} style={visualStyle}/>
      : shot.text ? <AbsoluteFill style={{background:'linear-gradient(135deg,#102e2c,#24524b)',padding:'12% 9%', justifyContent:'center'}}>
        <div style={{fontSize:32,color:'#a9e6c8',marginBottom:32}}>{title}</div>
        <div style={{fontSize:72,fontWeight:700,lineHeight:1.22}}>{shot.text}</div>
      </AbsoluteFill> : null}
    <AbsoluteFill style={{pointerEvents:'none'}} dangerouslySetInnerHTML={{__html:FX.texture(shot,frame)}}/>
  </AbsoluteFill></AbsoluteFill>;
};

// Layers attached to a shot render inside its transform, in shot-local time, so push/whip/zoom move them too.
// A layer reaching the shot end keeps running through a live outgoing overlap.
const ShotLayers = ({shot,layers,media,design}:any) => <>{(layers||[]).filter((l:any)=>l.attach_shot===shot.id).sort((a:any,b:any)=>a.z-b.z).map((l:any)=>
  <Sequence key={l.id} from={l.start_frame-shot.start_frame} durationInFrames={l.end_frame-l.start_frame+(l.end_frame>=shot.end_frame?90:0)} layout="none"><Layer layer={l} media={media} design={design}/></Sequence>)}</>;

const ShotWithTransition = ({shot,previous,media,title,background,layers,design}:any) => {
  const f=useCurrentFrame();
  const active=previous && shot.transition && f<shot.transition.duration_frames;
  const previousLength=previous?previous.end_frame-previous.start_frame:0;
  // live: the outgoing shot keeps running past its cut from its source handle; freeze: hold its last frame.
  const outgoing=active && (shot.transition.mode==='live'
    ? <Sequence from={-previousLength} layout="none"><Shot shot={previous} media={media} title={title} background={background}/><ShotLayers shot={previous} layers={layers} media={media} design={design}/></Sequence>
    : <Freeze frame={previousLength-1}><Shot shot={previous} media={media} title={title} background={background}/><ShotLayers shot={previous} layers={layers} media={media} design={design}/></Freeze>);
  return <AbsoluteFill>
    {active && <AbsoluteFill style={{isolation:'isolate',...FX.transitionOutStyle(shot.transition,f)}}>{outgoing}</AbsoluteFill>}
    <AbsoluteFill style={{isolation:'isolate',...(active?FX.transitionStyle(shot.transition,f):{})}}><Shot shot={shot} media={media} title={title} background={background}/><ShotLayers shot={shot} layers={layers} media={media} design={design}/></AbsoluteFill>
  </AbsoluteFill>;
};

// Compositing context for parenting and track mattes: every layer by id and the matte sources to hide, refreshed by the
// root on each render before any layer renders (parents and mattes may live in other sequences).
let LAYERS_BY_ID:any={};let MATTE_HIDDEN=new Set<string>();let LAYERS_SRC:any=null;
const Layer = ({layer:raw,media,design}:any) => {
  const canvas=useVideoConfig();
  const layer=DS.resolve(raw,design,canvas.width,canvas.height);
  const local=useCurrentFrame(),g=local+raw.start_frame;
  const f=FX.stepFrame(layer,local,design);
  const comp=FX.composite(raw,f,g,{byId:LAYERS_BY_ID,W:canvas.width,H:canvas.height,resolve:(l:any)=>DS.resolve(l,design,canvas.width,canvas.height)});
  if(layer.kind==='caption'&&layer.data?.pages&&!layer.data.pages.some((p:any)=>f>=p.start_frame&&f<p.end_frame))return null;
  const asset=media[layer.asset_id];
  const style:any={position:'absolute',left:`${layer.x*100}%`,top:`${layer.y*100}%`,width:`${layer.width*100}%`,height:`${layer.height*100}%`,
    zIndex:layer.z,mixBlendMode:FX.blendCss(layer.blend),color:layer.color,background:(layer.kind==='caption'||layer.kind==='callout')?'transparent':layer.background,fontSize:layer.font_size,whiteSpace:'pre-wrap',...layer._type,...FX.styleAt(layer,f,false,LAYERS_BY_ID)};
  const {_keyFilter,...compStyle}=comp.style;Object.assign(style,compStyle);
  if(_keyFilter)style.filter=`${_keyFilter} ${style.filter==='none'?'':style.filter}`.trim();
  if(MATTE_HIDDEN.has(raw.id))style.visibility='hidden';
  const mediaStyle:any={width:'100%',height:'100%',objectFit:layer.fit};
  return <>{comp.defs&&<div style={{position:'absolute',width:0,height:0}} dangerouslySetInnerHTML={{__html:comp.defs}}/>}<div style={style}>{layer.kind==='scene3d'?<Scene3D data={layer.data} media={media} width={Math.round(layer.width*canvas.width)} height={Math.round(layer.height*canvas.height)}/>:asset?asset.kind==='video'?<OffthreadVideo src={staticFile(asset.src)} transparent={asset.alpha||false} muted trimBefore={Math.round(layer.source_start*30)} playbackRate={layer.playback_rate} style={mediaStyle}/>:<Img src={staticFile(asset.src)} style={mediaStyle}/>:<div style={{width:'100%',height:'100%'}} dangerouslySetInnerHTML={{__html:FX.widget({...layer,_canvas_width:canvas.width,_canvas_height:canvas.height},f)}}/>}<div style={{position:'absolute',inset:0,pointerEvents:'none'}} dangerouslySetInnerHTML={{__html:FX.texture(layer,f)}}/></div></>;
};

const Overlay = ({overlay}:any) => {
  const f = useCurrentFrame();
  const duration = overlay.end_frame-overlay.start_frame;
  const fade = overlay.animation === 'none' ? 1 : Math.min(1, f/8, (duration-f)/8);
  const y = overlay.animation === 'rise' ? interpolate(Math.min(f,12),[0,12],[24,0]) : 0;
  return <div style={{position:'absolute',left:`${overlay.x*100}%`,top:`${overlay.y*100}%`,width:`${overlay.width*100}%`,
    color:overlay.color,background:overlay.background,fontSize:overlay.font_size,padding:24,borderRadius:16,
    opacity:fade,transform:`translateY(${y}px)`,whiteSpace:'pre-wrap'}}>{overlay.text}</div>;
};

export const AgentVideo = ({timeline,config,media,fonts=[]}:Props) => {
  const [fontHandle]=useState(()=>delayRender('Load verified local design fonts'));
  useEffect(()=>{DS.loadFonts(fonts,staticFile).then(()=>continueRender(fontHandle)).catch(cancelRender);},[fontHandle,JSON.stringify(fonts)]);
  // Rebuilt only when the timeline changes, so per-layer runtime caches (follow-through, IK) stay valid across frames.
  if(LAYERS_SRC!==timeline.layers){LAYERS_SRC=timeline.layers;
    LAYERS_BY_ID=Object.fromEntries((timeline.layers||[]).map((l:any)=>[l.id,l]));
    MATTE_HIDDEN=new Set((timeline.layers||[]).filter((l:any)=>l.matte&&l.matte.hide_source!==false).map((l:any)=>l.matte.source));}
  const f = useCurrentFrame();
  const timedCaption=(timeline.layers||[]).some((l:any)=>l.kind==='caption'&&f>=l.start_frame&&f<l.end_frame&&(!l.data?.pages||l.data.pages.some((p:any)=>f-l.start_frame>=p.start_frame&&f-l.start_frame<p.end_frame)));
  const cue = config.captions && !timedCaption && timeline.cues.find((c:any)=>f>=Math.ceil(c.start*30) && f<Math.ceil(c.end*30));
  return <AbsoluteFill style={{color:'white',fontFamily:timeline.design?.font_family||'Segoe UI, sans-serif',background:timeline.design?.background||'#102322'}}>
    <div style={{position:'absolute',width:0,height:0}} dangerouslySetInnerHTML={{__html:FX.filterDefs()}}/>
    {timeline.shots.map((s:any,i:number)=><Sequence key={s.id} from={s.start_frame} durationInFrames={s.end_frame-s.start_frame}>
      <ShotWithTransition shot={s} previous={timeline.shots[i-1]} media={media} title={config.title} background={timeline.design?.background} layers={timeline.layers} design={timeline.design}/></Sequence>)}
    {(timeline.layers||[]).filter((l:any)=>!l.attach_shot).map((l:any)=><Sequence key={l.id} from={l.start_frame} durationInFrames={l.end_frame-l.start_frame} layout="none"><Layer layer={l} media={media} design={timeline.design}/></Sequence>)}
    {(timeline.overlays || []).map((o:any)=><Sequence key={o.id} from={o.start_frame} durationInFrames={o.end_frame-o.start_frame}>
      <Overlay overlay={o}/></Sequence>)}
    {cue && <div style={{position:'absolute',zIndex:1100,bottom:'17%',left:'8%',width:'84%',textAlign:'center',fontSize:timeline.width>timeline.height ? 62 : 50,
      fontWeight:700,lineHeight:1.35,whiteSpace:'pre-wrap'}}><span style={{background:'rgba(10,22,26,.84)',padding:'8px 16px',boxDecorationBreak:'clone'}}>{cue.text}</span></div>}
  </AbsoluteFill>;
};

const Root = () => <Composition id="AgentVideo" component={AgentVideo} durationInFrames={30} fps={30} width={1080} height={1920}
  defaultProps={{timeline:{shots:[],cues:[],overlays:[],width:1080,height:1920,total_frames:30},config:{},media:{}}}
  calculateMetadata={({props})=>({durationInFrames:props.timeline.total_frames,width:props.timeline.width,height:props.timeline.height,fps:props.timeline.fps})}/>;
registerRoot(Root);
