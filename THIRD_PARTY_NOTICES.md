# Third-party notices

EditVideo Agent's own code is under the Apache License 2.0 ([LICENSE](LICENSE), [NOTICE](NOTICE)). It builds on, bundles or downloads the
components below; each keeps its own licence. Check the terms that apply to **you** before commercial use.

## Rendering engines (installed by `npm ci` in `engines/`, not committed)

| Component | Licence | Notes |
|---|---|---|
| Remotion 4 (`remotion`, `@remotion/bundler`, `@remotion/renderer`) | Remotion License | Free for individuals, for-profit organisations with up to 3 employees, and non-profits; larger for-profit organisations need a Remotion company licence. See `engines/node_modules/remotion/LICENSE.md` and remotion.dev/license. |
| `@remotion/three`, React, React DOM, three.js, `@react-three/fiber` | MIT | |
| HyperFrames | Apache-2.0 | |
| GSAP | GSAP Standard "no charge" licence | Copied as `gsap.min.js` into every exported HyperFrames project. Read its terms (gsap.com/standard-license), including the clause on tools that compete with Webflow, before you build a product on the exports. |

## Fonts (bundled in `assets/fonts/`)

15 families under the SIL Open Font License 1.1 and Roboto Slab under Apache-2.0. Each family folder carries its
licence file; `assets/fonts/manifest.json` records upstream commit and SHA-256 per face. Exported projects include the
licence of every font they use.

## Icons (bundled in `assets/icons/tabler/`)

Fourteen icons from Tabler Icons 3.19.0 (https://tabler.io/icons, MIT License, copyright Paweł Kuna; licence file
alongside). `editvideo/icons.py` reads their paths for pictogram charts (`cinematic.data_story` visuals).

## Models (downloaded on demand by `setup.ps1 -Vision / -Temporal`, never committed)

| Model | Licence | Notes |
|---|---|---|
| faster-whisper / CTranslate2 Whisper weights | MIT | Speech recognition |
| SAM 2 (pinned commit) | Apache-2.0 | Tracking and segmentation |
| Depth Anything V2 Small | Apache-2.0 | Relative depth |
| LaMa | Apache-2.0 | Frame inpainting |
| OWLv2 base/16 ensemble (`google/owlv2-base-patch16-ensemble`, pinned revision) | Apache-2.0 | Open-vocabulary detection (`find_subjects`); installed with `allow_download` after the user agrees |
| SigLIP base/16-224 (`google/siglip-base-patch16-224`, pinned revision) | Apache-2.0 | Text/image similarity search (`find_subjects`); same install |
| ProPainter | S-Lab License 1.0 — **non-commercial** | Temporal inpainting; upstream checkout keeps its LICENSE |
| LTX-Video (local) | LTX open-weights licence | Read its model card before commercial use |
| MoGe-2 (`Ruicheng/moge-2-vitl-normal`, code from microsoft/MoGe) | MIT (code); weights per the model card | Archive photographs in 3D (`archive3d`); installed by hand (INSTALL.md 5.5), run in its own process |
| Real-ESRGAN weights | BSD-3-Clause | Upscaling in `restore` |
| Beat This! (`final0` checkpoint) | MIT (code and weights) | Beats and downbeats (`music`); `requirements.music.txt`, fetched by `music.fetch_beat_model()` |

## Offline narration (optional, installed by `setup.ps1 -Voice`, never committed)

