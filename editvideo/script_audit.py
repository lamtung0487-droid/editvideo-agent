"""Documentary script audit: does the narration explain, or only list?

From the owner's review of the Vietnam documentary: no depth, it does not say why things happened or what they led to,
so viewers do not understand, and it does not move them. Also from research on American historical documentaries
(docs/PRO_WORKFLOWS.md §32). Each chapter:
- poses a question;
- gives the situation and its causes;
- shows the decision and who made it;
- shows the event;
- gives the consequence that opens the next chapter.
One person carries the feeling, and music gets room between the lines.

The audit measures what text can show: the beat roles the writer declared, causal connectives, named people, years in
order, the narrator's estimated speaking time, breathing beats, the opening question and the closing callback. It does
not judge truth or quality: verify facts against sources and listen to the result.
"""
import re
import unicodedata

ROLES = ("hook", "context", "cause", "decision", "event", "consequence", "witness", "link", "breath", "payoff")
FRAMING = {"hook", "payoff", "breath"}
# connectives that carry cause, purpose, contrast or consequence, per language: "do" in "tự do" or "Do Thái", "buộc" in "ràng
# buộc" and English "do" are not causes
_CAUSAL = {"vi": re.compile(r"(?<!\w)(?:vì|(?<!tự )do(?! Thái)|bởi|nên|cho nên|vì thế|vì vậy|khiến|dẫn đến|dẫn tới|(?<!ràng )buộc|để|nhằm|"
                            r"kết quả|hệ quả|từ đó|thế là|nhưng|tuy|mặc dù|nếu|chính vì|cái giá|đổi lại)(?!\w)", re.I),
           "en": re.compile(r"(?<!\w)(?:because|therefore|thus|led to|forced|in order to|as a result|which meant|but|although|so that)(?!\w)", re.I)}
_CONSEQ = {"vi": re.compile(r"(?<!\w)(?:dẫn đến|dẫn tới|kết quả|hệ quả|từ đó|khiến|(?<!ràng )buộc|cái giá|để lại|mở ra|chấm dứt|thay đổi)(?!\w)", re.I),
           "en": re.compile(r"(?<!\w)(?:led to|as a result|which meant|left|opened|ended|changed)(?!\w)", re.I)}
_YEAR = re.compile(r"(?<!\d)(18[5-9]\d|19\d\d|20[0-4]\d)(?!\d)")
_DATE_LEAD = re.compile(r"^\s*(năm|ngày|tháng|đầu năm|cuối năm|in|on)?\s*\d", re.I)
# common Vietnamese surnames, which name a person only with a given name after them ("Đông Dương" is a place, "Văn bản" a
# word); and single names history often uses alone
_SURNAMES = ("Nguyễn Trần Lê Phạm Hoàng Huỳnh Phan Vũ Võ Đặng Bùi Đỗ Hồ Ngô Dương Lý Đinh Trương Lương Đoàn Văn Trịnh Mai Tô Kim Tôn "
             "Phùng").split()
_SINGLE = ("Kissinger Johnson Nixon Kennedy Eisenhower Clinton Truman McCain Kerry Peterson Cronkite McNamara Whitehurst Diệm Thiệu "
           "Giáp Pol").split()
_UP = "".join(sorted({c for c in map(chr, range(0x41, 0x1EFA)) if c.isupper() and c.isalpha()}))  # every Latin capital, tone marks included
_NAME = re.compile(r"(?<!\w)(?:(?:" + "|".join(_SURNAMES) + r")(?:\s+[" + _UP + r"]\w*){1,3}|(?:" + "|".join(_SINGLE) + r")(?:\s+[" + _UP
                   + r"]\w*){0,2})(?!\w)")
_PLACES = {"Hoàng Sa", "Trường Sa", "Phan Thiết", "Phan Rang", "Hồ Gươm", "Hồ Tây", "Hồ Hoàn Kiếm", "Lê Lợi"}  # surname-shaped places and streets
_NOT_PEOPLE = {"", "narrator", "song", "music", "nhạc", "bài hát"}   # voice values that are not a speaking person
SYLLABLES_PER_S = 2.95  # measured: film 4 third cut, 64 ElevenLabs v3 lines at speed .9, 2435 syllables in 826 s
WORDS_PER_S_EN = 2.5    # documentary English, ~150 words a minute


