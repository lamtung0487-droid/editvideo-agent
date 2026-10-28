import json
import subprocess
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from editvideo import agent,store
from editvideo.effects import CATALOG,catalog
from editvideo.models import Effect,Layer
from editvideo.media import command,FFMPEG
from editvideo.perception import index_video,inspect_window,crop_detail
from editvideo.code_engine import scaffold,refresh_payload
from test_pipeline import workspace
from test_agent import planned

def test_catalog_runtime_deterministic_and_keyframes():
    script="""const f=require(process.argv[1]);const names=Object.keys(f.defaults);const values=names.map(name=>f.styleAt({effects:[{name,start_frame:0,end_frame:30,params:{}}]},15));const a={effects:[{name:'shake',end_frame:30,params:{seed:9}}]};const first=f.styleAt(a,13);f.styleAt(a,2);console.log(JSON.stringify({names,values,deterministic:JSON.stringify(first)===JSON.stringify(f.styleAt(a,13)),key:f.track([{frame:0,value:0},{frame:30,value:100,easing:'linear'}],15)}));"""
    # Node uses .js as ESM in engines; an isolated CJS copy matches Remotion's export.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        file=Path(tmp)/"effects.cjs";file.write_text((store.ROOT/"engines/effects.js").read_text())
        result=json.loads(subprocess.check_output(["node","-e",script,str(file)],text=True))
    assert set(result["names"])==set(CATALOG) and len(CATALOG)==95
    assert result["deterministic"] and result["key"]==50
    assert len({json.dumps(v,sort_keys=True) for v in result["values"]})>35
    with pytest.raises(ValueError):Effect(name="invented")
    with pytest.raises(ValueError):Effect(name="rise",params={"amount":9000})
    with pytest.raises(ValueError):Effect(name="rise",params={"speed":3})
    with pytest.raises(ValueError):Layer(id="x",start_frame=0,end_frame=30,kind="bar_chart",data={"values":[1,4],"max":2})
    assert catalog("quantity")["effects"]==[] # Intents/recipes are explicit, not a fabricated semantic search.

def source_video(tmp_path):
    target=tmp_path/"source.mp4"
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i","color=c=red:s=320x180:r=30:d=1","-f","lavfi","-i","color=c=blue:s=320x180:r=30:d=1","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=2","-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[v]","-map","[v]","-map","2:a","-c:v","libx264","-c:a","aac",target])
    return target

def test_temporal_index_dense_evidence_crop(workspace,tmp_path):
    source=source_video(tmp_path);indexed=index_video(str(source),8)
    assert indexed["total_segments"]==2
    assert abs(indexed["segments"][0]["end"]-1)<.05
    result=inspect_window(str(source),.8,1.2,6,640,True)
    assert len(result["frames"])==6 and result["audio"]
    colors=[np.array(Image.open(f["path"])).mean(axis=(0,1)) for f in result["frames"]]
    assert colors[0][0]>200 and colors[-1][2]>200
    crop=crop_detail(str(source),1.2,[.25,.25,.75,.75],640)
    assert crop["source_crop_pixels"]==[80,45,160,90]
    assert crop["display_size"]==[640,360]
    assert index_video(str(source),8)["index_path"]==indexed["index_path"]

def test_layers_atomic_and_custom_source_survives(workspace):
    if not (store.ROOT / "engines/node_modules/three").exists():
        pytest.skip("engine packages not installed (run setup: npm ci in engines/)")
    pid=planned();p=agent.read(pid);source=Path(scaffold(pid,"remotion")["directory"])
    custom=source/"index.tsx";custom.write_text(custom.read_text()+"\n// custom kept\n")
    result=agent.patch(pid,p["revision"],[{"op":"set_design","design":{"intent":"Explain a mechanism"}},
        {"op":"upsert_layer","layer":{"id":"number","kind":"counter","start_frame":0,"end_frame":30,"data":{"to":42,"suffix":"%"},"effects":[{"name":"progress","end_frame":29}],"keyframes":{"opacity":[{"frame":0,"value":0},{"frame":10,"value":1}]}}}])
    refresh_payload(pid,source,result["timeline"],p["config"])
    assert "custom kept" in custom.read_text()
    assert json.loads((source/"input.json").read_text(encoding="utf-8"))["timeline"]["layers"][0]["id"]=="number"
    before=agent.read(pid)
    with pytest.raises(ValueError):agent.patch(pid,before["revision"],[{"op":"upsert_layer","layer":{"id":"bad","start_frame":0,"end_frame":20,"effects":[{"name":"spring","end_frame":30}]}}])
    assert agent.read(pid)["revision"]==before["revision"]

def test_existing_video_retains_audio(workspace,tmp_path):
    p=agent.from_video(str(source_video(tmp_path)))
    assert p["timeline"]["total_frames"]==60
    assert p["timeline"]["timing_method"]=="source_video_audio"
    assert p["config"]["narration_id"] and not p["config"]["captions"]


