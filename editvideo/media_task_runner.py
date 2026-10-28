"""Isolated worker entry point; no MCP stdout protocol in this process."""
import sys
from .media_tasks import run,folder

if __name__ == "__main__":
    task_id=sys.argv[1]
    # WMI launch has no inherited stdout/stderr handles. Never print to MCP.
    with (folder(task_id)/"worker.log").open("a",encoding="utf-8",buffering=1) as log:
        sys.stdout=sys.stderr=log
        run(task_id)
