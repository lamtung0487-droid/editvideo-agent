"""Narration backends with a fallback chain, so a plan never dies on a network hiccup.

auto: Edge TTS (network, word boundaries) → Piper (offline neural voice, if a model for the language is installed under
data/models/piper) → the OS speech engine (Windows SAPI) when it has a voice in the script's language → a silent
placeholder with reading-speed timing (the plan, captions and edits proceed; import the real narration later with
import_media(preserve_plan=true)). Every result says which backend spoke and why the earlier ones did not, so the
calling model never mistakes a placeholder for a voice.
"""
import sys
import json
import shutil
import subprocess
import wave
from pathlib import Path
from . import store

BACKENDS = ("auto", "edge", "piper", "sapi", "silent")


def language(config):
    """BCP-47 language-region of the configured voice ("vi-VN-NamMinhNeural" → "vi-VN"); a bare name ("alloy") is itself."""
    parts = str(config.get("voice") or "vi-VN").split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else parts[0]


def align_words(audio_path, text, language="vi", duration=None):
    """Word timings for speech whose engine gives none (Piper, SAPI): local Whisper word timestamps (cached model, no
    download) matched onto the known spoken text token by token; tokens Whisper missed are spread evenly between their
    matched neighbours. Returns [] when Whisper is unavailable or nothing matches. Measured from the audio, but an ASR
    estimate, not forced alignment."""
    import difflib
    import re
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8", download_root=str(store.models_root("models--Systran--faster-whisper-small")), local_files_only=True)
        segs, _ = model.transcribe(str(audio_path), language=language.split("-")[0], word_timestamps=True, beam_size=5, initial_prompt=text[:800])
        heard = [(w.word.strip(), w.start, w.end) for seg in segs for w in (seg.words or []) if w.end > w.start]
    except Exception:
        return []
    norm = lambda w: re.sub(r"[^\w]", "", w.lower())
    tokens = text.split()
    times = [None] * len(tokens)
    for blk in difflib.SequenceMatcher(None, [norm(t) for t in tokens], [norm(h[0]) for h in heard], autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = heard[blk.b + k][1:]
    known = [i for i, x in enumerate(times) if x]
    if len(known) < max(2, len(tokens) // 4):  # too little agreement to trust
        return []
    end = duration or (heard[-1][2] if heard else 0)
    i = 0
    while i < len(tokens):
        if times[i]:
            i += 1
            continue
        j = i
        while j < len(tokens) and not times[j]:
            j += 1
        a = times[i - 1][1] if i else 0.0
        b = times[j][0] if j < len(tokens) else max(a, end)
        step = (b - a) / (j - i)
        for k in range(i, j):
            times[k] = (a + (k - i) * step, a + (k - i + 1) * step)
        i = j
    return [{"start": round(float(a), 3), "end": round(float(b), 3), "text": t} for t, (a, b) in zip(tokens, times)]


PIPER_LENGTH = 1.4


def asr_check(audio_path, text, language="vi"):
    """Listen-back check for synthetic narration: an UNPROMPTED local Whisper pass (the timing pass is given the script
    and hides mistakes) compared word by word with the text. Returns the share of words not heard as written and the
    words to check by ear, each with what was heard instead. An ASR proxy, not a pronunciation verdict."""
    import difflib
    import re
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8", download_root=str(store.models_root("models--Systran--faster-whisper-small")), local_files_only=True)
        segs, _ = model.transcribe(str(audio_path), language=language.split("-")[0], word_timestamps=True, beam_size=5)
        heard = [(w.word.strip(), w.start) for seg in segs for w in (seg.words or [])]
    except Exception as error:
        return {"available": False, "reason": type(error).__name__}
    norm = lambda w: re.sub(r"[^\w]", "", w.lower())
    tokens = text.split()
    a, b = [norm(t) for t in tokens], [norm(h[0]) for h in heard]
    numerals = {"không", "một", "mốt", "hai", "ba", "bốn", "tư", "năm", "lăm", "sáu", "bảy", "tám", "chín", "mười", "mươi", "trăm", "nghìn",
                "ngàn", "triệu", "linh", "lẻ", "rưỡi"}
    odd = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        said_nums = [x for x in a[i1:i2] if x in numerals]
        if tag == "replace" and said_nums and any(any(c.isdigit() for c in x) for x in b[j1:j2]):
            rest = [tokens[i] for i in range(i1, i2) if a[i] not in numerals]  # number words written as digits are fine
            if not rest:
                continue
            odd.append({"said": " ".join(rest), "heard": " ".join(h[0] for h in heard[j1:j2]),
                        "at_s": round(float(heard[j1][1]), 2) if j1 < len(heard) else None})
            continue
        if tag != "equal":
            odd.append({"said": " ".join(tokens[i1:i2]), "heard": " ".join(h[0] for h in heard[j1:j2]),
                        "at_s": round(float(heard[j1][1]), 2) if j1 < len(heard) else None})
    missed = sum(len(o["said"].split()) for o in odd)
    return {"available": True, "words": len(tokens), "not_heard_as_written": round(missed / max(1, len(tokens)), 3), "check_by_ear": odd[:20],
            "note": "Listen at these times; respell a word in spoken_text if the voice really says it wrong."}


UNCLEAR_CHECK, UNCLEAR_PROBLEM = .10, .20  # share of words not heard as written (Edge TTS measured ~8% on the same check)


def narration_finding(pid):
    """Finding dict (level, code, evidence, suggestion) for a synthetic narration that may be hard to understand, from
    the plan's voice-backend.json, or None. Offline voices without a listen-back check are reported as unchecked."""
    from . import store
    try:
        vb = store.folder(pid) / "plan" / "voice-backend.json"
    except (ValueError, TypeError):  # a would-be timeline audited without a stored project
        return None
    if not vb.exists():
        return None
    data = store.read_json(vb)
    backend, asr = data.get("backend"), data.get("asr_check")
    if backend in ("piper", "sapi") and not (asr or {}).get("available"):
        return ("check", "narration_unchecked", {"backend": backend, "reason": (asr or {}).get("reason", "not run")},
                "Offline narration was not checked by ear or by the listen-back pass (Whisper model missing: "
                "scripts/setup_voice.py --whisper). Listen to it before delivery.")
    if not (asr or {}).get("available"):
        return None
    share = asr.get("not_heard_as_written", 0)
    if share < UNCLEAR_CHECK:
        return None
    return ("likely_problem" if share >= UNCLEAR_PROBLEM else "check", "narration_unclear",
            {"backend": backend, "not_heard_as_written": share, "check_by_ear": asr.get("check_by_ear", [])[:8]},
            "A recogniser did not hear these words as written: listen at the listed times. If the voice really says them "
            "wrong, respell them in spoken_text (keep the script for captions), re-plan and compare the new share; or use "
            "another voice/backend for delivery.")


def piper_model(lang):
    root = store.models_root("piper") / "piper"
    if not root.exists():
        return None
    tag = lang.replace("-", "_")
    return next((p for p in sorted(root.glob("*.onnx")) if p.name.startswith(tag)), None)


def piper_available():
    """Piper is installed (as a module or an executable). Checked without importing it: Piper is GPL-3.0 and only ever
    runs as a separate process."""
    import importlib.util
    return importlib.util.find_spec("piper") is not None or shutil.which("piper") is not None


def sapi_voices():
    """[(name, culture)] from the Windows speech engine (empty elsewhere)."""
    if shutil.which("powershell") is None:
        return []
    ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "$s.GetInstalledVoices()|%{ $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return []
    return [tuple(line.strip().split("|", 1)) for line in out.splitlines() if "|" in line]


def capabilities(config=None):
    lang = language(config or {})
    sapi = sapi_voices()
    return {"edge": "network service (word boundaries)", "piper": {"runtime": piper_available(), "model": str(piper_model(lang)) if piper_model(lang) else None},
            "sapi": [n for n, c in sapi if c.lower() == lang.lower()], "sapi_other_languages": sorted({c for _, c in sapi if c.lower() != lang.lower()}),
            "silent_placeholder": True, "language": lang,
            "note": "auto tries edge → piper → sapi (same language only) → silent placeholder with estimated timing."}


def _wav_seconds(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def piper_speak(text, config, target):
    model = piper_model(language(config))
    if not model or not piper_available():
        raise RuntimeError("no Piper runtime/model for " + language(config))
    wav = target.with_suffix(".wav")
    exe = shutil.which("piper")
    cmd = [exe] if exe else [sys.executable, "-m", "piper"]  # the module installed in this environment
    # Narration pace: vi_VN vais1000 measured ~4.5 syllables/s of speech at phoneme length 1.2 (79 syllables in 17.4 s);
    # 1.4 brings it to ~3.9, an explainer's pace. Sentences get the silent placeholder's short pause; voice_rate (%) as for Edge.
    length = PIPER_LENGTH / (1 + (config.get("voice_rate") or 0) / 100)
    subprocess.run([*cmd, "--model", str(model), "--output_file", str(wav), "--length-scale", f"{length:.3f}", "--sentence-silence", "0.35"],
                   input=text.encode("utf-8"), check=True, timeout=600, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return wav


def sapi_speak(text, config, target):
    lang = language(config)
    match = [n for n, c in sapi_voices() if c.lower() == lang.lower()]
    if not match:
        raise RuntimeError(f"no OS voice for {lang}")
    wav = target.with_suffix(".wav")
    src = target.with_suffix(".txt")
    src.write_text(text, encoding="utf-8")
    rate = max(-10, min(10, round((config.get("voice_rate") or 0) / 10)))
    q = lambda v: str(v).replace("'", "''")  # PowerShell single-quoted literal
    ps = (f"Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('{q(match[0])}');"
          f"$s.Rate={rate}; $s.SetOutputToWaveFile('{q(wav)}'); $s.Speak([IO.File]::ReadAllText('{q(src)}',[Text.Encoding]::UTF8)); $s.Dispose()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=600, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        src.unlink(missing_ok=True)  # the script text handed to PowerShell, created above
    return wav


def silent_placeholder(text, target, words_per_second=2.6, pause=.35):
    """A silent track as long as reading the script aloud takes (Vietnamese narration ≈ 2.4-2.8 words/s)."""
    from .audio import sentences
    secs = sum(len(s.split()) / words_per_second + pause for s in sentences(text)) or 1.0
    wav = target.with_suffix(".wav")
    n = int(round(secs * 48000))
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(b"\x00\x00" * n)
    return wav


def speak(text, config, target, cancelled, edge):
    """→ (audio path, timed words or [], backend, attempts). edge: the async Edge TTS coroutine factory."""
    import asyncio
    want = config.get("voice_backend") or "auto"
    order = ["edge", "piper", "sapi", "silent"] if want == "auto" else [want]
    attempts = []
    for b in order:
        try:
            if b == "edge":
                words = asyncio.run(asyncio.wait_for(edge(text, config, target, cancelled), timeout=240))
                return target, words, b, attempts
            if b == "piper":
                return piper_speak(text, config, target), [], b, attempts
            if b == "sapi":
                return sapi_speak(text, config, target), [], b, attempts
            if b == "silent":
                return silent_placeholder(text, target), [], b, attempts
        except Exception as e:  # keep going down the chain; record why
            from .media import Cancelled
            if isinstance(e, Cancelled):
                raise
            attempts.append({"backend": b, "error": (type(e).__name__ + ": " + str(e))[:160]})
    raise ValueError("No narration backend worked: " + json.dumps(attempts, ensure_ascii=False))
