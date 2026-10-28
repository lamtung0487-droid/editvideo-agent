"""Exercise nonzero trim and a later shot through both real renderers."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import agent,store
from editvideo.media import FFMPEG,command
from editvideo.jobs import Worker
from editvideo.code_engine import scaffold
from editvideo.observe import observe
from PIL import Image,ImageStat

store.initialize(recover=False)
p=agent.create({"title":"Source trim test","script":"Nguồn hình kiểm thử.","profile":"landscape","captions":False})
pid=p["id"]
root=store.folder(pid)
command([FFMPEG,"-y","-v","error","-f","lavfi","-i","color=red:s=640x360:r=30:d=1",
         "-f","lavfi","-i","color=blue:s=640x360:r=30:d=2","-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0",
         "-c:v","libx264","-pix_fmt","yuv420p",root/"colors.mp4"])
command([FFMPEG,"-y","-v","error","-f","lavfi","-i","sine=frequency=220:sample_rate=48000:duration=1.2",root/"signal.wav"])
video=agent.import_media(pid,str(root/"colors.mp4"))
voice=agent.import_media(pid,str(root/"signal.wav"))
p=store.get_project(pid);store.update_project(pid,{**p["config"],"narration_id":voice["id"]})
j=store.create_job(pid,"plan");Worker().run(j["id"])
assert store.get_job(j["id"])["state"]=="completed"
p=store.get_project(pid)
agent.patch(pid,p["revision"],[{"op":"split_shot","shot_id":"shot-001","frame":18,"new_id":"blue"},
    {"op":"update_shot","shot_id":"shot-001","changes":{"asset_id":video["id"],"source_start":.2,"motion":"hold"}},
    {"op":"update_shot","shot_id":"blue","changes":{"asset_id":video["id"],"source_start":1.4,"motion":"hold"}}])
for engine in ("remotion","hyperframes"):
    p=store.get_project(pid);store.update_project(pid,{**p["config"],"renderer":engine})
    scaffold(pid,engine,True)
    j=store.create_job(pid,"preview");Worker().run(j["id"])
    result=agent.result(j["id"])
    assert result["state"]=="completed",result["error"]
    path=root/"jobs"/j["id"]/"preview.mp4"
    obs=observe(str(path),[.2,.8],2)
    means=[]
    for frame in obs["frames"]:
        with Image.open(frame["path"]) as im:
            means.append(ImageStat.Stat(im.convert("RGB")).mean)
    assert means[0][0]>200 and means[0][2]<20,(engine,means)
    assert means[1][2]>200 and means[1][0]<20,(engine,means)
    print({"engine":engine,"job":j["id"],"means":means,"video":str(path)},flush=True)
print("PASSED video offsets and second shot for both engines",flush=True)
