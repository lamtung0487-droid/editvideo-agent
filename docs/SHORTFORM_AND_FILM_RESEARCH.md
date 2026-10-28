# Short-form and AI film capabilities — research and implementation

Research checked 2026-10-17. This is a headless capability layer for a directing AI: schemas, persistent memory,
source selection, backend-valid requests and editable timelines. The caller supplies story and interpretation of
pixels/audio. No studio, hidden judge, engagement prediction or human approval workflow is introduced.

## Tóm tắt khả năng mới

- **Video ngắn:** AI đưa các đoạn đã xem, mục đích từng ý và giới hạn thời lượng; `sequence_plan` chọn tổ hợp phù hợp,
  giữ đủ các ý, dựng dự án nhiều nguồn với tiếng gốc để AI tiếp tục chỉnh chữ, màu, nhịp và âm thanh.
- **Phim nhiều cảnh:** `film_world` giữ hồ sơ nhân vật/đạo cụ/bối cảnh, trạng thái trước–sau từng shot, ý đồ máy quay,
  ảnh tham chiếu và lời thoại. AI đọc một shot để lấy gói yêu cầu hợp lệ cho công cụ sinh footage hiện có.
- **Ranh giới:** đây là khả năng điều phối và ghi nhớ cho AI. Gói prompt không bảo đảm model giữ đúng gương mặt,
  vật lý hoặc bố cục; lượt này chưa cài mô hình mới hay chạy thử sinh phim diffusion.

## Academic basis and engineering decisions

