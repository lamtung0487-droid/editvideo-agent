# Fast, precise AI editing and delivery

The system provides senses, editable techniques and resource-bounded execution to an AI director. It is headless.
No new model, browser studio, paid API or automatic aesthetic judge is required for these operations.

## Start with meaning, not the effect inventory

`read_narration`, `workbench`, `beat_map` and `direct_scene` share `plan/meaning.json`. For a custom build, empty
script/cues/word timing does not establish silence: narration may live in separate dialogue clips. Call
`bind_narrative()` for its exact schema, then bind original text, purpose, chapter, visual goal and sources to actual
shot/audio IDs. `clip_bounds` must exactly match referenced audio boundaries. A picture-only window uses
`authored_window`. Segment bounds never become invented per-word alignment. Native cues/timed words remain fallbacks.

Bindings have their own revision and immutable history. A media/timing signature invalidates old mappings when shots,
source offsets/rates or audio windows change; colour/layout-only edits keep the narrative usable. A supplied final
render is hashed once and carries a full picture signature. A changed layout cannot silently reuse its old picture.
Normal render and incremental-delivery source ZIPs preserve the narrative snapshot.

Use `direct_scene(project_id,start,end,inspect=true,listen=true)` for <=60s. The tool returns the local narrative,
previous/next meaning, three craft patterns, a real contact sheet and up to 30s of actual audio. Frames cover the
window and cut/reveal candidates; this is sampling, not continuous motion perception. For fast action use narrower
windows and the existing motion/temporal tools. Enlarged text needs the existing crop tool, not a smaller overview.
Evidence is cached by source file state/window/budget; missing image/audio artifacts are rebuilt. No vision model
or paid API is loaded: the host's multimodal AI interprets the returned ImageContent/AudioContent.
If the host cannot accept audio, leave listen=false and use the timed text with read_audio_events/waveforms;
do not claim to have heard it. Related saved lessons are retrieved from the actual scene goal, not just a broad
project name. Open the cited learning_library card and inspect its timestamped reference before adapting it.

`assets/craft/directing.json` has twelve practical patterns covering orientation, quantities, records, geography,
human detail, cause/consequence, rhythm, sound bridges, eye trace, parallel strands and returning motifs. Each says
what the viewer should understand, how to construct it, when to avoid it and which existing tools execute it.
Role matching orders the cards; it is not a learned aesthetic recommendation or proof of source truth.

Three patterns compile directly: `chapter_route`, `quantity_focus` and `evidence_compare`. Read `direct_scene()` for
the exact SceneDecision schema. Supply the question, rationale, heading, items, source and current revision. Text
is fitted against bundled glyphs, with explicit line breaks; unfit text fails before a render. Portrait and landscape
layouts differ. One quantity may retain a real image/video in a paired panel (asset ID plus source offset), so a
number need not erase the evidence. Source labels must name readable sources, not internal filenames.

Compilation changes no project. It persists the complete editable operations and returns a small plan handle.
Apply using `patch_timeline(project_id,base_revision,direction_plan=handle)`: project/revision and exact timeline hash
must still match. Then preview actual frames and the moving/sounding scene. Use an alternative arrangement when
the first composition fails the viewer's question; do not declare professional quality from passing software tests.

The documentary productions bind their authored narration with `narrative.bind_narrative`: the original text is
matched to the vo-* clip IDs, including clips cut from two real source segments, after audio finishing. A directing
trial (`directing.direct_scene`) builds a separate visual trial with its scene decisions as a new editable project,
ending before the next sentence and leaving the existing masters untouched. (The production scripts themselves are
private.)
Research sources and implementation boundaries: `assets/craft/directing-research.json`.

## Work on one meaningful scene

1. Bootstrap once, then `workbench(project_id,start,end,purpose)` for <=15 seconds. It returns the actual revision,
   local shot/layer summary, three craft cards, three inspection frames and available disk/commit memory. A declared
   purpose such as a sourced number, place, quotation or contrasting record routes to an existing recipe. Suggestions
   are textual matches, not semantic inspection of the film. No model loads or whole-film audits happen here.
