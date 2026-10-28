# EditVideo Agent

**Senses, hands and composition skills that let an AI edit video.** EditVideo Agent is an MCP server and CLI that gives
Claude, Codex or any MCP client the ability to *read* footage and audio, *edit* a revision-locked timeline or the
generated source code, *render* with Remotion or HyperFrames, and *check* the result with measurements, then iterate.

It is not a video editor for people and has no studio UI. The calling model makes the editorial and aesthetic decisions;
the runtime executes them deterministically and returns evidence (frames, crops, audio, numbers). There is no hidden
beauty score and no approval gate. Tiếng Việt: [README.vi.md](README.vi.md).

<!-- counts below come from scripts/repo_facts.py; tests/test_round6.py keeps them honest -->
**v0.8.0 + unreleased upgrades:** 137 MCP tools · 95 runnable effects (each with a before/after preview strip in both engines) +
7 tested combos · 18 layer kinds · 17 explainer recipes + 4 title recipes · 16 Vietnamese-complete font families ·
24 palettes · 17 style kits · 7 original LUTs plus a scene-referred colour graph.

## What the AI gets

| | Capabilities |
|---|---|
| **Senses** | Index and inspect video windows with real frames and audio blocks; crops with exact coordinate mapping; transcripts with word timing; audio events; music tempo, sections, hits and beat-fit; dialogue reading (speakers, pauses, filler candidates); edit-event profile (cuts, punch-ins, overlay pops); motion audit (static spans, judder, frozen endings, baked letterbox bars); colour statistics, scopes and shot consistency; planar and region tracking; reference-video study. |
| **Hands** | Revision-locked timeline patches (shots, layers, keyframes, transitions, audio); expressions as data — track modifiers (loop, inertia, wiggle), follow-through, **drivers** (link any track to another) and **two-bone IK**; masks, track mattes, chroma key, corner pin / screen replacement; native 3D scenes (glTF, lights, keyed spots, turntables); a **scene-referred colour graph** (camera log → ACEScct grading → Cineon print look under the output transform → display, with tracked windows); retime, stabilise, reframe; dialogue condensing with room tone; multicam sync and switching; aspect adaptation (9:16, 4:5, 1:1); optional GPU tools (SAM 2 masks, LaMa/ProPainter inpainting, local LTX footage). |
| **Composition skills** | Recipes that compile to editable layers: titles (impact cards, lockups, word cards, sound-first), explainers (diagrams, plots, unit grids, camera stages, documentary time cards, **evidence_3d**), professional edit recipes, ad and trailer planning/audits, direction cards, a design library with glyph-measured layout (including ink-measured line height for stacked Vietnamese diacritics). |
| **Learning from successful work** | `learn` (the `learnkit` package, host-independent): register finished works of any kind (video, image, audio, web page, text) with evidence of success against a baseline, measure them and their labelled parts with the same senses, compare winners with controls (effect sizes, confounders), keep evidence-gated blueprints, measure new work against them and log real outcomes. No model training. [Guide](docs/LEARNKIT.md). |
| **Craft memory** | `learning_library` retrieves prior studies and original craft lessons in Vietnamese/English with source windows; `remember_lesson` preserves purpose, use/avoid, steps, tool examples and demonstrations across sessions. Local retrieval, no model training or automatic example execution. [Workflow](docs/LEARNING_FROM_REFERENCES.md). |
| **Shorts and films** | `sequence_plan` selects inspected multi-source windows under a story budget and builds an editable project with audio; `film_world` maintains cast/prop state and per-shot generation packets. TikTok craft: `shortform_audit` reads the rendered short against platform UI zones and evidence-graded rules; pop captions, face-following reframes, talking-head selects. [Academic basis and workflow](docs/SHORTFORM_AND_FILM_RESEARCH.md). |
| **Self-review** | `audit_timeline`, `motion_audit`, `motion_quality`, `cut_audit` and an **independent reviewer agent** ([.claude/agents/editvideo-reviewer.md](.claude/agents/editvideo-reviewer.md), rubric in [docs/REVIEW_RUBRIC.md](docs/REVIEW_RUBRIC.md)) that judges renders and code from evidence and returns prioritised fixes. |

**Token economy.** Tool I/O is compacted at the protocol edge: compact JSON with rounded floats, slimmed schemas, no
duplicate structured copy, catalogs that list one-line rows until an exact id is asked for, handles (`track_id`,
manifests) instead of dumps, and image packets whose text carries only evidence ids. `EDITVIDEO_TOOLSET=compact`
exposes 7 entry tools for small-context hosts. See [docs/AI_ERGONOMICS.md](docs/AI_ERGONOMICS.md).

## Demo

Three short archive films built end to end by the system from public-domain material (720p previews; credits in
[docs/demo](docs/demo/README.md)):

