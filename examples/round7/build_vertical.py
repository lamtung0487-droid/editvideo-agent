"""Round-7 real build D: the footage documentary (build A) re-cut for 9:16 with adapt_aspect, then audited.
Usage: python examples/round7/build_vertical.py [--fresh]  (after build_doc.py; --fresh adapts again into a new project) → prints the new project id, clamped layers, findings"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from editvideo import mcp_server as m, store
store.initialize(recover=False)
STATE = ROOT / "data" / "films" / "r7-vertical.json"
DOC = json.loads((ROOT / "data" / "films" / "r7-doc.json").read_text())["pid"]


def main():
    if STATE.exists() and "--fresh" not in sys.argv:
        pid = json.loads(STATE.read_text())["pid"]
        r = {"project_id": pid, "reused": True}
    else:
        r = m.editvideo_adapt_aspect(DOC, "vertical", "Artemis · tư liệu dọc")
        pid = r.get("project_id") or r.get("id")
        STATE.write_text(json.dumps({"pid": pid}))
    au = [(x["code"], x.get("where")) for x in m.editvideo_audit_timeline(pid)["findings"] if x["level"] != "info"]
    print(json.dumps({"pid": pid, "adapt": {k: v for k, v in r.items() if k != "project_id"}, "audit": au}, ensure_ascii=False)[:4000])
    m.editvideo_export_code(pid, engine="remotion", overwrite=True)


if __name__ == "__main__":
    main()
