# Explainer kit

Craft notes and tools for science and technology explainers: a presenter or narration carried by motion graphics, real
data and footage. Techniques were studied frame by frame from a professionally produced physics explainer
(CERN, "Particle collisions – episode 1", kept locally in `data/references/` for study only; none of its imagery or
text is reused). The notes below describe the techniques in general terms and map each one to a tool.

Tools: `editvideo_explainer_catalog()` lists recipes and fields; `editvideo_compose_explainer(project_id, base_revision,
request, dry_run)` compiles one recipe into ordinary layers that render identically in Remotion and HyperFrames.

## What makes this genre read as professional

1. **One idea per beat, one focal element per frame.** A stat line, a diagram, a plot: never two competing graphics.
   Black or near-black limbo lets a single element carry the frame; the background returns when the idea needs place.
2. **Continuity over cuts.** The reference has only seven hard cuts in 3¾ minutes. Ideas flow by camera moves,
   zoom-throughs into the next scale, elements that move into a new role (a big label shrinks into the header of the
   next diagram) and dissolves through the presenter. Cut when the subject changes, not to add energy.
3. **Numbers are performed, not shown.** A distance grows as an arrow while its number counts in sync; a big number
   lands, then multiplies into a wall to make scale felt; a counter in a HUD card keeps ticking while the scene plays.
4. **Typography is quiet and consistent.** One clean sans family, mostly regular weight with **one emphasised phrase**
   in bold; centred bottom stat lines; small boxed labels; generous spacing. Emphasis comes from weight, not colour or
   effects.
5. **A small, fixed palette with meaning.** Cyan for the thing being explained, white for neutral elements, one warm
   colour (orange or red) for energy or the highlighted finding. Colour changes signal state changes (white → red when
   the same diagram is now "the other case").
6. **Abstract first, then evidence.** A flat diagram explains the mechanism; a real plot or real footage proves it,
   with a hand-drawn mark on the exact place to look.
7. **Analogies get real imagery** (sand through fingers, a coastline from above) and are measured on screen so the
   comparison is concrete.

## Technique → tool

| Technique | Tool | Notes |
|---|---|---|
| Stat caption with one bold phrase | `stat_line` (text markup `**strong**`, `==accent==`) | One line, ≤3 words/s, bottom-centre, shadow for footage |
| Distance that grows with a counting label | `measure` | Arrow grows from the middle; the label uses the same frames and easing so number and length agree |
| Mechanism diagram (particles, signals, decays) | `diagram` | Wave connectors for radiation/signals, arrows for flow, dashed for virtual/uncertain; ripples on emission |
| One among many, counting by halves | `unit_grid` | Wave-in from centre, glowing highlight with ripple, scanning band, bracket counts |
| Real data, then "look here" | `plot` + `highlight` (or `annotate` over an image of a plot) | Points stagger in left to right, fit line draws after the points, hand-drawn ellipse last |
| Mark something on footage or a still | `annotate` | ellipse, underline, box or arrow; draw in 12–18 frames, hold, never pulse |
| Concepts building a relationship | `chips` + `dividers` | A chip moves/shrinks into the header, new chips stack over a divider (fraction layout); light theme on bright backgrounds, dark on dark |
| Scale that words cannot carry | `number_wall` | Hero number lands, then becomes rows drifting in alternate directions |
| Live technical readout | `hud_card` | Small caption + counter on a coloured panel; slides in from its edge |
| Accelerator bunch, beams, swarms | `particles` preset `bunch` / `stream` | Glow dots (white core, coloured halo), screen blend over dark plates |
| Collision / event display | `particles` preset `collision` | Curved tracks drawn out from the vertex with a flash; mix two track colours |
| Space, depth, quiet background life | `particles` preset `starfield` | Low count, slow drift, twinkle ≤ .6 |
| Zoom-through to the next scale | shot transition `zoom_through` + film `speed_lines` layer over the transition | Keep speed lines ≤ 1.5 s; intensity .5–.8 |
| A light source that feels optical | film `flare` with `center` on the source | Intensity ≤ .6 on footage; one flare per shot |
| Number readouts in general | `counter` data `group: " "`, `style: count/roll/scramble`, `align` | roll for "precise machine" numbers, scramble for data being computed |
| Shares of a whole | `pie` (optionally `donut`, `pop` one slice) | Sweeps clockwise from 12 o'clock in ~24 frames; the popped slice slides out along its bisector after the build; % labels last |
| Comparing a few values | `columns` | Baseline grows from the centre, bars rise as strokes 10 frames apart, values land on top; flat (butt) bar ends |
| Big canvas, many elements (maps, collages) | `camera_stage` | Stops every ~2 s, 18-frame moves with bezier [.7,0,.2,1], drift after landing, velocity motion blur, `step_frames: 2` for the hand-made look |
| A word as a window, then into the picture | `text_window_zoom` | Footage through the letters; flies through the thickest stroke (never a counter) to full frame, then the same footage continues unmatted |
| Deep zoom (orbit → country → city) | `camera_stage` with `zoom_space: log` (default) and stop `move: land/dive/glide` | Zoom changes by equal ratios and the centre follows 1/zoom, so the target approaches steadily instead of crawling then swooping; up to 40×, keep children vector |
| A jump in time (investigative/map docs) | `doc_timecard` | Tracked label (QUÁ KHỨ / HIỆN TẠI / place), mono year rolling from the previous one, accent rule; same corner all film |
| Chapter progress through a long film | `motif_progress` | Ticks on a line, done chapters filled, the current lit with a ripple and named; reuse at every chapter break |
| A document or archival photo as evidence | `evidence_3d` | Card in 3D with shadow and tilt, slow push to the region that matters, exact projected mark, caption + source line; no grade on the evidence |
| Documentary/map grade | effect `tritone` | Shadow → mid → highlight colours unify archive and satellite imagery |

## Timing that held up

- Entrances 6–12 frames, snappy or smooth easing; exits shorter than entrances (6–10 frames).
- Draw-on lines and arrows 12–20 frames; measurement growth 40–60 frames so the count is readable.
- Diagram order: node, connector (12–18 frames), child nodes, then ripples; label each node 4 frames after it appears.
- Hold every finished graphic at least 1.5 s before the next change; hold a key number 2 s.
- Chips: enter one at a time 30–40 frames apart; a move/shrink takes ~14 frames with snappy easing.

## Failure modes

- Two graphics competing (tracks behind a diagram, a plot plus a HUD). Give each its own beat.
- Bold everywhere. Only one phrase per line is emphasised.
- Chips with dark ink on dark footage (use `theme: dark`) or light chips on bright plates without an outline.
- Counters that change width while counting jitter when left-aligned; recipes centre them with `align`.
- Dot grids with dots under ~6 px shimmer when scaled; the recipe warns.
- Illustrative data presented as measured. Label models and illustrations as such (e.g. "mô hình quỹ đạo tròn").

## Verify

`compose_explainer(dry_run=true)` → read notes/measurements → apply → `snapshot_code` on the returned `inspect_frames`
(sheet) → after rendering, `motion_audit` and `cut_audit`. Check legibility of every label on the actual plate.
