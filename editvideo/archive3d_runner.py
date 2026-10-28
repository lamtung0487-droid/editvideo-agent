"""Subprocess for editvideo.archive3d: MoGe-2 geometry of one photograph, written to an .npz and the process ends, so
the 1.3 GB model and its CUDA memory never stay in the editor. Usage: archive3d_runner.py <image> <out.npz> <moge root>"""
import sys
from pathlib import Path

image, out, root = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(root / "code"))  # vendored MoGe and utils3d_moge (MIT); never the working directory
import numpy as np
import torch
from PIL import Image
from moge.model.v2 import MoGeModel

dev = "cuda" if torch.cuda.is_available() else "cpu"
model = MoGeModel.from_pretrained(str(root / "moge-2-vitl-normal" / "model.pt")).to(dev).eval()
img = np.asarray(Image.open(image).convert("RGB"), np.float32) / 255.0
with torch.no_grad():
    o = model.infer(torch.tensor(img, device=dev).permute(2, 0, 1), use_fp16=dev == "cuda")
get = lambda k: o[k].float().cpu().numpy() if k in o and o[k] is not None else None
np.savez_compressed(out, points=get("points").astype(np.float32), depth=get("depth").astype(np.float32), mask=get("mask").astype(bool),
                    intrinsics=get("intrinsics").astype(np.float32), **({"normal": get("normal").astype(np.float16)} if "normal" in o else {}),
                    size=np.array(img.shape[:2]), device=np.array(dev))
print("ok", out)
