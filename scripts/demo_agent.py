"""Real Vietnamese narration demo, authored/refined/rendered through an MCP client."""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from editvideo import store
from editvideo.audio import write_srt

DIAGRAM = '''
const ScienceDiagram = () => {
  const f = useCurrentFrame();
  const progress = Math.min(1, f/70);
  const enter = interpolate(Math.min(f,14),[0,14],[0,1]);
  return <AbsoluteFill style={{background:'linear-gradient(150deg,#102d2b,#173a32)',padding:80,opacity:enter}}>
    <div style={{fontSize:28,color:'#bee58f',letterSpacing:3,marginTop:70}}>HIỂU TRONG MỘT HÌNH</div>
    <h1 style={{fontSize:88,lineHeight:1.1,marginTop:35}}>Quang hợp<br/>hoạt động thế nào?</h1>
    <svg width="920" height="850" viewBox="0 0 920 850" style={{position:'absolute',top:500,left:80}}>
      <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#bee58f"/></marker></defs>
      <circle cx="460" cy="370" r="170" fill="#426b41" stroke="#bee58f" strokeWidth="4"/>
      <path d="M360 450Q330 230 550 260Q590 420 360 450Z" fill="#8cc672"/>
      <path d="M360 450L535 280" stroke="#ddefbe" strokeWidth="10"/>
      {[['Ánh sáng',460,70],['Nước',130,370],['CO₂',790,370]].map(([text,x,y],i)=><g key={String(text)} opacity={Math.min(1,Math.max(0,(f-i*18)/12))}>
        <rect x={Number(x)-115} y={Number(y)-50} width="230" height="100" rx="22" fill="#284b42"/>
        <text x={Number(x)} y={Number(y)+13} fill="#edf4df" fontSize="42" textAnchor="middle">{text}</text>
        <line x1={i===0?Number(x):i===1?Number(x)+120:Number(x)-120} y1={Number(y)+(i===0?60:0)} x2={i===0?460:i===1?280:640} y2={i===0?180:370} stroke="#bee58f" strokeWidth="5" markerEnd="url(#arrow)"/>
      </g>)}
      <g opacity={Math.max(0,(progress-.45)/.55)}>
        <line x1="460" y1="550" x2="460" y2="630" stroke="#bee58f" strokeWidth="6" markerEnd="url(#arrow)"/>
        <rect x="150" y="660" width="620" height="135" rx="26" fill="#bee58f"/>
        <text x="460" y="720" fill="#17352c" fontSize="43" fontWeight="700" textAnchor="middle">Chất hữu cơ + O₂</text>
        <text x="460" y="763" fill="#17352c" fontSize="27" textAnchor="middle">Năng lượng được tích trữ trong chất hữu cơ</text>
      </g>
    </svg>
  </AbsoluteFill>;
};
'''


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    original=store.get_project("9b2ef483-59bf-40ac-8d6f-1d8d613a09ea")
    original_plan=store.folder(original["id"])/"plan"
    original_timeline=store.read_json(original_plan/"timeline.json")
    words=store.read_json(original_plan/"words.json")["words"]
    # Preserve meaning units such as 'chất hữu cơ' and 'chăm sóc' using measured word boundaries.
    original_timeline["cues"]=[{"start":words[a]["start"],"end":words[b-1]["end"],"text":" ".join(w["text"] for w in words[a:b])}
                              for a,b in ((0,12),(12,18),(18,23),(23,28),(28,32),(32,38),(38,42),(42,50),(50,56),(56,60),(60,66))]
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/"run.py")],
                                env={**os.environ,"PYTHONIOENCODING":"utf-8"})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize()
            async def call(name,args):
                result=await client.call_tool("editvideo_"+name,args)
                if result.isError:
                    raise RuntimeError(str(result.content))
                return result.structuredContent or result.content
            p=await call("create_project",{"config":{**original["config"],"narration_id":None,"music_id":None,"renderer":"remotion"}})
            pid=p["id"]
            ids={}
            for asset in store.assets(original["id"]):
                a=await call("import_media",{"project_id":pid,"path":asset["path"],"tags":asset["tags"],"role":asset["role"]})
                ids[asset["id"]]=a["id"]
            voice=await call("import_media",{"project_id":pid,"path":str(original_plan/"voice.wav"),"tags":"Thuyết minh tiếng Việt thật"})
            p=await call("read_project",{"project_id":pid})
            await call("configure_project",{"project_id":pid,"base_revision":p["revision"],
                "changes":{"narration_id":voice["id"],"music_id":ids[original["config"]["music_id"]]}})
            write_srt(store.folder(pid)/"captions-input.srt",original_timeline["cues"])
            async def job(kind):
                j=await call("submit_job",{"project_id":pid,"kind":kind})
                while True:
                    result=await call("get_job",{"job_id":j["id"]})
                    if result["state"] not in ("queued","running"):
                        if result["state"]!="completed":
                            raise RuntimeError(result["error"])
                        return result
                    await asyncio.sleep(2)
            await job("plan")
            p=await call("read_project",{"project_id":pid})
            # Select observed original illustration media rather than guessing asset semantics from a new ID.
            shots=original_timeline["shots"]
            edits=[{"op":"update_shot","shot_id":s["id"],"changes":{"asset_id":ids[s["asset_id"]],"motion":"hold"}} for s in shots]
            await call("patch_timeline",{"project_id":pid,"base_revision":p["revision"],"operations":edits})
            await call("export_code",{"project_id":pid,"engine":"remotion"})
            source=await call("read_code",{"project_id":pid,"engine":"remotion","relative_path":"index.tsx"})
            content=source["content"].replace('export const AgentVideo =',DIAGRAM+'\nexport const AgentVideo =')
            content=content.replace('    {(timeline.overlays || [])',
                '    <Sequence from={134} durationInFrames={196}><ScienceDiagram/></Sequence>\n    {(timeline.overlays || [])')
            await call("write_code",{"project_id":pid,"engine":"remotion","relative_path":"index.tsx",
                "content":content,"expected_sha256":source["sha256"]})
            snap=await call("snapshot_code",{"project_id":pid,"engine":"remotion","frames":[200,300]})
            metadata=json.loads(snap[0].text)
            print({"project":pid,"snapshots":metadata["frames"]},flush=True)
            result=await job("final")
            out=store.ROOT/"outputs"
            for artifact in result["artifacts"]:
                names={"final.mp4":"agent-quang-hop.mp4","delivery.zip":"agent-quang-hop.zip","storyboard.jpg":"agent-storyboard.jpg"}
                if artifact["name"] in names:
                    shutil.copyfile(artifact["path"],out/names[artifact["name"]])
            store.write_json(out/"agent-demo.json",{"project_id":pid,"job":result})
            print({"project":pid,"job":result["id"],"output":result["output"]},flush=True)
            observed=await call("observe_media",{"path":str(out/"agent-quang-hop.mp4"),"timestamps":[1,6.7,10,12.5,18],"max_frames":5})
            print({"observation":json.loads(observed[0].text)["contact_sheet"]},flush=True)


if __name__=="__main__":asyncio.run(main())
