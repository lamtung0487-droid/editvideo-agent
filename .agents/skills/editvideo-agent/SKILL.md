---
name: editvideo-agent
description: Creates and edits videos through the local EditVideo MCP server (Remotion and HyperFrames runtimes) - narrated and science explainers (measured distances, diagrams, plots, unit grids, particle effects), footage edits, cinematic treatments, 20 creative style directions, storyboards, beat-synced cutting, stabilization and vertical reframing, globe/map/3D scenes, captions, color, depth, subject tracking, plus evidence-based review (timeline audit, glyph-level frame review, motion and cut audits, credits traced from licences). Use when the user asks to make, edit, restyle, review or render a video, or mentions Remotion, HyperFrames, motion graphics, editing, transitions, titles, color grading, video style or footage.
---

# EditVideo Agent

Tools live on MCP server `editvideo` (e.g. `editvideo:editvideo_audit_timeline`). Start with `editvideo_bootstrap(task, project_id?)`; it routes to the right tools and guide. `editvideo_discover_tools(query, include_schema=true)` gives exact schemas. You direct story and taste from real pixels and audio; the runtime executes edits and returns measurements. No hidden beauty score or approval gate.

## Make a video (copy this checklist)

```
- [ ] 0. Meaning: read_narration/workbench. Custom dialogue with empty script/cues needs bind_narrative (actual clip IDs/bounds); never assume silence or invent word timing. direct_scene(inspect=true,listen=true) supplies real pixels/audio with the narrative.
- [ ] 1. Storyboard: editvideo_storyboard(storyboard=...) — message, arc, audience, mood, direction_id, breather, negative list, callback
- [ ] 2. Style: editvideo_style_directions → editvideo_apply_direction (restyle=true once layers exist)
- [ ] 3. Hero technique: editvideo_cinematic_catalog → editvideo_compose_cinematic(dry_run=true), read its audit, then apply
- [ ] 4. Cut: transitions from the direction's vocabulary; music → music_structure (bars, sections, hits, pulse) → snap_cuts_to_beats (use priority/hits/phrases/against) and music_fit to length; footage fixes → stabilize/reframe/retime
- [ ] 5. Validate: editvideo_audit_timeline → fix likely_problem; snapshot_code / review_frames on the frames it names
- [ ] 6. Render, then motion_audit + cut_audit + storyboard(check=true, render_path) → fix and re-measure the same frames
- [ ] 7. editvideo_project_credits → deliver MP4 + source ZIP and state limitations
```

Repeat 5–6 until no unexplained likely_problem remains. Stills cannot show judder; renders can.

For a scene with weak communication, use direct_scene to state the viewer question and compare a motivated arrangement. Three patterns compile to editable layers; apply the returned handle with patch_timeline(direction_plan=...). Inspect the moving result. Passing software tests and counting effects are not evidence of professional storytelling. Twelve craft patterns: assets/craft/directing.json; workflow: docs/FAST_AI_WORKFLOW.md.

## Routes (read only what the task needs)

