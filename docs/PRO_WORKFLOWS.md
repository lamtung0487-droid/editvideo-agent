# Professional workflows

Working rules distilled from studying twelve widely watched tutorials on editing theory, retention editing, seamless
transitions, Premiere/After Effects technique, kinetic type, 3D tracking, colour grading and sound design (studied
locally with `editvideo_study_video`; see LEARNING_FROM_REFERENCES.md). Numbers marked *measured* were measured frame by
frame from the examples; others are working defaults. Every rule names the tool or parameter that applies it.

## 1. Transition grammar (default: a plain cut)

Priority when choosing a cut (Murch): emotion > story > rhythm > eye trace > 2D plane > 3D space. A transition other
than a cut must have a job.

| Job | Use | Parameters | Tool |
|---|---|---|---|
| Time passes, memory | dissolve | 1.3–2.5 s *measured*; never under ~8 frames | `transition dissolve, duration_frames 40-75` |
| Two lives compared | long superimposition | 6–9 s, subjects in opposite halves | dissolve with a long duration; place subjects apart |
| Chapter / ending | fade or dip | dip 10–12 frames (5 out, 1–2 held, 5 in) *measured*; opening fade 4–5 s | `dip_black`/`dip_white` + `hold_frames` |
| Shock, contrast | smash cut | big jump in brightness/loudness between sides | plain cut; check contrast |
| Momentum, change of place | whip | blur peaks at the join; both shots move the same way | `whip_left/right/up/down`, `intensity` |
| Energy, same subject distance | spin | both roll the same way and rate | `spin`, intensity = roll amount |
| Dark → bright scene | luma key | frame-filling subject in fast move | `luma_key` |
| Hide the cut behind something crossing | pass / occluder | sweep 12–14 frames, soft edge, with a whoosh | `pass_left/right` (SAM2 matte for exact objects) |
| Isolate a subject | iris | off-centre on the subject | `iris` + `center` |
| Techy beat | glitch cut | 4–6 frames, sparingly | `glitch_cut` |
| Same theme, both pushing in | zoom through | — | `zoom_through` + `speed_lines` film layer |

Rules: at most one stylised transition per real scene change; never three of the same in a row
(`transition_repeat`); motion must match (direction difference under ~45°, speed ratio under 2). After rendering,
`cut_audit` measures optical-flow direction on both sides of every seam and flags `transition_against_motion` (a
whip/push/pass travelling against the footage) and `screen_direction_reversal` (plain cut between opposite moves). `audit_timeline`
flags `short_dissolve`, `decorative_transitions`, `jump_cut`.

## 2. Cutting

- Cut on action in the middle of a movement, with motion on both sides (`cut_audit` on_action; both sides above 0.8).
- Short shots need a stable eye trace: keep the focal point near where the last one was (`cut_audit eye_trace_jump`).
- Pace follows emotion: contemplative median shot ≥3 s, dialogue 2–5 s, action under 1.5 s, frantic under 1 s *measured*.
- Jump cuts: either a deliberate series of 2–3, a punch-in of about 15–30% on alternate fragments, or a cutaway.
- J/L cuts: dialogue overlaps from a few frames to 1 s; scene pre-laps of several seconds, landing the picture cut on an
  audio event (`j_cut_audio`, `l_cut_audio`, `sound_bridge`, `read_audio_events`).

## 3. Retention pacing (talking-head and explainer content)

- Count visual events, not just cuts. Events are cuts, transitions, graphics entering and punch-ins. Aim for one every
  3–6 s, allowing up to ~10 s when the content itself moves. `audit_timeline` flags `attention_gap` (>8 s held, nothing
  happens) and `event_overload` (>4 events in 3 s).
- A-roll for confident key statements; B-roll and graphics for most of the runtime; motion graphics for points that are
  essential but complex.
- Punch-in for emphasis at most every 15–20 s; never two consecutive jump-cut fragments at the same scale.
- Captions for emphasis only, ≤3 words per page.
- None of the studied tutorials cut on the musical beat (on-beat share at chance level). Sync music *changes* to topic
  boundaries instead: a hard stop to spotlight one moment, a 2–4 s fade at segment ends, a swell at the problem→solution
  turn.

## 4. Motion design

- Easy ease ≈ bezier `[.33,0,.67,1]`; to make the last element lag, raise incoming influence to about `[.33,0,.25,1]`.
  Use `bezier` on effects and keyframes rather than generic `smooth` when matching a reference.
- Timing: a text block enters in ~12 frames; a swing or dock 4–6 frames; paired elements 5–10 frames apart; exits in
  reverse order and faster than entries.
- Type: build hierarchy with value and weight (active line white, earlier lines stepped darker or in the accent colour;
  one **bold** phrase per line). Tools: `text_animate` (units, order, in/out/sweep, own easing), `color_to`, inline
  `**strong**`/`==accent==`.
- Energy decays: repeated impacts fall roughly 100 → 70 → 20%.
- Stillness makes motion land: vary density between beats (`motion_audit uniform_energy`).
- Finish: `bloom` for light sources (judge the falloff, not the brightness), `gate_weave` 1–2 px for an organic frame,
  `boil` for illustrated lines, `grain`; gradients get ≥3 stops (warm lights, cool darks).
- VFX on footage: anchor at the contact point, match motion blur, screen blend for light/fire, time-offset looped
  duplicates, SAM2 foreground above (`text_behind_subject`, `track_subject`).

## 5. Colour grading (serial order)

1. Input transform first: camera log is developed with `process_color(input_space=slog3|logc3|vlog, input_range=...)` (published curves, primaries-derived gamut matrix, filmic shoulder, 18% grey at 42%); Rec.709 sources are decoded as tagged. Check `color_scopes`.
2. Levels: lift until the darkest real object just touches black; gain so nothing but speculars clips.
   Targets: p0.5 luma 1–4% with ≤1% under 2%; p99 85–93%, ~0% over 98%.
