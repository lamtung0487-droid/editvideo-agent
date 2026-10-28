"""Real engine integration test, short local signal; no service credentials."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import agent,store
from editvideo.media import command,FFMPEG
from editvideo.jobs import Worker
from editvideo.code_engine import scaffold
from editvideo.observe import observe

store.initialize(recover=False)
p=agent.create({"title":"AI dựng video bằng code","script":"Quan sát. Tinh chỉnh. Dựng lại.","profile":"landscape"})
pid=p["id"]
signal=store.folder(pid)/"test-signal.wav"
command([FFMPEG,"-y","-v","error","-f","lavfi","-i","sine=frequency=220:sample_rate=48000:duration=1.2",signal])
a=agent.import_media(pid,str(signal),"test signal")
p=store.get_project(pid)
store.update_project(pid,{**p["config"],"narration_id":a["id"]})
j=store.create_job(pid,"plan");Worker().run(j["id"])
assert store.get_job(j["id"])["state"]=="completed",store.get_job(j["id"])
p=store.get_project(pid)
agent.patch(pid,p["revision"],[{"op":"upsert_overlay","overlay":{"id":"callout","start_frame":0,"end_frame":36,
    "text":"Code → video","font_size":80,"y":.12,"animation":"rise"}}])
for engine in ("remotion","hyperframes"):
    p=store.get_project(pid)
    store.update_project(pid,{**p["config"],"renderer":engine})
    source=scaffold(pid,engine,True)
    print(source,flush=True)
    j=store.create_job(pid,"preview");Worker().run(j["id"])
    result=agent.result(j["id"])
    print({k:result[k] for k in ("id","state","error","output")},flush=True)
    assert result["state"]=="completed",result["error"]
    path=store.folder(pid)/"jobs"/j["id"]/"preview.mp4"
    observation=observe(str(path),[.2,.8],2)
    print({"engine":engine,"video":str(path),"contact_sheet":observation["contact_sheet"]},flush=True)
print("PROJECT_ID="+pid,flush=True)
