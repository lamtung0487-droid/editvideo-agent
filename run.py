import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EditVideo Agent — MCP video perception and code rendering")
    parser.add_argument("--studio",action="store_true",help="Optional legacy browser interface")
    parser.add_argument("--cli",action="store_true",help="Read one tool call as JSON from stdin")
    parser.add_argument("--port",type=int,default=8765)
    args = parser.parse_args()
    if args.studio:
        import uvicorn
        uvicorn.run("editvideo.server:app",host="127.0.0.1",port=args.port,workers=1)
    elif args.cli:
        import json, sys
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        from editvideo import mcp_server, store
        store.initialize(recover=False)
        body=json.load(sys.stdin)
        name=body["tool"]
        if not name.startswith("editvideo_") or not callable(getattr(mcp_server,name,None)):
            raise ValueError("Unknown tool")
        output=getattr(mcp_server,name)(**body.get("arguments",{}))
        import inspect,asyncio
        if inspect.isawaitable(output):output=asyncio.run(output)
        if name=="editvideo_submit_job":
            mcp_server.worker.run(output["id"])
            output=mcp_server.editvideo_get_job(output["id"])
        print(json.dumps(output,ensure_ascii=False,default=lambda x:x.model_dump()))
    else:
        from editvideo.mcp_server import main
        main()