- Fast scene work and final fixes: `workbench(project_id,start,end,purpose)` gives compact context, matching craft cards and inspect frames; `recipe` returns one schema. `finish_video` repairs a bounded layer-edit region from a verified base, copies unchanged picture, packages selectable captions and measures final AAC. `render_3d` exposes cached Blender terrain/globe jobs with cheap still previews. Read [FAST_AI_WORKFLOW](../../../docs/FAST_AI_WORKFLOW.md). Use a technique to explain the idea; do not add effects merely to exercise the inventory.
- TikTok/Reels/Shorts craft: `professional_toolkit(platform)` templates, UI zones and rule evidence → talking head = `reframe_footage` auto_focus faces → `condense_dialogue` windows + transcript → `punch_in` ladder → `word_captions` word_animation pop + outline → `design_sound` beat → `audio_finish` → render → `shortform_audit` (UI overlay sheet, evidence-graded findings) · PRO_WORKFLOWS §24
- Many sources + effects by genre (velocity, wildlife, food, city): `rank_clips` (windows, action peaks, directions, cross-clip match cuts, silent clips, contact sheet; inspect it, a peak is movement not meaning) → `retime_footage` peaks (source s) → cuts on beats/bars → patch `freeze_frame` / `apply_combo`, `compose_edit` split_screen → `accent_sync(style)` (drops in music-file seconds; one stacked hit per drop, a leak per phrase) → `design_sound` forest/rain for mute footage · PRO_WORKFLOWS §25
- What is in the frame (offline OWLv2/SigLIP; allow_download once the user agrees): `find_subjects` queries → spans, best {at,box}; text/image → ranked windows; `rank_clips(subject)`; lower_third `avoid`; boxes are source shares → `semantic.to_canvas` before placing; `frame_for: vertical` → a framing that keeps the subject whole · archival stills: pushes aimed at the detected subject, maps with a callout · `compose_product reveal: dark` · PRO_WORKFLOWS §26
- Short-form selects and multi-shot AI films: `sequence_plan` chooses caller-inspected windows within a duration budget and builds a new editable project with source audio; `film_world` persists cast/prop state and compiles one generation packet per shot. Neither tool watches pixels or guarantees generated identity. Call either without args for its schema. [Research, limits and recipes](../../../docs/SHORTFORM_AND_FILM_RESEARCH.md).
- Story, treatment, techniques: [cinematic](references/cinematic.md) · [docs/CINEMATIC_TECHNIQUES.md](../../../docs/CINEMATIC_TECHNIQUES.md)
- Science/tech explainers (stat lines with **emphasis**, measured distances, diagrams, unit grids, plots, concept chips, number walls, HUD cards, particle bunches/collisions): `editvideo_explainer_catalog` → `editvideo_compose_explainer` · [docs/EXPLAINER_KIT.md](../../../docs/EXPLAINER_KIT.md)
- Style directions and motion language: [docs/STYLE_DIRECTIONS.md](../../../docs/STYLE_DIRECTIONS.md)
- Editing craft (Murch, eye trace, cutting on action, rhythm, beats, color workflow, pro toolkit): [docs/EDITING_CRAFT.md](../../../docs/EDITING_CRAFT.md)
- Pro workflows (transition grammar with measured durations, retention pacing, motion timing/easing, grading order with scope targets, sound layering and levels): [docs/PRO_WORKFLOWS.md](../../../docs/PRO_WORKFLOWS.md) · tools `color_scopes`, `process_color` grade, `sfx_sync`, `audit_audio`, effects `text_animate` `color_to` `bloom` `boil` `gate_weave`; compositing on any layer: `parent`/`null`/`anchor`, `masks`, `matte`, `key` (chroma); `step_frames` (on twos), `jitter`, svg `trim`, `clock_wipe`; explainer `camera_stage`; audio `role`+`normalize`; hook audit for short-form
- Review and evidence: [review](references/review.md) · [docs/REVIEW_AND_EVIDENCE.md](../../../docs/REVIEW_AND_EVIDENCE.md)
- Resources, sources, licences, credits, geography: [resources](references/resources.md)
- Narrated video: [narrated](references/narrated.md) · reading footage: [perception](references/perception.md), [temporal](references/temporal.md)
- Learn from finished work that succeeded (any kind: video, image, audio, web page, text): `editvideo_learn` registers works with evidence of success and a baseline, measures them and their labelled parts, compares winners with controls and keeps evidence-gated blueprints; measure your own work against one (`conform`) and log its real outcome (`apply`). Empty action: contract. [docs/LEARNKIT.md](../../../docs/LEARNKIT.md)
- Learn/apply craft across sessions: `editvideo_learning_library(query)` first retrieves related lessons and timestamped references; `editvideo_study_video` + strips supply pixels; `editvideo_remember_lesson` saves your original principle, when/avoid, steps, what you observed in each source window and schema-checked template examples (`{{project_id}}`). After a build that used a lesson, log `remember_lesson(lesson_id, outcome={project_id,revision,kept,note})`; raise its `level` only when the gates pass. Inspect the reference before generalising; attached renders are demonstrations, not aesthetic verdicts. Read an exact card for examples and artifact freshness. Loop/schema: [docs/LEARNING_FROM_REFERENCES.md](../../../docs/LEARNING_FROM_REFERENCES.md)
- Music, trailers, titles: `music_structure`, `music_fit`, `cut_alignment`, `snap_cuts_to_beats` modes; `trailer_plan` → `trailer_audit`; `title_catalog` → `compose_title` (title_card impact/minimal_wide/atmospheric/two_tone/integrated, type_lockup poster/credit, word_cards, sound_first); `design_sound` braam/suck_out · [docs/PRO_WORKFLOWS.md](../../../docs/PRO_WORKFLOWS.md) §12–14
- VFX: `track_plane` → `screen_replace` (corner_pin), effects luma_alpha/tint_fill/highlight_glow/tritone/heat_distortion/light_wrap/tracking, particles `mode: system` (fire/embers/sparks/smoke/bokeh), blends add/soft_light/hard_light/color_dodge; doc recipes `doc_timecard`, `motif_progress`, log-zoom `camera_stage` · §15
- Context economy: listings are compact (query an exact id for the full card); analyses return summaries + `full_path`; pass handles (`track_id`) instead of data; one contact sheet per snapshot; prefer `read_edit_context` over `read_project` for one moment · [docs/AI_ERGONOMICS.md](../../../docs/AI_ERGONOMICS.md)
- Dialogue, colour matching, character motion, short-form and ads: dialogue `read_dialogue` → `condense_dialogue` / `clean_dialogue`, `audio_profile`; colour `color_match`, `color_consistency`, grade `secondaries` + `protect_skin`, effect `halation`, film grain `gauge`; motion `animate` (hop/drop/slide_to/turn/rock/pop/hit/enter/exit), tracks `squash`/`scale_x`/`scale_y`/`skew` + `track_mods`, `motion_quality`; short-form `event_profile`, `punch_in`, `ad_plan` → `ad_audit`, caption_style build/keyword · [docs/PRO_WORKFLOWS.md](../../../docs/PRO_WORKFLOWS.md) §16-19
- Multicam, aspect, product shots, tracked windows: `multicam` (sync + speaker switching), room tone in `condense_dialogue`, `adapt_aspect` (9:16, 4:5, 1:1), layer `follow` (follow-through), `compose_product` (turntable, keyed spot sweep), `tracked_window` (color/blur/spotlight on a track), typewriter `script` + `cursor` · §20
- Rigs, scene-referred colour, independent review: layer `ik` (two-bone, target null) and `drivers` (link tracks), `process_color` `graph` (scene-referred: ACEScct nodes, Cineon print look, tracked windows), `evidence_3d`; independent `editvideo-reviewer` agent (docs/REVIEW_RUBRIC.md) for renders/code · §21
- Narration against picture, effect pairings, voices: `beat_map` (narration ↔ picture per sentence: late/early text, static sentences, unsupported figures, rhythm CV, motifs) after narration is placed; effect cards carry `pairs_with`/`avoid` + before/after strips (`read_design_preview kind=effect|combo`), 7 tested combos in `effect_catalog`; `voice_backend` auto/edge/piper/sapi/silent (offline plans get a timed silent placeholder); `project_from_video(segments)` in any order; `adapt_aspect` keeps cards together · §22
- Reading holds, labels on moving footage, offline voice, speed ramps: `beat_map(strips=true)` (judge picture vs words from one sheet per 8 sentences); `pin_to_track` (labels stay on handheld/drone footage after `track_region`); `voice_backend=piper` offline Vietnamese with audio-timed words; stillness audit separates `reading_hold` from dead frames; `create_silent_project` for reels/ads; speed changes on one take via `retime_footage` speed_keys (audits `speed_step`, `fractional_speed`, `fast_forward` at effective speed); `narration_unclear` = listen at the listed times · §23
- Typography/color/layout/effects: [design](references/design.md) · professional recipes/audio: [professional](references/professional.md)
- Tracking/masks/inpaint/generation: [subjects](references/subjects.md) · HDR/LUT/depth/3D/globe: [docs/COLOR_DEPTH_3D.md](../../../docs/COLOR_DEPTH_3D.md)
- Source code, runtimes, rendering: [source](references/source.md) · host integration: [docs/MODEL_INTEGRATION.md](../../../docs/MODEL_INTEGRATION.md)

