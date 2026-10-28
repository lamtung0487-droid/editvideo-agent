"""Music timing: calibrated beat times, bars/sections/hits, bar-aligned music edits and cut-to-beat reading."""
import importlib.util
import subprocess
from pathlib import Path
import numpy as np
import pytest
from editvideo import music

SR = 44100


def _song():
    spec = importlib.util.spec_from_file_location("synth_song", Path(__file__).with_name("synth_song.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clicks(path, bpm, dur=16.0, start=.5):
    x, t, ts = np.zeros(int(SR * dur)), start, []
    a = np.arange(int(.03 * SR)) / SR
    while t < dur - .5:
        i = int(t * SR)
        x[i:i + len(a)] += np.exp(-a / .004) * np.sin(2 * np.pi * 2000 * a) * .8
        ts.append(t)
        t += 60 / bpm
    x += .05 * np.sin(2 * np.pi * 220 * np.arange(len(x)) / SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-", str(path)], input=x.tobytes(), check=True)
    return np.array(ts)


@pytest.mark.parametrize("bpm", [87, 128])
def test_beat_times_land_on_the_attack(tmp_path, bpm):
    truth = _clicks(tmp_path / "c.wav", bpm)
    r = music.beats(str(tmp_path / "c.wav"))
    b = np.array(r["beats"])
    err = np.array([b[np.argmin(np.abs(b - t))] - t for t in truth])
    assert abs(err.mean()) < .005 and err.std() < .006  # was ~73 ms early before calibration
    assert abs(r["bpm"] - bpm) < 1.5 and r["pulse"] == "clear"


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    d = tmp_path_factory.mktemp("song")
    truth = _song().make(str(d / "song.wav"))
    return str(d / "song.wav"), truth


def test_structure_finds_bars_sections_hits_and_gaps(song):
    path, truth = song
    st = music.structure(path, bpm_range=(90, 180))
    assert abs(st["bpm"] - 120) < 1
    b = np.array(st["beats"])
    err = np.array([b[np.argmin(np.abs(b - t))] - t for t in truth["beats"]])
    assert np.median(np.abs(err)) < .02  # on the beat, not on the off-beat hats
    assert abs(st["downbeats"][0] - .5) < .03  # bar phase from the kick
    found = [(s["label"], s["start"]) for s in st["sections"]]
    # The intro→build, build→drop and breakdown→drop boundaries are found within half a bar.
    for name, t in truth["sections"][1:3] + truth["sections"][4:5]:
        assert any(abs(s - t) < 1.0 for _, s in found), (name, t, found)
    labels = [lab for lab, _ in found]
    assert labels[0] == "intro" and "peak" in labels and labels.count("peak") >= 2
    assert any(abs(h["time"] - truth["hit"]) < .03 and h["rise_db"] > 30 for h in st["hits"])
    gap0, gap1 = truth["gap"]
    assert any(q["start"] <= gap0 + .1 and q["end"] >= gap1 - .1 for q in st["quiet"])  # the dip before the drop


def test_fit_joins_on_bar_lines_and_reaches_target(song):
    path, _ = song
    st = music.structure(path, bpm_range=(90, 180))
    bars = st["bar_starts"]
    plan = music.fit(path, 45, bpm_range=(90, 180))
    assert abs(plan["length_s"] - 45) <= 2.05  # within one bar
    j = plan["join"]
    assert min(abs(j["from_s"] - b) for b in bars) < 1e-3 and min(abs(j["to_s"] - b) for b in bars) < 1e-3
    a, b2 = plan["segments"]
    xf = a["fade_out"]
    assert abs((a["source_end"] - a["source_start"]) - (b2["at_s"] + xf)) < 1e-3  # crossfade overlaps by its length
    assert abs(b2["at_s"] + xf / 2 - (j["from_s"])) < 1e-3  # the downbeat after the join lands on the old bar line
    fade = music.fit(path, 40, ending="fade", bpm_range=(90, 180))["segments"][0]
    assert min(abs(fade["source_end"] - b) for b in bars) < 1e-3 and fade["fade_out"] > 1.5
    with pytest.raises(ValueError):
        music.fit(path, 2, bpm_range=(90, 180))


def test_cut_alignment_reads_lead_and_on_beat_share(song):
    path, truth = song
    beats = [t for t in truth["beats"] if 33 < t < 72]
    cuts = [t - 3 / 30 for t in beats[::4]]  # every bar, 3 frames early
    r = music.cut_alignment(path, cuts, 32, 72, bpm_range=(90, 180))
    assert r["reading"].startswith("cut to the beat") and abs(r["lead_frames"] + 3) <= 1 and r["cuts_on_beat"] >= .9
    rng = np.random.default_rng(4)
    loose = music.cut_alignment(path, sorted(rng.uniform(33, 71, 12)), 32, 72, bpm_range=(90, 180))
    assert loose["cuts_on_beat"] is None or loose["cuts_on_beat"] < .9


def test_snap_modes_priority_hits_against_and_protect(song, monkeypatch):
    from editvideo import agent
    path, truth = song
    st = music.structure(path, bpm_range=(90, 180))
    fr = lambda t: round(t * 30)
    # Cuts a few frames off: one near a downbeat (also near beat 2), one near the drop hit, one inside dialogue.
    d = st["downbeats"][10]
    cuts = [fr(d) + 4, fr(truth["hit"]) + 3, fr(st["downbeats"][30]) + 2]
    edges = [0, *cuts, 2400]
    shots = [{"id": f"s{i}", "start_frame": a, "end_frame": b} for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 7, "timeline": {"shots": shots}})
    pr = music.snap_cuts("p", 7, path, use="priority", lead_frames=2, dry_run=True, protect=[[cuts[2] - 10, cuts[2] + 10]], bpm_range=(90, 180))
    moves = {m["after_shot"]: m for m in pr["planned"]}
    assert moves["s0"]["to"] == fr(d) - 2 and moves["s0"]["weight"] == 1.0  # the downbeat, 2 frames early
    assert "s2" not in moves and any(s["reason"] == "protected range" for s in pr["skipped"])
    hits = music.snap_cuts("p", 7, path, use="hits", lead_frames=1, dry_run=True, bpm_range=(90, 180))
    assert any(m["after_shot"] == "s1" and abs(m["to"] - (fr(truth["hit"]) - 1)) <= 1 for m in hits["planned"])
    ag = music.snap_cuts("p", 7, path, use="against", lead_frames=0, dry_run=True, bpm_range=(90, 180))
    beats = np.array(st["beats"]) * 30
    for m in ag["planned"]:
        assert np.min(np.abs(beats - m["to"])) >= 6  # off-beat targets sit between beats (beat = 15 frames)
    assert isinstance(pr["section_entries_without_cut"], list)
    with pytest.raises(ValueError):
        music.snap_cuts("p", 7, beat_times=[1, 2], use="hits")


def test_snap_reads_the_whole_track_and_returns_the_grid_it_cut_to(song, monkeypatch):
    """Analysed from music_start, the reel's bed had come out at 133 BPM where music_structure (the whole track) said 200:
    the cuts went to one grid while the picture drew the other. The snap now reads the grid music_structure returns, and
    says where each cut went in the music."""
    from editvideo import agent
    path, _ = song
    whole = music.structure(path, bpm_range=(90, 180))
    start, fr = 20.0, lambda t: round((t - 20.0) * 30)
    cuts = [fr(b) + 3 for b in whole["beats"][40:60:4]]
    edges = [0, *cuts, 1500]
    shots = [{"id": f"s{i}", "start_frame": a, "end_frame": b} for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    monkeypatch.setattr(agent, "read", lambda pid: {"revision": 7, "timeline": {"shots": shots}})
    r = music.snap_cuts("p", 7, path, use="beats", lead_frames=0, music_start=start, dry_run=True, bpm_range=(90, 180))
    assert "whole track" in r["beat_info"]["analysis"] and r["beat_info"]["bpm"] == whole["bpm"]
    beats = set(round(b, 3) for b in whole["beats"])
    assert r["targets"] and all(t["music_s"] in beats and abs(t["frame"] - fr(t["music_s"])) <= 1 for t in r["targets"])
    assert len(r["planned"]) == len(cuts) and all(m["music_s"] in beats and abs(m["to"] - fr(m["music_s"])) <= 1 for m in r["planned"])
