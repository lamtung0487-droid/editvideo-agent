"""Text and scripts (.txt, .md, timed .srt/.vtt): structure, sentence rhythm, hook, address, numbers, calls to action.

Vietnamese and English are both read (words are Unicode letter runs; Vietnamese is told apart by its diacritics). These
are surface measurements of how a text is built, not of what it means: the caller reads the evidence and judges.
"""
import html
import re
import unicodedata
from pathlib import Path
from . import feature, register

WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)?")
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n{2,}")
VI_MARKS = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)
SECOND_PERSON = {"en": re.compile(r"\b(?:you|your|you're|yours|yourself)\b", re.I),
                 "vi": re.compile(r"(?<![^\W_])(?:bạn|các bạn|anh chị)(?![^\W_])", re.I)}
# Calls to action, by language. A verb counts only where it is an ask: opening a sentence or clause, after "please" /
# "hãy", or followed by "now/today/free/ngay…" ("they start the film" is not an ask; "Start now." is).
CTA = {"en": re.compile(r"\b(?:buy|order|sign up|subscribe|download|try|get started|learn more|book|call|join|click|shop|start|"
                        r"register|follow|share|comment|claim|grab|add to (?:cart|bag|basket)|contact us|get (?:\d+\s?% off|a quote|a demo)|"
                        r"request a demo|start (?:your )?free trial|see (?:plans|pricing))\b", re.I),
       "vi": re.compile(r"(?<![^\W_])(?:mua(?! sắm)|đặt hàng|đặt ngay|đặt lịch|đăng ký|tải|thử(?! thách)|bắt đầu|xem thêm|liên hệ|gọi|"
                        r"tham gia|nhấn|bấm|theo dõi|chia sẻ|bình luận|nhận ngay|nhận ưu đãi|khám phá|inbox|nhắn tin)(?![^\W_])", re.I)}
ASK_BEFORE = {"en": re.compile(r"(?:^|[.!?\n:;•*–—-]\s*|\b(?:please|now|just)\s+)$", re.I),
              "vi": re.compile(r"(?:^|[.!?\n:;•*–—-]\s*|(?<![^\W_])(?:hãy|vui lòng|nhanh tay|ngay)\s+)$", re.I)}
ASK_AFTER = {"en": re.compile(r"^\s+(?:now|today|free|here|up|for free|yours|it now)\b", re.I),
             "vi": re.compile(r"^\s+(?:ngay|hôm nay|miễn phí|tại đây|ở đây|liền)(?![^\W_])", re.I)}
TIME = re.compile(r"(\d{1,2}:)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}:)?(\d{1,2}):(\d{2})[.,](\d{3})")