## Fragile operations (follow exactly)

- Read the latest revision before every mutation; on conflict re-read and re-apply intent. Batch ≤100 ops.
- Timeline is 30 fps, ranges `[start_frame, end_frame)`; effects and 3D poses use local frames; source offsets are seconds.
- Downloads: `find_sources` only searches. Show file, source page, licence and size, wait for explicit user approval, then `fetch_source(expected_bytes=...)`.
- Credits come from `project_credits`, never memory; record unknown licences as `unknown`.
- Durable tasks return IDs: poll `get_media_task` / `get_job`; attach results with the current revision.
- Re-export source (`export_code overwrite=true`) only for projects without custom code; customized source needs a hash-protected merge.

## Lean context and resources

- `read_project` returns a summary (counts, shot list, layer ids); fetch only what you edit with `read_layers(ids)`. Use `detail="full"` only in scripts that rewrite the whole timeline.
- `snapshot_code` returns one contact sheet by default; `review_frames`, `audit_timeline` and `motion_audit` are lean unless you pass `verbose`/`series`.
- Batch frames into one `snapshot_code` call (one browser, one bundle) instead of calling it per frame.
- Media are hardlinked, bundles cached per code hash, temp cleaned per run. `storage_report` shows GB by area and orphaned projects; deleting is the user's decision.
- Renders keep `final.mp4` and a lean `delivery.zip` (code, timeline, media manifest). Call `package_source` only when the project must move machines.

## Creative freedom (use judgement)

Pick one hero technique that carries the film's idea; cut techniques that only decorate. Choose the direction by audience and idea, not trend. Measurements are evidence with thresholds — intent may overrule a heuristic, but say why. Generated or reconstructed imagery is illustration, not evidence.
