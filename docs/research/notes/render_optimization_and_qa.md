# Headless Blender 5.x render optimisation on one RTX 3060 12 GB, and automated visual QA for rendered documentary video

Research date: 2026-10-27. Scope: (a) render speed/quality settings and Blender 5.0-5.2 changes, (b) passes/compositing/EXR, (c) colour management for Rec.709 delivery next to browser-rendered 2D graphics, (d) automated no-human quality checks, (e) caching/reproducibility.

Source-access note: developer.blender.org, docs.blender.org, www.blender.org and code.blender.org all returned HTTP 403 to the fetch tool in this session. Blender facts below therefore come from search-result snippets of those pages, from secondary coverage (CGPress, Digital Production, 80.lv, iRendering, itsfoss), or from devtalk/projects threads. Each is marked. Where a fact would need the primary page to confirm, it is listed under Gaps.

Local context (for the report writer): the repo's current Blender shot script already renders EEVEE with `taa_render_samples` 32, `use_gtao`, `volumetric_end` 400, `volumetric_tile_size` "4", `volumetric_samples` 64, volumetric shadows only when mist is on, motion blur on, AgX view transform, and a Cycles fallback of 64 samples with denoising — [<repository>/editvideo/blender_scripts/terrain_shot.py lines 507-530](F:/EDIT%20VIDEO/editvideo/blender_scripts/terrain_shot.py). The repo also already has a Real-ESRGAN (`realesr-general-x4v3`) restore path with a sha256 content-hash cache key — [<repository>/editvideo/restore.py lines 26-101](F:/EDIT%20VIDEO/editvideo/restore.py). The owner's memory notes record EEVEE at about 0.65 s/frame for the existing terrain shots with Blender 5.2.2 headless.

---

## Q1. Render optimisation: EEVEE vs Cycles OptiX, sampling/denoising, textures, headless tips, s/frame on RTX 3060, Blender 4.2-5.2 changes

### Takeaway
For documentary terrain flyovers on a 3060, EEVEE (Next) remains roughly an order of magnitude faster per frame than Cycles, but EEVEE volumetrics regressed badly in 4.2 and are scene-dependent, so mist/haze should be kept cheap (coarse volume tiles, few steps, or faked with the mist pass in compositing). Cycles is the "hero shot" engine: Blender 5.0's null-scattering volumes remove step-size tuning, 5.2 LTS adds a tiled/mipmapped texture cache for huge satellite textures, and OptiX temporal denoising (Python-only operator on multilayer EXR) is the built-in answer to per-frame denoiser flicker.

### Cited Findings

