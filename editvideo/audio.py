import asyncio
import math
import re
import wave
from pathlib import Path
from . import store
from .media import FFMPEG, Cancelled, command, normalize_audio, safe_asset_path


def sentences(text):
    # Preserve script, including punctuation; line breaks are editorial beats.
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", text.strip()) if s.strip()]


def audio_samples(path):
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 48000:
            raise ValueError("Audio phải được chuẩn hóa 48 kHz")
        return w.getnframes()


def parse_srt(text):
    from .models import Cue
    pattern = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})")
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "").strip()):
        match = pattern.search(block)
        if not match:
            continue
        nums = [int(n) for n in match.groups()]
        start = nums[0]*3600 + nums[1]*60 + nums[2] + nums[3]/1000
        end = nums[4]*3600 + nums[5]*60 + nums[6] + nums[7]/1000
        content = re.sub(r"<[^>]+>", "", block[match.end():].strip())
        if content:
            cues.append(Cue(start=start, end=end, text=content).model_dump())
    if not cues:
        raise ValueError("File SRT không có phụ đề hợp lệ")
    previous = 0
    for c in cues:
        if c["start"] < previous - .001:
            raise ValueError("Phụ đề SRT chồng thời gian hoặc sai thứ tự")
        previous = c["end"]
    return cues


def estimated_cues(text, duration):
    chunks = []
    for s in sentences(text):
        words = s.split()
        for i in range(0, len(words), 9):
            chunks.append(" ".join(words[i:i+9]))
    count = sum(len(c.split()) for c in chunks)
    if not count:
        raise ValueError("Kịch bản đang trống")
    cursor = 0
    out = []
    for c in chunks:
        end = cursor + duration * len(c.split()) / count
        out.append({"start": cursor, "end": end, "text": c})
        cursor = end
    out[-1]["end"] = duration
    return out


async def edge_voice(text, config, target, cancelled):
    import edge_tts
    communicate = edge_tts.Communicate(text, config["voice"], rate=f'{config["voice_rate"]:+d}%', boundary="WordBoundary")
    words = []
    with target.open("wb") as f:
        async for chunk in communicate.stream():
            if cancelled():
                raise Cancelled()
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"start": chunk["offset"] / 10000000,
                              "end": (chunk["offset"] + chunk["duration"]) / 10000000,
                              "text": chunk["text"]})
    if not target.stat().st_size:
        raise ValueError("Dịch vụ giọng không trả audio. Hãy tải giọng đọc có sẵn.")
    return words


PROTECTED_PAIRS = {("ánh","sáng"),("quang","hợp"),("năng","lượng"),("chất","hữu"),("hữu","cơ"),("chăm","sóc"),("môi","trường"),("cây","xanh"),("khung","hình"),("chủ","thể"),("mặt","nạ"),("thuyết","minh"),("chuyển","động"),("thời","gian"),("nhấp","nháy"),("minh","họa"),("bố","cục"),("dễ","đọc"),("ổn","định"),("đúng","nhịp"),("màu","sắc"),("nội","dung"),("kết","quả"),("hiện","tượng"),("câu","chuyện"),("liền","mạch"),("dấu","hiệu"),("thói","quen"),("màn","hình"),("điều","tiết"),("hẹn","giờ")}
# Function words that usually open a new clause; a caption page may start here.
BREAK_BEFORE = set("là và nhưng vì nên thì khi để hoặc mà nếu rồi trong của với cho ở hãy".split())


def _clean(text):
    return re.sub(r"[^\w-]", "", text.lower())


