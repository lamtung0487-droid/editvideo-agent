import asyncio
import json
import os
import sys
from pathlib import Path
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from editvideo import agent,store
from editvideo.jobs import Worker
from editvideo.source_tools import read_source,write_source
from test_pipeline import fixture_project,workspace


def J(result):
    """Tool JSON: one compact text copy (token economy); structuredContent only when EDITVIDEO_STRUCTURED=1."""
    return result.structuredContent if result.structuredContent is not None else json.loads(result.content[0].text)


def planned():
    pid=fixture_project()
    j=store.create_job(pid,"plan");Worker().run(j["id"])
    assert store.get_job(j["id"])["state"]=="completed"
    return pid


def test_atomic_edits_conflict_and_history(workspace):
    pid=planned();p=agent.read(pid);before=p["timeline"]
    with pytest.raises(ValueError):
        agent.patch(pid,p["revision"],[{"op":"update_shot","shot_id":"shot-001","changes":{"text":"changed"}},
                                       {"op":"split_shot","shot_id":"shot-001","frame":999,"new_id":"right"}])
    assert agent.read(pid)["timeline"]==before
    after=agent.patch(pid,p["revision"],[{"op":"split_shot","shot_id":"shot-001","frame":30,"new_id":"right"},
        {"op":"upsert_overlay","overlay":{"id":"callout","start_frame":0,"end_frame":30,"text":"Chú thích"}}])
    assert Path(after["history"]).is_file()
    assert after["timeline"]["shots"][1]["start_frame"]==30
    with pytest.raises(ValueError,match="Revision conflict"):
        agent.patch(pid,p["revision"],[{"op":"delete_overlay","id":"callout"}])


def test_code_hash_and_path_protection(workspace):
    pid=planned()
    (store.folder(pid)/"code"/"remotion").mkdir(parents=True)
    initial=write_source(pid,"remotion","index.tsx","before")
    with pytest.raises(ValueError,match="hash conflict"):
        write_source(pid,"remotion","index.tsx","wrong","not-the-hash")
    assert read_source(pid,"remotion","index.tsx")["content"]=="before"
    written=write_source(pid,"remotion","index.tsx","after",initial["sha256"])
    assert Path(written["previous"]).read_text()=="before"
    with pytest.raises(ValueError):
        write_source(pid,"remotion","../../outside.tsx","bad")


def test_cancel_holds_lock_until_worker_stops(workspace):
    pid=planned();job=store.create_job(pid,"preview")
    store.job_progress(job["id"],state="running",progress=35)
    store.cancel(job["id"])
    assert store.get_job(job["id"])["state"]=="cancelling"
    with pytest.raises(ValueError):
        store.create_job(pid,"preview")
    store.finish_cancel(job["id"])
    assert store.create_job(pid,"preview")["state"]=="queued"


def test_dead_worker_job_can_be_resubmitted(workspace):
    pid=planned();job=store.create_job(pid,"preview")
    with store.connection() as db:
        db.execute("UPDATE jobs SET owner_pid=99999999 WHERE id=?",(job["id"],))
    replacement=store.create_job(pid,"preview")
    assert replacement["id"]!=job["id"]
    assert store.get_job(job["id"])["state"]=="interrupted"


