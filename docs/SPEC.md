# EditVideo Agent: repository specification

This document says what the system is, its parts and their contracts, what it runs on, and how quality is kept. It
describes version 0.8.0 with the unreleased work listed at the top of [CHANGELOG.md](../CHANGELOG.md). For
installation see [INSTALL.md](../INSTALL.md).

## 1. Purpose and scope

EditVideo Agent gives an AI model **senses, hands and composition skills for video**:
- It reads footage, audio, music, images and documents, and returns evidence: real frames, crops, audio blocks,
  measurements.
- It edits a revision-locked timeline, or the generated Remotion/HyperFrames source code.
- It renders and then checks the result with audits, delivery gates and a licence ledger.

The calling model (Claude, Codex, or any MCP client) makes the editorial and aesthetic decisions. The runtime executes
them deterministically and reports what it measured.

**Non-goals:**
- It is not a video editor for people: there is no studio UI. An optional legacy browser view exists (`--studio`).
- It has no hidden beauty score and no approval gate: checks report findings, they do not judge taste.
- It does not train models. "Learning" is retrieval and measurement over registered works (`learnkit`).
- No media is redistributed: sources stay local with their licences recorded.

## 2. Users and entry points

| Entry point | For | How |
|---|---|---|
| MCP server (stdio) | Claude Code, Claude Desktop, Codex, any MCP host | `python run.py` (default), configured by `.mcp.json` |
| Compact toolset | small-context hosts | `EDITVIDEO_TOOLSET=compact`: 7 entry tools route to the rest (`editvideo_execute_tool`) |
| CLI, one call | scripts, CI | `echo '{"tool":"…","arguments":{…}}' \| python run.py --cli` |
| Python API | build scripts (`examples/`) | `import editvideo.mcp_server as m` and the modules below |
| Skills | the calling model | `.claude/skills/editvideo-agent/`, `.agents/skills/editvideo-agent/` |
| Reviewer agent | independent checks | `.claude/agents/editvideo-reviewer.md` (read-only, prioritised findings) |

A session starts with `editvideo_bootstrap(task)` and `editvideo_discover_tools(query, include_schema=true)`. The
full toolset has 137 tools; their descriptions stay under a 40,000-character total (enforced by a test).

## 3. Architecture

```
AI host ──MCP stdio──► editvideo.mcp_server ──► recipes (cinematic, montage, montage_forms, professional, explainer…)
                          │                         │ compile intent into timeline operations
                          │                         ▼
                          ├──► agent / models ──► revision-locked timeline (SQLite store + JSON on disk)
                          ├──► perception, music, review, ledger ──► evidence: frames, numbers, findings, licences
                          └──► jobs / renderer ──► engines/ (Remotion | HyperFrames, shared effects.js / scene3d.js)
                                                 └─► FFmpeg audio mix + master ──► MP4 + editable source ZIP + CREDITS
optional runtimes (separate processes): SAM 2, depth, LaMa/ProPainter, local LTX, Blender, MoGe-2, Piper, Beat This!
```

| Package / folder | Role |
|---|---|
| `editvideo/mcp_server.py` | Tool surface, result compaction (token economy), compact toolset |
| `editvideo/models.py` | Pydantic schema of projects, shots, layers (18 kinds), effects, masks, mattes, audio clips, mix |
| `editvideo/store.py`, `agent.py` | Data directory, SQLite catalog, revisions and patches, GPU admission |
| `editvideo/renderer.py`, `jobs.py` | Render jobs, audio mix (ducking, roles), loudness master, safe encode |
| `engines/` | `AgentVideo.tsx` (Remotion entry), HyperFrames runtime, `effects.js` and `scene3d.js` shared by both |
| `editvideo/perception.py`, `temporal.py`, `music.py`, `dialogue.py` | Senses: indexing, windows, tracking, beats and bars, phrases |
| `editvideo/cinematic.py`, `montage.py`, `montage_forms.py`, `professional.py`, `explainer.py` | Recipes that compile to editable layers |
| `editvideo/review.py`, `delivery.py`, `snapshot.py` | Audits, delivery gates, exact-frame snapshots |
| `editvideo/ledger.py`, `resources.py`, `pd_sources.py` | Licence ledger, credits, resource library, public-domain archive fetch |
| `editvideo/blender.py`, `terrain.py`, `archive3d.py` | Headless Blender scenes (terrain, maps), photos in 3D |
| `learnkit/` | Register finished works, measure, compare, evidence-gated blueprints |
| `assets/` | Bundled fonts (OFL/Apache), Tabler icons (MIT), original LUTs and previews |
| `examples/` | Reference build scripts of the sample films |
| `tests/` | pytest suite, synthetic ground-truth generators (`synth_*.py`) |

## 4. Core contracts

- **Revisions.** Every mutation names the revision it was read at. A stale revision is refused, so you reread and
  reapply your intent. Related edits go in one atomic batch.