| Primary source | Relevant finding/design | EditVideo application | Boundary |
|---|---|---|---|
| [Smith, Projections 2012: Attentional Theory of Cinematic Continuity](https://ualresearchonline.arts.ac.uk/id/eprint/21187/) | Attention and perceptual expectations help explain continuity across edits, including match-action and the 180-degree system. | Explicit axis side and screen direction raise concrete continuity questions between declared shots. | These metadata checks do not model gaze or prove that a cut is perceived as continuous. |
| [VideoDirectorGPT, COLM 2024](https://arxiv.org/html/2309.15091v2), §3.1–3.2 | Separate a scene/entity/layout plan from generation, with consistency groups. | `film_world` stores entities, shot purpose, framing, camera, layout and state; compiles a packet per shot. | We do not implement or train Layout2Vid; a text layout does not enforce geometry in LTX. |
| [MovieDreamer, ICLR 2025](https://arxiv.org/html/2407.16655v3) | Hierarchical narrative modeling and rendering address different scales of coherence. | Persist film-level look/premise and shot-level intent; maintain state through the ordered narrative. | No autoregressive visual-token model, diffusion decoder or claimed paper performance is ported. |
| [MovieBench, CVPR 2025](https://arxiv.org/html/2411.15262v2) | Long narratives expose cross-shot character appearance and audio consistency challenges. | Character description, voice intent, reference paths and mutable costume/prop state remain explicit. | Voice intent is handed to finishing; no automatic cloning, lip sync or identity lock. |
| [Your Interest, Your Summaries, ICARCV 2024](https://arxiv.org/html/2410.14087v1), §III | Selection should reflect a query; generic importance need not match the requested subject. | `sequence_plan` takes caller-inspected candidates per story beat and relevance under a duration budget. | Our bounded search is an engineering adaptation, not FCSNA-QFVS inference/training or a retention estimator. |
| [GroundShot, arXiv preprint, June/July 2026](https://arxiv.org/abs/2606.20799) | Useful entity references and their retrieval matter across shots, beyond full-frame memory. | A shot packet lists first/previous entity appearances and identity assets to inspect before making its keyframe. | No automatic entity grounding, reference verification or generation-order scheduler from this paper is implemented. |
| [EM-Vid, arXiv preprint, May 2026](https://arxiv.org/abs/2605.23610) | Full-frame memory can mix persistent identity with transient context; entity-centric memory is an alternative. | Identity references stay separate from the shot's whole-scene `reference_image`. | No latent patch bank, sparse attention or noise-injection mechanism is implemented. |
| [FilmBench, arXiv preprint, July 2026](https://arxiv.org/abs/2607.24241) | Cinematic language and multi-shot continuity deserve attention beyond single-clip image quality. | Keep framing, camera, spatial intent, screen direction and narrative purpose available to the directing AI. | No FilmBench score or automated beauty verdict. |

These are design motivations, not evidence that EditVideo matches the papers' experimental results. The 2026 items
above are preprints; they are not presented as peer-reviewed publications. Current implementation has no new
model/weight dependencies, external downloads, paid calls or network service.

## Video ngắn: source selects with a story budget

1. `index_video`, `inspect_window` and `read_dialogue`/`transcribe` provide source times and actual frames/audio.
2. Caller AI defines beats by the message: hook → demonstration → payoff, question → reveal, interview answer →
   explanation, or another structure. A CTA and fast opening are choices, not mandatory grammar for every short.
3. `sequence_plan()` gives the request schema. Supply title, budget_seconds (1..180), optional minimum_seconds,
   profile/engine, and beats with candidate windows. Each candidate needs id, local path, start/end seconds,
   caller relevance (0..1) and reason; fit/focus/role/keep_audio are optional.
4. Bounded beam search chooses one complete window for EVERY beat, in beat order, under the frame budget. It can
   avoid overlapping intervals from the same source and require chronological order within each source. Both are
   configurable. It never silently drops a payoff, speeds up speech, pads time or trims a window to boost a score.
   It floors sub-frame tails to stay within source bounds; callers should select complete speech/action boundaries.
5. The result is a persistent `sequence-...` handle with exact output frames, source offsets, reasons and unused
   budget. `search_pruned` reports beam truncation: this is approximate search, not a global optimality claim.
6. `sequence_plan(plan_id=..., build=true)` creates a NEW project; `request=..., build=true` can plan and build in
   one call when the caller already inspected its inputs. Imported multi-source video and optional source
   audio become editable shots/clips with exact offsets. Existing narration/projects are untouched. Repeating a
   completed build returns the same project; a partial build reports its project for inspection rather than
   silently creating copies. A changed source hash requires a new plan.
7. Apply caption/layout/style/reframe/music tools already in the system, then export/render. Use cover deliberately:
   a fixed focus point is not dynamic subject tracking. Use `reframe_footage` when action moves out of the crop.

No frames are watched by the selector itself. `relevance` is caller input; it is not measured audience retention.
Do not confuse a feasible selection with a good story. The default `contain` preserves the source image until the
caller chooses a crop. A source without audio remains silent; generated narration is a separate operation.

## Phim: film world and shot packets

`film_world()` returns the exact schema. Save a caller-authored world:

```json
{
  "title": "The key",
  "premise": "A courier finds a door that only opens from the outside.",
  "look": "Warm side light, quiet camera, original fictional characters",
  "entities": [
    {"id": "linh", "kind": "character", "description": "Short black hair, green coat",
     "voice": "Quiet low voice", "initial_state": {"holds": "nothing"}},
    {"id": "key", "kind": "prop", "description": "Brass key"}
  ],
  "shots": [
    {"id": "pick", "scene": "room", "purpose": "Discovery", "action": "Linh picks up the key.",
     "seconds": 3, "entities": ["linh", "key"], "framing": "insert",
     "changes": {"linh": {"holds": "key"}}},
    {"id": "door", "scene": "room", "purpose": "A choice", "action": "Linh walks toward the door holding the key.",
     "seconds": 3, "entities": ["linh", "key"], "framing": "medium",
     "requires": {"linh": {"holds": "key"}}}
  ]
}
```

Entity kinds are character/prop/location. `description` records identity/style invariants; `initial_state`, shot
`requires`/`changes` record mutable story state. `reset_state` makes deliberate time jumps, costume changes and other
off-screen changes explicit. These are declarations, not measurements of generated footage. Continuity notes name
state mismatches, unmotivated A↔B axis changes and screen-direction reversal during declared continuous action.
Use `motivated_axis_cross` or an on-axis/establishing shot when intentional; the tool does not forbid expressive cuts.

Save returns `world_id` and `revision`. Shot summaries are paged (offset, limit=12, max 40) and include total/next_offset.
Update with both handle and current `base_revision`. Read `detail=true` for
the full editable document, or `shot_id=...` for one compact shot packet:

- story purpose, framing/camera, cast descriptions and voice intent;
- declared before/after state and previous/next narrative shot;
- first/previous appearances per entity for reference selection;
- entity identity references, kept separate from the current scene keyframe;
- a composed prompt and `generation_call` for the EXISTING `generate_footage` adapter, validated against its actual
  provider schema, with notes when the duration/resolution/backend options cannot work;
- finishing intent (dialogue/sound) and exact target frames for trimming the returned generated shot.

`generation` in a shot holds existing backend options (provider, preset, workflow, model, seed, dimensions, etc.).
Prompt, duration and shot reference are compiled explicitly. Local LTX uses enough 8n+1 frames to cover the target,
at most 161; longer shots return a reason to split them or select another configured backend. No request is silently
shortened or submitted. Missing scene reference images return a preparation note instead of silently switching to T2V.
The caller chooses whether to generate, polls the task, watches the result, and attaches the output. A valid request
does not establish installed models, provider availability, visual identity or sound synthesis.

After outputs are real local files, place them with `sequence_plan` (short sequences <=180 s) or timeline patches
for longer films. `film_world` can store 160 shots; assemble long works in scenes. Preserve reference identities
and declare state updates when revising one scene. Existing `learning_library` supplies related craft lessons.

## TikTok craft: evidence, tools and limits (round 9)

What makes a short vertical video hold attention, graded by evidence, and what the system builds and checks for it.
Grades: **S** spec/standard, **PR** peer-reviewed, **P** platform research (internal, correlational, mostly ads),
**A** academic, not peer-reviewed, **H** practice/heuristic. The same table lives in `editvideo/platforms.py`
(`EVIDENCE`) and every `shortform_audit` finding cites its row.

| Rule | Threshold | Grade | Source |
|---|---|---|---|
| Key text clear of the platform UI | ads safe area x 120-888, y 288-1248 at 1080x1920 (all three platforms) | S (ads) | TikTok/Meta/Google ad specs, [Socialync](https://www.socialync.io/tools/safe-zones) |
| Native vertical, full resolution | 1080x1920, no bars, >= 720 wide | P | [TikTok](https://ads.tiktok.com/business/en-US/blog/creative-that-drives-conversions) |
| Key message early | by 3 s | P | [TikTok creative tips](https://ads.tiktok.com/business/library/Auction_Ads_Creative_Tips.pdf) |
| First on-screen text | by 2 s | P | TikTok (text within 7 s +43%) |
| First visual change | by 1 s; frame 0 not black | H | [Meta feed attention](https://www.facebook.com/business/news/insights/capturing-attention-feed-video-creative) (~1.7 s per item) |
| Staying past 5 s | the early seconds carry the watch share | PR | [ECCV'24](https://arxiv.org/html/2410.00289v1), r=0.93 on 90k videos |
| Cut pace (talking head) | 0.19-0.52 cuts/s; faster lowered completion | A | [Dost & Huang 2026](https://archives.marketing-trends-congress.com/2026/pages/PDF/paper_professor_DOST_HUANG.pdf) |
| Captions for speech | >= 95% of speech covered | P | Meta: captions +12% view time |
| Caption geometry | <= 2 lines, <= 42 characters per line; ~0.33 s per word without voice | S | BBC / Netflix subtitle guides |
| Contrast | >= 4.5:1 (3:1 large text) | S | [WCAG 2.1](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum) |
| Sound in sync | +40/-60 ms | S | ITU-R BT.1359 / EBU R37 |
| Loudness | -14 LUFS, <= -1 dBTP; music >= 7 LU under voice | H | no published TikTok/Reels target |
| CTA (ads) | text CTA held >= 1.5 s at the end | P | TikTok conversion model |

Faster is not better: engagement peaks at a moderate shot count, and one experiment found faster pacing lowered
completion. No controlled evidence was found for karaoke captions, punch-ins, beat-synced cuts, sound-effect cues,
loops or progress bars: the system offers them as tools, never as audit rules.

**Workflow, talking head** (`examples/round9/build_talking_head.py`):
1. `reframe_footage` with `auto_focus: faces`: the main face held in a 9:16 crop, keeping the source sound.
2. `transcribe` the reframed clip.
3. `condense_dialogue` with `windows` (ordered selects, the strongest line first) and `transcript`: pauses go and the
   measured words are carried through the cuts, so `word_captions` runs at once.
4. `punch_in` with `ladder`: alternate in/out at phrase starts; every cut inside one take changes the framing (a
   select boundary would otherwise be a jump cut), and the zoom stays under ~3x source pixels.
5. `compose_edit` `word_captions` with `word_animation: pop` and `outline` (pages of 1-3 words that never split a
   name or a Vietnamese compound and never end on a function word); for viewers of another language add
   `translations` (caller-written lines under the spoken words). B-roll as full-frame video layers on the line that
   names it (two angles rather than one long hold; `punch_in` keeps clear of it); `design_sound` `beat` under the
   voice; `sfx_sync`; `audio_finish` on a short-form platform (-14 LUFS / -2 dBTP).
6. Render, then `shortform_audit` (rendered MP4 + timeline): look at its UI-overlay sheet.

**Workflow, listicle / how-to / before-after / POV / product demo:** `professional_toolkit(platform=tiktok)` returns
the template beats with time windows, the tools that build each and the evidence behind the structure
(`examples/round9/build_listicle.py`).

**Engines.** HDR sources (HLG/PQ phone clips) and sources with keyframes over 2 s apart are played by both engines
from a cached H.264 SDR proxy (tone-mapped, a keyframe a second): one HLG clip had made HyperFrames promote a whole
render to BT.2020 with washed colours and overlays lost after it.

**Limits.** Audits measure, they do not forecast retention. Caption timing is checked against the measured word
times, not against the audio itself. Visual cuts are counted from one-frame spikes of change: cuts inside fast,
handheld motion can be missed. Platform numbers are correlational and mostly from ads.
Face focus uses OpenCV's bundled Haar detectors: small, turned-away or heavily lit faces are missed (frames without a
face hold the last one). Text rules need the project timeline: there is no OCR of arbitrary videos. Contrast on the
render is a screen; `review_frames` measures exact glyphs. No trending-sound sourcing; the beat bed is procedural.

## Effect combinations by genre: evidence, tools and limits (round 10)

Which accents go together, where they land against the music, and how four genres differ. Pro editors rarely publish
numbers: most frame counts come from tutorials and forums (**H**), some are the system's defaults (**D**, not
sourced). Grades as above.

**What studies show (every genre)**
- Cutting on motion hides the cut: viewers missed about a quarter of cuts inside a scene, about a third when the cut
  fell on a sudden start of motion ([Smith & Henderson 2008](https://bop.unibe.ch/JEMR/article/view/2264), PR).
- More audiovisual accent alignment was rated more positively ([Rogers & Gibson 2012](https://eprints.hud.ac.uk/id/eprint/14946/),
  abstract only, no effect sizes); on real film clips exact alignment mattered less than on simple animation
  ([Lipscomb 1995](https://auditory.org/postings/1998/35.html)).
- Sync window: sound may lead by ~45 ms or lag by ~125 ms before it is noticed (ITU-R BT.1359, measured on lip
  sync): a visual accent lands on the beat frame or 1-2 frames before the transient, never more than one frame after.
- Visual beats are sudden decelerations or direction changes; landing them on musical beats makes footage "dance"
  ([Davis & Agrawala 2018](https://openaccess.thecvf.com/content_cvpr_2018_workshops/w49/html/Davis_Visual_Rhythm_and_CVPR_2018_paper.html)):
  land action peaks on beats, not only the cuts.

**Music hierarchy (synthesis; `accent_sync` implements it)**

| Music level | What lands there | Budget |
|---|---|---|
| Beat | cuts in high-energy sections; a punch-in 105-110 % | at most one light accent per bar |
| Downbeat | shot changes; ramp exits; whip or zoom landings | one per bar |
| Phrase (4 bars) | location or section change; title; a light leak (Screen blend, 3-4 f ease) | one per phrase |
| Drop | one stacked accent on the hero frame: white flash 1-2 f + shake decaying over 8-12 f + RGB split 2-4 f + impact, a riser before it | once per section |

Accents are placed from absolute music times (`round(t x fps)` through the music clip's start, offset and speed),
never summed beat lengths, so they do not drift; they snap onto a cut up to 2 frames before the beat or 1 after (3
before for food's cut punches), only while the music plays, and stay 8+ frames apart.

**Genre stacks**

| Genre | Structure | Accents | Amateur tells |
|---|---|---|---|
| Velocity (sports) | hook with the best play, a build of fast runs and a riser, the hero play on the drop, 2-bar runs, a freeze on the hero | fast (2x) between beats, a ramp 100 -> 20-30 % around the peak ([AE Juice](https://aejuice.com/blog/how-to-do-velocity-edits-after-effects), [Motion Array](https://blog.motionarray.com/learn/premiere-pro/premiere-pro-speed-ramping-tutorial/), H); the stacked hit on the drop only | shake or flash on every cut; every ramp the same; slow motion from 30p without interpolation; a visual accent with no sound |
| Wildlife mini-doc | exposition, tension, peak, resolution; ~4.4 s per shot ([Blue Planet II editor, RTS](https://rts.org.uk/article/all-about-editing-blue-planet-iis-editor-how-he-put-together-some-shows-iconic-scenes), H) | hard cuts, a dissolve only where time passes, slow motion only on the strike, ambience leading the cut (J-cut); most animal sound is recreated in post ([Northumbria](https://newsroom.northumbria.ac.uk/pressreleases/expert-comment-the-animal-sounds-in-most-nature-documentaries-are-made-by-humans-heres-how-they-do-it-and-why-it-matters-3297094)) | whips, glitch, flash; music burying the ambience |
| Food | the striking image first, steps cut on the contact frame ([Sonilo](https://sonilo.com/blog/guides/how-to-make-video-sync-with-music), H), repeated steps in quick succession, the payoff ramped slow with a small punch on the beat, an end card ([UT rhetoric-of-food](https://sites.dwrl.utexas.edu/rhetoric-of-food/2017/03/29/genre-conventions-videogif-recipes/)) | punch-ins on cuts once per bar; split screen for two crafts | glitch, shake or flash; step text under ~1.5 s |
| City montage | orient the viewer, one place per bar, one kinetic climax on the strongest musical moment ([Brandon Li, Musicbed](https://www.musicbed.com/blog/filmmaking/directing/the-art-of-the-travel-film-a-conversation-with-brandon-li/), H) | whips following the motion (7-10 f), match cuts on shape, a light leak per phrase at most | a transition on every cut; light leaks everywhere; static shots with nothing moving |

**Tools.** `rank_clips` (windows across many clips by motion, local action, sharpness and colour; each with its
action peak and direction; cross-clip match cuts; which clips are silent; a contact sheet), `accent_sync` (the
hierarchy above per style: velocity, travel, food, product, nature), `retime_footage` `peaks` (absolute source
seconds, slowed to `peak_speed` with S-curve ramps), patch ops `freeze_frame` and `apply_combo`, the `split_screen`
recipe, `white_flash` / `chroma_split` / `impact_shake` / `impact_zoom` in both engines, `design_sound` `rain` /
`forest` beds, and four `professional_toolkit` templates (sports_velocity, nature_doc, food_short, city_montage).

**Four builds** (`examples/round10/`, 27 Commons clips, three CC0 tracks): a 20 s rally velocity edit, a 39 s
wildlife mini-doc (16:9), a 25 s food short and a 24 s city montage. What building them taught the system:
- A measured peak is not a semantic one: the strongest "action" in one rally clip was a spectator's hand before the
  car arrived; the hero shot and the freeze were chosen on a contact sheet. `rank_clips` now measures local action
  (picture change after following the camera, 99.5th percentile), which found a cuckoo's take-off that dense flow
  missed, but the caller still looks.
- Commons footage often has a mute sound track (all six wildlife clips): `rank_clips` reports it, and the mini-doc's
  sound is a synthesized forest bed with rain leading and trailing the hippo shot, credited as synthesized.
- Engine parity bugs that only real material showed: HyperFrames ignored push/pull/pan on video shots and on the held
  frame under a transition; it started media at the unrounded source time (a whole shot one frame behind Remotion),
  then at Python's half-to-even rounding where Remotion rounds halves up; stills (freeze, transition posters) came from the frame after the one a player shows on 25/29.97
  fps sources; a poster seek inside a 24 fps clip's last frame found nothing.
- The short-form audit counted the edit's own accents (a 2-frame white flash) as flash cuts and read a dark outline
  on dark text as the text's backing; both are fixed, so its findings on these builds are the real ones.
- Units that read naturally were wrong: `peaks` counted from the window start (rank_clips reports source time),
  `drops` were music-file seconds without saying so (and one outside the edit crashed the sound step).

**Limits.** Timings are practice, not experiments; the studies support cutting on motion and aligning accents, not
specific frame counts. Peaks are measured movement, not meaning. `rain` / `forest` are procedural, not field
recordings. Reframing follows saliency and motion; small subjects in wide shots (a rally car on a hillside) stay
small in 9:16. Off-speed playback (e.g. 0.85x) of a 24 fps WebM source still differs between the engines by one source
frame on about a third of its frames (both are real frames; the browser's seek lands on the earlier one near a frame
boundary): measured, not yet fixed.

## Seeing what is in the frame; archival, science and product films (round 11)

Round 10's largest limit was semantic: the system measured motion but not content, so its strongest "action" in a
rally clip was a spectator's hand. Round 11 adds offline open-vocabulary sight, then builds three genres with it.

**Models (both Apache-2.0, pinned revisions, SHA-256 checked, 1.44 GB, offline after one approved download)**
- Detection: OWLv2 base/16 ensemble (`google/owlv2-base-patch16-ensemble`): LVIS rare-class AP 40.5 zero-shot, each
  text query scored on its own (so "is it there, and how big" is a direct reading), image-conditioned search possible.
  Chosen over Grounding DINO / LLMDet (fp32-only in transformers 4.57, box even when the class is absent), YOLO-World
  (GPL/AGPL), Florence-2 (no detection scores) and closed-vocabulary RT-DETR.
- Search: SigLIP base/16-224 (`google/siglip-base-patch16-224`): ImageNet zero-shot 76.2, about CLIP-L/14 quality at
  half the size, permissive weights (OpenAI CLIP's card puts deployment out of scope).
- Pitfalls handled in `semantic.py`: transformers 4.57 pads OWLv2 frames with grey (frames are padded black first,
  boxes read in the padded square); SigLIP text uses max-length padding; SigLIP squashes 16:9 to a square (the best of
  three square crops per frame); a detection needs a neighbouring sampled frame (lone hits are mostly false), NMS .5.
- Measured on round 10's material: "rally car" in the hairpin clip spans 2.5-4.0 s, exactly the window chosen there by
  eye; `rank_clips(subject="rally car")` puts that hairpin (best view 3.25 s) and the close Monte-Carlo pass first and
  the wide Welsh shots (car 3-5 % of the frame) after. 14 frames in 3.6 s on an RTX 3060 with the fast processor.

**Archival explainer** (practice, H): decide what each still is for; moves of 5-8 % toward the detail that carries the
sentence, mixed with holds, pans and a pull-back ([shoots.video](https://www.shoots.video/post/building-the-opening-of-race-to-the-clouds/),
[MasterClass on Ken Burns](https://www.masterclass.com/articles/how-to-use-the-ken-burns-effect-in-a-documentary));
maps orient the viewer, zooms as keyframed focus areas with a hold ([Mapcreator](https://support.mapcreator.io/how-to-create-a-map/how-can-i-create-an-animated-map));
a paper/click sound on each new photograph (Vox practice). The build aims every push at the detected bridge (boxes
mapped from the photo to the canvas through the shot's fit and focus: on a 4:3 photo framed 16:9 the bridge of an aerial
view fell outside a centred crop, so the frame was set on it), crops a scan to the detected postcard, and keeps facts to
well-documented ones.

**Science explainer**: one clear story, scientists check the facts, guide the eye to the feature that matters
([NASA SVS](https://science.nasa.gov/sciact-team/scientific-visualization-studio), [Ma et al.](https://vis.cs.ucdavis.edu/papers/Scientific_Storytelling_CGA.pdf)).
NASA media are not copyrighted, but its insignia and any endorsement are not to be implied
([NASA brand](https://www.nasa.gov/nasa-brand-center/images-and-media/)). The build decides each vertical frame from
detection (`semantic.frame_subject`): the telescope whole and as large as the space between the step title and the
fact line allows, on the black of space. The first attempt zoomed a cover framing out, which only shrank the cropped
picture (a shot's zoom never shows more of its source) and left it in a teal box: the canvas colour had stayed the
default. Framing up from contain, with the canvas set to the footage's black, fixed both; "space telescope" missed
the sunshield view where "spacecraft" found it, so the build asks both and keeps the query that saw it longest.

**Product reveal** (practice, weaker sources): glossy surfaces reflect the shape of the light, so soft strip lights
make the gradient highlight; a rim light separates a dark product from a dark ground; a dark reveal starts in black,
the rim builds, the key lands on the beat; a slow turntable ([PetaPixel](https://petapixel.com/how-to-create-gradients-of-light-product-photography/),
[Digital Photography School](https://digital-photography-school.com/tabletop-photography-walkthrough-or-how-to-create-an-eye-catching-product-shot)).
`compose_product` `reveal: dark` implements it; the camera now fits the layer's own aspect (a 9:16 frame had been
fitted as 16:9, leaving the product tiny).

**What building them fixed** (each with a test): off-speed shots (0.85x of a 24 fps clip) now play a pre-timed 30 fps
clip in both engines, frame-identical (HyperFrames' own extraction had shown the previous source frame on a third of
the frames; the render and snapshot paths had also overwritten the payload's timeline); archival TIFF scans and maps
over 40 MP import as JPEG working copies whose provenance keeps the original's credit; text is measured with the face a
browser draws (CSS font matching: a 500 asked of a 400/600/700 family is drawn at 400; it had raised "not bundled");
`.gltf` models with external parts pack to self-contained `.glb`; HyperFrames encodes at Remotion's CRF 18 (it had
written twice the bitrate); `accent_sync` is one atomic patch; `fetch_source` never waits more than a minute (it reports
when to retry). Rendering the three in both engines found five more: a 1921 film transferred at PAL 720x576 with
16:15 pixels was drawn 4:3 by the browser and 5:4 by frame extraction (it now imports as square pixels at its display
size), and its 157 dropped frames let the engines pick different neighbours at each gap (dropped-frame sources now
play from a constant-rate proxy); a contained shot dissolving in left the outgoing shot at its sides in HyperFrames
until the dissolve ended, and HyperFrames' held outgoing frame moved (its pan was applied about the zoom's focus, not
the centre) and lost its vignette; HyperFrames now nests each shot as Remotion does (transition wrapper, canvas
colour, picture with effects), which also keeps a held zoom through a push or whip. Remotion captured one blank
frame where a 3D layer starts (its asset wait was released before the canvas had mounted). The independent review
then found photos with EXIF rotation squashed by the scan working copy, rotated phone video read sideways by
detection, `frame_subject` placing subjects outside the free region, and detection tracks cut at 60 samples; all
fixed with tests. A second review, of the films and the fixes, found the HyperFrames restructure had turned wipes and
iris into cuts (a `-webkit-clip-path` reset erased the clip) and stacked attached layers differently (now nested in
the shot as in Remotion; a test checks every transition at its midpoint in both engines); the science short's 2.5x,
1.5x and 1.2x deployment shots juddered (fractional fast-forward now averages the frames each output frame covers,
and `motion_audit` reads periodicity in flow speed); the telescope was cut by straight edges in mid-frame where it ran
off its own frame (those edges now fade into the canvas); the map callout missed the bridge (measured on the
contained map, not on the cover framing it labelled) and ran off the frame (plates now stay in the safe area); a
caption's 1.7 km contradicted the postcard's printed 1800 m (the caption now names the spans and builders instead). `shortform_audit` on the product reveal
flagged its black first frame: the dark reveal now shows the rim's edge from frame 0 and lands the key light at 1.5 s.

**Limits.** Detection is presence and size, not meaning: an aerial reconnaissance photo was called a "map", a hand is a
"person", actions and relations are beyond it. Scores compare within a query. Its boxes are in source shares; map them
with `semantic.to_canvas` before placing anything on the canvas. The archival film's sound is synthesized.

## Learning from a film and making one like it (round 12)

The user upgraded learnkit and asked for a test of strength: learn from a beautiful film and remake it. The exemplar was
"THE BEAUTY OF VIETNAM" (Kirk Mihelakos, 150 s, studied locally, never reused). learnkit registered it, Claude
labelled six parts (cold open, establishing, montage burst, dusk turn, night, outro) and distilled a blueprint of 14,
then 15, measured targets; four remakes were built on licensed footage and conformed against it.

| Measure (blueprint range) | exemplar | v1 Commons | v3 Pexels | v4 senses |
|---|---|---|---|---|
| cuts on the beat (.65-1) | .785 | .70 | .857 | .879 |
| median shot s (1.4-2.4) | 1.75 | 1.47 | 1.23 | 2.4 |
| handheld shake px (0-1) | .26 | 1.06 | .20 | .14 |
| windows graded A (.6-1) / C (0-.06) | .78 / 0 | .67 / .067 | 1 / 0 | .91 / 0 |
| subject isolation (2-4) | 2.64 | 1.67 | 1.58 | 1.9 |
| saturation (.25-.55) | .379 | .318 | .255 | .24 |
| repeat_share (0-.15) | .091 | .222 | .467 | .057 |
| conformance (revision 5) | 1.0 | .667 | .80 | .80 |

**What each attempt taught.** v1 matched structure and rhythm and the user found it uglier than earlier work: its
footage, chosen by content (SigLIP) and motion, was phone video, shaky and upscaled. Nothing in the system read the
picture, so `editvideo.look` was built (resolution against the canvas, detail, noise, shake, isolation, exposure,
colour) and v2/v3 used Pexels clips gated by it. Two independent reviews of v3 then found what a demanding viewer sees
first: five people four times each in 25 s (61 % of shots nearly repeating another, the exemplar 9 %), judder on 13 of
23 clips (24/25/50 fps on a 30 fps timeline: 264 repeated frames, 29 of them in the opening glide), and a soft-drink
sign for 3.6 s; the code review found the new sense itself wrong in places (a smooth 24 fps pan graded shaky, clean
rice terraces graded noisy, grain inside letterbox bars unseen). Each became system work with a test: `repeat_share`
in the learned features and `repeated_picture` / `repeated_source` in the plan audit (0.638 on v3's plan, 0.644 on its
render), `frame_sampling: "flow"` and `off_cadence_footage`, `matte_cuts_subject`, the corrected look. v4's script
chooses every window with these senses; its opening glide has no frozen frame (29 in v3) and its cadence CV fell from
0.43 to 0.11, its repeats from .467 to .057, and HyperFrames matches Remotion with no divergent frame (SSIM mean
0.99).

**Measuring the measure.** Conformance counts targets in range: v1 (judged ugly) and a far better v3 both scored
0.786 on revision 4. The features behind the score said what was wrong; the score alone did not. `repeat_share`
first read the v4 render as .37: identical letterbox bars made every pair of frames alike; it now crops them
(v4 .057). The study's transition detector misses some whips and a dissolve between two dark night shots (v4 reads
0.67 transitions a minute for two whips and a dissolve). Noise is unmeasurable on frames made only of texture
(foliage, terraces) and is then None, not 0.

**Footage and practice.** Pexels clips are free to use without attribution (we credit the makers on screen, traced
from the API records). Professional editors put 24/25p footage on a 30p timeline with frame sampling by default and
optical flow where it shows (slow pans); FFmpeg's motion-compensated interpolation kept sharpness (blend: pulsing
softness) at about 2 frames a second at 1080p, so it runs per shot window and is cached. HyperFrames stalled at
readiness past six distinct videos because each `preload="auto"` element held one of Chrome's six connections per
host (`preload="metadata"` fixed it).

**Limits.** The blueprint rests on one exemplar (level: observation; 3+ successful works and an outcome make it
trusted). Isolation stays low: drone footage is sharp everywhere, and only footage shot with shallow focus fixes it.
With 25 clips the people section had to shrink (25 shots to 19) to stop repeating; more material is the real fix.
The look grade is a gate calibrated on this round's material, not a measure of beauty; composition, story and timing
stay with the caller. Motion interpolation can smear thin structures and fast occlusions (water, crowds): look at the
flow-sampled shots.

## Next capabilities after this increment

Prioritise entity-cropped visual memory with real source attribution; model-native multi-reference conditioning;
semantic event/action grounding from continuous windows; reference-aware shot generation with a configured backend;
dialogue lip sync and casting; then sound perspective and motivated match-on-action timing. These are research and
integration targets, not capabilities claimed by the two new tools. Renderer parity and unit tests cannot prove
character identity or narrative quality: inspect actual source and generated windows at the relevant times.

## Verification of this increment

263 tests passed, 2 optional tests skipped. Real MCP stdio passed in full (127 tools) and compact (7 entry tools)
modes, including paged film reads. A four-second vertical edit from two synthetic local sources rendered and decoded
in both engines; source colour order and 440 Hz -> 880 Hz audio order were checked from the actual outputs. A saved
two-shot film world passed the key-holding state into the next shot and produced a schema-valid generation request.
These are engineering checks, not evidence of narrative quality or generated character consistency. Full evidence
is local in `outputs/shortform-film-research/`; the reproducible integration script is `examples/verify_sequence_film.py`.
