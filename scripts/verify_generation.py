"""A real local generation request over MCP, durable across client shutdown."""
import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store,media_tasks
from editvideo.media import FFMPEG,command,probe,sha256
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

REQUEST={"provider":"local_ltx","prompt":"A cinematic documentary shot of a peaceful lush green forest at sunrise. Warm golden sunlight shines through tall trees and illuminates delicate green leaves in the foreground. A light breeze makes the leaves gently sway. Soft morning haze creates depth between the trees. The camera slowly glides forward with smooth stable motion. Natural realistic colors, subtle movement, crisp plant details, calm atmosphere. Continuous single shot.","width":768,"height":448,"fps":24,"duration":5,"frame_count":121,"seed":1729,"timeout":3600}

async def submit():
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/'run.py')],env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize();r=await client.call_tool('editvideo_generate_footage',{'request':REQUEST})
            if r.isError:raise RuntimeError(str(r.content))
            task=r.structuredContent;store.write_json(store.ROOT/'outputs/local-generation-task.json',task);return task['id']

def main():
    p=argparse.ArgumentParser();p.add_argument('--resume-task');p.add_argument('--wait-models',action='store_true');args=p.parse_args()
    if args.wait_models:
        from editvideo.local_footage import ready
        print('Waiting for cached model setup',flush=True);start=time.monotonic()
        while not ready():
            if time.monotonic()-start>3600:raise TimeoutError('Model setup did not finish')
            time.sleep(5)
    task_id=args.resume_task or asyncio.run(submit());print('task',task_id,flush=True)
    started=time.monotonic();last=None
    while True:
        r=media_tasks.get(task_id)
        if r['message']!=last:print(r['state'],r['message'],flush=True);last=r['message']
        if r['state'] in media_tasks.TERMINAL:break
        if time.monotonic()-started>4000:raise TimeoutError('Generation worker did not finish')
        time.sleep(5)
    assert r['state']=='completed',r['error']
    path=Path(r['result']['artifacts']['video']);command([FFMPEG,'-v','error','-xerror','-i',path,'-f','null','-'])
    shutil.copyfile(path,store.ROOT/'outputs/ai-generated-forest.mp4')
    info=probe(path);stream=next(s for s in info['streams'] if s['codec_type']=='video')
    assert int(stream['nb_frames'])==r['request']['frame_count']
    assert stream['r_frame_rate']==f"{r['request']['fps']}/1"
    report={'task_id':task_id,'provider':'local_ltx','live_generation_verified':True,'mcp_submit_then_client_closed':True,'request':r['request'],'result':r['result'],'decoder_errors':0,'actual_dimensions':[stream['width'],stream['height']],'sha256':sha256(path)}
    setup=store.read_json(store.DATA/'models/temporal-models.json')['ltx']
    report['model_setup']={k:setup[k] for k in ('model_revision','text_encoder_revision','fp8_revision','config_revision')}
    report['actual_frames']=int(stream['nb_frames'])
    store.write_json(store.ROOT/'outputs/local-generation-verification.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':main()
