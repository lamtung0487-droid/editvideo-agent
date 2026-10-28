"""Explicit install of pinned100MB Depth Anything V2 Small, no runtime downloads."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store
from editvideo.depth import install
store.initialize(recover=False)
print(install(allow_download='--download' in sys.argv))
