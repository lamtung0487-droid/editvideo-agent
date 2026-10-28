"""Real image-conditioned refinement over MCP, then inspect/verify artifacts."""
import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store,media_tasks,motion
from editvideo.media import FFMPEG,command,probe,sha256
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def refine(parent):
    original=media_tasks.get(parent)
    changes={'image_cond_noise_scale':.025,'reference_frames':[{
        'path':original['request']['reference_image'],
        'frame_index':original['request']['frame_count']-1,'strength':.85}]}
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/'run.py')],env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize()
            names={t.name for t in (await client.list_tools()).tools}
            assert {'editvideo_analyze_motion','editvideo_temporal_lens','editvideo_read_motion','editvideo_refine_footage'}<=names
            result=await client.call_tool('editvideo_refine_footage',{'task_id':parent,'changes':changes})
            if result.isError:raise RuntimeError(str(result.content))
            task=result.structuredContent
            store.write_json(store.ROOT/'outputs/image-refinement-task.json',{'task_id':task['id'],'parent':parent,'mcp_submit_then_client_closed':True})
            print(json.dumps({'task_id':task['id'],'state':task['state']}))


def verify(task_id,name):
    task=media_tasks.get(task_id)
    assert task['state']=='completed',task.get('error')
    result=task['result'];path=Path(result['artifacts']['video'])
    command([FFMPEG,'-v','error','-xerror','-i',path,'-f','null','-'])
    stream=next(s for s in probe(path)['streams'] if s['codec_type']=='video')
    assert int(stream['nb_frames'])==task['request']['frame_count']
    assert [stream['width'],stream['height']]==[task['request']['width'],task['request']['height']]
    out=store.ROOT/'outputs';video=out/f'{name}.mp4';shutil.copyfile(path,video)
    packet=motion.analyze(path,0,result['actual_duration'],sampling_fps=24,width=384,evidence_frames=6)
    # This is a numerical observation, not identity/beauty proof.
    from PIL import Image
    import numpy as np
    references=result['remote']['reference_frames'];root=media_tasks.folder(task_id)
    reference_error=[]
    for r in references:
        ref=np.asarray(Image.open(r['prepared_path']).convert('RGB')).astype(float)
        frame=np.asarray(Image.open(root/'generated-frames'/f"{r['frame_index']:06}.png").convert('RGB')).astype(float)
        reference_error.append({'frame_index':r['frame_index'],'rgb_mae':float(np.abs(ref-frame).mean()),
                                'strength':r['strength'],'note':'Aligned canvas only; not semantic identity or quality score'})
    report={'task_id':task_id,'output':str(video),'video_sha256':sha256(video),'decoder_errors':0,
            'actual_frames':int(stream['nb_frames']),'actual_fps':stream['r_frame_rate'],'request':task['request'],
            'generation':result['remote'],'motion':packet,'reference_observations':reference_error,
            'refinement':result.get('refinement'),'live_image_to_video_verified':True}
    store.write_json(out/f'{name}-verification.json',report)
    print(json.dumps({'output':str(video),'frames':report['actual_frames'],'cache':result['remote']['prompt_cache'],
                      'timings':result['remote']['stage_timings'],'reference_observations':reference_error}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--refine');parser.add_argument('--verify');parser.add_argument('--name',default='image-to-video-refined')
    args=parser.parse_args()
    if args.refine:asyncio.run(refine(args.refine))
    elif args.verify:verify(args.verify,args.name)
    else:parser.error('Choose --refine TASK or --verify TASK')
