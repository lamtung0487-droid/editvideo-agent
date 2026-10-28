"""Typed deterministic 3D scenes shared by ThreeCanvas and HTML WebGL."""
import copy
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Point3(BaseModel):
 model_config=ConfigDict(extra='forbid')
 x:float=Field(default=0,ge=-100,le=100,allow_inf_nan=False)
 y:float=Field(default=0,ge=-100,le=100,allow_inf_nan=False)
 z:float=Field(default=0,ge=-100,le=100,allow_inf_nan=False)
class Pose(BaseModel):
 """Frame pose. Omitted position/rotation/scale inherit the object's base values (no silent reset to origin)."""
 model_config=ConfigDict(extra='forbid')
 frame:int=Field(ge=0)
 position:Point3|None=None
 rotation:Point3|None=None
 scale:float|None=Field(default=None,ge=.01,le=20,allow_inf_nan=False)
 opacity:float|None=Field(default=None,ge=0,le=1,allow_inf_nan=False)
class Spin(BaseModel):
 model_config=ConfigDict(extra='forbid')
 axis:Literal['x','y','z']='y'
 deg_per_s:float=Field(default=45,ge=-1440,le=1440,allow_inf_nan=False)
 start_frame:int=Field(default=0,ge=0)
 end_frame:int|None=Field(default=None,ge=1)
class Object3D(BaseModel):
 model_config=ConfigDict(extra='forbid')
 id:str=Field(min_length=1,max_length=70)
 geometry:Literal['box','sphere','torus','cylinder','cone','plane','icosahedron','torus_knot','capsule','octahedron','dodecahedron','tube']='box'
 # tube: smooth CatmullRom curve through path points; grow [start,end] reveals it along its length.
 path:list[list[float]]|None=Field(default=None,max_length=512)
 tube_radius:float=Field(default=.02,ge=.001,le=2,allow_inf_nan=False)
 grow:list[int]|None=None
 # follow: ride along another tube object's curve over follow_range frames (optionally facing the tangent).
 follow:str|None=Field(default=None,max_length=70)
 follow_range:list[int]|None=None
 follow_orient:bool=True
 segments:int=Field(default=1,ge=1,le=512)
 displacement_texture:str|None=Field(default=None,max_length=100)
 displacement_scale:float=Field(default=1,ge=-20,le=20,allow_inf_nan=False)
 displacement_bias:float=Field(default=0,ge=-20,le=20,allow_inf_nan=False)
 # Hide this object's label while it faces away from the camera relative to a center (e.g. far side of a globe).
 label_facing:Point3|None=None
 detail:int=Field(default=1,ge=0,le=5)
 color:str=Field(default='#81e6be',pattern=r'^#[0-9a-fA-F]{6}$')
 position:Point3=Field(default_factory=Point3)
 rotation:Point3=Field(default_factory=Point3)
 scale:float=Field(default=1,ge=.01,le=20,allow_inf_nan=False)
 size:list[float]=Field(default_factory=lambda:[1,1,1],min_length=3,max_length=3)
 roughness:float=Field(default=.45,ge=.02,le=1,allow_inf_nan=False)
 metalness:float=Field(default=.15,ge=0,le=1,allow_inf_nan=False)
 opacity:float=Field(default=1,ge=.05,le=1,allow_inf_nan=False)
 wireframe:bool=False
 emissive:str=Field(default='#000000',pattern=r'^#[0-9a-fA-F]{6}$')
 emissive_intensity:float=Field(default=0,ge=0,le=20,allow_inf_nan=False)
 transmission:float=Field(default=0,ge=0,le=1,allow_inf_nan=False)
 clearcoat:float=Field(default=0,ge=0,le=1,allow_inf_nan=False)
 # Project asset IDs. Image textures map onto the primitive UVs (sphere = equirectangular).
 texture:str|None=Field(default=None,max_length=100)
 bump_texture:str|None=Field(default=None,max_length=100)
 bump_scale:float=Field(default=1,ge=0,le=20,allow_inf_nan=False)
 emissive_texture:str|None=Field(default=None,max_length=100)
 alpha_texture:str|None=Field(default=None,max_length=100)
 texture_repeat:list[float]=Field(default_factory=lambda:[1,1],min_length=2,max_length=2)
 texture_tint:bool=False
 # Binary glTF (.glb) asset replaces the primitive; size[0] is the fitted largest dimension.
 model:str|None=Field(default=None,max_length=100)
 animation:str|None=Field(default=None,max_length=120)
 animation_speed:float=Field(default=1,ge=-8,le=8,allow_inf_nan=False)
 animation_offset:float=Field(default=0,ge=0,le=3600,allow_inf_nan=False)
 label:str=Field(default='',max_length=80)
 keyframes:list[Pose]=Field(default_factory=list,max_length=100)
 # smooth: ease between each pair of pose keys; linear: constant speed (dense keys, loops, turntables).
 ease:Literal['smooth','linear']='smooth'
 # Constant-speed turn added on top of the pose (turntable), deterministic per frame.
 spin:Spin|None=None
 @model_validator(mode='after')
 def bounds(self):
  import math
  if any(not math.isfinite(v) or not .0005<=v<=20 for v in self.size):raise ValueError('3D size components.0005..20')
  if self.geometry=='tube' and (not self.path or len(self.path)<2 or any(len(p)!=3 or any(not math.isfinite(v) or abs(v)>100 for v in p) for p in self.path)):raise ValueError(f'{self.id}: tube needs >=2 [x,y,z] path points within +-100')
  for name in ('grow','follow_range'):
   r=getattr(self,name)
   if r is not None and (len(r)!=2 or not 0<=r[0]<r[1]):raise ValueError(f'{self.id}: {name} needs [start,end] frames')
  if self.follow and not self.follow_range:raise ValueError(f'{self.id}: follow needs follow_range')
  if any(a.frame>=b.frame for a,b in zip(self.keyframes,self.keyframes[1:])):raise ValueError('3D pose keyframes increasing')
  return self