| [![Leo thang](docs/demo/leo-thang.jpg)](docs/demo/leo-thang-720p.mp4) | [![Lan rộng](docs/demo/lan-rong.jpg)](docs/demo/lan-rong-720p.mp4) | [![Vịnh Bắc Bộ](docs/demo/vinh-bac-bo.jpg)](docs/demo/vinh-bac-bo-720p.mp4) |
|---|---|---|
| **Leo thang 1964-1968**: `archive_montage`, cuts tightening toward a hit | **Lan rộng 1965-1968**: `map_matte`, footage inside the land it was shot in | **Vịnh Bắc Bộ 1964**: `dossier`, the story's own documents shot close |

## Quick start

Requirements: Python 3.11+, Node.js 22+, FFmpeg/FFprobe on `PATH`. Windows is the tested platform; `setup.sh` covers the
core runtime on Linux/macOS (less tested). The full guide, with prerequisites, optional extras, client configuration
and troubleshooting, is [INSTALL.md](INSTALL.md) ([tiếng Việt](INSTALL.vi.md)); what the system is and its contracts:
[docs/SPEC.md](docs/SPEC.md).

```powershell
./setup.ps1            # core: Python venv, engines (npm ci), writes .mcp.json for this clone
./setup.ps1 -Vision    # + SAM 2 / depth / LaMa (CUDA, ~2.5 GB)
./setup.ps1 -Temporal  # + ProPainter and local LTX footage
./setup.ps1 -Voice     # + offline Vietnamese narration: Piper (GPL-3.0, separate process), vi_VN voice and Whisper small for word timing (~580 MB)
```

**Claude Code:** open the folder; `.mcp.json` (written by setup from [.mcp.example.json](.mcp.example.json)) registers the
server, and the skill lives in [.claude/skills/editvideo-agent](.claude/skills/editvideo-agent/SKILL.md).
**Codex:** skill in [.agents/skills/editvideo-agent](.agents/skills/editvideo-agent/SKILL.md); add the server:

```toml
[mcp_servers.editvideo]
command = '<repo>\.venv\Scripts\python.exe'
args = ['<repo>\run.py']
```

Start every session with `editvideo_bootstrap(task)` → `editvideo_discover_tools(query, include_schema=true)`. The
bootstrap reports the server version and tool count so a stale client connection is easy to spot. One-shot CLI:
`echo '{"tool":"editvideo_list_projects","arguments":{}}' | python run.py --cli`.

## Verify

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

About 600 tests run in about 15 minutes on CPU (FFmpeg, Node and the Remotion Chromium are needed; GPU model tests only
run with `EDITVIDEO_RUN_RUNTIME_TESTS=1`, and tests of optional extras skip when the extra is not installed). The suite
uses its own temporary data store. Synthetic ground-truth generators (`tests/synth_*.py`) check music, dialogue and
multicam analysis against known answers.

## Repository layout

```
editvideo/        MCP server, timeline model, perception, recipes, colour, audio, review
engines/          Remotion entry (AgentVideo.tsx), HyperFrames runtime, shared effects.js / scene3d.js
assets/           bundled fonts (with licences), original LUTs, vendored library previews
.claude/ .agents/ skills for Claude Code and Codex; the independent reviewer agent
docs/             guides (workflows, colour/3D, explainer kit, review rubric, research log)
examples/         reference build scripts (the sample films)
scripts/          setup helpers, atlas builders, repo facts
tests/            pytest suite and synthetic ground-truth generators
```

Runtime state (`data/`) and renders (`outputs/`) stay local and are git-ignored; publish chosen renders as release
assets.

## Documentation

[Install](INSTALL.md) · [Specification](docs/SPEC.md) · [Demo films](docs/demo/README.md) · [Pro workflows](docs/PRO_WORKFLOWS.md) · [Explainer kit](docs/EXPLAINER_KIT.md) · [Colour, depth & 3D](docs/COLOR_DEPTH_3D.md) ·
[Design library](docs/DESIGN_LIBRARY.md) · [Model integration](docs/MODEL_INTEGRATION.md) · [AI ergonomics](docs/AI_ERGONOMICS.md) ·
[Review rubric](docs/REVIEW_RUBRIC.md) · [Learning from references](docs/LEARNING_FROM_REFERENCES.md) · [Changelog](CHANGELOG.md) ·
[Contributing](CONTRIBUTING.md) · [Code of conduct](CODE_OF_CONDUCT.md) · [Security](SECURITY.md)

## Licence

EditVideo Agent is licensed under the [Apache License 2.0](LICENSE) ([NOTICE](NOTICE)). The engines, fonts, models,
data and media it uses keep their own licences: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Remotion is free for individuals and small companies, but larger for-profit organisations need a Remotion company
  licence. HyperFrames (Apache-2.0) is the open engine.
- ProPainter is non-commercial.
- Piper (GPL-3.0) runs as a separate process.