def test_mcp_real_stdio_multimodal_and_edit(tmp_path):
    async def run():
        params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/"run.py")],
            env={**os.environ,"EDITVIDEO_DATA":str(tmp_path),"PYTHONIOENCODING":"utf-8"})
        async with stdio_client(params) as (reader,writer):
            async with ClientSession(reader,writer) as client:
                await client.initialize()
                tools=await client.list_tools()
                names={t.name for t in tools.tools}
                assert {"editvideo_observe_media","editvideo_patch_timeline","editvideo_write_code","editvideo_effect_catalog","editvideo_track_region","editvideo_aesthetic_packet","editvideo_project_from_video"}<=names
                assert {"editvideo_track_subject","editvideo_edit_subject","editvideo_generate_footage","editvideo_attach_media_result","editvideo_media_capabilities"}<=names
                assert {"editvideo_analyze_motion","editvideo_read_motion","editvideo_temporal_lens","editvideo_refine_footage"}<=names
                assert {"editvideo_professional_toolkit","editvideo_compose_edit","editvideo_read_audio_events","editvideo_design_sound"}<=names
                assert {"editvideo_design_catalog","editvideo_apply_design","editvideo_compose_graphic","editvideo_read_design_preview","editvideo_layout_text","editvideo_derive_palette"}<=names
                designs=await client.call_tool("editvideo_design_catalog",{"kind":"font","limit":20})
                assert not designs.isError and J(designs)["total"]==16
                measured=await client.call_tool("editvideo_layout_text",{"font_id":"bevietnampro","text":"Chữ tiếng Việt có dấu.","weight":600})
                assert not measured.isError and J(measured)["missing_glyphs"]==[]
                caps=await client.call_tool("editvideo_media_capabilities",{})
                assert not caps.isError and J(caps)["subject_tracking"]["backend"]=="sam2.1-hiera-tiny"
                catalog=await client.call_tool("editvideo_effect_catalog",{"query":"reveal","limit":12})
                assert not catalog.isError and J(catalog)["effects"]
                assert J(catalog)["engines"]==["remotion","hyperframes"] and all("use_when" in v for v in J(catalog)["effects"])
                prompts=await client.list_prompts()
                assert "video_director" in {p.name for p in prompts.prompts}
                created=await client.call_tool("editvideo_create_project",{"config":{"title":"Video kiến thức","script":"Mặt trời."}})
                assert not created.isError
                p=J(created)
                assert p["config"]["renderer"]=="remotion"
                from PIL import Image
                source=tmp_path/"source.png";Image.new("RGB",(320,240),"red").save(source)
                result=await client.call_tool("editvideo_observe_media",{"path":str(source),"max_frames":1})
                assert not result.isError
                assert len([c for c in result.content if c.type=="image"])==1
                assert json.loads(result.content[0].text)["frames"][0]["timestamp"]==0
                detail=await client.call_tool("editvideo_crop_detail",{"path":str(source),"timestamp":0,"region":[.25,.25,.75,.75]})
                assert not detail.isError and any(c.type=="image" for c in detail.content)
                bad=await client.call_tool("editvideo_configure_project",{"project_id":p["id"],"base_revision":0,"changes":{"title":"bad"}})
                assert bad.isError
                project=await client.call_tool("editvideo_read_project",{"project_id":p["id"]})
                assert J(project)["revision"]==1
                schema=await client.read_resource("editvideo://schemas")
                assert "Overlay" in schema.contents[0].text
                assert "reference_frames" in schema.contents[0].text
                toolkit=await client.call_tool('editvideo_professional_toolkit',{'platform':'tiktok'})
                assert not toolkit.isError and J(toolkit)['total']==17
                template=await client.read_resource('editvideo://runtime/remotion/effects.cjs')
                assert 'caption' in template.contents[0].text and 'paper_grain' in template.contents[0].text
                accent=await client.call_tool('editvideo_design_sound',{'kind':'impact','duration':.5,'gain_db':-24})
                assert not accent.isError
                events=await client.call_tool('editvideo_read_audio_events',{'path':J(accent)['path'],'start':0,'end':.5})
                assert not events.isError and any(c.type=='audio' for c in events.content)
                from editvideo.media import FFMPEG,command
                footage=tmp_path/'moving.mp4'
                command([FFMPEG,'-y','-v','error','-f','lavfi','-i','testsrc2=s=256x144:r=12:d=1','-c:v','libx264',footage])
                imported=await client.call_tool('editvideo_project_from_video',{'path':str(footage)})
                assert not imported.isError
                vp=J(imported)
                styled=await client.call_tool('editvideo_apply_design',{'project_id':vp['id'],'base_revision':vp['revision'],'request':{'style_id':'vietnam_knowledge'}})
                assert not styled.isError,styled.content
                graphic=await client.call_tool('editvideo_compose_graphic',{'project_id':vp['id'],'base_revision':J(styled)['revision'],'request':{'component':'keyword','end_frame':30,'text':'Một ý rõ'}})
                assert not graphic.isError,graphic.content
                colors=await client.call_tool('editvideo_derive_palette',{'seed':'#123456','harmony':'triadic','tone':'light'})
                assert not colors.isError and J(colors)['roles']['accent']=='#123456'
                preview=await client.call_tool('editvideo_read_design_preview',{'kind':'font','id':'bevietnampro'})
                # Optional atlas is built in development, omitted from the source-only ZIP.
                if (store.ROOT/'outputs/design-atlas.json').exists():assert not preview.isError and any(c.type=='image' for c in preview.content)
                template=await client.read_resource('editvideo://runtime/remotion/design.cjs')
                assert 'loadFonts' in template.contents[0].text
                motion=await client.call_tool('editvideo_analyze_motion',{'path':str(footage),'start':0,'end':1,'sampling_fps':12,'width':256,'evidence_frames':4})
                assert not motion.isError,motion.content
                packet=json.loads(motion.content[0].text)
                assert packet['sample_count']==12
                assert len([c for c in motion.content if c.type=='image'])>=4
                page=await client.call_tool('editvideo_read_motion',{'manifest':packet['manifest'],'limit':5})
                assert not page.isError and J(page)['total']==11
                lens=await client.call_tool('editvideo_temporal_lens',{'path':str(footage),'start':0,'end':1,'sampling_fps':24,'width':256,'low_hz':1,'high_hz':4})
                assert not lens.isError,lens.content
                assert len([c for c in lens.content if c.type=='image'])==3
    asyncio.run(run())