def _lang(text):
    return "vi" if re.search(r"[đăâêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ]", text.lower()) else "en"


def _people(text):
    out = set()
    for m in _NAME.finditer(text):
        name = m.group(0).strip()
        if any(name == p or name.startswith(p + " ") for p in _PLACES) or re.search(r"(?:phố|TP\.?)\s+$", text[max(0, m.start() - 6):m.start()]):
            continue
        out.add(name)
    return out


def _spoken(text):
    """Text the narrator says: a beat written as '(nhạc)' or '[silence]' is not spoken."""
    t = text.strip()
    return "" if (t.startswith("(") and t.endswith(")")) or (t.startswith("[") and t.endswith("]")) else t


# Narration both audiences can trust (docs/NARRATION_STYLE.md). Round 13: the owner found words that were obscure or
# could start an argument ("từ tuyên ngôn độc lập dẫn đến chiến tranh"), and asked for documentary prose, not AI prose.
_LOADED = {  # epithets and verdicts: the picture, the numbers and the witnesses carry judgement, the narrator does not
    "vi": re.compile(r"(?<!\w)(?:ngụy|giặc|bè lũ|đế quốc|tay sai|bù nhìn|tàn bạo|dã man|man rợ|hèn hạ|hèn nhát|anh dũng|oanh liệt|vĩ đại|"
                     r"hào hùng|huy hoàng|lẫy lừng|chói lọi|vẻ vang|vắt kiệt|trút xuống|trút bom|cuồng|kẻ thù truyền kiếp|xâm lược)(?!\w)", re.I),
    "en": re.compile(r"\b(?:heroic|brutal|barbaric|evil|puppet|cowardly|glorious|savage|aggressors?|invaders?|regime|commies?|gooks?)\b", re.I)}
_TELLS = {  # documentary prose that reads as machine-written (humanizer's patterns, carried into Vietnamese)
    "vi": re.compile(r"(?<!\w)(?:không chỉ|hành trình|dấu ấn|minh chứng|biểu tượng của|bản hùng ca|khúc tráng ca|trang sử vàng|chưa từng có|"
                     r"đáng kinh ngạc|có thể nói|điều đáng nói|đánh dấu một|mở ra một chương|một chương mới|nốt son|bức tranh|câu chuyện về|"
                     r"không thể phủ nhận|thực sự là|vô cùng)(?!\w)", re.I),
    "en": re.compile(r"\b(?:not just|not only|testament|tapestry|pivotal|crucial|landscape of|journey|delve|showcas\w*|underscor\w*|"
                     r"stands as|serves as|indelible|enduring legacy)\b", re.I)}
_STRONG_CAUSE = {"vi": re.compile(r"(?<!\w)(?:dẫn đến|dẫn tới|khiến|(?<!ràng )buộc(?! (?:ngọn|dây|chặt|lại|vào|tóc|cây|tay))|vì thế|vì vậy|"
                                r"cho nên|là nguyên nhân)(?!\w)", re.I),
                 "en": re.compile(r"\b(?:led to|caused|forced|because of this|as a result|which is why)\b", re.I)}
_ATTRIBUTED = {"vi": re.compile(r"(?<!\w)(?:theo|cho rằng|tin rằng|nói|tuyên bố|viết|gọi|coi|thừa nhận|công bố|kết luận|ước tính|lập luận)(?!\w)", re.I),
               "en": re.compile(r"\b(?:according to|said|says|argued|believed|claimed|wrote|called|estimated|concluded|admitted)\b", re.I)}
_IRONY = {"vi": re.compile(r"gọi (?:đó|nó|việc này|việc đó) là [^.]{2,60}\.\s*Nhưng", re.I),
          "en": re.compile(r"called it [^.]{2,60}\.\s*But", re.I)}
MAX_SENTENCE = {"vi": 32, "en": 28}  # syllables (Vietnamese) or words: one breath of a calm narrator
# The owner's team review of the sixth cut's script (round 13): absolute claims, formula contrasts, numbers the ear cannot
# hold, and a narrator who explains the meaning instead of telling what happened.
_ABSOLUTE = {"vi": re.compile(r"(?<!\w)(?:không còn ai|không ai|không có quyền quyết định điều gì|hoàn toàn|tất cả mọi|mọi người đều|"
                              r"chưa bao giờ|không bao giờ|không người nào|không một ai|duy nhất|bị san phẳng|san phẳng)(?!\w)", re.I),
             "en": re.compile(r"(?:no one|nobody|never|always|everyone|entirely|completely|wiped out|razed)", re.I)}
