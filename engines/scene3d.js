/* Actual perspective geometry/material/lighting shared across both renderers. */
import * as THREE from 'three';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {DRACOLoader} from 'three/addons/loaders/DRACOLoader.js';
import {clone as cloneSkinned} from 'three/addons/utils/SkeletonUtils.js';
const vec=p=>new THREE.Vector3(p?.x||0,p?.y||0,p?.z||0);
const smooth=p=>p*p*(3-2*p);
function blend(a,b,p){return {x:a.x+(b.x-a.x)*p,y:a.y+(b.y-a.y)*p,z:a.z+(b.z-a.z)*p};}
function sample(keys,f,base,linear){if(!keys?.length)return base;if(f<=keys[0].frame)return keys[0];for(let i=1;i<keys.length;i++){if(f<=keys[i].frame){const a=keys[i-1],b=keys[i],u=(f-a.frame)/(b.frame-a.frame),p=linear?u:smooth(u);return {position:blend(a.position,b.position,p),...(a.target?{target:blend(a.target,b.target,p)}:{rotation:blend(a.rotation,b.rotation,p),scale:a.scale+(b.scale-a.scale)*p,opacity:a.opacity+(b.opacity-a.opacity)*p})};}}return keys[keys.length-1];}

// Asset IDs referenced by a scene: image textures (color/bump/emissive/equirect) and binary glTF models.
const TEXTURE_FIELDS=['texture','bump_texture','emissive_texture','alpha_texture','displacement_texture'];
export function sceneAssetIds(data){const ids=new Set();for(const o of data.objects||[]){for(const k of TEXTURE_FIELDS)if(o[k])ids.add(o[k]);if(o.model)ids.add(o.model);}
 for(const k of ['background_texture','environment_texture'])if(data[k])ids.add(data[k]);return [...ids];}
// Load everything before the first frame. url(assetId) maps to the engine's local public path.
// dracoPath: local folder holding three's gltf Draco decoder (copied into public/draco/ on export).
// frameSize: the composition's long edge. Textures are fitted to texture_max (default 2x the long edge): an equirect
// sphere filling the frame samples ~1 texel per pixel at that size, so larger maps only cost GPU memory
// (an 8K map per tab per scene exhausted Chrome's GPU process on a 6-tab render).
export function fitTexture(t,cap){const img=t.image,w=img?.width||0,h=img?.height||0,s=Math.min(1,cap/Math.max(w,h,1));if(s>=1)return t;
 const c=document.createElement('canvas');c.width=Math.max(1,Math.round(w*s));c.height=Math.max(1,Math.round(h*s));const g=c.getContext('2d');g.imageSmoothingEnabled=true;g.imageSmoothingQuality='high';g.drawImage(img,0,0,c.width,c.height);
 t.image=c;t.needsUpdate=true;return t;}
export async function loadSceneAssets(data,url,dracoPath,frameSize=1920){
 const cap=Math.max(512,Math.round(data.texture_max||2*frameSize));
 const textures=new Map(),models=new Map(),loader=new THREE.TextureLoader(),gltf=new GLTFLoader();
 let draco=null;if(dracoPath&&(data.objects||[]).some(o=>o.model)){draco=new DRACOLoader();draco.setDecoderPath(dracoPath);draco.setDecoderConfig({type:'wasm'});gltf.setDRACOLoader(draco);}
 const colorIds=new Set([...(data.objects||[]).flatMap(o=>[o.texture,o.emissive_texture].filter(Boolean)),data.background_texture,data.environment_texture].filter(Boolean));
 await Promise.all(sceneAssetIds(data).map(async id=>{
  const isModel=(data.objects||[]).some(o=>o.model===id);
  if(isModel){models.set(id,await gltf.loadAsync(url(id)));return;}
  const t=fitTexture(await loader.loadAsync(url(id)),cap);t.colorSpace=colorIds.has(id)?THREE.SRGBColorSpace:THREE.NoColorSpace;t.anisotropy=8;textures.set(id,t);
 }));
 draco?.dispose();
 return {textures,models};
}
function geometryFor(o){const [x,y,z]=o.size,seg=o.segments||1;if(o.geometry==='tube'){const curve=new THREE.CatmullRomCurve3(o.path.map(p=>new THREE.Vector3(p[0],p[1],p[2])));const g=new THREE.TubeGeometry(curve,Math.max(64,o.path.length*12),o.tube_radius??.02,12,false);g.userData.curve=curve;return g;}
 if(o.geometry==='plane'&&seg>1)return new THREE.PlaneGeometry(x,y,seg,seg);return o.geometry==='sphere'?new THREE.SphereGeometry(x/2,Math.max(96,seg),Math.max(64,seg>>1)):o.geometry==='torus'?new THREE.TorusGeometry(x,y,16,64):o.geometry==='cylinder'?new THREE.CylinderGeometry(x/2,z/2,y,48):o.geometry==='cone'?new THREE.ConeGeometry(x/2,y,48):o.geometry==='plane'?new THREE.PlaneGeometry(x,y):o.geometry==='icosahedron'?new THREE.IcosahedronGeometry(x,o.detail??1):o.geometry==='octahedron'?new THREE.OctahedronGeometry(x,o.detail??0):o.geometry==='dodecahedron'?new THREE.DodecahedronGeometry(x,o.detail??0):o.geometry==='torus_knot'?new THREE.TorusKnotGeometry(x,y,220,32):o.geometry==='capsule'?new THREE.CapsuleGeometry(x/2,y,12,32):new THREE.BoxGeometry(x,y,z);}