def _secs(h, m, s, ms):
    return int((h or "0:").rstrip(":")) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def decode(data):
    """Text from bytes: a BOM decides UTF-16/UTF-8, else UTF-8; then NFC, so decomposed Vietnamese counts the same."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace")
    elif data[:200].count(b"\x00") > 20:  # UTF-16 without a BOM
        text = data.decode("utf-16-le" if data[1:2] == b"\x00" else "utf-16-be", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    # One newline convention, so character spans mean the same on Windows (CRLF) and elsewhere.
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def asks(text, lang):
    """Calls to action that read as asks (see CTA)."""
    n = 0
    for m in CTA[lang].finditer(text):
        if ASK_BEFORE[lang].search(text[max(0, m.start() - 40):m.start()]) or ASK_AFTER[lang].search(text[m.end():m.end() + 20]):
            n += 1
    return n


def read(path):
    """(plain text, timed cues or None). Timed cues are (start, end, text) from SRT/VTT."""
    raw = decode(Path(path).read_bytes())
    if Path(path).suffix.lower() not in (".srt", ".vtt"):
        return raw, None
    cues = []
    for block in re.split(r"\n\s*\n", raw.replace("\r", "")):
        m = TIME.search(block)
        if not m:
            continue
        a, b = _secs(*m.groups()[:4]), _secs(*m.groups()[4:])
        body = " ".join(html.unescape(re.sub(r"<[^>]+>", "", ln)).strip() for ln in block[m.end():].splitlines() if ln.strip())
        if body and b > a and (not cues or body != cues[-1][2]):
            cues.append((a, b, body))
    return "\n".join(c[2] for c in cues), cues


def language(text):
    letters = sum(ch.isalpha() for ch in text)
    return "vi" if letters and len(VI_MARKS.findall(text)) / letters > .02 else "en"


def _sentences(text):
    return [s.strip() for s in SENTENCE_END.split(text) if WORD.search(s)]


def _features(text, lang):
    words = WORD.findall(text)
    sents = _sentences(text)
    lengths = sorted(len(WORD.findall(s)) for s in sents) or [0]
    n = max(1, len(words))
    out = {"words": feature(len(words), "words"), "sentences": feature(len(sents), "sentences"),
           "words_per_sentence": feature(sum(lengths) / max(1, len(sents)), "words"),
           "long_sentence_share": feature(sum(1 for x in lengths if x > 25) / max(1, len(sents)), "share"),
           "question_share": feature(sum(1 for s in sents if s.rstrip().endswith("?")) / max(1, len(sents)), "share"),
           "numbers_per_100_words": feature(100 * len(re.findall(r"\d+(?:[.,]\d+)?", text)) / n, "per 100 words"),
           "second_person_per_100_words": feature(100 * len(SECOND_PERSON[lang].findall(text)) / n, "per 100 words"),
           "cta_phrases": feature(asks(text, lang), "asks (imperative calls to action)"),
           "lexical_diversity": feature(len({w.lower() for w in words[:300]}) / max(1, min(300, len(words))), "unique share (first 300 words)")}
    if sents:
        out["first_sentence_words"] = feature(len(WORD.findall(sents[0])), "words")
    return out


def _blocks(text):
    """Paragraphs (or markdown sections) as (start, end) character spans."""
    spans, pos = [], 0
    for m in re.finditer(r"\n\s*\n|(?=^#{1,6}\s)", text, re.M):
        if text[pos:m.start()].strip():
            spans.append((pos, m.start()))
        pos = m.end()
    if text[pos:].strip():
        spans.append((pos, len(text)))
    return spans


class TextSense:
    kind = "text"
    version = "4"
    extensions = (".txt", ".md", ".markdown", ".srt", ".vtt")
    spans = ("chars", "t")

    def measure(self, path, options=None):
        text, cues = read(path)
        lang = language(text)
        feats = _features(text, lang)
        feats["paragraphs"] = feature(len(_blocks(text)), "paragraphs")
        feats["headings"] = feature(len(re.findall(r"^#{1,6}\s", text, re.M)), "headings")
        feats["list_items"] = feature(len(re.findall(r"^\s*(?:[-*•]|\d+[.)])\s+", text, re.M)), "items")
        feats["text_chars"] = feature(len(text), "characters after NFC and LF newlines (what chars spans count)")
        notes = [f"language: {lang}"]
        if cues:
            duration = cues[-1][1]
            words = [len(WORD.findall(c[2])) for c in cues]
            first = sum(w for c, w in zip(cues, words) if c[0] < 10)
            gaps = [b[0] - a[1] for a, b in zip(cues, cues[1:])]
            feats.update(duration_s=feature(duration, "s"), words_per_min=feature(60 * sum(words) / max(1e-6, duration), "words/min"),
                         words_first_10s=feature(first, "words"), first_words_at_s=feature(cues[0][0], "s"),
                         longest_pause_s=feature(max(gaps) if gaps else 0.0, "s"))
            parts, bucket = [], 15.0
            for k in range(int(duration // bucket) + 1):
                a, b = k * bucket, min(duration, (k + 1) * bucket)
                if b > a:
                    parts.append({"span": {"t": [round(a, 2), round(b, 2)]}, "features": self.measure_span(path, {"t": [a, b]})["features"]})
        else:
            parts = [{"span": {"chars": [a, b]}, "features": _part(text[a:b], lang)} for a, b in _blocks(text)[:40]]
        return {"features": feats, "parts": parts, "notes": notes}

    def measure_span(self, path, span, options=None):
        text, cues = read(path)
        lang = language(text)
        if "t" in span:
            if not cues:
                raise ValueError("A time span needs timed text (.srt/.vtt)")
            a, b = span["t"]
            chunk = " ".join(c[2] for c in cues if a <= c[0] < b)
            f = _part(chunk, lang)
            f["words_per_min"] = feature(60 * f["words"]["value"] / max(1e-6, b - a), "words/min")
            return {"features": f}
        a, b = span["chars"]
        return {"features": _part(text[int(a):int(b)], lang)}

    def fingerprint(self, path, options=None):
        from .. import fingerprint
        return fingerprint.text(read(path)[0])

    def geometry(self, path, span, features, options=None):
        text, cues = read(path)
        key, (a, b) = next(iter(span.items()))
        total = (cues[-1][1] if cues else 0) if key == "t" else len(text)
        if key == "t" and not cues:
            raise ValueError("A time span needs timed text (.srt/.vtt)")
        if not total or b > total + 1e-6:
            raise ValueError(f"span ends after the text ({round(total, 2)} {'s' if key == 't' else 'characters'})")
        return {"share": round((b - a) / total, 4), "start_share": round(a / total, 4)}

    def evidence(self, path, span, out_dir, options=None):
        self.geometry(path, span, {}, options)  # refuses a span outside the (normalised) text
        text, cues = read(path)
        if "t" in span:
            a, b = span["t"]
            chunk = " ".join(c[2] for c in cues or [] if a <= c[0] < b)
        else:
            chunk = text[int(span["chars"][0]):int(span["chars"][1])]
        return [{"type": "text", "text": chunk[:600] + ("…" if len(chunk) > 600 else "")}]


def _part(chunk, lang):
    f = _features(chunk, lang)
    return {k: f[k] for k in ("words", "sentences", "words_per_sentence", "question_share", "numbers_per_100_words",
                              "second_person_per_100_words", "cta_phrases") if k in f}


register(TextSense())
