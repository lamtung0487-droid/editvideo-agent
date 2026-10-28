/* Portable deterministic render functions. No network, clocks or mutable random state. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.EditVideoFX=api;})(typeof window==='undefined'?globalThis:window,function(){
 const defaults={white_flash:1,chroma_split:9,impact_shake:24,impact_zoom:.08,fade_in:1,fade_out:1,rise:80,drop:80,slide_left:180,slide_right:180,pop:.2,spring:.3,blur_in:18,rotate_in:15,flip_x:80,flip_y:80,zoom_in:.1,zoom_out:.1,pan_x:100,pan_y:100,float:12,pulse:.04,shake:8,orbit:20,spin:360,skew:10,wipe_left:1,wipe_right:1,wipe_up:1,wipe_down:1,iris:1,typewriter:1,tracking_in:16,highlight:.5,glow:24,shadow:20,brightness:1.1,contrast:1.1,saturate:1.2,grayscale:1,sepia:.7,hue:20,warm:.25,cool:.25,invert:1,blur:8,rounded:32,circle:1,vignette:.45,scanlines:.2,letterbox:.08,border:4,progress:1,flash:.5,diagonal_reveal:1,diamond_reveal:1,soft_edge_reveal:1,slide_spring:120,focus_zoom:.08,defocus_pulse:8,fade_pulse:.25,light_sweep:.2,paper_grain:.08,text_outline:2,marker_reveal:.35,exposure:0,handheld:6,rgb_split:4,glitch:18,decode:1,motion_blur:180};
 Object.assign(defaults,{color_to:1,text_animate:30,gate_weave:1,boil:4,bloom:16,jitter:3,clock_wipe:1,tracking:.2,luma_alpha:1,tint_fill:1,highlight_glow:1,tritone:1,heat_distortion:6,light_wrap:.6,halation:.7});
 Object.assign(defaults,{mask_reveal:110,char_spring:.6,word_reveal:24,line_reveal:24,character_reveal:12,text_gradient:1,underline_draw:.06,radial_glow:.18,edge_feather:.08});
 const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v));
 // smooth=smoothstep, ease_out=power1.out, snappy=power4.out, dramatic=expo.out, bouncy=back.out(1.7), springy=elastic.out,
 // dreamy=sine.inOut, ease_in_out=power2.inOut, stepped=6-step stop-motion hold. Overshooting curves are for transforms, not numbers.
 const ease=(p,k)=>k==='smooth'?p*p*(3-2*p):k==='ease_in'?p*p:k==='ease_out'?1-(1-p)*(1-p):k==='snappy'?1-Math.pow(1-p,4):k==='dramatic'?(p>=1?1:1-Math.pow(2,-10*p))
  :k==='bouncy'?1+2.70158*Math.pow(p-1,3)+1.70158*Math.pow(p-1,2):k==='springy'?(p<=0?0:p>=1?1:Math.pow(2,-10*p)*Math.sin((p*10-.75)*2.0944)+1)
  :k==='dreamy'?-(Math.cos(Math.PI*p)-1)/2:k==='ease_in_out'?(p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2):k==='stepped'?Math.min(1,Math.floor(p*6+1e-9)/6):p;
 function bezier(p,b){if(p<=0||p>=1)return p;const [x1,y1,x2,y2]=b;let lo=0,hi=1,t=p;
  for(let i=0;i<40;i++){t=(lo+hi)/2;const x=3*(1-t)*(1-t)*t*x1+3*(1-t)*t*t*x2+t*t*t;if(x<p)lo=t;else hi=t;}
  return 3*(1-t)*(1-t)*t*y1+3*(1-t)*t*t*y2+t*t*t;}
 const curve=(p,k,b)=>b?bezier(p,b):ease(p,k);
 const phase=(e,f)=>curve(clamp((f-(e.start_frame||0))/Math.max(1,e.end_frame-(e.start_frame||0))),e.easing||'smooth',e.bezier);
 // Smooth seeded noise in [-1,1] (sum of three incommensurate sines): organic handheld drift, never per-frame jitter.
 const smoothNoise=(seed,t,ch)=>{let v=0;for(let k=0;k<3;k++){const fr=[1,2.37,4.13][k],ph=random(seed,ch*7+k)*Math.PI*2;v+=Math.sin(2*Math.PI*fr*t+ph)/[1.6,2.6,4.4][k];}return v/1.2;};
 // Colour interpolation in OKLab (perceptually even: no muddy midpoint between saturated colours).
 const hexRgb=h=>{const s=String(h||'#ffffff').replace('#','');const v=s.length===3?s.split('').map(c=>c+c).join(''):s.padEnd(6,'f');return [0,2,4].map(i=>parseInt(v.slice(i,i+2),16)/255);};
 const toLin=c=>c<=.04045?c/12.92:Math.pow((c+.055)/1.055,2.4),toSrgb=c=>c<=.0031308?12.92*c:1.055*Math.pow(c,1/2.4)-.055;
 function oklab([r,g,b]){[r,g,b]=[r,g,b].map(toLin);const l=Math.cbrt(.4122214708*r+.5363325363*g+.0514459929*b),m=Math.cbrt(.2119034982*r+.6806995451*g+.1073969566*b),s=Math.cbrt(.0883024619*r+.2817188376*g+.6299787005*b);
  return [.2104542553*l+.7936177850*m-.0040720468*s,1.9779984951*l-2.4285922050*m+.4505937099*s,.0259040371*l+.7827717662*m-.8086757660*s];}
 function fromOklab([L,A,B]){const l=(L+.3963377774*A+.2158037573*B)**3,m=(L-.1055613458*A-.0638541728*B)**3,s=(L-.0894841775*A-1.2914855480*B)**3;
  return [4.0767416621*l-3.3077115913*m+.2309699292*s,-1.2684380046*l+2.6097574011*m-.3413193965*s,-.0041960863*l-.7034186147*m+1.7076147010*s].map(c=>Math.round(clamp(toSrgb(clamp(c)))*255));}
 const mixColor=(a,b,t)=>{const p=oklab(hexRgb(a)),q=oklab(hexRgb(b)),[r,g,bb]=fromOklab(p.map((v,i)=>v+(q[i]-v)*clamp(t)));return `rgb(${r},${g},${bb})`;};
 const rgba=(h,a)=>{const [r,g,b]=hexRgb(h);return `rgba(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)},${a})`;};
 const random=(seed,n)=>{let x=(Math.imul((seed|0)+n+1,1664525)+1013904223)|0;x^=x>>>16;x=Math.imul(x,2246822507);return (x>>>0)/4294967296;};
 function track(points,f){if(f<=points[0].frame)return points[0].value;for(let i=1;i<points.length;i++){if(f<=points[i].frame){const a=points[i-1],b=points[i];return a.value+(b.value-a.value)*curve((f-a.frame)/(b.frame-a.frame),b.easing,b.bezier);}}return points[points.length-1].value;}
 // Track modifiers (After Effects expression equivalents, frame-deterministic):
 //  loop cycle|pingpong|offset repeats the keyed span after the last key (loopOut);
 //  inertia {amount, period_frames, decay} adds a damped oscillation after every key that is reached with velocity
 //  (inertial bounce: initial slope = amount × arrival velocity, amplitude × decay per period);
 //  wiggle {amp, hz, seed} adds smooth seeded noise.
 function trackMod(points,f,m){if(!m)return track(points,f);const a=points[0],z=points[points.length-1],span=z.frame-a.frame;let ff=f,base=0;
  if(m.loop&&span>0&&f>z.frame){const k=Math.floor((f-a.frame)/span),r=(f-a.frame)-k*span;
   if(m.loop==='pingpong')ff=a.frame+(k%2?span-r:r);else{ff=a.frame+r;if(m.loop==='offset')base=k*(z.value-a.value);}}
  let v=track(points,ff)+base;
  const I=m.inertia;if(I&&points.length>1){let j=-1;for(let i=1;i<points.length;i++)if(points[i].frame<=ff)j=i;
   if(j>0){const t=ff-points[j].frame,next=points[j+1];if(t>0&&(!next||ff<next.frame)){const vel=track(points,points[j].frame)-track(points,points[j].frame-1);
    const P=Math.max(2,I.period_frames??8),w=2*Math.PI/P,amp=vel*(I.amount??.5)/w;v+=amp*Math.sin(w*t)*Math.pow(clamp(I.decay??.5,.01,1),t/P);}}}
  const W=m.wiggle;if(W)v+=(W.amp||0)*smoothNoise(W.seed??7,f/30*(W.hz??1),3);
  return v;}
 // Drivers (AE expression links / Blender drivers): a track computed from another layer's keyed track at the same global
 // frame: add + mul × value (or its per-frame velocity), clamped, replacing or adding to the layer's own track. Wheels roll
 // with x, a shadow shrinks as its object rises, a character leans into its own speed. Chains resolve up to 6 deep.
 const NEUTRAL={scale:1,opacity:1,scale_x:1,scale_y:1,squash:1};
 function ownTrack(it,key,f){const p=it.keyframes?.[key];return p&&p.length?trackMod(p,f,it.track_mods?.[key]):(NEUTRAL[key]??0);}
 function trackAt(it,key,f,byId,depth=0){const v=ownTrack(it,key,f),d=it.drivers?.[key];if(!d||!byId||depth>5)return v;
  const src=byId[d.source];if(!src)return v;const dur=Math.max(1,(src.end_frame||1)-(src.start_frame||0)),g=f+(it.start_frame||0)-(d.delay_frames||0);
  const val=h=>trackAt(src,d.track||key,clamp(h-(src.start_frame||0),0,dur-1),byId,depth+1);
  let dv=(d.add||0)+(d.mul??1)*(d.mode==='velocity'?val(g)-val(g-1):val(g));if(d.clamp)dv=clamp(dv,d.clamp[0],d.clamp[1]);
  return d.mix==='add'?v+dv:dv;}
 // Entrance effects hold their starting state before start_frame (like a held first keyframe): a staggered fade or rise
 // must not show the finished layer first and then blink to its start. Other effects simply begin at start_frame.
 const ENTRANCE=new Set(['fade_in','rise','drop','slide_left','slide_right','pop','spring','blur_in','rotate_in','flip_x','flip_y','zoom_out','wipe_left','wipe_right','wipe_up','wipe_down','iris','tracking_in','diagonal_reveal','diamond_reveal','soft_edge_reveal','slide_spring','clock_wipe','tracking']);
 const gz=(a,p)=>1+a>0?Math.pow(1+a,p):1+a*p;  // geometric zoom factor between 1 and 1+a
 function styleAt(item,f,raw,byId){
  let x=0,y=0,scale=1,rot=item.rotation||0,rx=0,ry=0,skew=0,opacity=item.opacity??1,filters=[],extra={},shadows=[];
  for(const e of item.effects||[]){if(f<(e.start_frame||0)&&!ENTRANCE.has(e.name))continue;
   // Accent bursts (glitch, shake) end at end_frame when they were timed (a span over one frame): a 4-frame glitch ran
   // for the rest of its clip and broke the sixth cut's news walls. A one-frame span keeps the old whole-layer meaning.
   if((e.name==='glitch'||e.name==='shake')&&e.end_frame!=null&&e.end_frame-(e.start_frame||0)>1&&f>e.end_frame)continue;
   const p=phase(e,f),a=e.params?.amount??defaults[e.name],color=e.params?.color||'#81e6be',u=Math.PI*2*(e.params?.cycles||1)*p;
   switch(e.name){
    case 'fade_in':opacity*=1-a+a*p;break;case 'fade_out':opacity*=1-a*p;break;
    case 'rise':y+=a*(1-p);break;case 'drop':y-=a*(1-p);break;case 'slide_left':x-=a*(1-p);break;case 'slide_right':x+=a*(1-p);break;
    case 'pop':scale*=1-a*(1-p);break;case 'spring':scale*=1-a*Math.exp(-7*p)*Math.cos(12*p);break;
    case 'blur_in':filters.push(`blur(${a*(1-p)}px)`);break;case 'rotate_in':rot+=a*(1-p);break;
    case 'flip_x':rx+=a*(1-p);break;case 'flip_y':ry+=a*(1-p);break;
    // Zooms interpolate on a log scale (constant ratio per frame): a linear push keeps its perceived speed to the end
    // instead of slowing as the picture grows. Endpoints are unchanged (1 and 1+amount).
    case 'zoom_in':scale*=gz(a,p);break;case 'zoom_out':scale*=gz(a,1-p);break;case 'pan_x':x+=a*(p-.5);break;case 'pan_y':y+=a*(p-.5);break;
    case 'float':y+=a*Math.sin(u);break;case 'pulse':scale*=1+a*Math.sin(u);break;
    case 'shake':x+=a*(random(e.params?.seed??7,Math.floor(f)*2)-.5)*2;y+=a*(random(e.params?.seed??7,Math.floor(f)*2+1)-.5)*2;break;
    case 'orbit':x+=a*Math.cos(u);y+=a*Math.sin(u);break;case 'spin':rot+=a*p;break;case 'skew':skew+=a*p;break;
    case 'wipe_left':extra.clipPath=`inset(0 ${(1-p)*100}% 0 0)`;break;case 'wipe_right':extra.clipPath=`inset(0 0 0 ${(1-p)*100}%)`;break;
    case 'wipe_up':extra.clipPath=`inset(${(1-p)*100}% 0 0 0)`;break;case 'wipe_down':extra.clipPath=`inset(0 0 ${(1-p)*100}% 0)`;break;
    case 'iris':extra.clipPath=`circle(${p*72}% at 50% 50%)`;break;
    case 'tracking_in':extra.letterSpacing=`${Math.min(a*(1-p),e.params?._fit_px??Infinity)}px`;break;case 'highlight':extra.backgroundColor=color;extra.boxShadow=`inset 0 -${a*50}px 0 ${color}`;break;
    case 'glow':filters.push(`drop-shadow(0 0 ${a}px ${color})`);break;case 'shadow':filters.push(`drop-shadow(0 ${a*.35}px ${a}px rgba(0,0,0,.55))`);break;
    case 'brightness':case 'contrast':case 'saturate':case 'grayscale':case 'sepia':case 'invert':filters.push(`${e.name}(${a})`);break;
    case 'hue':filters.push(`hue-rotate(${a}deg)`);break;case 'warm':filters.push(`sepia(${a}) saturate(1.12)`);break;case 'cool':filters.push(`sepia(${a}) hue-rotate(155deg)`);break;
    case 'blur':filters.push(`blur(${a}px)`);break;case 'rounded':extra.borderRadius=`${a}px`;extra.overflow='hidden';break;case 'circle':extra.clipPath='circle(50% at 50% 50%)';break;
    case 'vignette':case 'scanlines':break; // Rendered above media by texture(), not hidden behind an image.
    case 'letterbox':extra.clipPath=`inset(${a*100}% 0)`;break;case 'border':extra.border=`${a}px solid ${color}`;break;
    case 'diagonal_reveal':extra.clipPath=`polygon(0 0,${p*200}% 0,0 ${p*200}%)`;break;
    case 'diamond_reveal':extra.clipPath=`polygon(50% ${50-p*100}%,${50+p*100}% 50%,50% ${50+p*100}%,${50-p*100}% 50%)`;break;
    case 'soft_edge_reveal':extra.maskImage=`linear-gradient(90deg,#000 0%,#000 ${p*110-10}%,transparent ${p*110}%)`;extra.WebkitMaskImage=extra.maskImage;break;
    // Opacity ramps over the first ~8% of the spring: the start state sits up to `amount` px off its place and was
    // shown sharp and clipped at the frame edge (also during the hold before a delayed start).
    case 'slide_spring':x+=a*Math.exp(-7*p)*Math.cos(12*p)*(1-p);opacity*=Math.min(1,p/.08);break;
    // focus_zoom with params.cut: a hard punch-in held from start_frame (jump-cut cover, emphasis punch), no ramp.
    case 'focus_zoom':scale*=e.params?.cut?1+a:gz(a,p);extra.transformOrigin=`${(e.params?.focus_x??.5)*100}% ${(e.params?.focus_y??.5)*100}%`;break;
    case 'defocus_pulse':filters.push(`blur(${a*Math.sin(Math.PI*p)}px)`);break;
    case 'fade_pulse':opacity*=1-a*Math.sin(Math.PI*p);break;
    case 'text_outline':extra.WebkitTextStroke=`${a}px ${e.params?.color||'#101820'}`;extra.paintOrder='stroke fill';break;
    case 'marker_reveal':break; // Text-sized strip rendered by widget(), not a whole-layer band.
    case 'exposure':filters.push(`brightness(${Math.pow(2,a)})`);break;
    case 'edge_feather':{const b=e.params?.box;
     // box [x0,y0,x1,y1]: where a contained picture sits in its element; its edges on the axis that leaves bands fade
     // into the canvas (one linear mask: HyperFrames copies mask-image to a video's frame image, not mask-composite)
     if(Array.isArray(b)&&b.length===4){const v=Math.max(b[1],1-b[3])>=Math.max(b[0],1-b[2]),lo=(v?b[1]:b[0])*100,hi=(v?b[3]:b[2])*100,w=a*(hi-lo);
      extra.maskImage=`linear-gradient(${v?'to bottom':'to right'},transparent ${lo}%,#000 ${lo+w}%,#000 ${hi-w}%,transparent ${hi}%)`;}
     else if(e.params?.shape==='rect'){
      // a box (a dark field under type) fades on all four sides: the radial ellipse left ~49 % opacity at the middle of
      // each side, a visible hard edge (65 -> 92 luma within 2 px under a counter)
      const w=Math.min(50,a*100).toFixed(1);
      extra.maskImage=`linear-gradient(to right,transparent 0%,#000 ${w}%,#000 ${100-w}%,transparent 100%),linear-gradient(to bottom,transparent 0%,#000 ${w}%,#000 ${100-w}%,transparent 100%)`;
      extra.maskComposite='intersect';extra.WebkitMaskComposite='source-in';}
     else extra.maskImage=`radial-gradient(ellipse at center,#000 ${100-a*200}%,transparent 100%)`;extra.WebkitMaskImage=extra.maskImage;break;}
    case 'flash':filters.push(`brightness(${1+a*(1-p)*3})`);break;
    // white_flash: contrast(1-k) brightness(1+k) takes EVERY pixel to white at k=1 (a brightness boost alone leaves
    // dark pixels grey); impact_shake decays (strongest on the hit, still at the end); impact_zoom punches and settles.
    case 'white_flash':{const k=a*Math.pow(1-p,1.6);filters.push(`contrast(${(1-k).toFixed(4)}) brightness(${(1+k).toFixed(4)})`);break;}
    case 'impact_shake':{const env=Math.pow(1-p,2),sd=e.params?.seed??11,fr=Math.floor(f);x+=a*env*(random(sd,fr*2)-.5)*2;y+=a*env*.7*(random(sd,fr*2+1)-.5)*2;rot+=a*env*.02*(random(sd,fr*2+7)-.5)*2;break;}
    case 'impact_zoom':scale*=1+a*(1-ease(p,'ease_out'));break;
    case 'chroma_split':{const k=a*Math.pow(1-p,1.2),st=CHROMA_STEPS.reduce((q,b)=>Math.abs(b-k)<Math.abs(q-k)?b:q);if(k>=.5)filters.push(`url(#ev-rgb-${st})`);break;}
    case 'handheld':{const fq=e.params?.frequency??.6,t=f/30*fq,sd=e.params?.seed??7;x+=a*smoothNoise(sd,t,1);y+=a*.7*smoothNoise(sd,t,2);rot+=(e.params?.rotation??a*.04)*smoothNoise(sd,t,3);break;}
    case 'rgb_split':{const ang=(e.params?.angle??0)*Math.PI/180,dx=(a*Math.cos(ang)).toFixed(2),dy=(a*Math.sin(ang)).toFixed(2);filters.push(`drop-shadow(${-dx}px ${-dy}px 0 rgba(255,30,70,.7)) drop-shadow(${dx}px ${dy}px 0 rgba(0,220,255,.7))`);break;}
    case 'glitch':{const sd=e.params?.seed??7,fr=Math.floor(f),r=random(sd,fr*5);if(r<(e.params?.rate??.15)){x+=a*(random(sd,fr*5+1)-.5)*2;skew+=(random(sd,fr*5+2)-.5)*10;const o=(a*.35).toFixed(1);filters.push(`drop-shadow(${-o}px 0 0 rgba(255,30,70,.8)) drop-shadow(${o}px 0 0 rgba(0,220,255,.8))`);
     if(r<(e.params?.rate??.15)*.5){const t0=random(sd,fr*5+3)*80;extra.clipPath=`inset(${t0.toFixed(1)}% 0 ${(100-t0-8-random(sd,fr*5+4)*25).toFixed(1)}% 0)`;}}break;}
    case 'motion_blur':break; // resolved after the transform is known (velocity between f-1 and f)
    // Colour arrives from params.color and settles on the layer colour (fade-with-colour entrance, state change).
    case 'color_to':extra.color=mixColor(color,item.color||'#ffffff',1-(1-p)*a);break;
    // Gate weave: smooth ~frequency-Hz wobble of `amount` px (film gate / hand-made feel), 1% overscan hides edges. Never per-frame random.
    case 'gate_weave':{const fr=(e.params?.frequency??12)/4.13,t=f/30*fr,sd=e.params?.seed??7;x+=a*smoothNoise(sd,t,0);y+=a*smoothNoise(sd,t,1);scale*=1.01;break;}
    // Boil: hand-drawn line wobble; the displacement pattern changes every `hold` frames (4 variants cycle, 7.5 fps at hold 4).
    case 'boil':{const s=BOIL_SCALES.reduce((q,b)=>Math.abs(b-a)<Math.abs(q-a)?b:q),h=Math.max(1,Math.round(e.params?.cycles??4));filters.push(`url(#ev-boil-${s}-${Math.floor(f/h)%4})`);break;}
    // Bloom: three glows of growing radius with falling strength; a soft filmic falloff instead of one hard halo.
    // Jitter: stepped tremble of cut-outs (paper collage look): a new random offset/rotation every `cycles` frames.
    case 'jitter':{const h=Math.max(1,Math.round(e.params?.cycles??4)),k=Math.floor(f/h),sd=e.params?.seed??7;x+=(random(sd,k*5)-.5)*2*a;y+=(random(sd,k*5+1)-.5)*2*a;rot+=(random(sd,k*5+2)-.5)*2*(e.params?.rotation??.5);scale*=1+(random(sd,k*5+3)-.5)*.02;break;}
    // Clock wipe: radial sweep around a pivot; negative amount sweeps counter-clockwise (pie builds, logo fills).
    case 'clock_wipe':{if(p<1){const deg=p*360,st=e.params?.angle??0,cx=(e.params?.focus_x??.5)*100,cy=(e.params?.focus_y??.5)*100,from=a<0?st-deg:st,m=`conic-gradient(from ${from.toFixed(2)}deg at ${cx}% ${cy}%,#000 0deg,#000 ${deg.toFixed(2)}deg,transparent ${(deg+.6).toFixed(2)}deg)`;extra.maskImage=m;extra.WebkitMaskImage=m;}break;}
    case 'bloom':filters.push(`drop-shadow(0 0 ${a*.5}px ${rgba(color,.7)}) drop-shadow(0 0 ${a}px ${rgba(color,.4)}) drop-shadow(0 0 ${a*2}px ${rgba(color,.25)})`);break;
    // Tracking in em (scales with the type): params.from_em → amount over the effect span. Letter-spacing also trails the
    // last glyph, which pulls centred text left by half the spacing; the layer is shifted back so the title stays centred.
    // _fit_em/_fit_px (written at export from bundled glyph advances) cap the spacing so a line never reflows mid-entrance.
    case 'tracking':{const P=e.params||{},em=Math.min((P.from_em??0)+(a-(P.from_em??0))*p,Math.max(a,P._fit_em??Infinity));extra.letterSpacing=`${em.toFixed(4)}em`;
     if(P.center??(item.data?.align==='center'||item._type?.textAlign==='center')){const fs=parseFloat(item._type?.fontSize)||item.font_size||60;x+=em*fs/2;}break;}
   }
  }
  let sx=1,sy=1;
  const dr=byId&&item.drivers&&Object.keys(item.drivers).length?item.drivers:null,keys=Object.keys(item.keyframes||{});
  if(dr)for(const k of Object.keys(dr))if(!keys.includes(k))keys.push(k);
  for(const key of keys){const v=dr&&dr[key]?trackAt(item,key,f,byId):trackMod(item.keyframes[key],f,item.track_mods?.[key]);if(key==='x')x+=v;else if(key==='y')y+=v;else if(key==='scale')scale*=v;else if(key==='rotate')rot+=v;else if(key==='opacity')opacity*=v;else if(key==='blur')filters.push(`blur(${v}px)`);
   else if(key==='scale_x')sx*=v;else if(key==='scale_y')sy*=v;else if(key==='skew')skew+=v;
   // squash: width/height ratio with constant area (sx = √s, sy = 1/√s); s > 1 squashes, s < 1 stretches.
   else if(key==='squash'){const q=Math.sqrt(Math.max(.01,v));sx*=q;sy/=q;}}
  if(shadows.length)extra.boxShadow=shadows.join(',');
  if(raw)return {x,y,scale,rot,sx,sy,skew};
  const mb=(item.effects||[]).find(e=>e.name==='motion_blur'&&f>=(e.start_frame||0));
  if(mb&&f>0){// Shutter-angle velocity blur: displacement over the exposure fraction of one frame (isotropic approximation).
   const q=styleAt({...item,effects:(item.effects||[]).filter(e=>e.name!=='motion_blur')},f-1,true,byId),diag=Math.hypot(item.width||1,item.height||1)*600;
   const ddx=Math.abs(x-q.x),ddy=Math.abs(y-q.y),zr=Math.abs(scale-q.scale)*diag+Math.abs(rot-q.rot)*Math.PI/180*diag*.5;
   const move=Math.hypot(ddx,ddy)+zr,px=move*(mb.params?.amount??180)/360*.5;
   // Smear along the travel axis when translation dominates; scale/rotation (or diagonal) moves keep an isotropic blur.
   const axis=zr<move*.3?(ddx>ddy*2?'h':ddy>ddx*2?'v':''):'';
   if(px>.15)filters.push(axis&&px>=1?dirBlur(px,axis):`blur(${Math.min(40,px).toFixed(2)}px)`);}
  return {...extra,opacity:clamp(opacity),transform:`translate(${x}px,${y}px) scale(${sx===sy?scale*sx:`${scale*sx},${scale*sy}`}) rotate(${rot}deg) perspective(1200px) rotateX(${rx}deg) rotateY(${ry}deg) skewX(${skew}deg)`,filter:filters.join(' ')||'none',boxSizing:'border-box'};
 }
 // Two-sided transitions: incoming style plus the matching outgoing style. In "live" mode the outgoing
 // shot keeps playing from its source handle; in "freeze" mode its last frame moves.
 const PUSH={push_left:[1,0],push_right:[-1,0],push_up:[0,1],push_down:[0,-1],whip_left:[1,0],whip_right:[-1,0],whip_up:[0,1],whip_down:[0,-1]};
 const whipEase=p=>p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;
 // Shared SVG filters, injected once per document by both engines (filterDefs). Directional blur smears along the
 // motion axis like a real shutter (CSS blur() is isotropic); luma filters turn luminance into alpha for luma-key wipes.
 const BLUR_STEPS=[2,3,4,6,8,12,16,24,32,48],LUMA_STEPS=20,BOIL_SCALES=[2,4,8];
 // Channel split for footage: red and blue planes offset in opposite directions, recombined (drop-shadow fringes only
 // show at a layer's edges, never across a full-frame shot). Steps in px; the nearest step is used.
 const CHROMA_STEPS=[2,4,6,9,13,18,24,32];
 function filterDefs(){const f=[];
  for(const s of CHROMA_STEPS)f.push(`<filter id="ev-rgb-${s}" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB"><feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0" result="r"/><feOffset in="r" dx="${-s}" dy="0" result="ro"/><feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 1 0" result="g"/><feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 1 0" result="b"/><feOffset in="b" dx="${s}" dy="0" result="bo"/><feBlend in="ro" in2="g" mode="screen" result="rg"/><feBlend in="rg" in2="bo" mode="screen"/></filter>`);
  for(const s of BOIL_SCALES)for(let k=0;k<4;k++)f.push(`<filter id="ev-boil-${s}-${k}" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="2" seed="${k*17+3}" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="${s}" xChannelSelector="R" yChannelSelector="G"/></filter>`);for(const s of BLUR_STEPS){f.push(`<filter id="ev-mb-h-${s}" x="-20%" y="-5%" width="140%" height="110%"><feGaussianBlur stdDeviation="${s} 0"/></filter>`,`<filter id="ev-mb-v-${s}" x="-5%" y="-20%" width="110%" height="140%"><feGaussianBlur stdDeviation="0 ${s}"/></filter>`);}
  for(let i=0;i<=LUMA_STEPS;i++){const th=1-i/LUMA_STEPS,slope=4;f.push(`<filter id="ev-luma-${i}" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 .2126 .7152 .0722 0 0" result="l"/><feComponentTransfer in="l"><feFuncA type="linear" slope="${slope}" intercept="${(-th*slope+.5).toFixed(3)}"/></feComponentTransfer></filter>`);}
  return `<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true"><defs>${f.join('')}</defs></svg>`;}
 const dirBlur=(px,axis)=>{if(!(px>=1))return '';if(axis!=='h'&&axis!=='v')return `blur(${Math.min(40,px).toFixed(2)}px)`;const s=BLUR_STEPS.reduce((a,b)=>Math.abs(b-px)<Math.abs(a-px)?b:a);return `url(#ev-mb-${axis}-${s})`;};
 const jitter=(seed,f,k)=>(random(seed,f*7+k)-.5)*2;
 const flashFilter=(t,p)=>{const k=Math.sin(Math.PI*p);return t.name==='burn'?`brightness(${(1+k*1.6).toFixed(3)}) sepia(${(k*.8).toFixed(3)}) saturate(${(1+k*1.8).toFixed(3)})`:`contrast(${(1-k).toFixed(3)}) brightness(${(1+k).toFixed(3)})`;};  // peak = every pixel white
 function transitionStyle(t,f){if(!t)return {};const p=clamp(f/t.duration_frames);if(t.name==='dissolve')return {opacity:p};
  if(t.name==='flash'||t.name==='burn')return {opacity:clamp(p*2-.5),filter:flashFilter(t,p)};if(t.name==='zoom_in')return {opacity:p,transform:`scale(${1.2-.2*p})`};
  if(PUSH[t.name]){const [dx,dy]=PUSH[t.name],w=t.name.startsWith('whip'),q=w?whipEase(p):ease(p,'smooth');return {transform:`translate(${dx*(1-q)*100}%,${dy*(1-q)*100}%)`,filter:w?dirBlur(Math.sin(Math.PI*p)*36*(t.intensity??1),dx?'h':'v')||'none':'none'};}
  if(t.name==='zoom_through'){const q=ease(p,'smooth');return {opacity:q,transform:`scale(${.82+.18*q})`,filter:`blur(${((1-q)*10).toFixed(2)}px)`};}
  // Spin: both shots roll the same way through the seam (match the camera roll in the footage), blur peaking at the join.
  if(t.name==='spin'){const q=whipEase(p),th=90*(t.intensity??1),b=Math.sin(Math.PI*p)*14*(t.intensity??1);return {opacity:clamp((p-.38)/.24),transform:`rotate(${(-(1-q)*th).toFixed(2)}deg) scale(${(1+.3*(1-q)).toFixed(4)})`,filter:b>.5?`blur(${b.toFixed(2)}px)`:'none'};}
  // Luma key: the incoming shot appears through its brightest areas first, then the darks (bridges dark→bright scenes).
  if(t.name==='luma_key'){const i=Math.round(clamp(ease(p,'smooth'))*LUMA_STEPS);return i>=LUMA_STEPS?{}:{filter:`url(#ev-luma-${i})`};}
  // Glitch cut: 4-6 frames of seeded flicker, horizontal jitter and an RGB split; deliberately techy, use sparingly.
  if(t.name==='glitch_cut'){const k=(t.intensity??1),on=random(31,f)<.25+p*.9,dx=jitter(17,f,1)*(1-p)*4*k,rgb=(1-p)*10*k;return {opacity:on?1:0,transform:`translateX(${dx.toFixed(2)}%) skewX(${(jitter(17,f,2)*(1-p)*6*k).toFixed(2)}deg)`,filter:`drop-shadow(${rgb.toFixed(1)}px 0 0 rgba(255,0,60,.75)) drop-shadow(${(-rgb).toFixed(1)}px 0 0 rgba(0,220,255,.75))`};}
  // Dip to black: the outgoing shot darkens in the first half, the incoming rises from black in the second.
  if(t.name==='dip_black'||t.name==='dip_white'){const [a,b]=dipSpan(t),q=clamp((f-b)/Math.max(1,t.duration_frames-b));return t.name==='dip_black'?{opacity:q}:{opacity:q,filter:`contrast(${q.toFixed(3)}) brightness(${(2-q).toFixed(3)})`};}
  if(t.name==='iris'){const [cx,cy]=t.center||[.5,.5],R=Math.hypot(Math.max(cx,1-cx)*16,Math.max(cy,1-cy)*9)/Math.hypot(16,9)*Math.SQRT2*102;return {clipPath:`circle(${(ease(p,'smooth')*R).toFixed(2)}% at ${(cx*100).toFixed(1)}% ${(cy*100).toFixed(1)}%)`};}
  // Pass: a soft-edged band sweeps across (an occluder crossing frame) and the incoming shot is revealed behind it.
  if(t.name==='pass_left'||t.name==='pass_right'){const q=whipEase(p)*130-15,deg=t.name==='pass_right'?90:270,m=`linear-gradient(${deg}deg,#000 ${q.toFixed(2)}%,transparent ${(q+15).toFixed(2)}%)`;return {maskImage:m,WebkitMaskImage:m};}
  return styleAt({effects:[{name:t.name,end_frame:t.duration_frames,params:{amount:t.name==='blur_in'?24:1}}]},f);}
 function transitionOutStyle(t,f){if(!t)return {};const p=clamp(f/t.duration_frames);
  if(t.name==='flash'||t.name==='burn')return {filter:flashFilter(t,p)};
  if(PUSH[t.name]){const [dx,dy]=PUSH[t.name],w=t.name.startsWith('whip'),q=w?whipEase(p):ease(p,'smooth');return {transform:`translate(${-dx*q*100}%,${-dy*q*100}%)`,filter:w?dirBlur(Math.sin(Math.PI*p)*36*(t.intensity??1),dx?'h':'v')||'none':'none'};}
  if(t.name==='zoom_through'){const q=ease(p,'smooth');return {opacity:1-q,transform:`scale(${1+.55*q})`,filter:`blur(${(q*12).toFixed(2)}px)`};}
  if(t.name==='spin'){const q=whipEase(p),th=90*(t.intensity??1),b=Math.sin(Math.PI*p)*14*(t.intensity??1);return {transform:`rotate(${(q*th).toFixed(2)}deg) scale(${(1+.3*q).toFixed(4)})`,filter:b>.5?`blur(${b.toFixed(2)}px)`:'none'};}
  if(t.name==='glitch_cut'){const k=(t.intensity??1),dx=jitter(23,f,1)*p*4*k;return {transform:`translateX(${dx.toFixed(2)}%)`,filter:`drop-shadow(${(p*8*k).toFixed(1)}px 0 0 rgba(255,0,60,.6))`};}
  if(t.name==='dip_black'||t.name==='dip_white'){const [a]=dipSpan(t),q=clamp(f/Math.max(1,a));return t.name==='dip_black'?{filter:`brightness(${(1-q).toFixed(3)})`}:{filter:`contrast(${(1-q).toFixed(3)}) brightness(${(1+q).toFixed(3)})`};}
  if(t.name==='pass_left'||t.name==='pass_right'){const k=Math.sin(Math.PI*p);return {filter:k>.05?`brightness(${(1-.35*k).toFixed(3)})`:'none'};}
  return {};}
 // Dip timing: fade out over [0,a), hold on black/white over [a,b), fade in over [b,duration).
 const dipSpan=t=>{const hold=Math.min(t.hold_frames||0,t.duration_frames-2),a=Math.max(1,Math.floor((t.duration_frames-hold)/2));return [a,a+hold];};
 const esc=s=>String(s??'').normalize('NFC').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function progress(item,f){const e=(item.effects||[]).find(e=>e.name==='progress');return e?phase(e,f):1;}
 const graphemes=text=>typeof Intl.Segmenter==='function'?Array.from(new Intl.Segmenter('vi',{granularity:'grapheme'}).segment(text),s=>s.segment):Array.from(text.normalize('NFC'));
 // Inline emphasis inside one text layer: **strong** (heavier weight) and ==accent== (accent colour), e.g.
 // "Over a billion **per second**". Markup becomes a plain string plus a style code per grapheme, so every reveal below
 // (typewriter, word/line/character, mask, spring, decode) keeps the emphasis on the right glyphs.
 function rich(item){const raw=(item.text||'').normalize('NFC');if(!raw.includes('**')&&!raw.includes('=='))return null;
  const g=graphemes(raw),units=[],style=[];let strong=0,accent=0;
  for(let i=0;i<g.length;i++){if(g[i]==='*'&&g[i+1]==='*'){strong^=1;i++;continue;}if(g[i]==='='&&g[i+1]==='='){accent^=2;i++;continue;}units.push(g[i]);style.push(strong|accent);}
  return {plain:units.join(''),units,style,weight:item.data?.strong_weight??800,accent:esc(item.data?.accent||'#81e6be')};}
 const plainText=item=>{const R=rich(item);return R?R.plain:(item.text||'').normalize('NFC');};
 const sty=(R,html,s)=>!R||!s?html:`<span style="${s&1?`font-weight:${R.weight};`:''}${s&2?`color:${R.accent};`:''}">${html}</span>`;
 // Escaped HTML for str whose first grapheme sits at plain index start, grouped into runs of equal style.
 function runsAt(R,start,str){if(!R)return esc(str);const g=graphemes(str);let out='',cur=-1,buf='';
  for(let j=0;j<g.length;j++){const s=R.style[start+j]||0;if(s!==cur&&buf){out+=sty(R,esc(buf),cur);buf='';}cur=s;buf+=g[j];}
  return buf?out+sty(R,esc(buf),cur):out;}
 function textAt(item,f){const e=(item.effects||[]).find(e=>e.name==='typewriter'),plain=plainText(item),units=graphemes(plain);return e?units.slice(0,Math.ceil(units.length*phase(e,f))).join(''):plain;}
 const backOut=(t,k)=>{const c1=1.70158*k,c3=c1+1;return 1+c3*Math.pow(t-1,3)+c1*Math.pow(t-1,2);};
 // Typewriter with a script: type each phrase at params.cps (measured ~20 chars/s), hold, delete at 2x speed back to the
 // prefix it shares with the next phrase, type the next. A block cursor (params.cursor) blinks every 16 frames when idle.
 function typeScript(e,f){const P=e.params||{},cps=P.cps??20,fpc=30/cps,holdOf=i=>P.hold??Math.max(24,Math.round(30*(.5+.32*String(P.script[i]).trim().split(/\s+/).length))),ph=(P.script||[]).map(x=>graphemes(String(x).normalize('NFC')));let t=f-(e.start_frame||0),cur=[],typing=false;
  for(let i=0;i<ph.length;i++){const prev=cur,target=ph[i];let k=0;while(k<prev.length&&k<target.length&&prev[k]===target[k])k++;
   const del=(prev.length-k)*fpc/2;if(t<del){return {text:prev.slice(0,prev.length-Math.floor(t/(fpc/2))).join(''),typing:true};}t-=del;
   const typ=(target.length-k)*fpc;if(t<typ){return {text:target.slice(0,k+Math.floor(t/fpc)).join(''),typing:true};}t-=typ;cur=target;
   if(i<ph.length-1){const hold=holdOf(i);if(t<hold)return {text:cur.join(''),typing:false};t-=hold;}}
  return {text:cur.join(''),typing:false};}
 function cursorHtml(e,f,typing){const P=e.params||{};if(!P.cursor)return '';const on=typing||Math.floor(f/(P.blink??16))%2===0;
  return `<span style="display:inline-block;width:.52em;height:.32em;margin-left:.06em;vertical-align:baseline;background:${esc(P.cursor_color||'#ffd166')};opacity:${on?1:0}"></span>`;}
 function plated(item){const b=String(item.background||'').trim().toLowerCase();return !!b&&b!=='transparent'&&b!=='none'&&!/^rgba\(.*,\s*0(\.0+)?\)$/.test(b);}
 function textWidget(item,f){
  const tw=(item.effects||[]).find(e=>e.name==='typewriter');
  if(tw&&tw.params?.script?.length){const r=typeScript(tw,f);return esc(r.text)+cursorHtml(tw,f,r.typing);}
  const R=rich(item),raw=R?R.plain:(item.text||'').normalize('NFC');
  let text=runsAt(R,0,textAt(item,f));const effects=item.effects||[];
  if(tw?.params?.cursor){const typing=f>=(tw.start_frame||0)&&f<tw.end_frame;text+=cursorHtml(tw,f,typing);}
  // Premium reveals: per-line clipping masks (padding keeps Vietnamese diacritics inside the mask) and per-grapheme springs.
  const dec=effects.find(e=>e.name==='decode');
  if(dec){const units=graphemes(raw),n=Math.max(1,units.filter(u=>u.trim()).length),sd=dec.params?.seed??7,
    t=clamp((f-(dec.start_frame||0))/Math.max(1,dec.end_frame-(dec.start_frame||0))),set='ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&@*+=?';let i=0;
   return units.map((u,j)=>{if(u===String.fromCharCode(10))return '<br>';if(!u.trim())return esc(u);const k=i++,start=k/n*.75,settle=start+.25;
    if(t>=settle)return sty(R,esc(u),R?.style[j]);if(t<start)return `<span style="opacity:0">${esc(u)}</span>`;
    const g=set[Math.floor(random(sd,k*131+Math.floor(f/2))*set.length)];return `<span style="opacity:.85">${g}</span>`;}).join('');}
  const mr=effects.find(e=>e.name==='mask_reveal'),cs=effects.find(e=>e.name==='char_spring');
  if(mr||cs){const e=mr||cs,stagger=e.params?.stagger??(mr?.35:.6),a=e.params?.amount??defaults[e.name];
   const t=clamp((f-(e.start_frame||0))/Math.max(1,e.end_frame-(e.start_frame||0)));
   const units=mr?raw.split(String.fromCharCode(10)):graphemes(raw),n=units.filter(u=>u.trim()).length;let i=0,at=0;
   const local=()=>{const k=i++,off=n<=1?0:k/(n-1)*stagger;return clamp((t-off)/Math.max(.05,1-stagger));};
   if(mr)text=units.map(line=>{const q=local(),y=(1-backOut(q,.9))*a,html=runsAt(R,at,line);at+=graphemes(line).length+1;return `<span style="display:block;overflow:hidden;padding:.18em 0 .12em;margin:-.18em 0 -.12em"><span style="display:block;transform:translateY(${y.toFixed(2)}%)">${html||'&nbsp;'}</span></span>`;}).join('');
   else text=units.map((u,j)=>{if(u===String.fromCharCode(10))return '<br>';if(!u.trim())return esc(u);const q=local(),sc=q<=0?0:backOut(q,a*1.6);return `<span style="display:inline-block;opacity:${Math.min(1,q*2.5).toFixed(3)};transform:scale(${sc.toFixed(3)}) translateY(${((1-q)*.25).toFixed(3)}em);filter:blur(${((1-q)*6).toFixed(2)}px)">${sty(R,esc(u),R?.style[j])}</span>`;}).join('');
   return text;}
  const e=effects.find(e=>['word_reveal','line_reveal','character_reveal'].includes(e.name));
  if(e){const units=e.name==='line_reveal'?raw.split('\n'):e.name==='character_reveal'?graphemes(raw):raw.split(/(\s+)/),count=units.filter(x=>x.trim()).length;let i=0,at=0;
   text=units.map(unit=>{const start=at;at+=graphemes(unit).length+(e.name==='line_reveal'?1:0);if(!unit.trim()&&e.name!=='line_reveal')return esc(unit);const index=i++,stagger=e.params?.stagger??.12,span=1-stagger,offset=count<=1?0:index/(count-1)*stagger,local=ease(clamp((clamp((f-(e.start_frame||0))/Math.max(1,e.end_frame-(e.start_frame||0)))-offset)/span),e.easing||'smooth'),rise=(e.params?.amount??defaults[e.name])*(1-local);return `<span style="display:${e.name==='line_reveal'?'block':'inline-block'};opacity:${local};transform:translateY(${rise}px)">${runsAt(R,start,unit)}</span>`;}).join('');
  }
  // Range selector (After Effects text animator): a window sweeps across units in a chosen order; each unit moves
  // between its rest state and a start state (opacity, offset, scale, rotation, blur, colour). mode in: arrive;
  // out: leave (run it at the end, order reverse for last-in-first-out); sweep: a band passes through and returns
  // (colour or scale accent travelling along a line). The sweep has its own easing/bezier like a range keyframe.
  // Several text_animate effects combine on one layer (e.g. an entry and an exit): each unit's state is the product of
  // their opacities and the sum of their offsets/rotations, the product of scales; the last active colour wins. The unit
  // split comes from the first instance. Per-unit motion blur (params.shutter, degrees) smears along the unit's own travel.
  const tas=effects.filter(e=>e.name==='text_animate');
  if(tas.length&&!e){const P0=tas[0].params||{},unit=P0.unit||'word';
   const units=unit==='line'?raw.split('\n'):unit==='char'?graphemes(raw):raw.split(/(\s+)/),vis=units.map((u,i)=>u.trim()?i:-1).filter(i=>i>=0),n=vis.length,base=item.color||'#ffffff';
   // params.target: unit numbers (0-based, words/chars/lines counted without spaces) that this instance animates; the
   // others stay at rest, so an emphasis can hit one word by position and survive text edits elsewhere in the line.
   const posFor=P=>{const order=P.order||'forward',m=new Map(),tg=Array.isArray(P.target)?new Set(P.target):null,sel=tg?vis.filter((_,k)=>tg.has(k)):vis,ns=sel.length;
    sel.forEach((ui,k)=>{let r=ns<=1?0:k/(ns-1);if(order==='reverse')r=1-r;else if(order==='center')r=Math.abs(r-.5)*2;else if(order==='random')r=random(P.seed??7,k);m.set(ui,r);});return m;};
   const plans=tas.map(ta=>({ta,P:ta.params||{},pos:posFor(ta.params||{})}));
   const stateAt=(ui,fr)=>{let op=1,x=0,y=0,sc=1,rot=0,bl=0,col='';
    for(const {ta,P,pos} of plans){if(!pos.has(ui))continue;const mode=P.mode||'in',w=clamp(P.window??.35,.02,1),sweep=curve(clamp((fr-(ta.start_frame||0))/Math.max(1,ta.end_frame-(ta.start_frame||0))),ta.easing||'smooth',ta.bezier);
     const raw01=pos.size<=1?sweep:clamp((sweep*(1+w)-pos.get(ui))/w),q=P.shape==='square'?(raw01>0?1:0):P.shape==='ramp'?raw01:ease(raw01,'smooth');
     const k=mode==='in'?1-q:mode==='out'?q:Math.sin(Math.PI*raw01);  // 1 = start/accent state, 0 = rest
     if(mode!=='sweep')op*=1-(1-(P.opacity??0))*k;y+=(P.amount??30)*k*(mode==='out'?-1:1);x+=(P.x||0)*k;sc*=1+((P.scale??1)-1)*k;rot+=(P.rotate||0)*k;bl+=(P.blur||0)*k;
     if(P.color&&k>.001)col=mixColor(base,P.color,k);}
    return {op,x,y,sc,rot,bl,col};};
   const shutter=Math.max(0,...plans.map(p=>p.P.shutter||0));let at=0;
   text=units.map((u,ui)=>{const start=at;at+=graphemes(u).length+(unit==='line'?1:0);if(!pos0(ui))return unit==='line'?'<span style="display:block">&nbsp;</span>':esc(u);
    const s=stateAt(ui,f);let bl=s.bl;
    if(shutter>0){const p=stateAt(ui,f-shutter/360),v=Math.hypot(s.x-p.x,s.y-p.y);if(v>.3)bl+=v*.5;}
    return `<span style="display:${unit==='line'?'block':'inline-block'};opacity:${s.op.toFixed(3)};transform:translate(${s.x.toFixed(2)}px,${s.y.toFixed(2)}px) scale(${s.sc.toFixed(4)}) rotate(${s.rot.toFixed(2)}deg);${bl>.05?`filter:blur(${bl.toFixed(2)}px);`:''}${s.col?`color:${s.col};`:''}">${runsAt(R,start,u)||'&nbsp;'}</span>`;}).join('');
   function pos0(ui){return vis.includes(ui);}
  }
  const marker=effects.find(e=>e.name==='marker_reveal'&&f>=(e.start_frame||0)),line=effects.find(e=>e.name==='underline_draw'&&f>=(e.start_frame||0)),gradient=effects.find(e=>e.name==='text_gradient'&&f>=(e.start_frame||0));
  if(marker||line){const e=marker||line,color=esc(e.params?.color||'#81e6be'),size=marker?(e.params?.amount??.35)*100+'%':(e.params?.amount??.06)+'em';text=`<span style="background-image:linear-gradient(${color},${color});background-position:0 ${marker?'92%':'100%'};background-size:${phase(e,f)*100}% ${size};background-repeat:no-repeat;box-decoration-break:clone">${text}</span>`;}
  if(gradient)text=`<span style="background-image:linear-gradient(110deg,${esc(gradient.params?.color||'#81e6be')},${esc(gradient.params?.secondary_color||'#e4b866')});background-clip:text;-webkit-background-clip:text;color:transparent">${text}</span>`;
  return text;
 }
 const iconPaths={play:'M8 5l12 7-12 7z',pause:'M8 5v14M16 5v14',check:'M4 12l5 5L20 6',close:'M5 5l14 14M19 5L5 19',arrow_right:'M3 12h17M13 5l7 7-7 7',arrow_up:'M12 21V3M5 10l7-7 7 7',info:'M12 10v8M12 6v1',question:'M8 7c0-5 9-5 9 0 0 4-5 3-5 7M12 18v1',lightbulb:'M9 21h6M9 17h6M8 14c-6-8 2-15 8-10 4 3 1 8-1 10v3H9v-3z',book:'M12 5v15M3 4c4-1 6 0 9 1 3-1 5-2 9-1v15c-4-1-6 0-9 1-3-1-5-2-9-1z',eye:'M2 12c6-10 14-10 20 0-6 10-14 10-20 0zM15 12a3 3 0 1 0-6 0 3 3 0 1 0 6 0',camera:'M3 7h5l2-3h4l2 3h5v13H3zM16 13a4 4 0 1 0-8 0 4 4 0 1 0 8 0',mic:'M9 4v8a3 3 0 0 0 6 0V4a3 3 0 0 0-6 0zM5 11v1a7 7 0 0 0 14 0v-1M12 19v3M8 22h8',clock:'M12 6v7l4 2M22 12a10 10 0 1 0-20 0 10 10 0 1 0 20 0',link:'M9 15l6-6M7 14l-2 2c-4 4 2 8 5 4l3-3M11 7l3-3c4-4 9 1 5 5l-2 2',chart:'M3 3v18h18M7 16v-5M12 16V6M17 16v-8',code:'M8 6l-6 6 6 6M16 6l6 6-6 6M14 3l-4 18',location:'M12 22c-16-16-3-24 4-18 8 6-4 18-4 18zM15 9a3 3 0 1 0-6 0 3 3 0 1 0 6 0',star:'M12 2l3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z',heart:'M12 21C-9 8 7-6 12 5c5-11 21 3 0 16z',volume:'M3 9h4l5-5v16l-5-5H3zM16 8c4 2 4 6 0 8M19 4c6 5 6 11 0 16',search:'M21 21l-6-6M17 9a8 8 0 1 0-16 0 8 8 0 1 0 16 0',target:'M22 12a10 10 0 1 0-20 0 10 10 0 1 0 20 0M18 12a6 6 0 1 0-12 0 6 6 0 1 0 12 0M14 12a2 2 0 1 0-4 0 2 2 0 1 0 4 0',spark:'M12 1l3 8 8 3-8 3-3 8-3-8-8-3 8-3z'};
 function patternWidget(item){const d=item.data||{},s=d.spacing||60,c=esc(item.color||'#81e6be'),sw=d.stroke_width??1.5,w=Math.max(1,(item.width||1)*(item._canvas_width||1920)),h=Math.max(1,(item.height||1)*(item._canvas_height||1080)),id='pat-'+String(item.id).replace(/[^a-zA-Z0-9_-]/g,'_');let body='';
  const lines={grid:`M${s} 0H0V${s}`,stripes:`M0 ${s/2}H${s}`,diagonal:`M-${s/2} ${s/2}L${s/2} -${s/2}M0 ${s}L${s} 0M${s/2} ${1.5*s}L${1.5*s} ${s/2}`,crosshatch:`M0 0L${s} ${s}M0 ${s}L${s} 0`,hexagons:`M${s/4} 0L${.75*s} 0 ${s} ${s/2} ${.75*s} ${s} ${s/4} ${s} 0 ${s/2}z`,waves:`M0 ${s/2}Q${s/4} 0 ${s/2} ${s/2}T${s} ${s/2}`,contour:`M0 ${s/2}Q${s/2} 0 ${s} ${s/2}M0 ${.8*s}Q${s/2} ${.3*s} ${s} ${.8*s}`};
  if(lines[d.pattern])body=`<path d="${lines[d.pattern]}" fill="none" stroke="${c}" stroke-width="${sw}"/>`;
  if(d.pattern==='dots')body=`<circle cx="${s/2}" cy="${s/2}" r="${Math.max(1,sw)}" fill="${c}"/>`;
  if(d.pattern==='rings')body=`<circle cx="${s/2}" cy="${s/2}" r="${s*.38}" fill="none" stroke="${c}" stroke-width="${sw}"/>`;
  if(d.pattern==='checker')body=`<path d="M0 0h${s/2}v${s/2}H0zM${s/2} ${s/2}h${s/2}v${s/2}H${s/2}z" fill="${c}"/>`;
  if(d.pattern==='speckles')body=Array.from({length:12},(_,i)=>`<circle cx="${random(d.seed??7,i)*s}" cy="${random(d.seed??7,i+12)*s}" r="${1+random(d.seed??7,i+24)*2}" fill="${c}"/>`).join('');
  if(d.pattern==='gradient')return `<div style="width:100%;height:100%;background:linear-gradient(125deg,${c},${esc(d.secondary_color||'#102322')})"></div>`;
  return `<svg width="100%" height="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><defs><pattern id="${id}" width="${s}" height="${s}" patternUnits="userSpaceOnUse">${body}</pattern></defs><rect width="100%" height="100%" fill="url(#${id})"/></svg>`;
 }
 // Declarative vector illustration (maps, routes, diagrams). All timing is local frames; no DOM measurement,
 // so path draw-on uses pathLength=1 and followers interpolate along polyline arc length.
 function svgWidget(item,f){const d=item.data||{},[W,H]=d.view_box||[1000,1000],num=v=>Number.isFinite(+v)?+v:0;
  const prog=r=>r?ease(clamp((f-r[0])/Math.max(1,r[1]-r[0])),'smooth'):1;
  const routes={};for(const e of d.elements||[])if(e.type==='polyline'){let L=0;const seg=[0];for(let i=1;i<e.points.length;i++){L+=Math.hypot(e.points[i][0]-e.points[i-1][0],e.points[i][1]-e.points[i-1][1]);seg.push(L);}routes[e.id]={pts:e.points,seg,L};}
  const at=(r,t)=>{const target=r.L*clamp(t);let i=1;while(i<r.seg.length-1&&r.seg[i]<target)i++;const a=r.pts[i-1],b=r.pts[i],span=Math.max(1e-9,r.seg[i]-r.seg[i-1]),u=clamp((target-r.seg[i-1])/span);return [a[0]+(b[0]-a[0])*u,a[1]+(b[1]-a[1])*u];};
  const defs=[],out=[];
  for(const e of d.elements||[]){
   if(e.appear&&f<e.appear[0])continue;if(e.draw&&f<e.draw[0]&&!e.appear)continue;if(e.type==='follower'&&f<e.progress[0])continue;
   const ap=prog(e.appear),dr=prog(e.draw),fi=e.fill_in?prog(e.fill_in):1,op=num(e.opacity??1)*ap;
   const glow=e.glow?`filter:drop-shadow(0 0 ${num(e.glow)}px ${esc(e.stroke!=='none'?e.stroke:e.fill)});`:'';
   const scale=e.appear?.85+.15*ap:1;
   let geom='',cx=0,cy=0;
   if(e.type==='path')geom=`<path d="${esc(e.d)}"`;
   else if(e.type==='polyline')geom=`<polyline points="${e.points.map(p=>num(p[0])+','+num(p[1])).join(' ')}"`;
   else if(e.type==='line')geom=`<line x1="${num(e.x1)}" y1="${num(e.y1)}" x2="${num(e.x2)}" y2="${num(e.y2)}"`;
   else if(e.type==='rect'){geom=`<rect x="${num(e.x)}" y="${num(e.y)}" width="${num(e.width)}" height="${num(e.height)}" rx="${num(e.rx)}"`;cx=num(e.x)+num(e.width)/2;cy=num(e.y)+num(e.height)/2;}
   else if(e.type==='circle'){geom=`<circle cx="${num(e.cx)}" cy="${num(e.cy)}" r="${num(e.r)}"`;cx=num(e.cx);cy=num(e.cy);}
   else if(e.type==='follower'){const r=routes[e.route];if(!r)continue;const [x,y]=at(r,prog(e.progress));cx=x;cy=y;geom=`<circle cx="${x}" cy="${y}" r="${num(e.r)}"`;}
   // Arrow / dimension line: draw grows it from its start or outward from its middle, and the heads ride the growing tips.
   if(e.type==='arrow'){const x1=num(e.x1),y1=num(e.y1),x2=num(e.x2),y2=num(e.y2),t=e.draw?dr:1,mid=e.grow==='center';
    const ax=mid?(x1+x2)/2+(x1-x2)/2*t:x1,ay=mid?(y1+y2)/2+(y1-y2)/2*t:y1,bx=mid?(x1+x2)/2+(x2-x1)/2*t:x1+(x2-x1)*t,by=mid?(y1+y2)/2+(y2-y1)/2*t:y1+(y2-y1)*t;
    const L=Math.hypot(bx-ax,by-ay)||1e-9,dx=(bx-ax)/L,dy=(by-ay)/L,hs=num(e.head_size)||num(e.stroke_width)*4,col=esc(e.stroke),heads=e.heads||'end';
    const head=(x,y,sx,sy)=>`<path d="M${x} ${y}L${x-sx*hs-sy*hs*.55} ${y-sy*hs+sx*hs*.55}L${x-sx*hs+sy*hs*.55} ${y-sy*hs-sx*hs*.55}Z" fill="${col}"/>`;
    const inset=(h)=>h?hs*.7:0,sa=heads==='both'||heads==='start',sb=heads==='both'||heads==='end';
    if(L>hs*.2)out.push(`<g opacity="${op}" style="${glow}"><line x1="${ax+dx*inset(sa)}" y1="${ay+dy*inset(sa)}" x2="${bx-dx*inset(sb)}" y2="${by-dy*inset(sb)}" stroke="${col}" stroke-width="${num(e.stroke_width)}" stroke-linecap="butt"/>${sb?head(bx,by,dx,dy):''}${sa?head(ax,ay,-dx,-dy):''}</g>`);
    continue;}
   // Ripple: rings expand from a circle and fade, staggered (emission, signal, "photon" rings, attention pulse).
   if(e.type==='circle'&&e.ripple&&f>=e.ripple[0]){const t=clamp((f-e.ripple[0])/Math.max(1,e.ripple[1]-e.ripple[0])),k=Math.max(1,e.ripple_count||3),life=.6,sc=num(e.ripple_scale)||2.4;
    for(let j=0;j<k;j++){const q=clamp((t-(k>1?j/(k-1)*(1-life):0))/life);if(q<=0||q>=1)continue;const rr=num(e.r)*(1+(sc-1)*(1-Math.pow(1-q,2)));
     out.push(`<circle cx="${cx}" cy="${cy}" r="${rr.toFixed(2)}" fill="none" stroke="${esc(e.stroke!=='none'?e.stroke:e.fill)}" stroke-width="${Math.max(1,num(e.stroke_width)).toFixed(2)}" opacity="${((1-q)*op*.9).toFixed(3)}"/>`);}}
   if(e.type==='text'){out.push(`<text x="${num(e.x)}" y="${num(e.y)}" text-anchor="${e.anchor||'start'}" font-size="${num(e.font_size)}" font-weight="${num(e.font_weight)}" fill="${esc(e.fill==='none'?e.stroke:e.fill)}" opacity="${op}" style="${glow}paint-order:stroke;transform-box:fill-box;transform-origin:center;transform:translateY(${(1-ap)*num(e.font_size)*.4}px)">${esc(e.text)}</text>`);continue;}
   const wr=e.width_ramp,sw=wr?num(wr[2])+(num(wr[3])-num(wr[2]))*ease(clamp((f-wr[0])/Math.max(1,wr[1]-wr[0])),'smooth'):num(e.stroke_width);
   const fillOp=(e.fill_opacity??1)*fi,stroke=esc(e.stroke),fill=esc(e.fill);
   if(e.trim){const tr=e.trim,q=curve(clamp((f-tr.frames[0])/Math.max(1,tr.frames[1]-tr.frames[0])),'smooth',e.trim_bezier),[s0,s1]=tr.start||[0,0],[e0,e1]=tr.end||[1,1];
    const st=s0+(s1-s0)*q,en=e0+(e1-e0)*q,len=Math.max(0,en-st);if(len<=.0005)continue;
    out.push(`${geom} fill="${fill}" fill-opacity="${fillOp}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="${e.linecap||'round'}" stroke-linejoin="round" pathLength="1" stroke-dasharray="${len.toFixed(5)} 2" stroke-dashoffset="${(-st).toFixed(5)}" opacity="${op}" style="${glow}${scale!==1?`transform-box:fill-box;transform-origin:center;transform:scale(${scale});`:''}"/>`);continue;}
   const tf=scale!==1?`transform-box:fill-box;transform-origin:center;transform:scale(${scale});`:'';
   if(e.draw&&e.dashed){const id='m'+String(item.id).replace(/[^a-zA-Z0-9_-]/g,'_')+'_'+e.id;
    defs.push(`<mask id="${id}" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}">${geom} fill="none" stroke="#fff" stroke-width="${sw*3+2}" stroke-linecap="round" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${1-dr}"/></mask>`);
    out.push(`${geom} mask="url(#${id})" fill="${fill}" fill-opacity="${fillOp}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${num(e.dashed)} ${num(e.dashed)*.8}" stroke-linecap="round" stroke-linejoin="round" opacity="${op}" style="${glow}${tf}"/>`);}
   else if(e.draw)out.push(`${geom} fill="${fill}" fill-opacity="${fillOp}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${1-dr}" opacity="${op}" style="${glow}${tf}"/>`);
   else out.push(`${geom} fill="${fill}" fill-opacity="${fillOp}" stroke="${stroke}" stroke-width="${sw}" ${e.dashed?`stroke-dasharray="${num(e.dashed)} ${num(e.dashed)*.8}"`:''} stroke-linecap="round" stroke-linejoin="round" opacity="${op}" style="${glow}${tf}"/>`);
  }
  const family=d.font_family?`font-family:'EV ${esc(d.font_family)}',inherit;`:'';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="display:block;overflow:visible;${family}"><defs>${defs.join('')}</defs>${out.join('')}</svg>`;
 }
 // Cinematic finishing layers. Grain reseeds per frame (deterministic, seekable); leaks drift on absolute-frame sines.
 function filmWidget(item,f){const d=item.data||{},k=clamp(d.intensity??.5),seed=((d.seed??7)+Math.floor(f*(d.speed??1)))%997,id='fg'+String(item.id).replace(/[^a-zA-Z0-9_-]/g,'_');
  if(d.type==='light_leak'){const t=f*(d.speed??1)/30,c1=esc(d.color||'#ff9a3c'),c2=esc(d.secondary_color||'#ff3c6e');
   const x1=50+42*Math.sin(t*.7+(d.seed??7)),y1=35+30*Math.cos(t*.53),x2=55+40*Math.cos(t*.41+1.3),y2=70+25*Math.sin(t*.37+.6),pulse=.65+.35*Math.sin(t*1.3+(d.seed??7));
   return `<div style="width:100%;height:100%;opacity:${(k*pulse).toFixed(3)};background:radial-gradient(ellipse 60% 45% at ${x1.toFixed(1)}% ${y1.toFixed(1)}%,${c1} 0%,transparent 70%),radial-gradient(ellipse 45% 55% at ${x2.toFixed(1)}% ${y2.toFixed(1)}%,${c2} 0%,transparent 65%);filter:blur(30px)"></div>`;}
  if(d.type==='scanlines'||d.type==='vhs'){const pitch=Math.max(2,Math.round(4*(d.scale??1))),c=esc(d.color||'#000000'),flick=.85+.15*random(seed,1);
   let html=`<div style="position:absolute;inset:0;opacity:${(k*flick).toFixed(3)};background:repeating-linear-gradient(0deg,${c} 0px,${c} ${Math.max(1,pitch>>1)}px,transparent ${Math.max(1,pitch>>1)}px,transparent ${pitch}px)"></div>`;
   // A soft brighter band rolls down the frame (CRT refresh / tape tracking), position frame-indexed.
   const band=((f*(d.speed??1)*0.9)%140)-20;
   html+=`<div style="position:absolute;left:0;right:0;top:${band.toFixed(2)}%;height:${d.type==='vhs'?7:14}%;background:linear-gradient(180deg,transparent,rgba(255,255,255,${(k*.18).toFixed(3)}),transparent)"></div>`;
   if(d.type==='vhs'){const ty=random(seed,7)*100,th=1+random(seed,8)*3,c2=esc(d.secondary_color||'#ff3c6e');
    html+=`<div style="position:absolute;left:0;right:0;top:${ty.toFixed(2)}%;height:${th.toFixed(2)}%;opacity:${(k*.55).toFixed(3)};background:repeating-linear-gradient(90deg,rgba(255,255,255,.75) 0 ${2+Math.round(random(seed,9)*6)}px,transparent 0 ${7+Math.round(random(seed,10)*9)}px);mix-blend-mode:screen"></div>`;
    html+=`<div style="position:absolute;inset:0;opacity:${(k*.12).toFixed(3)};background:linear-gradient(90deg,${c2},transparent 30%,transparent 70%,#3cc9ff);mix-blend-mode:screen"></div>`;}
   return `<div style="position:relative;width:100%;height:100%;overflow:hidden">${html}</div>`;}
  const W=(item._canvas_width||1920)*(item.width||1),H=(item._canvas_height||1080)*(item.height||1),[mx,my]=d.center||[.5,.5],cx=mx*W,cy=my*H,diag=Math.hypot(W,H);
  // Radial speed lines streaming out of `center`: sells a zoom-through / warp move without a costly radial blur.
  if(d.type==='speed_lines'){const n=Math.round(30+120*k),c=esc(d.color||'#ffffff'),t=f*(d.speed??1)/30,sd=d.seed??7;let s='';
   for(let i=0;i<n;i++){const th=random(sd,i)*Math.PI*2,u=(random(sd,i+500)+t*(.6+.8*random(sd,i+900)))%1,r0=(.08+u*.75)*diag*.6,len=(.04+.18*u*u)*diag*(d.scale??1);
    s+=`<line x1="${(cx+Math.cos(th)*r0).toFixed(1)}" y1="${(cy+Math.sin(th)*r0).toFixed(1)}" x2="${(cx+Math.cos(th)*(r0+len)).toFixed(1)}" y2="${(cy+Math.sin(th)*(r0+len)).toFixed(1)}" stroke="${c}" stroke-width="${(.6+2.4*u*random(sd,i+1300)).toFixed(2)}" stroke-linecap="round" opacity="${(Math.sin(Math.PI*u)*(.35+.65*random(sd,i+1700))).toFixed(3)}"/>`;}
   return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W.toFixed(1)} ${H.toFixed(1)}" width="100%" height="100%" preserveAspectRatio="none" style="display:block;opacity:${k.toFixed(3)}">${s}</svg>`;}
  // Anamorphic lens flare at `center`: horizontal streak, halo, four-point star and ghosts mirrored through frame centre.
  if(d.type==='flare'){const c=esc(d.color||'#9fd4ff'),c2=esc(d.secondary_color||'#ffffff'),fl=k*(.92+.08*Math.sin(f*.37+(d.seed??7))),sc=d.scale??1,id='fl'+String(item.id).replace(/[^a-zA-Z0-9_-]/g,'_');
   // Radial gradients on flat ellipses fall off along both axes, so streaks and rays stay soft instead of reading as bars.
   const g=(n,stops)=>`<radialGradient id="${id}${n}">${stops.map(([o,col,a])=>`<stop offset="${o}" stop-color="${col}" stop-opacity="${a}"/>`).join('')}</radialGradient>`;
   const defs=g('h',[[0,c2,1],[.1,c,.5],[1,c,0]])+g('s',[[0,c2,1],[.3,c,.45],[1,c,0]])+g('d',[[0,c,.5],[1,c,0]])+g('r',[[0,c,0],[.72,c,.05],[.86,c,.55],[1,c,0]]);
   const el=(rx,ry,fill,op,deg=0)=>`<ellipse cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" rx="${rx.toFixed(1)}" ry="${Math.max(.6,ry).toFixed(2)}" fill="url(#${id}${fill})" opacity="${op}"${deg?` transform="rotate(${deg} ${cx.toFixed(1)} ${cy.toFixed(1)})"`:''}/>`;
   // Ghosts sit on the line from the source through frame centre, small, alternating soft discs and thin rings.
   const ghosts=[[-.35,.016,'d'],[.45,.028,'r'],[.8,.011,'d'],[1.25,.042,'r'],[1.55,.02,'d']].map(([u,r,kind])=>{const gx=cx+(W/2-cx)*u*2,gy=cy+(H/2-cy)*u*2;
    return `<circle cx="${gx.toFixed(1)}" cy="${gy.toFixed(1)}" r="${(diag*r*sc).toFixed(1)}" fill="url(#${id}${kind})" opacity="${kind==='r'?.8:.6}"/>`;}).join('');
   return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W.toFixed(1)} ${H.toFixed(1)}" width="100%" height="100%" preserveAspectRatio="none" style="display:block;mix-blend-mode:screen"><defs>${defs}</defs><g opacity="${fl.toFixed(3)}">`
    +el(diag*.42*sc,diag*.014*sc,'s',.55)+el(diag*.3*sc,1.4*sc,'s',1)+`<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${(diag*.06*sc).toFixed(1)}" fill="url(#${id}h)"/>`
    +el(diag*.06*sc,1.2*sc,'s',.9,90)+el(diag*.03*sc,1*sc,'s',.7,45)+el(diag*.03*sc,1*sc,'s',.7,135)+`<g opacity=".7">${ghosts}</g></g></svg>`;}
  if(d.type==='dust'){const n=Math.round(6+40*k),c=esc(d.color||'#ffffff');let s='';
   for(let i=0;i<n;i++){const r=random(seed,i*3)*1.6+.3,cx=random(seed,i*3+1)*100,cy=random(seed,i*3+2)*100;s+=`<circle cx="${cx.toFixed(2)}%" cy="${cy.toFixed(2)}%" r="${r.toFixed(2)}" fill="${c}" opacity="${(.35+.5*random(seed,i+400)).toFixed(2)}"/>`;}
   const scratches=random(seed,900)<.6?1+Math.floor(random(seed,901)*2):0;
   for(let i=0;i<scratches;i++){const x=random(seed,910+i)*100;s+=`<line x1="${x.toFixed(2)}%" y1="0" x2="${(x+random(seed,920+i)*.6-.3).toFixed(2)}%" y2="100%" stroke="${c}" stroke-width=".8" opacity=".35"/>`;}
   return `<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" preserveAspectRatio="none" style="display:block;opacity:${k.toFixed(3)}">${s}</svg>`;}
  // Grain by gauge: smaller film = bigger, stronger grain (16 mm ≈ 2x the size and 1.5x the amplitude of 35 mm). Use the
  // layer with blend overlay/soft_light so grain sits in the midtones like real film; color_grain keeps per-channel noise.
  const G={8:[.24,1.9],16:[.42,1.5],35:[.85,1],65:[1.15,.7]}[d.gauge]||[d.scale??.85,1],freq=G[0].toFixed(3);const kk=clamp(k*G[1]);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" preserveAspectRatio="none" style="display:block"><filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="${freq}" numOctaves="2" seed="${seed}" stitchTiles="stitch"/>${d.color_grain?'':'<feColorMatrix type="saturate" values="0"/>'}</filter><rect width="100%" height="100%" filter="url(#${id})" opacity="${kk.toFixed(3)}"/></svg>`;}
 function adjustWidget(item,f){const d=item.data||{},dur=Math.max(1,(item.end_frame||1)-(item.start_frame||0)),r=d.ramp||[0,0];
  const m=clamp(Math.min(r[0]?f/r[0]:1,r[1]?(dur-1-f)/r[1]:1))*(d.mix??1),lerp=(v,n)=>n+(v-n)*m,fs=[];
  if(d.exposure)fs.push(`brightness(${Math.pow(2,lerp(d.exposure,0)).toFixed(4)})`);
  if(d.contrast!=null)fs.push(`contrast(${lerp(d.contrast,1).toFixed(4)})`);
  if(d.saturation!=null)fs.push(`saturate(${lerp(d.saturation,1).toFixed(4)})`);
  if(d.temperature){const t=lerp(d.temperature,0);fs.push(t>0?`sepia(${(t*.3).toFixed(4)}) saturate(${(1+t*.15).toFixed(4)})`:`hue-rotate(${(t*14).toFixed(2)}deg) saturate(${(1+t*.08).toFixed(4)})`);}
  if(d.hue)fs.push(`hue-rotate(${lerp(d.hue,0).toFixed(2)}deg)`);
  if(d.grayscale)fs.push(`grayscale(${lerp(d.grayscale,0).toFixed(4)})`);
  if(d.sepia)fs.push(`sepia(${lerp(d.sepia,0).toFixed(4)})`);
  if(d.blur)fs.push(`blur(${lerp(d.blur,0).toFixed(2)}px)`);
  const bf=fs.join(' ')||'none',vig=d.vignette?`<div style="position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 45%,rgba(0,0,0,${(lerp(d.vignette,0)).toFixed(3)}) 100%)"></div>`:'';
  return `<div style="position:absolute;inset:0;backdrop-filter:${bf};-webkit-backdrop-filter:${bf}"></div>${vig}`;}
 // Number readouts. group inserts a separator every 3 integer digits ("50 000 000"); style count (default) interpolates,
 // roll spins each digit column like an odometer and settles left to right, scramble shows seeded random digits that
 // lock in left to right. All three land on exactly `to` when progress reaches 1.
 // sep groups thousands; dm is the decimal mark (given, else ',' when sep is '.', else '.'; editvideo/widgets.decimal_mark)
 const grouped=(s,sep,dm='.')=>{const [i,dec]=s.split('.'),neg=i.startsWith('-'),body=sep?(neg?i.slice(1):i).replace(/\B(?=(\d{3})+(?!\d))/g,sep):(neg?i.slice(1):i);return (neg?'-':'')+body+(dec?(dm||'.')+dec:'');};
 function counterWidget(item,f,p){const d=item.data||{},from=d.from||0,to=d.to??100,dp=d.decimals||0,sep=d.group||'',dm=d.decimal_mark||(sep==='.'?',':'.'),style=d.style||'count';
  const pre=esc(d.prefix||''),suf=esc(d.suffix||'');
  if(style==='count')return pre+esc(grouped((from+(to-from)*p).toFixed(dp),sep,dm))+suf;
  const target=grouped(to.toFixed(dp),sep,dm),chars=Array.from(target),digits=chars.filter(ch=>/\d/.test(ch)).length,stagger=.45;let k=0;
  const body=chars.map(ch=>{if(!/\d/.test(ch))return esc(ch);const i=k++,off=digits<=1?0:i/(digits-1)*stagger,q=clamp((p-off)/(1-stagger));
   if(style==='scramble'){if(q>=1)return ch;if(p<=0)return `<span style="opacity:.0">${ch}</span>`;return `<span style="opacity:.8">${Math.floor(random(d.seed??7,i*97+Math.floor(f/2))*10)}</span>`;}
   if(q<=0&&i<digits-1)return `<span style="visibility:hidden">${ch}</span>`;
   const pos=(10*(d.spins??2)+(+ch))*(1-Math.pow(1-q,3)),frac=pos%10,col=Array.from({length:11},(_,n)=>`<span style="display:block;height:1.15em">${n%10}</span>`).join('');
   return `<span style="display:inline-block;height:1.15em;line-height:1.15em;overflow:hidden;vertical-align:bottom"><span style="display:block;transform:translateY(${(-frac*1.15).toFixed(4)}em)">${col}</span></span>`;}).join('');
  return pre+body+suf;}
 // Particle systems in the layer's own pixel space, deterministic per (seed, frame) so any frame renders alone.
 // bunch: an elongated cloud travelling along `angle` across the box as progress runs (accelerator bunch, swarm);
 // stream: continuous flow along `angle` at `speed` box-lengths per second; drift: slow starfield/dust with
 // size-based parallax and twinkle; tracks: curved tracks drawn out from `origin` (collision event) with a flash.
 // Glowing dots use a radial gradient (white-hot core, coloured halo) instead of per-dot blur filters.
 // Particle system: continuous emission with closed-form physics, so any frame renders alone (no state).
 // Birth i at i/rate (+ jitter); age a = t - birth. Drag k with wind w and gravity g: v_inf = w + g/k,
 // x(a) = x0 + v_inf*a + (v0 - v_inf)(1 - e^{-k a})/k  (ballistic when k -> 0). Turbulence is a smooth field sampled at the
 // particle's base path so neighbours drift together. Size, opacity and colour (OKLab) follow the particle's life.
 const PRESETS={fire:{rate:420,life:[.6,1.2],speed:[60,130],angle:-90,spread:40,gravity:-220,drag:1.5,wind:[0,0],turb:[22,90,1.2],size:[46,14],sizeVar:.6,
   opacity:[[0,0],[.12,.85],[.6,.55],[1,0]],colors:['#fff4c0','#ffb000','#ff4a00','#5a0e00'],emitter:{shape:'line',w:.5},blend:'add',soft:1,flicker:.25},
  embers:{rate:40,life:[2,4],speed:[40,110],angle:-80,spread:50,gravity:-40,drag:.4,wind:[30,0],turb:[45,140,.7],size:[3.5,1.5],sizeVar:.5,
   opacity:[[0,0],[.1,1],[.8,.9],[1,0]],colors:['#fff1b0','#ffae3c','#ff5a1e'],emitter:{shape:'line',w:.7},blend:'add',soft:.35,flicker:.6,streak:120},
  sparks:{burst:140,rate:0,life:[.3,.9],speed:[400,1200],angle:-90,spread:110,gravity:900,drag:.8,wind:[0,0],turb:[0,1,0],size:[3,1.2],sizeVar:.4,
   opacity:[[0,1],[.7,.9],[1,0]],colors:['#ffffff','#ffd27a','#ff7a1e'],emitter:{shape:'point'},blend:'add',soft:.2,streak:300},
  smoke:{rate:14,life:[3,5],speed:[20,50],angle:-90,spread:30,gravity:-15,drag:.3,wind:[18,0],turb:[60,220,.25],size:[80,400],sizeVar:.4,
   opacity:[[0,0],[.25,.35],[1,0]],colors:['#9a9a9a','#6b6b6b'],emitter:{shape:'line',w:.4},blend:'normal',soft:1},
  bokeh:{rate:6,life:[4,7],speed:[5,20],angle:-90,spread:180,gravity:-4,drag:.2,wind:[8,0],turb:[20,300,.15],size:[40,90],sizeVar:.8,
   opacity:[[0,0],[.3,.28],[.7,.22],[1,0]],colors:['#ffd9a0','#ff9f6b'],emitter:{shape:'box',w:1,h:1},blend:'add',soft:.25}};
 function systemParticles(item,f,W,H){const d=item.data||{},P={...PRESETS[d.preset||'fire'],...(d.physics||{})},sd=d.seed??7,u=H/1080,t=f/30;
  const rnd=(i,k)=>random(sd,i*31+k),rate=P.rate||0,burst=P.burst||0,[l0,l1]=P.life,em=P.emitter||{shape:'point'};
  const ox=(d.origin?.[0]??.5)*W,oy=(d.origin?.[1]??.85)*H,k=P.drag||0,g=[0,(P.gravity||0)*u],wv=(P.wind||[0,0]).map(v=>v*u),[ta,ts,tv]=P.turb||[0,1,0];
  const cols=P.colors,nb=8,id='ps'+sid(item.id||'p'),soft=P.soft??.5,shutter=(P.streak||0)/360/30;
  const bucket=q=>Math.min(nb-1,Math.floor(clamp(q)*nb)),colAt=q=>{const x=clamp(q)*(cols.length-1),i=Math.min(cols.length-2,Math.floor(x));return cols.length<2?cols[0]:mixColor(cols[i],cols[i+1],x-i);};
  const defs=Array.from({length:nb},(_,b)=>{const c=colAt((b+.5)/nb);return `<radialGradient id="${id}${b}"><stop offset="0" stop-color="${c}"/><stop offset="${(1-soft*.75).toFixed(2)}" stop-color="${c}" stop-opacity="${(.9-soft*.4).toFixed(2)}"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient>`;}).join('');
  const opAt=q=>{const ks=P.opacity;for(let i=1;i<ks.length;i++)if(q<=ks[i][0])return ks[i-1][1]+(ks[i][1]-ks[i-1][1])*(q-ks[i-1][0])/Math.max(1e-6,ks[i][0]-ks[i-1][0]);return ks[ks.length-1][1];};
  const pos=(i,a)=>{const th=((P.angle||0)+(rnd(i,1)-.5)*(P.spread||0))*Math.PI/180,sp=(P.speed[0]+(P.speed[1]-P.speed[0])*rnd(i,2))*u,v0=[Math.cos(th)*sp,Math.sin(th)*sp];
   const ex=em.shape==='point'?0:(rnd(i,3)-.5)*(em.w??.3)*W,ey=em.shape==='box'||em.shape==='ellipse'?(rnd(i,4)-.5)*(em.h??.3)*H:0;
   const out=[0,1].map(j=>{const vi=wv[j]+(k>1e-4?g[j]/k:0);return k>1e-4?vi*a+(v0[j]-vi)*(1-Math.exp(-k*a))/k:(v0[j]+wv[j])*a+.5*g[j]*a*a;});
   let x=ox+ex+out[0],y=oy+ey+out[1];if(ta){const r=Math.min(1,a/.5)*ta*u,s=ts*u;x+=r*Math.sin(y/s+t*tv*6.283+sd)*Math.cos(x/s*.7-t*tv*3.1);y+=r*Math.cos(x/s+t*tv*5.1+sd*1.3)*Math.sin(y/s*.8+t*tv*2.3);}
   return [x,y];};
  const items=[],add=(i,birth)=>{const life=l0+(l1-l0)*rnd(i,5),a=t-birth;if(a<0||a>=life)return;const q=a/life,[x,y]=pos(i,a);
   const sz=(P.size[0]+(P.size[1]-P.size[0])*q)*u*(1+((rnd(i,6)-.5)*2)*(P.sizeVar||0)),op=opAt(q)*(P.flicker?1-P.flicker*(.5+.5*Math.sin(t*23+rnd(i,7)*6.283)):1);
   if(op<=.004||sz<=.2||x<-sz||x>W+sz||y<-sz||y>H+sz)return;
   if(shutter>0){const [x2,y2]=pos(i,Math.max(0,a-shutter));if(Math.hypot(x-x2,y-y2)>sz*.6){items.push(`<line x1="${x2.toFixed(1)}" y1="${y2.toFixed(1)}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${colAt(q)}" stroke-width="${Math.max(.6,sz).toFixed(2)}" stroke-linecap="round" opacity="${op.toFixed(3)}"/>`);return;}}
   items.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(sz/2*(1+soft)).toFixed(2)}" fill="url(#${id}${bucket(q)})" opacity="${op.toFixed(3)}"/>`);};
  for(let i=0;i<burst;i++)add(1e6+i,0);
  if(rate>0){const first=Math.max(0,Math.floor((t-l1)*rate)),last=Math.floor(t*rate),stepN=Math.max(1,Math.ceil((last-first+1)/(d.max_particles||900)));
   for(let i=first;i<=last;i+=stepN)add(i,i/rate+rnd(i,9)/rate);}
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W.toFixed(1)} ${H.toFixed(1)}" width="100%" height="100%" preserveAspectRatio="none" style="display:block;overflow:visible"><defs>${defs}</defs>${items.join('')}</svg>`;}
 function particlesWidget(item,f,p){const d=item.data||{},W=(item._canvas_width||1920)*(item.width||1),H=(item._canvas_height||1080)*(item.height||1);
  if(d.mode==='system')return systemParticles(item,f,W,H);
  const seed=d.seed??7,n=d.count||200,c=esc(item.color||'#ffb347'),c2=esc(d.secondary_color||item.color||'#ffffff'),R=d.radius??3,glow=d.glow??2.5;
  const id='pg'+String(item.id||'p').replace(/[^a-zA-Z0-9_-]/g,'_'),rnd=(i,k)=>random(seed,i*13+k),gauss=(i,k)=>(rnd(i,k)+rnd(i,k+1)+rnd(i,k+2)-1.5)/1.5;
  const defs=`<radialGradient id="${id}"><stop offset="0" stop-color="#ffffff"/><stop offset=".22" stop-color="${c}" stop-opacity=".95"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient><radialGradient id="${id}b"><stop offset="0" stop-color="#ffffff"/><stop offset=".22" stop-color="${c2}" stop-opacity=".95"/><stop offset="1" stop-color="${c2}" stop-opacity="0"/></radialGradient>`;
  const a=(d.angle??0)*Math.PI/180,ux=Math.cos(a),uy=Math.sin(a),vx=-uy,vy=ux,diag=Math.hypot(W,H),dot=(x,y,r,o,b)=>`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(r*glow).toFixed(2)}" fill="url(#${id}${b?'b':''})" opacity="${clamp(o).toFixed(3)}"/>`;
  let out='';
  if(d.mode==='bunch'||d.mode==='stream'){const len=(d.length??.35)*diag,wid=(d.spread??.06)*diag,t=f/30;
   for(let i=0;i<n;i++){let s;if(d.mode==='bunch'){const cen=-.25+1.5*p;s=cen*diag+gauss(i,0)*len*.5;}else{s=(((rnd(i,0)+t*(d.speed??.25)*(.8+.4*rnd(i,5)))%1)*1.3-.15)*diag;}
    const off=gauss(i,3)*wid*(d.mode==='bunch'?Math.max(.25,1-Math.abs(gauss(i,0))*.6):1),jit=Math.sin(t*6+rnd(i,7)*6.28)*wid*.04;
    const x=W/2+(s-diag/2)*ux+(off+jit)*vx,y=H/2+(s-diag/2)*uy+(off+jit)*vy,r=R*(.5+rnd(i,8)),o=.45+.55*rnd(i,9);
    if(x>-50&&x<W+50&&y>-50&&y<H+50)out+=dot(x,y,r,o,rnd(i,10)<(d.mix??0));}}
  else if(d.mode==='drift'){const t=f/30,sp=(d.speed??.02)*diag;
   for(let i=0;i<n;i++){const depth=.3+.7*rnd(i,0),r=R*depth*(.6+.8*rnd(i,1)),x0=rnd(i,2)*(W+100)-50+ux*sp*depth*t,y0=rnd(i,3)*(H+100)-50+uy*sp*depth*t;
    const x=((x0%(W+100))+(W+100))%(W+100)-50,y=((y0%(H+100))+(H+100))%(H+100)-50,tw=1-(d.twinkle??.5)*(.5+.5*Math.sin(t*(1+2*rnd(i,4))*2+rnd(i,5)*6.28));
    out+=dot(x,y,r,(.25+.75*depth)*tw,rnd(i,6)<(d.mix??0));}}
  else if(d.mode==='tracks'){const [ox,oy]=d.origin||[.5,.5],cx=ox*W,cy=oy*H,k=d.curvature??1,sw=d.stroke_width??2.2;
   for(let i=0;i<Math.min(n,300);i++){const th=rnd(i,0)*Math.PI*2,L=(.15+.6*Math.pow(rnd(i,1),.7))*diag*.5,kap=(rnd(i,2)-.5)*2*k*4/diag,start=rnd(i,3)*.35,q=ease(clamp((p-start)/.65),'ease_out');
    if(q<=0)continue;const pts=[];for(let j=0;j<=24;j++){const s=L*j/24;pts.push(Math.abs(kap)<1e-6?[cx+Math.cos(th)*s,cy+Math.sin(th)*s]:[cx+(Math.sin(th+kap*s)-Math.sin(th))/kap,cy-(Math.cos(th+kap*s)-Math.cos(th))/kap]);}
    const col=rnd(i,4)<(d.mix??.35)?c2:c,end=pts[Math.min(24,Math.round(24*q))];
    out+=`<polyline points="${pts.map(v=>v[0].toFixed(1)+','+v[1].toFixed(1)).join(' ')}" fill="none" stroke="${col}" stroke-width="${(sw*(.5+rnd(i,5))).toFixed(2)}" stroke-linecap="round" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${(1-q).toFixed(4)}" opacity="${(.55+.45*rnd(i,6)).toFixed(3)}" style="filter:drop-shadow(0 0 ${(sw*2).toFixed(1)}px ${col})"/>`;
    if(q>.97)out+=dot(end[0],end[1],R*.8,.9,true);}
   const fl=Math.pow(1-clamp(p*2.2),2);if(fl>0)out+=dot(cx,cy,diag*.06*(.4+fl),fl,false);}
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W.toFixed(1)} ${H.toFixed(1)}" width="100%" height="100%" preserveAspectRatio="none" style="display:block;overflow:visible"><defs>${defs}</defs>${out}</svg>`;}
 function widget(item,f){const d=item.data||{},p=progress(item,f),c=esc(item.color||'#81e6be');
  if(item.kind==='null')return '';
  if(item.kind==='film')return filmWidget(item,f);
  if(item.kind==='adjust')return adjustWidget(item,f);
  if(item.kind==='svg')return svgWidget(item,f);
  if(item.kind==='text'){const h=textWidget(item,f),inner=d.align?`<div style="text-align:${esc(d.align)}">${h}</div>`:h;
   // text on its own plate: inset from the plate's edges and centred in its height (glyphs had sat in the top-left
   // corner of every lower third, chip and credit box); the inset stays within the 24 px that text fitting reserves
   return plated(item)?`<div style="box-sizing:border-box;height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 min(.35em,24px)"><div>${inner}</div></div>`:inner;}
  if(item.kind==='pattern')return patternWidget(item);
  if(item.kind==='icon')return `<svg viewBox="0 0 24 24" width="100%" height="100%" style="display:block"><path d="${iconPaths[d.icon]||''}" fill="none" stroke="${c}" stroke-width="${d.stroke_width??1.8}" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  if(item.kind==='caption'){
   const page=d.pages?.find(page=>f>=page.start_frame&&f<page.end_frame);if(d.pages&&!page)return '';
   const words=page?.words||d.words||[],active=words.reduce((n,w,i)=>f>=w.start_frame&&f<w.end_frame?i:n,-1),mode=d.mode||'box';
   // Short-form word motion (deterministic per frame, so both engines match): pop = a word lands with a small
   // overshoot and the spoken word stays slightly larger; bounce = a hop on the word's onset; rise = words slide up
   // into place. Transforms do not reflow the line. outline = a ring of text-shadows (em) plus a soft drop shadow.
   const anim=d.animation||'none',back=e=>{const x=e-1;return 1+2.70158*x*x*x+1.70158*x*x;},ow=d.outline||0,oc=esc(d.outline_color||'#000000');
   const ring=ow>0?`text-shadow:${[0,45,90,135,180,225,270,315].map(a=>`${(Math.cos(a*Math.PI/180)*ow).toFixed(3)}em ${(Math.sin(a*Math.PI/180)*ow).toFixed(3)}em 0 ${oc}`).join(',')},0 ${(ow*1.6).toFixed(3)}em ${(ow*2.4).toFixed(3)}em rgba(0,0,0,.45);`:'';
   const age0=page?f-page.start_frame:99,pagePop=anim==='pop'&&age0<5?.86+.14*back(clamp(age0/5)):1;
   const motion=(w,on)=>{const age=f-w.start_frame;if(anim==='none'||age<0)return '';
    if(anim==='pop')return `transform:scale(${((age<5?.72+.28*back(clamp(age/5)):1)*(on?(d.active_scale??1.08):1)).toFixed(4)});`;
    if(anim==='bounce')return `transform:translateY(${(age<7?-.22*Math.sin(Math.PI*clamp(age/7)):0).toFixed(4)}em);`;
    if(anim==='rise'){const e=clamp(age/5);return `transform:translateY(${((1-ease(e,'ease_out'))*.35).toFixed(4)}em);opacity:${e.toFixed(3)};`;}
    return '';};
   return `<div style="font-weight:${item._type?.fontWeight||700};text-align:center;line-height:${item._type?.lineHeight||1.45};white-space:normal${pagePop!==1?`;transform:scale(${pagePop.toFixed(4)});transform-origin:50% 60%`:''}"><div style="display:inline-block;max-width:100%;background:${esc(item.background||'transparent')};padding:.15em .25em;border-radius:.12em">${words.map((w,i)=>{const on=i===active,foreground=on?d.active_color||'#101820':w.color||item.color||'#ffffff',background=on&&mode==='box'?d.active_background||'#e4b866':'transparent';return `<span style="display:inline-block;margin:0 .07em;padding:0 .12em;border-radius:.1em;color:${esc(foreground)};background:${esc(background)};opacity:${f<w.start_frame?(d.future_opacity??.65):1};transform-origin:50% 70%;${ring}${on&&mode==='underline'?`border-bottom:.08em solid ${esc(d.active_background||'#e4b866')};`:''}${motion(w,on)}">${esc(w.text)}</span>`;}).join(' ')}</div></div>`;
  }
  if(item.kind==='callout'){
   const W=(item._canvas_width||1920)*item.width,H=(item._canvas_height||1080)*item.height;
   let target=d.target||[.5,.5];if(d.target_keyframes?.length)target=['x','y'].map(k=>track(d.target_keyframes.map(n=>({frame:n.frame,value:n[k],easing:'linear'})),f));
   const tx=target[0]*W,ty=target[1]*H,lx=d.label_point[0]*W,ly=d.label_point[1]*H,bw=(d.label_width||.25)*W,fs=item.font_size||30,sw=d.stroke_width??3;
   const lines=String(item.text||'').split('\n'),bh=lines.length*fs*1.3+fs*.6,ax=lx+bw/2,ay=ly+bh/2;
   return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="100%" height="100%" style="overflow:visible"><path d="M${tx} ${ty}L${ax} ${ty}L${ax} ${ay}" fill="none" stroke="${c}" stroke-width="${sw}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="${1-p}"/><circle cx="${tx}" cy="${ty}" r="${sw*2}" fill="${c}"/><rect x="${lx}" y="${ly}" width="${bw}" height="${bh}" rx="${fs*.2}" fill="${esc(item.background==='transparent'?'#101820':item.background||'#101820')}"/>${lines.map((line,i)=>`<text x="${lx+fs*.3}" y="${ly+fs*(1+i*1.3)}" font-family="inherit" fill="${c}" font-size="${fs}">${esc(line)}</text>`).join('')}</svg>`;
  }
  if(item.kind==='counter'){const h=counterWidget(item,f,p);return d.align?`<div style="text-align:${esc(d.align)}">${h}</div>`:h;}
  let svg='',view='0 0 1000 500';
  if(item.kind==='shape'){const shape=d.shape||'rectangle',sw=d.stroke_width??8;svg=shape==='ellipse'?`<ellipse cx="500" cy="250" rx="490" ry="240" fill="${c}"/>`:shape==='triangle'?`<path d="M500 10L990 490H10Z" fill="${c}"/>`:shape==='arrow'?`<path d="M10 190H700V30L990 250 700 470V310H10Z" fill="${c}"/>`:shape==='ring'?`<ellipse cx="500" cy="250" rx="470" ry="220" fill="none" stroke="${c}" stroke-width="${sw}"/>`:`<rect x="0" y="0" width="1000" height="500" rx="${d.corner_radius??24}" fill="${c}"/>`;}
  if(item.kind==='bar_chart'){const num=v=>grouped(String(v),d.group||'',d.decimal_mark||(d.group==='.'?',':'.')),values=d.values||[],low=d.min??0,high=d.max??Math.max(1,...values),row=460/Math.max(1,values.length);svg=values.map((v,i)=>`<text x="0" y="${i*row+row*.6}" fill="${c}" font-size="32">${esc(d.labels?.[i]??i+1)}</text><rect x="230" y="${i*row+8}" width="${650*clamp((v-low)/(high-low))*p}" height="${Math.max(4,row-24)}" rx="6" fill="${esc(d.colors?.[i]||c)}"/><text x="900" y="${i*row+row*.6}" fill="${c}" font-size="32">${esc(num(v))}</text>`).join('')+`<text x="230" y="494" fill="${c}" font-size="24">${esc(num(low))}</text><text x="825" y="494" fill="${c}" font-size="24">${esc(num(high))}</text>`;}
  if(item.kind==='line_chart'){const v=d.values||[],lo=d.min??0,hi=d.max??Math.max(1,...v);const points=v.map((n,i)=>`${60+i*880/Math.max(1,v.length-1)},${420-clamp((n-lo)/(hi-lo))*360}`).join(' ');svg=`<path d="M60 50V420H940" fill="none" stroke="${c}" opacity=".4" stroke-width="3"/><polyline points="${points}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="${1-p}" fill="none" stroke="${c}" stroke-width="${d.stroke_width??8}"/><text x="0" y="60" fill="${c}" font-size="26">${esc(hi)}</text><text x="0" y="420" fill="${c}" font-size="26">${esc(lo)}</text>`+(d.labels||[]).map((label,i)=>`<text text-anchor="middle" x="${60+i*880/Math.max(1,v.length-1)}" y="470" fill="${c}" font-size="26">${esc(label)}</text>`).join('');}
  if(item.kind==='flow'){const labels=d.labels||[],w=1000/Math.max(1,labels.length);svg=labels.map((label,i)=>`<g opacity="${clamp(p*labels.length-i)}"><rect x="${i*w+8}" y="140" width="${w-40}" height="180" rx="20" stroke="${c}" fill="none" stroke-width="5"/><text text-anchor="middle" x="${i*w+w/2-12}" y="244" fill="${c}" font-size="${Math.min(32,180/Math.max(1,Array.from(label).length))}">${esc(label)}</text>${i<labels.length-1?`<path d="M${(i+1)*w-27} 230h30m-8-8 8 8-8 8" stroke="${c}" stroke-width="4" fill="none"/>`:''}</g>`).join('');}
  if(item.kind==='particles'){if(d.mode&&d.mode!=='burst')return particlesWidget(item,f,p);const count=d.count||40,seed=d.seed??7;svg=Array.from({length:count},(_,i)=>{const a=random(seed,i)*Math.PI*2,r=(80+random(seed,i+count)*360)*p;return `<circle cx="${500+Math.cos(a)*r}" cy="${250+Math.sin(a)*r*.6}" r="${d.radius??4}" fill="${c}" opacity="${1-p*.8}"/>`;}).join('');}
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${view}" preserveAspectRatio="${item.kind==='shape'?'none':'xMidYMid meet'}" width="100%" height="100%" style="display:block;overflow:visible">${svg}</svg>`;
 }
 function texture(item,f){return (item.effects||[]).filter(e=>f>=(e.start_frame||0)).map(e=>{const a=e.params?.amount??defaults[e.name],p=phase(e,f);
  if(e.name==='radial_glow')return `<div style="position:absolute;inset:0;background:radial-gradient(ellipse at center,${esc(e.params?.color||'#81e6be')} 0%,transparent 68%);opacity:${a};pointer-events:none"></div>`;
  if(e.name==='light_sweep')return `<div style="position:absolute;inset:0;overflow:hidden;pointer-events:none"><div style="position:absolute;top:-30%;height:160%;width:30%;left:${-50+p*200}%;transform:skewX(-18deg);background:linear-gradient(90deg,transparent,${esc(e.params?.color||'#ffffff')},transparent);opacity:${a};mix-blend-mode:screen"></div></div>`;
  if(e.name==='paper_grain'){const id='grain-'+String(item.id||'x').replace(/[^a-zA-Z0-9_-]/g,'_');return `<svg width="100%" height="100%" style="position:absolute;inset:0;opacity:${a};pointer-events:none;mix-blend-mode:soft-light"><filter id="${id}"><feTurbulence type="fractalNoise" baseFrequency=".7" numOctaves="3" seed="${Math.floor(e.params?.seed??7)}"/><feColorMatrix type="saturate" values="0"/></filter><rect width="100%" height="100%" filter="url(#${id})"/></svg>`;}
  return e.name==='vignette'?`<div style="position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 30%,rgba(0,0,0,${a}) 100%);pointer-events:none"></div>`:e.name==='scanlines'?`<div style="position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(0,0,0,${a}) 0px,rgba(0,0,0,${a}) 2px,transparent 2px,transparent 5px);pointer-events:none"></div>`:'';}).join('');}

 // ---------------------------------------------------------------- compositing (both engines)
 // Affine 2D matrices [a,b,c,d,e,f] (CSS matrix order) in canvas pixels.
 const mmul=(m,n)=>[m[0]*n[0]+m[2]*n[1],m[1]*n[0]+m[3]*n[1],m[0]*n[2]+m[2]*n[3],m[1]*n[2]+m[3]*n[3],m[0]*n[4]+m[2]*n[5]+m[4],m[1]*n[4]+m[3]*n[5]+m[5]];
 const mT=(x,y)=>[1,0,0,1,x,y],mRS=(s,deg)=>{const r=deg*Math.PI/180;return [Math.cos(r)*s,Math.sin(r)*s,-Math.sin(r)*s,Math.cos(r)*s,0,0];};
 const minv=m=>{const d=m[0]*m[3]-m[1]*m[2]||1e-9;return [m[3]/d,-m[1]/d,-m[2]/d,m[0]/d,(m[2]*m[5]-m[3]*m[4])/d,(m[1]*m[4]-m[0]*m[5])/d];};
 const pivot=(it,W,H)=>{const [ax,ay]=it.anchor||[.5,.5];return [(it.x+ax*it.width)*W,(it.y+ay*it.height)*H];};
 // A layer's own transform around its anchor at its local frame g-start, in CSS order translate · scale(sx,sy) · rotate ·
 // skewX (matching styleAt), plus the rig angle (follow-through, IK) unless bare.
 function localMatrix(it,g,byId,W,H,bare){const dur=Math.max(1,(it.end_frame||1)-(it.start_frame||0)),r=styleAt(it,clamp(g-(it.start_frame||0),0,dur-1),true,byId),[px,py]=pivot(it,W,H);
  const rot=r.rot+(bare?0:rigAngle(it,g,byId,W,H)),sx=r.scale*(r.sx||1),sy=r.scale*(r.sy||1),sk=r.skew?Math.tan(r.skew*Math.PI/180):0;
  let m=mmul([sx,0,0,sy,0,0],mRS(1,rot));if(sk)m=mmul(m,[1,0,sk,1,0,0]);
  return mmul(mT(px+r.x,py+r.y),mmul(m,mT(-px,-py)));}
 // Parenting: world = parent world [x parent world at bind frame ^-1] x own local. Translate/scale/rotate inherit; opacity and filters do not.
 function worldMatrix(it,g,byId,W,H,depth=0,bare=false){let m=localMatrix(it,g,byId,W,H,bare);const p=it.parent&&byId[it.parent];
  if(p&&depth<8){let pm=worldMatrix(p,g,byId,W,H,depth+1);if(it.parent_bind_frame!=null)pm=mmul(pm,minv(worldMatrix(p,it.parent_bind_frame,byId,W,H,depth+1)));m=mmul(pm,m);}return m;}
 const apply2=(m,p)=>[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]];
 // Rig angle added to a layer's rotation: follow-through lag, plus its share of a two-bone IK solve (as the lower bone that
 // carries `ik`, or as that bone's parent, the upper bone). Children of rigged bones inherit through worldMatrix.
 const IK_INDEX=new WeakMap();
 function ikUpper(byId){let ix=IK_INDEX.get(byId);if(!ix){ix={};for(const l of Object.values(byId))if(l&&l.ik&&l.parent&&byId[l.ik.target])ix[l.parent]=l;IK_INDEX.set(byId,ix);}return ix;}
 function rigAngle(it,g,byId,W,H){if(!byId)return 0;let a=0;
  if(it.follow&&it.parent&&byId[it.parent])a+=followAngle(it,g,byId,W,H);
  if(it.ik&&it.parent&&byId[it.parent]&&byId[it.ik.target])a+=ikSolve(it,g,byId,W,H)[1];
  const lo=ikUpper(byId)[it.id];if(lo)a+=ikSolve(lo,g,byId,W,H)[0];
  return a;}
 // Two-bone IK (law of cosines): the upper bone pivots at its anchor, the lower bone (its child, carrying ik) at its own
 // anchor; ik.tip is the end point in the lower bone's box. Bone lengths come from the un-rigged pose at this frame, so
 // keyed scale or squash on a bone still reads. Out of reach the limb straightens toward the target; bend picks the elbow
 // side (cw = clockwise on screen); weight blends with the keyed (FK) pose. Returns [upper Δ°, lower Δ°].
 const IK_CACHE=new WeakMap();
 function ikSolve(lo,g,byId,W,H){const hit=IK_CACHE.get(lo);if(hit&&hit.g===g&&hit.W===W&&hit.byId===byId)return hit.r;
  const up=byId[lo.parent],T=byId[lo.ik.target],k=lo.ik,deg=180/Math.PI;
  const Mu=worldMatrix(up,g,byId,W,H,0,true),Ml=mmul(Mu,localMatrix(lo,g,byId,W,H,true)),tip=k.tip||[.5,1];
  const P0=apply2(Mu,pivot(up,W,H)),P1=apply2(Ml,pivot(lo,W,H)),Q=apply2(Ml,[(lo.x+tip[0]*lo.width)*W,(lo.y+tip[1]*lo.height)*H]);
  const Tp=apply2(worldMatrix(T,g,byId,W,H),pivot(T,W,H)),L1=Math.hypot(P1[0]-P0[0],P1[1]-P0[1]),L2=Math.hypot(Q[0]-P1[0],Q[1]-P1[1]);
  let r=[0,0];
  if(L1>1e-6&&L2>1e-6){const a1=Math.atan2(P1[1]-P0[1],P1[0]-P0[0]),a2=Math.atan2(Q[1]-P1[1],Q[0]-P1[0]),dx=Tp[0]-P0[0],dy=Tp[1]-P0[1];
   const d=clamp(Math.hypot(dx,dy),Math.abs(L1-L2)+1e-4,L1+L2-1e-4),phi=Math.atan2(dy,dx),s=k.bend==='ccw'?-1:1;
   const al=Math.acos(clamp((L1*L1+d*d-L2*L2)/(2*L1*d),-1,1)),t1=phi-s*al,E=[P0[0]+L1*Math.cos(t1),P0[1]+L1*Math.sin(t1)];
   const R=[P0[0]+d*Math.cos(phi),P0[1]+d*Math.sin(phi)],t2=Math.atan2(R[1]-E[1],R[0]-E[0]),wrap=x=>((x+Math.PI)%(2*Math.PI)+2*Math.PI)%(2*Math.PI)-Math.PI;
   const w=k.weight??1,d1=wrap(t1-a1)*deg*w,d2=wrap(t2-a2-(t1-a1))*deg*w;r=[d1,d2];}
  IK_CACHE.set(lo,{g,W,byId,r});return r;}
 const fmtM=m=>`matrix(${m.map(v=>+v.toFixed(5)).join(',')})`;
 const sid=s=>String(s).replace(/[^a-zA-Z0-9_-]/g,'_');
 // Masks in the layer's own box (objectBoundingBox units); add/subtract paint white/black in order, intersect nests.
 function maskGeom(mk,f){let g=mk.geom;const ks=mk.keyframes;if(ks?.length){if(f<=ks[0].frame)g=ks[0].geom;else if(f>=ks[ks.length-1].frame)g=ks[ks.length-1].geom;else for(let i=1;i<ks.length;i++)if(f<=ks[i].frame){const a=ks[i-1],b=ks[i],q=curve((f-a.frame)/Math.max(1,b.frame-a.frame),b.easing||'smooth',b.bezier);g=a.geom.map((v,j)=>v+(b.geom[j]-v)*q);break;}}return g;}
 function maskShape(mk,g,fill,filt){const a=`fill="${fill}"${filt?` filter="url(#${filt})"`:''}${mk.opacity!=null&&mk.opacity<1?` fill-opacity="${mk.opacity}"`:''}`;
  if(mk.shape==='rect')return `<rect x="${g[0]}" y="${g[1]}" width="${Math.max(0,g[2])}" height="${Math.max(0,g[3])}" ${a}/>`;
  if(mk.shape==='ellipse')return `<ellipse cx="${g[0]}" cy="${g[1]}" rx="${Math.max(0,g[2])}" ry="${Math.max(0,g[3])}" ${a}/>`;
  const pts=[];for(let i=0;i+1<g.length;i+=2)pts.push(`${g[i]},${g[i+1]}`);return `<polygon points="${pts.join(' ')}" ${a}/>`;}
 function maskDefs(it,f,W,H){const ms=it.masks||[];if(!ms.length)return null;const id='ev-mask-'+sid(it.id),w=Math.max(1,it.width*W),h=Math.max(1,it.height*H),defs=[];
  const inv=!!it.mask_invert,on=inv?'#000':'#fff',off=inv?'#fff':'#000';let body=inv||ms[0].mode==='subtract'?`<rect x="-1" y="-1" width="3" height="3" fill="${inv&&ms[0].mode==='subtract'?'#000':'#fff'}"/>`:'';
  ms.forEach((mk,k)=>{const g=maskGeom(mk,f);let filt='';if(mk.feather_px>0){filt=`${id}-f${k}`;defs.push(`<filter id="${filt}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${(mk.feather_px/2/w).toFixed(5)} ${(mk.feather_px/2/h).toFixed(5)}"/></filter>`);}
   if(mk.mode==='intersect'){const nid=`${id}-i${k}`;defs.push(`<mask id="${nid}" maskUnits="objectBoundingBox" maskContentUnits="objectBoundingBox" x="-1" y="-1" width="3" height="3">${maskShape(mk,g,'#fff',filt)}</mask>`);body=`<g mask="url(#${nid})">${body}</g>`;}
   else body+=maskShape(mk,g,mk.mode==='subtract'?off:on,filt);});
  return {id,defs:`${defs.join('')}<mask id="${id}" maskUnits="objectBoundingBox" maskContentUnits="objectBoundingBox" x="-1" y="-1" width="3" height="3">${body}</mask>`};}
 // Track matte: the source layer's vector content (svg/shape/icon widgets, or text as SVG lines) drawn into a mask in the
 // target's box. alpha uses the source's coverage, luma its brightness; *_inverted flip them.
 function matteMarkup(src,f,W,H,resolved){const w=src.width*W,h=src.height*H;
  if(src.kind==='text'||src.kind==='counter'){const ty=resolved?._type||{},fs=parseFloat(ty.fontSize)||src.font_size||60,lh=(parseFloat(ty.lineHeight)||1.2)*fs,al=src.data?.align||'left',anchor=al==='center'?'middle':al==='right'?'end':'start',x=al==='center'?w/2:al==='right'?w:0;
   const lines=String(src.kind==='counter'?widget(src,f).replace(/<[^>]+>/g,''):plainText(src)).split('\n');
   return `<svg x="0" y="0" width="${w}" height="${h}" overflow="visible"><g font-family="${esc(ty.fontFamily||'sans-serif')}" font-weight="${esc(ty.fontWeight||700)}" font-size="${fs}" fill="${esc(src.color||'#ffffff')}" text-anchor="${anchor}">${lines.map((l,i)=>`<text x="${x}" y="${(fs*.85+i*lh).toFixed(1)}">${esc(l)}</text>`).join('')}</g></svg>`;}
  let s=widget({...src,_canvas_width:W,_canvas_height:H},f);if(!s.trim().startsWith('<svg'))return '';
  return s.replace(/<svg\b([^>]*)>/,(m0,attrs)=>`<svg${attrs.replace(/\s(width|height)="[^"]*"/g,'')} x="0" y="0" width="${w}" height="${h}">`);}
 function matteDefs(it,f,g,byId,W,H,resolve){const mt=it.matte,src=mt&&byId[mt.source];if(!src)return null;
  const id='ev-matte-'+sid(it.id),wt=Math.max(1,it.width*W),ht=Math.max(1,it.height*H),fs=stepFrame(src,clamp(g-(src.start_frame||0),0,Math.max(0,src.end_frame-src.start_frame-1)));
  const sw=worldMatrix(src,g,byId,W,H),place=mmul(minv(mT(it.x*W,it.y*H)),mmul(sw,mT(src.x*W,src.y*H)));  // source box → target box pixels
  const visible=g>=src.start_frame&&g<src.end_frame,inner=visible?matteMarkup(src,fs,W,H,resolve?resolve(src):null):'';
  const mode=mt.mode||'alpha',inv=mode.endsWith('inverted'),luma=mode.startsWith('luma');
  const filt=luma?(inv?`<filter id="${id}-f" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="-1 0 0 0 1 0 -1 0 0 1 0 0 -1 0 1 0 0 0 1 0"/></filter>`:'')
   :`<filter id="${id}-f" color-interpolation-filters="sRGB"><feFlood flood-color="${inv?'#000':'#fff'}"/><feComposite in2="SourceAlpha" operator="in"/></filter>`;
  const fattr=filt?` filter="url(#${id}-f)"`:'';
  return {id,defs:`${filt}<mask id="${id}" maskUnits="objectBoundingBox" maskContentUnits="objectBoundingBox" x="-1" y="-1" width="3" height="3">${inv?'<rect x="-1" y="-1" width="3" height="3" fill="#fff"/>':''}<g transform="scale(${(1/wt).toFixed(8)},${(1/ht).toFixed(8)}) ${fmtM(place)}"><g${fattr}>${inner}</g></g></mask>`};}
 // Chroma key as an SVG filter: d = G - max(R,B) normalised by the key colour; alpha ramps between clip_black and clip_white;
 // choke erodes, soften blurs the matte; spill limits G to (R+B)/2. Blue screen swaps G and B.
 function keyDefs(it){const k=it.key;if(!k)return null;const id='ev-key-'+sid(it.id),blue=k.screen==='blue',[r,g,b]=hexRgb(k.color||(blue?'#0047bb':'#00b140'));
  const dk=Math.max(.05,blue?b-Math.max(r,g):g-Math.max(r,b)),cb=k.clip_black??.1,cw=Math.max(cb+.05,k.clip_white??.6),sl=-1/(cw-cb)/dk,ic=1+cb/(cw-cb);
  const m1=blue?'-1 0 1 0 0':'-1 1 0 0 0',m2=blue?'0 -1 1 0 0':'0 1 -1 0 0';
  const spill=k.spill??.8,despill=blue?`1 0 0 0 0 0 1 0 0 0 ${(.5*spill).toFixed(3)} ${(.5*spill).toFixed(3)} ${(1-spill).toFixed(3)} 0 0 0 0 0 1 0`:`1 0 0 0 0 ${(.5*spill).toFixed(3)} ${(1-spill).toFixed(3)} ${(.5*spill).toFixed(3)} 0 0 0 0 1 0 0 0 0 0 1 0`;
  return {id,defs:`<filter id="${id}" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">`
   +`<feColorMatrix in="SourceGraphic" type="matrix" values="${m1} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1" result="d1"/><feColorMatrix in="SourceGraphic" type="matrix" values="${m2} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1" result="d2"/>`
   +`<feBlend in="d1" in2="d2" mode="darken" result="d"/><feComponentTransfer in="d" result="a0"><feFuncR type="linear" slope="${sl.toFixed(4)}" intercept="${ic.toFixed(4)}"/></feComponentTransfer>`
   +`<feColorMatrix in="a0" type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 1 0 0 0 0" result="alpha"/>`
   +(k.choke_px>0?`<feMorphology in="alpha" operator="erode" radius="${k.choke_px}" result="alpha"/>`:'')+(k.soften_px>0?`<feGaussianBlur in="alpha" stdDeviation="${k.soften_px}" result="alpha"/>`:'')
   +(k.view==='matte'?`<feComposite in="alpha" in2="alpha" operator="over"/>`:`<feColorMatrix in="SourceGraphic" type="matrix" values="${despill}" result="ds"/><feBlend in="SourceGraphic" in2="ds" mode="darken" result="clean"/><feComposite in="clean" in2="alpha" operator="in"/>`)
   +`</filter>`};}
 // Pixel effects that CSS filter() cannot express (threshold, tone remap, displacement, alpha from luminance): one SVG
 // filter per effect per layer, applied after the key and before the CSS filters. Static from start_frame; params.ramp
 // scales the amount by the effect's eased phase instead.
 const FX_FILTERS=new Set(['luma_alpha','tint_fill','highlight_glow','tritone','heat_distortion','light_wrap','halation']);
 const n4=v=>(+v).toFixed(4),tbl=(cs,i)=>cs.map(c=>n4(hexRgb(c)[i])).join(' ');
 function fxDefs(it,f,ns='ev-fx'){const defs=[],urls=[];let i=0;
  for(const e of it.effects||[]){if(!FX_FILTERS.has(e.name)||f<(e.start_frame||0))continue;
   const P=e.params||{},a=(P.amount??defaults[e.name])*(P.ramp?phase(e,f):1),id=`${ns}-${sid(it.id)}-${i++}`;let reg='x="0" y="0" width="100%" height="100%"',body='';
   switch(e.name){
    // Alpha from luminance between clip_black and clip_white (fire, smoke, light leaks shot on black); invert keys whites out.
    case 'luma_alpha':{const cb=P.clip_black??.05,cw=Math.max(cb+.02,P.clip_white??.6),s=a/(cw-cb),sg=P.invert?-1:1,L=[.2126,.7152,.0722].map(v=>n4(v*s*sg)).join(' ');
     body=`<feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 ${L} ${n4(1-a)} ${n4(P.invert?cw*s:-cb*s)}" result="k"/><feComposite in="k" in2="SourceAlpha" operator="in"/>`;break;}
    // Solid colour over the layer's own alpha (AE Fill/Tint): silhouettes, logo colourways, a state flash.
    case 'tint_fill':body=`<feFlood flood-color="${esc(P.color||'#ffffff')}" result="c"/><feComposite in="c" in2="SourceGraphic" operator="in" result="t"/><feComposite in="SourceGraphic" in2="t" operator="arithmetic" k1="0" k2="${n4(1-a)}" k3="${n4(a)}" k4="0"/>`;break;
    // Highlights above `threshold` bloom through three blurs (r/4, r/2, r) added back; anamorphic flattens them into streaks.
    case 'highlight_glow':{const th=clamp(P.threshold??.75,0,.98),k=1/(1-th),r=P.radius??24,an=clamp(P.anamorphic??0),sy=v=>n4(v*(1-an*.92));
     reg=an>.3?'x="-60%" y="-25%" width="220%" height="150%"':'x="-25%" y="-25%" width="150%" height="150%"';
     body=`<feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 ${n4(.2126*k)} ${n4(.7152*k)} ${n4(.0722*k)} 0 ${n4(-th*k)}" result="m"/><feComposite in="m" in2="SourceAlpha" operator="in" result="hi0"/>`
      +(P.color?`<feFlood flood-color="${esc(P.color)}"/><feComposite in2="hi0" operator="in" result="hi"/>`:`<feMerge result="hi"><feMergeNode in="hi0"/></feMerge>`)
      +[.25,.5,1].map((q,j)=>`<feGaussianBlur in="hi" stdDeviation="${n4(r*q)} ${sy(r*q)}" result="b${j}"/>`).join('')
      +`<feComposite in="b0" in2="b1" operator="arithmetic" k2=".5" k3=".3" result="b01"/><feComposite in="b01" in2="b2" operator="arithmetic" k2="1" k3=".2" result="gl"/><feComposite in="SourceGraphic" in2="gl" operator="arithmetic" k2="1" k3="${n4(a)}"/>`;break;}
    // Luminance mapped through shadow → mid → highlight colours, mixed with the original by amount (graded doc/map looks).
    case 'tritone':{const cs=[P.shadow_color||'#0d1b2a',P.color||'#7d8b99',P.highlight_color||'#f4ead5'],L='.2126 .7152 .0722 0 0';
     body=`<feColorMatrix in="SourceGraphic" type="matrix" values="${L} ${L} ${L} 0 0 0 1 0" result="g"/><feComponentTransfer in="g" result="t">${['R','G','B'].map((c,j)=>`<feFunc${c} type="table" tableValues="${tbl(cs,j)}"/>`).join('')}</feComponentTransfer><feComposite in="SourceGraphic" in2="t" operator="arithmetic" k2="${n4(1-a)}" k3="${n4(a)}"/>`;break;}
    // Heat haze: displacement by fractal noise that morphs between seeds every `cycles` frames (no flicker, frame-indexed).
    case 'heat_distortion':{const per=Math.max(2,Math.round(P.cycles??8)),k=Math.floor(f/per),w=ease((f-k*per)/per,'smooth'),bf=1/Math.max(4,P.size??40),sd=P.seed??7;
     const tu=(s,n)=>`<feTurbulence type="fractalNoise" baseFrequency="${n4(bf)} ${n4(bf*2.5)}" numOctaves="2" seed="${s}" result="${n}"/>`;
     body=`${tu(sd+k,'n0')}${tu(sd+k+1,'n1')}<feComposite in="n0" in2="n1" operator="arithmetic" k2="${n4(1-w)}" k3="${n4(w)}" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="${n4(a)}" xChannelSelector="R" yChannelSelector="G"/>`;break;}
    // Film halation: light scattered back from the film base reddens the edges of bright areas. Highlights above the
    // threshold become an orange-red luminance image, blurred at radius and 2x radius (measured ≈ 2-3 % of frame height).
    case 'halation':{const th=clamp(P.threshold??.78,0,.98),k=1/(1-th),r=P.radius??18,t=hexRgb(P.color||'#ff5a1f');
     reg='x="-10%" y="-10%" width="120%" height="120%"';
     body=`<feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 ${n4(.2126*k)} ${n4(.7152*k)} ${n4(.0722*k)} 0 ${n4(-th*k)}" result="m"/><feComposite in="m" in2="SourceAlpha" operator="in" result="hi0"/>`
      +`<feColorMatrix in="hi0" type="matrix" values="${[0,1,2].map(i=>`${n4(.2126*t[i])} ${n4(.7152*t[i])} ${n4(.0722*t[i])} 0 0`).join(' ')} 0 0 0 1 0" result="hi"/>`
      +`<feGaussianBlur in="hi" stdDeviation="${n4(r)}" result="b0"/><feGaussianBlur in="hi" stdDeviation="${n4(r*2)}" result="b1"/>`
      +`<feComposite in="b0" in2="b1" operator="arithmetic" k2=".6" k3=".4" result="gl"/><feComposite in="SourceGraphic" in2="gl" operator="arithmetic" k2="1" k3="${n4(a)}"/>`;break;}
    // Light wrap: the backdrop colour (params.color, sample it from the plate) bleeds into the inside edge of a cut-out.
    case 'light_wrap':{const r=P.radius??12;
     body=`<feGaussianBlur in="SourceAlpha" stdDeviation="${n4(r)}" result="b"/><feComponentTransfer in="b" result="ib"><feFuncA type="linear" slope="-1" intercept="1"/></feComponentTransfer><feComposite in="ib" in2="SourceAlpha" operator="in" result="edge"/><feFlood flood-color="${esc(P.color||'#ffffff')}"/><feComposite in2="edge" operator="in" result="wrap"/><feComposite in="SourceGraphic" in2="wrap" operator="arithmetic" k2="1" k3="${n4(a)}"/>`;break;}
   }
   defs.push(`<filter id="${id}" ${reg} color-interpolation-filters="sRGB">${body}</filter>`);urls.push(`url(#${id})`);}
  return {defs,urls};}
 // The same pixel effects on a shot (tritone, halation, glows, keys, heat haze): shots take them too, as the catalogue
 // says; shot, held-frame and layer filters live in separate id namespaces.
 function pixelFilters(it,f,ns='ev-sfx'){const fx=fxDefs(it,f,ns);  // ev-sfx: shots, ev-pfx: held poster frames, ev-fx: layers
  return {defs:fx.defs.length?`<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true"><defs>${fx.defs.join('')}</defs></svg>`:'',filter:fx.urls.join(' ')};}
 const withPixel=(style,px)=>{if(px&&px.filter)style.filter=`${px.filter} ${style.filter&&style.filter!=='none'?style.filter:''}`.trim();return style;};
 // Corner pin: the homography taking the layer box onto four frame points (TL, TR, BR, BL, frame-normalised) as a CSS
 // matrix3d about the box's top-left. A track ([{frame, corners}], layer-local frames) interpolates linearly between samples.
 function solve8(A,b){const n=8,M=A.map((r,i)=>[...r,b[i]]);
  for(let c=0;c<n;c++){let p=c;for(let r=c+1;r<n;r++)if(Math.abs(M[r][c])>Math.abs(M[p][c]))p=r;[M[c],M[p]]=[M[p],M[c]];const d=M[c][c];if(Math.abs(d)<1e-12)return null;
   for(let r=0;r<n;r++){if(r===c)continue;const k=M[r][c]/d;if(k)for(let j=c;j<=n;j++)M[r][j]-=k*M[c][j];}}
  return M.map((r,i)=>r[n]/r[i]);}
 function homography(src,dst){const A=[],b=[];for(let i=0;i<4;i++){const [x,y]=src[i],[u,v]=dst[i];A.push([x,y,1,0,0,0,-u*x,-u*y]);b.push(u);A.push([0,0,0,x,y,1,-v*x,-v*y]);b.push(v);}return solve8(A,b);}
 function pinCorners(cp,f){const tr=cp.track;if(!tr||!tr.length)return cp.corners;if(f<=tr[0].frame)return tr[0].corners;const L=tr[tr.length-1];if(f>=L.frame)return L.corners;
  let lo=0,hi=tr.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(tr[m].frame<=f)lo=m;else hi=m;}
  const A=tr[lo],B=tr[hi],t=(f-A.frame)/Math.max(1e-9,B.frame-A.frame);return A.corners.map((c,i)=>[c[0]+(B.corners[i][0]-c[0])*t,c[1]+(B.corners[i][1]-c[1])*t]);}
 function pinMatrix(it,f,W,H){const c=pinCorners(it.corner_pin,f);if(!c||c.length!==4)return null;const w=it.width*W,h=it.height*H,ox=it.x*W,oy=it.y*H;
  const m=homography([[0,0],[w,0],[w,h],[0,h]],c.map(p=>[p[0]*W-ox,p[1]*H-oy]));if(!m)return null;const [a,b,cc,d,e,ff,gg,hh]=m;
  return `matrix3d(${[a,d,0,gg,b,e,0,hh,0,0,1,0,cc,ff,0,1].map(v=>+v.toPrecision(10)).join(',')})`;}
 // Follow-through: a child drags behind its parent's motion on a damped rotational spring about its own anchor
 // (antenna, hair, a hanging tag). The spring chases θ* = -k_v·v - k_a·a (air drag bends it back while moving, inertia
 // on starts/stops; v and a in frame-width-normalised px/frame), ζ from the per-cycle decay, simulated per frame from the
 // layer's start (deterministic in any frame order). Measured: a stiff antenna drags -21° at 26.8 px/frame, overshoots
 // ~0.68x 2-3 frames after the stop with a 5-frame period halving each cycle; a feather keeps dragging ~4 frames, then
 // makes one big swing and settles in ~29 frames.
 const FOLLOW={stiff:{period_frames:5,decay:.5,k_v:.78,k_a:.05,max_deg:35},soft:{period_frames:16,decay:.2,k_v:.9,k_a:.6,max_deg:70}};
 // The simulation state is cached per layer object, so sequential frames cost one step each (was a replay from the
 // layer start every frame, O(n²) over a render); a frame earlier than the cache restarts from the start.
 const FOLLOW_STATE=new WeakMap();
 function followAngle(it,g,byId,W,H){const P={...(FOLLOW[it.follow.preset]||FOLLOW.stiff)};for(const [k,v] of Object.entries(it.follow))if(v!=null)P[k]=v;const p=byId[it.parent],s0=it.start_frame||0,nw=1920/W;
  const px=f=>apply2(worldMatrix(p,f,byId,W,H),pivot(it,W,H));
  const w=2*Math.PI/Math.max(2,P.period_frames),z=-Math.log(clamp(P.decay,.01,.99))/(2*Math.PI),sub=4,dt=1/sub;
  let S=FOLLOW_STATE.get(it);if(!S||S.W!==W||S.p!==p||S.f>g){const p0=px(s0);S={W,p,f:s0,th:0,om:0,p1:p0,v1:0};}
  if(S.f===g){FOLLOW_STATE.set(it,S);return S.th;}
  let {th,om,p1,v1}=S;const dir=P.axis==='y'?1:0,sign=P.invert?-1:1;
  for(let f=S.f+1;f<=g;f++){const p2=px(f),v=(p2[dir]-p1[dir])*nw,acc=v-v1;p1=p2;v1=v;const target=sign*(-P.k_v*v-P.k_a*acc);
   for(let k=0;k<sub;k++){const a=-w*w*(th-target)-2*z*w*om;om+=a*dt;th+=om*dt;}th=clamp(th,-P.max_deg,P.max_deg);}
  FOLLOW_STATE.set(it,{W,p,f:g,th,om,p1,v1});return th;}
 // One call per layer per frame: defs markup to place in the document plus style overrides (transform/mask/filter).
 function composite(it,f,g,ctx){const {byId={},W=1920,H=1080,resolve}=ctx||{},defs=[],style={};
  const pin=it.corner_pin?pinMatrix(it,f,W,H):null;
  if(pin){style.transform=pin;style.transformOrigin='0 0';}
  else if((it.parent&&byId[it.parent])||ikUpper(byId)[it.id]){
   const m=mmul(mT(-it.x*W,-it.y*H),mmul(worldMatrix(it,g,byId,W,H),mT(it.x*W,it.y*H)));style.transform=fmtM(m);style.transformOrigin='0 0';}
  else if(it.anchor)style.transformOrigin=`${it.anchor[0]*100}% ${it.anchor[1]*100}%`;
  const ms=maskDefs(it,f,W,H),mt=it.matte?matteDefs(it,f,g,byId,W,H,resolve):null,urls=[];
  if(ms){defs.push(ms.defs);urls.push(`url(#${ms.id})`);}if(mt){defs.push(mt.defs);urls.push(`url(#${mt.id})`);}
  if(urls.length){style.maskImage=style.WebkitMaskImage=urls.join(',');if(urls.length>1){style.maskComposite='intersect';style.WebkitMaskComposite='source-in';}}
  // _keyFilter carries every SVG filter (key first, then pixel effects); engines prepend it to the CSS filter chain.
  const ky=keyDefs(it),fx=fxDefs(it,f),sf=[];if(ky){defs.push(ky.defs);sf.push(`url(#${ky.id})`);}defs.push(...fx.defs);sf.push(...fx.urls);if(sf.length)style._keyFilter=sf.join(' ');
  return {defs:defs.length?`<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true"><defs>${defs.join('')}</defs></svg>`:'',style};}
 // Stepped time for animation on twos/threes: hold each pose for n frames, counted from the layer's own start.
 const blendCss=b=>!b||b==='normal'?'normal':b==='add'?'plus-lighter':String(b).replace('_','-');
 const stepFrame=(item,f,design)=>{const n=(item?.step_frames>1?item.step_frames:design?.step_frames)||1;return n>1?f-(((f%n)+n)%n):f;};
 return {defaults,styleAt,transitionStyle,transitionOutStyle,widget,textAt,progress,track,esc,random,texture,filterDefs,stepFrame,composite,blendCss,worldMatrix,trackAt,pixelFilters,withPixel};
});
