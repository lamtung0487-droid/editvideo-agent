"""Author a narrated film through MCP; reuse the plan while attaching real media."""
import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store
from editvideo.media import sha256
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

PARAGRAPHS=[
"Một bức hình đẹp chưa đủ. Khi sửa video, nền phải liền mạch qua từng khung hình.",
"Đây là cảnh gốc. Chủ thể chuyển động, che khuất nhau và để lộ nền ở những thời điểm khác nhau.",
"Nếu AI tái tạo từng hình riêng lẻ, hoa văn và màu sắc có thể thay đổi liên tục. Ta nhìn thấy hiện tượng nhấp nháy.",
"Xóa và lấp nền theo thời gian tận dụng cả hình trước lẫn hình sau. Dòng chuyển động giúp đưa phần nền đã thấy sang vùng đang bị che.",
"Claude có thể đọc các khung hình, chỉnh lại mặt nạ, xóa vật thể và giữ lời thuyết minh. Khi thiếu cảnh minh họa, AI còn có thể tạo đoạn phim mới từ mô tả.",
"Video đẹp cần chuyển động ổn định, bố cục dễ đọc và nhịp dựng hợp lời dẫn. Kết quả phải được xem trong chuyển động, vì vài ảnh tĩnh chưa kể hết câu chuyện."]