def test_optical_flow_translation(workspace,tmp_path):
    from editvideo.perception import track_region
    noise=np.random.default_rng(12).integers(30,230,(80,80,3),dtype=np.uint8)
    for i in range(60):
        frame=Image.new("RGB",(320,180),"#202020");frame.paste(Image.fromarray(noise),(32+round(i*1.5),45));frame.save(tmp_path/f"moving-{i:03}.png")
    target=tmp_path/"moving.mp4"
    command([FFMPEG,"-y","-v","error","-framerate","30","-i",tmp_path/"moving-%03d.png","-c:v","libx264","-crf","15",target])
    result=track_region(str(target),0,2,[.1,.25,.35,.7],8,320,180)
    assert result["lost_at"] is None
    last=result["tracks"][-1]
    assert abs(last["delta_pixels"][0]-last["timestamp"]*30*1.5)<8
    assert abs(last["delta_pixels"][1])<3
    assert len(result["keyframes"]["x"])==len(result["tracks"])


@pytest.mark.parametrize("duck,rate",[(False,1),(True,1),(False,1.5)])
def test_timed_audio_is_absent_before_placement(workspace,tmp_path,duck,rate):
    import shutil,wave
    from editvideo.jobs import Worker
    from editvideo.renderer import mix_audio
    pid=planned();tone=tmp_path/"accent.wav"
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i","sine=frequency=1000:sample_rate=48000:duration=2",tone])
    a=agent.import_media(pid,str(tone));j=store.create_job(pid,"plan");Worker().run(j["id"])
    assert store.get_job(j["id"])["state"]=="completed"
    p=agent.read(pid);result=agent.patch(pid,p["revision"],[{"op":"upsert_audio","audio":{"id":"accent","asset_id":a["id"],"start_frame":30,"end_frame":60,"volume":1,"playback_rate":rate,"fade_in":.1,"fade_out":.1,"duck_under_voice":duck}}])
    work=tmp_path/"mix-test";work.mkdir();shutil.copyfile(store.folder(pid)/"plan/voice.wav",work/"voice.wav");store.write_json(work/"timeline.json",result["timeline"])
    mix_audio(pid,p["config"],work,result["timeline"]["total_frames"]/30,lambda:False)
    with wave.open(str(work/"mix.wav")) as wav:
        pixels=np.frombuffer(wav.readframes(wav.getnframes()),dtype="<i2").reshape(-1,2).mean(axis=1)
    def energy(at):
        sample=pixels[round(at*48000):round((at+.1)*48000)];spec=np.abs(np.fft.rfft(sample*np.hanning(len(sample))));return spec[100]
    assert energy(.2)<energy(1.4)*.01


def test_one_file_used_by_many_clips_is_opened_once(workspace,tmp_path):
    """A documentary reuses an effect file many times: the mix opens it once and splits it (one -i per clip passed the
    Windows command-line limit at ~270 clips); each placement still sounds where it is placed."""
    import shutil,wave
    from unittest import mock
    from editvideo.jobs import Worker
    from editvideo import renderer
    pid=planned();tone=tmp_path/"accent.wav"
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i","sine=frequency=1000:sample_rate=48000:duration=1",tone])
    a=agent.import_media(pid,str(tone));j=store.create_job(pid,"plan");Worker().run(j["id"])
    p=agent.read(pid)
    ops=[{"op":"upsert_audio","audio":{"id":f"accent-{k}","asset_id":a["id"],"start_frame":6+24*k,"end_frame":18+24*k,"volume":1,"fade_in":.01,"fade_out":.01,"duck_under_voice":False}} for k in range(3)]
    result=agent.patch(pid,p["revision"],ops)
    work=tmp_path/"mix-many";work.mkdir();shutil.copyfile(store.folder(pid)/"plan/voice.wav",work/"voice.wav");store.write_json(work/"timeline.json",result["timeline"])
    calls=[]
    real=renderer.command
    def spy(args,*a,**k):
        calls.append([str(x) for x in args]);return real(args,*a,**k)
    with mock.patch.object(renderer,"command",spy):
        renderer.mix_audio(pid,p["config"],work,result["timeline"]["total_frames"]/30,lambda:False)
    mix=next(c for c in calls if any(x.endswith("base-mix.wav") for x in c))
    inputs=[mix[i+1] for i,x in enumerate(mix) if x=="-i"]
    assert len(inputs)==len(set(inputs))==3  # base mix, voice, and the shared file once
    with wave.open(str(work/"mix.wav")) as wav:
        x=np.frombuffer(wav.readframes(wav.getnframes()),dtype="<i2").reshape(-1,2).mean(axis=1)
    def energy(at):
        s=x[round(at*48000):round((at+.1)*48000)];return np.abs(np.fft.rfft(s*np.hanning(len(s))))[100]
    for k in range(3):
        assert energy((6+24*k)/30+.1)>energy((6+24*k)/30+.45)*20  # every placement sounds, then stops