2. Inspect actual source/frame/audio windows. State what the viewer must understand before choosing a technique.
   Common documentary choices: data_story for quantities; document_highlight for documentary evidence; history_map
   for spatial understanding; photo_3d for a purposeful move within a still; credibility_gap for a sourced contrast;
   news_montage for media escalation. A calm archival shot may need no additional effect.
3. Read just one schema with `workbench(recipe=...)`. Compose with dry_run, inspect touched frames, then patch at
   the returned revision. Read exact layers with read_edit_context/read_layers when the compact summary is insufficient.
4. Plan the places where picture, words and sound meet: opening, new evidence, changes of place/time, transitions,
   climax, pause and ending. Use beat_map strips for narration/meaning and sound tools for the motivated event.
   Do not substitute an event-rate target for the viewer's need to read and understand a documentary scene.

## Finish without rendering the film again

`finish_video()` returns DeliveryRequest. Supply project_id, current base_revision, a completed base_job_id and
caption_path (local cue JSON or SRT). An optional patch_frames=[start,end] is a half-open 30fps window covering all
changed layers. The task snapshots current data/captions, verifies the base video's hash and decoded technical
evidence, and rejects changed shots, canvas, media/3D layers or config: those require a normal new render.

For a supported layer edit, the repair expands to enclosing H.264 keyframes and uses the base job's immutable
custom source/payload. Only the changed layers are replaced, retaining render-time media proxies. At most two
browser tabs and a 256MB decoded-video cache render the bounded section. The other GOPs are copied. A splice is
accepted only with the exact total frame count and no repeated/skipped packet timestamps; final decoding also runs.
This supports Remotion H.264 base jobs. Unsupported changes fail visibly instead of silently reusing stale pictures.

Caption pages retain every word and the separation between raised archival translations and normal captions.
Nearby contiguous translation cues may share reading time and borrow bounded adjacent silence; report() measures
actual durations instead of stale cached cps. This is reading allocation, not English speech alignment. Check the
result against Vietnamese speech at key moments. Long passages that cannot fit are reported rather than cut.

Final MP4 has a default selectable subtitle stream with its ISO language; SRT and styled ASS travel beside it and
inside delivery.zip. Selectable text does not retain ASS's raised position in all players: use the ASS sidecar with
a capable player where source captions occupy the bottom, or create a separately burned-in delivery if required.
The ZIP preserves authored source, updates timeline/input, and describes incremental finishing in delivery.json.

The existing sound mix is preserved, with attenuation for encoded AAC headroom. Final AAC is remeasured, up to
three attempts; meeting a true-peak ceiling can lower integrated loudness. Report both. No claim of automatic
musical/emotional improvement is made. Normal final renderers also measure encoded peaks and correct audio alone
when needed. Previews avoid this final-only pass.

Poll get_media_task for progress, then inspect the actual final MP4, named timestamps and subtitle artifact. Renders,
Blender jobs and heavy model tasks share the store's admission lock, so they do not exhaust memory by starting
together. No original video is overwritten or unused media deleted. Store temp/cache/output on a volume with room.

## Cached 3D through MCP

`render_3d()` gives the contract for the three templates: terrain, globe and domino. Prepare local
height, texture and font inputs, and camera keys; nothing is downloaded behind your back. For terrain, use the
existing terrain/imagery preparation functions, or a prepared .npy height grid and satellite image. For a globe, use
a local equirectangular image. For dominoes, provide a map image of the bbox and the paths. The domino camera follows
the fall, so it needs no keys. The tool runs a registered template, never Python supplied by a prompt.

A terrain flyover must not be a still with a pin on it. The template gives it:
- `mist` lying in the valleys;
- `zones` glowing on the slopes themselves;
- `strikes`;
- routes that grow with a bright `head` and can `fade` to nothing;
- dashed borders (`dash_km`).

