import uuid
from pathlib import Path
from . import store
from .media import sha256


def source_path(pid, engine, relative_path):
    if engine not in ("remotion","hyperframes"):
        raise ValueError("engine: remotion|hyperframes")
    root = store.folder(pid)/"code"/engine
    store.get_project(pid)
    if not root.exists():
        raise ValueError("Export code first")
    path = (root/relative_path).resolve()
    if not path.is_relative_to(root.resolve()) or "node_modules" in path.parts or path.name=="source-meta.json":
        raise ValueError("Source path must stay inside code directory")
    if path.suffix not in (".tsx",".ts",".jsx",".js",".mjs",".cjs",".html",".css",".json",".svg"):
        raise ValueError("Text source extensions only")
    return path


def read_source(pid,engine,relative_path):
    path = source_path(pid,engine,relative_path)
    if path.stat().st_size>2*1024*1024:
        raise ValueError("Source file exceeds 2MB")
    return {"path":str(path),"sha256":sha256(path),"content":path.read_text(encoding="utf-8")}


def write_source(pid,engine,relative_path,content,expected_sha256=None):
    path = source_path(pid,engine,relative_path)
    if len(content.encode("utf-8"))>2*1024*1024:
        raise ValueError("Source exceeds 2MB")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if store.busy(db,pid):
            raise ValueError("Project busy; wait before editing source")
        actual = sha256(path) if path.exists() else None
        if actual != expected_sha256:
            raise ValueError("Source hash conflict: read current source before editing")
        history = store.folder(pid)/"code-history"/(str(uuid.uuid4())+path.suffix)
        history.parent.mkdir(exist_ok=True)
        if path.exists():
            history.write_bytes(path.read_bytes())
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp = path.with_name(path.name+".tmp")
        tmp.write_text(content,encoding="utf-8")
        tmp.replace(path)
    return {"path":str(path),"sha256":sha256(path),"previous":str(history) if actual else None}
