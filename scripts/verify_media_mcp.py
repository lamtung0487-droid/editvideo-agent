"""Real MCP transport: submit, close client, reconnect and inspect inline masks."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from editvideo import store,media_tasks

async def main():
    params=StdioServerParameters(command=sys.executable,args=[str(store.ROOT/'run.py')],env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize();tools=await client.list_tools();assert len(tools.tools)==36
            result=await client.call_tool('editvideo_track_subject',{'request':{'path':str(store.ROOT/'outputs/subject-source.mp4'),'start':0,'end':1,'width':640,'prompts':[{'object_id':1,'box':[.32,.01,.55,.76]}]}})
            assert not result.isError,result
            task_id=result.structuredContent['id']
    # MCP owner has exited; independent media worker must finish anyway.
    start=time.monotonic()
    while True:
        state=media_tasks.get(task_id)
        if state['state'] in media_tasks.TERMINAL:
            assert state['state']=='completed',state;break
        assert time.monotonic()-start<180,state
        await asyncio.sleep(1)
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize()
            result=await client.call_tool('editvideo_read_subject',{'task_id':task_id,'object_id':1,'frames':[0,15,29]})
            assert not result.isError,result
            images=[c for c in result.content if c.type=='image'];assert len(images)==6
            schema=await client.read_resource('editvideo://schemas');assert 'GenerationRequest' in schema.contents[0].text
            state=await client.call_tool('editvideo_get_media_task',{'task_id':task_id});assert state.structuredContent['state']=='completed'
    report={'task_id':task_id,'mcp_tools':36,'survived_client_close':True,'inline_images':len(images),'new_schemas':True,'manifest':state.structuredContent['result']['manifest']}
    store.write_json(store.ROOT/'outputs/media-mcp-verification.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':asyncio.run(main())
