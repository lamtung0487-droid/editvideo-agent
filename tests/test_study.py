"""study_video: rolling auto-caption de-duplication, technique vocabulary, rhythm on a clip with known cuts."""
from editvideo import store, study
from editvideo.media import FFMPEG, command

AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000 align:start position:0%
today<00:00:01.400><c> we</c><00:00:01.700><c> talk</c><00:00:02.000><c> about</c><00:00:02.400><c> the</c><00:00:02.600><c> j</c><00:00:02.800><c> cut</c>

00:00:03.000 --> 00:00:03.010 align:start position:0%
today we talk about the j cut


00:00:03.010 --> 00:00:05.000 align:start position:0%
today we talk about the j cut
and<00:00:03.400><c> a</c><00:00:03.600><c> speed</c><00:00:04.000><c> ramp</c><00:00:04.300><c> with</c><00:00:04.600><c> motion</c><00:00:04.800><c> blur</c>

00:00:05.000 --> 00:00:07.000 align:start position:0%
and a speed ramp with motion blur
then &amp; color grading with a LUT
"""


def test_auto_captions_are_deduplicated_and_terms_found(tmp_path):
    p = tmp_path / "v.en.vtt"
    p.write_text(AUTO_VTT, encoding="utf-8")
    cues = study.parse_subtitles(p)
    assert [c["text"] for c in cues] == ["today we talk about the j cut", "and a speed ramp with motion blur", "then & color grading with a LUT"]
    assert cues[0]["start"] == 1.0 and cues[1]["start"] == 3.01
    hits = study.glossary_hits(cues)
    assert hits["editing"]["j cut"]["at"] == ["00:01"] and "speed ramp" in hits["editing"]
    assert "motion blur" in hits["motion"] and "lut" in hits["color"] and "color grading" in hits["color"]
    assert "cut" not in hits.get("editing", {})  # vocabulary matches whole terms, not fragments


def test_subtitles_are_bound_to_the_video_not_an_unrelated_sibling(tmp_path):
    source = tmp_path / "lesson.mp4"
    unrelated = tmp_path / "another.en.vtt"
    unrelated.write_text(AUTO_VTT, encoding="utf-8")
    assert study.subtitle_path(source) is None
    matching = tmp_path / "lesson.en-orig.vtt"
    matching.write_text(AUTO_VTT, encoding="utf-8")
    assert study.subtitle_path(source) == matching
    human = tmp_path / "lesson.en.vtt"
    human.write_text(AUTO_VTT, encoding="utf-8")
    assert study.subtitle_path(source) == human
    assert study.subtitle_path(source, unrelated) == unrelated
    import pytest
    with pytest.raises(FileNotFoundError):
        study.subtitle_path(source, tmp_path / "missing.vtt")


def test_study_measures_rhythm_and_reads_sibling_subtitles(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize()
    clip = tmp_path / "ref" / "video.mp4"
    clip.parent.mkdir()
    # Four 2.5 s shots of very different colours: three hard cuts at 2.5, 5, 7.5 s.
    parts = []
    for i, colour in enumerate(("red", "blue", "white", "green")):
        part = tmp_path / f"p{i}.mp4"
        command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=30:d=2.5", "-pix_fmt", "yuv420p", part])
        parts.append(part)
    (tmp_path / "list.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    command([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", tmp_path / "list.txt", "-c", "copy", clip])
    (clip.parent / "video.en.vtt").write_text(AUTO_VTT, encoding="utf-8")
    r = study.study_video(clip, sheet_frames=6, strips=[[1, 3]], beats=False)
    assert r["rhythm"]["shots"] == 4 and abs(r["rhythm"]["median_shot_s"] - 2.5) < .1
    assert r["transcript"]["cues"] == 3 and "editing" in r["techniques_mentioned"]
    assert len(r["strips"]) == 1 and r["sheet"].endswith("overview.jpg")
    assert any(c.startswith("#") for c in r["look"]["dominant_colors"])
    # The event list stays with its study instead of an unreferenced observations/events-*.json.
    assert r["events"]["list"].endswith("events.json") and store.read_json(__import__("pathlib").Path(r["events"]["list"]))["events"] is not None
    assert not list((store.DATA / "observations").glob("events-*.json"))


def test_ambiguous_words_count_only_in_their_craft_sense():
    cues = [{"start": 1.0, "text": "now hit enter to apply it"}, {"start": 2.0, "text": "drag and drop the clip here"},
            {"start": 3.0, "text": "add a hit sound effect on the cut"}, {"start": 4.0, "text": "the bass drop lands on the beat"},
            {"start": 5.0, "text": "we go into the pre-log node"}]
    hits = study.glossary_hits(cues)
    assert hits["sound"]["hit"]["at"] == ["00:03"] and hits["sound"]["drop"]["at"] == ["00:04"]
    assert hits["color"]["log"]["count"] == 1
    more = [{"start": 1.0, "text": "log in to your account"}, {"start": 2.0, "text": "then the post log node"},
            {"start": 3.0, "text": "make the edit hit the beat"}, {"start": 4.0, "text": "a reverse [Music] cymbal swell"}]
    hits = study.glossary_hits(more)
    assert hits["color"]["log"]["at"] == ["00:02"] and hits["sound"]["hit"]["at"] == ["00:03"]
    assert hits["editing"]["reverse"]["at"] == ["00:04"]


def test_transition_detector_finds_dissolve_and_dip_but_not_a_cut(tmp_path):
    clip = tmp_path / "t.mp4"
    # A (bars) dissolves into B (test pattern) over 1 s at 2 s; B fades to black, holds 0.5 s, C (mandelbrot) fades in.
    norm = "format=yuv420p,setsar=1,fps=30,settb=AVTB"
    graph = (f"[0:v]{norm}[a];[1:v]{norm}[b];[a][b]xfade=transition=fade:duration=1:offset=2[ab];"
             f"[ab]fade=t=out:st=4.5:d=0.5,{norm}[abo];[2:v]{norm}[k];[3:v]trim=duration=3,setpts=PTS-STARTPTS,{norm},fade=t=in:st=0:d=0.5[c];"
             "[abo][k][c]concat=n=3:v=1:a=0[v]")
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "smptebars=s=320x180:r=30:d=3", "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=3",
             "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=0.5", "-f", "lavfi", "-i", "mandelbrot=s=320x180:r=30", "-filter_complex", graph,
             "-map", "[v]", "-t", "8", "-pix_fmt", "yuv420p", clip])
    r = study.transitions(clip, 8.0)
    kinds = [(e["type"], e["start"]) for e in r["events"]]
    assert any(k == "dissolve" and 1.6 <= s <= 2.4 for k, s in kinds), kinds
    assert any(k == "dip_to_black" and 4.0 <= s <= 5.2 for k, s in kinds), kinds
    assert not any(k == "dissolve" and s > 4 for k, s in kinds)