def group_words(words, max_words=9):
    """Group timed words into caption pages.

    Sentence ends and pauses >0.45s always break. Longer spans are split
    recursively at the cheapest boundary: clause punctuation, measured pauses and
    clause-opening words are preferred; known compounds are kept; tiny orphans and
    unbalanced pages are avoided. A page may exceed max_words by up to two words
    when every available break would cut a phrase."""
    def count(items):
        return len(" ".join(x["text"] for x in items).split())
    def size(items):
        return sum(len(x["text"].split()) for x in items)
    orphan = min(2, max_words-1)
    def cost(seg, k):
        left, right = seg[k-1], seg[k]
        a, b = size(seg[:k]), size(seg[k:])
        c = abs(a-b)/max(1, a+b)*2
        c += 0 if re.search(r"[,;:]$", left["text"]) else 1.5
        c -= 1 if _clean(right["text"]) in BREAK_BEFORE else 0
        gap = right["start"]-left["end"]
        c -= gap*3 if gap > .15 else 0
        c += 6 if (_clean(left["text"]), _clean(right["text"])) in PROTECTED_PAIRS else 0
        c += 4 if a < orphan or b < orphan else 0
        return c
    def split(seg):
        if count(seg) <= max_words or len(seg) < 2:
            return [seg]
        k = min(range(1, len(seg)), key=lambda k: (cost(seg, k), abs(size(seg[:k])-size(seg[k:]))))
        if count(seg) <= max_words+2 and cost(seg, k) >= 1.4:
            return [seg]
        return split(seg[:k]) + split(seg[k:])
    spans, span = [], []
    for w in words:
        if span and w["start"] - span[-1]["end"] > .45:
            spans.append(span)
            span = []
        span.append(w)
        if re.search(r"[.!?。]$", w["text"]):
            spans.append(span)
            span = []
    if span:
        spans.append(span)
    return [{"start": seg[0]["start"], "end": seg[-1]["end"], "text": " ".join(x["text"] for x in seg)}
            for span in spans for seg in split(span)]


def _align_display_words(words, original):
    """Map display tokens onto measured spoken words when they differ only locally.

    Typical case: script shows "20-20-20" or "6 mét" while TTS read "hai mươi..."
    and "sáu mét". Equal tokens keep their own boundaries; a differing run of
    display tokens shares the measured span of the corresponding spoken run.
    Nothing is interpolated from text length. Returns None when the texts do not
    share enough exact words to make the mapping trustworthy."""
    from difflib import SequenceMatcher
    normalize = lambda t: re.sub(r"[^\w]", "", t.lower())
    units = [w for w in words if w["text"].split()]
    if not original or not units:
        return None
    display_keys = [normalize(t) for t in original]
    spoken_keys = [normalize(w["text"]) for w in units]
    ops = SequenceMatcher(None, display_keys, spoken_keys, autojunk=False).get_opcodes()
    matched = sum(i2-i1 for tag, i1, i2, _, _ in ops if tag == "equal")
    if matched < .6*len(original):
        return None
    result, pending_text = [], []
    for tag, i1, i2, j1, j2 in ops:
        shown, heard = original[i1:i2], units[j1:j2]
        if tag in ("replace", "delete") and not any(re.search(r"\d", t) for t in shown) and len(shown) > 3:
            return None
        if tag in ("replace", "insert") and len(heard) > 12:
            return None
        if tag == "equal":
            for token, w in zip(shown, heard):
                result.append({**w, "text": " ".join(pending_text+[token])})
                pending_text = []
        elif tag == "delete":
            # Display-only symbols (e.g. "—") ride on a neighbouring spoken word.
            if result:
                result[-1]["text"] += " " + " ".join(shown)
            else:
                pending_text += shown
        elif tag == "insert":
            if result:
                result[-1]["end"] = max(result[-1]["end"], heard[-1]["end"])
            elif j2 < len(units):
                units[j2] = {**units[j2], "start": heard[0]["start"]}
        else:
            groups = len(shown) if len(heard) >= len(shown) else len(heard)
            for g in range(groups):
                a, b = g*len(heard)//groups, (g+1)*len(heard)//groups
                c, d = g*len(shown)//groups, (g+1)*len(shown)//groups
                result.append({"start": heard[a]["start"], "end": heard[b-1]["end"],
                               "text": " ".join(pending_text+shown[c:d])})
                pending_text = []
    if pending_text or any(w["end"] <= w["start"] for w in result):
        return None
    return result


def restore_display_text(words, text):
    """Restore script punctuation/numerals onto measured word timings without inventing timings."""
    original = text.split()
    spoken = [token for w in words for token in w["text"].split()]
    normalize = lambda t: re.sub(r"[^\w]", "", t.lower())
    if len(original) != len(spoken) or [normalize(t) for t in original] != [normalize(t) for t in spoken]:
        return _align_display_words(words, original)
    cursor, result = 0, []
    for w in words:
        length = len(w["text"].split())
        result.append({**w, "text": " ".join(original[cursor:cursor+length])})
        cursor += length
    return result


