# Internal audits of the EditVideo Agent (2026-10-27, HEAD f7920d0)

Three independent read-only reviewer agents audited the running system. Their findings, as reported (evidence: file:line in the repo, frames/crops under <data drive>/EditVideo-data/tmp/rv3d2d/).

## 1. Token economy of the MCP server (measured in-process)

Verdict: the compact tool surface is cheap (7 tools, 4,090 characters) but responses are not. A typical montage task (bootstrap, 4 discover calls, summary, 2 contexts, 4 patches, 2 audits, observe, motion and cut audits, 3 job polls, credits, SKILL.md and 3 routed guides) measured ~764k characters (~218k tokens) plus ~6k image tokens; ~43k tokens after the P0 and P1 fixes.

| Item | Characters | ≈ Tokens |
|---|---|---|
| patch_timeline / set_captions response (whole timeline) | 132,554 (70 s montage); 1,408,604 (29-min film) | 38k / 400k |
| read_project summary | 24,215; 160,499 (29-min) | 7k / 46k |
| read_narration page 1 | 77,982 | 22k |
| read_edit_context 0–8 s / 40–55 s | 33,722 / 53,257 | 10k / 15k |
| full host listing, 137 tools (descriptions 39,937 + schemas 33,090) | 93,718; compact host 4,090 | 27k / 1.2k |
| docs/PRO_WORKFLOWS.md (bootstrap routes to the whole file) | 84,648 | 24k |
| project_credits | 19,534 | 5.6k |
| inspect_window / aesthetic_packet defaults | 8×960×540 images + 341k/427k base64 audio | 5.5k image tokens each |

- P0: patch returns the whole timeline (agent.py:222 via mcp_server.py:109/135). Fix: a receipt.
- P1: read_project summary unbounded; read_edit_context sends ~25 default fields per layer (−61 % without them); read_narration repeats all cues per page and pages beats by the word offset (empty beats after page 1); cut_audit iterates shots only and silently passes a 48-cut layer montage; audio blocks sent by default (unknown whether Claude keeps them); no response-size tests.
- P2: audit findings padded with info rows; get_job repeats the folder in 17 paths; project_credits traced_assets opt-in; docs routed as whole files (PRO_WORKFLOWS 34 sections by round, SKILL.md has a 2.5k changelog); some list-returning tools skip _lean; default toolset is full; docs/AI_ERGONOMICS.md table stale.

Status (Claude, same day): P0 and the P1s above are fixed (patch receipt; summary paged, used assets only; sparse context; narration words packed, cues per page, beats with their own offset; picture_shots for cut/motion audits; audio only for a client that declares it; size tests).

## 2. System bugs and stability

Verdict: the render core holds (validator, atomic patches, frame grid, splice path).

- P0 ledger and credits skip the narration track (ledger._uses, resources.project_credits never read config.narration_id; from_video imports extracted source audio with no provenance). A reel with public-domain picture and all-rights-reserved sound comes out clear for online use. 105 projects use source-audio.wav as narration.
- P1-1 library catalog and sha cache written with plain write_text on F: (405 MB free); package() swallows credit errors and writes an empty CREDITS.txt.
- P1-2 Blender via the Store launcher: run() never checks the process is alive; default timeout 3 h; render3d waits 1800 s holding media-heavy.lock.
- P1-3 GPU sharing rule applied on some paths only (render jobs take media-heavy.lock; LTX media-gpu.lock; direct blender.run, MoGe subprocess take none).
- P1-4 montage clock and Shepard beds are capped at 60 s by sound.design: on a 125 s montage the clock ends 16.8 s before the suck-out.
- P1-5 every snapshot/render re-hashes all media (2.92 GB, ~33 s on c582339d), find_asset O(n²), credits 7.5 s per package.
- P1-6 blender.encode writes straight to shot.mp4 with no timeout and reuses any existing (possibly partial) file.
- P2: project music measured with duration_frames (a transition field) so it shows 0 s; three reading-time formulas (cinematic._reading_frames 3.5/2.5 words/s; review.reading_frames; text_too_brief ≥ 3.5 s); audiofx dead_air/uncovered_gap ignore intent markers; flashes() O(E²); process_alive checks PID only; Worker.submit only enqueues; montage avail max(8,…) lets a short shot's slot pass its footage; archival_sound literal clips can end 12 frames past the timeline; archive3d MoGe path hard-coded, reports an unrendered scale after 5 failed checks, full-res float arrays; pd_sources max_bytes ignored when all files exceed it, unknown-length truncation accepted; blender log handle never closed; history stores a full timeline per patch (289 MB over 207 revisions); ledger write=False still rewrites the sha cache. Test gaps: project_ledger, blender.encode, delivery.process, montage bodies > 90 s, lock admission.