_FORMULA = {"vi": re.compile(r"(?<!\w)(?:\w+ đến, nhưng [^.,]{2,30} ở lại|không thể tiếp tục như cũ|nhanh hơn ai ngờ|sau tất cả|hơn bao giờ hết|"
                             r"ngần ấy cuộc chiến|dân tộc nhỏ|vẫn đang nối dài|là câu chuyện của cả|không mang lại một)(?!\w)", re.I),
            "en": re.compile(r"(?:after all|more than ever|faster than anyone|the story of an entire|still reaching out)", re.I)}
# A spoken quantity is a run of number words with a magnitude in it ("sáu mươi chín", "hai trăm tỷ", "61 %"); dates are
# not counted (the ear takes "ngày 27 tháng 1 năm 1973" as one moment, not three figures), nor "năm người con" alone.
_DATES = {"vi": re.compile(r"(?<!\w)(?:(?:ngày|mùng)\s+\d{1,2}\s+)?(?:tháng\s+(?:\d{1,2}|giêng|chạp)\s+)?(?:năm\s+|những năm\s+)?"
                          r"(?:18[5-9]\d|19\d\d|20[0-4]\d)(?!\d)|(?<!\w)(?:ngày|mùng|đêm)\s+\d{1,2}(?:\s+tháng\s+\d{1,2})?|(?<!\w)tháng\s+\d{1,2}(?!\d)",
                          re.I),
          "en": re.compile(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}"
                           r"(?:,\s*\d{4})?|(?<!\d)(?:18[5-9]\d|19\d\d|20[0-4]\d)s?(?!\d)", re.I)}
_NUMBER_WORDS = {"vi": set("một hai ba bốn tư năm lăm sáu bảy tám chín mười mươi mốt linh lẻ trăm nghìn ngàn vạn triệu tỷ rưỡi nửa phần".split()),
                 "en": set("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
                           "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion "
                           "percent half".split())}
_MAGNITUDE = {"vi": {"mười", "mươi", "trăm", "nghìn", "ngàn", "vạn", "triệu", "tỷ", "nửa", "rưỡi"},
              "en": {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
                     "billion", "percent", "half"}}


def _quantities(text, lang):
    """The quantities a listener has to hold in one beat: runs of number words or digits that carry a magnitude, dates
    left out."""
    text = _DATES[lang].sub(" , ", text)
    text = re.sub(r"(?<!\w)[A-Za-z]{1,4}-\d+\w*", " ", text)  # a model name (B-52, F-4, AK-47) is not a figure
    vague = {"vi": r"(?<!\w)(?:hàng|vài|mấy)\s+(?:chục\s+|trăm\s+)?(?:chục|trăm|nghìn|ngàn|vạn|triệu)(?:\s+(?:nghìn|ngàn|triệu))?(?!\w)",
             "en": r"(?:tens of |hundreds of )?(?:dozens|hundreds|thousands|millions)(?: of)?"}[lang]
    text = re.sub(vague, " ", text, flags=re.I)  # "hàng nghìn", "thousands of": a size, not a figure to hold
    if lang == "vi":
        text = re.sub(r"(?<!\w)tỷ (?:lệ|số|giá|trọng)(?!\w)", " ", text, flags=re.I)  # a rate, not a billion
    runs = []
    for clause in re.split(r"[,.;:!?()«»\"“”]", text.lower()):
        run = []
        for w in [*clause.replace("-", " ").split(), ""]:
            w = w.strip("%")
            if w and (w in _NUMBER_WORDS[lang] or re.fullmatch(r"\d[\d.,]*", w)):
                run.append(w)
                continue
            if any(x in _MAGNITUDE[lang] or x[0].isdigit() for x in run) or ("phần" in run[:-1]):
                runs.append(" ".join(run))
            run = []
    return runs


MAX_QUANTITIES = 2  # per beat: the ear holds two (the team flagged beats of three); the rest go on screen with their source


