# Changelog

## Unreleased: fixes from the first community review (2026-10-28)

- FFmpeg:
  - The edit-event profile no longer mistakes a punch-in for a cut on FFmpeg 7.1. It finds more corners on soft
    frames, and the pixels must confirm a rescale.
  - Banding needs an FFmpeg with libvmaf. Ubuntu's and Debian's packages lack it; the delivery report now lists
    banding as `unmeasured` instead of failing.
  - On FFmpeg 7.1, slow-motion and deduped proxies no longer come out short: 7.1's MP4 muxer discards frames off a
    regular grid, so they now end on `fps=30`.
  - Under the MCP server, FFmpeg and other child processes no longer inherit the protocol's stdin. FFmpeg 6.1 read
    from it and hung `read_audio_events`.
  - Tested with FFmpeg 6.1, 7.1 and 8.1.
- Windows PowerShell 5.1:
  - `setup.ps1` no longer stops at pip's or npm's first stderr line when its output is redirected.
  - `.mcp.json` is written without a byte-order mark.
  - `start.ps1` parses on 5.1.
- Windows paths: `setup.ps1` stops early, with the fix, on a clone path too long for the 260-character limit. Render
  engines keep their browser profiles in a short temp folder.
- Docs: a documentation map by task ([docs/README.md](docs/README.md)) and a "Start here" path in the README.
- Demo: [EditVideo Agent in 89 seconds](docs/demo/README.md) (1080p on the `demo-reel-v2` release), the tools at
  work full frame, each chapter made by the MCP tools it names; chapter 07 shows the delivery gates measured on the
  reel itself.
- `motion_audit(gates=true)` runs the delivery gates over MCP.
- The text-contrast checks read translucent layers through their opacity, and read previews at their own size.
- The licence ledger counts works, not files: a render of another project carries that project's works
  (`ledger.register_project_render`), and `project_ledger` returns `works` and `work_count`. `project_credits`
  credits each work in the part of a render that is used.
- `snap_cuts_to_beats` reads the whole track's beat grid (the one `music_structure` returns) and returns its targets.
- `unit_grid` notes when its row does not fill its box; `audit_timeline` flags an SVG whose view box has another shape
  than its box; `map_matte` reports footage shown too small to read.

## The first public snapshot (2026-10-28)

EditVideo Agent gives an AI model senses, hands and composition skills for video, through MCP. This is the first
public snapshot; earlier development happened in a private repository.

What is in it:
- **Senses.** These read media and return evidence: indexing and inspection of video windows with real frames and
  audio, crops with exact coordinates, transcripts with word timing, music tempo, bars, sections and beat fit (Beat
  This! when installed), dialogue reading, motion, cut and colour audits, tracking, and reference-video study.
- **Hands.** Revision-locked timeline patches, expressions as data, masks and track mattes, 3D scenes, a
  scene-referred colour graph, retiming, multicam, aspect adaptation, and optional GPU tools.
- **Composition skills.** Recipes compile intent into editable layers: titles, explainers, history maps, documents,
  data stories, and three archive montage forms (`archive_montage`, `map_matte`, `dossier`). The sound recipes are
  measured on the render.
- **Checks.**
  - Delivery gates (legal levels, flashes, stills, blacks, banding, text holds and contrast).
  - A licence ledger with credits for every render.
  - A loudness master that keeps a film's dynamics.
  - An independent reviewer agent.
- **Token economy.** Results are compacted at the MCP edge, and a 7-tool compact toolset exists for small-context
  hosts.

See [README.md](README.md), [INSTALL.md](INSTALL.md) and [docs/SPEC.md](docs/SPEC.md). Licence: Apache-2.0.
