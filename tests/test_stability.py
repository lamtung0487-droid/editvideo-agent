"""Stability contracts from the system audit of 2026-10-27: one GPU slot, a crashed Blender noticed, safe encodes."""
import subprocess
import sys
import time
from pathlib import Path
import pytest
from editvideo import store


def test_the_gpu_slot_is_re_entrant_in_its_thread_and_exclusive_across_processes(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    outer = store.acquire_gpu()
    with store.gpu_admission():  # a task that renders with Blender inside it does not wait for itself
        pass
    code = "import sys;sys.path.insert(0,r'%s');from pathlib import Path;from editvideo import store;store.DATA=Path(r'%s');" \
           "from filelock import FileLock,Timeout\ntry:\n FileLock(str(store.DATA/'media-heavy.lock')).acquire(timeout=.3);print('got')\nexcept Timeout:print('busy')"
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert subprocess.run([sys.executable, "-c", code % (root, tmp_path)], capture_output=True, text=True).stdout.strip() == "busy"
    outer.release()
    assert subprocess.run([sys.executable, "-c", code % (root, tmp_path)], capture_output=True, text=True).stdout.strip() == "got"


def test_a_busy_gpu_slot_names_its_holder_and_a_limited_wait_gives_up(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(store, "DATA", tmp_path)
    slot = store.acquire_gpu(what="Blender terrain_shot")
    assert store.gpu_holder()["what"] == "Blender terrain_shot" and store.gpu_holder()["pid"] == os.getpid()
    code = "import sys;sys.path.insert(0,r'%s');from pathlib import Path;from editvideo import store;store.DATA=Path(r'%s')\n" \
           "try:\n store.acquire_gpu(what='MoGe',wait_s=1)\nexcept TimeoutError as e:print(e)"
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-c", code % (root, tmp_path)], capture_output=True, text=True).stdout
    assert "busy for 1 s" in out and "Blender terrain_shot" in out
    slot.release()


def test_a_blender_that_died_under_the_launcher_fails_fast(tmp_path):
    from editvideo import blender
    job = tmp_path / "job"
    job.mkdir()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (job / "blender.pid").write_text(str(dead.pid))
    proc = subprocess.Popen([sys.executable, "-c", "pass"])  # the launcher returns at once
    t0 = time.time()
    with pytest.raises(RuntimeError, match="exited without finishing"):
        blender._watch(job, job / "done.json", proc, True, 3600, .2, None)
    assert time.time() - t0 < 30