def style(beats):
    """Per narration beat: loaded words, machine-prose tells, strong causal claims nobody is credited with, irony, dashes and
    over-long sentences. Findings name the beat and the words; a prompt for the writer, quotes inside «» or "" are
    left alone (they are someone's words)."""
    out = []
    for beat in beats:
        text = unicodedata.normalize("NFC", _spoken(beat.get("narration", "")))
        if not text:
            continue
        lang = _lang(text)
        said = re.sub(r"«[^»]*»|\"[^\"]*\"|“[^”]*”", " ", text)  # the narrator's own words only
        bid = beat.get("id")
        for code, rx, tip in (("loaded_word", _LOADED, "A verdict or an epithet in the narrator's mouth: state the fact, put judgement in a witness's words."),
                              ("machine_prose", _TELLS, "A stock phrase that sounds machine-written: say the specific thing instead.")):
            hits = sorted({m.group(0).lower() for m in rx[lang].finditer(said)})
            if hits:
                out.append({"level": "check", "code": code, "where": bid, "evidence": hits[:6], "suggestion": tip})
        for s in re.split(r"(?<=[.!?…;:])\s+", said):
            if _STRONG_CAUSE[lang].search(s) and not _ATTRIBUTED[lang].search(s):
                out.append({"level": "check", "code": "unattributed_cause", "where": bid, "evidence": s.strip()[:120],
                            "suggestion": "A cause stated as fact. Credit it to whoever argued it, or tell the events in order and let "
                                          "the viewer connect them."})
            n = len(s.split())
            if n > MAX_SENTENCE[lang]:
                out.append({"level": "check", "code": "long_sentence", "where": bid, "evidence": {"length": n, "max": MAX_SENTENCE[lang]},
                            "suggestion": "More than one breath: split it, one fact per sentence."})
        for code, rx, tip in (("absolute_claim", _ABSOLUTE, "An absolute claim ('no one', 'completely', 'razed'): check it against the "
                                                                "sources and say exactly what happened, or drop it."),
                              ("formula_line", _FORMULA, "A formula line ('peace came, but poverty stayed', 'after all'): it explains "
                                                         "instead of telling. Say the next fact, or let the picture and music end it.")):
            hits = sorted({m.group(0).lower() for m in rx[lang].finditer(said)})
            if hits:
                out.append({"level": "check", "code": code, "where": bid, "evidence": hits[:6], "suggestion": tip})
        q = len(_quantities(said, lang))
        if q > MAX_QUANTITIES:
            out.append({"level": "check", "code": "number_load", "where": bid, "evidence": {"quantities": q, "max": MAX_QUANTITIES},
                        "suggestion": "More numbers than the ear can hold: say the one that matters, put the rest on screen with "
                                      "their source (data_story)."})
        if _IRONY[lang].search(said):
            out.append({"level": "check", "code": "irony", "where": bid,
                        "suggestion": "'They called it X. But…' mocks instead of telling; give the fact plainly."})
        if "—" in said or re.search(r"(?<![A-ZÀ-Ỹa-zà-ỹ]) – |[a-zà-ỹ] – [a-zà-ỹ]", said):  # "Xuân – Hè", "Việt – Trung" are names
            out.append({"level": "info", "code": "dash", "where": bid, "suggestion": "A dash in narration: a full stop or a comma reads better aloud."})
    # a writer who checked a finding and keeps the line says so on the beat: accept={"absolute_claim": "the 1956 vote was never held"}
    accepted = {b.get("id"): set(b.get("accept") or ()) for b in beats}
    return [f for f in out if f["code"] not in accepted.get(f["where"], ())]


_SCHEDULED = re.compile(r"(?<!\w)(?:hẹn|dự kiến|sẽ|scheduled|planned|due|set for)(?!\w)[^.;!?]{0,50}$", re.I)
_SINCE = re.compile(r"^\s*(?:từ|kể từ|since|from)\s", re.I)


