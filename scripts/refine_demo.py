"""Refine observed arrow/label overlap in the existing MCP demo, then re-render."""
import asyncio,json,os,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from editvideo import store
from demo_agent import DIAGRAM

async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pid="8f2e867c-9234-46be-a3a1-10bbe4955f9f"
    words=store.read_json(store.folder("9b2ef483-59bf-40ac-8d6f-1d8d613a09ea")/"plan"/"words.json")["words"]
    cues=[{"start":words[a]["start"],"end":words[b-1]["end"],"text":" ".join(w["text"] for w in words[a:b])}
          for a,b in ((0,12),(12,18),(18,23),(23,28),(28,32),(32,38),(38,42),(42,50),(50,56),(56,60),(60,66))]
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/"run.py")],env={**os.environ,"PYTHONIOENCODING":"utf-8"})
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as client:
            await client.initialize()
            async def call(name,args):
                result=await client.call_tool("editvideo_"+name,args)
                if result.isError:raise RuntimeError(str(result.content))
                return result.structuredContent or result.content
            p=await call("read_project",{"project_id":pid})
            await call("patch_timeline",{"project_id":pid,"base_revision":p["revision"],"operations":[{"op":"replace_cues","cues":cues}]})
            await call("export_code",{"project_id":pid,"engine":"remotion","overwrite":True})
            src=await call("read_code",{"project_id":pid,"engine":"remotion","relative_path":"index.tsx"})
            content=src["content"].replace('export const AgentVideo =',DIAGRAM+'\nexport const AgentVideo =')
            content=content.replace('    {(timeline.overlays || [])','    <Sequence from={134} durationInFrames={196}><ScienceDiagram/></Sequence>\n    {(timeline.overlays || [])')
            await call("write_code",{"project_id":pid,"engine":"remotion","relative_path":"index.tsx","content":content,"expected_sha256":src["sha256"]})
            snapshot=await call("snapshot_code",{"project_id":pid,"engine":"remotion","frames":[300]})
            print(json.loads(snapshot[0].text),flush=True)
            j=await call("submit_job",{"project_id":pid,"kind":"final"})
            while True:
                result=await call("get_job",{"job_id":j["id"]})
                if result["state"]=="completed":break
                if result["state"]=="failed":raise RuntimeError(result["error"])
                await asyncio.sleep(3)
            out=store.ROOT/"outputs"
            for artifact in result["artifacts"]:
                names={"final.mp4":"agent-quang-hop.mp4","delivery.zip":"agent-quang-hop.zip","storyboard.jpg":"agent-storyboard.jpg"}
                if artifact["name"] in names:shutil.copyfile(artifact["path"],out/names[artifact["name"]])
            store.write_json(out/"agent-demo.json",{"project_id":pid,"job":result})
            print({"project":pid,"job":j["id"],"report":result["output"]["report"]},flush=True)
            observed=await call("observe_media",{"path":str(out/"agent-quang-hop.mp4"),"timestamps":[1,6.7,10,12.5,18],"max_frames":5})
            print({"contact_sheet":json.loads(observed[0].text)["contact_sheet"]},flush=True)
asyncio.run(main())