- **Time.** The timeline runs at 30 fps.
  - Frame ranges are half-open `[start_frame, end_frame)`.
  - Effects and 3D poses use frames local to their layer.
  - Source offsets are in seconds.
  - Narration, dimensions and the timebase are locked through ordinary patches.
- **Evidence over claims.** A render is checked on its pixels and its sound: snapshots, audits, delivery gates,
  `montage.arc` / `form_arc`. Sampled or unseen intervals are reported as uncertain.
- **Honesty in the schema.** Archive keeps its own date and place. A reconstruction can never carry an archive
  date. Footage shown inside a country's shape must name a place that lies there. Generated imagery is labelled as
  illustration.
- **Rights.** Every asset goes into a licence ledger with its source, credit and class: public domain, permissive,
  attribution, share-alike, non-commercial, internal-only or unknown. `project_ledger(pid, use)` gives a verdict for
  internal, online or broadcast use, and renders carry `CREDITS.txt`.
- **Token economy.** Results are compacted at the MCP edge:
  - patches answer with receipts;
  - catalogs list compact rows until an exact id is asked for;
  - large data stays on disk behind a handle;
  - dry runs summarise long element and keyframe lists.

## 5. Data

| Location | Contents | Tracked by git |
|---|---|---|
| `EDITVIDEO_DATA` (default `./data`) | `studio.db`, `projects/<id>/` (assets, timeline, history, jobs, code), caches, observations, sound designs | no |
| `<installation>/data/models` | downloaded model weights (vision, temporal, voice, Beat This!) | no |
| `outputs/` | renders a person chose to keep | no |
| `assets/` | fonts, icons, LUTs, previews, with licences | yes |
| `docs/demo/` | 720p previews of the public-domain demo films | yes |

Environment variables:
- **Data, toolset, engines:** `EDITVIDEO_DATA`, `EDITVIDEO_TOOLSET` (`full`/`compact`), `EDITVIDEO_RENDER_CONCURRENCY`.
- **Optional runtimes:**
  - `EDITVIDEO_BLENDER` (path to blender.exe);
  - `EDITVIDEO_MOGE` (MoGe-2 folder);
  - `EDITVIDEO_BEAT_TRACKER` (`dp` to switch Beat This! off), `EDITVIDEO_BEAT_CHECKPOINT`, `EDITVIDEO_BEAT_DEVICE`.
- **Optional services:** `PEXELS_API_KEY`, `EDITVIDEO_RUNWAY_API_KEY`, `EDITVIDEO_COMFY_URL`,
  `EDITVIDEO_LLM_BASE_URL` / `_MODEL` / `_API_KEY`.

API keys are read from the environment only and never written into project files or render environments.

## 6. Platforms and requirements

| | Required | Optional |
|---|---|---|
| OS | Windows 10/11 (the tested platform; setup tested in Windows PowerShell 5.1; a clone path under ~100 characters unless long paths are enabled) | Linux (core runtime, run in CI), macOS (untested) |
| Python | 3.11 or newer | |
| Node.js | 22 or newer (Remotion and HyperFrames) | |
| FFmpeg / FFprobe | 6.1 or newer on `PATH` (tested with 6.1, 7.1 and 8.1) | a build with libvmaf, for the banding gate |
| GPU | none for the core | NVIDIA with CUDA 12.4 for the vision and temporal extras; tested on 12 GB VRAM |
| Disk | ~2 GB for the core install, plus space for the data directory | +2.5 GB vision, more for temporal/LTX; ~600 MB voice |
| 3D | | Blender 4.x/5.x (headless), MoGe-2 weights |

## 7. Quality

- **Tests:** `python -m pytest -q` runs about 600 tests in about 15 minutes on CPU. The tests use synthetic ground
  truth (music, dialogue, multicam), node-level runtime checks and exact snapshots. GPU and model tests only run with
  `EDITVIDEO_RUN_RUNTIME_TESTS=1`.
- **CI:** `.github/workflows/ci.yml` runs the suite on Windows and Ubuntu with Python 3.11 and Node 22.
- **Reviews:** after a build or a system change, the read-only reviewer agent returns P0/P1/P2 findings with evidence.
  Fixes are made at the system level: a recipe, default or check, never a one-off patch to one video.
- **Budgets:** tool descriptions stay under 40,000 characters, and a single description under 900 characters.

## 8. Licensing

The code is under [Apache-2.0](../LICENSE); see [NOTICE](../NOTICE). Third-party components keep their own licences;
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) lists them. Three components need attention:
- **Remotion** is not open source. Larger for-profit organisations need a Remotion company licence to render with it.
  HyperFrames (Apache-2.0) is the alternative engine.
- **ProPainter** (optional) is non-commercial.
- **Piper** (optional) is GPL-3.0. It runs only as a separate process.

## 9. Versioning

The project uses semantic versioning (`pyproject.toml`). Unreleased work is listed at the top of the changelog until a
release tags it. Breaking changes to tool names, schemas or timeline contracts are called out in the changelog.
