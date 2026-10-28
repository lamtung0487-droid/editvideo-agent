# Demo films

## The capability reel

[**EditVideo Agent in 89 seconds**](https://github.com/lamtung0487-droid/editvideo-agent/releases/download/demo-reel-v2/editvideo-reel-1080p.mp4) (1080p, 51 MB, on the release page; [720p preview](editvideo-reel-720p.mp4),
[poster](editvideo-reel.jpg)) shows the tools at work:
each chapter puts on screen what a tool did, full frame, before and after. The footage is real and credited
([full credits](editvideo-reel-CREDITS.md)). The tool names on screen are the MCP tools that made each picture.

| Chapter | What you see | MCP tools |
|---|---|---|
| Opening | A Blender terrain flight over the Điện Biên Phủ valley | `render_3d` |
| 01 Sees and follows a subject | A rally car found, then masked in every frame; the rest of the frame darkens around it and a label rides it. Then the lit source beside the 9:16 cut that keeps the car centred. | `find_subjects`, `track_subject` (SAM 2), `edit_subject` (spotlight, reframe) |
| 02 Cuts to the music | A rally montage whose cuts were moved onto the beats of the music you hear, with a 0.3x speed ramp on the drift. Underneath, a strip shows the beats the snap aimed at and where each cut landed. | `music_structure`, `snap_cuts_to_beats`, `retime_footage` |
| 03 Explains with 3D and motion graphics | A Three.js scene pulls back from the Earth to the Moon at true scale. A dimension line counts to 384,400 km, a row of about 30 Earths fills the gap, and light crosses it in 1.28 s. | `compose_scene3d`, `compose_explainer` |
| 04 Renders 3D, headless | A glTF model lit from the dark, then a Blender bloc map | `compose_product`, `render_3d` |
| 05 Grades colour | A drone shot as delivered and after `process_color`, with a divider sweeping across | `process_color` |
| 06 Builds history from the archive | Archive film inside the land it was shot in; the story's own documents shot close | `compose_cinematic` (`map_matte`, `dossier`) |
| 07 Checks its own work | Legal levels, flashes, banding, text contrast, loudness and the licence ledger (each work counted once, the works inside the nested films included), measured on the reel's own render | `motion_audit` (`gates=true`), `audit_audio`, `project_credits` |

The 1080p file is the master re-encoded at 4.5 Mbps; the 720p preview in this folder is 1.25 Mbps, small enough to
keep in the repository, and visibly softer. Its own captions are in English; the archive films it plays in chapter
06 keep their Vietnamese map labels and captions. The script that lays it out reads local renders and stays with the
private production files. The MCP calls it makes are the ones named above.

## The archive films

Three short archive films that EditVideo Agent built end to end from public-domain material. An AI composed each one
through the MCP recipes, then rendered it with Remotion and checked it with the delivery gates and the licence
ledger. The files here are 720p previews of the 1080p renders. Captions are in
Vietnamese.

| Film | Form | Length | Build script |
|---|---|---|---|
| [Leo thang 1964-1968](leo-thang-720p.mp4) ([poster](leo-thang.jpg)) | `archive_montage`: real archive cut tighter toward a hit, dated captions, a white-out | 70 s | not yet portable (see below) |
| [Lan rộng 1965-1968](lan-rong-720p.mp4) ([poster](lan-rong.jpg)) | `map_matte`: no cut; footage inside the land it was shot in, sourced events by date | 46 s | not yet portable (see below) |
| [Vịnh Bắc Bộ 1964](vinh-bac-bo-720p.mp4) ([poster](vinh-bac-bo.jpg)) | `dossier`: the story's own documents shot close, pencil marks, a white-out | 19.5 s | [`examples/public_domain/dossier_tonkin.py`](../../examples/public_domain/dossier_tonkin.py) |

What each one demonstrates, and the numbers measured on the render, are in
[docs/FAST_AI_WORKFLOW.md](../FAST_AI_WORKFLOW.md) (the archive montage section).

## Reproducing them

*Vịnh Bắc Bộ 1964* rebuilds on any machine:

```
python examples/public_domain/dossier_tonkin.py --render
```

The script fetches the five scans from Wikimedia Commons, checks that each is marked public domain, and renders the
film. Expect the delivery gates to pass and the ledger to come out clear for online use.

*Leo thang* and *Lan rộng* were cut from a local pool of National Archives reels. Their build scripts will become
portable examples once the National Archives catalog fetch (`editvideo.pd_sources`) works again. See
[examples/public_domain](../../examples/public_domain/README.md).

## Credits and licences

Every picture and voice is a work of the United States federal government, in the public domain under 17 U.S.C. 105:
- US Navy, Marine Corps, Army Signal Corps and Air Force films from the US National Archives (NARA). These are
  catalog records 428-NPC-34312, -34315, -34317, -34706, -34724, -34978, -35076, -35606, -35664, -36735 and -37204,
  111-LC-48206, and "Airpower at Khe Sanh" (USAF, 1968, via the Internet Archive).
- The Joint Chiefs of Staff cable 042158Z of 4 August 1964, the Joint Resolution of 10 August 1964 (Public Law 88-408)
  and the White House photographs NARA 192482 and 192484. These are NARA scans published through DPLA and Wikimedia
  Commons.

NARA's own reels of August 1964 are titled "Simulated Tonkin Gulf Incident". They show the ships and the strike being
readied, and they are never captioned as the attack.

The music in *Leo thang* is "The Escalation" by Kevin MacLeod (incompetech.com), licensed under Creative Commons:
By Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/).

All other sound is procedural, made by EditVideo. The typefaces are SIL OFL fonts bundled in `assets/fonts/`. The
maps use Natural Earth outlines (public domain).

The films are historical illustrations made with an AI-driven tool. A date or place shown on screen is the archive
record's own; restaged footage is never captioned as the event.