3. White balance on a neutral, unclipped area (`grade.neutral_region`); midtone cast under ~2–3% chroma.
4. Creative primary: gentle contrast around pivot .435, a soft S-curve, saturation +10–40% in mean chroma.
5. Colour contrast: small split tone (≤.04): cool shadows, warm mids/highlights; keep skin on the 123° line ±10° unless
   the look is deliberately warm (`skin_region`).
6. Optional sharpen (soft log footage) and a vignette that pulls the eye to the subject.
7. Compare with the reference or the previous version (`color_scopes(compare=...)`).
Tool: `process_color(request.grade={...})` then `color_scopes` before/after.

## 6. Sound design (layered, then restrained)

1. Temp score cut to picture: land the cue's hit on the key action; drone for tension.
2. Ambience in every location (`room_tone`, `wind`), low (20–30 dB under speech), switched with the scene.
3. Foley for visible actions, no repeated sample back to back (`sfx_sync` rotates variants).
4. Space: dry foley sounds fake; give it the room.
5. Creative layer on purpose: whoosh peaking mid-move (`sfx_sync` anchors the peak), pop on graphic entrances, chime on
   a title reveal, reverse cymbal/riser ending exactly on the cut, impact or sub drop starting on it.
6. Restraint: decide which moments matter; ≤ ~16 accents per minute; one max-intensity hit per scene.
7. Mix: speech-led master about −16 LUFS, true peak ≤ −1 dBFS; music 10–18 dB under speech.
Tools: `design_sound` (14 kinds, `onset_s`/`peak_s`), `sfx_sync`, `audit_audio` (density, repeats, unresolved risers,
dead air, true peak).

## 7. Compositing: mattes, keying, rigs, node thinking

