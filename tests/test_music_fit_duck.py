"""Music to picture: a fit through several invisible joins landing on the frame, Beat This!'s own bars when it is
there, and ducking by measured loudness (the music a set number of LU under each spoken phrase, back in the pauses)."""
import subprocess
import numpy as np
import pytest
from editvideo import music
from editvideo.media import FFMPEG


def test_join_path_reaches_the_length_through_joins_a_phrase_apart():
    bars = [2.0 * k for k in range(41)]                    # 40 bars of 2 s: 80 s of music
    cost = lambda i, j: .2 if (i % 4 == 0 and j % 4 == 0) else 1.2
    c, runs = music._join_path(bars, cost, 50.0, 2.0, max_joins=3)
    played = sum(bars[e] - bars[s] for s, e in runs)
    assert runs[0][0] == 0 and runs[-1][1] == 40 and abs(played - 50) <= 2
    assert len(runs) - 1 <= 3 and all(e - s >= 4 for s, e in runs[1:-1])  # never two joins inside a phrase
    assert all(e % 4 == 0 for s, e in runs[:-1]) and all(s % 4 == 0 for s, e in runs[1:])  # cheap joins: on phrase lines


def test_exact_plays_a_plan_onto_the_frame_within_three_percent():
    plan = {"segments": [{"source_start": 0, "source_end": 30.0, "at_s": 0.0, "fade_in": 0, "fade_out": .2},
                         {"source_start": 50.0, "source_end": 80.6, "at_s": 29.8, "fade_in": .2, "fade_out": .15}], "length_s": 60.6, "note": ""}
    out = music._exact(dict(plan, segments=[dict(s) for s in plan["segments"]]), 60.0)
    assert out["stretch"] == pytest.approx(1.01, abs=1e-4) and out["segments"][1]["at_s"] == pytest.approx(29.8 / 1.01, abs=1e-3)
    far = music._exact(dict(plan, segments=[dict(s) for s in plan["segments"]], length_s=66.0), 60.0)
    assert "stretch" not in far and "Not stretched" in far["note"]


def test_structure_takes_the_networks_own_bars(monkeypatch, tmp_path):
    sr = 22050
    x = np.zeros(sr * 20, np.float32)
    for k in range(40):                                    # a click every 0.5 s, the first of every three louder (3/4)
        i = int(k * .5 * sr)
        x[i:i + 200] = .9 if k % 3 == 0 else .3
    f = tmp_path / "waltz.wav"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", str(f)], input=x.tobytes(), check=True)
    beats = np.arange(40) * .5
    monkeypatch.setattr(music, "_neural", lambda x_, start: (beats + start, beats[::3] + start))
    monkeypatch.setattr(music, "_beat_this", lambda: object())
    st = music.structure(str(f))
    assert st["tracker"] == "beat_this" and st["downbeats"][:3] == [0.0, 1.5, 3.0]
    assert st["beat_in_bar"][:7] == [0, 1, 2, 0, 1, 2, 0]


def _tone(path, seconds, spans=None, freq=220, level=.3):
    sr = 48000
    t = np.arange(int(seconds * sr)) / sr
    x = (level * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    if spans is not None:  # a "voice": noise bursts where it speaks, silence elsewhere
        rng = np.random.default_rng(1)
        x = np.zeros_like(x)
        for a, b in spans:
            x[int(a * sr):int(b * sr)] = (rng.standard_normal(int(b * sr) - int(a * sr)) * .1).astype(np.float32)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", str(path)], input=x.tobytes(), check=True)


def test_duck_puts_the_music_under_each_phrase_and_back_in_the_pauses(tmp_path):
    m, v = tmp_path / "m.wav", tmp_path / "v.wav"
    _tone(m, 40)
    _tone(v, 40, spans=[(2, 6), (6.8, 9), (15, 19), (26, 30)])  # a short pause at 6-6.8 s stays down
    clips = [{"start_frame": 0, "end_frame": 600, "source_start": 0.0, "volume": .8, "fade_in": .5, "fade_out": .2},
             {"start_frame": 600, "end_frame": 1200, "source_start": 20.0, "volume": .8, "fade_in": .2, "fade_out": .5}]  # a join at 20 s
    r = music.duck(clips, str(m), str(v), 0.0, 13.0, downbeats=[k * 2.0 for k in range(20)])
    assert len(r["phrases"]) == 3 and r["min_gap_lu"] >= 12.5
    assert all(p_["gain_db"] < 0 for p_ in r["phrases"])
    full = [c for c in r["clips"] if c["volume"] == pytest.approx(.8)]
    down = [c for c in r["clips"] if c["volume"] < .79]
    assert full and down and all(not c["duck_under_voice"] for c in r["clips"])
    # the pause between 9 s and 15 s is at full level, the phrase at 15-19 s down
    at = lambda s: [c for c in r["clips"] if c["start_frame"] <= s * 30 < c["end_frame"]]
    assert any(c["volume"] == pytest.approx(.8) for c in at(12)) and all(c["volume"] < .79 for c in at(17))
    # each piece starts where its source does: crossfaded copies stay sample-aligned
    for c in r["clips"]:
        orig = next(o for o in clips if o["start_frame"] <= c["start_frame"] < o["end_frame"])
        assert c["source_start"] == pytest.approx(orig["source_start"] + (c["start_frame"] - orig["start_frame"]) / 30, abs=1e-3)


def test_join_path_ends_on_a_phrase_and_counts_the_pickup():
    bars = [1.0 + 2.0 * k for k in range(41)]              # a 1 s pickup before the first bar
    cost = lambda i, j: .1 if j >= 36 else 1.5              # a cheap jump straight to the last bars would leave a sliver
    c, runs = music._join_path(bars, cost, 51.0, 2.0, max_joins=3, pickup=1.0)
    assert all(e - s >= 4 for s, e in runs[1:])
    assert abs(sum(bars[e] - bars[s] for s, e in runs) + 1.0 - 51.0) <= 2


def test_bar_positions_count_a_pickup_back_from_the_first_downbeat():
    beats = [k * .5 for k in range(11)]
    down = [1.0, 2.5, 4.0]                                   # 3/4, two pickup beats
    assert music._bar_positions(beats, down)[:6] == [1, 2, 0, 1, 2, 0]


def test_beat_this_is_never_fetched_inside_an_analysis(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITVIDEO_BEAT_CHECKPOINT", str(tmp_path / "none.ckpt"))
    music._BT.clear()
    assert not music._beat_ready() and music._beat_this() is None   # no checkpoint on disk: no download, the DP tracker runs