Put labels in the film, not in the 3D: with `labels_2d` the job writes `tracks.json` (each place's screen position
every frame, hidden behind a ridge or not). `blender.label_layers(tracks, start_frame, [{id, text, at}])` turns it
into crisp text layers that move with their place. With `pin=True` each label also gets a dot and a leader, so set
`stem: false` on the places in the template: a 3D stem would stay in the clip even when its label is dropped for
leaving the frame. Run `review.source_cuts` before rendering, because an archive window that crosses a cut shows
whatever follows the cut, for example a title card. On a map, a label avoids the lines leaving its city and the
words around it. Keep the camera low and oblique, but steep enough that the
frame's top edge still lands on the terrain: a bbox edge on screen reads as grey void. Leave depth of field off for
terrain, because the scene is in kilometres and Blender reads metres. Lower `shutter` for fast flights.

First render <=8 stills at percent25. Inspect composition, map labels, scale and camera path, then request full
frames. A content-based key covers script, params and input bytes even when task snapshot paths differ. Identical
inputs reuse the cache; changing bytes without changing timestamps invalidates it. The actual Blender PID is
recorded so cancellation/timeout can stop a detached launcher job. Completed clips attach with attach_media_result.
3D is an authored illustration, not proof of historical appearance or a survey.

## One look for the whole film: bible, finish, gates

Read `editvideo.style` (the bible, `assets/style/documentary_vn.json`) before you choose any colour, typeface, label
size, camera speed or sun. It covers:
- the palette, with one fixed colour for each side;
- the type pair;
- reading speed: Vietnamese 17 characters a second, with a 1.5 s floor (`style.hold_frames`);
- camera limits, light, atmosphere, render settings and the finish.

Blender templates receive the bible's defaults automatically. A scene still sets its own values when the story needs
them, but the bible is the default for every series.

- Map colours: render them with the Khronos PBR Neutral view, the bloc map's default, or draw them in the 2D layer.
  AgX bends hues and is meant for photographic terrain.
- Plates: render at 16-bit.
- Finish: every CG clip goes through `editvideo.finish` (`blender.encode(finish=True)`, the default in
  `terrain.blender_shot`). The finish softens slightly, adds a warm halation, grain that changes every frame,
  sub-pixel gate weave and a vignette. It also removes banding from dark gradients; the bloc map's CAMBI fell from
  6.6 to 0.003. Text is composited afterwards and stays clean.

Before you show a cut, run `review.delivery_gates(video, timeline)`. It checks, cheapest first:
- legal levels: about 1 % of a frame may stray;
- flashes: more than three a second over a quarter of the screen fails;
- still pictures and hard cuts to black;
- banding (CAMBI): a run of 12 frames over 5 fails, and a few frames in a fade do not;
- text held too briefly to read;
- text contrast against the actual rendered picture: 3:1 for labels, 4.5:1 for small type.

Before you render, run `review.source_cuts(timeline, assets)` on archive footage.

## Real ground, real period

- `terrain.elevation` reads Copernicus GLO-30 by default; SRTM is the fallback.
- `imagery.satellite(source=...)`:
  - `s2c2016`: 10 m, publishable with its credit;
  - `esri`: sub-metre, internal research only, flagged `internal_only` in the result.

  A camera 2 km above the ground needs about 2 m a pixel. Sentinel-2 at that height is soft, so fly higher or use
  `esri` for internal cuts. `blender_shot` sizes the texture from the nearest camera key (up to 16,384 px) and
  reports `texel`: metres a texel, metres a screen pixel, the magnification (over 2 comes with a note).
- The terrain look (blender_scripts/terrain_shot.py):
  - Blender's physical sky (multiple scattering) is lit by the same sun; `sky.model: "gradient"` keeps the old ramp.
  - Aerial perspective lives in the ground's shader: the distance from the camera fades the ground toward the horizon's
    colour, and the sky stays as drawn (`aerial: {strength, curve, start_km, depth_km, color, emit}`). It replaces the
    haze volume unless `haze.volume` is set. (A compositor mix on the mist pass painted far ridges black in Blender
    5.2.) Below the horizon the physical sky reads mirrored, and a shadowless fill from the side away from the sun in
    the bible's `shadow_tint` keeps shaded slopes from going black.
  - Cloud shadows drift over the ground in the shader (`clouds: {shadow, cell_km, drift_km}`), and roughness follows
    brightness.
  - Settings Blender rejects are reported in `settings_failed` instead of being swallowed.
