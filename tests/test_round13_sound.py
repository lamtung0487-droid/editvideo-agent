"""Round 13, tension sound design (docs/PRO_WORKFLOWS.md §29): the new procedural kinds do what their names promise,
clip treatments really filter, and the audit flags sounds that would dampen a startle (prepulse and gap inhibition)."""
import sys, wave
from pathlib import Path
import numpy as np
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editvideo import sound, store
from editvideo.media import FFMPEG, command


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    return tmp_path


def _read(path):
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32767


def _peak_hz(x, lo, hi, at, win=.25):
    seg = x[int(at * 48000):int((at + win) * 48000)] * np.hanning(int(win * 48000))
    spec = np.abs(np.fft.rfft(seg, 8 * len(seg)))
    f = np.fft.rfftfreq(8 * len(seg), 1 / 48000)
    band = (f >= lo) & (f <= hi)
    return float(f[band][np.argmax(spec[band])])


def test_heartbeat_and_clock_report_beats_and_accelerate(data):
    steady = sound.design("heartbeat", 10, bpm=60)
    assert len(steady["beat_times"]) == 10 and steady["end_bpm"] == 60
    fast = sound.design("heartbeat", 10, bpm=60, end_bpm=120)
    gaps = np.diff(fast["beat_times"])
    assert gaps[0] > gaps[-1] * 1.5 and len(fast["beat_times"]) > 10
    clock = sound.design("clock", 6, bpm=120)
    assert len(clock["beat_times"]) == 12
    x = _read(clock["path"])
    # each tick is a sharp onset: energy right after a beat time dwarfs the energy just before the next one
    i = int(clock["beat_times"][3] * 48000)
    assert np.abs(x[i:i + 480]).max() > 10 * np.abs(x[i + 18000:i + 23000]).max()
    with pytest.raises(ValueError):
        sound.design("heartbeat", 5, bpm=60, end_bpm=200)


def test_shepard_partials_glide_up_and_it_stops_dead(data):
    r = sound.design("shepard", 6, bpm=120, gain_db=-12)
    assert r["octave_s"] == 8.0
    x = _read(r["path"])
    # the partial that starts at 576 Hz climbs 1/8 octave per second at 120 bpm
    f1, f3 = _peak_hz(x, 540, 1000, 1.0), _peak_hz(x, 540, 1000, 3.0)
    assert f3 / f1 == pytest.approx(2 ** .25, rel=.04)
    tail = np.abs(x[-int(.02 * 48000):]).max()
    assert tail > .3 * np.abs(x).max()  # no fade-out: the next sound lands on silence


def test_siren_winds_up_and_tinnitus_rings_high(data):
    s = sound.design("siren", 8, bpm=120)  # one 8 s cycle
    x = _read(s["path"])
    assert _peak_hz(x, 100, 700, .05) < _peak_hz(x, 100, 700, 3.4) * .6
    t = sound.design("tinnitus", 3, seed=3)
    f = _peak_hz(_read(t["path"]), 1000, 10000, .5)
    assert 3300 < f < 4700 and t["onset_s"] < .1


def _noise(path):
    rng = np.random.default_rng(1)
    x = rng.normal(0, .2, 48000 * 2)
    with wave.open(str(path), "wb") as w:
        w.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def _band_db(x, lo, hi):
    spec = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / 48000)
    return 10 * np.log10(spec[(f >= lo) & (f < hi)].mean() + 1e-20)


@pytest.mark.parametrize("name,lo,hi,drop", [("muffled", 3000, 8000, 40), ("radio", 30, 120, 20), ("telephone", 5000, 10000, 25)])
def test_clip_treatments_filter(tmp_path, name, lo, hi, drop):
    from editvideo.renderer import clip_chain
    src, out = tmp_path / "noise.wav", tmp_path / f"{name}.wav"
    _noise(src)
    command([FFMPEG, "-y", "-v", "error", "-i", src, "-af", clip_chain({"treatment": name}), "-ac", "1", out])
    a, b = _read(src), _read(out)
    assert (_band_db(a, lo, hi) - _band_db(a, 400, 1000)) - (_band_db(b, lo, hi) - _band_db(b, 400, 1000)) > drop


def test_reverse_plays_backwards(tmp_path):
    from editvideo.renderer import clip_chain
    src, out = tmp_path / "ramp.wav", tmp_path / "rev.wav"
    t = np.arange(48000) / 48000
    with wave.open(str(src), "wb") as w:
        w.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        w.writeframes((np.sin(2 * np.pi * 440 * t) * .5 * np.exp(-4 * t) * 32767).astype("<i2").tobytes())
    command([FFMPEG, "-y", "-v", "error", "-i", src, "-af", clip_chain({"reverse": True}), "-ac", "1", out])
    y = _read(out)
    assert np.abs(y[-4800:]).max() > 5 * np.abs(y[:4800]).max()  # a decay became a swell


