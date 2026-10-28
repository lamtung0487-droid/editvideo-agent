"""Actual dual-engine transitions, rate/trim, animated layers and timed audio."""
import json
import shutil
import sys
import wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from editvideo import agent,store
from editvideo.media import command,FFMPEG,sha256
from editvideo.code_engine import scaffold
from editvideo.jobs import Worker
from editvideo.observe import observe
from editvideo.snapshot import snapshot

store.initialize(recover=False)
output=store.ROOT/"outputs";output.mkdir(exist_ok=True)
source=output/"integration-source.mp4"
command([FFMPEG,"-y","-v","error","-f","lavfi","-i","color=red:s=640x360:r=30:d=2","-f","lavfi","-i","color=blue:s=640x360:r=30:d=2","-f","lavfi","-i","sine=frequency=180:sample_rate=48000:duration=4","-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[v]","-map","[v]","-map","2:a","-c:v","libx264","-c:a","aac",source])
p=agent.from_video(str(source));pid=p["id"]
agent.patch(pid,p["revision"],[{"op":"split_shot","shot_id":"source-001","frame":60,"new_id":"incoming"}])
for engine in ("remotion","hyperframes"):scaffold(pid,engine)
# Imported SFX would stale a voice plan, so reuse the existing audio asset to add a delayed source excerpt.
p=agent.read(pid);voice=p["config"]["narration_id"]
layers=[{"id":"title","kind":"text","start_frame":0,"end_frame":120,"x":.1,"y":.08,"height":.08,"font_size":54,"text":"AI · Dựng nhiều lớp","effects":[{"name":"typewriter","end_frame":20},{"name":"glow","end_frame":20,"params":{"amount":6}}]},
    {"id":"counter","kind":"counter","start_frame":0,"end_frame":120,"x":.1,"y":.26,"width":.2,"height":.15,"data":{"to":42,"suffix":"%"},"effects":[{"name":"progress","end_frame":40}]},
    {"id":"bars","kind":"bar_chart","start_frame":0,"end_frame":120,"x":.4,"y":.23,"width":.45,"height":.25,"data":{"values":[35,80],"labels":["A","B"],"max":100},"effects":[{"name":"progress","end_frame":40}]},
    {"id":"flow","kind":"flow","start_frame":0,"end_frame":120,"x":.12,"y":.57,"width":.74,"height":.18,"data":{"labels":["Đọc","Dựng","Tinh chỉnh"]},"effects":[{"name":"progress","end_frame":50}]},
    {"id":"particles","kind":"particles","start_frame":60,"end_frame":120,"x":.6,"y":.03,"width":.3,"height":.3,"data":{"count":25,"seed":17},"effects":[{"name":"progress","end_frame":40}],"opacity":.5},
    {"id":"ring","kind":"shape","start_frame":0,"end_frame":120,"x":.06,"y":.25,"width":.28,"height":.24,"data":{"shape":"ring"},"effects":[{"name":"pulse","end_frame":119}],"keyframes":{"rotate":[{"frame":0,"value":0},{"frame":119,"value":25}]}},
    {"id":"chart","kind":"line_chart","start_frame":0,"end_frame":120,"x":.1,"y":.8,"width":.6,"height":.1,"data":{"values":[10,30,60,40],"max":100},"effects":[{"name":"progress","end_frame":80}]}]
operations=[{"op":"update_shot","shot_id":"source-001","changes":{"playback_rate":1.5}},
    {"op":"update_shot","shot_id":"incoming","changes":{"source_start":1,"playback_rate":1.5,"transition":{"name":"dissolve","duration_frames":12}}},
    {"op":"set_design","design":{"intent":"Explain an agent editing loop with clear labels"}},
    {"op":"upsert_audio","audio":{"id":"source-accent","asset_id":voice,"start_frame":30,"end_frame":60,"volume":.15,"duck_under_voice":False}}]
operations.extend({"op":"upsert_layer","layer":l} for l in layers)
agent.patch(pid,p["revision"],operations)
reports={}
for engine in ("remotion","hyperframes"):
    source_dir=store.folder(pid)/"code"/engine;entry=source_dir/("index.tsx" if engine=="remotion" else "index.html");before=sha256(entry)
    p=store.get_project(pid);store.update_project(pid,{**p["config"],"renderer":engine})
    j=store.create_job(pid,"preview");Worker().run(j["id"]);r=agent.result(j["id"]);assert r["state"]=="completed",r["error"]
    assert sha256(entry)==before
    work=store.folder(pid)/"jobs"/j["id"];video=output/f"advanced-{engine}.mp4";shutil.copyfile(work/"preview.mp4",video)
    obs=observe(str(video),[.3,1.6,2.1,3.5],4,640)
    means=[]
    for f in obs["frames"]:
        pixels=np.array(Image.open(f["path"]));means.append(pixels[-20:,-20:].mean(axis=(0,1)).tolist())
    assert means[0][0]>180 and means[0][2]<40,(engine,means)
    assert means[1][2]>180 and means[1][0]<40,(engine,means)
    assert means[2][0]>30 and means[2][2]>30,(engine,means)
    assert means[3][2]>180 and means[3][0]<40,(engine,means)
    with wave.open(str(work/"mix.wav")) as wav:assert wav.getnframes()==192000
    snap=snapshot(pid,engine,[63,9])
    reports[engine]={"job_id":j["id"],"video":str(video),"report":r["output"]["report"],"corner_rgb":means,"snapshots":snap["frames"],"source_customizations_preserved":True}
    print(json.dumps({"engine":engine,"passed":True,"corner_rgb":means}),flush=True)
store.write_json(output/"advanced-verification.json",{"project_id":pid,"engines":reports})
