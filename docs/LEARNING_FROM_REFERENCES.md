# Learning from reference videos

A repeatable loop for studying professional videos and tutorials and turning what they teach into system capability
(runtime effects, recipes, audits, guidance). It is the procedure used to build the explainer kit from a CERN
explainer and the editing/motion/colour/sound upgrades from YouTube tutorials.

To learn from finished, successful works of any kind with evidence of their success (market metrics against a baseline),
compare winners with controls and keep evidence-gated blueprints, use `editvideo_learn`: [LEARNKIT.md](LEARNKIT.md). This
page covers studying tutorials and references for craft.

## Loop

0. **Recall before researching.** `editvideo_learning_library(query="chuyển cảnh", kind="all")` searches saved studies
   and original lessons without downloads or an API. Results include the reference title, short excerpts and
   source-second inspection windows; lessons show their level and logged uses. An exact `item_id` returns a lesson
   card (with artifact hash checks) or a study report without its raw shot list (`view="segments"` pages that list,
   100 rows at most). `bootstrap(task)` already lists up to three related lessons. Retrieval is BM25 over transcripts,
   titles (yt-dlp sidecar, else the reference set's `index.json`) and cards, plus an explicit Vietnamese → English
   craft lexicon (`editvideo/learning_lexicon.py`): accented words only match accented text, so "cân/âm" never match
   English "can/am"; both tone placements ("hoà"/"hòa") are one spelling; one-syllable keys whose bare form is English
   ("no", "hat") need accents. Words no text contains come back as `unmatched`; retry those in English. It is not semantic video
   understanding: a transcript mention tells you where to look, not what the video demonstrates.

1. **Find candidates (metadata only).** `yt-dlp --flat-playlist -J "ytsearch12:<query>"` per craft area (editing
   theory, transitions, motion graphics, typography, colour, sound, tracking/VFX). Rank by views, channel reputation
   and length (6–40 min). Then read exact formats and sizes with `yt-dlp -J --skip-download <url>`.
2. **Ask before downloading.** List file, source page and exact size per video and the total; wait for an explicit yes
   per batch. Prefer 480p + audio + English subtitles (most knowledge is in the narration; 480p shows results).
3. **Download into a new empty folder per video** under `data/references/<set>/<id>/` (study copies only: never reuse
   their imagery or text in outputs; standard YouTube licences are not Creative Commons).
4. **Study each video in one call:** `editvideo_study_video(path)`. It returns rhythm (cuts/min by 30 s, median shot,
   longest holds), look, transcript path with technique mentions and timestamps, music/cut alignment, on-screen text/UI
   moments, detected gradual transitions (dissolves, dips/fades, whips, listed separately: rhythm statistics still come
   from cut detection, so a long "shot" containing whip events is several shots) and one timestamped sheet; full data
   goes to `study.json`, the timestamped edit events to `events.json` beside it. About 15–20 s per 10 min of video.
   Technique mentions skip everyday senses of ambiguous words ("hit enter", "drag and drop": "hit"/"drop" count only in
   a sound phrase such as "hit sound" or "bass drop"). Without subtitles, run
   `editvideo_transcribe` (local Whisper) and save the SRT next to the video before studying.
5. **Look where the technique is demonstrated.** `learning_library(view="candidates")` lists studies not yet
   distilled into a lesson, each with its best windows to look at (`item_id=<study>` + `view="candidates"` gives more for
   one study, paged with `offset`; a `query` narrows both to a technique). Nearby mentions are grouped and split into
   windows of at most 30 s that fit the video, so every scored mention lies in one window; a window is ranked by the
   craft words said in it (rarer terms weigh more), plus the transitions (with their times), edit events and dense
   cutting the study measured there; windows a lesson already uses are cut out, and signals a study never measured are
   listed as `unmeasured`. `ui_on_screen` is true/false only when an overview-sheet frame fell inside the window, else
   null. Look with `inspect_window(path, start, end, frames=8)`
   (or `strips` when re-studying); for transitions sample ~1 s around each listed join. Read the finished result, not
   the UI clicks: of the top window of the first six local studies, 3 showed the technique's result and 3 showed it
   through the tool's interface (two colour grades, an EQ). A window is a place to look, not proof.
6. **Extract, in your own words:** what the technique does for the viewer, when to use and avoid it, concrete
   parameters (frames, easing, amounts, levels) and the workflow order. Never copy transcript passages.
7. **Gap analysis** against the live inventory (`discover_tools`, `effect_catalog`, `explainer_catalog`,
   `cinematic_catalog`): EXISTS / PARTIAL / MISSING.
8. **Integrate by type:**
   - runtime effect, transition or layer kind in `engines/effects.js` (shared by Remotion and HyperFrames) plus validation;
   - recipe that computes geometry and timing (`explainer.py`, `cinematic.py`, `professional.py`);
   - audit or analysis check that measures the rule on a render (`review.py`, `study.py`);
   - craft guidance in `docs/` and the skill.
9. **Prove it.** Add tests, then apply it in a short test render and inspect frames (`snapshot_code`), then re-run the
   full test suite.
10. **Record** an original reusable card with `editvideo_remember_lesson`, plus implementation guidance in the relevant
    doc. Save the viewer purpose, when/avoid, concrete steps, source windows with what you observed there, and
    parameters with their provenance. Optional tool examples are templates validated against the live input models but
    never run. An optional demonstration stores its video hash and your observation; it does not certify beauty. Update
    using the card's `id` and `revision`; retire a misleading rule instead of silently teaching it again.
11. **Apply and log.** When a build uses a lesson, render it, then record `remember_lesson(lesson_id=…,
    outcome={project_id, revision, kept, note, job_id})`. The runtime checks the project, that the job is a completed
    render of that revision, and runs the card's check on it. Promote the card (`level`) only when its gates are met.
    Pick the next topic area from actual gaps.

## Durable craft card

`remember_lesson()` with no arguments returns this contract. `remember_lesson(request=...)` accepts:

```json
{
  "title": "A dissolve can suggest elapsed time",
  "principle": "Blend related compositions when the story needs a soft temporal ellipsis.",
  "when_to_use": "A before/after scene whose composition remains readable during overlap.",
  "avoid": "Unrelated moving compositions, or overlapping two text labels that must be read.",
  "steps": ["Inspect both sides", "Choose a duration for this story", "Compare against a straight cut"],
  "tags": ["transition", "documentary", "time"],
  "sources": [{"study_id": "study-0123456789abcdef", "start": 302, "end": 320,
               "observed": "Your own description of what the window shows (not the narration)."}],
  "parameters": [{"name": "dissolve_frames", "range": [30, 48], "unit": "frames@30fps", "provenance": "chosen",
                  "note": "picked for the demo, not measured"}],
  "examples": [{"tool": "editvideo_patch_timeline", "arguments": {"project_id": "{{project_id}}",
                "base_revision": "{{base_revision}}", "operations": [{"op": "update_shot", "shot_id": "{{shot_id}}",
                "changes": {"transition": {"name": "dissolve", "duration_frames": 36}}}]}}],
  "check": {"uses": ["dissolve"], "codes": ["text_over_push"], "expect": "absent"},
  "state": "active"
}
```

Use a real `study_id` returned by `study_video` or `learning_library`. A source must still exist with the studied hash,
and windows must fit its duration. Each saved window also stores what the study already measured there (`measured`:
cut candidates and gradual transitions; older studies say transitions were not analysed). A `measured` parameter names
the source window it came from; `chosen` and `cited` are honest alternatives. `examples` are templates: `{{project_id}}`,
`{{base_revision}}`, `{{shot_id}}`… are filled with typed stand-ins for the schema check and by you on reuse; a fixed
project/revision is a warning, and blocks `rule`. `check` says how a build shows the lesson: `uses` (required) lists
technique names the audit inventory must contain (transition, effect or layer kinds) and `codes` the `audit_timeline`
findings that must be absent (or present). Codes alone prove nothing: an empty project passes "absent" and a blank
carrier already reports `long_shot` or `late_hook`. Codes are checked against what `audit_timeline` itself can emit
(its own findings incl. conditional levels and the narration check; motion-audit codes are not run there); a code
reported only as `info` cannot back an `absent` check; `uses` must be transition, effect or visible layer names that
the card itself names in its steps, text or examples (a colour lesson cannot be "verified" by any video with text).
Presence is measured on the timeline: shot and layer effects count, but only elements a viewer can see (at least 6
frames, opacity above 0; `null`/`adjust` layers never). `demonstration` may be `{path, observation}` for a playable local video.

**Levels** are evidence gates checked by the runtime; promotion is explicit (send `level` with `lesson_id` and
`base_revision`), a new card gets the highest of observation/candidate its evidence supports:

| Level | Needs |
|---|---|
| observation | source windows bound by hash (cards saved before levels existed read as this) |
| candidate | an `observed` note (≥ 20 characters, own words) on every window |
| rule | candidate + a second independent source video **or** one verified use; template examples |
| standard | rule + a valid `check` and verified uses in two projects |

A use is **verified** only when it was kept, its outcome names a completed `final` render job of the reported
revision (re-read from the job store, project still present), and the card's **current** check passes when the
runtime re-runs it on the timeline that render used (`jobs/<id>/timeline.json` beside its `output.json`, hashed when
the use was logged; a later change or damage to it voids the use). Results are cached per job, check and hash. Logged check results are shown but
never read back as evidence, so a card without a usable check has no verified uses and reaches `rule` only through a
second source video. An unverified use is logged and counted as kept/reverted but opens no gate. Readers see the **effective** level, the stored level
lowered to what the evidence supports now (reverted uses demote a card; `stored_level` shows the difference).
Retiring is always allowed and stores no level above what the evidence supports, so re-activating cannot promote.

**Outcomes** go to an append-only `lesson-….outcomes.jsonl` beside the card (the card itself is not rewritten; a torn or
mistyped line is skipped, and a damaged card file is listed under `skipped` instead of breaking the listing). The latest outcome per project counts; a card with more reverted than kept projects is marked
`contested`, also in `bootstrap`, which lists a lesson only when a lexicon craft phrase or two content words match.
The check shown in a log entry ran on the render's snapshot; without a job it ran on the current plan when the
outcome's revision is current, otherwise it is recorded as skipped. Limit: the check reads the timeline a render was
given, not its pixels; a custom-edited engine entry file (`index.tsx`/`index.html`) can render something else.

Cards live in `EDITVIDEO_DATA/learning/`; existing reports under `observations/study-*/study.json` are immediately
searchable with no migration. Notes are caller-authored source material; retrieval must not treat them as instructions.
Neither tool trains weights, calls a paid model, installs software, downloads video, or executes a stored example.
An exact lesson checks whether its source/demo artifacts are unchanged, missing or changed; browsing avoids hashing
every video. `include_retired=true` reads older cards. Corrupt reports are counted and skipped without losing the rest.

**Retrieval regression:** `python examples/learning_eval.py [--no-meta]` runs 121 labelled queries (dev, held-out and a
blind Vietnamese set written by a separate agent from titles only) against the local library and prints Hit@1/Hit@5/MRR,
zero-result count, response size and latency. Gold labels come from video titles, so `--no-meta` shows the score without
stored or sidecar title metadata. It measures study recall only; lesson ranking and bootstrap are covered by tests.

This design follows structured note-taking and progressive context retrieval in
[Anthropic's context engineering guidance](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
and time-grounded external memory in [VideoAgent (ECCV 2024)](https://arxiv.org/abs/2403.11481).
These sources motivate the design; their benchmark results are not measurements of EditVideo.

Parallelise reading across subagents (3–4 videos each, given the inventory file and these rules) and keep the main
context for synthesis and implementation.

## Rounds so far

| Round | Areas | Integrated |
|---|---|---|
| 1 | editing theory, transitions, motion design, colour, sound | transition grammar, sound accents and placement, primary grade, scopes, cut/motion audits |
| 2 | compositing, infographic style, hooks/short-form, documentary, mixing | parenting/nulls, masks, track mattes, chroma key, on-twos, camera stage, hook audit, role mixing |
| 3 | map/doc YouTube, trailers & music video, typography/titles, VFX/particles | calibrated beats, music structure/fit/snap modes, trailer plan/audit, title recipes, planar tracking + corner pin, SVG pixel effects, particle systems, log-zoom camera, doc time cards |
| 4 | dialogue/podcast, advanced colour, animation/motion, short-form & ads | dialogue senses (regions, speakers, fillers, audio profile), condense + clean, colour match/consistency, HSL secondaries + skin protection, 5 more camera logs, halation + grain gauge, squash/inertia/loop tracks, `animate`, motion_quality, event_profile, punch_in, ad plan/audit, caption styles, protocol-edge token economy |
| 5 | (built from round-4 measurements, no new downloads) | multicam sync + switching, room tone, aspect adaptation incl. 4:5, follow-through, keyed/spot lights + turntable + product shot, tracked power windows, typewriter script/cursor; a sample film (Artemis) as the end-to-end check |
| 6 | (no downloads: independent review of the system and the sample film) | two-bone IK, drivers, scene-referred colour graph with Cineon print look and tracked windows, evidence_3d; 2 P0 + 8 P1 code fixes, ink-measured titles, entrance hold, motion/ending/letterbox audits, streaming analysis, token trims, release standardisation |
| 7 | (external evaluation; one approved download: a NASA interview soundbite reel, 116 MB) | effect atlas v2 (91 strips × 2 engines, 7 combos, pairs/avoid), beat_map, narration fallback chain, selects in any order with gap report, HyperFrames static video declarations + frame-index fix + decoded dissolve posters, tracking cap, group-aware adapt_aspect with upscale cap, soft_upscale / jump-cut-on-selects / scale-matched dissolve audits; four real builds (doc, interview, vertical ad, vertical doc) in both engines |
| 8 | (external re-assessment; approved downloads: two Wikimedia Commons takes 53 + 77 MB, Piper + Vietnamese voice ~97 MB, a clean networked install) | motion-span stillness audit with reading holds, beat_map sentence strips, offline Vietnamese narration with audio-measured word timing, pin_to_track; builds in two new genres (square how-it-works with offline narration, vertical drone travel reel) |
| 9 | TikTok/Reels/Shorts craft, evidence-graded (no new downloads; existing NASA and Commons footage) | shortform_audit with evidence-cited findings and a UI overlay sheet, one platform table, pop/outline/bilingual captions, face reframing, condense windows + transcript, punch ladder, beat bed, engine proxies for HDR and sparse-keyframe sources; builds: vertical talking head, listicle |
| 11 | semantic sight; archival, science, product films (approved downloads: OWLv2 + SigLIP 1.44 GB, ~200 MB of Commons/NASA/Khronos/Poly Haven media) | find_subjects (open-vocabulary detection, text/image search, frame_for framing), rank_clips(subject), lower_third avoid, working copies (archival scans, rotated and anamorphic pictures), glTF packing, dark product reveal, rate and dropped-frame proxies, HyperFrames nesting shots like Remotion, CSS font matching; builds: Long Biên bridge, how Webb unfolds, product reveal. Lesson: render every new genre in both engines and look at the frames that differ, each divergence was a system bug |
| 10 | effect combinations by genre (approved downloads: 27 Wikimedia Commons clips, three CC0 tracks) | rank_clips (local action, silent clips, cross-clip match cuts), accent_sync (music hierarchy per style), impact effects in both engines, retime peaks, freeze_frame, apply_combo, split_screen, forest/rain beds, genre templates; builds: rally velocity, wildlife mini-doc, food short, city montage; 9 engine/audit parity fixes |

Lessons from round 3 about the loop itself:
- **Measure the tool against the reference before trusting it.** The beat tracker was ~73 ms early and the study's
  music check called a clearly beat-locked montage "independent of the beat"; a click track and a known-good reference
  exposed both. Keep such references as regression tests (`tests/test_music_timing.py` uses a synthetic song with known
  sections, hits and a dip).
- **Synthetic ground truth for vision tools.** The planar tracker was proven on a rendered perspective move with a
  crossing occluder (sub-pixel), which caught a wrong ECC mask convention that a visual check would have missed.
- **Render-check every runtime feature in both engines** (`data/films/titles_test.py`, `doc_test.py`): corner pin,
  filters and title layouts must match between Remotion and HyperFrames frame for frame.

Lessons from round 4:
- **Hand-measured numbers are the regression target.** event_profile was tuned until it matched the analysts' hand
  counts on two reference edits; cut_alignment was fixed when an analyst showed that a significant-looking lead was
  chance (it now uses a permutation test).
- **Tests on synthetic ground truth catch silent bugs.** A short-form caption test exposed a variable-shadowing bug
  that broke vertical caption layout; a synthetic dialogue exposed that feature standardisation erased the pitch weight.
- **Optimise what the model reads.** Tool I/O was compacted at the protocol edge (docs/AI_ERGONOMICS.md) before adding
  12 tools, so the surface still shrank (about 20.4k → 16.5k tokens, for 116 tools instead of 104).

Lessons from round 5:
- **A real film is the integration test.** Building the Artemis sample exposed issues no unit test had: a 3D product
  scene blown out by stacked light + bloom + halation, Vietnamese marks colliding in a stacked title, a time card hidden
  under an opaque 3D layer, phone-unreadable label sizes, and audit false positives on deliberate hard-cut titles. Each
  became a system fix (light/studio controls, line-height rule, recipe sizes, audit exemption), not a one-off tweak.

Lessons from round 6:
- **Separate the judge from the builder.** Four read-only reviewers (code, performance/tokens, release, film) found two
  silent desync/corruption bugs the test suite passed, a title that read as a different word, a blink in every
  staggered entrance, and a 1.7 GB release footprint — none visible from the builder's side. Each finding became a
  system change plus a test; the film was then re-reviewed against the same list.
- **Box metrics lie about ink.** Collisions between Vietnamese marks and between text blocks are decided from glyph
  ink (FreeType masks), not layout boxes; the same measurement removed false positives on the poster.

Lessons from round 7:
- **Different kinds of film find different gaps.** The documentary needed narration↔picture timing (beat_map), the
  interview exposed a reel slug inside a select (silence + black) and out-of-order jump cuts, the vertical ad exposed
  letter-spacing reflow, entrance start states clipped at the frame edge and 720p upscaling, and the vertical adaptation
  exposed cards coming apart and zoom caps that turned punches into jump cuts. None showed up in the 16:9 sample film.
- **Sample less, miss more.** Engine parity on 12 sampled frames read 0.94–0.97 while a one-frame glitch at a cut
  (SSIM 0.49) and a five-frame dissolve dip (0.24) sat between the samples; parity is now measured on every frame and
  divergence is a dip against the neighbours that PSNR confirms (dark passages sit lower everywhere from encoder
  noise alone). Downscaled comparisons also hid two full-size defects in HyperFrames: marks above Â/Ô clipped by
  the layer box and an 8-px black edge on every portrait frame; text ink and frame edges are now compared at full
  size.
- **A fix in one place can break a rule elsewhere.** Capping zoom for pixel quality shrank a punch below a readable
  step and unmatched a dissolve; adapt now re-checks cut grammar after the cap (step out instead of in, keep dissolves
  scale-matched).

Lessons from round 8:
- **New material finds new gaps.** The Artemis builds never needed labels on a moving camera; a handheld product
  take and a drone pull-back made pinning a missing operation, and three small system bugs (frame rounding on
  import, sub-frame "jump cuts", keyframes one frame past a layer) surfaced only on them.
- **An audit that is wrong in a known case loses trust in every case.** The re-assessment found one false positive
  (a drawn chart called static); the fix replaced a yes/no rule with a measured still stretch and a reading need, so
  the finding now says how long the picture is still and why that is or is not a problem.

Lessons from round 10:
- **Four genres at once find what one cannot.** The velocity edit exposed retime peaks counted from the wrong origin
  and drops in unstated units; the wildlife film exposed mute Commons tracks (now reported) and a missed take-off (now
  found by camera-compensated local action); the food short exposed freeze shots that could not hold a clip's last
  frame and a poster seek inside a 24 fps clip's last frame; the city montage turned a measured match cut into the
  edit. Each became a system change with a test.
- **A measured peak is not the moment.** The top "action" in one rally clip was a spectator's hand before the car came;
  a 0.5 s contact sheet of the reframed clips chose the hero. Measurements rank; looking decides.
- **Parity bugs hide in rounding.** A source start at 0.15 s is frame 4.5: Remotion (JS) rounds it to 5, Python's
  round() to 4, and a whole HyperFrames shot sat one frame behind. Snapshots did not show it (the runtime re-set the
  value); only every-frame parity on the final renders did, so parity stays on the real renders.
- **Audit the auditor on the builds.** The short-form audit called the edit's own 2-frame white flashes "flash cuts"
  and a dark outline on dark text "contrast 1.06"; with the timeline it now excludes authored accents and treats a
  same-tone outline as ink.