class CameraPose(BaseModel):
 model_config=ConfigDict(extra='forbid')
 frame:int=Field(ge=0)
 position:Point3=Field(default_factory=lambda:Point3(x=4,y=2.5,z=7))
 target:Point3=Field(default_factory=Point3)
class LightKey(BaseModel):
 model_config=ConfigDict(extra='forbid')
 frame:int=Field(ge=0)
 position:Point3|None=None
 intensity:float|None=Field(default=None,ge=0,le=40,allow_inf_nan=False)
class Light3D(BaseModel):
 model_config=ConfigDict(extra='forbid')
 kind:Literal['ambient','directional','point','spot']='directional'
 position:Point3=Field(default_factory=lambda:Point3(x=4,y=6,z=5))
 color:str=Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
 intensity:float=Field(default=3,ge=0,le=40,allow_inf_nan=False)
 # spot: aimed at target with a cone (angle degrees) and soft edge (penumbra 0..1): product light sweeps, key lights.
 target:Point3=Field(default_factory=Point3)
 angle:float=Field(default=25,gt=1,le=89,allow_inf_nan=False)
 penumbra:float=Field(default=.5,ge=0,le=1,allow_inf_nan=False)
 # Frame-addressed light moves (position/intensity), eased like object poses: a highlight sweeping across a product.
 keyframes:list[LightKey]=Field(default_factory=list,max_length=60)
 @model_validator(mode='after')
 def keys(self):
  if any(a.frame>=b.frame for a,b in zip(self.keyframes,self.keyframes[1:])):raise ValueError('Light keyframes increasing')
  return self
class Bloom(BaseModel):
 model_config=ConfigDict(extra='forbid')
 strength:float=Field(default=.8,ge=0,le=3,allow_inf_nan=False)
 radius:float=Field(default=.4,ge=0,le=1,allow_inf_nan=False)
 threshold:float=Field(default=.75,ge=0,le=1,allow_inf_nan=False)
class Fog(BaseModel):
 model_config=ConfigDict(extra='forbid')
 color:str=Field(default='#0a1a33',pattern=r'^#[0-9a-fA-F]{6}$')
 near:float=Field(default=6,ge=0,le=200,allow_inf_nan=False)
 far:float=Field(default=20,gt=0,le=400,allow_inf_nan=False)
