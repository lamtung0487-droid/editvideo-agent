"""Masks and provider protocols tested independently of costly model inference."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from editvideo import agent,store,media_tasks,subjects,generation
from editvideo.media import FFMPEG,command,sha256,probe


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    # a fresh store sees no models: not its own, nor the installation's shared ones (store.models_root)
    monkeypatch.setattr(store,"DATA",tmp_path);monkeypatch.setattr(store,"SHARED_MODELS",tmp_path/"no-shared-models");store.initialize();return tmp_path


def make_session(root):
    source=root/"source.mp4"
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i","color=red:s=256x144:r=30:d=1","-c:v","libx264",source])
    task=media_tasks.submit("subject",{"path":str(source),"end":1,"width":256,"prompts":[{"object_id":1,"box":[.25,.25,.75,.75]}]},launch=False)
    out=media_tasks.folder(task["id"]);frames=out/"frames";frames.mkdir();masks=out/"masks-1";masks.mkdir();overlay=out/"overlay-frames";overlay.mkdir()
    hashes={};tracks=[]
    for i in range(30):
        rgb=np.zeros((144,256,3),np.uint8);rgb[:]=[180,30,10]
        mask=np.zeros((144,256),np.uint8);mask[36:108,64:192]=255
        Image.fromarray(rgb).save(frames/f"{i:06d}.jpg");Image.fromarray(rgb).save(overlay/f"{i:06d}.png")
        p=masks/f"{i:06d}.png";Image.fromarray(mask).save(p);hashes[p.relative_to(out).as_posix()]=sha256(p)
        tracks.append({"frame":i,"source_time":i/30,"box":[.25,.25,.75,.75],"visible":True,"area_fraction":.25})
    manifest={"source":str(source),"source_sha256":sha256(source),"start":0,"end":1,"fps":30,"frames":30,"mask_dimensions":[256,144],"mask_hashes":hashes,"tracks":{"1":tracks}}
    path=out/"subjects.json";store.write_json(path,manifest);store.write_json(out/"request.json",task["request"])
    media_tasks.update(task["id"],"completed",1,result={"manifest_sha256":sha256(path)})
    return task["id"],source


def test_prompt_validation_and_immutable_corrections(workspace,monkeypatch):
    for prompt in ({"box":[.8,.1,.2,.6]}, {"points":[[.5,.5]],"labels":[]}, {"box":[0,0,1,float('nan')]}):
        with pytest.raises(ValueError):subjects.Prompt.model_validate({"object_id":1,**prompt})
    task_id,_=make_session(workspace);captured=[]
    monkeypatch.setattr(media_tasks,"submit",lambda kind,request:captured.append(request) or request)
    subjects.refine(task_id,[{"object_id":1,"frame":12,"points":[[.4,.5],[.1,.1]],"labels":[1,0]}])
    assert len(captured[0]["prompts"])==2
    assert len(store.read_json(media_tasks.folder(task_id)/"request.json")["prompts"])==1
    result=subjects.read_session(task_id,1,offset=25,limit=5,frames=[0,29]);assert len(result["tracks"])==5 and result["next_offset"] is None


def test_temporal_scene_boundaries_and_overlapping_coverage(workspace):
    from editvideo.temporal import windows,scene_boundaries
    files=[]
    for i in range(6):
        p=workspace/f"{i}.png";Image.new("RGB",(96,64),"red" if i<3 else "blue").save(p);files.append(p)
    assert scene_boundaries(files)==[0,3,6]
    assert scene_boundaries(files,[2])==[0,2,3,6]
    ranges=windows(0,60,24,6)
    assert ranges==[(0,24),(18,42),(36,60)]
    assert {i for a,b in ranges for i in range(a,b)}==set(range(60))
    with pytest.raises(ValueError):windows(0,60,24,24)
    with pytest.raises(ValueError):scene_boundaries(files,[0])


def test_temporal_fill_composites_only_hole_at_native_resolution(workspace,monkeypatch):
    from editvideo import temporal
    session,_=make_session(workspace)
    def fill(task_id,req,manifest,subject_root,source_frames,suffix,out):
        dest=out/"predictions";dest.mkdir()
        for i in range(manifest['frames']):Image.new('RGB',(128,72),'blue').save(dest/f'{i:06d}.png')
        return dest,{'backend':'propainter','temporal_model':True}
    monkeypatch.setattr(temporal,'inpaint',fill)
    t=media_tasks.submit('mask_edit',{'subject_task_id':session,'object_ids':[1],'operation':'remove','backend':'propainter','dilation':0,'feather':0},launch=False)
    r=media_tasks.run(t['id']);assert r['state']=='completed',r['error']
    image=np.asarray(Image.open(Path(r['result']['frames_directory'])/'000000.png'))
    source=np.asarray(Image.open(media_tasks.folder(t['id'])/'source-frames/000000.png'))
    assert image.shape==source.shape==(144,256,3)
    assert np.array_equal(image[:30],source[:30])
    assert image[60,100].tolist()==[0,0,255]
    assert r['result']['temporal']['temporal_model']


def test_temporal_isolated_frame_never_borrows_across_cut(workspace,monkeypatch):
    from editvideo import temporal
    session,_=make_session(workspace);manifest,subject_root=subjects.load_session(session)
    repo=temporal.root();(repo/'weights').mkdir(parents=True)
    for name in temporal.WEIGHTS:(repo/'weights'/name).write_bytes(b'contract fixture')
    seen=[]
    def upstream(args,**kwargs):
        if args[0]=='git':return temporal.REVISION
        frames=Path(args[args.index('--video')+1]);images=sorted(frames.glob('*.png'));seen.append(len(images))
        dest=Path(args[args.index('--output')+1])/'input/frames';dest.mkdir(parents=True)
        for i,x in enumerate(images):Image.open(x).save(dest/f'{i:04d}.png')
    monkeypatch.setattr(temporal,'ready',lambda:True);monkeypatch.setattr(temporal,'command',upstream)
    t=media_tasks.submit('mask_edit',{'subject_task_id':session,'object_ids':[1],'operation':'remove','backend':'propainter','scene_cuts':[1],'temporal_window':24,'temporal_overlap':6},launch=False)
    req=subjects.MaskEditRequest.model_validate(t['request'])
    out=media_tasks.folder(t['id']);dest,metadata=temporal.inpaint(t['id'],req,manifest,subject_root,subject_root/'frames','.jpg',out)
    assert metadata['windows'][0]==[0,1] and metadata['windows'][1][0]==1
    assert seen[0]==2 and len(list(dest.glob('*.png')))==30
    assert sha256(out/'temporal-window-000/input/000000.png')==sha256(out/'temporal-window-000/input/000001.png')


def test_local_generation_constraints_and_cached_only_preflight(workspace):
    base={'provider':'local_ltx','prompt':'Sunlight moves through leaves','width':512,'height':320,'fps':24,'duration':3,'frame_count':73}
    assert generation.GenerationRequest(**base).model=='ltx-2b-distilled'
    simple=generation.GenerationRequest(provider='local_ltx',prompt='Sunlight moves through leaves')
    assert (simple.width,simple.height,simple.fps,simple.frame_count)==(512,320,24,73)
    for change in ({'width':513},{'frame_count':72},{'frame_count':169},{'reference_mask':'missing.png'},{'negative_prompt':'text'}):
        with pytest.raises(ValueError):generation.GenerationRequest(**{**base,**change})
    with pytest.raises(ValueError,match='not installed'):generation.validate_request(base)
    assert not generation.capabilities()['generation']['local_ltx']['ready']


def test_local_model_ready_rejects_changed_verified_artifacts(workspace,monkeypatch):
    from editvideo import local_footage
    names=[local_footage.MODEL,'text_encoder/config.json','tokenizer/spiece.model',
           'tokenizer/added_tokens.json','tokenizer/special_tokens_map.json','tokenizer/tokenizer_config.json',
           'config/transformer/config.json','config/vae/config.json',
           'config/scheduler/scheduler_config.json','t5xxl_fp8_e4m3fn.safetensors']
    artifacts=[]
    for name in names:
        path=local_footage.root()/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'cached artifact contract fixture')
        artifacts.append({'path':str(path),'bytes':path.stat().st_size,
                          'mtime_ns':path.stat().st_mtime_ns,'sha256':sha256(path)})
    store.write_json(store.DATA/'models/temporal-models.json',{'ltx':{
        'text_encoder_precision':'fp8','artifacts':artifacts}})
    monkeypatch.setattr(local_footage.importlib.util,'find_spec',lambda name:True)
    assert local_footage.ready()
    checkpoint=local_footage.root()/local_footage.MODEL
    stat=checkpoint.stat()
    os.utime(checkpoint,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000))
    assert not local_footage.ready()


def test_import_preserves_locked_plan_and_conflicting_revision(workspace):
    _,source=make_session(workspace);p=agent.from_video(str(source))
    folder=store.folder(p['id']);before=[sha256(folder/'plan'/n) for n in ('voice.wav','timeline.json')]
    a=agent.import_media(p['id'],str(source),'additional footage',preserve_plan=True,base_revision=p['revision'])
    assert a['plan_preserved'] and a['revision']==p['revision']+1
    assert before==[sha256(folder/'plan'/n) for n in ('voice.wav','timeline.json')]
    with pytest.raises(ValueError,match='Revision conflict'):agent.import_media(p['id'],str(source),preserve_plan=True,base_revision=p['revision'])


def test_mask_integrity_alpha_and_attach_preserve_plan(workspace):
    session,source=make_session(workspace)
    task=media_tasks.submit("mask_edit",{"subject_task_id":session,"object_ids":[1],"operation":"foreground","dilation":0,"feather":0},launch=False)
    r=media_tasks.run(task["id"]);assert r["state"]=="completed",r["error"]
    alpha_frame=np.asarray(Image.open(Path(r["result"]["frames_directory"])/"000000.png"))
    assert alpha_frame[60,100,3]==255 and alpha_frame[0,0,3]==0
    p=agent.from_video(str(source));before=sha256(store.folder(p["id"])/"plan/voice.wav")
    attached=media_tasks.attach(task["id"],p["id"],p["revision"])
    assert attached["plan_preserved"] and attached["asset"]["alpha"]
    assert sha256(store.folder(p["id"])/"plan/voice.wav")==before
    agent.patch(p["id"],attached["revision"],[{"op":"upsert_layer","layer":{"id":"subject","kind":"video","asset_id":attached["asset"]["id"],"start_frame":0,"end_frame":30}}])
    with pytest.raises(ValueError):media_tasks.attach(task["id"],p["id"],p["revision"])
    mask=media_tasks.folder(session)/"masks-1/000000.png";Image.new("L",(256,144),0).save(mask)
    bad=media_tasks.submit("mask_edit",{"subject_task_id":session,"object_ids":[1],"operation":"blur"},launch=False)
    assert "Mask changed" in media_tasks.run(bad["id"])["error"]


def test_cancel_and_dead_process_recovery(workspace):
    session,_=make_session(workspace)
    t=media_tasks.submit("mask_edit",{"subject_task_id":session,"object_ids":[1],"operation":"blur"},launch=False)
    media_tasks.cancel(t["id"]);assert media_tasks.run(t["id"])["state"]=="cancelled"
    t=media_tasks.submit("mask_edit",{"subject_task_id":session,"object_ids":[1],"operation":"blur"},launch=False)
    with store.connection() as db:db.execute("UPDATE media_tasks SET owner_pid=99999999 WHERE id=?",(t["id"],))
    assert media_tasks.get(t["id"])["state"]=="interrupted"


def test_comfy_real_http_protocol_output_and_scoped_cancel(workspace,monkeypatch):
    source=workspace/"provider.mp4";command([FFMPEG,"-y","-v","error","-f","lavfi","-i","color=blue:s=256x144:r=24:d=1","-c:v","libx264",source])
    seen=[];pending=[False]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path.startswith('/view'):
                self.send_response(200);self.end_headers();self.wfile.write(source.read_bytes());return
            data={}
            if self.path=='/object_info':data={'Text':{'input':{}},'SaveVideo':{'input':{}}}
            elif self.path.startswith('/history/') and not pending[0]:data={'remote-1':{'status':{'completed':True,'status_str':'success'},'outputs':{'2':{'videos':[{'filename':'clip.mp4','type':'output'}]}}}}
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append((self.path,body))
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'prompt_id':'remote-1'} if self.path=='/prompt' else {}).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    monkeypatch.setenv('EDITVIDEO_COMFY_URL',f'http://127.0.0.1:{server.server_port}');monkeypatch.delenv('EDITVIDEO_COMFY_TARGETED_INTERRUPT',raising=False)
    generation.register_workflow('test',{'1':{'class_type':'Text','inputs':{'text':''}},'2':{'class_type':'SaveVideo','inputs':{}}},{'prompt':[{'node':'1','input':'text'}]},output_node='2')
    request={'provider':'comfyui','workflow':'test','prompt':'A slow explanatory camera shot','width':256,'height':144,'duration':2}
    try:
        t=media_tasks.submit('generate',request,launch=False)
        workflow_file=generation.workflow_path('test');saved=store.read_json(workflow_file);workflow_file.unlink()
        r=media_tasks.run(t['id']);assert r['state']=='completed',r['error']
        store.write_json(workflow_file,saved)
        assert seen[0][1]['prompt']['1']['inputs']['text']==request['prompt']
        assert r['result']['fps']==30 and r['result']['actual_duration']==1
        assert 'width' in r['result']['remote']['unbound_parameters']
        assert probe(r['result']['artifacts']['video'])['streams'][0]['r_frame_rate']=='30/1'
        pending[0]=True
        t=media_tasks.submit('generate',request,launch=False)
        monkeypatch.setattr(generation,'_pause',lambda tid:media_tasks.cancel(tid))
        assert media_tasks.run(t['id'])['state']=='cancelled'
        assert ('/queue',{'delete':['remote-1']}) in seen
        assert not any(path=='/interrupt' for path,_ in seen)
    finally:server.shutdown();server.server_close()


def test_runway_configuration_and_provider_constraints(workspace,monkeypatch):
    monkeypatch.delenv('EDITVIDEO_RUNWAY_API_KEY',raising=False);monkeypatch.setenv('OPENAI_API_KEY','unrelated-key')
    with pytest.raises(ValueError,match='not configured'):generation.validate_request({'provider':'runway','prompt':'A leaf moving slowly'})
    with pytest.raises(ValueError):generation.GenerationRequest(provider='runway',prompt='x',model='gen4_turbo')
    with pytest.raises(ValueError):generation.GenerationRequest(provider='runway',prompt='x',negative_prompt='text')
    assert not generation.capabilities()['generation']['runway']['configured']


def test_running_task_cannot_be_claimed_twice(workspace):
    session,_=make_session(workspace)
    t=media_tasks.submit('mask_edit',{'subject_task_id':session,'object_ids':[1],'operation':'blur'},launch=False)
    media_tasks.update(t['id'],'running',.4,'Another worker owns this task')
    assert media_tasks.run(t['id'])['progress']==.4
    assert not (media_tasks.folder(t['id'])/'edited-frames').exists()


def test_runway_http_contract_and_storage_key_isolation(workspace,monkeypatch):
    import httpx
    source=workspace/'runway-output.mp4'
    command([FFMPEG,'-y','-v','error','-f','lavfi','-i','color=green:s=256x144:r=24:d=1','-c:v','libx264',source])
    calls=[]
    def handle(request):
        calls.append(request)
        if request.url.host=='storage.example':
            assert 'authorization' not in request.headers
            return httpx.Response(200,content=source.read_bytes())
        assert request.headers['authorization']=='Bearer test-key'
        assert request.headers['X-Runway-Version']=='2024-11-06'
        if request.method=='POST':
            body=json.loads(request.content);assert body['model']=='gen4.5' and body['promptText']=='A botanical explanatory shot'
            if request.url.path=='/v1/image_to_video':
                import base64
                assert body['promptImage']=='data:image/png;base64,'+base64.b64encode(original_reference).decode()
            return httpx.Response(200,json={'id':'runway-task'})
        return httpx.Response(200,json={'status':'SUCCEEDED','output':['https://storage.example/video.mp4']})
    actual_client=httpx.Client
    monkeypatch.setattr(generation.httpx,'Client',lambda **kwargs:actual_client(transport=httpx.MockTransport(handle),**kwargs))
    monkeypatch.setenv('EDITVIDEO_RUNWAY_API_KEY','test-key')
    t=media_tasks.submit('generate',{'provider':'runway','prompt':'A botanical explanatory shot'},launch=False)
    result=media_tasks.run(t['id'])
    assert result['state']=='completed',result['error']
    assert result['result']['actual_dimensions']==[256,144]
    assert [r.url.path for r in calls]==['/v1/text_to_video','/v1/tasks/runway-task','/video.mp4']
    reference=workspace/'reference.png';Image.new('RGB',(256,144),'green').save(reference)
    original_reference=reference.read_bytes()
    t=media_tasks.submit('generate',{'provider':'runway','prompt':'A botanical explanatory shot','reference_image':str(reference)},launch=False)
    Image.new('RGB',(256,144),'red').save(reference)
    result=media_tasks.run(t['id']);assert result['state']=='completed',result['error']
    assert calls[-3].url.path=='/v1/image_to_video'