def prepare_audio(pid, config, work, cancelled, progress):
    voice = work / "voice.wav"
    source_srt = store.folder(pid) / "captions-input.srt"
    words = []
    if config.get("narration_id"):
        progress(8, "Chuẩn hóa giọng đọc đã tải lên")
        normalize_audio(safe_asset_path(pid, config["narration_id"]), voice, cancelled, work / "render.log")
        duration = audio_samples(voice) / 48000
        if source_srt.exists():
            cues = parse_srt(source_srt.read_text(encoding="utf-8-sig"))
            method = "supplied_srt"
        else:
            cues = estimated_cues(config["script"], duration)
            method = "estimated_from_script"
    else:
        progress(8, "Tạo giọng đọc tiếng Việt")
        mp3 = work / "narration.mp3"
        text = config.get("spoken_text") or config["script"]
        from .voices import speak
        spoken, words, backend, attempts = speak(text, config, mp3, cancelled, edge_voice)  # edge → piper → sapi → silent
        normalize_audio(spoken, voice, cancelled, work / "render.log")
        tail = float(config.get("tail_seconds", .8) or 0)
        if tail > 0:  # room after the last word (end cards fade on silence, not mid-syllable)
            padded = work / "voice-tail.wav"
            from .media import command, FFMPEG
            command([FFMPEG, "-y", "-v", "error", "-i", voice, "-af", f"apad=pad_dur={tail}", "-c:a", "pcm_s16le", padded], cancelled=cancelled,
                    log=work / "render.log")
            padded.replace(voice)
        duration = audio_samples(voice) / 48000
        store.write_json(work / "voice-backend.json", {"backend": backend, "attempts": attempts})
        if backend == "silent":
            cues = estimated_cues(config["script"], duration)
            store.write_json(work / "words.json", {"method": "silent_placeholder", "backend": backend, "attempts": attempts, "words": [], "cues": cues})
            return voice, cues, "silent_placeholder"
        if not words and backend in ("piper", "sapi"):
            # Offline engines give no word boundaries: time the known words from the audio itself (local Whisper).
            from .voices import align_words, language
            progress(12, "Căn thời gian từng từ cho giọng offline")
            words = align_words(voice, text, language(config), duration)
            from .voices import asr_check
            store.write_json(work / "voice-backend.json", {"backend": backend, "attempts": attempts,
                                                           "asr_check": asr_check(voice, text, language(config)),
                                                           **({} if words else {"timing": "estimated: no Whisper model for word timing "
                                                                                          "(scripts/setup_voice.py --whisper)"})})
        if source_srt.exists():
            cues = parse_srt(source_srt.read_text(encoding="utf-8-sig"))
            method = "supplied_srt"
        elif words:
            # Display text may differ from pronunciation text (numerals, acronyms).
            # Map display tokens onto measured TTS boundaries; estimate only if that fails.
            restored = restore_display_text(words, config["script"])
            if restored is not None:
                mapped = config.get("spoken_text") and config["spoken_text"].split() != config["script"].split()
                words = restored
                cues = group_words(words, max_words=7 if config.get("profile") == "vertical" else 9)
                method = ("asr_aligned_" + backend) if backend in ("piper", "sapi") else ("tts_word_boundaries_mapped" if mapped else "tts_word_boundaries")
            else:
                cues = estimated_cues(config["script"], duration)
                method = "estimated_display_mapping"
        else:
            cues = estimated_cues(config["script"], duration)
            method = "estimated_from_script"
    if cues[-1]["end"] > duration + .1:
        raise ValueError("Phụ đề dài hơn giọng đọc. Hãy sửa SRT trước khi dựng.")
    for c in cues:
        c["end"] = min(c["end"], duration)
    store.write_json(work / "words.json", {"method": method, "words": words, "cues": cues})
    return voice, cues, method


def timestamp(value):
    ms = round(value * 1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def write_srt(path, cues):
    path.write_text("\n\n".join(f'{i+1}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}' for i, c in enumerate(cues)) + "\n", encoding="utf-8")
