/* HTML authoring runtime: the input data can change while custom HTML/code stays intact. */
// HyperFrames calls the page ready once its own runtime settles, while this build is async (fonts, 3D assets, decoded
// held frames): __hf.buildReady holds that readiness until the timeline is registered and drawn. Without it a snapshot's
// first seek reached an empty page (round 13: a 104-shot film built in 5.4 s, and frame 706 alone came out black).
window.__hf=window.__hf||{};(window.__hf.buildReady=window.__hf.buildReady||{}).editvideo=(async function(){
 const {timeline:t,config:c,media:m}=window.EditVideoInput,FX=window.EditVideoFX,root=document.getElementById('root');let BY_ID=null;const HIDDEN=new Set((t.layers||[]).filter(l=>l.matte&&l.matte.hide_source!==false).map(l=>l.matte.source));root.insertAdjacentHTML('beforebegin',FX.filterDefs());
 const DS=window.EditVideoDesign;
 if(DS){await DS.loadFonts(window.EditVideoInput.fonts||[],s=>'public/'+s);t.layers=(t.layers||[]).map(l=>DS.resolve(l,t.design,t.width,t.height));}
 let G3;
 const G3assets=new Map();
 if(t.layers?.some(l=>l.kind==='scene3d')){G3=await import('./scene3d.js');
  // Textures/glTF load before the paused timeline is registered, so every seeked frame is complete.
  for(const l of t.layers.filter(l=>l.kind==='scene3d'))G3assets.set(l.id,await G3.loadSceneAssets(l.data,id=>'public/'+m[id].src,'public/draco/',Math.max(t.width,t.height)));}
 root.style.fontFamily=t.design?.font_family||'Segoe UI,sans-serif';root.style.background=t.design?.background||'#102322';
 const el=(tag,cls,parent=root)=>{const n=document.createElement(tag);n.className=cls;parent.appendChild(n);return n;};
// One element standing in for Remotion's nesting: an outer transform about origin o (the element's transform-origin)
// around an inner one about origin i, as outer translate(i-o) inner translate(o-i) in percentages of the same box.
const nest=(outer,o,inner,i='50% 50%')=>{const has=x=>x&&x!=='none';if(!has(inner))return has(outer)?outer:'none';
 const xy=v=>{const [x,y]=String(v||'50% 50%').split(' ').map(parseFloat);return [isNaN(x)?50:x,isNaN(y)?50:y];},[ox,oy]=xy(o),[ix,iy]=xy(i),dx=ix-ox,dy=iy-oy;
 return `${has(outer)?outer+' ':''}translate(${dx}%,${dy}%) ${inner} translate(${-dx}%,${-dy}%)`;};
 const apply=(n,s)=>Object.assign(n.style,s);
 // Shot-attached layers live in a full-frame group inside their shot's wrapper, so they take its transition and stack
 // with the shot under every global layer (Remotion: ShotLayers inside the shot's transition wrapper).
 const groups=new Map();
 const groupFor=id=>{if(!groups.has(id)){const g=el('div','shot-group',scenes.find(v=>v.item.id===id)?.wrap||root);apply(g,{position:'absolute',inset:'0',pointerEvents:'none',zIndex:String(Math.min(...t.layers.filter(l=>l.attach_shot===id).map(l=>l.z)))});groups.set(id,g);}return groups.get(id);};
 function layerFrame(item,f){if(!item.attach_shot)return f>=item.start_frame&&f<item.end_frame?f:null;
  const i=t.shots.findIndex(s=>s.id===item.attach_shot),sh=t.shots[i],nx=t.shots[i+1];let g=null;
  if(f>=sh.start_frame&&f<sh.end_frame)g=f;else if(nx?.transition&&f>=nx.start_frame&&f<nx.start_frame+nx.transition.duration_frames)g=nx.transition.mode==='live'?f:sh.end_frame-1;
  if(g===null||g<item.start_frame)return null;if(g>=item.end_frame&&!(item.end_frame>=sh.end_frame&&g>=sh.end_frame))return null;return g;}
 function visual(item,cls,layer=false){const wrap=layer?null:el('div','scene-wrap'),parent=layer?(item.attach_shot?groupFor(item.attach_shot):root):wrap,bg=layer?null:el('div','scene-bg',wrap),a0=m[item.asset_id],still=!layer&&item.freeze&&a0?.kind==='video'&&a0.posters?.['freeze:'+item.id],a=still?{...a0,kind:'image',src:a0.posters['freeze:'+item.id]}:a0,vid='video-'+(layer?'l-':'s-')+item.id,pre=a?.kind==='video'?document.getElementById(vid):null,n=pre?(parent.appendChild(pre),pre):el(a?.kind==='video'?'video':'div',cls,parent);const content=a?.kind==='video'?n:el('div','visual-content',n);
  if(content!==n)apply(content,{width:'100%',height:'100%'});
  let world,renderer,labels;
  if(item.kind==='scene3d'){const canvas=el('canvas','scene3d-canvas',content);world=G3.createWorld(item.data,G3assets.get(item.id));renderer=G3.createRenderer(canvas);renderer.setSize(Math.round(item.width*t.width),Math.round(item.height*t.height),false);G3.prepareRenderer(world,renderer,Math.round(item.width*t.width),Math.round(item.height*t.height));apply(canvas,{width:'100%',height:'100%'});labels=el('div','scene3d-labels',content);apply(labels,{position:'absolute',inset:'0',pointerEvents:'none'});}
  if(a){if(a.kind==='video'){n.src='public/'+a.src;n.muted=true;n.playsInline=true;n.id=vid;n.dataset.start=String(item.start_frame/30);n.dataset.duration=String((item.end_frame-item.start_frame)/30);n.dataset.mediaStart=String(Math.round(item.source_start*30)/30);n.dataset.playbackRate=String(item.playback_rate||1);n.dataset.trackIndex=String(layer?item.z:0);n.preload='metadata';/* not auto: past six distinct sources the held connections stalled HyperFrames' player */}
   else {const img=el('img','asset',content);img.src='public/'+a.src;apply(img,{width:'100%',height:'100%',objectFit:item.fit,objectPosition:`${(item.focus_x??.5)*100}% ${(item.focus_y??.5)*100}%`});}}
  else if(!layer&&item.text) content.innerHTML=`<div class="card"><small>${FX.esc(c.title)}</small><h1>${FX.esc(item.text)}</h1></div>`;
  // A video layer is the <video> element itself: it needs the layer's fit (Remotion applies it; without it the browser letterboxes).
  if(layer)apply(n,{left:item.x*100+'%',top:item.y*100+'%',width:item.width*100+'%',height:item.height*100+'%',zIndex:item.z,color:item.color,background:(item.kind==='caption'||item.kind==='callout')?'transparent':item.background,fontSize:item.font_size+'px',mixBlendMode:FX.blendCss(item.blend),whiteSpace:'pre-wrap',...item._type,fontSize:item.font_size+'px',...(a?.kind==='video'?{objectFit:item.fit||'contain'}:{})});
  else apply(n,{inset:'0',width:'100%',height:'100%',objectFit:item.fit,objectPosition:`${(item.focus_x??.5)*100}% ${(item.focus_y??.5)*100}%`});
  // A shot is nested as Remotion nests it: a wrapper that takes the transition (one group: a contained shot dissolves
  // in with its bands as one picture), the canvas colour behind the picture (a contained shot covers the outgoing one at
  // its sides; not on the picture element, whose effects would recolour it and which HyperFrames swaps for a frame
  // image), then the picture with its effects and its texture.
  if(wrap){apply(wrap,{position:'absolute',inset:'0',overflow:'hidden',display:'none',isolation:'isolate',zIndex:'auto'});apply(bg,{position:'absolute',inset:'0',pointerEvents:'none',background:t.design?.background||'#102322'});}
  const texture=el('div','texture',parent);apply(texture,{position:'absolute',pointerEvents:'none',...(layer?{left:item.x*100+'%',top:item.y*100+'%',width:item.width*100+'%',height:item.height*100+'%',zIndex:item.z+1}:{inset:'0',zIndex:2})});
  return {item,n,wrap,content,asset:a,layer,texture,world,renderer,labels};
 }
 const scenes=t.shots.map(s=>visual(s,'scene')),layers=(t.layers||[]).map(l=>visual(l,'layer',true)),overlays=(t.overlays||[]).map(o=>{const n=el('div','overlay');n.textContent=o.text;apply(n,{left:o.x*100+'%',top:o.y*100+'%',width:o.width*100+'%',fontSize:o.font_size+'px',color:o.color,background:o.background,zIndex:1050});return {item:o,n};});
 // Live transitions: the outgoing video keeps its source handle running through the overlap; alternate
 // tracks so Hyperframes never sees two clips overlapping on one track.
 scenes.forEach((v,i)=>{const next=t.shots[i+1];if(v.asset?.kind==='video'){v.n.dataset.trackIndex=String(i%2);if(next?.transition?.mode==='live')v.n.dataset.duration=String((v.item.end_frame-v.item.start_frame+next.transition.duration_frames)/30);}});
 const previous=el('div','scene frozen'),caption=el('div','caption');root.insertBefore(previous,root.firstChild);apply(previous,{zIndex:'auto',isolation:'isolate'});caption.style.zIndex='1100';
 // The held outgoing shot keeps its texture (vignette, grain, leaks) at its last frame, as Remotion's frozen Shot does:
 // without it a vignetted photo brightened at its edges for the length of the dissolve.
 const frozenTexture=el('div','texture',previous);
 const posterDefs=document.createElement('div');posterDefs.style.cssText='position:absolute;width:0;height:0';  // the held frame's pixel filters
 function freezeTexture(old){const last=old.end_frame-old.start_frame-1,px=FX.pixelFilters(old,last,'ev-pfx'),os=FX.withPixel(FX.styleAt(old,last),px);  // the held frame's filters
  if(!posterDefs.parentNode)root.appendChild(posterDefs);if(posterDefs.dataset.html!==px.defs){posterDefs.innerHTML=px.defs;posterDefs.dataset.html=px.defs;}
 if(frozenTexture.parentNode!==previous)previous.appendChild(frozenTexture);
  frozenTexture.style.cssText='';frozenTexture.innerHTML=FX.texture(old,last);apply(frozenTexture,{position:'absolute',inset:'0',pointerEvents:'none',zIndex:2,transform:'none',filter:'none',...os});}
 // Frozen outgoing frames of non-live transitions are decoded before the timeline is registered: an <img> created
 // during a seek is not decoded when the frame is captured (the dissolve showed an almost empty plate).
 const posters=new Map();
 for(const [i,old] of t.shots.entries()){const nx=t.shots[i+1],a=m[old.asset_id];if(!a||!nx?.transition||nx.transition.mode==='live')continue;
  const img=new Image();img.src='public/'+(a.kind==='video'?a.posters?.[old.id]||a.src:a.src);apply(img,{width:'100%',height:'100%',objectFit:old.fit,objectPosition:`${(old.focus_x??.5)*100}% ${(old.focus_y??.5)*100}%`});
  try{await img.decode();}catch(e){}posters.set(old.id,img);}
 function draw(f){
  const current=t.shots.findIndex(s=>f>=s.start_frame&&f<s.end_frame),s=t.shots[current],local=s?f-s.start_frame:0;
  const transitioning=current>0&&s.transition&&local<s.transition.duration_frames;
  const live=transitioning&&s.transition.mode==='live',out=transitioning?FX.transitionOutStyle(s.transition,local):{};
  previous.style.display=transitioning&&!live?'block':'none';
  if(transitioning&&!live){apply(previous,{transform:'none',filter:'none',opacity:1,...out});const old=t.shots[current-1],a=m[old.asset_id];if(posters.has(old.id)){const img=posters.get(old.id);if(previous.firstChild!==img)previous.replaceChildren(img);const opx=FX.pixelFilters(old,old.end_frame-old.start_frame-1,'ev-pfx'),os=FX.withPixel(FX.styleAt(old,old.end_frame-old.start_frame-1),opx);if(!posterDefs.parentNode)root.appendChild(posterDefs);if(posterDefs.dataset.html!==opx.defs){posterDefs.innerHTML=opx.defs;posterDefs.dataset.html=opx.defs;}
   // the held last frame keeps the outgoing shot's push/pull/pan at its end, as Remotion's frozen shot does
   const oe=old.motion==='hold'||old.fit==='contain'?'':old.motion==='pull'?'scale(1)':old.motion==='pan'?'scale(1.075) translateX(1.5%)':'scale(1.075)';
   apply(img,{transform:'none',filter:'none',transformOrigin:'50% 50%',...os,...(oe?{transform:nest(os.transform,os.transformOrigin,oe)}:{})});}else previous.innerHTML=a?`<img src="public/${FX.esc(a.kind==='video'?a.posters?.[old.id]||a.src:a.src)}" style="width:100%;height:100%;object-fit:${old.fit};object-position:${old.focus_x*100}% ${old.focus_y*100}%">`:old.text?`<div class="card"><small>${FX.esc(c.title)}</small><h1>${FX.esc(old.text)}</h1></div>`:'';
   freezeTexture(old);}
  for(const v of scenes){const active=v.item===s,outgoing=live&&v.item===t.shots[current-1],vl=outgoing?f-v.item.start_frame:local;v.n.style.display=active||outgoing?'block':'none';v.texture.style.display=active||outgoing?'block':'none';v.wrap.style.display=active||outgoing?'block':'none';if(!active&&!outgoing){if(v.pxHtml){v.pxDefs.innerHTML='';v.pxHtml='';}continue;}const px=FX.pixelFilters(v.item,vl),style=FX.withPixel(FX.styleAt(v.item,vl),px),origin=style.transformOrigin||'50% 50%';if(!v.pxDefs){v.pxDefs=document.createElement('div');apply(v.pxDefs,{position:'absolute',width:'0',height:'0'});root.appendChild(v.pxDefs);}if(v.pxHtml!==px.defs){v.pxDefs.innerHTML=px.defs;v.pxHtml=px.defs;}
   // the transition on the wrapper, the effects on the picture: they compose as in Remotion (a held zoom stays through a
   // push or whip instead of dropping to 1x for its length)
   const tr=transitioning?(outgoing?out:FX.transitionStyle(s.transition,local)):{};
   // clip-path/mask have -webkit- aliases in Chrome: both of a pair get one value, or the reset of one erases the other
   const clip=tr.clipPath??tr.WebkitClipPath??'none',mask=tr.maskImage??tr.WebkitMaskImage??'none';
   apply(v.wrap,{transform:'none',filter:'none',opacity:1,transformOrigin:'50% 50%',...tr,clipPath:clip,WebkitClipPath:clip,maskImage:mask,WebkitMaskImage:mask});
   apply(v.n,{transform:'none',filter:'none',...style});v.texture.innerHTML=FX.texture(v.item,vl);apply(v.texture,style);
   const p=Math.min(1,vl/Math.max(1,v.item.end_frame-v.item.start_frame-1)),e=.5-.5*Math.cos(p*Math.PI),scale=v.item.motion==='hold'||v.item.fit==='contain'?1:v.item.motion==='pull'?1.075-.075*e:1+.075*e;
   const push=`scale(${scale}) translateX(${v.item.motion==='pan'?(e-.5)*3:0}%)`;
   if(v.asset?.kind!=='video')apply(v.content,{width:'100%',height:'100%',transform:push});
   // a video shot is the <video> itself: its push/pull/pan composes inside the effect/transition transform (Remotion: the
   // wrapper carries effects, the media element the push; without this a pushed video shot stayed still here)
   else if(scale!==1||v.item.motion==='pan')v.n.style.transform=nest(style.transform,origin,push);
   if(v.asset?.kind==='video'&&v.item.playback_rate!==1){v.n.playbackRate=v.item.playback_rate;const target=Math.round(v.item.source_start*30)/30+vl/30*v.item.playback_rate;if(Math.abs(v.n.currentTime-target)>.02)v.n.currentTime=target;}
  }
  // attached groups ride their shot's wrapper; while a non-live transition holds the outgoing shot's last frame, its
  // group sits on that frozen picture, under the incoming shot (Remotion freezes Shot and ShotLayers together)
  for(const [sid,g] of groups){const home=scenes.find(v=>v.item.id===sid)?.wrap||root,held=transitioning&&!live&&t.shots[current-1]?.id===sid,want=held?previous:home;if(g.parentNode!==want)want.appendChild(g);}
  for(const v of layers){const g=layerFrame(v.item,f),active=g!==null&&(!(v.item.kind==='caption'&&v.item.data?.pages)||v.item.data.pages.some(p=>g-v.item.start_frame>=p.start_frame&&g-v.item.start_frame<p.end_frame));v.n.style.display=active?'block':'none';v.texture.style.display=active?'block':'none';if(!active)continue;const local=FX.stepFrame(v.item,g-v.item.start_frame,t.design);BY_ID=BY_ID||Object.fromEntries((t.layers||[]).map(l=>[l.id,l]));const style=FX.styleAt(v.item,local,false,BY_ID);const comp=FX.composite(v.item,local,g,{byId:BY_ID,W:t.width,H:t.height,resolve:l=>l});const {_keyFilter,...compStyle}=comp.style;Object.assign(style,compStyle);if(_keyFilter)style.filter=(_keyFilter+' '+(style.filter==='none'?'':style.filter)).trim();if(HIDDEN.has(v.item.id))style.visibility='hidden';if(comp.defs!==v.defsHtml){if(!v.defs){v.defs=document.createElement('div');apply(v.defs,{position:'absolute',width:'0',height:'0'});root.appendChild(v.defs);}v.defs.innerHTML=comp.defs;v.defsHtml=comp.defs;}apply(v.n,style);apply(v.texture,style);v.texture.innerHTML=FX.texture(v.item,local);if(v.world){G3.drawPose(v.world,local,(v.item.width*t.width)/(v.item.height*t.height));G3.renderWorld(v.world,v.renderer);v.labels.innerHTML=G3.projectLabels(v.world,v.item.width*t.width,v.item.height*t.height).filter(l=>l.visible).map(l=>`<div style="position:absolute;left:${l.x}px;top:${l.y}px;transform:translateX(-50%);white-space:nowrap;font-size:${v.item.data.label_font_size}px;color:${v.item.data.label_color};font-weight:600;background:${v.item.data.background};padding:4px 10px;border-radius:4px;opacity:${l.alpha}">${FX.esc(l.text)}</div>`).join('');}else if(!v.asset)v.content.innerHTML=FX.widget({...v.item,_canvas_width:t.width,_canvas_height:t.height},local);else if(v.asset.kind==='video'&&v.item.playback_rate!==1){v.n.playbackRate=v.item.playback_rate;v.n.currentTime=Math.round(v.item.source_start*30)/30+local/30*v.item.playback_rate;}}
  for(const {item:o,n} of overlays){const f0=f-o.start_frame,d=o.end_frame-o.start_frame;n.style.display=f0>=0&&f0<d?'block':'none';apply(n,{opacity:o.animation==='none'?1:Math.max(0,Math.min(1,f0/8,(d-f0)/8)),transform:`translateY(${o.animation==='rise'?24*(1-Math.min(1,Math.max(0,f0/12))):0}px)`});}
  const timedCaption=(t.layers||[]).some(l=>l.kind==='caption'&&f>=l.start_frame&&f<l.end_frame&&(!l.data?.pages||l.data.pages.some(p=>f-l.start_frame>=p.start_frame&&f-l.start_frame<p.end_frame)));
  const cue=c.captions&&!timedCaption&&t.cues.find(c=>f>=Math.ceil(c.start*30)&&f<Math.ceil(c.end*30));caption.innerHTML=cue?'<span>'+FX.esc(cue.text)+'</span>':'';
 }
 const clock={seconds:0},tl=gsap.timeline({paused:true});tl.to(clock,{seconds:t.total_frames/30,duration:t.total_frames/30,ease:'none',onUpdate:()=>draw(Math.min(t.total_frames-1,Math.floor(clock.seconds*30+.01)))},0);
 window.__timelines=window.__timelines||{};window.__timelines.AgentVideo=tl;window.EditVideoDraw=draw;draw(0);
 // Snapshots and renders await hf-seek waitUntil() promises before capturing a seeked frame: each seek waits until the
 // stills it shows (freeze frames, images, the held outgoing frame) are decoded. The listener runs inside the seek; the
 // visible set is read a microtask later, once the seek has drawn the requested frame.
 addEventListener('hf-seek',e=>e.detail?.waitUntil?.(Promise.resolve().then(()=>Promise.all([...root.querySelectorAll('img')].filter(i=>i.checkVisibility?.()!==false).map(i=>i.decode().catch(()=>{}))))));
})();