- **Parenting and nulls.** `parent: <layer id>` makes a layer inherit translate/scale/rotate (not opacity or filters) around
  the parent's `anchor`; `kind: "null"` is an invisible controller. `parent_bind_frame` keeps the child where it is at that
  frame instead of jumping onto the parent. Rig a group (labels around a planet, a character's limbs, a whole infographic)
  under one null and animate the null.
- **Masks.** `masks: [{shape rect|ellipse|polygon, geom in layer-box units, mode add|subtract|intersect, feather_px,
  keyframes}]`, `mask_invert`. Garbage masks around a subject, an iris onto a detail, a slit or window cut.
- **Track mattes.** `matte: {source, mode alpha|alpha_inverted|luma|luma_inverted}` with the source hidden by default.
  Text windows (footage inside a word, then zoom through a letter), shape reveals, wipes. Sources are vector/text layers.
- **Chroma key.** `key: {screen green|blue, color (sample it), clip_black, clip_white, choke_px, soften_px, spill, view}`.
  Workflow: denoise/pre-render the plate if noisy → garbage mask the set → sample the screen colour → raise clip_black
  until the screen is gone, lower clip_white until the subject is solid (check `view: "matte"`) → choke 1–2 px and soften
  1 px on the edge → despill (green pulled to the R/B average) → place over the plate and match its grade. For hair, pair a
  SAM2 subject mask (`track_subject`) as the core with the key for the edge band.
- **Node habits that map to layers.** An effect stack is a node chain; z-order + blend is a merge; a null is a transform
  after the merge; mattes are merge In/Held Out.

## 8. Infographic house style (Vox-like explainers)

- Black-and-white imagery (desaturate, raise contrast), off-white paper ground, black type, one acid accent (lime) and at
  most one secondary; faint blue grid, paper grain, vintage scans; clean cut-outs with a pin or a tag.
- Animation **on twos** (`step_frames: 2` on layers or `design.step_frames`) plus a 2–3 px stepped tremble on cut-outs
  (`jitter`, `cycles` 4).
- One big canvas and a moving camera (`camera_stage`): a new stop about every 2 s, 18-frame moves with bezier
  [.7,0,.2,1], a slow drift after landing (never fully still), push-ins with zoom blur (`speed_lines`).
- Builds: draw strokes rather than rectangles. Use `trim` for segmented lines and arrows, `clock_wipe` for pies and fills,
  and `width_ramp` for strokes that swell in. Labels slide out of their bars. Map order: land → accent border trace →
  highlights → pinned photo → name tag.
- Logo reveal grammar: outline write-on with two echo colours 7–8 frames apart → hold → clock-wipe fill → icon settles
  while the wordmark rises → hold ≥1 s.

## 9. Hooks and short-form (9:16)

- Hook types: curiosity gap (open loops), challenge a belief, a desired result, social proof, controversy, before/after,
  the viewer's own pain. Test: after the first frame, what question does the viewer have? None means no hook.
- First frame: one large subject separated from a clean background, one contrast element, and it matches the cover.
  Hook text gives context but withholds the answer; one emphasised word.
- Pacing, from evidence (see §24): the first visual change by 1 s, text or speech by 0.5 s, the key message by 3 s.
  More is not better: top talking-head TikToks run 0.19–0.52 cuts/s and an experiment found faster pacing lowered
  completion (one short-form tutorial measured 3 changes/s in its first 3 s; that is one style, not a target).
- Layout: keep the right rail and the bottom block clear (`platforms.zones`); hook text around y .15–.30; spoken
  captions 1–3 words and ≤2 s per page around y .60–.66 (`word_captions` with platform tiktok/youtube_shorts).
- `audit_timeline` flags `late_hook`, `sparse_open` (no change by 1 s), `flat_hook_pace`, `fast_pace` (> 0.6 cuts/s),
  `hook_text_long`, `hook_text_in_ui_zone`, and uses a 4 s `attention_gap` threshold for vertical video.

## 10. Documentary story editing

1. Re-outline from what was actually captured (transcribe, then a paper edit in the storyboard).
2. Organise selects by material: interviews, B-roll, archive.
3. Radio edit first: cut the interview audio with deliberate breathing gaps, then lay B-roll as a progression of actions.
4. Show the world before the character; introduce people through action before the talking head.
5. Build-up (shots shortening), a breath (one long held shot) before the turn, then release (faster cuts, music steps up).
6. Emotional core: stay on face and hands, show the object of the story only in details.
7. Match cuts on shape and on sound; motivated transitions (an object crossing frame, smoke over a memory).
8. Fill masks and relights with the scene's shadow colour, never pure black.
9. End by decompressing: longer holds after the peak, a final image that bookends the opening (storyboard callback).

## 11. Mixing by role

| Role | Target | Chain (`AudioClip.role`) |
|---|---|---|
| dialogue | about -16 LUFS, peaks -6..-3 dBFS | high-pass 80 Hz, 3:1 compression around -20 dB, limiter -3 dBFS |
| music | 10–18 dB under speech (about -30 LUFS), ducked | — |
| sfx | peaks -12..-18 dBFS, under dialogue | — |
| ambience | 20–30 dB under speech | gentle low-pass |
| foley | about -28 LUFS | rumble cut |

Set `normalize: true` to measure the used section of each source and bring it to its role target; `volume` trims on
top. Master stays two-pass loudnorm with true peak ≤ -1 dBFS; check with `audit_audio`.

## 12. Editing to music

- **Beat times are calibrated.** `beat_track`/`music_structure` place beats on the attack (±2 ms on click tracks; the
  tracker used to report them ~73 ms early). Onset strength mixes linear-bin flux, mel-band flux and kick-band flux so
  bright off-beat hats do not pull the grid. Half/double time is common: check `bpm` and pin it with `bpm_range`.
- **Read the track first:** `music_structure` returns beats with their bar position, bars, 4/8-bar phrase lines, sections
  (intro/build/peak/breakdown/body/outro), hits (≥15 dB jumps) and quiet gaps. `pulse` from periodicity: clear ≥ .22,
  weak < .15 (orchestral trailer beds). Weak pulse → cut to hits, section entries and gaps, not to a beat grid.
- **Snap modes** (`snap_cuts_to_beats use=`): `priority` (downbeat 1.0 > beat 3 0.7 > others 0.4), `hits`, `phrases`,
  `against` (off-beats for tension), plus `beats`/`downbeats`. Default lead 2 frames (a measured montage cut 4.6 ± 0.7
  frames before the beat). `protect` dialogue ranges. The result lists section entries that have no cut: the strongest
  places to add one.
- **Shot lengths in beats:** even numbers of beats (2, 4, 6, 8); speed up to one cut per bar in the loud phrase; a cut on
  the section entry; the last cut where the music starts to fade. Dialogue scenes follow the words, not the music.
- **Beat This! first.** When the `beat_this` package and its checkpoint are installed, beats and downbeats come from
  it (Foscarin, Schlüter and Widmer, ISMIR 2024; MIT code and weights; no DBN, any metre, so 3/4 stays 3/4, a pickup
  counted back from the first downbeat).
  - `music.fetch_beat_model()` fetches the checkpoint once into the store's `models/beat_this`, with a timeout, a size
    check and a load test; a bad file is set aside as `.bad`. `EDITVIDEO_BEAT_CHECKPOINT` points at a copy fetched by
    hand. The JKU host answered 500 on 2026-10-28.
  - An analysis never fetches or waits on a host: it only uses the checkpoint when it is already on disk.
  - The calibrated DP tracker stands in otherwise, and whenever a `bpm_range` is pinned. `music_structure` says which
    one ran (`tracker`).
- **Cutting the song to length** (`music_fit`): remove or repeat whole bars between two similar-sounding bar lines,
  crossfade ½ beat centred on the bar line, keep the real ending (`natural`), or end on a one-bar fade or just after
  the last hit. Join cost < 1 is usually seamless; listen across the join.
  - `max_joins` > 1 finds the cheapest path through the bars with several joins: a length-constrained shortest path,
    as in Scalable Music (Eurographics 2013). Joins are at least a phrase (4 bars) apart and from the end, and the
    pickup before the first bar counts in the length. On The Escalation cut to 150 s, it found joins costing 0.93 and
    0.42 where the single join cost 1.43.
  - `exact` plays the plan up to 3 % faster or slower (`playback_rate`, pitch kept) so it ends on the frame.
- **Music under narration by measured loudness** (`music.duck`, `music_fit duck_lu`): no compressor's threshold.
  - Each spoken phrase is measured (EBU R128 momentary), and the music under it is set `gap_lu` (13) under it.
    Torcoli et al. (JAES 2019) put speech at least 10 LU over music, and lay listeners want about 4 LU more than
    mixers.
  - The music comes back to its bed level in pauses of a bar or longer. Shorter pauses stay down, so the music does
    not pump between words.
  - The dip starts on the downbeat before the phrase, and the swell lands on the downbeat after it.
  - The clips are re-cut into constant-gain pieces crossfaded over each ramp. The pieces are sample-aligned copies, so
    a crossfade is a gain ramp; their `duck_under_voice` is off.
  - A phrase that runs across a music join stays down in the next clip.
  - On a stereo mix of real speech over The Escalation, the measured gaps were 12.9-13.2 LU for a 13 LU target, and
    the pauses were back at the bed's own level.
  - With `exact`, each piece is stretched by its own `atempo` and the pieces crossfade over the ramps. That has not
    been checked by ear: listen across each ramp.
  - `music_fit` with `duck_lu` keeps the placed revision if the ducking fails, and returns `duck_error`.
- **Reading a reference edit:** `cut_alignment(path, cuts)` gives the editor's habitual lead (offset histogram peak),
  on-beat share against chance and the downbeat share, per 30 s window. `study_video` uses it.

## 13. Trailer grammar

| Section | Measured | Notes |
|---|---|---|
| Bumper (YouTube) | 3–6 s | best moments before the trailer proper |
| Cold open | 10.5–11.8 s, median shot 1.22 s | dialogue hook with little context; ~0.9 s of quiet after the punchline, then logos/music ~20 dB louder |
| Act 1 | median shot 0.73 s | premise; music builds without drawing attention |
| Act 2 | median shot 0.65 s (tightest) | conflict + doubt, enters on a cut with a ~+10 dB step; act cards after a 0.85 s fade to -36 dB, then a +23 dB hit |
| Act 3 | median 1.0 s, bursts of 0.4–0.8 s | 0.3 s dip, then ~9 s of steady loud music |
| Title | ~2.3 s hold | starts on the last hit, holds while the tail decays to about -27 dB |
| Button | 6–8 s | dialogue-led joke or tease |

- `trailer_plan(duration, music_path)` lays these out and moves act changes and the title onto section entries and
  hits; `trailer_audit(project, sections, music_path)` checks pacing per act, acceleration, a climax burst, title hold,
  button, dialogue per act, changes on hits (±2 frames), dips before the climax/title and a ≥6 s loud climax.
- Sound-first reveal: hit on black, picture ~1.7 s later (`compose_title` `sound_first`). One-word cards of 9–18 frames
  on hits, cut ~1 frame early, optional 2-frame picture flash (`word_cards`). Trailer sounds: `design_sound braam` on a
  title or act card, `suck_out` ending exactly on the beat before a hit; a signature sound repeats through the trailer.

## 14. Title design

- Decide **impact or integration** first. Impact: hard cut on a harsh hit after 1–2 s of black, frame-filling condensed
  capitals (cap height up to ~.45 H, width ≤ .94 W, tracking ~0), hold 1.8–3.4 s. Integration: linear 1.5–2 s fade with
  the picture or scene sound, holds up to 8 s.
- `compose_title` `title_card` presets: `impact`, `minimal_wide` (light sans, +.6 → +.45 em while fading in),
  `atmospheric` (small spaced serif, low contrast allowed), `two_tone` (first word in the accent), `integrated` (whip-in
  with motion blur over the picture, leaves by scattering). Sizes come from FreeType metrics so the cap band is centred.
- `type_lockup`: poster stack (main ≈ 7.5× the top line, top/sub lines .023 H bold +.15 em, footer at y ≥ .88) or credit
  (role line 0.4× the name, surname heavier). Vietnamese capitals need line height ≥ 1.25 for the accents.
- Text animation craft (measured): words enter from +.026 W while fading in, 3–5 frames apart, ~12 frames each with a
  strong ease-out (quint-out [.22,1,.36,1]); exits are opacity only and ~2.5× shorter than entries; no overshoot.
  Several `text_animate` effects now combine on one layer (entry + exit), `shutter` adds per-word motion blur, `target`
  animates chosen words only (emphasis by position). `tracking` is in em and keeps centred titles centred.
- Rules: readable hold ≥ 0.6 s + 0.3 s per word (never < 1.5 s); exit ≤ half the entry; main-to-secondary ≥ 2.5×.

## 15. VFX and finishing

- **Planar tracking → corner pin.** `track_plane(path, corners, start, end)` follows a flat surface in perspective
  (≤1.2 px on a synthetic move with a crossing occluder); `screen_replace` pins any layer onto it (`corner_pin` track,
  matrix3d in both engines). Exclude reflections/occluders at the start; matte a hand crossing the screen above the insert;
  add `light_wrap` and a grade so the insert sits in the plate.
- **Pixel effects (SVG filters, both engines):** `luma_alpha` (fire/smoke/light leaks shot on black composite without a
  box), `tint_fill`, `highlight_glow` (threshold + three radii, `anamorphic` streaks), `tritone` (documentary/map grade,
  archive unification), `heat_distortion` (morphing noise displacement), `light_wrap` (backdrop colour into the edge).
  They run after a chroma key and before CSS filters; `ramp` animates the amount.
- **Particle systems:** `particles` `mode: system` with presets fire, embers, sparks, smoke, bokeh (closed-form drag,
  gravity, wind, turbulence; size/opacity/colour over life; streaks with a shutter). Use `blend: add` on dark plates.
- **Blend modes:** add (plus-lighter), soft_light, hard_light, color_dodge join screen/multiply/overlay.

## 16. Dialogue and podcasts

- **Read first:** `read_dialogue` gives speech regions (adaptive floor, about ±2 frames), speakers (pitch + spectral
  clustering, no identity; pass `speakers` when known), turns, pause statistics and filler candidates (flat-pitch steady
  vowels; ASR filler words when word timings are passed). `audio_profile` measures floor, speech level, SNR, 50/60 Hz
  hum, band balance, sibilance and loudness; `compare_to` returns only deltas.
- **Pause targets (measured finished edits):** 16-29 pauses ≥120 ms per minute, median 0.16-0.39 s, p90 0.29-0.50 s,
  longest 0.57-0.80 s, none ≥1 s, 8.5-13.7 % silence, about 0.1 fillers/min. `condense_dialogue` shortens pauses over
  `max_pause_s` to `target_pause_s`, removes fillers, cuts picture and sound together into a new project (time map
  kept) and can cover jump cuts with alternating punch-ins.
- **Cleanup chain:** HPF 90-120 Hz → de-hum (only when measured) → spectral denoise at the measured floor → mud cut
  250-450 Hz → presence +2..+4 dB around 3.5 kHz (the +11.6 dB seen on screen is extreme) → de-ess → compressor
  -23 dB 2.5:1 7/85 ms. Always compare floor and SNR: a presence boost plus make-up gain raised the floor 16 dB against
  7.8 dB for speech in the measured chain; `clean_dialogue` adds an expander automatically when that happens.
- **J/L cuts (measured in films):** straight cuts sit in the gap 12-14 frames after a line; conversational overlaps
  15-20 frames; reaction holds 45-123 frames of off-screen speech; scene pre-laps 43-102 frames; hard-SFX pre-laps
  about 29. `j_cut_audio`/`l_cut_audio` now accept up to 150 frames.
- **Podcast multicam (measured):** cut to the next speaker about 20 frames before their turn; the wide covers bursts of
  overlapping turns (about 3.5 s); shots 3.5-4.3 s. Social clips stand alone at 1 minute or less.

## 17. Colour: matching, secondaries, film

- **Balance every shot, then match to a hero** (`color_match`): per-channel gain/offset from channel percentiles, a
  5-point luma curve, saturation from the chroma ratio, and a skin secondary when skin hues differ. It reports
  residuals measured by applying the grade (good: |Δmid| < 2 points, cast < 1 %, chroma ratio 0.95-1.05, skin < 4°).
  Six cameras after their input transform alone still spread about 18 points in black and 33 in white.
- **Consistency before render** (`color_consistency`): flags mid ±6 points (about 1/3 stop), black ±2, cast > 2 %,
  saturation outside 0.85-1.15, skin hue ±8° against the group median.
- **Secondaries:** `grade.secondaries` are soft HSL keys (hue band with cosine edges, chroma and luma ranges) with hue
  shift, saturation and luma adjustments, baked exactly into the 3D LUT. `protect_skin` keeps the skin key out of the
  look (an unprotected teal/orange look cost skin 34 % chroma in the measured example).
- **Camera log:** slog3, logc3, logc4, vlog, log3g10, applelog, flog2, bmdfilm5 (18 % grey decodes to 0.18 for each).
- **Film:** `halation` (orange-red scatter around highlights, radius about 2-3 % of frame height), grain by `gauge`
  (16 mm about 2x the size and 1.5x the amplitude of 35 mm; blend overlay keeps grain in the midtones), gate weave,
  dust, a print look via LUT. Measured film-emulation black points 1.5-4 %, white shoulders 81-94 %.

## 18. Animation principles as data

- `animate` compiles verbs (hop, drop, slide_to, turn, rock, pop, hit, enter, exit) with a material (ui, stiff, rubber,
  soft) into keyframes and track modifiers. Measured rules it follows: anticipation about 3x the action (crouch 5,
  hold 4, launch 2-3 frames); x linear and y eased through an arc (decelerate up, accelerate down, no ease into
  contact); stretch only in the last ~5 frames of a fall; a 1-frame contact squash of about 1 + 1.5·v at constant area;
  2 frames of rebound stretch; bounce heights x0.33 then x0.26; overshoot about 0.65x the drag with a 5-frame period
  halving each cycle; a product pop 0 → 1.08 → 0.955 → 1.0 over 9/4/3 frames; a rock 5° → -2° → 0.6° → 0 in 5-frame steps.
- New tracks: `scale_x`, `scale_y`, `skew`, `squash` (width/height at constant area). `track_mods` per track:
  `inertia` (amount, period_frames, decay), `loop` (cycle, pingpong, offset), `wiggle` (amp, hz, seed).
- `motion_quality` samples the runtime and flags mechanical moves (peak/mean speed < 1.15; eased moves measure
  1.5-2.3), abrupt stops, straight paths on organic moves, area changes and twin layers.

## 19. Short-form and ads

- **Pace by events, not cuts:** cuts + punch-ins + graphic pops. Measured retention edits: 10.8-14.7 events/min,
  median gap 3.3-4.2 s, first change by about 2.6 s, opening about 2x the body. `event_profile` reads this from any
  video (validated against hand counts: 12.5/min vs 10.8, 15.1/min vs 14.7).
- **Emphasis punch-ins:** hard cut to x1.14 about the eye line (0.51, 0.31) on the first word after a pause ≥ 0.35 s,
  held to the next cut, about 0.5/min (`punch_in`; `ladder` alternates in/out for jump-cut-heavy talking edits).
- **Captions:** 1-3 words per page; `caption_style` karaoke | build (words appear on their timestamps) | keyword (only
  emphasis words); `emphasis` in the accent, `negative` in saturated red; `uppercase`.
- **Ad structure** (`ad_plan` / `ad_audit`, one measured commercial, so starting points): brand at 0 s, product by
  0.9-3 s, hero reveal by 2.4 s, sections about 3.6 s, offer tags at about 31 % and 52 %, a 0.6 s music drop before the
  main offer, a CTA end card ≥ 3 s (about 12 %) with logo and the bed ducked 15 dB, ≤ 4 words per line and ≤ 7 on screen.

## 20. Multicam, room tone, aspect, rigs, product shots, tracked windows

- **Multicam** (`multicam`): angles sync to the master by onset cross-correlation refined on the waveform (within
  ~0.2 frame on synthetic angles), speakers map to the single that hears them loudest, and the switch follows the
  measured rules: cut ~12 frames before a turn, ignore backchannels under 0.7 s, wide for rapid crosstalk (held ~3.5 s),
  shots ≥ 2.5 s (a too-early cut is held to the minimum, then made if the turn still runs), listener reactions in long
  monologues. The project keeps the continuous master audio.
- **Room tone** (`room_tone`, automatic in `condense_dialogue`): the longest stretch within ±3 dB of the noise floor,
  looped with equal-power crossfades, placed under every join so micro-fades never drop to digital silence.
- **Aspect adaptation** (`adapt_aspect`, profiles vertical / landscape / square / portrait45 = 4:5): footage to cover
  around its focus, layers placed proportionally into the target safe area (order and spacing kept), type scaled by
  the short-side ratio and shrunk until the longest word fits (FreeType metrics), pixel keys scaled per axis.
- **Follow-through** (`layer.follow`, needs a parent): a damped rotational spring that chases −k·v (air drag while the
  parent moves) and inertia on starts/stops; stiff preset: 5-frame period halving each cycle, overshoot ≈ 0.7× after
  the stop (measured 0.68×); soft preset: long lag and one big swing.
- **Product shot** (`compose_product`): slide in (strong ease-out) → rock and settle on the base (5° → −2° → 0.6° → 0,
  5 frames each) → constant turntable (`spin`) → a spot-light highlight sweeping across after it settles (keyed lights)
  → slow camera push. glTF/metallic models want `light` 0.3-0.5 and `studio=false`; an archival look (tritone,
  halation, 16 mm grain) can sit on the 3D layer.
- **Tracked windows** (`tracked_window`): a feathered adjust-layer window riding a `track_region` result or a planar
  `track_id`: color (gentle lift inside), blur (anonymise), spotlight (darken outside).
- **Typewriter script**: phrases typed at ~20 chars/s, deleted at 2× back to the shared prefix, a blinking block cursor.
- **Titles**: stacked titles get line height ≥ 1.2 so Vietnamese marks on adjacent lines never touch; documentary time
  cards use ≥ 26 px labels at 1080p (phone-readable).

## 21. Rigs, scene-referred colour, evidence in 3D, independent review

- **Two-bone IK** (`layer.ik` on the lower bone, whose parent is the upper bone): both bones rotate so `ik.tip` (a point
  in the lower bone's box) reaches the target layer's anchor — usually a null with keyframes. Law of cosines, exact to
  < 0.5 px; out of reach the limb straightens toward the target; `bend` picks the elbow side; `weight` blends with the
  keyed pose. Children of the bones (a hand) inherit the solve. The target must not be parented under the chain.
- **Drivers** (`layer.drivers[track] = {source, track, mul, add, mode, delay_frames, clamp, mix}`): AE-style expression
  links as data. A wheel rolls with its car (`rotate = x · 180/(π r)`), a shadow shrinks as its object rises, a character
  leans into its own speed (`mode: velocity`), a follower trails a leader (`delay_frames`). Cycles are rejected.
- **Scene-referred colour graph** (`process_color` with `graph`): decode camera log (or BT.1886 display footage) to
  scene-linear, grade in ACEScct (exposure in stops, white balance, ASC CDL, contrast about 18 % grey, saturation),
  apply a *look under the output transform* (a print-film LUT that expects Cineon — `print_film_cineon` is an original
  one), then the filmic (log) or BT.1886 (display) output. An empty graph on display footage is an identity. `window`
  nodes grade inside a feathered moving mask (box, keyed boxes or a track). `graph_checks` reports where 18 % grey, black,
  diffuse white and +2 stops land on the display.
- **evidence_3d** (explainer recipe): a scan or archival photo as a physical card (tilt, shadow), a slow push toward the
  region the narration points at, then a mark projected exactly from the final camera, a caption and the source line.
  The image stays the evidence: no LUT on the card.
- **Ink-measured stacked titles**: line height for stacked lines comes from the glyph ink (dot below vs breve/hat/hook
  above), not box metrics, and from proximity grouping: the gap to the other line must be ≥ 2.5x a mark's own gap to
  its letter, or the mark reads as belonging to the other line (a dot between Ạ and Ă's breve turned TRĂNG into TRẮNG
  with nothing touching). `audit_timeline` reports `diacritic_collision` with the needed value, and `text_over_push`
  when a plate under text scales ≥ 1.3x (re-check contrast at the end of the push).
- **Constant-speed pushes**: zooms interpolate on a log scale, so a linear push holds its perceived speed; chain pushes
  across punch-in cuts at one rate (the sample film: x1.45 push, x1.3 punch, push, x1.25 punch, push).
- **Entrances hold before they start**: a fade/rise/wipe with a delayed `start_frame` shows its start state until then
  (no blink).
- **Motion audit** merges holds into one span and flags `still_shot` (> 80 % still for > 3 s), `static_ending` (a final
  hold that never resolves to black) and `black_bands` (letterbox baked into a source); the timeline audit flags
  `same_clip_dissolve`.
- **Independent review**: run the `editvideo-reviewer` agent (rubric in REVIEW_RUBRIC.md) on a render or on the code;
  it returns P0/P1/P2 findings with evidence and the level to fix them at. The round-6 sample-film fixes came from it.

## 22. Narration → picture → rhythm, effect atlas, four real builds

- **beat_map after narration is placed.** For every spoken sentence it lists the shots under it (and whether they are
  evidence or illustration), the visual events while it is said, and on-screen text that repeats the words with its
  lag. Bring text in on (or just before) the word it echoes (`late_visual` > 1 s); give a figure or date spoken over
  illustration its number, source or evidence footage (`claim_without_support`); motivate a cut, reveal or move in any
  sentence ≥ 4 s with no event (`no_visual_change`). `rhythm.cv` < .25 over ≥ 5 shots is `uniform_rhythm`: size
  beats by content (short around a long held one). `motifs` lists styled elements that recur (same kind/font/size/
  colour) — keep a motif in one screen region and style so it reads as a callback.
- **Effects by preview, combos by purpose.** Each effect card shows a strip (source, t+10, t+30, t+52 in both engines)
  and `pairs_with`/`avoid`. Start from a combo when the purpose matches (archival_film for a dated insert,
  impact_title for one hard-landing title, documentary_push for a slow evidence push, fire_composite for elements shot
  on black) and keep one combo per moment; the `avoid` line names the usual misuse (a second entrance on an impact
  title, decode over Vietnamese marks).
- **Letter-spacing entrances stay on their lines.** `tracking` from a wide spacing is capped at export to what the
  box holds on the bundled font, so a title never wraps mid-entrance; widen the box if you want the full spread.
- **Narration offline.** `voice_backend=auto` tries Edge TTS, Piper, then a same-language Windows voice, and finally a
  timed silent placeholder (method `silent_placeholder`, estimated cues) so the edit can be planned and replaced by
  real narration later; `voice-backend.json` says what happened.
- **Interview radio edit.** `project_from_video(segments=[[a,b], ...])` in story order (not source order); punch in on
  the second of two same-angle answers (`punch_in` ladder steps from the held scale, so a wide shot is not a no-op);
  subtitles from the transcript, cut to the selects.
- **Vertical.** `adapt_aspect` keeps cards together (panel + caption + value; time-card rows): the group scales as
  one unit by the short-side ratio, so spacing grows with the type, not with the taller frame. For a vertical ad,
  put text where the plate is quiet at the *end* of each push (`text_over_push`) and keep it out of the platform UI
  zones (top bar, right rail and bottom bar, checked by `ad_audit`). Vietnamese on-screen density is counted in
  syllables (≤ 6 per line, ≤ 10 per text layer).
- **Both engines.** Render a finished project in Remotion and HyperFrames and compare *every* frame
  (`examples/round7/render_both.py`: SSIM + PSNR at 480 px). Sampling misses one-frame glitches at cuts and short
  dissolve dips; on dark or near-black frames SSIM swings on encoder noise alone, so a divergence is an SSIM dip that
  PSNR confirms (< 35 dB). Typography is checked separately at full size: per text layer, pixels where ink exists in
  one engine only (> 200 px is a real difference such as a clipped mark), and so are the four 8-px frame edges.
  HyperFrames needs every video clip declared
  as a static `<video>` (export and every render/snapshot refresh write them); a runtime-created video plays from
  the wrong source time.
- **Selects.** `project_from_video(segments)` returns `gaps` (silence ≥ 1 s, black ≥ 0.25 s inside a select): a reel
  slug between soundbites must be cut out, not kept as dead air. On a selects edit any time discontinuity on the same
  framing is a `jump_cut`; alternate wide/close across every cut (joins and punches alike).
- **Pixels.** `soft_upscale` reports fit x zoom per source: a 720p source covering 9:16 is already ~2.7x, so pushes
  stay small (a few %) and punches stay ≤ ~1.15; `adapt_aspect` caps inherited zooms to ~3x and steps a punch out
  rather than in when the cap would shrink it into a jump.

## 23. Reading holds, sentence strips, offline voice, pinned labels

- **Still is not dead.** A chart that draws in and then holds for reading is a reading hold, not a static frame;
  the audit measures the longest still stretch against the words and graphics on screen (~3 words/s + 1-2 s to take
  in a chart). Shorten a hold that runs well past its reading need, or spread the reveal over it.
- **Judge picture against words with your eyes.** `beat_map(strips=true)` returns one sheet per 8 sentences: start,
  middle and end of each sentence from the render of this timeline. Read it for claims the picture does not show
  (a splashdown said over a space view) and for labels that sit on the wrong thing.
- **Offline narration.** With Piper installed, `voice_backend=piper` (or auto when Edge is unreachable) narrates at
  an explainer pace and times every word from the audio (Whisper, local): beat_map, captions and cut-on-sentence
  work as with Edge. Check names and numbers by ear: ASR timing is an estimate.
- **Labels that stay on the thing.** Place the label where it belongs on its first frame, `track_region` the part
  over the source seconds the shot plays (from that frame), then `pin_to_track` (translation only). On a drone
  pull-back the buildings rise through the frame: place a name beside the building, not between two of them.
- **One take, many speeds.** Do not cut one moving take into shots at different playback rates: an instant x1→x2
  step reads as a jolt, a fractional rate judders, and a skipped second reads as a jump cut. Retime the take once
  with `retime_footage` `speed_keys` (smooth ramps, flow interpolation, motion blur) and play it at 1x; place labels
  at the output times of their source seconds. Fast-forward handheld footage only after `stabilize_footage`
  (mode lock), or the shake is multiplied by the rate.
- **Offline narration by ear.** `narration_unclear` (audit and beat_map) lists words an unprompted recogniser did not
  hear as written, with times: listen there; respell a word in `spoken_text` when the voice really says it wrong,
  re-plan, and compare the share. Above ~20% use another voice for delivery.
- **Time-lapse from handheld.** `stabilize_footage` mode lock with `region` on a RIGID part of the subject (a body,
  not liquid, a screen or a person: moving content drags the lock) and enough crop (`max_zoom` 1.3-1.4 on 1080p into
  a square or vertical) to reach `correction_capped: false`; then `retime_footage` with motion blur. The audit judges
  the effective speed (retime x playback rate) against `residual_px_over_frames` (< 2 px per output frame).
- **Silent edits.** `create_silent_project(profile, seconds)` gives an exact-length silent timeline for reels and ads.

## 24. TikTok / Reels / Shorts

- One platform table (`platforms.py`): organic UI zones (heuristic) and the published AD safe zones; the area clear
  on all three platforms' ads is x 120-888, y 288-1248 at 1080x1920. `review.SAFE`, `adapt_aspect`, `ad_audit` and
  `professional_toolkit` all read it.
- `shortform_audit` reads the rendered file: first frame, first change (<= 1 s), cut pace (0.19-0.52/s for talking
  heads; faster flagged), stills over 5.3 s, bars, loudness (-14 LUFS) and true peak, delivery spec, and with the
  project: text under the UI, first text (<= 2 s), key message (<= 3 s), caption coverage and word sync, contrast on
  the real plate, CTA for ads. It returns cover candidates and five frames with the platform UI drawn over.
- Captions: `word_captions` `word_animation` pop/bounce/rise and `outline`, rendered by the shared widget so both
  engines match; outlined captions drop the box by default; pages keep names and compounds together; `translations`
  adds a caller-written line in another language under the spoken words.
- Flash shots: a picture visible for under 0.3 s between two cuts (B-roll in/out included) is flagged by
  `audit_timeline` (`flash_shot`) and `shortform_audit` (`flash_cut`); `punch_in` never lands under or beside a
  full-frame B-roll.
- Talking heads: `reframe_footage` `auto_focus: faces`; `condense_dialogue` `windows` + `transcript`; `punch_in`
  `ladder` changes the framing at every cut in one take and caps the zoom by source resolution.
- `design_sound` `beat`: a 60-180 BPM bed (TikTok reports >120 BPM music with higher view-through) with its beat times.
- Evidence, templates and limits: [SHORTFORM_AND_FILM_RESEARCH.md](SHORTFORM_AND_FILM_RESEARCH.md#tiktok-craft-evidence-tools-and-limits).

## 25. Effect combinations by genre, many sources

- Choose material across many clips with `rank_clips`: windows ranked by motion, local action, sharpness and colour,
  each with its action peak (absolute source seconds) and motion direction; cross-clip match cuts (never two moments
  of one take); which clips are silent; a contact sheet. Look at the sheet: a peak is measured movement (a
  spectator's hand counts), not the moment that matters.
- Land accents on the music with `accent_sync(style)`: velocity, travel, food, product or nature (none). Drops are
  music-file seconds (default: loud peak entries); one stacked hit per drop (white flash, decaying shake, RGB split
  + impact/riser), a flash or light leak per phrase, a punch at most once per bar; re-runs replace.
- Slow motion on the action: `retime_footage` `peaks` (source seconds) slowed to `peak_speed` for `hold_s` with S-curve
  `ramp_s`, flow-interpolated; place the result at 1x. Hold a moment with patch `freeze_frame` (a flash and a punch-in
  on the still, the shot's look kept on every part); a freeze shot needs only its one source frame, so it can hold a
  clip's last frame.
- Stacks in one call: patch `apply_combo` (e.g. `impact_title` on a title). Two clips at once: `compose_edit`
  `split_screen` (rows in 9:16, columns in 16:9, grid for four). Recipe cards fade out as they fade in.
- Mute nature footage: `design_sound` `forest` / `rain` beds (<= 60 s, synthesized; say so in the credits), the
  ambience leading the picture cut (J-cut) and trailing it (L-cut).
- Templates: `professional_toolkit(platform=tiktok)` sports_velocity, nature_doc, food_short, city_montage.
- Check text against the footage: `audit_timeline` `low_contrast_plate` measures unplated, unoutlined text against
  the source frame under it (any aspect ratio); text on a plate is inset and centred by both engines.
- Evidence, the music hierarchy, the four builds and their lessons: [SHORTFORM_AND_FILM_RESEARCH.md](SHORTFORM_AND_FILM_RESEARCH.md#effect-combinations-by-genre-evidence-tools-and-limits).

## 26. Seeing what is in the frame; archival, science and product films

- `find_subjects` (offline OWLv2 + SigLIP, installed once with `allow_download` after the user agrees): `queries`
  ["rally car"] give per clip spans, share and the best view {at, score, box, area}; `best.box` seeds `track_subject`.
  `text` or `image` {path, at} rank windows by similarity. Boxes are source-frame shares: map them with
  `semantic.to_canvas` through the shot's fit and focus before placing anything (a 4:3 photo framed 16:9 moves them).
- `rank_clips(subject=...)` ranks by the subject's presence and size and reports `subject.at`, its clearest view.
- `compose_edit lower_third` `avoid: "gorilla"` takes the side clear of the detected subject.
- Archival stills: aim each 5-8 % move (`focus_zoom` amount and focus point) at the detected subject; crop a scan to
  its detected postcard or print (`focus_zoom` cut to fill); orient with the map, its zoom's fixed point on the feature,
  a `tracked_callout` on it. TIFF scans and images over 40 MP import as JPEG working copies with their credit.
- Vertical from wide renders (science, product, space): `find_subjects(queries, frame_for="vertical")` returns per
  subject a shot framing (`fit`, focus, a held `focus_zoom` and the subject's canvas box) that keeps it whole; in code
  `semantic.frame_subject(box, sw, sh, cw, ch, region=...)` keeps it inside the area the titles leave free
  (`inside_region: false` when no framing can: move the titles instead). A subject
  wider than a 9:16 crop is framed up from contain (zooming a shot out never shows more of its source); set the
  timeline's `design.background` to the footage's black so the bands disappear (`create_silent_project` uses its colour).
  Try a second query when one misses ("space telescope" missed the sunshield view, "spacecraft" found it).
- Product reveals: `compose_product reveal: "dark"` (rim light first, key light at `reveal_at`, fog on the floor, slow
  orbit); the camera fits the layer's aspect, so 9:16 works; `.gltf` models pack with `media.pack_gltf`.
- Pictures import as they are shown: old transfers with non-square pixels (PAL 720x576 shows 4:3), rotated phone video
  and EXIF-rotated photos become upright square-pixel working copies; sources with dropped frames render from a
  constant-rate proxy.
- Off-speed shots (any `playback_rate` other than 1) play a pre-timed 30 fps clip in both engines, frame-identical.
- Evidence and limits: [SHORTFORM_AND_FILM_RESEARCH.md](SHORTFORM_AND_FILM_RESEARCH.md#seeing-what-is-in-the-frame-archival-science-and-product-films).

## 27. Learning a film and making one like it; the picture first

- Learn: `learn register` the exemplar (local copy, its licence in `usage`), `anatomy` its parts, `evidence` to look,
  `distill` a blueprint whose targets the exemplar measured, then build, render and `learn conform` the render. The
  conformance number counts targets in range; read the misses and the features behind them, not the score (the first
  rebuild and a far better one both scored 0.786).
- Choose footage by picture before content: `rank_clips(min_look="B")` or `editvideo.look.measure(path, start, end)`
  per window. A C is upscaled (source smaller than the canvas), shaky (> 4 px per 1/15 s after smooth camera moves are
  removed) or noisy; noise is read spatially (flat pixels) and temporally (two aligned consecutive frames, which also
  reads night and textured footage); `noise: None` with the flag `noise unmeasured` means neither could look (a still
  of pure texture, a cut) and caps the grade at B.
- Before rendering, read `audit_timeline` for `repeated_picture` / `repeated_source` (a few clips on a loop; the same
  scene shown again from another moment counts, by ORB features, not only the same picture), `off_cadence_footage`
  (24/25/50 fps at 1x: set `frame_sampling: "flow"` on shots with camera movement; it renders slower, about 2 frames a
  second per window, cached; where a fast foreground or occlusion would ghost, the render measures it and takes the
  nearest source frame instead, logging the shot) and `matte_cuts_subject` (a letterbox bar across a face or a
  medium shot's head). With too little material, cut fewer, longer shots rather than reuse.
- Brands: ask `find_subjects` for "a brand logo" and "a soft drink advertisement sign" (scores around .15-.35) and
  skip those windows; a sign in every frame rules the clip out.
- Grade toward the exemplar per shot (saturation up to x1.35 where a shot is short of the target, nothing where it is
  already there); let the light fall at dusk (brightness about .88) and leave night alone.
- A selection script that applies all of this slot by slot: `examples/round12/build_travel_v4.py`.
- Evidence and limits: [SHORTFORM_AND_FILM_RESEARCH.md](SHORTFORM_AND_FILM_RESEARCH.md#learning-from-a-film-and-making-one-like-it).
