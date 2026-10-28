# AI ergonomics: senses, hands and skills at the lowest context cost

EditVideo is a capability layer for an AI editor, not an editor for people. The model sees nothing except what tools
return, so every tool is designed around two costs: **context tokens** (what the model must read) and **round trips**
(how many calls an intent needs).

| Layer | What the AI gets | Examples |
|---|---|---|
| Senses (eyes/ears) | measurements, one contact sheet, short evidence clips | `index_video`, `inspect_window`, `crop_detail`, `analyze_motion`, `read_audio_events`, `music_structure`, `color_scopes`, `study_video`, `review_frames` |
| Hands | revision-safe patches, recipes that compile intent into layers, renders, durable media tasks | `patch_timeline`, `compose_*`, `screen_replace`, `snap_cuts_to_beats`, `music_fit`, `process_color`, `submit_job` |
| Skills | measured craft rules baked into recipes and audits | `title_card` presets, `trailer_plan`/`trailer_audit`, `audit_timeline`, `cut_audit`, `motion_audit`, docs/PRO_WORKFLOWS.md |

## Rules every tool follows

1. **Summaries by default, detail on demand.** Listings return one compact row per item (what it is for, ranges,
   defaults); the full card comes back for an exact id (`effect_catalog`, `design_catalog`, `cinematic_catalog`).
   Analyses return decisions and counts; full arrays go to disk with a path (`music_structure` → `full_path`,
   `study_video` → `study.json`).
2. **Handles, not payloads.** Large per-frame data stays on disk and is passed by id: `track_plane` returns a
   `track_id` that `screen_replace` accepts, so per-frame corners never travel through the model; `read_dialogue`,
   `event_profile` and `condense_dialogue` keep regions, events and time maps in manifests; `animate` writes keyframes
   and returns counts and beat frames.
3. **One image, labelled.** `snapshot_code` returns one contact sheet; `review_frames` returns one overlay per frame.
4. **Intent in, geometry out.** Recipes compute positions, timings, sizes (FreeType metrics), homographies and beat
   grids; the AI states the intent (`preset`, `hit_frame`, `use: hits`) instead of placing hundreds of values.
5. **Dry runs carry the audit.** `compose_*` with `dry_run` return the layers plus only the findings that touch them.
6. **Measured, not judged.** Tools return numbers with thresholds and a next step, never a beauty score.

## Protocol-edge economy (editvideo/mcp_server.py `economize_tools`)

- Results are one compact JSON text block (no indentation), floats rounded to 4 decimals (0.0001 of a normalised
  coordinate is 0.2 px at 1920), and no second structured copy. Set `EDITVIDEO_STRUCTURED=1` for programmatic clients
  that need MCP `structuredContent`.
- Input schemas drop per-property titles and collapse `anyOf [X, null]` to X (defaults stay visible; validation still
  uses the Python signature).
- Tool descriptions say when to use the tool, its key parameters and its limits; craft detail lives in catalogs/docs.

Measured on this repository (characters on the wire; ~4 characters per token):

| Item | Before | After |
|---|---|---|
| Tool surface (descriptions + schemas) | ~20.4k tokens for 104 tools | ~17.0k tokens for 120 tools (round 6; ~21.5k with names and annotations) |
| `inspect_window` text (8 frames) | 5.6-6.9k chars (guide + paths + hashes) | 1.7k (evidence ids; paths in the manifest) |
| `list_projects` (20) | 8.9k | 3.6k (one row each) |
| `resources()` / `style_directions()` | 11.7k / 8.9k | one row per entry (full card for an exact id) |
| `effect_catalog()` | 21.9k chars + structured copy | 2.7k |
| `design_catalog()` | ~18k + copy | 4.0k |
| `cinematic_catalog()` | ~13k + copy | 4.1k |
| `music_structure` (81 s song) | 10.4k + copy | 3.0k (+ full_path) |
| `read_project` | 9.8k + copy | 5.3k |
| `audit_timeline` | 5.4k + copy | 3.7k |

Re-measured on 2026-10-27 (a 70 s montage of 119 layers; a 29-min film of 477 layers), after the token audit:

| Item | Before | After |
|---|---|---|
| `patch_timeline` / `set_captions` reply | the whole timeline: 132.6k (montage), 1.41M (29-min film) | a receipt: revision, history, each op and its target, counts (< 1.5k); `return_timeline=true` for the old reply |
| `read_project` summary | 24.2k; 160.5k on the long film | counts, then shots/layers/used assets 60 a page (`page`): 16.8k |
| `read_edit_context` 0-8 s / 40-55 s | 33.7k / 53.3k | 23.9k / 15.3k: fields at their schema default are left out |
| `read_narration` page 1 / later pages | 78.0k / every cue and the same beats again | 44.2k / 14.5k: words as `[word, start_s, end_s]`, the cues they fall in, beats paged by `beat_offset` (they had been paged by the word offset and came back empty) |
| `inspect_window`, `aesthetic_packet` | ~340k-430k base64 audio by default | audio only for a client that declares it at `bootstrap` (`openai`); measured `audio_energy` otherwise |

Response-size tests sit in tests/test_agent.py. cut_audit and motion_audit read the picture's cuts from full-frame video
layers when a recipe builds the film on one carrier shot (`review.picture_shots`): they had reported a 48-cut montage
as one shot with no findings.

## Hosts

- Claude Code defers MCP tool schemas behind tool search, so the full toolset (`EDITVIDEO_TOOLSET=full`, default) costs
  only names until a tool is loaded. Hosts that load every schema up front should use `EDITVIDEO_TOOLSET=compact`
  (7 tools: `bootstrap`, `discover_tools`, `execute_tool`, ...), which dispatches to the same registry.
- In-process Python (`from editvideo import mcp_server as m; m.editvideo_x(...)`) returns full Python objects; only the
  MCP edge is compacted.

## When adding a tool

- Return what the model needs to decide the next step; write anything else to disk and return its path or id.
- Keep the description to: purpose, when to use it, key parameters, limits (≈ 400 characters).
- Prefer one call that does the geometry over many calls that place values.
- Add a test that pins the contract (fields present, size bound where it matters).

## Round 6 additions

- Evidence packets (`inspect_window`, `crop_detail`, previews) send images as image blocks and keep only evidence ids,
  timestamps and sizes in the text; the director guide lives in the prompts, not in every result.
- Browsing calls return one compact row per item (`list_projects`, `resources`, `style_directions`, `discover_tools`);
  an exact id returns the full record.
- The MCP edge emits valid JSON only (NaN → null, numpy scalars → numbers) and never advertises `default: null` on a
  non-null schema type.
- `bootstrap` reports `server.version` and `server.tools`: a client that sees fewer tools is connected to a stale server.
- Read-only tools carry only the hints that mean something (`readOnlyHint`, `openWorldHint`).