class Scene3D(BaseModel):
 model_config=ConfigDict(extra='forbid')
 objects:list[Object3D]=Field(default_factory=list,max_length=160,min_length=1)
 lights:list[Light3D]=Field(default_factory=lambda:[Light3D(),Light3D(kind='ambient',intensity=.6)],max_length=8,min_length=1)
 camera_position:Point3=Field(default_factory=lambda:Point3(x=4,y=2.5,z=7))
 camera_target:Point3=Field(default_factory=Point3)
 camera_keyframes:list[CameraPose]=Field(default_factory=list,max_length=100)
 # smooth: ease in/out between each pair of keys (few authored keys). linear: constant speed through dense pre-eased keys.
 camera_ease:Literal['smooth','linear']='smooth'
 fov:float=Field(default=40,ge=15,le=90,allow_inf_nan=False)
 background:str=Field(default='#102322',pattern=r'^#[0-9a-fA-F]{6}$')
 transparent:bool=False
 ground:bool=True
 shadows:bool=True
 label_font_size:int=Field(default=32,ge=16,le=96)
 label_color:str=Field(default='#f2f7ef',pattern=r'^#[0-9a-fA-F]{6}$')
 environment:Literal['none','studio']='none'
 environment_texture:str|None=Field(default=None,max_length=100)
 background_texture:str|None=Field(default=None,max_length=100)
 texture_max:int|None=Field(default=None,ge=512,le=16384)  # px cap for image textures; default 2x the frame's long edge
 background_intensity:float=Field(default=1,ge=0,le=4,allow_inf_nan=False)
 environment_intensity:float=Field(default=1,ge=0,le=3,allow_inf_nan=False)
 bloom:Bloom|None=None
 fog:Fog|None=None
 @model_validator(mode='after')
 def ordered(self):
  if len({o.id for o in self.objects})!=len(self.objects):raise ValueError('3D object IDs unique')
  if any(a.frame>=b.frame for a,b in zip(self.camera_keyframes,self.camera_keyframes[1:])):raise ValueError('Camera keyframes increasing')
  if self.fog and self.fog.near>=self.fog.far:raise ValueError('Fog near must be closer than far')
  tubes={o.id for o in self.objects if o.geometry=='tube'}
  for o in self.objects:
   if o.follow and o.follow not in tubes:raise ValueError(f'{o.id}: follow must reference a tube object')
  return self

PRESETS={
 'depth_layers':{'intent':'Illustrate near/mid/far planes with actual perspective','objects':[
  {'id':'near','geometry':'box','label':'GẦN','position':{'x':-1.4,'y':0,'z':1.4},'size':[1.3,1.8,.22],'color':'#81e6be'},
  {'id':'middle','geometry':'box','label':'GIỮA','position':{'x':0,'y':0,'z':0},'size':[1.3,1.8,.22],'color':'#e4b866'},
  {'id':'far','geometry':'box','label':'XA','position':{'x':1.4,'y':0,'z':-1.4},'size':[1.3,1.8,.22],'color':'#8abdda'}]},
 'material_study':{'intent':'Compare authored surface/materials under shared lighting','objects':[
  {'id':'matte','geometry':'sphere','position':{'x':-1.6},'roughness':.85,'metalness':0},
  {'id':'metal','geometry':'sphere','position':{'x':1.6},'roughness':.22,'metalness':.8,'color':'#e4b866'}]},
 'mechanism':{'intent':'A stylized mechanical graphic, not an engineering simulation','objects':[
  {'id':'ring','geometry':'torus','size':[1.6,.2,1],'color':'#81e6be'},
  {'id':'core','geometry':'icosahedron','size':[.65,.65,.65],'color':'#e4b866'}]},
 'product_pedestal':{'intent':'An abstract product placeholder on a lit pedestal','objects':[
  {'id':'pedestal','geometry':'cylinder','size':[1.5,.3,1.5],'position':{'y':-.8},'color':'#354c52'},
  {'id':'hero','geometry':'box','size':[1,1.3,.5],'position':{'y':.1},'color':'#e4b866'}]}}
