"""Create/render an editable before/after comparison through real MCP tools."""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store,media_tasks
from editvideo.media import sha256,command,FFMPEG,probe
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

BEFORE='8368d415-929a-416b-a0ab-9565f715bb07'
AFTER='f287193b-2ed6-4a71-90ce-330653dc5b87'

async def main():
    before,after=media_tasks.get(BEFORE),media_tasks.get(AFTER)
    assert before['state']==after['state']=='completed'
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/'run.py')],env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize()
            async def call(name,args):
                r=await client.call_tool('editvideo_'+name,args)
                if r.isError:raise RuntimeError(str(r.content))
                return r.structuredContent or r.content
            p=await call('project_from_video',{'path':after['result']['artifacts']['video'],'title':'Từ ảnh tham chiếu đến cảnh video','engine':'remotion','profile':'landscape'})
            pid=p['id'];voice=store.folder(pid)/'plan/voice.wav';voice_hash=sha256(voice);ids={}
            for name,tid in [('before',BEFORE),('after',AFTER)]:
                p=await call('read_project',{'project_id':pid})
                a=await call('attach_media_result',{'task_id':tid,'project_id':pid,'base_revision':p['revision'],'tags':name,'role':'reconstruction'})
                ids[name]=a['asset']['id']
            for name,r in zip(['reference_start','reference_end'],after['result']['remote']['reference_frames']):
                p=await call('read_project',{'project_id':pid})
                a=await call('import_media',{'project_id':pid,'base_revision':p['revision'],'preserve_plan':True,'path':r['prepared_path'],'tags':name,'role':'reconstruction'})
                ids[name]=a['asset']['id']
            p=await call('read_project',{'project_id':pid})
            ops=[{'op':'update_shot','shot_id':p['timeline']['shots'][0]['id'],'changes':{'asset_id':ids['after'],'motion':'hold','role':'reconstruction'}}]
            ops += [{'op':'upsert_layer','layer':{'id':'reference-'+name,'kind':'image' if name.startswith('reference') else 'video','asset_id':aid,'start_frame':0,'end_frame':p['timeline']['total_frames'],'opacity':0}} for name,aid in ids.items()]
            await call('patch_timeline',{'project_id':pid,'base_revision':p['revision'],'operations':ops})
            await call('export_code',{'project_id':pid,'engine':'remotion'})
            source=await call('read_code',{'project_id':pid,'engine':'remotion','relative_path':'index.tsx'})
            template=(store.ROOT/'scripts/image_director_demo.tsx').read_text(encoding='utf-8').replace('__ASSETS__',json.dumps(ids))
            await call('write_code',{'project_id':pid,'engine':'remotion','relative_path':'index.tsx','expected_sha256':source['sha256'],'content':template})
            snapshots=await call('snapshot_code',{'project_id':pid,'engine':'remotion','frames':[0,45,90]})
            j=await call('submit_job',{'project_id':pid,'kind':'final'});print('render',j['id'],flush=True)
            while True:
                job=await call('get_job',{'job_id':j['id']})
                if job['state'] not in ('queued','running'):break
                await asyncio.sleep(3)
            assert job['state']=='completed',job['error']
            out=store.ROOT/'outputs'
            for artifact in job['artifacts']:
                names={'final.mp4':'image-to-video-comparison.mp4','delivery.zip':'image-to-video-comparison.zip'}
                if artifact['name'] in names:shutil.copyfile(artifact['path'],out/names[artifact['name']])
            assert sha256(voice)==voice_hash
            dest=out/'image-to-video-comparison.mp4';command([FFMPEG,'-v','error','-xerror','-i',dest,'-f','null','-'])
            report={'project_id':pid,'job_id':j['id'],'assets':ids,'before_task':BEFORE,'after_task':AFTER,
                    'snapshots':json.loads(snapshots[0].text),'voice_sha256_before':voice_hash,'voice_sha256_after':sha256(voice),
                    'video':str(dest),'video_sha256':sha256(dest),'streams':probe(dest)['streams'],'decoder_errors':0,
                    'source_zip':str(out/'image-to-video-comparison.zip'),'notes':'Silent comparison, native source512x320/24fps inside FullHD30fps composition; not native FullHD model generation.'}
            store.write_json(out/'image-director-demo.json',report)
            print(json.dumps({'project_id':pid,'video':str(dest)}),flush=True)

if __name__=='__main__':asyncio.run(main())
