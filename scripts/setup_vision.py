"""Download pinned public model artifacts; heavy backend installation is separate."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from editvideo import store
from editvideo.media import sha256

MODELS={
 "sam2.1_hiera_tiny.pt":("https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt",None),
 "big-lama.pt":("https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt","e3aa4aaa15225a33ec84f9f4bc47e500")}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--models",nargs="+",choices=MODELS,default=list(MODELS));args=parser.parse_args()
    root=store.DATA/"models";root.mkdir(parents=True,exist_ok=True)
    results=[]
    for name in args.models:
        url,md5=MODELS[name];path=root/name
        if not path.exists():
            temp=path.with_suffix(".download")
            with httpx.stream("GET",url,follow_redirects=True,timeout=120) as response:
                response.raise_for_status()
                with temp.open("wb") as f:
                    for block in response.iter_bytes(1024*1024):f.write(block)
            if md5 and hashlib.md5(temp.read_bytes()).hexdigest()!=md5:
                temp.unlink();raise ValueError("Model checksum mismatch")
            temp.replace(path)
        if md5 and hashlib.md5(path.read_bytes()).hexdigest()!=md5:raise ValueError("Cached model checksum mismatch")
        results.append({"name":name,"path":str(path),"sha256":sha256(path),"bytes":path.stat().st_size,"source":url})
        print(name+" ready",flush=True)
    store.write_json(root/"vision-models.json",results)

if __name__=="__main__":main()
