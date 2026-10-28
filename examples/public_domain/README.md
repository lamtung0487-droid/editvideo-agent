# Public-domain examples

Build scripts that anyone can run on the core install. Their sources are public domain and are fetched by the script
itself, with each file's licence read before it is used.

| Script | Film | Sources |
|---|---|---|
| `dossier_tonkin.py` | *Vịnh Bắc Bộ 1964*: a `dossier` montage (19.5 s) | five US government documents and photographs of August 1964, NARA scans on Wikimedia Commons |

```powershell
.venv\Scripts\python examples\public_domain\dossier_tonkin.py --render
```

The script:
1. downloads the scans into `<EDITVIDEO_DATA>/sources/commons/tonkin-1964`, keeping each file's Commons record;
2. registers each scan in the licence ledger;
3. composes the dossier and its sound;
4. with `--render`, renders to `outputs/demo/vinh-bac-bo.mp4` and prints the delivery gates, `form_arc` and the
   ledger's verdict for online use (expected: clear).

The other two demo films in [docs/demo](../../docs/demo/README.md) are *Leo thang* (`archive_montage`) and *Lan rộng*
(`map_matte`). Their footage comes from US Navy, Marine Corps and Air Force films in the National Archives. Their
build scripts read a clip pool cut from those reels, and they will be added here once the fetch from the National
Archives catalog (`editvideo.pd_sources`) works again: its search route answered with a web page instead of JSON on
2026-10-28. The recipes themselves are documented in [docs/FAST_AI_WORKFLOW.md](../../docs/FAST_AI_WORKFLOW.md).