- Satellite imagery carries its own light. `terrain.imagery_light` finds it (the hillshade azimuth that best matches
  the image's relief shading), and `blender_shot` keeps the 3D sun within `sun_tolerance` (10) degrees of it
  (`sun_note` says when it moved; `sun_from_imagery=False` to keep a chosen sun). On Điện Biên Phủ the photo is lit
  from 150 degrees: the bible's 330 fought it, and even 170-195 drew each ridge as a dark contour line (the photo's
  shaded slopes and the 3D shading disagree); at 150 the hills read as one solid relief.
- `period_maps` drapes 1960s US Army Map Service sheets (series L7014 Vietnam, L7015 Laos, 1:50,000) on the
  terrain, using their GeoPDF registration and the published Indian 1960 to WGS 84 datum shift.
  - Find a sheet's number in the ANU or USGS indexes. The USGS file is
    `store.usgs.gov/assets/yimages/NGA/<series><sheet>_geo.pdf`, where the sheet number drops the Roman quadrant to a
    digit (5651 IV becomes 56514).
  - Pass `period_map=[("L7014", "56514"), ...]` to `blender_shot`.
  - Render the map version and the satellite version with the same camera and dissolve between them: the map
    becomes the land.

## The archive montage: something huge is coming

`archive_montage` (`editvideo.montage`, research: `reports/Montage tư liệu kiểu bom tấn.md`) cuts real archive over a
driving cue toward a hit. The numbers come from the reference sequences measured on local study copies:
- World War Z's opening: the average shot falls from 2.36 s to 1.63 s to 1.25 s across the thirds, and to 0.6 s in
  its last ten seconds; the sound rises about 25 LU;
- Kong: Skull Island's titles: 0.67 s average, 45 one- or two-frame leader frames, dates in small tracked capitals;
- Godzilla (2014): redacted documents, a 13 LU crescendo, a white-out and near silence before a small title.

Give the shots in story order, each with the year it was shot and its own date and place, and mark one `role: climax`.
A `kind: reconstruction` or `graphic` shot can never carry an archive date or place, and `years: [first, last]`
refuses footage shot outside the story (the first sample opened on VNA's CG reconstruction of USS Maddox captioned
5.8.1964, and showed 1975 Saigon inside 1964-67). Vet every window with `review.clean_runs(path, start)` before it
goes in: it finds hidden cuts (a histogram jump or a structural break), dissolves, burnt or punched frames and dark
heads, judging each shot against its own level and the picture inside any black bars. Cards are optional:
- `teletype`: a dated line typed on screen;
- `redact`: a real document struck out except the words that matter;
- `stamp`: lands on the document;
- `headline`: the film's own words, never a newspaper's masthead;
- `counter`: a number that climbs, with its source;
- `quote`: a sourced line.

The recipe snaps cuts to the cue's beats and half-beats, frames some shots as projected film and adds leader frames
(at most two a second). No slot runs past its shot's usable footage, and no shot is a sliver: frames no shot can take go to
the next card or the gap. ONE line of type is on screen at a time (dates, teletype, counters, quotes); a date waits through
its own event or is dropped with a note, never captioning another event, and an overlay never crosses more than one card.
Every line stays up for at least the delivery gate's reading time (`hold` can lengthen it, never shorten it). A dated
card sits over footage of its year and between the dates captioned either side of it: "end of 1965: 184,300" over
carriers of 11.2.1965, before "15.4.1965 · Huế", read as 184,300 by February. A shot with its own voice (`sound`) can
carry `says` (the line, translated) and `says_by` (who, when): the subtitle is placed first, at the voice. It holds 0.6 s of black
silence, lands the hit, then fades to white, holds silence and shows a title. Small type gets a soft dark field, and
16 mm grain in overlay covers the body and the climax but never the gap or the end card (in normal blend it lifted
the black to RGB 42; it also removes the banding of compressed dark reels). `montage.score(sound_plan, music)`
returns the sound to import:
- a drone, a quickening clock and a Shepard riser that stops dead;
- a braam on the first shots of each threat run;
- typewriter, stamp and headline hits;
- the suck-out, a silent gap, then the hit with a tinnitus ring;
- the archive's own voices through a radio filter, low, in the first two thirds only. A shot's `voice_s` lets its
  line run on past its cut, over the next shots, to the end of the phrase (an L-cut, never past the shot's usable
  footage); a voice that runs on is speech, so it needs `says`;