def _told_years(text):
    """(earliest, latest) for each year a passage tells as having happened: a decade ('những năm 1980', 'the 1980s') spans
    ten years; a date something was set for ('hẹn tổng tuyển cử vào tháng 7 năm 1956') has not happened yet."""
    out = []
    for m in _YEAR.finditer(text):
        before = text[max(0, m.start() - 60):m.start()]
        if _SCHEDULED.search(before):
            continue
        y = int(m.group(1))
        decade = y % 10 == 0 and (re.search(r"(?:những năm|thập niên)\s*$", before, re.I) or text[m.end():m.end() + 1] == "s")
        out.append((y, y + 9 if decade else y))
    return out


def beat_order(beats):
    """Within one chapter, a beat that opens earlier than the beats before it reached is a jump back the viewer is not
    told about (the team's review: Roosevelt 1944 before the 1940 famine; July 1945 told after 2 September). A beat opens
    at the first year of its first sentence; a year mentioned later in it is backstory. Not jumps: a beat that opens with
    a span to the present ('Từ năm 1988, …'), and beats the writer marks `flashback` (a coda, a date card on screen) or
    `comparison` (then and now: 'In 1995 … In 2025 …'). Returns findings `beat_time_jump`."""
    out, reach, chapter = [], None, None
    for beat in beats:
        if beat.get("chapter") != chapter:
            chapter, reach = beat.get("chapter"), None
        text = unicodedata.normalize("NFC", _spoken(beat.get("narration", "")))
        told = _told_years(text)
        if not told:
            continue
        first = re.split(r"(?<=[.!?…])\s+", text.strip())[0]
        opens = _told_years(first)
        if (reach is not None and opens and opens[0][1] < reach - 1 and not _SINCE.match(first)
                and not (beat.get("flashback") or beat.get("comparison"))):
            out.append({"level": "check", "code": "beat_time_jump", "where": beat.get("id"), "evidence": {"opens": opens[0][0], "reached": reach},
                        "suggestion": "This beat goes back in time without saying so: move it before the later events, or mark "
                                      "it as a flashback on screen (a date card)."})
        reach = max(reach or 0, max(a for a, _ in told))
    return out


def recording_gate(lines):
    """Which narration lines may be recorded: a line with a number, a date or a quotation needs sources and the status
    'verified'; 'needs_source' and 'disputed' wait (the team's review: lock nothing whose figures or quotations are not yet
    traced). lines: [{"id", "text", "status"?, "sources"?}]. Returns {"ready": [ids], "waiting": [{"id", "why"}]}."""
    ready, waiting = [], []
    for ln in lines:
        text = unicodedata.normalize("NFC", ln.get("text", ""))
        factual = bool(_YEAR.search(text) or _quantities(text, _lang(text)) or re.search(r"[«“\":]", text))
        status = ln.get("status") or ("verified" if not factual else "needs_source")
        if status != "verified":
            waiting.append({"id": ln.get("id"), "why": status})
        elif factual and not ln.get("sources"):
            waiting.append({"id": ln.get("id"), "why": "verified without a source named"})
        else:
            ready.append(ln.get("id"))
    return {"ready": ready, "waiting": waiting}


