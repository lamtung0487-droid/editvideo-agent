# Demo films

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