def catalog():return {'presets':[{'id':k,**v} for k,v in PRESETS.items()],'geometries':['box','sphere','torus','cylinder','cone','plane','icosahedron','torus_knot','capsule','octahedron','dodecahedron'],'camera':'Perspective fov15..90, frame-addressed position/target keys','lighting':'Ambient/directional/point, standard or physical material (roughness/metalness, emissive, transmission glass, clearcoat), ground/shadow; environment=studio adds procedural RoomEnvironment reflections','post':'bloom {strength,radius,threshold} glows emissive/bright pixels; fog {color,near,far} fades distance. Pose keys may give only rotation or position; the rest inherits the object base.','assets':'Object texture/bump_texture/emissive_texture/alpha_texture take image asset IDs (sphere UV = equirectangular map); model takes a .glb asset ID (fitted to size[0], optional animation clip sampled at frame time); scene background_texture/environment_texture take equirectangular images.','units':'Authored arbitrary3D units and rotation radians; not calibrated source depth/meters. glTF meshes/materials/skinned clips load from local .glb assets; no motion blur or depth-to-mesh reconstruction.'}
def compose(pid,base_revision,request):
 from . import agent
 from .models import Layer
 allowed={'id','preset','scene','start_frame','end_frame','x','y','width','height','z'}
 if set(request)-allowed:raise ValueError('Unknown3D composition fields')
 p=agent.read(pid);scene=request.get('scene')
 if scene is None:
  preset=request.get('preset','depth_layers')
  if preset not in PRESETS:raise ValueError('Unknown3D preset')
  scene={'objects':copy.deepcopy(PRESETS[preset]['objects'])}
 scene=Scene3D.model_validate(scene).model_dump();start=request.get('start_frame',0);end=request['end_frame'];d=end-start
 if d<=0:raise ValueError('3D layer range invalid')
 if not scene['camera_keyframes']:
  scene['camera_keyframes']=[{'frame':0,'position':{'x':3.8,'y':2,'z':7},'target':{'x':0,'y':0,'z':0}}, {'frame':d-1,'position':{'x':-1.2,'y':1.6,'z':7.8},'target':{'x':0,'y':0,'z':0}}] if d>1 else []
 layer=Layer.model_validate({'id':request.get('id','scene3d'),'kind':'scene3d','start_frame':start,'end_frame':end,'x':request.get('x',.08),'y':request.get('y',.2),'width':request.get('width',.84),'height':request.get('height',.56),'z':request.get('z',100),'data':scene}).model_dump()
 result=agent.patch(pid,base_revision,[{'op':'upsert_layer','layer':layer}]);return {'revision':result['revision'],'layer':layer,'inspect_frames':[start,start+d//2,end-1],'scope':'Native ThreeCanvas/HTML Three.js geometry with deterministic frame poses; no wall-clock loops or CSS imitation. Read Scene3D schema to author objects/camera/light/materials. Existing custom runtimes need deliberate merge.'}


def product_scene(duration, model=None, primitive='cylinder', texture=None, color='#d8d2c4', size=None, background='#0e0f12', accent='#ffffff',
                  slide_frames=40, rock_deg=5.0, turn_deg_per_s=40.0, sweep=True, push=True, bloom=True, light=1.0, ground=True, studio=True,
                  reveal='slide', reveal_at=None, aspect=16 / 9):
    """Product shot from measured ad practice: slide in (strong ease-out), rock-and-settle on the base (5° → -2° → 0.6° →
    0, 5 frames per step), then a constant-speed turn, a light sweep across the product after it settles (a vertical
    highlight band ≈ 15 % of the product width), and a slow camera push (115 % → 100 %) so no frame is dead."""
    import math
    d = int(duration)
    slide_frames = min(slide_frames, max(10, d - 30))  # short ad beats: a faster slide, same settle
    if d < slide_frames + 30:
        raise ValueError('duration too short for slide + settle (needs >= 40 frames)')
    obj = {'id': 'product', 'geometry': primitive if not model else 'box', 'color': color, 'roughness': .35, 'metalness': .2, 'clearcoat': .6,
           'size': size or ([1.1, 2.0, 1.1] if primitive == 'cylinder' else [1.4, 1.4, 1.4]), 'segments': 64, 'position': {'x': 0, 'y': -.15, 'z': 0}}
    if model:
        obj.update(model=model, size=[size[0] if size else 2.2, 1, 1])
    if texture:
        obj.update(texture=texture)
    r = math.radians(rock_deg)
    settle = slide_frames + 20
    obj['keyframes'] = [
        {'frame': 0, 'position': {'x': -6, 'y': -.15, 'z': 0}, 'rotation': {'x': 0, 'y': -.9, 'z': -r * 1.6}},
        {'frame': slide_frames, 'position': {'x': 0, 'y': -.15, 'z': 0}, 'rotation': {'x': 0, 'y': 0, 'z': r}},
        {'frame': slide_frames + 5, 'rotation': {'x': 0, 'y': 0, 'z': -.4 * r}},
        {'frame': slide_frames + 10, 'rotation': {'x': 0, 'y': 0, 'z': .12 * r}},
        {'frame': slide_frames + 15, 'rotation': {'x': 0, 'y': 0, 'z': 0}},
    ]
    obj['spin'] = {'axis': 'y', 'deg_per_s': turn_deg_per_s, 'start_frame': settle}
    if reveal == 'dark':  # premium reveal: the product waits in the dark, turning slowly (about 2 rpm), no slide
        obj['keyframes'] = [{'frame': 0, 'position': {'x': 0, 'y': -.15, 'z': 0}, 'rotation': {'x': 0, 'y': -.6, 'z': 0}}]
        obj['spin'] = {'axis': 'y', 'deg_per_s': min(turn_deg_per_s, 12.0), 'start_frame': 0}
        settle = 0
    # light scales every source (glTF models with bright/metallic materials need ~0.3-0.5); studio adds reflections.
    lights = [{'kind': 'directional', 'position': {'x': 3, 'y': 5, 'z': 4}, 'intensity': round(2.2 * light, 3)},
              {'kind': 'ambient', 'intensity': round(.35 * light, 3)},
              {'kind': 'point', 'position': {'x': -3, 'y': 2, 'z': -3}, 'intensity': round(6 * light, 3), 'color': '#9fb6ff'}]
    if reveal == 'dark':
        # From black (product-video practice: a rim light builds the silhouette, the key light lands on the beat, then fill):
        # rim up over the first stretch, key + fill at reveal_at, a soft strip light crossing the surface after it. The
        # first frame already shows the rim's edge: a black first frame is skipped in a feed (shortform_audit).
        r = int(reveal_at if reveal_at is not None else min(d - 40, max(45, d // 3)))
        if not 20 <= r <= d - 30:
            raise ValueError('reveal_at must leave >= 20 frames of rim light before it and 30 after it')
        lights = [{'kind': 'spot', 'position': {'x': -3.5, 'y': 2.2, 'z': -4}, 'target': {'x': 0, 'y': .2, 'z': 0}, 'angle': 30, 'penumbra': .8,
                   'intensity': 0, 'color': '#a9c4ff', 'keyframes': [{'frame': 0, 'intensity': round(10 * light, 2)}, {'frame': r - 6, 'intensity': round(28 * light, 2)}]},
                  {'kind': 'spot', 'position': {'x': 3.5, 'y': 2.2, 'z': -4}, 'target': {'x': 0, 'y': .2, 'z': 0}, 'angle': 30, 'penumbra': .8,
                   'intensity': 0, 'color': '#ffe2c4', 'keyframes': [{'frame': 8, 'intensity': 0}, {'frame': r - 2, 'intensity': round(18 * light, 2)}]},
                  {'kind': 'directional', 'position': {'x': 3, 'y': 5, 'z': 4}, 'intensity': 0,
                   'keyframes': [{'frame': r, 'intensity': 0}, {'frame': r + 10, 'intensity': round(2.2 * light, 3)}]},
                  {'kind': 'ambient', 'intensity': 0, 'keyframes': [{'frame': r + 4, 'intensity': 0}, {'frame': r + 24, 'intensity': round(.3 * light, 3)}]},
                  {'kind': 'point', 'position': {'x': -3, 'y': 2, 'z': 3}, 'intensity': 0, 'color': '#ffffff',
                   'keyframes': [{'frame': r + 4, 'intensity': 0}, {'frame': r + 20, 'intensity': round(4 * light, 3)}]}]
        a_sw, b_sw = r + 30, min(d - 5, r + 30 + 50)
        studio, push = False, True  # reflections cannot fade in: the strip light makes the gradient highlight instead
        beats_extra = {'rim': [0, r - 6], 'reveal': r}
    else:
        beats_extra = {}
    a_sw, b_sw = (a_sw, b_sw) if reveal == 'dark' else (settle + 10, min(d - 5, settle + 10 + 45))
    if sweep and b_sw - a_sw >= 20:  # a sweep needs ~20 frames (fade up, cross, fade down); short shots skip it
        a, b = a_sw, b_sw
        lights.append({'kind': 'spot', 'position': {'x': -5, 'y': 2.5, 'z': 3}, 'target': {'x': 0, 'y': .2, 'z': 0}, 'angle': 9, 'penumbra': .35,
                       'intensity': 0, 'color': accent, **({'angle': 14, 'penumbra': .7} if reveal == 'dark' else {}),
                       'keyframes': [{'frame': a, 'position': {'x': -5, 'y': 2.5, 'z': 3}, 'intensity': 0},
                                     {'frame': a + 8, 'intensity': round(30 * light, 2)}, {'frame': b - 8, 'intensity': round(30 * light, 2)},
                                     {'frame': b, 'position': {'x': 5, 'y': 2.5, 'z': 3}, 'intensity': 0}]})
    # Fit the camera to the product through the whole turn: the bounding extent (a model's width stands in for its
    # height and depth; it can be any shape) must stay inside the frame with a margin at the closest camera position.
    sx, sy, sz = obj['size'] if not model else (obj['size'][0],) * 3
    half_h, radius = sy / 2, math.hypot(sx, sz) / 2
    tan = math.tan(math.radians(32 / 2)) * .9  # 10 % margin
    # the layer's own aspect: a 9:16 frame is narrow, so its width decides the distance (a 16:9 fit left the product tiny)
    need = max(6.0 if aspect >= 1 else 0.0, (abs(.1 - (-.15 - half_h)) + .05) / tan, (abs(-.15 + half_h - .1) + .05) / tan, radius * 1.1 / (tan * aspect))
    cam0, cam1 = (need * (1.3 if reveal == 'dark' else 1.15), need) if push else (need, need)
    scene = {'objects': [obj], 'lights': lights, 'background': background, 'ground': ground, 'shadows': True, 'environment': 'studio' if studio else 'none', 'fov': 32,
             'camera_keyframes': [{'frame': 0, 'position': {'x': -1.2 if reveal == 'dark' else 0, 'y': .5 if reveal == 'dark' else .9, 'z': round(cam0, 3)}, 'target': {'x': 0, 'y': .1, 'z': 0}},
                                  {'frame': d - 1, 'position': {'x': .4, 'y': .45 if reveal == 'dark' else .8, 'z': round(cam1, 3)}, 'target': {'x': 0, 'y': .1, 'z': 0}}],
             'camera_ease': 'linear'}
    if bloom:
        scene['bloom'] = {'strength': .35, 'radius': .4, 'threshold': .85}
    if reveal == 'dark':  # the floor falls off into the dark behind the product (no horizon line in a tall frame); fog is
        # measured from the camera, so it starts past the product's far side at the farthest camera (it had dimmed the
        # product itself by half on the first frames, rim light included)
        scene['fog'] = {'color': background, 'near': round(cam0 + radius, 2), 'far': round(cam0 + radius + cam1 * .8, 2)}
    beats = {**({'slide_in': [0, slide_frames], 'rock_settle': [slide_frames, slide_frames + 15]} if reveal != 'dark' else beats_extra),
             'turn_from': settle, 'camera_distance': round(cam1, 2), 'light_sweep': [a_sw, b_sw] if sweep and b_sw - a_sw >= 20 else None}
    return Scene3D.model_validate(scene).model_dump(), beats
