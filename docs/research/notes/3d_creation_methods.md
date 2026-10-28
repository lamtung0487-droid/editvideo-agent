# Methods for documentary-grade 3D from archival photos, maps and data (headless Python + Blender 5.2, RTX 3060 12 GB)

Research date: 2026-10-27. Scope: methods only (camera projection, photogrammetry/splats, AI image-to-3D, procedural/GIS, map draping, vehicles/FX). Unless a line is labelled an inference, every claim has a source. Many VRAM and price figures come from vendors or third parties, and those are flagged.

---

## 1. Camera projection mapping of archival photos onto proxy geometry (2.5D / "3D photo animation")

### Takeaway
Camera projection is the lowest-risk, highest-authenticity method for history films. The pixels stay the archival photo, and only the camera moves. In 2026 it can be automated fully in a headless pipeline: a monocular geometry model (MoGe-2/3 gives depth, intrinsics/FOV and a textured GLB in one command; it is MIT code and runs in about 60 ms on a 3090-class GPU) provides the proxy geometry, and Blender's UV Project modifier or the model's own image-space UVs project the photo. The two main artefacts are stretching at depth edges and holes revealed behind foreground objects. Professionals hide them with small, slow moves, layer separation along natural edges, and cleaned or cloned background plates.

### Cited Findings
**How the technique works and where it comes from**
- Camera projection turns a 2D matte painting into a 3D-like scene through camera movement (the "2.5D technique"). — [3dart.it, Camera Projection in NUKE](https://3dart.it/camera-projection-in-nuke)
- A standard Nuke workflow (Ludovic Iochem tutorial): split the image into layers, build rough geometry for each layer, project the texture onto it, and let camera parallax create depth. — [Lester Banks](https://lesterbanks.com/?p=59178)
- The look is linked to *The Kid Stays in the Picture*. Joe Fellows animated hundreds of archival photos with the layered-stills approach. — [The Creators Project / Vice](https://thecreatorsproject.vice.com/blog/joe-fellows-teaches-us-how-to-master-25D-photography)
- Alexey Zakharov's "The Old New World" mapped Shorpy archive photographs onto 3D spaces, slicing the photos and animating people, cars and buildings separately. — [Fast Company](https://www.fastcompany.com/3058892/vintage-photos-of-new-york-come-to-life-in-this-3-d-animation); [aescripts](https://aescripts.com/learn/---the-old-new-world-----photo-based-animation-project)
- A different authentic route: a Tony Robinson WWI series used a lost archive of genuine period stereo (3D) photographs, assembled by a stereographer. — [Broadcast](https://www.broadcastnow.co.uk/ww1-in-3d-with-tony-robinson/5079868.article)
- Criticism: commenters say the parallax effect has become overused in documentaries. — [MetaFilter thread](https://metafilter.com/135845/The-Parallax-Effect-Bringing-still-images-to-pseudo-life)

**Blender mechanics**
- The UV Project modifier works like a slide projector. Its projector is a camera or empty projecting along −Z, it supports up to 10 projectors, and each face picks the closest projector aligned with its normal. When the projector is a camera, the projection follows its perspective/orthographic setting, and the aspect and scale controls apply only to cameras. — [Blender Manual 4.2, UV Project Modifier](https://docs.blender.org/manual/en/4.2/modeling/modifiers/modify/uv_project.html)
- Known limitation: in a perspective projection, vertices behind the camera map incorrectly. The workaround is to subdivide the geometry. The material is usually an Image Texture node reading the UV map that the modifier writes. — [Blender Manual 4.2](https://docs.blender.org/manual/en/4.2/modeling/modifiers/modify/uv_project.html)
- fSpy workflow: match the camera from vanishing lines in fSpy, import the camera into Blender with the fSpy importer add-on, align a box to the photographed box, project, then bake to a clean UV unwrap. — [Tutorial video (Blender 2.8)](https://tw.voicetube.com/videos/79060) (single source of modest quality)

**Monocular geometry models that build the proxy automatically**
- MoGe (Microsoft): `model.infer()` returns a metric point map, metric depth, normalized 3×3 intrinsics, a validity mask and, in some variants, normals. If you do not pass `--fov_x`, MoGe estimates the horizontal FOV. `moge infer --glb` writes a textured GLB (the photo as texture) and `--ply` writes vertex colours. Latency is 60 ms per image on an A100 or RTX 3090 (FP16, ViT-L). Code is MIT (the DINOv2 part is Apache 2.0); the README gives no licence for the weights. MoGe-2 sizes: ViT-L 326M, ViT-B 104M, ViT-S 35M. MoGe-3 was released 2026-08-18 (ViT-g 1.25B, ViT-L 370M) and needs FlexGEMM/Triton. — [microsoft/MoGe](https://github.com/microsoft/MoGe)
- Depth Pro (Apple) outputs metric depth plus focal length in pixels, with no camera metadata needed, and makes a 2.25-megapixel depth map in 0.3 s "on a standard GPU". — [apple/ml-depth-pro](https://github.com/apple/ml-depth-pro)
- Depth Pro licence: a custom Apple software licence that allows use, reproduction, modification and redistribution. It does not explicitly address commercial use. — [Depth Pro LICENSE](https://raw.githubusercontent.com/apple/ml-depth-pro/main/LICENSE)
- Depth Anything V2: code and the Small (ViT-S) checkpoint are Apache 2.0. The Base, Large and Giant checkpoints are CC-BY-NC-4.0 (non-commercial). — [HF model card, Large](https://huggingface.co/depth-anything/Depth-Anything-V2-Large); [Roboflow docs](https://inference-models.roboflow.com/models/depth-anything-v2/)
- Depth Anything 3 (ByteDance Seed, Nov 2025) recovers depth and camera pose from any number of views. The authors claim it beats VGGT by 44.3% on pose and 25.1% on geometry; arXiv v1 gave 35.7%/23.6%. Licences differ by checkpoint: DA3-BASE is Apache 2.0, DA3-GIANT is CC BY-NC 4.0. — [arXiv 2511.10647](https://arxiv.org/pdf/2511.10647); [DA3-BASE card](https://huggingface.co/depth-anything/DA3-BASE/blob/main/README.md); [DA3-GIANT card](https://huggingface.co/depth-anything/da3-giant)
- Marigold (ETH): code is Apache 2.0 and checkpoints are RAIL++-M. v1-1 checkpoints (2025-05-15) cover depth, normals, and "IID" appearance (albedo/roughness/metallic) and lighting. It is in Diffusers core since v0.28. `--fp16` cuts VRAM, Stable Diffusion works best at 768×768, and it was tested on an RTX 3090. — [prs-eth/Marigold](https://github.com/prs-eth/Marigold)

### Inferences
- **Recommended headless recipe** (an inference from the tools above, not a published pipeline):
  1. Run MoGe-2 (ViT-L, or ViT-B for speed) on the restored scan. Save `--maps --glb`. Read the FOV from the intrinsics.
  2. In `blender -b -P script.py`: create the camera with that FOV and the photo's aspect ratio, then import the GLB, or build your own grid by pushing vertices along camera rays by depth.
  3. Delete triangles whose depth jumps across an edge (a threshold on edge-length/depth ratio or on the normal angle relative to the view ray). This removes "rubber-sheet" smears and splits the mesh into foreground and background layers.
  4. Fill the holes the moving camera will reveal behind each foreground layer. Use a clone/patch on a background copy (the classic method), or an inpainting model, which must then be logged as AI restoration.
  5. Use an Emission shader (or an Image Texture fed straight to the output) so the photo's own lighting is kept. Render in EEVEE.
  At about 0.65 s/frame EEVEE (owner's measured figure for this machine), a 6-second 30 fps shot takes about 2 minutes.
- **VRAM:** MoGe ViT-L, Depth Anything V2-S and Depth Pro are single-image inferences and should fit comfortably in 12 GB, since 3090 timings are published and the models are 35M to about 1B parameters. MoGe-3 ViT-g (1.25B) may need FP16. Marigold under SD2 at 768 px with fp16 should also fit. None of the sources publishes 3060 numbers, so this is an inference.
- **Model choice by licence for a monetised channel:** prefer MoGe-2 (MIT code; check the weight terms), Depth Anything V2-Small or DA3-BASE (Apache 2.0), and Marigold (RAIL++-M use restrictions). Avoid DA-V2 Base/Large/Giant and DA3-Giant (non-commercial). Treat Depth Pro as a grey area until its licence is cleared.
- **Artefacts and how to hide them:**
  - stretching at occlusion edges
  - holes revealed behind objects
  - texture smearing on surfaces nearly parallel to the projection rays
  - wrong depth on grainy, low-contrast or retouched historical prints (the models are trained on modern photos)
  - "warped" human figures
  
  Mitigations: keep moves small (slow push-ins and short lateral drifts, short shot lengths); keep people as flat cut-out cards rather than depth-warped meshes, which looks more honest and holds up better; add film grain, motion blur and shallow DOF consistently across layers; and never move the camera past the point where unphotographed surfaces would show.
- **Authenticity:** projection is the most defensible method because no new image content is created. Inpainted fill is the exception, and it should be logged.

### Gaps
- I found no fxguide or befores & afters breakdown of a named documentary's photo-projection pipeline. The sources here are tutorials and press pieces.
- No source gives MoGe, Depth Pro or Marigold VRAM or runtime on an RTX 3060.
- No source gives the licence of MoGe's pretrained weights or the commercial terms of Marigold's RAIL++-M; check LICENSE-MODEL.txt and the HF cards.
- I found no published Blender script that automates depth-edge cutting and layered inpainting. That would be new code in this pipeline.
- No source compares depth-model accuracy on historical black-and-white photos specifically.

---

## 2. Photogrammetry and 3D Gaussian Splatting from multiple archival photos or video frames

### Takeaway
Multi-view reconstruction works only where the archive has several overlapping views of the same static subject: stereo cards, film/newsreel frames with camera motion, or a series of photos of one building. Classic COLMAP often fails on sparse, mixed-era sets. Feed-forward models (VGGT, MASt3R, DA3) still recover poses there, but less accurately. Splat training libraries (gsplat, Brush) are memory-efficient enough for a 12 GB card for modest scenes. Blender 5.3 (final release expected 10 Nov 2026) adds native splat import and EEVEE/Cycles rendering. Until then, add-ons render splats in Blender 5.2.

### Cited Findings
- On sparse aerial sets, DUSt3R, MASt3R and VGGT recovered all camera poses even at 10% overlap where COLMAP did not, but their accuracy still trailed COLMAP. The authors suggest using their poses as initial guesses refined by bundle adjustment. — [arXiv 2507.14798 (evaluation on photogrammetric aerial blocks)](https://arxiv.org/pdf/2507.14798)
- With fewer than 10 images (resized to 518 px max), the feed-forward models reached up to 50% more completeness than COLMAP. MASt3R degrades sharply as the image count grows, and all of them struggle with high-resolution, large sets. — [arXiv 2507.14798](https://arxiv.org/pdf/2507.14798)
- A 2026 comparison concludes that transformer-based methods cannot fully replace traditional SfM/MVS but complement it in challenging, low-resolution, sparse scenarios. — [arXiv 2604.10246](https://arxiv.org/pdf/2604.10246)
- Depth Anything 3 predicts consistent geometry from any number of views, with or without known poses, and claims to beat VGGT (see section 1 for licence by checkpoint). — [arXiv 2511.10647](https://arxiv.org/pdf/2511.10647)
- gsplat (Nerfstudio team) uses up to 4× less memory and up to 10% less training time than the original Kerbl et al. 3DGS implementation (A100, MipNeRF360). Apache 2.0. — [gsplat paper](https://arxiv.org/html/2409.06765v1)
- Brush: a Gaussian-splatting reconstruction engine for macOS, Windows, Linux, AMD and NVIDIA, Android and the browser. Its README calls it a proof of concept that is not yet performance-optimal (this may be dated). — [ArthurBrussee/brush](https://github.com/ArthurBrussee/brush)
- Postshot (Jawset) is commercial and subscription-only. Its free tier is limited to 4K SDR input, and since March 2026 it can no longer export .ply. — [3DVF](https://3dvf.com/en/gaussian-splatting-postshot-is-finally-out-of-beta-try-it-out-now/); [HKU BookStack (Mar 2026)](https://bookstack.hku.nl/books/3d-scan/page/gaussian-splatting-online-and-local)
- **Blender 5.3 native splats:**
  - splats are stored as a native PointCloud type with scale, rotation, opacity and radiance
  - import: PLY (auto-detected), SPZ up to v4, and USD `UsdVolParticleField3DGaussianSplat`
  - Geometry Nodes: an Import SPZ node and a Set Point Cloud Type node
  - Workbench, EEVEE and Cycles render splats with an emissive default shader; an early relighting method swaps in a Diffuse BSDF
  - limitations: performance; sRGB-to-linear colour handling not fully correct; Apply Transform doesn't update all Gaussian attributes; no export
  - status: alpha, final release expected 10 November 2026
  
  — [Digital Production, 22 Sep 2026](https://digitalproduction.com/2026/09/22/blender-5-3-brings-gaussian-splats-home/)
- **Add-ons for current Blender:**
  - BlendSplat: a free Geometry Nodes and shader library; EEVEE, plus Cycles since v0.6.0 (June 2026); splats do not receive shadows — [Radiance Fields](https://radiancefields.com/platforms/blendsplat)
  - KIRI Engine 3DGS add-on: open source, PLY import, EEVEE integration; the 2024 article said only Blender 4.2 was supported — [Radiance Fields](https://radiancefields.com/kiri-engine-gaussian-splatting-blender-add-on)
  - 3DGS Render: free, renders splats in Blender — [CG Channel](https://cgchannel.com/2024/09/free-tool-3dgs-render-renders-3d-gaussian-splats-inside-blender/)
  - PCD Splatter: E57 laser scans to splats, EEVEE and Cycles — [Radiance Fields](https://radiancefields.com/pcd-splatter-turns-e57-laser-scans-into-gaussian-splats-inside-blender)

### Inferences
- **When archival material allows it:**
  - (a) newsreel or amateur film with a moving camera past a static scene: extract frames → COLMAP/GLOMAP, or VGGT/DA3 poses refined by bundle adjustment → gsplat or Brush
  - (b) stereo cards (two views): a feed-forward pair model gives depth, which is better used as a 2.5D projection (section 1) than as a full splat
  - (c) many photos of a still-standing monument, including modern photos: photogrammetry of the present-day site, labelled as such
  
  Single photos should use section 1, not splats.
- **12 GB feasibility:** gsplat's 4× memory reduction, and Brush targeting consumer hardware, suggest that scenes of a few hundred frames at 1–2 MP train on 12 GB, especially with densification caps. This is an inference; no 3060 benchmark was found.
- **Blender path:** stay on 5.2.2 with BlendSplat (Geometry Nodes, scriptable headless) for now. Plan to move to 5.3's native PointCloud splats after 10 Nov 2026, and test the colour-space issue before trusting the output.
- **Authenticity:** splats rebuilt from real footage are measurement, not generation. Surfaces the archive never saw will be blurry or "floaters", and the camera should stay within the original viewpoints.

### Gaps
- No source tests COLMAP or VGGT on actual historical photo collections (mixed lenses, eras, prints).
- No source gives gsplat or Brush peak VRAM on a 12 GB card, or Nerfstudio splatfacto memory on consumer GPUs.
- I could not confirm whether the KIRI add-on works on Blender 5.2, or the current Postshot prices.

---

## 3. AI image-to-3D and text-to-3D models (local and cloud) as of 2025–2026

### Takeaway
On a 12 GB RTX 3060, the officially supported local options are the small, fast models: Stable Fast 3D (about 6 GB; Stability Community licence, free under $1M revenue), TripoSR (about 6 GB; MIT), and Hunyuan3D 2.1 shape-only (10 GB; texturing needs 21 GB). TRELLIS (16 GB) and TRELLIS.2 (24 GB) officially need more VRAM and are tested on Linux only, though vendors claim low-VRAM ComfyUI modes. Hunyuan's licence excludes the EU, UK and South Korea and requires that AI-generated content be labelled. For history films these models only suit generic props (crates, period vehicles as illustration), and every output must be labelled as illustration.

### Cited Findings
**Microsoft TRELLIS / TRELLIS.2**
- TRELLIS (v1): needs ≥16 GB VRAM, verified on A100/A6000, tested on Linux only. MIT, though some submodules (diffoctreerast, modified FlexiCubes) have their own licences. Outputs 3D Gaussians (PLY), radiance fields and meshes with textured GLB. TRELLIS-image-large is 1.2B; text models are 342M to 2.0B. The image-conditioned model is recommended over text. Multi-image conditioning was added 2024-12-18 and is tuning-free. — [microsoft/TRELLIS](https://github.com/microsoft/TRELLIS)
- TRELLIS.2-4B: ≥24 GB VRAM, Linux only, verified on A100/H100. On an H100 it takes about 3 s at 512³, 17 s at 1024³ and 60 s at 1536³. Output is a mesh with PBR materials including opacity (GLB). MIT. Paper dated 16 Dec 2025. Raw meshes can have holes. It is a base model not tuned for aesthetics. — [HF model card](https://huggingface.co/microsoft/TRELLIS.2-4B)
- A commercial site claims TRELLIS.2 runs on a 6–8 GB GPU in low-VRAM mode, and at full resolution on a 12 GB RTX 3060, via ComfyUI `--lowvram`. This is unverified vendor marketing. — [trellis2.app](https://trellis2.app/blog/trellis-2-low-vram)

**Tencent Hunyuan3D 2.1**
- Takes 10 GB VRAM for shape, 21 GB for texture, and 29 GB for both. It has a `--low_vram_mode` flag (savings not documented) and supports macOS, Windows and Linux. The shape model is 3.3B and the paint model 2B. It generates PBR materials. Released 13 June 2025. — [Tencent-Hunyuan/Hunyuan3D-2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)
- **Licence:**
  - Territory is "worldwide … excluding the European Union, United Kingdom and South Korea", and using outputs outside the Territory is unlicensed
  - products above 1M monthly active users must request a licence
  - the acceptable-use policy prohibits publishing machine-generated material without clearly identifying it as such
  - outputs may not be used to train other AI models
  - Tencent claims no rights in outputs
  
  — [Hunyuan3D 2.1 LICENSE (mirror)](https://gitserver.onethingai.com/ai-models/Hunyuan3D-2.1/raw/branch/main/LICENSE). The 2.0 licence has the same territory carve-out. — [HF Hunyuan3D-2 LICENSE](https://huggingface.co/tencent/Hunyuan3D-2/blob/main/LICENSE)

**Stability AI (SF3D, SPAR3D), TripoSR**
- Stable Fast 3D: about 6 GB VRAM for one image by default. Outputs a GLB with UV-unwrapped textures, predicted material parameters and "delit" colour. Linux is the baseline; Windows is experimental (needs VS 2022, quality not guaranteed). — [Stability-AI/stable-fast-3d](https://github.com/Stability-AI/stable-fast-3d)
- SF3D licence: the Stability Community License is free for research and for commercial use under $1M annual revenue; above that an enterprise licence is required. — [HF model card](https://huggingface.co/stabilityai/stable-fast-3d)
- SPAR3D (CES 2025) is reportedly also under the Community licence. This comes from one secondary article and is not confirmed. — [all-ai.de](https://www.all-ai.de/news/top-news24/stability-ai-präsentiert-spar3d-auf-der-ces-2025)
- TripoSR (Stability + Tripo): MIT for code and weights. About 6 GB VRAM by default. Under 0.5 s per object on an A100. Trained on a CC-BY subset of Objaverse. — [TripoSR paper](https://arxiv.org/html/2403.02151v1); [CG Channel](https://www.cgchannel.com/?p=155878); [npm listing](https://npmjs.com/package/tripo-ssr)

**Cloud APIs (third-party figures, which conflict; check vendor pages)**
- Meshy: about $0.60 per textured text-to-3D model (preview plus refine) on the $20/1,000-credit Pro plan; image-to-3D is 30 credits; the API needs Pro or higher. Another source lists different tiers ($10 Pro). — [3D AI Studio comparison](https://www.3daistudio.com/blog/best-3d-model-generation-apis-2026); [Ludo.ai](https://ludo.ai/compare/meshy-alternatives)
- Tripo: 1 API credit = $0.01; textured text-to-3D is 20 credits and image-to-3D 30 credits; the Professional plan is $19.90/month for 3,000 credits. — [Tripo review (2026)](https://pasqualepillitteri.it/en/news/7811/tripo-ai-review-3d-model-generator)
- Rodin (Hyper3D): generation is free, downloads cost credits (high-density about 40 credits); an estimated $0.50–1.50 per model; Creator plan $20/month. — [Dupple review](https://dupple.com/reviews/rodin-ai); [Dupple guide](https://dupple.com/learn/best-ai-3d-modeling-tools)

### Inferences
- **Practical fit on this machine:**
  - SF3D and TripoSR run anywhere, with seconds-per-object output and low-detail meshes.
  - Hunyuan3D 2.1 shape fits in 12 GB. Its texture stage needs `--low_vram_mode` or CPU offload; untested here, so expect slow runs or OOM. A pragmatic workaround is to texture the mesh by camera-projecting the source image in Blender (section 1).
  - TRELLIS v1 and v2 officially exceed 12 GB and are Linux-only. Treat community low-VRAM claims as something to test, not to rely on. WSL2 may be needed.
- **The user appears to be in Vietnam, which is inside Hunyuan's Territory.** But the licence makes using outputs outside the Territory unlicensed, so publishing on YouTube to EU/UK viewers is a legal grey area. Prefer the MIT models (TRELLIS, TripoSR) for anything published, or get legal advice.
- **Cost comparison:** cloud generation at about $0.2–1.5 per asset is cheap per prop. But the owner's rule is that paid generations must be announced, and these vendors' licences and data retention need checking. Local SF3D/TripoSR cost nothing.
- **Documentary suitability: low for "evidence" shots.** Image-to-3D invents unseen sides of an object, so outputs must carry an "illustration / AI reconstruction" label (the Hunyuan licence makes this a contractual obligation). Use them for background props, not for identifiable historical objects.

### Gaps
- No measured RTX 3060 timings for any of these models.
- No current, official TRELLIS.2 low-VRAM figures.
- Hunyuan3D 2.5/3.0 (cloud-only?) status and licence not checked.
- InstantMesh licence and VRAM not verified (the search returned nothing).
- SPAR3D VRAM and licence not confirmed.
- No official Meshy, Tripo or Rodin price pages were fetched; all prices are third-party.

---

## 4. Procedural generation: Geometry Nodes terrain/vegetation/roads/trenches, OSM import, period settlements

### Takeaway
Blosm (free base version, GPL) and BlenderGIS bring OSM buildings and roads plus SRTM/30 m terrain into Blender with real coordinates. Both import present-day data, so period settlements need footprints traced from georeferenced historical maps, then extruded and scattered procedurally. Geometry Nodes covers trenches, vegetation and road detail, but I fetched no primary sources on that, so those recommendations are inferences.

### Cited Findings
- Blosm (formerly blender-osm) imports OpenStreetMap data, Google 3D cities and terrain worldwide. The base version is free (or pay-what-you-want) and its source is GPL. — [vvoovv/blosm](https://github.com/vvoovv/blosm); [OSM Wiki](https://wiki.openstreetmap.org/wiki/Blender-osm)
- The free version imports buildings untextured but uses height and floor count, supports many roof shapes, imports terrain at about 30 m resolution and places buildings on it, imports rivers, lakes, forests and vegetation as polygons, and gives roads and railways a width. Premium ($17.80) adds textures, materials and 3D trees. Google 3D Tiles are unavailable for new projects created after 8 July 2025 with an EU/EEA billing address. — [OSM Wiki](https://wiki.openstreetmap.org/wiki/Blender-osm); [Gumroad](https://prochitecture.gumroad.com/l/blender-osm)
- BlenderGIS imports Shapefile vectors, raster images, GeoTIFF DEMs and OSM XML. It also offers web basemaps, OSM queries, SRTM download, Delaunay terrain triangulation, dropping objects onto terrain, scene georeferencing, cameras from geotagged photos, and a camera setup that renders a new georeferenced raster. It needs Blender ≥2.83. OpenTopography needs a free API key (since 2022). It has 300 open issues, so its maintenance status is unclear. — [domlysz/BlenderGIS](https://github.com/domlysz/BlenderGIS)

### Inferences
- **Headless pipeline:** pre-process GIS data outside Blender with GDAL/OGR, since Blosm and BlenderGIS are UI add-ons and their operators may be awkward to run headless. Write DEM heightfields as 16-bit PNG or EXR plus a JSON of bounds. In Blender, build the terrain with a grid plus a displacement or Geometry Nodes "Set Position" from the image, and extrude building footprints from GeoJSON with a Python reader. This avoids depending on add-on UIs.
- **Trenches and roads:** draw them as curves along traced lines → Geometry Nodes "Curve to Mesh" with a profile, plus a boolean or displacement cut into the terrain. Scatter vegetation with "Distribute Points on Faces" weighted by masks derived from the map. Instance low-poly CC0 assets so EEVEE stays near the owner's ~0.65 s/frame.
- **Period settlements:** OSM shows today's town. For 1940s–1970s scenes, trace footprints from the georeferenced period map (section 5) in QGIS → GeoJSON → extrude with storey heights taken from photos. Label it as a reconstruction. Generated "plausible" villages must not be presented as specific real places.

### Gaps
- No primary source fetched on Geometry Nodes for trenches or scattering (the Blender manual pages were not retrieved this session).
- I could not confirm whether Blosm or BlenderGIS operators run in `blender -b` background mode on Blender 5.2, or BlenderGIS's licence and 5.x compatibility.
- I found no published tool that procedurally generates historically plausible settlements from period maps.

---

## 5. Draping georeferenced vintage maps on terrain; hypsometric tint, hillshade and relief styles; tilt-shift vs realistic scale

### Takeaway
The standard method is to georeference the scanned map with ground control points in GDAL or QGIS (affine first, then a thin-plate-spline refinement), warp it to the DEM's CRS, and use it as the terrain's texture in Blender. Blender is an established tool for cartographic shaded relief. Large vertical exaggeration is normal, and Cycles renders take minutes per frame at high quality. Choose between a "miniature" relief-map look and a realistic look deliberately. No source was found for tilt-shift specifics.

### Cited Findings
- Georeferencing means picking ground control points (features shared by the historical and current map) and computing a warp that stays close to the matches. — [arXiv 1703.07138 (historical geocoding)](https://arxiv.org/pdf/1703.07138); [Old Maps Online](https://www.oldmapsonline.org/blog/2008/07/georeferencing-images-by-control-points)
- GDAL workflow: attach GCPs with `gdal_translate`, warp with `gdalwarp`. For non-affine historical maps, use `gdalwarp -tps` on a VRT with GCPs. A suggested two-pass approach: an affine fit from the corners first, then TPS with finer points such as road intersections. — [gdal-dev mailing list](https://lists.osgeo.org/pipermail/gdal-dev/2010-May/024469.html)
- Caution: users have reported warped output shifting away from the GCP targets, and GDAL mislocates a tile if the GCPs don't form a clean affine transform. Check the results after warping. — [GDAL ticket #5809](https://trac.osgeo.org/gdal/ticket/5809)
- QGIS has a GDAL-based Georeferencer. ArcGIS Pro needs at least 3 GCPs, ideally many more. — [GeoJamal tutorial](https://en.geojamal.com/2014/11/georeferencing-using-qgis-scanned-maps.html); [ArcGIS StoryMap](https://storymaps.arcgis.com/stories/dd75d0398f7d4ded924d303161895b8b)
- Blender is widely used for shaded relief. Daniel Huffman's tutorial is the reference write-up. — [Andy Woodruff, "Seasonal relief"](https://andywoodruff.com/blog/seasonal-relief/)
- In practice, users needed much stronger displacement than the tutorial default (10× instead of 0.3) because the default relief was too subtle. — [mdione blog, Blender hillshading](https://www.grulic.org.ar/~mdione/glob/posts/blender-hillshading-and-mapnik/)
- Relief setup: Cycles with the Experimental feature set (adaptive displacement), and a plane scaled to the DEM's aspect ratio. A ray-traced relief takes minutes. — [GMT.jl docs, Shading with Blender](https://www.generic-mapping-tools.org/GMTjl_doc/tutorials/blender_shading/blender_rt.html)
- Newsroom tutorials use BlenderGIS to bring GIS data into Blender for 3D maps. — [UC Berkeley J-School tutorial](https://multimedia.journalism.berkeley.edu/tutorials/blender/)

### Inferences
- **Pipeline:**
  1. Scan → `gdal_translate -gcp …` → `gdalwarp -tps -t_srs <DEM CRS> -te <DEM bounds>` → a PNG/TIFF exactly aligned to the DEM.
  2. In Blender: a subdivided plane (or adaptive subdivision in Cycles) with the DEM as displacement and the warped map as base colour.
  3. Mix with modern satellite imagery or hillshade through a mask or a Mix node (e.g. animate the old map fading over the satellite base).
  
  Use EEVEE for animation, with real geometry displacement since EEVEE has no adaptive subdivision. Keep Cycles for hero stills.
- **Styles:** a hypsometric tint is a colour ramp on height (Geometry/Position Z → ColorRamp). Hillshade comes from a low, warm sun lamp plus orthographic top-down renders. A "relief map" look is high exaggeration with soft sky light. These are standard shader setups, and no source was fetched for specific node graphs.
- **Tilt-shift/miniature vs realistic:** shallow DOF (a small f-number focused on a band), a high camera angle, saturated colours and sped-up motion read as "model / illustration". That suits signalling "this is a reconstruction, not footage". Realistic scale (a long lens, haze/atmosphere, eye-level heights) risks being mistaken for real aerial footage, so it needs a label. This is an editorial inference, and no source was found.
- **Authenticity:** georeferencing warps the historical map. State the source map and date on screen, and avoid "correcting" the map's historical errors without noting it.

### Gaps
- Daniel Huffman's original tutorial page was not fetched.
- No source fetched for hypsometric-tint node setups or for tilt-shift/miniature conventions in documentaries.
- No source on GDAL's error tolerance for heavily distorted hand-drawn maps.

---

## 6. Vehicle and aircraft animation, contrails, smoke and fire: Mantaflow cost vs VDB assets and flipbooks

### Takeaway
Mantaflow is still CPU-bound (its early CUDA support was dropped), so high-resolution pyro bakes are slow on this machine. The cheapest high-quality route is pre-simulated CC0 OpenVDB packs (JangaFX: 15 free fire, smoke and explosion sims) loaded as Blender volume sequences, plus image flipbooks for distant smoke. Paid GPU solvers exist (Fumaris for Blender 5.1+ via Vulkan, Pro Pyro) if custom sims are needed. Flight paths and rigging of downloaded models are standard Blender tasks, but no sources were fetched for them.

### Cited Findings
- Mantaflow was supposed to get CUDA acceleration but quickly dropped CUDA support. Every setting change needs a CPU re-bake. — [BlenderArtists, "Lets talk about Mantaflow"](https://blenderartists.org/t/lets-talk-about-mantaflow/644346?page=51); [devtalk, Realtime GPU smoke](https://devtalk.blender.org/t/realtime-gpu-smoke-simulation/13142?page=6)
- A community GPU solver showed large speedups over Mantaflow on a 300³ domain, but it is work in progress, not shipped. — [devtalk](https://devtalk.blender.org/t/realtime-gpu-smoke-simulation/13142?page=6)
- Fumaris: commercial interactive GPU smoke/fire for Blender. Bakes standard OpenVDB sequences, needs Blender 5.1+ and a Vulkan-capable GPU, and is a different solver from Mantaflow. — [Superhive docs](https://superhivemarket.com/products/fumaris/docs); [80.lv](https://80.lv/articles/create-gpu-based-smoke-fire-simulations-directly-in-blender-with-this-extension/)
- Pro Pyro: commercial sparse GPU volume solver for Blender (Windows, Linux, macOS). — [BlenderArtists release thread](https://blenderartists.org/t/released-pro-pyro-sparse-gpu-volumetric-solver-windows-linux-macos/1634317)
- JangaFX released 15 free EmberGen gaseous sims (explosions, fire and smoke plumes, shockwaves, ground-impact dust, a tornado) as VDB under CC0, so commercial use is allowed. — [CG Channel 2022](https://www.cgchannel.com/?p=135578); [CG Channel 2020](https://www.cgchannel.com/?p=113054); [80.lv](https://80.lv/articles/free-vdb-simulations)

### Inferences
- **Aircraft and vehicles:** import a CC0 or appropriately licensed GLB, parent it to an empty with a Follow Path constraint on a Bezier curve (tilt the curve for banking), and drive speed through the path's evaluation time.
  - Contrails: a Geometry Nodes simulation zone that records the wingtip positions into a curve → Curve to Mesh with a fading emission/volume, or simply a particle trail.
  - Propellers and wheels: driver expressions on rotation. No rig is needed for most documentary shots.
- **Smoke and fire budget:** EEVEE volume sequences from VDB render fast. Cycles volumes are much slower; budget extra. Mantaflow at a useful resolution (≥256³) on CPU can take hours per sim, a figure from experience that no source here gives. Prefer the CC0 VDBs, or render a VDB once to an RGBA image sequence and use it as a flipbook card for distant or background columns.
- **Authenticity:** an animated aircraft over a map is illustration, so use the correct aircraft type and markings for the date. Generic explosions should not be cut so they read as footage of a specific event. Label reconstructions.

### Gaps
- No sources fetched on Blender rigging for vehicles and aircraft, Follow Path workflows, or contrail techniques.
- No measured Mantaflow bake times on a comparable CPU.
- I did not confirm that the JangaFX free-VDB download page is still live.
- No VRAM figures for Fumaris or Pro Pyro on 12 GB.

---

## 7. Cross-method comparison and authenticity/ethics for historical documentaries

### Takeaway
Rank methods by authenticity: real-data methods first (camera projection of real photos, reconstruction from real footage, GIS/maps), then procedural reconstruction, then generative AI 3D. Industry guidance (the Archival Producers Alliance, Sept 2024, endorsed by the IDA) asks for transparency. That means cue sheets for every GenAI element and crediting AI-generated content the way archival footage is credited. The Hunyuan3D licence also makes undisclosed AI output a breach.

### Cited Findings
- The Archival Producers Alliance's *Best Practices for Use of Generative AI in Documentaries* (Sept 2024) builds on editorial independence, accuracy, transparency and inclusiveness. — [PBS Standards](https://www.pbs.org/standards/blogs/standards-articles/archival-producers-alliance-develops-guidelines-for-ai-use-in-documentaries/)
- Practical steps: keep cue sheets for every GenAI element and list AI-generated content in the credits as you would archival footage or music. The guide was endorsed by the IDA and Kartemquin, among others. — [Desktop Documentaries summary](https://www.desktop-documentaries.com/best-practices-for-use-of-gen-ai-in-documentaries.html); [MIT Open DocLab](https://opendoclab.mit.edu/presents/archival-producers-alliance-apa-best-practices-use-generative-ai-documentaries/)
- The APA warns that GenAI models draw on an incomplete historical record, since most physical audiovisual archives remain undigitised. This is a bias risk for history reconstructions. — [Desktop Documentaries summary](https://www.desktop-documentaries.com/best-practices-for-use-of-gen-ai-in-documentaries.html)
- The Hunyuan3D 2.1 acceptable-use policy prohibits publishing machine-generated material without clearly identifying it. — [Hunyuan3D 2.1 LICENSE](https://gitserver.onethingai.com/ai-models/Hunyuan3D-2.1/raw/branch/main/LICENSE)

### Inferences
Comparison matrix, synthesised from sections 1–6. VRAM/time figures are cited where available; others are estimates.

| Method | Quality ceiling | 12 GB VRAM / time | Cost | Licence risk | Automation effort (headless) | Documentary suitability |
|---|---|---|---|---|---|---|
| Camera projection + depth (MoGe-2 / DA-V2-S / Depth Pro) | High for short, small moves; breaks on big orbits | Depth: well under 12 GB, ~0.06–0.3 s/image on 3090-class; EEVEE ~0.65 s/frame | Free | Low (MIT/Apache); avoid DA-V2-L/G and DA3-Giant (NC); Depth Pro unclear | Medium: needs a depth-edge cutting and fill script | **Best**: pixels stay archival; log any inpainting |
| fSpy/manual proxy boxes + UV Project | Very high for architecture | Trivial | Free | None | High manual effort (vanishing lines); semi-automatable | Best for buildings and streets |
| Photogrammetry / 3DGS (COLMAP or VGGT → gsplat/Brush → BlendSplat or Blender 5.3) | Photoreal inside the captured views | Likely fits for modest scenes (gsplat 4× leaner); training minutes to hours | Free (Postshot paid) | Low (gsplat Apache 2.0) | Medium–high; needs suitable multi-view archive | Good when the source is real footage or many photos; no invented views |
| AI image-to-3D local (SF3D, TripoSR, Hunyuan 2.1 shape) | Medium; soft, invented backsides | ~6 GB (SF3D/TripoSR); 10 GB shape-only (Hunyuan) | Free | SF3D <$1M revenue; Hunyuan territory/MAU/labelling | Low–medium (CLI/Python) | Props only; label as illustration |
| AI image-to-3D local, large (TRELLIS, TRELLIS.2) | Highest open-model quality | Officially 16 / 24 GB, Linux only; low-VRAM claims unverified | Free | MIT | Medium–high (Linux/WSL, CUDA builds) | Props only; label |
| Cloud (Meshy, Tripo, Rodin) | High | No local VRAM | ~$0.2–1.5/model (third-party) | Check ToS, data retention | Low (REST) | Props only; label; announce paid use |
| GIS: DEM + georeferenced period map + OSM/footprints | High, data-true | Low VRAM; Cycles relief minutes/frame, EEVEE fast | Free (Blosm base GPL) | OSM ODbL attribution (not verified here); Google 3D Tiles terms | Medium (GDAL + bpy) | Excellent: cite map source and date |
| Procedural (Geometry Nodes scatter, trenches, settlements) | Medium–high | Low | Free | None | Medium | Reconstruction; label as such |
| FX: CC0 VDBs / flipbooks vs Mantaflow | High (VDB) | VDB in EEVEE OK; Mantaflow CPU-bound | Free (JangaFX CC0); GPU solvers paid | Low | Low (VDB import) | Generic; don't imply specific event footage |

- **Labelling convention** (inference, combining the APA and Hunyuan rules): on-screen "Minh họa / Illustration" or "Dựng lại 3D / 3D reconstruction" tags for generated or procedural shots, plus a cue sheet listing tool, model version, licence and inputs for every 3D element. This fits the existing per-export check and credits-from-licences tooling in this repo.
- **Rule of thumb for history films:** where a real photo exists, project it (section 1). Where several real views exist, reconstruct (section 2). Where only maps and data exist, build from GIS (sections 4–5). Use generative 3D last, for generic props, and label it.

### Gaps
- The full APA PDF was not retrieved; the points above come from secondary summaries (PBS, Desktop Documentaries, MIT Open DocLab).
- No source found on Vietnamese broadcaster or platform rules (YouTube/TikTok synthetic-content disclosure) for 3D reconstructions specifically.
- OSM's licence (ODbL attribution) was not verified in this session.
