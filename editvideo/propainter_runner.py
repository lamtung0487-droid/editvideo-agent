"""Run the upstream CLI in an isolated process, using preinstalled artifacts only."""
import os
import runpy
import sys
from pathlib import Path

def main():
    args=sys.argv[1:];i=args.index("--repository");repo=Path(args[i+1]).resolve(strict=True);del args[i:i+2]
    for name in ("raft-things.pth","recurrent_flow_completion.pth","ProPainter.pth"):
        if not (repo/"weights"/name).is_file():raise ValueError("Missing cached ProPainter weight: "+name)
    sys.path.insert(0,str(repo));os.chdir(repo)
    sys.argv=[str(repo/"inference_propainter.py"),*args]
    runpy.run_path(str(repo/"inference_propainter.py"),run_name="__main__")

if __name__=="__main__":main()