def test_audio_clip_accepts_treatment_and_rejects_unknown():
    from editvideo.models import AudioClip
    c = AudioClip(id="radio-1", asset_id="a", start_frame=0, end_frame=30, treatment="radio", reverse=True)
    assert c.treatment == "radio" and c.reverse
    with pytest.raises(Exception):
        AudioClip(id="x", asset_id="a", start_frame=0, end_frame=30, treatment="underwater")


def test_audit_flags_the_startle_window(monkeypatch):
    from editvideo import audiofx, agent
    clip = lambda i, a, b, **k: {"id": i, "asset_id": "s", "start_frame": a, "end_frame": b, **k}
    timeline = {"total_frames": 900, "shots": [{"id": "s1", "start_frame": 0, "end_frame": 900}], "audio_clips": [
        clip("impact-1975", 300, 330), clip("tick-early", 292, 296), clip("suck-out-a", 270, 295),
        clip("braam-dawn", 600, 690), clip("suck-out-b", 573, 600), clip("music-a", 590, 900, role="music")]}
    monkeypatch.setattr(agent, "read", lambda pid: {"timeline": timeline})
    codes = {(f["code"], f["where"][0]) for f in audiofx.audit("p")["findings"]}
    assert ("startle_prepulse", "impact-1975") in codes and ("startle_gap", "impact-1975") in codes
    assert not any(w == "braam-dawn" for _, w in codes)  # pull-in ends on the hit frame, music does not count


def test_accent_sync_can_follow_one_cue_of_several(monkeypatch):
    """A film scored with several cues: accents follow the named clip (its start and source offset), not the longest."""
    from editvideo import accents
    clips = [{"id": "music-a", "asset_id": "a", "role": "music", "start_frame": 90, "end_frame": 1400, "source_start": 0},
             {"id": "music-song", "asset_id": "s", "role": "music", "start_frame": 4000, "end_frame": 6000, "source_start": 33.5}]
    monkeypatch.setattr(accents.store, "find_asset", lambda pid, aid: {"path": f"{aid}.mp3"})
    t = {"total_frames": 7000, "audio_clips": clips}
    path, fr, span = accents._music(t, "p", None)
    assert path == "s.mp3" and span == (4000, 6000)                       # the longest by default
    path, fr, span = accents._music(t, "p", None, "music-a")
    assert path == "a.mp3" and span == (90, 1400) and fr(9.665) == 90 + 290
    with pytest.raises(ValueError, match="music-x"):
        accents._music(t, "p", None, "music-x")


def _lufs(path):
    out = command([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"], timeout=60)
    import re
    return float(re.findall(r"I:\s*(-?[\d.]+) LUFS", out)[-1])


@pytest.mark.parametrize("name", ["radio", "muffled", "distant", "telephone"])
def test_treatments_stay_near_the_role_level(tmp_path, name):
    """Normalisation is measured on the untreated source, so a treatment must not move the level far from it."""
    from editvideo.renderer import clip_chain
    src, out = tmp_path / "noise.wav", tmp_path / f"{name}.wav"
    command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.2:duration=4:seed=3", "-ar", "48000", src])
    command([FFMPEG, "-y", "-v", "error", "-i", src, "-af", clip_chain({"treatment": name}), out])
    assert abs(_lufs(out) - _lufs(src)) < 7.0
    assert "asoftclip" not in clip_chain({"treatment": name})  # FFmpeg < 4.3 lacks it; the whole mix would fail


def test_end_bpm_only_where_it_means_something(data):
    with pytest.raises(ValueError, match="end_bpm"):
        sound.design("beat", 4, bpm=100, end_bpm=160)
    r = sound.design("shepard", 3, bpm=120, end_bpm=150)
    assert r["peak_s"] == pytest.approx(r["duration"], abs=.001)  # anchored on its dead stop
    t = sound._tempo_times(10, 60, 120)
    assert len(t) == 15 and t[1] == pytest.approx(.9545, abs=1e-3)  # exact: integral of the tempo ramp


def test_end_anchored_accents_finish_on_the_event_frame(monkeypatch, data):
    """A riser / reverse cymbal / suck-out placed by sfx_sync ends on the event frame, never one frame early."""
    from editvideo import audiofx, agent
    monkeypatch.setattr(agent, "import_media", lambda *a, **k: {"revision": 1, "asset": {"id": "x"}})
    t = {"total_frames": 900, "shots": [{"id": "s", "start_frame": 0, "end_frame": 900}], "audio_clips": []}
    for seconds in (.9, 1.05, 1.25, 1.5, 2.0):
        for frame in (40, 377, 611):
            q = audiofx.SfxSync(transitions=False, entrances="none", hits=[{"frame": frame, "kind": "riser", "seconds": seconds}])
            r = audiofx._prepare("p", 1, t, q, [{"frame": frame, "kind": "riser", "seconds": seconds}], [])
            clip = next(o["audio"] for o in r["ops"] if o["op"] == "upsert_audio")
            assert clip["end_frame"] == frame, (seconds, frame, clip)
