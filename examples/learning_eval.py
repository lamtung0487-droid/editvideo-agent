"""Retrieval regression for learning_library on the local reference library (read-only).

Usage (from the repo root; point EDITVIDEO_DATA at a copy when experimenting):
    python examples/learning_eval.py [--split dev|heldout|all] [--json out.json]

Gold labels are study-id prefixes judged from video titles (see learning_eval.json). Queries whose gold studies are
not in this library are skipped and counted, so the script runs on any machine but only measures this one's library.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import learning, store


def evaluate(queries, depth=20):
    present = {p.parent.name[6:14] for p in (store.DATA / "observations").glob("study-*/study.json")}
    rows, skipped = [], 0
    for item in queries:
        if not present.intersection(item["gold"]):
            skipped += 1
            continue
        t0 = time.perf_counter()
        top = learning.library(item["q"], kind="study", limit=5)
        ms = (time.perf_counter() - t0) * 1000
        deep = learning.library(item["q"], kind="study", limit=depth)
        ids = [it["id"][6:14] for it in deep["items"]]
        rank = next((i + 1 for i, x in enumerate(ids) if x in item["gold"]), None)
        rows.append({**item, "rank": rank, "total": deep["total"], "bytes": len(json.dumps(top, ensure_ascii=False)), "ms": round(ms, 1),
                     "top3": ids[:3]})
    return rows, skipped


def summarise(rows):
    if not rows:
        return {"n": 0}
    n = len(rows)
    med = lambda xs: sorted(xs)[len(xs) // 2]
    return {"n": n, "hit@1": round(sum(r["rank"] == 1 for r in rows) / n, 2), "hit@5": round(sum(bool(r["rank"] and r["rank"] <= 5) for r in rows) / n, 2),
            "mrr@20": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3), "zero_results": sum(r["total"] == 0 for r in rows),
            "median_bytes_limit5": med([r["bytes"] for r in rows]), "median_ms": med([r["ms"] for r in rows])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["dev", "heldout", "blind", "all"])
    ap.add_argument("--file", help="another query file of the same shape (default: learning_eval.json)")
    ap.add_argument("--no-meta", action="store_true", help="ablation: ignore title/channel/tags sidecars (gold labels come from titles)")
    ap.add_argument("--json", help="write per-query rows here")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.no_meta:
        learning._reference = lambda doc, *_: {}  # stored, sidecar and set-index metadata alike
    spec = json.loads(Path(args.file or Path(__file__).with_suffix(".json")).read_text(encoding="utf-8"))
    queries = [{"split": "blind", "lang": "vi", **q} for q in spec["queries"]]
    rows, skipped = evaluate([q for q in queries if args.split in ("all", q["split"])])
    groups = {}
    for r in rows:
        groups.setdefault(f"{r['split']}/{r['lang']}", []).append(r)
    out = {"data": str(store.DATA), "no_meta": args.no_meta, "skipped_missing_gold": skipped, "all": summarise(rows),
           **{k: summarise(v) for k, v in sorted(groups.items())},
           "misses": [{"q": r["q"], "split": r["split"], "rank": r["rank"], "total": r["total"], "top3": r["top3"], "gold": r["gold"]}
                      for r in rows if not (r["rank"] and r["rank"] <= 5)]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": out, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
