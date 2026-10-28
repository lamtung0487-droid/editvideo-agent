# Changelog

## Unreleased: the first public snapshot (2026-10-28)

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