def audit(brief):
    """brief: a CreativeBrief (or its dict). Returns per-chapter measurements and findings (level 'check' or 'info')."""
    b = brief if isinstance(brief, dict) else brief.model_dump()
    beats = b.get("beats") or []
    chapters, order = {}, []
    for k, beat in enumerate(beats):
        ch = beat.get("chapter") or "film"
        if ch not in chapters:
            chapters[ch] = []
            order.append(ch)
        chapters[ch].append((k, beat))
    rows, findings = [], []
    prev_year = None
    for ch in order:
        items = [beat for _, beat in chapters[ch]]
        text = unicodedata.normalize("NFC", " ".join(_spoken(x.get("narration", "")) for x in items))
        lang = _lang(text)
        syl = len(text.split())
        rate = SYLLABLES_PER_S if lang == "vi" else WORDS_PER_S_EN
        roles = [x.get("role") or "" for x in items]
        sentences = [s for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
        causal = len(_CAUSAL[lang].findall(text))
        people = sorted(_people(text) | {unicodedata.normalize("NFC", x.get("voice")) for x in items
                                         if (x.get("voice") or "").strip().lower() not in _NOT_PEOPLE})
        years = [int(y) for y in _YEAR.findall(text)]
        anchor = years[0] if years else None   # where the chapter stands in time; an earlier year after it is a flashback
        dated = sum(1 for s in sentences if _DATE_LEAD.match(s))
        breaths = sum(1 for x, r in zip(items, roles) if r == "breath" or not _spoken(x.get("narration", "")))
        row = {"chapter": ch, "beats": len(items), "language": lang, "spoken_s": round(syl / rate, 1), "words": syl, "causal_connectives": causal,
               "causal_per_min": round(causal / max(syl / rate / 60, 1e-6), 1) if syl else 0.0, "people": people[:8],
               "years": [min(years), max(years)] if years else [], "date_led_sentences": dated, "sentences": len(sentences), "breaths": breaths,
               "roles": {r: roles.count(r) for r in ROLES if roles.count(r)}}
        rows.append(row)
        bookend = any(r in ("hook", "payoff") for r in roles)  # a present-day bookend may sit outside the order
        framing = bool(roles) and all(r in FRAMING for r in roles)  # only a chapter of pure framing is spared the story checks
        story = not framing and syl > 20
        if story and causal == 0:  # declared roles do not stand in for a reason the viewer can hear
            findings.append({"level": "check", "code": "chapter_without_cause", "where": ch,
                             "suggestion": "Say why it happened: the situation and the pressure behind the decision (because, so, which forced…)."})
        if story and not _CONSEQ[lang].search(text) and not ({"consequence", "link"} & set(roles) and causal):
            findings.append({"level": "check", "code": "chapter_without_consequence", "where": ch,
                             "suggestion": "Say what it led to, and hand over to the next chapter: the consequence is the next chapter's cause."})
        if story and not people:
            findings.append({"level": "check", "code": "chapter_without_person", "where": ch,
                             "suggestion": "Give the chapter a person: a named witness, a letter or diary line, a decision-maker in their own words."})
        if story and len(sentences) >= 3 and dated / len(sentences) > .5 and causal / max(len(sentences), 1) < .5:
            findings.append({"level": "check", "code": "chronicle_not_story", "where": ch, "evidence": {"date_led": dated, "sentences": len(sentences)},
                             "suggestion": "Most sentences open with a date and few explain: a list of events. Lead with what changed and why; dates as anchors."})
        if story and row["spoken_s"] > 45 and breaths == 0:
            findings.append({"level": "check", "code": "no_breathing_room", "where": ch, "evidence": {"spoken_s": row["spoken_s"]},
                             "suggestion": "Over 45 s of narration without a pause: give the music and the picture 8-20 s alone."})
        if anchor and prev_year is not None and anchor < prev_year - 1 and not bookend:
            findings.append({"level": "check", "code": "time_jumps_back", "where": ch, "evidence": {"first_year": anchor, "previous": prev_year},
                             "suggestion": "The chapter opens earlier than the previous one: keep the order, or open on the present of the "
                                           "story and give the earlier years as a flashback inside it."})
        if anchor and not bookend:
            prev_year = max(prev_year or 0, anchor)
    first = beats[:3]
    if beats and not any(x.get("viewer_question") or "?" in x.get("narration", "") or (x.get("role") == "hook") for x in first):
        findings.append({"level": "check", "code": "opening_without_question", "where": first[0].get("id") if first else None,
                         "suggestion": "Open on a question or a paradox the film will answer; state the film's thesis early."})
    motif = (beats[0].get("motif") or "").strip().lower() if beats else ""
    if motif and not any(motif in (x.get("motif") or "").lower() or motif in x.get("narration", "").lower() for x in beats[-3:]):
        findings.append({"level": "info", "code": "no_callback", "where": beats[-1].get("id"),
                         "suggestion": "The opening motif does not return at the end; a theme heard first and resolved last binds the film."})
    findings += style(beats) + beat_order(beats)
    total = sum(r["spoken_s"] for r in rows)
    return {"chapters": rows, "findings": findings,
            "estimates": {"spoken_s": round(total, 1), "syllables_per_s": SYLLABLES_PER_S, "words_per_s_en": WORDS_PER_S_EN,
                          "people": sorted({p for r in rows for p in r["people"]})[:40]},
            "method": "Text heuristics on the declared beat roles and the narration (Vietnamese and English connectives, surnames, years). "
                      "A prompt for the writer, not a verdict: facts still need sources, delivery needs listening."}
