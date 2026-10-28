## Existing video and perception

Use `editvideo_project_from_video` to retain footage/audio without script/TTS, then split and add edits. It drops the final fractional frame for 30fps alignment and defaults captions off. Source without audio stays silent. `upsert_audio` can retain or place natural audio/SFX from audio/video sources with trim/gain/rate/fade/duck.

Index before analyzing long footage; return only useful evidence to model context. A scene candidate is a pixel change, not a semantic scene. `inspect_window` reveals its spacing; narrow windows for fast motion. `extract_clip` gives a continuous playable excerpt. `crop_detail` provides actual image/source mapping; never use resized image coordinates directly as original pixels.

`track_region` tracks textured features using sparse optical flow and returns x/y keyframes in target pixels. Respect `lost_at`; it is not semantic identity, scale/rotation tracking, segmentation or inpainting. Account for footage fit/crop/speed when mapping into timeline. Inspect tracked labels at several times.