- the cue, rising by thirds (crossfaded copies at rising gains) and cut dead at the suck-out.

`montage.arc(video, plan)` measures the render: the body rises by thirds, the hit clears the last 5 s by 8 dB, the
gap is digital silence.

The gap and the end card are declared on the timeline (null layers, `data.intent` `deliberate_black` /
`deliberate_still`), so `review.delivery_gates` reports them as intended; a declared black must measure black (luma
16 or less) and no marker excuses more than 3 s of black or 8 s of still. A gate that crashes is reported as an error
and fails the report without stopping the others. Sample: *Leo thang* (Gulf of Tonkin 1964 to the B-52s, 70 s, in
[docs/demo](demo/README.md)), the publishable cut built from National Archives film only (see below), with its licence
ledger for online use.

### Two more forms: the map and the dossier

`editvideo.montage_forms` adds the other two forms from the research table (docs/research/Montage tư liệu kiểu bom tấn.md;
design rules in docs/research/Nâng cấp thẩm mỹ toàn diện.md).

`map_matte` follows Dawn of the Planet of the Apes' opening, Capra's maps and Elastic's titles for The Man in the High
Castle:
- There is no cut: one camera move (`start` to `focus`, each `[lat, lon, zoom]`, zoom 1-8) runs over a map drawn
  like `history_map`, with Vietnam's archipelagos. A null layer carries the move and every map layer, matte and label
  rides it through `parent`: one set of keys, not a copy per layer (a dry run had returned 140 KB, half of it keys).
- Each region is cut from a country by `lat_range` / `lon_range` (the South: `[-90, 17.0]`). Its side's colour is
  tinted on the map from the first frame, before any footage appears, and its edge is about 2 px on screen.
- Archive plays inside its region through a hidden track matte that rides the same camera path. It is toned toward
  the side's colour with the highlights held down (a bright sky inside the land had read as a white blob, a lifted
  grade as fog).
- The clip keeps its own proportions, covering the region, and its `focus` [x, y] picks the part of the picture the
  region shows.
- A clip must name a place its region accepts and a date inside the clock. Footage inside a country's shape claims
  it was shot there, then, so a mismatch is refused. With `at` [lat, lon] the place is tested against the shape
  itself: Hà Nội added to the South's places is still refused. Without it, the result says the place is the
  caller's word.
- Clips come up as the date clock (`dates`, by year or month) reaches their date, one reveal at a time, and dissolve
  into the next.
- `clock_warp` (0.5) blends even time with an equal share for each clip and event, so empty years pass quickly. The
  first cut had 14 s of three dots. A stretch over 8 s with nothing new is reported (`longest_empty_s`).
- Sourced `events` light up at their dates. Their colour runs from cold to red, a few are named, and every one needs
  a source.
