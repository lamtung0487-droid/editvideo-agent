import asyncio,json,os,subprocess,sys
from pathlib import Path
import numpy as np,cv2,pytest
from PIL import Image
from editvideo import agent,store,media_tasks,color_pipeline as cp,depth,scene3d
from editvideo.media import FFMPEG,command,probe
from editvideo.models import Layer
from test_pipeline import workspace
from test_agent import planned

def test_hdr_transfer_precision_and_declared_range(workspace):
 w,h=64,32;plane=np.repeat(np.array([.2,1,4,10],np.float32),w//4)[None,:].repeat(h,axis=0)
 raw=workspace/'radiance.bin';raw.write_bytes(np.stack([plane]*3).astype('<f4').tobytes());source=workspace/'native.mp4'
 command([FFMPEG,'-y','-v','error','-f','rawvideo','-pix_fmt','gbrpf32le','-s',f'{w}x{h}','-r','30','-i',raw,'-vf','loop=loop=5:size=1:start=0,zscale=pin=bt2020:tin=linear:min=gbr:rin=full:p=bt2020:t=smpte2084:m=bt2020nc:r=limited:npl=100,format=yuv420p10le','-frames:v','6','-c:v','libx265','-x265-params','pools=1:frame-threads=1','-pix_fmt','yuv420p10le','-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv',source])
 for mode,exposure in [('hdr10',1),('sdr',0)]:
  task=media_tasks.submit('color',{'path':str(source),'output':mode,'exposure':exposure},launch=False);media_tasks.run(task['id']);r=media_tasks.get(task['id']);assert r['state']=='completed',r['error']
  output=r['result']['video'];report=cp.inspect(output,timestamps=[.05]);maximum=report['scopes'][0]['linear_luma_reference_nits_percentiles']['99']
  if mode=='hdr10':assert 1800<maximum<2200 and r['result']['report']['actual_stream']['pix_fmt']=='yuv420p10le'
  else:assert 95<maximum<115
 with pytest.raises(ValueError):cp.input_color(cp.ColorRequest(path='x'),{'pix_fmt':'yuv420p'})
 with pytest.raises(ValueError):cp.ColorRequest(path='x',output='hdr10',lut_id='documentary')
 # No silent clip at100nits during a resized float scope.
 assert 900<cp.inspect(source,timestamps=[.05])['scopes'][0]['linear_luma_reference_nits_percentiles']['99']<1100

def test_cube_identity_validation_and_scene3d_frame_contract(workspace,tmp_path):
 if not (store.ROOT/"engines/node_modules/three").exists():pytest.skip("engine packages not installed (run setup: npm ci in engines/)")
 for spec in cp.catalog()['luts']:size,values=cp.read_cube(cp.LUT_ROOT/spec['file']);assert len(values)==size**3
 bad=tmp_path/'bad.cube';bad.write_text('LUT_3D_SIZE 2\n0 0 nan\n')
 with pytest.raises(ValueError):cp.read_cube(bad)
 pid=planned();p=agent.read(pid);voice=(store.folder(pid)/'plan/voice.wav').read_bytes()
 r=scene3d.compose(pid,p['revision'],{'end_frame':60,'preset':'depth_layers'});assert r['layer']['data']['objects'][0]['geometry']=='box'
 assert (store.folder(pid)/'plan/voice.wav').read_bytes()==voice
 with pytest.raises(ValueError):scene3d.compose(pid,r['revision'],{'end_frame':60,'scene':{'objects':[{'id':'x','keyframes':[{'frame':60}]}]}})
 with pytest.raises(ValueError):Layer(id='x',kind='scene3d',start_frame=0,end_frame=60,data={'objects':[{'id':'a','roughness':2}]})
 # Frame sample can seek backward/forward without accumulating pose.
 script="""import {createWorld,drawPose,destroyWorld} from './scene3d.js';const data=JSON.parse(process.argv[1]);const w=createWorld(data);drawPose(w,15,1.7);const a=w.camera.position.toArray();drawPose(w,2,1.7);drawPose(w,15,1.7);console.log(JSON.stringify({same:JSON.stringify(a)===JSON.stringify(w.camera.position.toArray()),geometry:w.meshes.get('near').geometry.type,material:w.meshes.get('near').material.type}));destroyWorld(w);"""
 out=json.loads(subprocess.check_output(['node','--input-type=module','-e',script,json.dumps(r['layer']['data'])],cwd=store.ROOT/'engines',text=True));assert out['same'] and out['geometry']=='BoxGeometry' and out['material']=='MeshStandardMaterial'

def test_temporal_depth_flow_reliability_and_no_download():
 rng=np.random.default_rng(7);gray=rng.integers(20,240,(64,96),dtype=np.uint8);gray=cv2.GaussianBlur(gray,(5,5),0);raw=np.linspace(0,1,96)[None,:].repeat(64,axis=0).astype(np.float32)
 smoothed,metrics=depth.stabilize(raw*1.05+.02,raw,gray,gray,.3)
 assert metrics['flow_reliable_fraction']>.9 and np.isfinite(smoothed).all()
 assert np.mean(abs(smoothed-raw))<np.mean(abs(raw*1.05+.02-raw))
 with pytest.raises(ValueError):depth.DepthRequest(path='x',end=16)

def test_compact_mcp_discovery_execution_images_errors(tmp_path):
 from mcp import ClientSession,StdioServerParameters
 from mcp.client.stdio import stdio_client
 async def run():
  params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/'run.py')],env={**os.environ,'EDITVIDEO_DATA':str(tmp_path),'EDITVIDEO_TOOLSET':'compact','PYTHONIOENCODING':'utf-8'})
  async with stdio_client(params) as (reader,writer):
   async with ClientSession(reader,writer) as client:
    await client.initialize();listed=await client.list_tools();assert len(listed.tools)==7
    route=await client.call_tool('editvideo_bootstrap',{'task':'đọc video và dựng HDR chiều sâu','client':'codex'});assert not route.isError
    found=await client.call_tool('editvideo_discover_tools',{'query':'HDR','include_schema':True,'limit':12});items=json.loads(found.content[0].text)['items'];assert any(t['name']=='editvideo_process_color' for t in items)
    assert found.structuredContent is None and '\n' not in found.content[0].text  # token economy: one compact JSON copy
    result=await client.call_tool('editvideo_execute_tool',{'tool':'editvideo_design_catalog','arguments':{'kind':'font','limit':1}});assert not result.isError and 'bevietnampro' in result.content[0].text
    bad=await client.call_tool('editvideo_execute_tool',{'tool':'editvideo_create_project','arguments':{'config':{'profile':'invented'}}});assert bad.isError and 'recover' in bad.content[0].text
    image=tmp_path/'inline.png';Image.new('RGB',(60,40),'green').save(image)
    result=await client.call_tool('editvideo_execute_tool',{'tool':'editvideo_observe_media','arguments':{'path':str(image)}});assert not result.isError and any(v.type=='image' for v in result.content)
    one=await client.read_resource('editvideo://schema/Scene3D');assert 'CameraPose' in one.contents[0].text
 asyncio.run(run())

def test_window_edit_context_has_revision_and_only_intersection(workspace):
 from editvideo.agent_interface import edit_context,creative_packet
 pid=planned();p=agent.read(pid)
 agent.patch(pid,p['revision'],[{'op':'upsert_layer','layer':{'id':'early','kind':'text','text':'First','start_frame':0,'end_frame':30}}, {'op':'upsert_layer','layer':{'id':'later','kind':'text','text':'Second','start_frame':30,'end_frame':60}}])
 packet=edit_context(pid,.1,.8);assert packet['revision']==p['revision']+1 and [l['id'] for l in packet['layers']]==['early']
 with pytest.raises(ValueError):edit_context(pid,0,16)
 brief=creative_packet({'title':'Một ý','audience':'Người học','promise':'Hiểu rõ','payoff':'Một ví dụ','beats':[{'id':'start','narration':'Một lời nói rõ.','visual_idea':'Sơ đồ giải thích','shot_choice':'diagram'}]})
 assert Path(brief['script_path']).read_text(encoding='utf-8')=='Một lời nói rõ.'