**Benchmarks / seconds per frame on RTX 3060**
- RTX 3060 Blender benchmark score 2,302 (aggregator, updated May 26 2026); per-scene OptiX single-frame estimates derived from Blender Open Data medians: Junkshop 26.03 s, Monster 17.23 s, Classroom 36.73 s. An older version of the same page listed 2,306 — [Renderjuice RTX 3060 for Blender](https://www.renderjuice.com/gpus/rtx-3060-for-blender). These are aggregator numbers, not the official Open Data figure.
- CGDirector's table lists RTX 3060 Ti at 3,012 (for scale vs the plain 3060) — [CGDirector benchmark results](https://www.cgdirector.com/blender-benchmark-results-updated-scores/).
- Anecdote: a user rendered 2048x2048 frames in EEVEE Next at 18 s/frame on an RTX 3060 with volumetrics, and estimated Cycles at "at least 10 minutes per frame" for equivalent sharpness — [Blender 4.2 EEVEE-Next Feedback thread (devtalk)](https://devtalk.blender.org/t/blender-4-2-eevee-next-feedback/31813?page=45) (single anecdote, no scene details).
- Simple-scene comparison: Cycles 1:26 vs EEVEE 0:06, GPU and volumetrics unstated — [iRendering, Blender 4.2 EEVEE Next vs Cycles](https://irendering.net/blender-4-2s-eevee-next-and-cycles-comparison/).

**EEVEE Next volumetrics and settings**
- Bug report: EEVEE Next renders volumetrics "between 15 and 20 times slower" than legacy EEVEE; one reporter's RTX 4070 Ti took nearly 40 min/frame on 4.2, vs about 1:10 on an RTX 3070 in 4.1 — [projects.blender.org issue #125364](https://projects.blender.org/blender/blender/issues/125364) (via search snippet; page 403 to fetcher).
- The slowdown is scene-dependent: an RTX 4090 user saw one scene go from 39 s (legacy) to 2 min 57 s (Next) — [EEVEE-Next Feedback thread](https://devtalk.blender.org/t/blender-4-2-eevee-next-feedback/31813?page=49).
- EEVEE volumes are evaluated in 3D textures sized by Resolution and Steps: smaller tile resolution increases VRAM and quality; more Steps increases VRAM and quality; samples are distributed along view depth; Distribution shifts samples toward the camera; Max Depth caps surface intersections for the accurate method and "will create artifacts if it is exceeded" — [Blender manual, EEVEE Volumes](https://docs.blender.org/manual/ja/dev/render/eevee/render_settings/volumes.html) (search snippet).
- EEVEE shadow settings: Steps = shadow-map samples per shadow ray; Rays = shadow rays per light — [EEVEE-Next manual update PR #104816](https://projects.blender.org/blender/blender-manual/pulls/104816/commits/33b962904577308a1d87480f5110730f34519cc9).
- EEVEE motion blur: more Steps (time slices) cost more render time; with multiple steps the render sample count is rounded up to the next multiple of steps; adding steps lets you reduce Max Blur (post-process blur distance) — [Blender 4.2 manual, EEVEE Motion Blur](https://docs.blender.org/manual/en/4.2/render/eevee/render_settings/motion_blur.html). Alpha-blended surfaces and volumetric effects do not get correct velocity and are not correctly blurred by the post-process blur; use accumulation (steps) for them — [Blender 4.0 manual, EEVEE Motion Blur](https://docs.blender.org/manual/en/4.0/render/eevee/render_settings/motion_blur.html).

**Cycles sampling, denoising, light tree**
- Adaptive sampling: typical Noise Threshold 0.1 to 0.001 (lower = less noise); 0 lets Cycles pick an automatic value from the sample count; Min Samples 0 (default) is derived from the threshold — [Blender 4.2 manual, Cycles Sampling](https://docs.blender.org/manual/en/4.2/render/cycles/render_settings/sampling.html) (snippet).
- Light tree caveat: custom falloff, ray visibility and complex shader setups (including textures) are not accounted for in the light tree and can increase noise — [Blender dev manual, Cycles Sampling](https://docs.blender.org/manual/pt/dev/render/cycles/render_settings/sampling.html) (snippet, possibly machine-translated).
- OIDN on GPU since Blender 4.1 for NVIDIA GTX 16xx/TITAN V/RTX; Junkshop denoise 0.078 s on RTX 3090 vs 1.224 s on an i9-13900K CPU; can be disabled to save VRAM — [Blender 4.1 Cycles release notes](https://wiki.blender.org/release_notes/4.1/cycles/) (snippet). Cycles denoiser prefilter options are none/fast/accurate — [Cycles device_denoise source](https://projects.blender.org/archive/blender-archive/src/commit/89c7c115cebb2ac0aaaeb98eb95decc7b5a129c8/intern/cycles/device/device_denoise.cpp).
- Flicker: per-frame denoisers ignore neighbouring frames, which causes flicker; OptiX temporal denoising was added in Blender 3.1 — [BlenderNation, OptiX temporal denoising](https://www.blendernation.com/2022/01/10/optix-temporal-denoising-support-added-to-blender-3-1-alpha/). Usage: enable the "Denoising Data" pass, output "OpenEXR MultiLayer", render the animation, then run `bpy.ops.cycles.denoise_animation()` (Python-only, not in UI); the EXRs are rewritten with the denoised sequence — same source.
- Tester reports (anecdotal): OIDN and standard OptiX are not temporally stable at 100 samples; OptiX temporal helps but leaves unstable areas; turning Animated Seed off helped OptiX temporal at 4096 spp but introduces structured, frame-locked patterns at low sample counts; adaptive sampling "kind of acts like an animated seed"; a noise threshold of 0.2 is far too high — [devtalk "Taking a look at OptiX 7.3 temporal denoising"](https://devtalk.blender.org/t/taking-a-look-at-optix-7-3-temporal-denoising-for-cycles/18656?page=6).

**Blender 5.0 (Nov 2025) changes relevant to rendering**
- Cycles volumes: new default "null scattering" algorithm reduces artefacts in overlapping volumes and removes the need to hand-tune step size / max steps; smoke/fire use less memory via NanoVDB; OptiX denoising quality improved; Random Walk SSS multi-bounce; "Experimental" feature set removed, with Adaptive Subdivision now production-ready — [CGPress, Blender 5.0 released](https://cgpress.org/archives/blender-5-0-released.html); [Digital Production, Blender 5.0](https://digitalproduction.com/2025/11/20/blender-5-0-its-here/) (secondary coverage; official Cycles notes 403).
- EEVEE 5.0: Light Probe Volume backface culling was inverted since 4.2 and is now fixed, so 5.0-saved files bake differently; View Layer overrides (material/world/samples) now supported — [Blender 5.0 EEVEE release notes](https://developer.blender.org/docs/release_notes/5.0/eevee/) (snippet). A secondary summary claims material compilation up to 4x faster — [tutkit.com (DE)](https://tutkit.com/de/blog/688-blender-50-grosses-rendering-update-mit-neuen-render-pipeli) (treat as best case).

**Blender 5.2 LTS (released 14 July 2026, supported to July 2028)**
- Cycles texture cache: generates `.tx` (tiled, mipmapped) files in a `blender_tx/` folder next to each image; enable Render > Performance > Texture Cache + Auto Generate; tx files regenerate automatically on change; colour space and filtering follow node usage; unused images not used by the last two render tiles are evicted; trade-off is extra disk use and a small render-time cost — [80.lv, Blender 5.2 texture cache](https://80.lv/articles/blender-5-2-lts-introduces-new-cycles-texture-cache-system); [Digital Production, 5.2 targets texture-heavy renders](https://digitalproduction.com/2026/05/12/blender-5-2-lts-targets-texture-heavy-renders/); [devtalk Cycles Texture Cache feedback](https://devtalk.blender.org/t/cycles-texture-cache-feedback/43725).
- EEVEE 5.2: Screen Space Raytracing pipeline reworked; energy-conservation fixes mean some scenes render darker than 5.1; new Backface option for screen-space GI; instancing-heavy (CPU-bound) scenes up to 2x faster; shadow pool options of 1.5 GB and 2 GB; camera ray visibility for lights — [Blender 5.2 LTS EEVEE notes](https://developer.blender.org/docs/release_notes/5.2/eevee/) (snippet); [gamedev.net 5.2 LTS](https://gamedev.net/news/blender-52-lts-release-r4468/); [Digital Production 5.2 LTS](https://digitalproduction.com/2026/07/21/blender-5-2-lts-lands-with-node-physics/).
- Principled BSDF gains a Thin Wall mode — same sources.

**Headless command line**
- Cycles add-on options go after `--`; valid devices: CPU CUDA OPTIX HIP ONEAPI METAL (append `+CPU` for hybrid); example `blender -b file.blend -f 20 -- --cycles-device OPTIX`; `-a` renders start..end, `-s`/`-e` set the range; `--cycles-print-stats` logs memory and time — [Blender 5.2 manual, Command Line Arguments](https://docs.blender.org/manual/ja/5.2/advanced/command_line/arguments.html) (snippet).

### Inferences
- Engine choice per shot type: EEVEE for most terrain flyovers (the pipeline's ~0.65 s/frame is ~25-50x faster than Cycles' 17-37 s/frame benchmark range on a 3060); Cycles only for hero shots where volumetric light shafts, accurate GI or sharp displacement matter, rendered after a still preview passes QA.
- Mist/haze in EEVEE: the 4.2+ volumetric regression and the doc's VRAM/quality relationship suggest keeping `volumetric_tile_size` at 8 or 16 for distance haze (low-frequency), modest `volumetric_samples`, and volumetric shadows off unless god-rays are the point. For plain aerial perspective, a compositor mist-pass blend is near-free and has no temporal noise. Volumes also do not get correct post-process motion blur, so if a volume moves relative to camera, use motion-blur Steps > 1 and set `taa_render_samples` to a multiple of Steps.
- Cycles animation recipe (to be validated on the 3060): adaptive sampling with noise threshold around 0.01-0.02, enough base samples that the denoiser is not inventing detail, render to multilayer EXR with Denoising Data, then `bpy.ops.cycles.denoise_animation()` for OptiX temporal denoise. Avoid per-frame OIDN on low-spp animation, which testers repeatedly report as flickery.
- Large satellite textures: on 5.2.2 (the pipeline's Blender), the texture cache is the first lever for 8k-16k orthophotos in Cycles; it does not appear to apply to EEVEE (EEVEE relies on GPU texture limits). For EEVEE, pre-tiling/downsampling the orthophoto per shot to what the camera footprint needs is the equivalent move.
- Because 5.2 EEVEE may render darker than 5.1 and 5.0 changed probe baking, cached EEVEE plates must include the Blender version in their cache key (see Q5).
- Render-at-lower-res + upscale: the repo already has Real-ESRGAN, but Real-ESRGAN is a per-frame GAN and hallucinates texture differently per frame; on terrain (high-frequency detail) that is a known flicker risk. Safer: render EEVEE at native 1080p (cheap anyway) and reserve upscaling for archival footage. No primary source tested Real-ESRGAN temporal stability on CG flyovers.

### Gaps
- Official Blender Open Data median for RTX 3060 (site not reached; only aggregator values).
- No measured EEVEE Next volumetric s/frame on a 3060 for a terrain + mist scene; no confirmation whether #125364's regression was fixed in 5.x (page 403).
- Persistent Data (`render.use_persistent_data`) speed-up numbers for animations were not found in any source this session; the feature exists (keeps scene data on the device between frames) but benefit on a 3060 is unmeasured.
- Official text of Blender 5.0/5.1/5.2 Cycles release notes (403); details above rely on secondary coverage.
- Whether EEVEE in 5.x has any adaptive-subdivision/displacement path or texture streaming equivalent: not found.
- No source on what professionals do regarding Real-ESRGAN vs Blender-native upscaling of CG animation; no temporal-stability benchmark of AI upscalers on rendered terrain.

---

## Q2. Render passes, compositor (mist, AO, glare, lens distortion, film grain) and multilayer EXR for later grade

### Takeaway
Render a multilayer EXR with the passes the later grade or QA needs (mist/depth, AO, vector, denoising data for Cycles), then do mist blend, glare, lens distortion and grain either in Blender's compositor or downstream. Blender 5.x reshaped the compositor (node-group assets such as an official Film Grain group, which a user thread places in 5.2), but primary release-note confirmation was not reachable.

### Cited Findings
- Multilayer EXR is a hard requirement for OptiX temporal denoising (Denoising Data pass + "OpenEXR MultiLayer" output) — [BlenderNation](https://www.blendernation.com/2022/01/10/optix-temporal-denoising-support-added-to-blender-3-1-alpha/).
- The Z pass was renamed to "Depth" in the Blender 4.x/5.0 cycle, and changes to Sky Texture, volume scattering, SSS and Voronoi can look like colour problems when moving files across versions — [iRendering, Why renders look different in Blender 5](https://irendering.net/why-your-renders-look-different-in-blender-5-aces-display-transforms-and-what-changed/).
- EXR files need correct colour-space interpretation in the receiving application, and the viewer's OCIO config and "View as Render" affect appearance — same source.
- Compositor assets: a CG Cookie thread says a film grain node group is new in Blender 5.2; another user reports the Glare node no longer has a "relative" option in 5.1 — [CG Cookie community thread](https://cgcookie.com/community/22694-for-anyone-trying-to-follow-along-in-blender-5-1) (user reports, not official). Add-on listings reference "Blender's official Film Grain asset" and an official sensor-noise compositor asset — [Superhive Compositing FX](https://superhivemarket.com/products/compositing-fx) (vendor page).
- A vendor claims its chromatic-aberration tool goes beyond "the upcoming 5.0 implementation" of Blender's Lens Distortion node — [ADC Automotive FX docs](https://superhivemarket.com/products/adc-automotivefx/docs) (vendor claim, indicates the node changed in 5.0).

### Inferences
- For an AI-driven pipeline, keep grain, glare and lens distortion out of the Blender render and apply them in the 2D finishing step (or a separate compositor pass on the EXR). Reasons: (1) film grain and per-frame noise defeat flicker/temporal QA and make cached plates non-reusable across looks; (2) grain inflates H.264/H.265 bitrate needs and causes banding/blocking when starved; (3) one grade across Blender plates and browser graphics is easier if plates arrive "clean".
- Minimal pass set for terrain documentary plates: Combined, Mist (or Depth) for haze/aerial perspective and depth-aware QA, AO for contact grounding, Vector for motion-blur QA or later vector blur, plus Denoising Data for Cycles. Store as half-float multilayer EXR for hero shots; for EEVEE bulk shots, 16-bit PNG/ProRes with mist baked in is probably enough.
- Mist pass gives a deterministic, noise-free haze that can be tuned without re-rendering, which also suits the "still preview before full render" pattern.

### Gaps
- Official 5.0/5.1/5.2 Compositing release notes (403): exact list of new/changed nodes (Glare modes, Lens Distortion rewrite, Film Grain asset, node-group-based effects) not confirmed from primary sources.
- EEVEE pass availability in 5.x (e.g. whether Vector/Mist/AO passes behave identically to Cycles) not verified this session.

---

## Q3. Colour management: AgX vs Filmic vs ACES in Blender 4.x/5.x and consistent sRGB/Rec.709 delivery alongside browser 2D graphics

### Takeaway
Blender 5.0 adds selectable working spaces (Linear Rec.709 default, ACEScg, Linear Rec.2020), ACES 1.3/2.0 view transforms alongside AgX and Filmic, and HDR displays. For SDR documentary delivery next to browser-rendered graphics, the simplest consistent path is Linear Rec.709 working space, sRGB display, AgX (or Standard where exact colour matching with UI graphics matters), 8/10-bit output, then one consistent BT.709 tagging at encode.

### Cited Findings
- Blender 5.0 working spaces: Linear Rec.709 (default), ACEScg, Linear Rec.2020; converting a file between working spaces is approximate and usually needs manual fix-ups — [itsfoss, Blender 5.0 released](https://itsfoss.com/news/blender-5-0-release/); [iRendering Blender 5 colour article](https://irendering.net/why-your-renders-look-different-in-blender-5-aces-display-transforms-and-what-changed/).
- ACES 1.3 and 2.0 workflows supported; ACES 2.0 view transforms sit alongside AgX and Filmic; full official ACES configs can be installed via the `OCIO` environment variable — [itsfoss](https://itsfoss.com/news/blender-5-0-release/); [Linuxadictos](https://en.linuxadictos.com/Blender-5.0-arrives-with-revamped-color-management--ACES-1--3--2--0--HDR--and-a-wide-gamut-for-video-and-images..html).
- HDR displays: Rec.2100-PQ, Rec.2100-HLG, AgX HDR; HDR viewing needs a compatible monitor plus the Vulkan backend on Windows/Linux — [itsfoss](https://itsfoss.com/news/blender-5-0-release/).
- Choosing an ACES view transform does not switch the working space to ACEScg; "AgX is a practical starting point"; Filmic remains for legacy looks; ACES 2.0 is for ACES pipelines and the article advises against switching "solely because it is available"; suggested SDR setup: Linear Rec.709 + AgX + sRGB PNG/JPEG output — [iRendering](https://irendering.net/why-your-renders-look-different-in-blender-5-aces-display-transforms-and-what-changed/).
- Texture colour spaces: colour textures sRGB; normal/roughness maps Non-Color — same source.
- Matching Blender versions, working spaces and OCIO configs across machines keeps renders consistent — [itsfoss summary via search](https://itsfoss.com/news/blender-5-0-release/).

### Inferences
- AgX (default view since Blender 4.0) desaturates and compresses highlights; that is good for sunlit terrain but means a brand colour typed into Blender will not render as the same sRGB hex as the same colour in a browser overlay. For map labels, coloured borders or UI-like elements rendered in Blender, use the "Standard" view transform (pure sRGB OETF) on a separate pass or view layer, or keep them in the 2D (browser) layer. Use AgX only for the photographic terrain plate.
- Browsers render CSS colours as sRGB; most video players decode Rec.709 with BT.1886 (approx. gamma 2.4) while sRGB images assume approx. 2.2, so the same 8-bit values look slightly darker/more contrasty in a video player. Since both the Blender plates and the browser graphics end up in the same encode, they shift together; the important thing is to (a) never mix "sRGB-tagged" and "709-tagged" intermediates in the final mux and (b) set explicit BT.709 primaries/transfer/matrix flags at encode so players do not guess (e.g. ffmpeg `-color_primaries bt709 -color_trc bt709 -colorspace bt709`). This is standard practice but not sourced this session.
- Do not adopt ACEScg/ACES 2.0 for this pipeline unless graded footage arrives in ACES: it adds a second OCIO config to keep in sync with no SDR-delivery benefit, and conversions between working spaces are approximate per the sources.
- Pin the OCIO config with the Blender version in the cache key; a config change silently changes every plate.

### Gaps
- Official Blender 5.0 colour-management release notes (403): exact list of display devices and whether "Rec.1886" / "Rec.709" display entries exist in the default config was not confirmed.
- Whether Blender's 5.x video output (FFmpeg) writes BT.709 colour tags itself was not verified.
- No source found comparing AgX vs Standard for matching overlay graphics specifically.

---

## Q4. Automated quality assessment of rendered/edited video (flicker, aliasing/shimmer, banding, motion smoothness, NR-VQA models, text legibility, saliency) and what Netflix/YouTube QC checks

### Takeaway
No single model covers it; a practical gate stacks (1) a fast general NR-VQA score (FAST-VQA/DOVER, ~0.81-0.84 SRCC even on rendered-game video), (2) an explicit flow-warped temporal-instability metric, since naive frame differencing is near-useless for flicker (SRCC 0.19), (3) Netflix CAMBI for banding, (4) rule-based checks (contrast, pan speed, black/frozen frames). LMM scorers (Q-Align/OneAlign, the new Q-ReAlign) are good coarse judges but slow; licences matter (pyiqa is PolyForm Noncommercial).

### Cited Findings

**Rendered-video-specific evidence (most relevant paper)**
- ReVQ-2k: 2,000 rendered clips (~8 s, 60 fps) from 15 Unreal Engine 4/5 scenes with varied AA, post-processing, shadows, textures, resolution scaling (FSR, DLSS, TAAU) at 720p/1080p/2K; distortions include noise, block artifacts, moiré, blur, aliasing, false edges, flicker, ghosting, "moving jaggies"; 57,450 cleaned ratings — [No-Reference Rendered Video Quality Assessment (arXiv 2510.13349)](https://arxiv.org/html/2510.13349v1).
- Baselines on ReVQ-2k (SRCC/PLCC): VSFA 0.771/0.762, CNN-TLVQM 0.772/0.779, GSTVQA 0.834/0.823, SimpleVQA 0.780/0.796, DOVER 0.814/0.820, FAST-VQA 0.840/0.850, MBVQA 0.812/0.829; proposed two-stream metric 0.879/0.882 — same source.
- The proposed metric = FAST-VQA (Swin-T, fragments: 8 clips x 4 frames, 7x7 grid of 32x32 patches) + a temporal-stability stream using dense optical tracking for motion and disocclusion maps, then warping and differencing at 1-, 2-, 3-frame gaps; runtime "typically over ten seconds per video", mostly motion estimation — same source.
- Ablation of the temporal stream (720p): no motion/masking SRCC 0.187; motion only 0.779; motion + disocclusion masking 0.831 — same source. No code/dataset URL was given on the page.

**General NR-VQA models**
- DOVER: overall score in [0,1] plus technical and aesthetic sub-scores (normalised N(0,1) per dataset); batch command `python evaluate_a_set_of_videos.py -in DIR -out CSV`; CPU time per video DOVER 3.6 s, DOVER-Mobile 1.4 s; DOVER-Mobile 9.86M params and under 1.9 GB VRAM; PLCC KoNViD-1k 0.883, LIVE-VQC 0.854, LSVQ_test 0.889, LSVQ_1080p 0.830 — [DOVER GitHub](https://github.com/vqassessment/DOVER). Licence files include an S-Lab licence — same source.
- FAST-VQA (ECCV 2022) samples small space-time fragments instead of all pixels for speed; needs a GPU; research licence reported by a secondary source — [Forasoft glossary, FAST-VQA](https://www.forasoft.com/learn/video-quality/glossary/terms-vqm/fast-vqa) (licence unconfirmed from primary).
- Q-Align (ICML 2024) teaches an LMM discrete text-defined rating levels; OneAlign unifies IQA, IAA and VQA; reported aesthetic SRCC 0.823 and LSVQ PLCC 0.886 (0.900 when ensembled with FAST-VQA); the OneScorer demo outputs [1,5], higher better; code at github.com/Q-Future/Q-Align — [Q-Align paper (PMLR)](https://proceedings.mlr.press/v235/wu24ah.html); [Papers with Code entry](https://ml.paperswithcode.com/paper/q-align-teaching-lmms-for-visual-scoring-via). A leaderboard lists Q-Align VQA SROCC 0.72 marked "Unverified" — [sotaverified](https://sotaverified.org/tasks/video-quality-assessment).
- pyiqa (IQA-PyTorch) bundles NR metrics including MUSIQ, TOPIQ (`topiq_nr`), NIQE, BRISQUE, DBCNN, NIMA, CLIPIQA, HyperIQA, QualiCLIP; added Q-ReAlign in June 2026 (`qrealign-mini` 0.8B, `-lite` 4B, `-pro` 9B; needs `transformers>=5.0`); `metric.lower_better` gives direction; retrained models normalised to [0,1]; README states PolyForm Noncommercial 1.0.0 + NTU S-Lab licence while the sidebar shows MIT (conflict) — [IQA-PyTorch GitHub](https://github.com/chaofengc/IQA-PyTorch). pyiqa also contains a LAION aesthetic architecture (`laion_aes_arch`) — [pyiqa docs](https://iqa-pytorch.readthedocs.io/en/latest/autoapi/pyiqa/archs/laion_aes_arch/index.html).
- LAION improved aesthetic predictor = MLP on CLIP ViT-L/14 768-d embeddings (checkpoint `sac+logos+ava1-l14-linearMSE.pth`); score range stated as 0-10 in one NVIDIA doc version and only "continuous, higher is better" in the current one — [NVIDIA NeMo Curator aesthetic filter](https://docs.nvidia.com/nemo/curator/curate-images/process-data/filters/aesthetic); [NeMo Curator 0.25.7](https://docs.nvidia.com/nemo/curator/0.25.7/curate-images/process-data/classifiers/aesthetic.html); [HF mirror](https://huggingface.co/camenduru/improved-aesthetic-predictor).

**Flicker / temporal consistency**
- Common no-reference recipe: estimate optical flow (typically RAFT), warp frame t to t+1, take a masked, normalised residual (warping error E_warp), compare with previous and first frame for short/long-term consistency — [BlazeBVD (arXiv 2403.06243)](https://arxiv.org/pdf/2403.06243); [Blind Video Deflickering (arXiv 2303.08120)](https://arxiv.org/pdf/2303.08120); "Flicker Penalty" from RAFT-warped L1 residual — [World Consistency Score (arXiv 2508.00144)](https://arxiv.org/pdf/2508.00144).
- Caveat: warping error is non-zero even for ground-truth videos due to natural intensity change and flow error; a relational variant was proposed — [arXiv 2312.16247](https://arxiv.org/pdf/2312.16247).
- A ready-made ComfyUI node combines RAFT warping error with forward-backward occlusion masking and a sliding-window brightness-variance flicker score (tool listing, not validated) — [comfy.icu VQ Temporal Consistency](https://comfy.icu/node/VQ_TemporalConsistency).

**Banding**
- Netflix CAMBI: open-sourced Oct 2021, inside the VMAF framework; default mode is no-reference, frame-by-frame; 0 = no banding, higher = more; around 5 is where banding "starts to become slightly annoying"; a full-reference mode accounts for banding in the source — [CAMBI doc (VMAF repo mirror)](https://github.com/AyazKhuraishi/netfllix-vmaf/blob/master/resource/doc/cambi.md); official repo [Netflix/vmaf](https://github.com/Netflix/vmaf).
- PSNR, SSIM and VMAF are not designed to detect banding; combining VMAF with CAMBI improves correlation with perceived quality — [Krasula et al., Banding vs. Quality (arXiv 2202.11038)](https://arxiv.org/pdf/2202.11038).

**Netflix automated QC**
- Netflix pixel-error detector: custom network over a 5-frame window at full resolution (downsampling makes the errors vanish), outputs per-frame error-likelihood maps, thresholded + connected components to (x,y) centroids; temporal window separates one-frame hot pixels from persistent highlights; trained on synthetic errors with a review-and-finetune loop for false positives; real time on one GPU; "near-perfect recall"; hours of manual QC down to minutes — [Netflix Tech Blog: Accelerating Video QC with Pixel Error Detection (mirror)](https://noise.getoto.net/2025/08/12/accelerating-video-quality-control-at-netflix-with-pixel-error-detection/).
- Netflix has a separate ML system predicting which assets will fail QC — [bestpractice.ai case study](https://bestpractice.ai/ai-use-cases/case-studies/media-entertainment/netflix-increases-quality-control-efficiency-by-using-machine-learning-to-predict-which-video-assets-are-likely-to-fail).

**Motion smoothness**
- RED's rule of thumb (quoted second-hand): pan no faster than one full image width every seven seconds or judder becomes too detrimental — [DPReview forum quoting RED](https://www.dpreview.com/forums/thread/4483295). At 24 fps add another second or two; a RED calculator reportedly gives about 16 s for a 90-degree pan at 24 fps vs 12 s at 30 fps — [MavicPilots thread](https://mavicpilots.com/threads/real-framerate-and-smooth-video.63482/post-724694) (second-hand).

**Text legibility**
- WCAG 2.x contrast minimum: 4.5:1 for normal text, 3:1 for large text (18 pt, or 14 pt bold) — [W3C WCAG 2.2, SC 1.4.3](https://www.w3.org/TR/WCAG22/#contrast-minimum). (Standard; page not fetched this session.)

### Inferences
- Suggested automated gate for each rendered shot (no human), cheapest first:
  1. Hard checks with ffmpeg: black/frozen frames, duration/fps/resolution, BT.709 tags, peak/average luma, clipped highlights %.
  2. Banding: CAMBI per frame via libvmaf (ffmpeg `libvmaf` with the `cambi` feature); flag shots with max CAMBI above ~5, especially skies and haze gradients (where AgX + 8-bit + volumetric mist are prone to banding).
  3. Flicker/shimmer: RAFT-flow warping error with occlusion masking at 1-3 frame gaps (the ReVQ-2k ablation shows motion compensation is what makes the signal meaningful; raw frame difference is useless for camera-moving flyovers). Also a per-frame global mean-luma series: high-frequency variance after detrending = exposure/denoiser flicker. Shimmer/aliasing on terrain edges shows up as localized high warping error on high-gradient pixels.
  4. Motion: compute camera pan speed from the Blender camera path (exact, no flow needed) and enforce "≥7-9 s per frame width" for 24/25/30 fps output, with motion blur on.
  5. General quality: DOVER-Mobile or FAST-VQA score as a regression signal (compare against the previous accepted render of the same shot, not an absolute threshold), since even the best models are around 0.84 SRCC on rendered video.
  6. Text: for burned-in labels, sample the background under each text box and compute WCAG contrast; OCR (any engine) round-trip of the expected string as a legibility proxy.
  7. Coarse "does this look good" judge: Q-Align/OneAlign or Q-ReAlign on a few keyframes only, because LMM inference is heavy relative to the 3060's 12 GB, which is also needed for rendering.
- Reliability: all NR-VQA models were trained on camera UGC or game renders; documentary terrain flyovers with overlays are out of distribution. Use them relative (A/B between versions) rather than absolute, and keep explicit metrics (CAMBI, warping error, contrast, pan speed) as the pass/fail gates.
- Licensing: pyiqa's README claims PolyForm Noncommercial; DOVER/FAST-VQA carry S-Lab/research licences. If the channel is monetised, prefer explicit metrics (VMAF/CAMBI are BSD-2-clause-plus-patent in Netflix's repo, not verified this session) or check each licence.
- Netflix's pixel-error design (5-frame window, full resolution, synthetic errors) is a good template for detecting render "fireflies" (single-frame hot pixels from Cycles caustics/volumes), which are the CG analogue of hot pixels.

### Gaps
- YouTube's automated upload-side quality checks: no source found this session.
- Netflix's broader automated QC (Photon/IMF checks, other artifact detectors) beyond pixel errors: not covered by the sources reached.
- FAST-VQA and Q-Align GitHub repos were not opened (licence, VRAM, exact s/video on a 3060 unknown).
- MUSIQ reliability on rendered content, saliency/composition-check models and their validation: not researched in depth; no source found.
- No published threshold mapping warping-error values to "visible flicker" for rendered terrain; would need calibration on the pipeline's own accepted/rejected renders.
- RED's official panning guide was not reached (rule is second-hand).
- VMAF/CAMBI licence text not verified this session.

---

## Q5. Caching and reproducibility for AI-driven 3D pipelines (content hashing, still previews before full renders)

### Takeaway
No primary source specific to "AI-driven Blender pipelines" was found; the pattern follows from what the sources say changes renders: Blender version (5.0 probe-bake fix, 5.2 darker EEVEE), OCIO config, working space, texture tx files, seeds. Hash all of these with the inputs, render a few stills first and gate them with the Q4 metrics, then render the range and keep EXR/plates keyed by hash.

### Cited Findings
- Renders differ across Blender versions: 5.0 fixed an inverted Light Probe Volume backface setting so 5.0 files bake differently — [Blender 5.0 EEVEE notes](https://developer.blender.org/docs/release_notes/5.0/eevee/) (snippet); 5.2 EEVEE screen-space RT changes can render darker than 5.1 — [Blender 5.2 EEVEE notes](https://developer.blender.org/docs/release_notes/5.2/eevee/) (snippet).
- Matching Blender versions, working spaces and OCIO configs across machines is needed for consistent renders; changing working space/view/look/exposure/gamma changes appearance — [iRendering](https://irendering.net/why-your-renders-look-different-in-blender-5-aces-display-transforms-and-what-changed/); [itsfoss](https://itsfoss.com/news/blender-5-0-release/).
- The 5.2 texture cache writes `.tx` files to `blender_tx/` and regenerates them when sources change — [80.lv](https://80.lv/articles/blender-5-2-lts-introduces-new-cycles-texture-cache-system).
- Seed behaviour affects temporal noise patterns: Animated Seed off gives frame-locked structured noise at low spp — [devtalk OptiX temporal thread](https://devtalk.blender.org/t/taking-a-look-at-optix-7-3-temporal-denoising-for-cycles/18656?page=6).
- `--cycles-print-stats` logs render memory and time per render, useful for a render log — [Blender manual CLI](https://docs.blender.org/manual/ja/5.2/advanced/command_line/arguments.html).
- The repo already uses a sha256 key over source path, size, mtime and all parameters plus a version tag for its Real-ESRGAN cache — [<repository>/editvideo/restore.py line 94](F:/EDIT%20VIDEO/editvideo/restore.py).

### Inferences
- Cache key for a Blender plate: sha256 over (shot-script source, parameter JSON with sorted keys, hashes of DEM/orthophoto/asset files, Blender version string `bpy.app.version_string` + build hash, OCIO config file hash, engine + device, GPU driver version for OptiX, seed, frame range, resolution). Store the key and `--cycles-print-stats`/timing output next to the plate.
- Still-first protocol: render 3-5 frames (first, last, max-camera-speed frame, frame with most mist/text) at full resolution, run the cheap per-frame checks (CAMBI, contrast, clipping, LAION/Q-Align keyframe score), and only then render the range; then run the temporal checks (warping error, luma-series flicker) on the full sequence. This matches the owner's "snap ≤8 frames" habit noted in memory.
- Frame chunking: render ranges with `-s/-e -a` into numbered frames so a crash or a failed QA chunk only re-renders that chunk; skip frames already present with matching key (Blender's "Overwrite"/"Placeholders" output options support this, unverified this session).
- Determinism: keep a fixed seed per shot (and Animated Seed on for Cycles with temporal denoise); record it. EEVEE determinism across runs is unverified, so the QA should compare against stored accepted frames with a tolerance, not exact hashes.

### Gaps
- No primary/industry source found on content-hash caching specifically for Blender or AI-driven 3D pipelines (e.g. studio pipeline write-ups, USD/OpenAssetIO practices).
- Whether EEVEE output is bit-exact across runs on the same GPU/driver: unknown.
- Persistent Data and "Placeholders/Overwrite" behaviour in 5.x headless chunked renders: not verified this session (manual 403).