async def main():
    sys.stdout.reconfigure(encoding="utf-8");parser=argparse.ArgumentParser();parser.add_argument("--prepare",action="store_true");parser.add_argument("--generation-task");parser.add_argument("--inpaint-task",default="fe6af504-2de7-49f3-a5e8-d2e38d153f1c");args=parser.parse_args()
    record=store.ROOT/"outputs/temporal-demo-project.json"
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/"run.py")],env={**os.environ,"PYTHONIOENCODING":"utf-8"})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize()
            async def call(name,args):
                r=await client.call_tool("editvideo_"+name,args)
                if r.isError:raise RuntimeError(str(r.content))
                return r.structuredContent or r.content
            async def job(pid,kind):
                j=await call("submit_job",{"project_id":pid,"kind":kind});print("job",kind,j["id"],flush=True)
                while True:
                    r=await call("get_job",{"job_id":j["id"]})
                    if r["state"] not in ("queued","running"):
                        if r["state"]!="completed":raise RuntimeError(r["error"])
                        return r
                    await asyncio.sleep(3)
            if args.prepare:
                p=await call("create_project",{"config":{"title":"AI sửa video: giữ chuyển động, giữ câu chuyện","script":"\n\n".join(PARAGRAPHS),"spoken_text":" ".join(PARAGRAPHS),"profile":"landscape","style":"documentary","renderer":"remotion","voice":"vi-VN-HoaiMyNeural","voice_rate":-5}})
                store.write_json(record,{"project_id":p["id"],"paragraphs":PARAGRAPHS})
                await job(p["id"],"plan");print("plan ready",p["id"],flush=True);return
            rec=store.read_json(record);rec["paragraphs"]=PARAGRAPHS;pid=rec["project_id"];ids=rec.get("assets",{})
            rec.setdefault('narration_before_sha256',sha256(store.folder(pid)/'plan/voice.wav'))
            store.write_json(record,rec)
            if not os.environ.get("EDITVIDEO_DEMO_SNAPSHOTS_ONLY") and not args.generation_task and "generated" not in ids:raise ValueError("Full film requires actual completed generated footage")
            for a in store.assets(pid):
                if a["tags"] in ("source","lama","overlay","temporal"):ids.setdefault(a["tags"],a["id"])
            for key,task in (("temporal",args.inpaint_task),("generated",args.generation_task)):
                if not task or key in ids:continue
                p=await call("read_project",{"project_id":pid});a=await call("attach_media_result",{"task_id":task,"project_id":pid,"base_revision":p["revision"],"tags":key,"role":"reconstruction"});ids[key]=a["asset"]["id"]
                rec["assets"]=ids;store.write_json(record,rec)
            for key,path in (("source","outputs/subject-source.mp4"),("lama","outputs/subject-inpaint.mp4"),("overlay","data/media-tasks/d5b21324-eb7f-4140-bedb-e2ba48562df3/subject-overlay.mp4")):
                if key in ids:continue
                p=await call("read_project",{"project_id":pid});a=await call("import_media",{"project_id":pid,"path":str(store.ROOT/path),"base_revision":p["revision"],"preserve_plan":True,"tags":key,"role":"illustration"});ids[key]=a["asset"]["id"]
                rec["assets"]=ids;store.write_json(record,rec)
            rec["assets"]=ids;store.write_json(record,rec)
            if "music" not in ids:
                import numpy as np,wave
                seconds=store.read_json(store.folder(pid)/"plan/timeline.json")["total_frames"]/30
                t=np.arange(round((seconds+.2)*48000))/48000
                notes=[110,164.8138,220];pad=sum(.024*np.sin(2*np.pi*n*t+.3*j)*(1+.12*np.sin(2*np.pi*(.06+j*.01)*t)) for j,n in enumerate(notes))
                pad*=np.minimum(1,t/1.5)*np.minimum(1,np.maximum(0,(seconds+.2-t)/1.5))
                path=store.ROOT/"outputs/temporal-demo-music.wav"
                with wave.open(str(path),'wb') as wf:wf.setparams((1,2,48000,0,'NONE','not compressed'));wf.writeframes((pad*32767).astype('<i2').tobytes())
                p=await call("read_project",{"project_id":pid});a=await call("import_media",{"project_id":pid,"path":str(path),"tags":"quiet original synthesized pad","preserve_plan":True,"base_revision":p["revision"]});ids["music"]=a["asset"]["id"];rec["assets"]=ids;store.write_json(record,rec)
            # Media references below are also represented as valid bounded layers,
            # so refresh_payload copies exactly the assets used by authored code.
            p=await call("read_project",{"project_id":pid});ops=[]
            from editvideo.audio import restore_display_text,group_words
            words=store.read_json(store.folder(pid)/"plan/words.json")["words"]
            restored=restore_display_text(words," ".join(PARAGRAPHS))
            if restored is None:raise ValueError("Measured narration words do not match display text")
            ops.append({"op":"replace_cues","cues":group_words(restored,max_words=10)})
            for key,aid in ids.items():
                if key=="music":continue
                ops.append({"op":"upsert_layer","layer":{"id":"reference-"+key,"kind":"video","asset_id":aid,"start_frame":0,"end_frame":30,"opacity":0}})
            ops.append({"op":"upsert_audio","audio":{"id":"quiet-pad","asset_id":ids["music"],"start_frame":0,"end_frame":p["timeline"]["total_frames"],"volume":.55,"fade_in":1,"fade_out":1.5,"duck_under_voice":True}})
            await call("patch_timeline",{"project_id":pid,"base_revision":p["revision"],"operations":ops})
            if not (store.folder(pid)/"code/remotion").exists():await call("export_code",{"project_id":pid,"engine":"remotion"})
            source=await call("read_code",{"project_id":pid,"engine":"remotion","relative_path":"index.tsx"})
            p=await call("read_project",{"project_id":pid});words=store.read_json(store.folder(pid)/"plan/words.json")["words"]
            # Align scenes to measured phrase boundaries, not estimated reading time.
            import re
            normalize=lambda s:re.sub(r"[^\w]+","",s,flags=re.UNICODE).casefold()
            normalized=[normalize(w["text"]) for w in words];cursor=0;bounds=[0]
            for para in PARAGRAPHS[1:]:
                start=[normalize(s) for s in para.split()[:4]]
                found=next((i for i in range(cursor+1,len(words)-4) if normalized[i:i+4]==start),None)
                if found is None:raise ValueError("Cannot align narration paragraph: "+para)
                bounds.append(round(words[found]["start"]*30));cursor=found
            bounds.append(p["timeline"]["total_frames"])
            trigger=next(i for i in range(len(words)-4) if normalized[i:i+4]==['khi','thiếu','cảnh','minh'])
            generate_from=round(words[trigger]["start"]*30)-bounds[4]
            rec["scene_frames"]=bounds;store.write_json(record,rec)
            template=(store.ROOT/"scripts/temporal_demo.tsx").read_text(encoding="utf-8")
            generated_frames=int(store.find_asset(pid,ids["generated"])["duration"]*30) if "generated" in ids else 151
            content=template.replace("__ASSETS__",json.dumps(ids)).replace("__BOUNDS__",json.dumps(bounds)).replace("__GENERATE_START__",str(generate_from)).replace("__GENERATED_FRAMES__",str(generated_frames))
            await call("write_code",{"project_id":pid,"engine":"remotion","relative_path":"index.tsx","content":content,"expected_sha256":source["sha256"]})
            snapshots=await call("snapshot_code",{"project_id":pid,"engine":"remotion","frames":[min(b+45,bounds[i+1]-1) for i,b in enumerate(bounds[:-1])]})
            rec["snapshots"]=json.loads(snapshots[0].text);store.write_json(record,rec)
            if os.environ.get("EDITVIDEO_DEMO_SNAPSHOTS_ONLY"):return
            result=await job(pid,"final");rec["job"]=result
            for a in result["artifacts"]:
                names={"final.mp4":"ai-video-complete.mp4","delivery.zip":"ai-video-complete.zip","storyboard.jpg":"ai-video-storyboard.jpg"}
                if a["name"] in names:shutil.copyfile(a["path"],store.ROOT/"outputs"/names[a["name"]])
            store.write_json(record,rec);print("complete",pid,result["id"],flush=True)

if __name__=="__main__":asyncio.run(main())