def test_token_economy_contracts():
    """Listings stay compact, exact ids return the full card, schemas carry no titles, analyses summarise."""
    import asyncio
    from editvideo import mcp_server as m
    from editvideo.effects import catalog
    listing = json.dumps(catalog(), separators=(",", ":"))
    assert len(listing) < 4000 and not any("caution" in row for row in catalog()["effects"])
    assert "caution" in catalog("tracking")["effects"][0]
    tools = asyncio.run(m.mcp.list_tools())
    def labels(o):
        if isinstance(o, dict):
            return any(k == "title" and isinstance(v, str) for k, v in o.items()) or any(labels(v) for v in o.values())
        return any(labels(v) for v in o) if isinstance(o, list) else False
    assert not any(labels(t.inputSchema) for t in tools)
    fs = next(t for t in tools if t.name == "editvideo_fetch_source").inputSchema
    assert set(fs["required"]) <= set(fs["properties"])  # a parameter literally named "title" survives slimming
    assert sum(len(t.description or "") for t in tools) < 40000
    assert max(len(t.description or "") for t in tools) < 900
    assert m.compact_result({"a": 0.123456789, "b": [1.0000049]}) == '{"a":0.1235,"b":[1.0]}'


def test_a_patch_answers_with_a_receipt_not_the_whole_timeline(workspace):
    from editvideo import mcp_server as m
    pid=planned();p=agent.read(pid)
    r=m.editvideo_patch_timeline(pid,p["revision"],[{"op":"upsert_overlay","overlay":{"id":"callout","start_frame":0,"end_frame":30,"text":"Chú thích"}}])
    assert r["revision"]==p["revision"]+1 and Path(r["history"]).is_file() and "timeline" not in r
    assert r["applied"]==[{"op":"upsert_overlay","target":"callout"}] and r["counts"]["shots"]==len(p["timeline"]["shots"])
    assert len(json.dumps(r))<1500
    full=m.editvideo_patch_timeline(pid,r["revision"],[{"op":"delete_overlay","id":"callout"}],return_timeline=True)
    assert "timeline" in full


def test_audits_see_the_cuts_a_recipe_makes_with_layers():
    from editvideo import review
    t={"shots":[{"id":"carrier","start_frame":0,"end_frame":300}],
       "layers":[{"id":f"s{i}","kind":"video","asset_id":f"a{i}","start_frame":i*60,"end_frame":i*60+60,"x":0,"y":0,"width":1,"height":1} for i in range(5)]
       +[{"id":"s2-proj","kind":"video","asset_id":"a2","start_frame":120,"end_frame":180,"x":0,"y":0,"width":1,"height":1},
         {"id":"inset","kind":"video","asset_id":"b","start_frame":30,"end_frame":90,"x":.6,"y":.6,"width":.3,"height":.3}]}
    shots=review.picture_shots(t)
    assert [s["start_frame"] for s in shots]==[0,60,120,180,240] and shots[2]["asset_id"]=="a2"
    assert review.picture_shots({"shots":t["shots"],"layers":[]})==t["shots"]


def test_reads_page_and_leave_schema_defaults_out(workspace):
    from editvideo import agent_interface
    pid=planned();p=agent.read(pid)
    t=p["timeline"];t["layers"]=[{"id":f"l{i}","kind":"text","text":"x","start_frame":0,"end_frame":30} for i in range(130)]
    agent.patch(pid,p["revision"],[{"op":"replace_timeline","timeline":t}])
    s=agent.summary(pid)
    assert s["counts"]["layers"]==130 and len(s["layers"])==60 and s["next_page"]==1
    assert len(agent.summary(pid,2)["layers"])==10 and agent.summary(pid,2)["next_page"] is None
    c=agent_interface.edit_context(pid,0,1)
    lay=c["layers"][0]
    assert "opacity" not in lay and "effects" not in lay and lay["text"]=="x" and "omitted" in c
