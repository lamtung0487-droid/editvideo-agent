# 3D beauty, round 2: look development, Blender 4.2–5.x features, camera language, reconstruction, stylised looks and automatic judgement for a headless Blender 5.2 pipeline on an RTX 3060 12 GB

Scope note for the report writer: this round deliberately skips what `docs/research/Nâng cấp 3D phim tài liệu.md` already covers (data sources and licences, MoGe-2 projection, period-map drapes, AgX hue shift, EEVEE volumetric slowdown #125364, Cycles OptiX temporal denoise, Huffman's Blender relief guide, NW/NNW light direction, Imhof blue-grey shadows, Prehistoric Planet camera rules, RED pan rule, gate checks). `docs.blender.org`, `developer.blender.org`, `projects.blender.org`, `shadedrelief.com` and NASA Earthdata all returned HTTP 403 to the fetch tool in this session, so Blender facts below come from secondary coverage (CG Channel, iRendering, 80.lv, BlenderNation), manual pages seen only as search snippets, and the repo's own code. Every Python property name marked "verify" is from memory of the 4.2+ API and must be checked with `bl_rna.properties.keys()` inside Blender 5.2 before use.

## 1. Look development: what separates premium terrain/map renders from "default Blender"

### Takeaway
The terrain template is currently lit like a default scene: a hand-made two-colour gradient world, a single sun lamp, a 0.95-roughness satellite texture with no relief normal, haze and mist as two volume boxes, EEVEE ray tracing off, and no render passes exported. The cheapest large gains are (1) a physically coupled sky and sun (the Multiple Scattering sky in 5.x), (2) aerial perspective and valley mist done in compositing from depth/height passes instead of volume boxes, (3) a relief-enhancing normal layered on the satellite colour, (4) shader-projected drifting cloud shadows, and (5) dedicated water and night-light materials; each should cost a fraction of a second per frame, while volumetrics and Cycles stay reserved for hero shots.

### Cited Findings
**What the pipeline does today (read from the repo, 2026-10-27)**
- Terrain world = Generated Z → Map Range (−0.05…0.32) → 2-stop Color Ramp (horizon, zenith colours) → Background; one SUN lamp, energy 4.0, angular size 1.5°, colour #fff1dc — [terrain_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/terrain_shot.py) lines 168–194.
- Terrain material = satellite image → Hue/Saturation (sat 0.9, value 1.05) → Principled Base Color, Roughness 0.95, specular 0.15; no bump/normal input; "zones" are added as emission — [terrain_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/terrain_shot.py) lines 100–166.
- Aerial haze is a scaled cube with Principled Volume (default colour #c9d3dc, anisotropy 0.35); valley mist is a second volume box up to `top_m` 900 m — [terrain_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/terrain_shot.py) lines 195–230.
- EEVEE settings are applied with `setattr` inside `try/except: pass` (taa 32, `use_gtao`, `volumetric_end` 400, tile "4", 64 volume samples, volumetric shadows when mist), so any property that no longer exists in EEVEE Next is silently dropped; `use_raytracing` is set only in `domino_shot.py` and `bloc_map.py`, not in the terrain or globe templates; output is 8-bit PNG by default; no render passes or compositor nodes are used in any Blender script — [terrain_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/terrain_shot.py) lines 517–537; [bloc_map.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/bloc_map.py) line 342; [domino_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/domino_shot.py) line 340.
- Default focal lengths: terrain 30 mm, globe 35 mm, bloc map 40 mm, dominoes 50 mm; shadow linking (`sun.light_linking.blocker_collection`) is already used for "sun blockers" in terrain and globe — [terrain_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/terrain_shot.py) lines 281, 335–337; [globe_shot.py](F:/EDIT%20VIDEO/editvideo/blender_scripts/globe_shot.py) lines 149, 237.

**Sky and sun**
- The Blender 5.0 Sky Texture node offers Single Scattering (the Nishita model) and Multiple Scattering; the manual calls Multiple Scattering, based on Fernando García Liñán's work, "the most accurate model as it accounts for multiple bounces of light in the atmosphere", and notes both are "very bright by default (hence accurate)" — [Blender 5.0 manual, Sky Texture](https://docs.blender.org/manual/en/5.0/render/shader_nodes/textures/sky.html) (seen via search snippet).
- The developer explains single-scattering Nishita gives wrong radiance everywhere and a black twilight Earth shadow; multiple scattering fixes this and sits closer to ground truth; it uses 4 wavelengths plus a "hero wavelength" technique versus 21 for Nishita — [Blender Artists, Multiple Scattering Sky Texture](https://blenderartists.org/t/multiple-scattering-sky-texture/1596166). Community feedback in the same thread complains the ground half renders black — [Blender Artists p.2](https://blenderartists.org/t/multiple-scattering-sky-texture/1596166?page=2).
- The original Nishita sky precomputes a 512×128 lookup texture, "fast enough to allow real-time tweaking in the viewport" (2020 commit) — [Blender commit](https://projects.blender.org/archive/blender-archive/commits/commit/2be0ae7c992d59dd74cffb8997bfdf5bcdf3c48d/intern/cycles/render/image_sky.cpp).
- No source in this session confirms whether the Multiple Scattering sky is evaluated identically in EEVEE (see Gaps).

**Atmosphere and volumes in EEVEE Next**
- EEVEE Next (4.2): world volumes are no longer limited by clipping distance; volume lighting is dithered to avoid flicker; mesh objects get correct volume intersection; many small volume objects are optimised — [iRendering, EEVEE Next in 4.2](https://irendering.net/blender-4-2-explore-whats-new-in-eevee-next/).
- Blender's EEVEE-Next performance analysis reports ray tracing as "quite costly", with horizon passes and denoising taking much of the cost (per-pass ms on unspecified hardware) — [Blender issue #117246](https://projects.blender.org/blender/blender/issues/117246) (seen via search snippet only; page 403).

**Cloud shadows**
- A Cycles technique: two planes (terrain, cloud cover) with a tiny gap lit by a distant emitter; cloud transparency driven by an inverted cloud image so bright cloud areas block light and project shadows — [glassroof.nl](https://www.glassroof.nl/?p=327) (single blog post, older Blender).
- Alternative: render once, paint/compute a greyscale cloud mask, and composite; or isolate the shadow by rendering terrain with and without the cloud layer — [Planetside forum](https://planetside.co.uk/forums/index.php?msg=33707).
- Real-time practice: a cloud-shadow texture multiplied over the whole terrain and scrolled over time; fine geometric detail is lost on rough meshes — [Khronos forum](https://community.khronos.org/t/cheap-dynamic-cloud-shadows/13190).

**Relief enhancement (beyond Huffman, already covered)**
- Tom Patterson's "resolution bumping" modifies coarse elevation data itself (in Photoshop, 16-bit layers) before building shaded relief or 3D scenes, to make rugged mountains read more clearly — [Patterson, Resolution Bumping](https://shadedrelief.com/bumping/bumping.html) (page 403; content via search snippet).
- A variant applies it to finished relief: duplicated layer in Overlay mode over a Gaussian-blurred base — [maphew archive](https://maphew-archive.nfshost.com/Projects/resolution-bumping-shaded-relief).
- Blender's Bump node turns a height input into a perturbed normal, controlled by Strength and Distance — [Blender 5.2 manual, Bump](https://docs.blender.org/manual/en/5.2/render/shader_nodes/vector/bump.html) (search snippet).
- NACIS 2024 Practical Cartography Day included a session on 3D terrain and basemaps, including plotting data in 3D with Geometry Nodes — [NACIS 2024 sched](https://nacis2024.sched.com/event/1fwlN/practical-cartography-day-morning-session-i-3d-terrain-and-basemaps).

**Ocean, coastline, night**
- The GEBCO Grid is placed in the public domain and may be used free of charge, including copying, adapting and commercial exploitation; users must acknowledge the source; provided "as is" — [GEBCO 2021 page](https://gebco.net/data_and_products/gridded_bathymetry_data/gebco_2021), [GEBCO terms PDF](https://pointcloud.ucsd.edu/Scale/sources/GEBCO_2020_27_Jun_2021/GEBCO_Grid_terms_of_use.pdf). Conflict: the AODN metadata record lists GEBCO 2021 as CC BY 4.0 — [researchdata.edu.au](https://researchdata.edu.au/gebco-2021-elevation-optimized-format/3650725). Older GEBCO_08 terms forbid using GEBCO/IHO/IOC names to imply endorsement — [Esri Arctic Ocean reference](https://doc.arcgis.com/en/data-appliance/latest/maps/arctic-ocean-reference.htm).
- NASA Black Marble is a suite of four calibrated VIIRS Day/Night Band night-light products, distributed through LAADS DAAC, AWS and Google Earth Engine — [LAADS DAAC](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/science-domain/nighttime-lights/), [NASA Applied Sciences agenda](https://appliedsciences.nasa.gov/sites/default/files/2020-10/Black%20Marble%20Agenda.pdf). Its use terms were not retrievable (see Gaps).

**Lighting controls**
- EEVEE Next removed the 128-light cap (4096 visible at once), added per-light ray-visibility options and a Transmission influence factor — [iRendering](https://irendering.net/blender-4-2-explore-whats-new-in-eevee-next/).
- Light & Shadow Linking arrived in EEVEE in Blender 4.3 (released 19 Nov 2024), previously Cycles-only — [Blender 4.3 release](https://www.blender.org/?p=93537), [AlternativeTo](https://alternativeto.net/news/2024/11/blender-4-3-released-with-eevee-enhancements-improved-rendering-and-vulkan-backend).

### Inferences
**Ranked recommendations: visual gain per render-minute (my synthesis; costs are estimates unless marked measured; baseline is the owner's measured ~0.65 s/frame EEVEE terrain at 1080p)**

| Rank | Change | Why it reads as "premium" | Extra cost per 1080p frame on 3060 | Confidence |
|---|---|---|---|---|
| 1 | Export Mist/Z + a world-height AOV + cloud-mask AOV as 16-bit/EXR; do aerial perspective and valley mist in the finish stage; delete the two volume boxes | Depth layering (far ridges lifted toward sky colour, desaturated, lower contrast) is what makes terrain feel kilometres deep; adjustable without re-render | Negative to ~0 (removes volumes, which prior research flagged as the one thing that multiplies EEVEE time 15–20×); compositing in ms–<1 s | High |
| 2 | Replace the gradient world with the Multiple Scattering Sky; derive sun lamp colour/strength from the same sun elevation; normalise with exposure | Sky colour, horizon glow and sun warmth become coherent with sun height (the "golden hour" relationship viewers know) | ~0 (sky is a precomputed LUT-type evaluation; EEVEE bakes world lighting into its probe) | Medium (EEVEE parity unverified) |
| 3 | Relief normal: Bump from a high-passed / resolution-bumped DEM (Strength ~0.2–0.5) plus very low-strength macro noise; vary roughness 0.75–0.95 by land cover instead of a flat 0.95 | Low sun rakes ridges; 10 m satellite colour stops looking like a flat photo on a surface | ~0 | High |
| 4 | Shader-projected cloud shadows (formula below), drifting 1–3 % of frame width per second | Breaks uniform light, shows scale and wind, adds motion to static plates | ~0 | High |
| 5 | Water material: mask from DEM ≤ 0 / GEBCO / OSM water; low roughness (0.05–0.2), depth tint from GEBCO, bright surf band at the coastline from a distance field, sun glint | Coasts are where "default" renders look most wrong (water treated as land texture) | Low (EEVEE ray tracing or SSR needed for reflections) | Medium |
| 6 | Enable EEVEE ray tracing on terrain (screen-trace, half resolution, denoise on, fast GI horizon scan) | Valley occlusion and bounce light; contact darkening under extrusions | Unknown — dev profiling says ray tracing is "quite costly"; measure on stills first | Medium |
| 7 | Studio rig for tabletop scenes (bloc map, dominoes, diorama): large soft key, world/HDRI fill, rim light linked only to blocs/markers | Silhouette separation without lifting the map | ~0 | High |
| 8 | Night layer: Black Marble as emission × (1 − day factor), slight bloom only on lights | Night city/coast shots become possible and look like the iconic NASA imagery | ~0 | Medium (licence wording unverified) |
| 9 | Geometry Nodes scatter (trees/villages) only for shots below ~2 km altitude | Fixes the soft-texture problem at low altitude | Medium–high (instances, VRAM) | Medium |
| 10 | Cycles hero shots with true adaptive-subdivision displacement | Best close-terrain silhouettes and shadows | 17–37 s+/frame (prior research's benchmark range) | High cost certainty |
| 11 | Real volumetric clouds (VDB) | Only for fly-through-cloud moments | Very high in EEVEE Next | — |

**Recipes**
- Aerial perspective (finish stage or Blender compositor): `f = 1 − exp(−d / D)` with d from Z or Mist; output = mix(image, sky_horizon_colour, f·a) then reduce saturation by f·0.3–0.5 and lift blacks slightly with f; choose D so the farthest ridge reaches ~60–70 % sky colour. Tint far shadows toward blue-grey per the Imhof convention already in the prior doc. Mist pass properties to try: `view_layer.use_pass_mist`, `world.mist_settings.start/depth/falloff` (verify).
- Valley mist without volumes: write world Z through a Shader AOV (EEVEE and Cycles support AOVs — verify in 5.2), compute `m = smoothstep(z_top, z_floor, z) × (1 − exp(−d/D2))`, add a soft mist colour with a slow 2D noise to avoid a hard plane; animate noise offset for drift.
- Cloud shadows in the terrain shader (no extra geometry): for surface point P, unit vector L toward the sun and cloud deck height H, sample `Q = P.xy + L.xy · (H − P.z) / L.z`; `mask = smoothstep(c0, c1, noise(Q·scale + wind·t))`; multiply diffuse colour by `1 − k·mask` with k 0.25–0.45. This darkens albedo rather than only direct light, which is acceptable for matte terrain under a low sun; in Cycles, a light-node gobo on the sun gives the physically exact version. Optionally add sparse alpha cloud cards above, hidden from camera rays (`visible_camera = False`, verify) so they cast but are not seen.
- Sun: real sun's angular diameter is about 0.5° (general knowledge, not sourced this session); the current 1.5° gives softer shadow edges—keep 0.5–1.0° for crisp "satellite" looks, 2–4° for painterly softness.
- HDRI choice: for exterior terrain prefer the analytic sky (it matches the sun exactly); ground-level HDRIs bring ground-level horizons that do not belong over a 50 km map. For tabletop/diorama/product, use an overcast or studio CC0 HDRI (Poly Haven, licence covered in prior research) rotated so its key agrees with the key lamp, at modest strength as fill.
- Relief-map materials: matte plaster/print look = roughness 0.9–1.0, specular 0.1–0.2, muted albedo, vertical exaggeration as a tested parameter; "school raised-relief plastic" look = roughness 0.35–0.5 so ridges catch highlights.
- Paper / vintage map sheet: roughness 0.7–0.85, small Sheen for fibre, bump from a CC0 paper scan, fold creases as low displacement along a fold grid, darkened edges; print ink bleed and misregistration baked into the texture with OpenCV/Pillow before Blender (zero render cost); translucency only for backlit sheets in Cycles.
- Light linking (4.3+) lets the rim light touch only extruded blocs, markers and labels, so the map itself keeps its key-light shading.

### Gaps
- No primary source confirmed the Multiple Scattering sky's EEVEE support or render cost, nor the exact 5.2 Python enum names (`sky_type` values).
- No measured cost on an RTX 3060 for EEVEE ray tracing on terrain; #117246's per-pass numbers could not be read (403).
- No authoritative Black Marble use statement was retrievable (NASA Earthdata page 403); NASA data is commonly treated as not copyrighted in the US, but this is unverified here.
- GEBCO licence wording conflicts between GEBCO (public domain + acknowledgement) and AODN (CC BY 4.0); check the download source's terms.
- No studio breakdown with concrete material values for relief or paper maps was found; all material numbers above are inference to be tuned against owner verdicts.
- The `try/except: pass` around EEVEE settings means nobody knows which of the template's settings actually took effect in 5.2; a one-off dump of `sc.eevee.bl_rna.properties.keys()` would close this.

## 2. Blender 4.2–5.x features worth using headless

### Takeaway
EEVEE Next (4.2) brought screen-space ray tracing for every BSDF, virtual shadow maps, real displacement and better volumes; 4.3 added light/shadow linking and rewrote Grease Pencil (v3, new Python API); 5.0 (19 Nov 2025) added the Multiple Scattering sky, Cycles null-scattering volumes, non-experimental adaptive subdivision, ACES/HDR colour management, Geometry Nodes volume grids and ready-made scatter modifiers, and compositor assets for chromatic aberration and vignette. For a headless pipeline, the high-value features are those that cost nothing per frame (sky, light linking, AOV/passes, GN scatter at low altitude); ray tracing must be measured, and API churn (Grease Pencil v3, compositor node-tree changes) is the main automation risk.

### Cited Findings
**EEVEE Next (4.2 LTS, July 2024)**
- Screen-space ray tracing for every BSDF, with no limit on BSDF count — [BlendNation 4.2](https://www.blendernation.com/2024/07/16/blender-4-2-lts-released-check-out-these-standout-features/), [iRendering](https://irendering.net/blender-4-2-explore-whats-new-in-eevee-next/).
- Virtual Shadow Maps with shadow-map ray tracing give soft shadows without jittering, reduce flicker and raise maximum shadow resolution; shadow biases are automatic; contact shadows removed — [iRendering](https://irendering.net/blender-4-2-explore-whats-new-in-eevee-next/), [CG Channel](https://www.cgchannel.com/2024/07/eevee-next-finally-arrives-in-blender).
- Displacement is supported (three per-material methods trading accuracy, performance and memory; "Displacement Only" falls back to "Displacement and Bump"); a Thickness output replaces Refraction Depth — [iRendering](https://irendering.net/blender-4-2-explore-whats-new-in-eevee-next/).
- Bloom left EEVEE's render settings; it now has to be added as a compositor (Glare) node — [CG Cookie community](https://cgcookie.com/community/22683-blender-5-0) (a user's account).
- Performance: a user reports a scene taking 39 s in legacy EEVEE and 2 min 57 s in EEVEE Next on an RTX 4090; results are strongly scene-dependent — [devtalk EEVEE-Next feedback](https://devtalk.blender.org/t/blender-4-2-eevee-next-feedback/31813?page=31) (page attribution from search summary). A render-farm vendor quotes 5–60 s per 1080p EEVEE frame and 2–30 min for Cycles without naming hardware — [SuperRendersFarm](https://superrendersfarm.com/es/article/eevee-vs-cycles-cloud-render-farm-comparison-2026) (vendor estimate).

**4.3 (19 Nov 2024)**
- EEVEE Light & Shadow Linking — [Blender 4.3](https://www.blender.org/?p=93537).
- Grease Pencil v3: object type `GPENCIL` → `GREASEPENCIL`, ID type `bpy.types.GreasePencil` → `bpy.types.GreasePencilv3`, modes renamed (e.g. `EDIT_GREASE_PENCIL`); a frame now references a *drawing* holding strokes/points, replacing `frame.strokes`/`stroke.points` — [4.3 GP migration](https://developer.blender.org/docs/release_notes/4.3/grease_pencil_migration/) (search snippet). Add operator is `bpy.ops.object.grease_pencil_add`; the migration page is incomplete and the Line Art modifier type name is disputed (`LINEART` vs `GREASE_PENCIL_LINEART`) — [developer-docs issue #89](https://projects.blender.org/blender/blender-developer-docs/issues/89). The 4.4 API documents `GreasePencilLineartModifier` with `crease_threshold`, `level_start/level_end` — [bpy 4.4](https://docs.blender.org/api/4.4/bpy.types.GreasePencilLineartModifier.html).
- Geometry Nodes can drive Grease Pencil from 4.3 — [CG Channel](https://www.cgchannel.com/2024/10/blender-4-3-lets-you-control-grease-pencil-with-geometry-nodes).

**5.0 (19 Nov 2025)** — all from [CG Channel 5.0](https://www.cgchannel.com/2025/11/blender-5-0-is-out-check-out-its-5-key-features) unless noted
- Geometry Nodes: volume grid data type with 27 new nodes (OpenVDB), mesh/point-cloud → SDF grids with Booleans, bundles and closures, UV Tangent node; six new GN-based modifiers including Array, Scatter on Surface, Instance on Elements, Randomize Instances.
- Cycles: new default volume algorithm based on unbiased null scattering (fewer parameters, fewer artefacts where volumes overlap; ray marching still available); NanoVDB for smoke/fire (less memory); improved random-walk SSS; thin-film in Metallic BSDF; adaptive subdivision no longer experimental.
- EEVEE: View Layer overrides; faster shader compilation on NVIDIA.
- Colour: working space selectable (Linear Rec.709 default, ACEScg), ACES 1.3/2.0, Rec.2100 PQ/HLG video output.
- Compositor: new Compositor modifier for the Sequencer (which uses the CPU compositor only); node trees reusable across files; new asset-shelf assets for chromatic aberration and vignetting. 80.lv adds an asset shelf in the node editor and a new Convolve node — [80.lv](https://80.lv/articles/major-compositor-improvements-coming-in-blender-5-0). A third-party changelog lists a Glare "Sun Beams" mode, a Convert to Display node, a Working Space option in Convert Color Space, Displace interpolation, and removal of the compositor Gamma node — [NodeToPython issue #171](https://github.com/BrendanParmer/NodeToPython/issues/171) (secondary).
- Grease Pencil: motion blur, sharp and flat stroke corners.

**Line Art cost**
- Each Line Art modifier runs the whole occlusion calculation (no global cache); "Use Cache" on later modifiers reuses the first one's scene data at the cost of some settings; many instanced objects hurt performance; Force Backface Culling speeds it up but changes occlusion levels — [Blender manual, Line Art (4.0)](https://docs.blender.org/manual/it/4.0/grease_pencil/modifiers/generate/line_art.html) (older manual version). Line Art loading was multithreaded in 2021 with modest overall gain — [BlenderNation](https://www.blendernation.com/2021/06/18/lineart-performance-improvements/).

### Inferences
- **EEVEE Next settings to A/B on 3–5 stills before any sequence** (property names from memory of the 4.2 API; verify): `eevee.use_raytracing=True`, `ray_tracing_method='SCREEN'`, `ray_tracing_options.resolution_scale='2'` (half res), `ray_tracing_options.use_denoise=True`, `fast_gi_method='GLOBAL_ILLUMINATION'`, `fast_gi_resolution='2'`, `fast_gi_step_count` 4–8; shadows `shadow_ray_count` 1–2, `shadow_step_count` 4–6, `shadow_resolution_scale` 1.0; per-light `use_shadow_jitter` off (VSM already soft). Expect ray tracing to add the most time; keep it if the still gain is visible at 1080p viewing size.
- **Remove the silent `try/except: pass`** around EEVEE settings or log what failed; the template may be paying for nothing (e.g. `use_gtao` may be a legacy name).
- **Passes as standard output**: Combined + Mist/Z + Normal + a few Shader AOVs (world height, cloud mask, water mask, object index for labels) written as multilayer EXR or 16-bit PNG sidecars. This turns aerial perspective, valley mist, night-light glow and label-safe darkening into adjustable finish operations and gives the beauty judge (section 6) depth-aware measurements.
- **Compositor in headless 5.x**: GPU compositing for final renders exists in 4.x via a performance setting (`render.compositor_device='GPU'`, verify); 5.0's move to reusable node groups may change how a script attaches a compositor tree (`scene.node_tree` vs a node-group property; verify). Because the repo already has an external finish pass, keep glare/lens/vignette there unless they need scene-linear HDR (bloom on city lights does—do it on EXR).
- **Arrows and hand-drawn lines**: Grease Pencil v3 is now scriptable but the API is young and its modifier names shifted between 4.3 and 4.4; a more robust headless path is Curve → GN (Curve to Mesh with radius taper, Trim Curve driven by a frame value for "draw-on") with a flat emission/ink material. Use GP v3 only if a genuinely hand-drawn stroke texture is needed, and pin the Blender version.
- **Geometry Nodes procedural detail**: the 5.0 "Scatter on Surface" modifier gives tree scatter without hand-built node trees; drive density from a land-cover or period-map mask and only enable below ~2 km camera altitude (above that, satellite colour already carries the forest).
- **Cycles on 12 GB**: adaptive subdivision now being standard (5.0) makes Cycles the right engine for close terrain hero shots with real displacement; keep EEVEE + bump for everything else.

### Gaps
- Exact 5.2 property names and defaults for EEVEE ray tracing, fast GI, shadows, Glare node types (a "Bloom" glare type is believed to have come with 4.2 but was not confirmed), GPU compositor and the 5.x compositor node-tree attachment could not be verified (manual/dev docs 403).
- No RTX 3060 measurements for EEVEE Next with ray tracing, Line Art, or GN scatter at 1080p.
- No source confirmed Freestyle's status under EEVEE Next.

## 3. Camera language for 3D documentary map and terrain shots

### Takeaway
Published studio breakdowns with concrete numbers remain scarce; beyond the rules already in the prior doc (aerial-vehicle logic, 50–135 mm oblique, one motivated move, slow pans), the useful new evidence is practical: route-following cameras must smooth their target (lerp) or they shake on turns, focus targets should lock to points of interest, and documentary map pipelines (Google Earth Studio + After Effects) separate a clean camera move from later highlights and labels. Rack focus, speed ramps and handheld noise have no sourced documentary norms and should be treated as calibrated parameters.

### Cited Findings
- Mapbox's Tour de France route animations: a camera locked to the leading edge of the route shook on sharp turns; smoothing the camera with linear interpolation (lerp) toward the target fixed it — [Mapbox blog](https://www.mapbox.com:443/blog/building-cinematic-route-animations-with-mapboxgl).
- A Cinema 4D map-animation guide: keyframed pans/zooms/rotations, a Target tag to hold focus on specific points, camera morph between positions, soft lighting and depth of field — [Novedge](https://novedge.com/blogs/design-news/cinema-4d-tip-creating-dynamic-3d-map-animations-in-cinema-4d).
- A documentary-style pipeline builds the clean camera move first in Google Earth Studio, then adds region highlights, vector maps and text in After Effects, targeting 1920×1080 — [Skillshare class](https://www.skillshare.com/en/classes/create-documentary-style-map-animation-with-google-earth-studio-and-adobe-after-effects/1671406834).
- No public material was found for "Fabian Fucke" map work; searches returned only generic tutorials and freelancer listings — [search result example](https://www.skillshare.com/en/classes/cinematic-3d-map-animation-in-after-effects-2026/615169581).

### Inferences
- **Shot grammar for a terrain sequence** (synthesis, to be calibrated on owner verdicts): (1) establishing: high oblique, 60–70° down-tilt, 85–135 mm, slow push; (2) descent: tilt rises toward the horizon while focal length shortens slightly so the ground "opens" (subtle dolly-zoom, ≤ 20 % focal change); (3) lateral truck along a ridge or coast for parallax, with near ridges, mist bands or cloud cards supplying foreground layers; (4) orbit only around one named point, ≤ 30–45° of arc per shot; (5) route-follow with a lerp-smoothed look-at target leading the line by 10–20 % of frame width.
- **Speed ramps**: Bezier keys with long eases (ease-in and ease-out each 30–40 % of the shot), no linear segments, no direction reversal; a gentle "settle" in the last 10 % before labels appear. These match the prior doc's "dừng trước khi nhãn xuất hiện" rule.
- **Rack focus**: use only when there is a meaningful foreground object (pin, 3D label, diorama piece, archive photo card); for full-scale terrain keep deep focus. Blender DOF uses scene units: with this repo's 1 BU = 1 km convention Blender "thinks" a 50 km map is 50 m wide, so to read as a 1 m table model the f-stop must be scaled by model size / scene size in BU (e.g. f/2.8 × 1/50 ≈ f/0.056) — derived from DOF scaling, verify visually.
- **Handheld/aircraft noise**: off by default for maps (it reads as amateur over cartography); for "helicopter" or "drone" sequences, an F-curve Noise modifier on rotation with ≤ 0.1–0.2° amplitude at 0.2–0.5 Hz, plus no roll except banking into turns.
- **Lens choice by genre**: documentary/history = long lenses, slow; travel = wider (24–35 mm) low-altitude glides with sun flare angles; product/explainer = 50–100 mm macro-like close passes with shallow DOF and studio light.

### Gaps
- No published focal lengths, speed curves or DOF settings from Antenna, Elastic, ManvsMachine, Apple TV+ or Ken Burns map work were found; "Fabian Fucke" could not be identified.
- No evidence base for perceptual limits on rack-focus duration or camera-noise amplitude.

## 4. Gaussian splatting / NeRF and image-to-3D on 12 GB

### Takeaway
The prior doc already covers Blender 5.3 native splats (scheduled 10 Nov 2026), BlendSplat, gsplat, Postshot's export change, SF3D, TripoSR, Hunyuan3D and TRELLIS. The new candidate this round is Meta's SAM 3D Objects (Nov 2025), released with checkpoints under a custom "SAM License" that secondary sources describe as permitting commercial use with restrictions (including a reported ban on military applications); VRAM requirements were not found. Reconstructed or generated 3D should stay in the role of props or short, small-motion shots.

### Cited Findings
- SAM 3D Objects is released under the SAM 3 / custom license; Roboflow advises reviewing terms before commercial use — [Roboflow model page](https://roboflow.com/model/sam-3d-objects), [Roboflow playground](https://playground.roboflow.com/models/meta/sam-3d-objects).
- A French guide says the SAM License permits commercial use with restrictions such as a ban on military applications; weights download free from GitHub and Hugging Face — [Aixploria FR](https://www.aixploria.com/meta-sam-3d/), [Aixploria EN](https://www.aixploria.com/?p=44039) (secondary).
- No VRAM figure was found; Roboflow says it can run on CPU and GPU devices — [Roboflow](https://roboflow.com/model/sam-3d-objects).

### Inferences
- A "military applications" restriction is about the use of the model, not necessarily about depicting historical war in a documentary, but this is a legal judgement; until the licence text is read, keep SAM 3D for non-weapon props and keep TripoSR (MIT, prior doc) as the default for anything published.
- Where image-to-3D looks good: small rigid props seen briefly, at mid-distance, under the same stylised finish as the rest (grain, softness), especially on a diorama/miniature look where imperfection reads as handmade. Where it looks fake: faces and bodies, text and insignia, mechanical detail on vehicles/aircraft, symmetric objects seen from the side the photo never showed, and anything lit by a different light than the generated texture's baked shading (re-light by flattening texture shading or using emission-only in projection shots).
- Splats from real footage are the only reconstruction that adds authenticity; use them only after 5.3's colour handling is checked (prior doc).

### Gaps
- SAM 3D Objects licence text, VRAM and Windows support not verified; no RTX 3060 measurements for any splat/image-to-3D model this round.
- No new 2026 sources on NeRF-in-Blender add-ons were searched (time budget).

## 5. Stylised looks that hide limited detail, and when each fits a historical documentary

### Takeaway
Stylisation is the most render-efficient way to look intentional when data is coarse: relief-shaded "atlas" terrain, hachure/engraved relief, stepped paper-diorama contours, miniature tilt-shift and ink outlines each convert missing detail into a visible design choice. The look should follow the story's period and claim: engraved/hachure for pre-1950 or colonial-map chapters, relief atlas for campaign overviews, diorama/miniature for openly reconstructed scenes, ink outline for explanatory beats.

### Cited Findings
- Hachures are strokes drawn in the direction of steepest slope; steeper slopes get thicker, shorter strokes; flat areas are usually blank; standardised by Johann Georg Lehmann in 1799 (sources disagree whether he was German or Austrian) — [Wikipedia, Hachure map](https://en.wikipedia.org/wiki/Hachure_map), [Wikipedia mirror](https://wiki.krisyotam.com/content/wikipedia_en_all_nopic_2026-03/Hachure).
- Hachure lines can be generated automatically from elevation data with GIS methods respecting the construction rules (2017 paper) — [Academia.edu, Automatic generation of hachure lines](https://www.academia.edu/32288968/AUTOMATIC_GENERATION_OF_HACHURE_LINES).
- Tilt-shift/miniature: the abrupt blur-to-sharp falloff resembles a macro lens — [Photoshop Cafe](https://photoshopcafe.com/miniature-photoshop-tutorial.htm); shallow depth of field is read by the eye as a cue of scale — [Lynda/LinkedIn Learning](https://www.lynda.com/Photoshop-tutorials/Creating-toy-effect/111233/119359-4.html); photographing a real miniature without tricks yields very narrow depth of field — [ProVideo Coalition](https://www.provideocoalition.com/fake_tilt_shift_cinematography/amp/); when a depth buffer exists, true DOF is preferable to a screen-space tilt-shift band — [luma.gl tilt-shift docs](https://luma.gl/docs/api-reference/shadertools/shader-passes/tilt-shift).
- Line Art cost scales with occlusion computation per modifier; use one modifier plus "Use Cache" — [Blender manual 4.0, Line Art](https://docs.blender.org/manual/it/4.0/grease_pencil/modifiers/generate/line_art.html).
- Resolution bumping exaggerates ridge/valley texture in coarse DEMs so mountains read as rugged — [Patterson](https://shadedrelief.com/bumping/bumping.html) (search snippet).

### Inferences
| Look | Hides | Fits (historical doc) | Headless recipe | Cost (est.) |
|---|---|---|---|---|
| Relief atlas ("National Geographic") | 10–30 m DEM softness, missing land cover | Campaign overviews, any period | Matte terrain, resolution-bumped normal, NW/NNW low sun, muted hypsometric or desaturated satellite, aerial perspective in comp | ~baseline |
| Engraved / hachure | Lack of photographic texture entirely | Colonial/pre-1950 chapters, matching period maps | GN: distribute points by slope, instance short curves aligned to gradient (down-slope), length ∝ 1/slope, width ∝ slope, skip flats; ink on paper-albedo terrain; optional cross-hatched shadow side | Medium (instance count; bake once per DEM) |
| Paper diorama / stepped contours | Small-scale inaccuracy (reads as a model) | Reconstructed battles, "how it unfolded" explainers | Quantise height `floor(z/step)·step` (GN or displacement), paper material with edge darkening, large soft key + world fill, true DOF scaled per section 3 | Low–medium |
| Miniature tilt-shift | Missing fine detail, people, vehicles | Travel/product; reconstructions that should look openly artificial | Real DOF with scene-scale f-stop; high saturation, bright soft light, top-down 30–50° angle, slight speed-up | ~0 |
| Ink outline (Line Art / Freestyle) | Flat materials, simple geometry | Explanatory beats, diagrams over terrain | One Line Art modifier + cache; flat or toon shading; limit to hero objects not full DEM | Medium–high on dense meshes |
| Archival-print look (halftone, misregistration) | CG cleanliness | Newspaper/propaganda-map moments | Texture prep in OpenCV + existing finish pass | ~0 |

- Rule of thumb: never mix two stylisations in one sequence, and keep the look fixed per chapter in the style-token file the prior research proposed.
- Miniature looks are honest for reconstructions (they announce artifice); photoreal looks for reconstructed historical places imply a document that does not exist—use the "Dựng lại 3D" label rule from the prior doc.

### Gaps
- No Blender-specific hachure, engraving or paper-diorama pipeline was found; recipes are inference.
- No source compared audience trust or comprehension across these styles for historical documentaries.

## 6. Judging 3D beauty automatically so an AI can iterate without a human each time

### Takeaway
Off-the-shelf aesthetic models are weak and biased judges: LAION's predictor is a small head on CLIP ViT-L/14 trained on photo-rating datasets (and an audit found demographic bias), and AesBench finds current multimodal LLMs have only "rudimentary" aesthetic perception with a significant gap to humans. The workable design is layered: explicit, pass-aware measurements (tonal range, depth-graded contrast, sun/camera angle, detail per depth band, palette adherence) as gates; reference-board similarity and pairwise VLM A/B comparisons against owner-approved frames as rankers; and the owner's verdicts as the calibration labels.

### Cited Findings
- LAION-Aesthetics Predictor V2 is a linear/MLP head on OpenAI CLIP ViT-L/14 image embeddings, trained on AVA, Simulacra Aesthetic Captions and LAION-Logos (1–10 ratings); a 2026 audit found it disproportionately keeps images whose captions mention women and filters those mentioning men or LGBTQ+ people — [arXiv 2601.09896](https://arxiv.org/html/2601.09896).
- The improved-aesthetic-predictor repository is Apache-2.0; weights are not separately licensed on the page; it takes CLIP embeddings as input — [GitHub, improved-aesthetic-predictor](https://github.com/christophschuhmann/improved-aesthetic-predictor). pyiqa wraps it as `laion_aes` — [IQA-PyTorch docs](https://iqa-pytorch.readthedocs.io/en/latest/autoapi/pyiqa/archs/laion_aes_arch/index.html) (prior research notes pyiqa's own PolyForm Noncommercial licence).
- Q-Align is an LMM trained with text-defined rating levels for quality and aesthetics; code and weights released; licence not stated in the snippet — [arXiv 2312.17090](https://export.arxiv.org/abs/2312.17090).
- AesBench: 2,800 expert-annotated natural, artistic and AI-generated images; evaluates perception, empathy, assessment and interpretation; finds MLLMs have only rudimentary aesthetic perception with a significant gap to humans — [AesBench arXiv 2401.08276](https://ar5iv.labs.arxiv.org/html/2401.08276).

### Inferences
**A three-tier "beauty judge" (synthesis; thresholds must be fitted to owner verdicts)**
1. *Pass-aware hard measurements on 3–8 stills* (cheap, deterministic):
   - Tonal structure: display-referred luminance 2nd–98th percentile spread, % clipped highlights/crushed shadows, and a "value grouping" score (how much of the frame falls into 3–4 clear value masses).
   - Aerial perspective: correlation between depth (Z/Mist) and contrast/saturation should be clearly negative; a flat correlation is the "default Blender" signature.
   - Light direction: angle between camera view azimuth and sun azimuth (side/back light 60–150° usually reads better than front light) and sun elevation band; computed from the scene file, not pixels.
   - Detail per depth band: Laplacian variance in near/mid/far bands; near band softer than mid flags over-magnified satellite texture (prior doc's 10 m problem) and should trigger GN scatter or a higher camera.
   - Composition: horizon tilt, horizon height near thirds, saliency centroid vs label positions from `tracks.json`.
   - Palette adherence and banding/flicker (already in prior gates).
2. *Reference comparison*: a curated board of approved frames per look (relief atlas, diorama, night, etc.); embed renders and references with a commercially licensed image encoder and report nearest-reference distance per shot; plus the LAION score only as a weak tiebreaker given its training bias toward photos.
3. *Pairwise VLM critique*: show the model the candidate next to the closest approved reference and the previous iteration, ask a fixed rubric (depth, light, value structure, colour harmony, clutter, label legibility) for a preference and the single biggest defect; AesBench's result argues against trusting absolute VLM scores, so only pairwise preferences and named defects are used, and each defect must map to a parameter the system can change (sun elevation, D for aerial perspective, bump strength, focal length).
- Every owner verdict ("đẹp"/"chưa đẹp") on a contact sheet should be stored with the render parameters and tier-1 metrics; after ~20–30 labelled shots, fit simple thresholds or a logistic model on tier-1 metrics—the same calibration approach the prior doc proposed for flicker and DOVER.
- Contact sheets: 4–8 frames (first, last, fastest camera, densest labels, deepest mist) at full resolution plus a 1/4-res strip, matching the repo's ≤8-frame snapshot habit.

### Gaps
- No licence was confirmed for Q-Align weights; no 2026 benchmark of VLMs on CG terrain/map renders was found; no study links any automatic metric to expert judgements of 3D map beauty.
- Thresholds for all tier-1 metrics are unsourced and must come from the owner's labelled verdicts.