| Component | Licence | Notes |
|---|---|---|
| piper-tts (Piper 1.x) | GPL-3.0-or-later | Run only as a separate process (`python -m piper`); EditVideo does not import or link it |
| Piper voice `vi_VN-vais1000-medium` | Dataset VAIS-1000: CC BY 4.0 (see the voice's MODEL_CARD) | Credit the voice/dataset when you publish narration made with it; renders list it in `CREDITS.txt` |
| faster-whisper `small` weights | MIT | Times the words of offline narration and runs the listen-back check (fetched by `-Voice`) |

## Media and look data

- LUTs in `assets/luts/` are original procedural EditVideo transforms.
- The design and effect previews in `assets/previews/` are rendered by EditVideo from its own procedural scenes.
- The LUT previews (`assets/previews/lut/`) apply those LUTs to a frame of the US Navy film "Operation Piranha" (1965;
  NARA 428-NPC-35664, NAID 84617). The frame is in the public domain.
- The demo films in `docs/demo/` are public-domain archive (US federal works). The music in *Leo thang* is CC BY 4.0
  (Kevin MacLeod). The full credits are in [docs/demo/README.md](docs/demo/README.md).
- The 3D/texture resources fetched by `fetch_source`/`register_resource` keep their source licence in the resource
  library (`resources(query)`); every render's source package carries `CREDITS.txt` built from those records.
- Sample films use NASA media (not copyrighted in the US; follow NASA media usage guidelines, no endorsement implied)
  and, where noted, Wikimedia Commons files under CC0 / CC BY / CC BY-SA (share-alike applies to adaptations).
  The round-10 examples name their clip authors and licences in their docstrings and end credits; their music is
  CC0 (Better Days by Uederson and High-Energy Adventure Theme by SRG774 from OpenGameArt; Komiku's "Mall" from
  Wikimedia Commons). No media is committed to the repository: `fetch_source` downloads it and records the credits.
- Reference videos downloaded for study are analysed locally and never redistributed.

## Python packages with terms to note

All core dependencies are permissive except these:
- **edge-tts** (LGPL-3.0): a core dependency for online narration. It calls Microsoft's online speech service, whose
  terms apply to what you generate.
- **soxr** (LGPL-2.1+): installed with Beat This!.
- **certifi** (MPL-2.0).
- **PyMuPDF** (AGPL-3.0, or a commercial licence from Artifex): only in the optional `geo` extra
  (`requirements.geo.txt`). `period_maps.sheet` imports it to read GeoPDF map sheets. If you install it and then
  distribute or serve the combined program, the AGPL applies to that combination. Without it, only GeoPDF reading is
  unavailable.

## Data sources fetched at run time (never committed)

| Source | Terms | Used by |
|---|---|---|
| Natural Earth 1:50m outlines | Public domain | maps (`geo_outline`, `history_map`, `map_matte`) |
| SRTM (NASA/USGS) | Public domain | terrain heights |
| Copernicus DEM GLO-30 | Free of charge; credit "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA" | terrain heights |
| Sentinel-2 cloudless 2016 (EOX IT Services) | CC BY 4.0 was stated for the 2016 mosaic; EOX now lists CC BY-NC-SA 4.0 for later years. The ledger treats it as unverified | terrain imagery (default) |
| Esri World Imagery | Esri's terms do not clear offline export or video use | terrain imagery, **opt-in for internal research only** (`EDITVIDEO_ESRI_INTERNAL=1`); renders made with it stay internal in the licence ledger |
| US National Archives catalog and scans (NARA), US Army Map Service sheets | Public domain (US federal works), each record's own use restriction checked | `pd_sources`, `period_maps` |

## Online services (optional, your own API keys)

Pexels, Runway, ComfyUI (local), an OpenAI-compatible LLM endpoint and the MCP servers you connect each have their
own terms. Those terms govern the media you fetch or generate. The licence ledger records the terms you state for
each asset; it cannot verify them for you.

## System tools (not bundled)

FFmpeg/FFprobe (LGPL/GPL depending on your build), Node.js, Python and Chromium (downloaded by Remotion) are used
from the host system under their own licences.

Blender (GPL-2.0-or-later) is run as a separate program. The scripts in `editvideo/blender_scripts/` run inside
Blender's Python. Like the rest of the code they are Apache-2.0, which is compatible with the GPL version 3 under
which Blender may be used.