## 3. Visual quality of 3D and 2D as rendered

Verdict: most of the "not beautiful" look has a few system-level causes; none needs a heavier renderer.

- P1-1 three of four showcase 3D scenes were rendered before the style bible existed (no view/colour depth/flow style in params): re-render (~2,450 frames, ~1 h EEVEE) and write the bible hash into done.json so delivery refuses older clips.
- P1-2 Trường Sơn flat and murky: luma 36–92/255; camera 44–110 km up looking nearly straight down; texture 3072 px over 351 km (114 m/px) magnified ~4.8× (terrain.py:222 sizes texture from height samples, not the camera). Fix: a texel-per-pixel check at each camera key, imagery at the matching zoom (16k fits in 12 GB), lower oblique camera, 50–85 mm.
- P1-3 3D sun fights the light baked into satellite photos (best correlation with light from 150°, worst 330°, the bible's sun); sky is a two-stop ramp (terrain_shot.py:183-194). Fix: de-shade by a hillshade at the measured angle or keep the sun within ±45° of it; physical Sky Texture driven by the sun.
- P1-4 map drape on steep low-lit relief reads as snow; hard seam where map sheets end; crumpled distant ridges (canopy in DEM ×1.6 under a 15° sun). Fix: multiply the map ~60 % over corrected imagery with paper tint and feathered sheet edges; smooth the mesh σ≈1–1.5 samples.
- P1-5 bloc map looks like plastic (flat colours, roughness .6, peak luma 95/255). Fix: emboss relief textures as bump, printed-paper roughness, brighter key.
- P1-6 domino imagery: grey halos around islands and satellite-pass seams (Sentinel-2 coastal tiles). Fix: sea masked by Natural Earth land polygons, one flat/bathymetry colour.
- P1-7 archive3d stretches at depth edges; measure_reveal counts only uncovered background. Fix: measure per-face screen growth, cut or feather faces growing > 2×.
- P1-8 dark text boxes have hard edges (engines/effects.js:105 radial gradient to the far corner leaves ~49 % opacity at side middles). Fix: linear masks on both axes.
- P1-9 history_map: outlines 23–26 px wide when zoomed (cinematic.py:1075 strokes scale with the camera), arrows cover labels (placement avoids only text and circles, cinematic.py:1147), red sublabel 2.0–2.3:1 contrast. Fix: constant on-screen stroke width, glow 2–3, arrows/routes as label obstacles, contrast check on coloured labels.
- P1-10 data_story comparison: icons sized per column (cinematic.py:1690-1695), so "26" looks 1.8× bigger than "81". Fix: one icon size per comparison.
- P1-11 archive colour swings between montage shots (red-vs-luma offset −34.8 … +35.5); the recipe only sets contrast/saturation (montage.py:311-312). Fix: neutralise each shot's cast at 50–70 % before the shared look.
- P1-12 then/now label on a white façade without backing. Fix: place over the darkest region or add a backing box.
- P1-13 interlace combing baked into a 480-line source that idet reads as progressive. Fix: a scaled-combing check.
- P1-14 half the style bible is read nowhere (camera.lens_mm, max_frame_widths_per_s, light.shadow_tint, atmosphere.mist_color, motion.*); Điện Biên Phủ used a 32 mm lens where the report advises 50–135 mm.
- P2: terrain route 0.35 km wide crosses the frame like a glitch (terrain routes lack constant screen width); data_story icon key 22 px under the bible's 26 px; v9 globe label ~17 px; archive3d mp4 tagged sRGB transfer; domino table edge against a void; autochrome specks.
- Keep: Điện Biên Phủ satellite flyover (warm low sun, valley mist, aerial haze, 2D tracked labels hiding behind ridges), domino physics/tiles/focus, bloc map key falloff and shadows, montage headline/redaction/quote cards, document underline, archive3d frame-0 check, finish stack, 16-bit plates.

## 4. Blender 5.2.3 facts probed on the machine (Claude, headless)

- Sky types: SINGLE_SCATTERING, MULTIPLE_SCATTERING, PREETHAM, HOSEK_WILKIE.
- EEVEE: use_raytracing, ray_tracing_method/options, use_fast_gi + fast_gi_*, shadow_resolution_scale, shadow_ray_count/step_count, volumetric_* (samples, tile size, shadows), taa_render_samples, motion_blur_*.
- View-layer passes include mist, z, position, normal, AO, shadow, diffuse/glossy/emit/environment, cryptomatte; EEVEE-specific bloom, transparent, volume_direct.
- Compositor: scene.compositing_node_group (5.x API); nodes Glare, Lensdist, Defocus, BokehBlur, Kuwahara, VecBlur, MapUV.
- Light linking on objects; Cycles devices: RTX 3060 CUDA and OptiX.