function textured(assets,id,repeat){const t=id&&assets?.textures.get(id);if(!t)return null;if(repeat&&(repeat[0]!==1||repeat[1]!==1)){const c=t.clone();c.wrapS=c.wrapT=THREE.RepeatWrapping;c.repeat.set(repeat[0],repeat[1]);c.needsUpdate=true;return c;}return t;}
export function createWorld(data,assets=null){
 const scene=new THREE.Scene(),group=new THREE.Group();scene.add(group);if(!data.transparent)scene.background=new THREE.Color(data.background);
 const meshes=new Map(),mixers=[],curves=new Map();
 if(data.fog)scene.fog=new THREE.Fog(data.fog.color,data.fog.near,data.fog.far);
 // Partial pose keys inherit the object's base position/rotation/scale instead of resetting to origin.
 data={...data,objects:data.objects.map(o=>({...o,fades:(o.keyframes||[]).some(k=>k.opacity!=null),keyframes:(o.keyframes||[]).map(k=>({frame:k.frame,position:k.position??o.position,rotation:k.rotation??o.rotation,scale:k.scale??o.scale,opacity:k.opacity??o.opacity??1}))}))};
 for(const o of data.objects){
  let node;
  if(o.model&&assets?.models.get(o.model)){
   const g=assets.models.get(o.model);node=new THREE.Group();const inner=cloneSkinned(g.scene);
   // Fit the model's largest dimension to size[0] and center it on its own origin.
   const box=new THREE.Box3().setFromObject(inner),dims=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
   const fit=o.size[0]/Math.max(dims.x,dims.y,dims.z,1e-6);inner.scale.setScalar(fit);inner.position.copy(center.multiplyScalar(-fit));
   inner.traverse(c=>{if(c.isMesh){c.castShadow=true;c.receiveShadow=true;if(o.texture_tint&&c.material){c.material=c.material.clone();c.material.color?.set(o.color);}}});
   node.add(inner);
   const clip=o.animation?g.animations.find(a=>a.name===o.animation):null;
   if(clip){const mixer=new THREE.AnimationMixer(inner);mixer.clipAction(clip).play();mixers.push({mixer,speed:o.animation_speed??1,offset:o.animation_offset??0});}
  } else {
   const repeat=o.texture_repeat||[1,1];
   const base={color:o.texture&&!o.texture_tint?'#ffffff':o.color,roughness:o.roughness,metalness:o.metalness,transparent:o.opacity<1||!!o.alpha_texture,opacity:o.opacity,wireframe:o.wireframe,side:THREE.DoubleSide,emissive:o.emissive||'#000000',emissiveIntensity:o.emissive_intensity||0,
    map:textured(assets,o.texture,repeat),bumpMap:textured(assets,o.bump_texture,repeat),bumpScale:o.bump_scale??1,displacementMap:textured(assets,o.displacement_texture,repeat),displacementScale:o.displacement_scale??1,displacementBias:o.displacement_bias??0,emissiveMap:textured(assets,o.emissive_texture,repeat),alphaMap:textured(assets,o.alpha_texture,repeat),depthWrite:!(o.alpha_texture)};
   const material=(o.transmission||o.clearcoat)?new THREE.MeshPhysicalMaterial({...base,transmission:o.transmission||0,thickness:.6,ior:1.45,clearcoat:o.clearcoat||0,clearcoatRoughness:.08}):new THREE.MeshStandardMaterial(base);
   node=new THREE.Mesh(geometryFor(o),material);node.castShadow=true;node.receiveShadow=true;if(node.geometry.userData.curve)curves.set(o.id,node.geometry.userData.curve);
  }
  group.add(node);meshes.set(o.id,node);
 }
 const lights=[];
 for(const l of data.lights){const light=l.kind==='ambient'?new THREE.AmbientLight(l.color,l.intensity):l.kind==='point'?new THREE.PointLight(l.color,l.intensity,100):l.kind==='spot'?new THREE.SpotLight(l.color,l.intensity,100,(l.angle??25)*Math.PI/180,l.penumbra??.5,1.2):new THREE.DirectionalLight(l.color,l.intensity);light.position.copy(vec(l.position));
  if(l.kind==='spot'){light.target.position.copy(vec(l.target||{x:0,y:0,z:0}));scene.add(light.target);light.castShadow=data.shadows;light.shadow.mapSize.set(1024,1024);light.shadow.bias=-.0002;}
  if(l.kind==='directional'){light.castShadow=data.shadows;light.shadow.mapSize.set(1024,1024);light.shadow.camera.left=-6;light.shadow.camera.right=6;light.shadow.camera.top=6;light.shadow.camera.bottom=-6;light.shadow.bias=-.0002;}scene.add(light);lights.push({light,data:l});}
 if(data.ground){const plane=new THREE.Mesh(new THREE.PlaneGeometry(30,30),new THREE.MeshStandardMaterial({color:data.background,roughness:.95}));plane.rotation.x=-Math.PI/2;plane.position.y=-1.15;plane.receiveShadow=true;scene.add(plane);}
 const bg=data.background_texture&&assets?.textures.get(data.background_texture);
 if(bg&&!data.transparent){bg.mapping=THREE.EquirectangularReflectionMapping;scene.background=bg;scene.backgroundIntensity=data.background_intensity??1;}
 const camera=new THREE.PerspectiveCamera(data.fov,1,.05,400);
 return {scene,group,meshes,camera,data,assets,mixers,curves,lights};
}
export function drawPose(world,frame,aspect){const d=world.data,c=sample(d.camera_keyframes,frame,{position:d.camera_position,target:d.camera_target},d.camera_ease==='linear');world.camera.position.copy(vec(c.position));world.camera.lookAt(vec(c.target));world.camera.aspect=aspect;world.camera.updateProjectionMatrix();
 const prog=r=>r?smooth(Math.min(1,Math.max(0,(frame-r[0])/Math.max(1,r[1]-r[0])))):1;
 // Light keys: position/intensity eased between keys (a highlight sweeping across a product), frame-addressed.
 for(const {light,data:l} of world.lights||[]){if(!l.keyframes?.length)continue;const ks=l.keyframes;let a=ks[0],b=ks[0],u=0;
  if(frame>=ks[ks.length-1].frame){a=b=ks[ks.length-1];}else if(frame>ks[0].frame){for(let i=1;i<ks.length;i++)if(frame<=ks[i].frame){a=ks[i-1];b=ks[i];u=smooth((frame-a.frame)/(b.frame-a.frame));break;}}
  const pa=a.position||l.position,pb=b.position||l.position;light.position.copy(vec(blend(pa,pb,u)));const ia=a.intensity??l.intensity,ib=b.intensity??l.intensity;light.intensity=ia+(ib-ia)*u;}
 for(const o of d.objects){const pose=sample(o.keyframes,frame,o,o.ease==='linear'),mesh=world.meshes.get(o.id);mesh.position.copy(vec(pose.position));mesh.rotation.set(pose.rotation.x,pose.rotation.y,pose.rotation.z);mesh.scale.setScalar(pose.scale);
  if(o.spin){const sp=o.spin,t=(Math.min(frame,sp.end_frame??frame)-(sp.start_frame||0))/30;if(t>0)mesh.rotation[sp.axis||'y']+=(sp.deg_per_s*Math.PI/180)*t;}
  // Opacity keys fade the whole object (all materials), hidden entirely at zero so it never writes depth.
  if(o.fades){const a=pose.opacity??1;mesh.visible=a>.003;mesh.traverse(n=>{if(n.material)(Array.isArray(n.material)?n.material:[n.material]).forEach(m=>{m.transparent=true;m.opacity=a;});});}
  // Tubes grow along their length by draw range (whole radial rings), deterministic per frame.
  if(o.grow&&mesh.geometry?.index){const ring=12*6,total=mesh.geometry.index.count;mesh.geometry.setDrawRange(0,Math.floor(total*prog(o.grow)/ring)*ring);}
  if(o.follow&&world.curves.get(o.follow)){const c=world.curves.get(o.follow),t=Math.min(.9999,prog(o.follow_range)),pos=c.getPointAt(t);mesh.position.copy(pos);if(o.follow_orient!==false){mesh.lookAt(pos.clone().add(c.getTangentAt(t)));}}}
 // glTF clips are sampled at absolute layer time, never advanced by wall-clock deltas.
 for(const m of world.mixers||[])m.mixer.setTime(Math.max(0,m.offset+frame/30*m.speed));
 world.scene.updateMatrixWorld(true);world.camera.updateMatrixWorld(true);
}
export function disposeSceneAssets(assets){assets?.textures?.forEach(t=>t.dispose());}
export function destroyWorld(world){world.composer?.dispose();world.envTexture?.dispose();world.scene.traverse(o=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());});}
// Renderer-dependent setup shared by ThreeCanvas and HTML: reflections (studio or equirect image) and bloom post.
// target is the scene the renderer actually draws (ThreeCanvas wraps world.scene in its own root scene).
export function prepareRenderer(world,renderer,width,height,target=world.scene){const d=world.data;world.renderScene=target;
 if(target!==world.scene){target.fog=world.scene.fog;target.background=world.scene.background;target.backgroundIntensity=world.scene.backgroundIntensity??1;}
 const envImage=d.environment_texture&&world.assets?.textures.get(d.environment_texture);
 if(!world.envTexture&&(envImage||d.environment==='studio')){const pmrem=new THREE.PMREMGenerator(renderer);
  if(envImage){envImage.mapping=THREE.EquirectangularReflectionMapping;world.envTexture=pmrem.fromEquirectangular(envImage).texture;}
  else world.envTexture=pmrem.fromScene(new RoomEnvironment(),.04).texture;pmrem.dispose();}
 if(world.envTexture){target.environment=world.envTexture;target.environmentIntensity=d.environment_intensity??1;}
 if(d.bloom&&!world.composer){const composer=new EffectComposer(renderer);composer.setSize(width,height);composer.addPass(new RenderPass(target,world.camera));composer.addPass(new UnrealBloomPass(new THREE.Vector2(width,height),d.bloom.strength,d.bloom.radius,d.bloom.threshold));composer.addPass(new OutputPass());world.composer=composer;}
 return world;}