- Each name goes on the side that covers no other word or point and stays inside the frame, above the clock. Region
  names avoid the events (MIỀN BẮC had covered Hà Nội's dot). Archipelago names are sized for the first frame and moved
  above or beside their islands when below would leave the frame.
- In the last `drain_share` the map darkens and the `keep` points light again.

`dossier` follows the Godzilla (2014) titles, Kyle Cooper's Se7en and the Narcos titles:
- It uses the story's own documents and photographs, each with its own date and archive reference, about 2-2.5 s
  each, through dissolves.
- A document is shot close: the sheet is wider than the type is small, up to twice the frame. The camera travels
  down it from above the first mark, arrives a second before the dissolve and rests. The focal plane stays
  mid-frame: a softened copy is cut away along a feathered band that moves with the page. A page with no room to
  travel that way is pushed into instead.
- A photograph is shown whole and pushed into its `focus`, the focal plane opening around it.
- Each sheet has its own seeded grain, angle and vignette. A warm raking light slides across, and a drop shadow
  lifts the sheet off the desk.
- Pencil `underline`s are drawn as the camera reaches them, and the last one is drawn and read before the dissolve.
  Each is measured on the scan: it goes in the clear gap under the line of type it points at, and is refused when
  none fits (a line through "take all necessary steps" reads as struck out).
- `withheld` marks trace the release's own black bars, on at most two documents (more reads as a gimmick). A box that
  is not mostly dark on the scan is refused.
- One caption (date and what it is, plus the archive reference) is on screen at a time, and each item is held long
  enough to read it.
- It ends on a white-out held to the last frame (a fade back to the dark desk banded), near silence and a small title.

Each form returns a `sound_plan`:
- `score_map_matte` gives a drone in phrases with holes, a tick per event and the clips' own sound through a radio
  filter, falling to the floor in the drain.
- `score_dossier` gives a bed rising by thirds to the climax, with breaths where it drops out, a shutter under each
  mark, then silence.
- `form_arc(video, plan, form)` measures the render.
  - A map needs at least three holes, a drain 12 dB under the body, and footage that reads inside the land: a luma
    spread (5th to 95th percentile) of 60 or more inside the shape at each clip's middle frame.
  - A dossier needs a rise of 10-20 dB to the climax, measured on the bed and not on its breaths, and three or more
    near silences totalling 4-9 s.
- A dry run through MCP returns its ops summarised (SVG element counts, keyframe ends); compose without `dry_run` to
  apply.

Sample: `examples/public_domain/dossier_tonkin.py [--render]` rebuilds the dossier on any machine.
- "Lan rộng 1965-1968" uses National Archives footage inside the South at its own dates and places, with nineteen
  sourced events.
- "Vịnh Bắc Bộ 1964" uses the JCS FLASH cable of 4.8.1964 ("all subsequent Maddox torpedo reports are doubtful"),
  Johnson's midnight address and the joint resolution. Its documents are NARA scans fetched through Wikimedia Commons.

## Archive photographs in 3D, four layers of sound, a licence ledger

- `archive3d.shot(image, move="push")`: MoGe-2 (MIT, weights under `EDITVIDEO_MOGE`, default
  `<data drive>/EditVideo-data/models/moge`) gives the photograph's geometry in its own process.
  - The mesh is cut only where a cell straddles a jump in depth.
  - A plate behind it fills the near side of each edge with OpenCV Telea (algorithmic, logged as `fill_share`).
  - The plate is filled only under the mesh, inside its border, so frame 0 is the photograph everywhere; objects
    standing against the sky count as near (a bridge truss doubled when the plate kept it).
  - The move is measured, not estimated: a check render paints the mesh black and the plate magenta where the
    mesh covered it, and the move shrinks until the revealed band is under 1.5 % of the width thick.
  - `frame0_check` compares the first frame with the photograph framed the same way.
  - Blender renders it with emission under the Standard view, so frame 0 is the photograph (measured: 4.6/255 mean
    difference on an autochrome of the Doumer bridge).
  - Label it as an illustration.
- `archival_sound.plan(shots, moments)` builds Ribicoff's four layers for silent archive:
  - the literal events you saw in the frames (`helicopter`, `jet`, `artillery`, `gunfire`, `waves`, `crowd`… are new
    procedural kinds in `sound.design`);
  - one place bed across consecutive shots of the same place;
  - the `archival` treatment (an optical track's band and wow) when the picture is old or worn;
  - abstract moments only where named.

  `coverage()` lists shots left without a literal sound or a place.
- `ledger.classes()` reads negations and hedges ("not public domain", "no copyright infringement intended",
  "public domain?"), licences spelled with spaces ("CC BY NC") and editorial-only stock; a composite owes every part's
  duty. An asset the store cannot find is listed as unknown and blocks.
- `ledger.project_ledger(pid, use)` lists every used asset (footage, sound, fonts, voice) with origin, licence, class,
  seconds and where. Uses are `internal`, `online` and `broadcast`.
  - Blockers for online use: unknown, internal-only, no-derivatives, non-commercial.
  - Obligations are listed with each asset: credit, share-alike, AI/3D label, stock terms.
  - It writes `plan/licence-ledger.json` and `.csv`.
  - Archive cuts inherit their reel's record (`ledger.register_cut`); a render names its inputs
    (`ledger.register_render`; `terrain.blender_shot` does it).
  - The production's archive register recorded 688 cuts this way.
  - The Sentinel-2 2016 licence is still unverified, so terrain renders on it count as unknown until it is.
  - A licence can be written per part, `"picture: …; audio: …"`, and the ledger reads only the parts the film uses
    (`used` in each row): a video layer uses the picture, an audio clip or the project music the sound. A newsreel's
    picture can then be free while its music and narration are not.

## Public-domain archive: the National Archives' own record

`editvideo.pd_sources` finds and fetches films a publishable cut can use, with the evidence a clearance reviewer
asks for:
- `nara_search(words, record_group, years)` searches the National Archives catalog (the catalog site's own proxy, no
  key; undocumented, so a web page served in place of JSON raises instead of reading as no results) for films with a
  file online. Most reels carry NARA's shot list (`"15) LS MS A-4C taxiing onto catapult … VG"`), so a
  search is read, shot by shot and graded, before anything is downloaded.
- `nara_fetch(local_id=…)` downloads the reel from NARA's media server (about 0.8 MB/s a stream, against 25 KB/s from
  the Internet Archive mirror), keeps `nara-record.json` and `rights.json` (catalog link, record hash, object, licence,
  reasons, date read) beside it and registers it in the library. Cuts then inherit it through `ledger.register_cut`.
- `nara_rights(record)` decides picture and sound apart:
  - a film of a federal record group (Navy 428, Army 111, Marine Corps 127, Air Force 342, OSD 330, USIA 306…) is a
    US government work (17 U.S.C. 105): picture public domain, and sound too, or none if it is silent;
  - unless NARA marks it "Restricted - Possibly/Fully": then it is unknown. Marine Corps 127-R reels carry that mark
    for copyright, and so does the Universal Newsreel (collection "UN");
  - or the record names another maker in its title, description or contributors (a network, a newsreel, a foreign
    studio, a copyright). Federal groups hold other people's films: OSD's RG 330 kept 574 ABC/CBS/NBC newscasts, and
    USIA's "Guardians at the Gate" (RG 306, "Unrestricted") is a Hearst Metrotone production. In RG 330 and 306 a film
    counts only when its producer is a US government body;
  - "Undetermined" is NARA's usual mark on unedited service footage (540 of 577 digitised RG 428 Vietnam reels), not a
    warning;
  - anything else is unknown until a person clears it.
- NARA does not certify copyright (36 C.F.R. 1254.62); `rights.json` is the evidence, not a clearance. The mirror can
  disagree with NARA: "The Battle of Ia Drang Valley" has a Public Domain Mark on the Internet Archive and "Restricted -
  Possibly" at NARA, and the record wins.
- `search`/`fetch` still read the Internet Archive mirror for films NARA has not put online; `origin()` says whether an
  identifier is a federal record group, the Universal Newsreel or a private upload whose rights the mirror cannot speak
  for. `fetch` takes NARA's record (and its per-part licence) whenever the identifier names one; a Public Domain Mark
  alone is "unverified" and blocks until a person clears it.
- The clip cutter cuts windows at the reel's display aspect (NARA's 720x480 NTSC scans have
  10:11 pixels) and records what the catalog record vouches for: the production date at its own precision and whether
  the reel is titled a simulation. The `--pd` build refuses a caption more precise than that record unless evidence is
  named (Piranha's own slate reads 9/7), and any caption or voice on restaged footage.

The production fetched the Navy reels proposed for the escalation montage with `pd_sources`. A shot sheet tiles the
clean shots of a reel (`review.clean_runs`) with their times, for choosing windows by eye.

## Worker recovery

get_job reconciles a dead queued/running worker. Completion requires decoded technical evidence, matching artifact
hash and exact probed frame count; mere file existence is insufficient. A verified MP4 stopped during packaging
is recovered with an explicit packaging caveat. An incomplete or changed file becomes interrupted. Live workers
and cancellation are preserved. Old videos and reports remain available for diagnosis.