export function renderWorld(world,renderer){if(world.composer)world.composer.render();else renderer.render(world.renderScene||world.scene,world.camera);}
export function projectLabels(world,width,height){return world.data.objects.filter(o=>o.label).map(o=>{
 const mesh=world.meshes.get(o.id),box=new THREE.Box3().setFromObject(mesh),center=box.getCenter(new THREE.Vector3()).project(world.camera),bottom=new THREE.Vector3((box.min.x+box.max.x)/2,box.min.y,(box.min.z+box.max.z)/2).project(world.camera);
 let facing=true;if(o.label_facing){const wp=new THREE.Vector3().setFromMatrixPosition(mesh.matrixWorld),n=wp.clone().sub(vec(o.label_facing)),v=world.camera.position.clone().sub(wp);facing=n.dot(v)>0;}
 const alpha=mesh.visible?Math.min(1,Math.max(0,(mesh.scale.x/(o.scale||1)-.3)/.6)):0;
 return {id:o.id,text:o.label,alpha,x:(center.x+1)*width/2,y:Math.min(height-world.data.label_font_size*1.5,(1-bottom.y)*height/2+8),visible:alpha>.01&&facing&&center.z>-1&&center.z<1&&Math.abs(center.x)<1};
});}
export function createRenderer(canvas){const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,preserveDrawingBuffer:true});renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;return renderer;}
export {THREE};
