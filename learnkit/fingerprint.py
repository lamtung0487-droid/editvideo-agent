"""Content fingerprints: is this the same work (a copy, a re-save, an edit, a trim, an excerpt), whatever its measurements say?

Measurements describe a work's design; two pages from one template can measure alike and still be different works,
and a copy with one invisible change can measure differently. So "same work" is decided per kind from content, with
three verdicts: "same", "unsure" (a light edit, or much shared material) and "distinct"; gates count "unsure" as the
same work, so an edit cannot pass for new evidence:

    text / web   normalised (NFKC, invisible characters dropped, look-alike letters folded, case folded), then MinHash
                 of 5-word shingles (same: Jaccard >= .8, or one nearly inside the other) and of word pairs (unsure:
                 Jaccard >= .5, or 80 % of one inside the other: a light edit); a web page by its own text, outside
                 site furniture (landmarks, and elements named like a menu or footer, unless they hold its h1, main or
                 article), and as the same work when one page's own text lies inside the other's whole text
    image        pHash + dHash after stripping uniform borders, also mirrored and as its centre square (a flip or a
                 square recrop of a wide image is the same picture)
    audio        band-energy difference bits (Haitsma-Kalker style, every 0.1 s) and video frame dHashes (2 per second),
    video        matched window by window (5 s), each window aligned on its own so trims, excerpts and speed changes
                 of 2 % still line up: same when 80 % of the shorter work's windows are found in the other, distinct
                 at a third or less (a shared intro), unsure between (half the material shared)

Works with no content to compare (empty text, silence, a plain image) give no verdict (None), and
neither do fingerprints of another version. Each fingerprint is a small JSON-able dict.
"""
import hashlib
import re
import unicodedata
import numpy as np

VERSION = "4"
SAME, UNSURE, DISTINCT = "same", "unsure", "distinct"
PERMS = 128
_RNG = np.random.default_rng(20261020)
_A = _RNG.integers(1, 2 ** 63, PERMS, dtype=np.uint64) | np.uint64(1)
_B = _RNG.integers(0, 2 ** 63, PERMS, dtype=np.uint64)
TOKEN = re.compile(r"[^\W_]+")
# Latin look-alikes used to disguise a copy: Cyrillic, Greek, Armenian and Cherokee letters and Latin small capitals that
# render like Latin letters (after case folding).
_FOLD = str.maketrans("аеорсухіјѕԁӏԛԝɡвкмнтһԍαεικνορτυχϲϳօսոհցաոɑɩꮪꭺꮃᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘʀꜱᴛᴜᴠᴡʏᴢ",
                      "aeopcyxijsdlqwgbkmhthgaeikvoptuxcjounhgwnaiswaabcdefghijklmnoprstuvwyz")
# Characters that show nothing: format controls (Cf), combining marks left after composition (Mn, Me: variation
# selectors, the grapheme joiner), and blank letters (Hangul fillers, the braille blank).
_BLANK = {"\u115f", "\u1160", "\u3164", "\uffa0", "\u2800"}


def normalise(text):
    text = unicodedata.normalize("NFKC", text)  # composes accented letters (Vietnamese keeps its tones) and folds width
    text = "".join(c for c in text if unicodedata.category(c) not in ("Cf", "Mn", "Me") and c not in _BLANK)
    return text.casefold().translate(_FOLD)


def _hash(s):
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little")


def _minhash(shingles):
    if not shingles:
        return []
    x = np.fromiter((_hash(s) for s in shingles), dtype=np.uint64, count=len(shingles))
    sig = np.full(PERMS, np.iinfo(np.uint64).max, dtype=np.uint64)
    for start in range(0, len(x), 4096):
        chunk = x[start:start + 4096]
        with np.errstate(over="ignore"):
            sig = np.minimum(sig, (_A[:, None] * chunk[None, :] + _B[:, None]).min(axis=1))
    return [int(v) & 0xFFFFFFFF for v in sig]  # 32 bits per permutation is plenty to estimate Jaccard


def _shingles(words, k):
    return {" ".join(words[i:i + k]) for i in range(max(1, len(words) - k + 1))} if words else set()


def text(content):
    """MinHash signatures of a text's 5-word shingles and of its word pairs (shorter texts use shorter shingles)."""
    words = TOKEN.findall(normalise(content))
    k = 5 if len(words) >= 25 else 3 if len(words) >= 9 else 1
    long, pairs = _shingles(words, k), _shingles(words, 2 if len(words) >= 4 else 1)
    return {"type": "text", "v": VERSION, "k": k, "n": len(long), "sig": _minhash(long), "n2": len(pairs), "sig2": _minhash(pairs)}


def web(own, everything):
    """A web page: its own text (outside site furniture) and all of its text."""
    return {"type": "web", "v": VERSION, "own": text(own), "all": text(everything)}


def _inside(part, whole):
    """How much of `part` lies inside `whole` (5-word shingles, then word pairs), from their MinHash signatures."""
    out = []
    for sig, n in (("sig", "n"), ("sig2", "n2")):
        if not part[n] or not whole[n] or (sig == "sig" and part.get("k") != whole.get("k")):
            out.append(0.0)
            continue
        j = float(np.mean(np.array(part[sig]) == np.array(whole[sig])))
        out.append(j * (part[n] + whole[n]) / (1 + j) / part[n])
    return out


def _web_verdict(a, b):
    """Pages compare on their own text (20+ shingles each). A page whose own text lies inside the other's whole text is
    the same work too: a copy can hide its content in elements named like furniture."""
    oa, ob = a["own"], b["own"]
    v = _text_verdict(oa, ob) if oa["n"] >= 20 and ob["n"] >= 20 else None
    if v in (SAME, UNSURE):
        return v
    cross = [_inside(x, y) for x, y in ((oa, b["all"]), (ob, a["all"])) if x["n"] >= 20]
    if any(c[0] >= .9 for c in cross):
        return SAME
    if any(c[1] >= .8 for c in cross):
        return UNSURE
    return v  # distinct, or None when neither page has 20 shingles of its own (measurements decide)


def _overlap(sa, sb, na, nb):
    j = float(np.mean(np.array(sa) == np.array(sb)))
    shared = j * (na + nb) / (1 + j)  # |A ∩ B| from Jaccard and sizes
    return j, shared / max(1, min(na, nb))


def _text_verdict(a, b):
    if not a["n"] or not b["n"]:
        return None  # nothing to compare
    j, inside = _overlap(a["sig"], b["sig"], a["n"], b["n"])
    if j >= .8 or (min(a["n"], b["n"]) >= 20 and inside >= .9):
        return SAME
    j2, inside2 = _overlap(a["sig2"], b["sig2"], a["n2"], b["n2"])
    if j2 >= .5 or (min(a["n2"], b["n2"]) >= 30 and inside2 >= .8):
        return UNSURE
    return DISTINCT


def _trim(g, tol=10, max_share=.25):
    """Strip uniform borders (letterbox, frames, padding) layer by layer, so a bordered copy hashes like the original."""
    h, w = g.shape
    t, b, l, r = 0, h, 0, w
    for _ in range(6):
        before = (t, b, l, r)
        while t < h * max_share and t < b - 1 and np.ptp(g[t, l:r]) <= tol:
            t += 1
        while b > h * (1 - max_share) and b - 1 > t and np.ptp(g[b - 1, l:r]) <= tol:
            b -= 1
        while l < w * max_share and l < r - 1 and np.ptp(g[t:b, l]) <= tol:
            l += 1
        while r > w * (1 - max_share) and r - 1 > l and np.ptp(g[t:b, r - 1]) <= tol:
            r -= 1
        if (t, b, l, r) == before:
            break
    return g[t:b, l:r]


def _pack(bits):
    return int("".join("1" if v else "0" for v in np.ravel(bits)), 2)


def _hashes(g):
    import cv2
    small = cv2.resize(g, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(small)[:8, :8]
    d9 = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA)
    return [_pack(dct > np.median(dct[1:, 1:])), _pack(d9[:, 1:] > d9[:, :-1])]


def image(rgb_or_gray):
    """pHash and dHash (64 bits each) of an image after stripping uniform borders, mirrored and as its centre square."""
    import cv2
    g = rgb_or_gray if rgb_or_gray.ndim == 2 else cv2.cvtColor(rgb_or_gray, cv2.COLOR_RGB2GRAY)
    g = g.astype(np.float32)
    scale = 256 / max(g.shape)
    if scale < 1:
        g = cv2.resize(g, (max(1, round(g.shape[1] * scale)), max(1, round(g.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    whole, g = g, _trim(g)
    if g.size < 4 or np.ptp(g) <= 10:
        return {"type": "image", "v": VERSION, "flat": True}  # a plain image: nothing to tell apart
    h, w = whole.shape
    side = min(h, w)
    centre = _trim(whole[(h - side) // 2:(h - side) // 2 + side, (w - side) // 2:(w - side) // 2 + side])  # as a square recrop sees it
    if centre.size < 4 or np.ptp(centre) <= 10:
        centre = g
    return {"type": "image", "v": VERSION, "full": _hashes(g), "mirror": _hashes(np.ascontiguousarray(g[:, ::-1])),
            "centre": _hashes(centre)}


def _bits(x):
    return bin(x).count("1")


def _image_verdict(a, b):
    """Measured on a 20-image series sharing one layout: re-encodes, resizes and frames <= 4 bits pHash, a 4 % crop per
    side 7-13; different images of the series >= 20."""
    if a.get("flat") or b.get("flat"):
        return None
    pairs = [(a["full"], b["full"]), (a["full"], b["mirror"]), (a["full"], b["centre"]), (a["centre"], b["full"])]
    dist = [(_bits(x[0] ^ y[0]), _bits(x[1] ^ y[1])) for x, y in pairs]
    if any(p <= 14 and d <= 16 for p, d in dist):
        return SAME
    if any(p <= 18 and d <= 22 for p, d in dist):
        return UNSURE
    return DISTINCT


_POP16 = np.array([bin(i).count("1") for i in range(1 << 16)], dtype=np.int64)


def _popcount(x):
    x = np.asarray(x, dtype=np.uint64)
    out = np.zeros(x.shape, dtype=np.int64)
    for shift in (0, 16, 32, 48):
        out += _POP16[((x >> np.uint64(shift)) & np.uint64(0xFFFF)).astype(np.int64)]
    return out


def audio(y, rate, step=.1, bands=17):
    """Sign bits of band-energy differences over time and frequency, one 16-bit word per 0.1 s (silence gives none).

    Each frame spans 8 steps (0.8 s; 0.4 or 0.2 s for clips under about 3 s): the long overlap keeps the bits stable when
    a copy is trimmed off the step grid or carries noise. Measured on synthetic music and speech: off-grid trims <= 0.13
    bit errors, noise at 5 dB SNR about 0.16, AAC 96k / MP3 128k / Opus 48k <= 0.044; other works about 0.48.
    """
    hop = int(rate * step)
    y = np.asarray(y, dtype=np.float32)
    for window in (8, 4, 2):
        span = window * hop
        n = (len(y) - span) // hop + 1 if len(y) >= span else 0
        if n >= 13:
            break
    else:
        return {"type": "audio", "v": VERSION, "frames": []}
    win = np.hanning(span).astype(np.float32)
    edges = np.geomspace(300, min(3000, rate / 2 - 1), bands + 1)
    bins = np.digitize(np.fft.rfftfreq(span, 1 / rate), edges) - 1  # band of each FFT bin; -1 and `bands` fall outside
    masks = [bins == b for b in range(bands)]
    energy = np.zeros((n, bands), dtype=np.float64)
    for start in range(0, n, 256):
        rows = np.arange(start, min(n, start + 256))
        mag = np.abs(np.fft.rfft(np.stack([y[r * hop:r * hop + span] for r in rows]) * win, axis=1)) ** 2
        for b, m in enumerate(masks):
            energy[rows, b] = mag[:, m].sum(axis=1)
    diff = (energy[1:, :-1] - energy[1:, 1:]) - (energy[:-1, :-1] - energy[:-1, 1:])
    if np.median(np.abs(diff)) <= 1e-6 * (np.median(energy) + 1e-12):
        return {"type": "audio", "v": VERSION, "frames": [], "flat": True}  # silence: nothing to tell apart
    words = [int("".join("1" if v > 0 else "0" for v in row), 2) for row in diff]
    level = np.log1p(energy.sum(axis=1)[1:])
    return {"type": "audio", "v": VERSION, "step": step, "window": window, "frames": words,
            "level": [round(float(v), 3) for v in level]}


def frames(hashes, levels, step):
    """A video as 64-bit dHashes of its frames sampled every `step` seconds, with each frame's mean level for alignment."""
    if len(hashes) < 4 or len(set(hashes)) < 2:
        return {"type": "frames", "v": VERSION, "frames": []}  # too short, or one still frame throughout
    return {"type": "frames", "v": VERSION, "step": step, "frames": [int(h) for h in hashes],
            "level": [round(float(v), 4) for v in levels]}


def video_file(path, ffmpeg, fps=2):
    """Frame fingerprint of a video file: ffmpeg samples `fps` frames per second as 9x8 grey thumbnails (area-averaged)."""
    import subprocess
    cmd = [ffmpeg, "-v", "error", "-i", str(path), "-an", "-vf", f"fps={fps},scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode:
        raise ValueError(f"Could not decode video frames: {p.stderr.decode(errors='replace')[:160]}")
    g = np.frombuffer(p.stdout, dtype=np.uint8)
    g = g[:len(g) // 72 * 72].reshape(-1, 8, 9).astype(np.int16)
    return frames([_pack(f[:, 1:] > f[:, :-1]) for f in g], g.reshape(len(g), -1).mean(axis=1) / 255, 1 / fps)


def _normed(x):
    x = np.asarray(x, dtype=np.float64)
    return (x - x.mean()) / (x.std() + 1e-9)


def _offsets(a, b, top=5):
    """Candidate lags (a[i] ~ b[i - lag]) aligning two level curves: peaks of their normalised FFT cross-correlation."""
    x, y = _normed(a), _normed(b)
    n = 1 << int(np.ceil(np.log2(len(x) + len(y))))
    cc = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(y, n)), n)
    lags = np.r_[np.arange(0, len(x)), np.arange(-len(y) + 1, 0)]
    vals = np.r_[cc[:len(x)], cc[n - len(y) + 1:]]
    return [int(v) for v in lags[np.argsort(vals)[::-1][:top]]]


def _local_starts(window_level, level, top=3):
    """Where in `level` a short level curve fits best (normalised cross-correlation at every position)."""
    w, lv = len(window_level), np.asarray(level, dtype=np.float64)
    if len(lv) < w or w < 2:
        return []
    t = _normed(window_level)
    n = 1 << int(np.ceil(np.log2(len(lv) + w)))
    num = np.fft.irfft(np.fft.rfft(lv, n) * np.conj(np.fft.rfft(t, n)), n)[:len(lv) - w + 1]
    c1, c2 = np.r_[0, np.cumsum(lv)], np.r_[0, np.cumsum(lv * lv)]
    s1, s2 = c1[w:] - c1[:-w], c2[w:] - c2[:-w]
    score = num / np.sqrt(np.maximum(s2 - s1 * s1 / w, 1e-9))
    return [int(v) for v in np.argsort(score)[::-1][:top]]


def matched_share(a, b, bits, win, err_max, max_windows=40):
    """Share of the shorter sequence's windows found in the other, each window aligned on its own (global offsets, the
    best local fits of its level curve, and the previous window's offset carried forward, each refined by +-2 steps)."""
    if len(a["frames"]) > len(b["frames"]):
        a, b = b, a
    fa, fb = np.asarray(a["frames"], dtype=np.uint64), np.asarray(b["frames"], dtype=np.uint64)
    la, lb = a["level"], b["level"]
    win = min(win, len(fa))
    starts = list(range(0, len(fa) - win + 1, win)) or [0]
    if len(starts) > max_windows:
        starts = [starts[int(i)] for i in np.linspace(0, len(starts) - 1, max_windows)]
    global_lags = _offsets(la, lb)
    pop = (lambda x: _POP16[x.astype(np.int64)]) if bits == 16 else _popcount
    steps = np.arange(-2, 3)
    probe = sorted({starts[int(i)] for i in np.linspace(0, len(starts) - 1, min(6, len(starts)))})
    matched, carried = 0, None
    for n, s in enumerate(probe + [s for s in starts if s not in probe]):
        if n == len(probe) and not matched:
            return 0.0  # six windows spread over the work, none found: different works (most pairs stop here)
        centres = {s - lag for lag in global_lags} | set(_local_starts(la[s:s + win], lb))
        if carried is not None:
            centres.add(carried + s)
        js = np.unique((np.array(sorted(centres))[:, None] + steps).ravel())
        js = js[(js >= 0) & (js <= len(fb) - win)]
        if not len(js):
            continue
        err = pop(fb[js[:, None] + np.arange(win)] ^ fa[s:s + win]).mean(axis=1) / bits
        k = int(np.argmin(err))
        if err[k] <= err_max:
            matched += 1
            carried = int(js[k]) - s
    return matched / len(starts)


def _sequence_verdict(a, b, bits, win, err_max):
    if not a.get("frames") or not b.get("frames") or a.get("step") != b.get("step") or a.get("window") != b.get("window"):
        return None
    share = matched_share(a, b, bits, win, err_max)
    return SAME if share >= .8 else DISTINCT if share <= 1 / 3 else UNSURE


def verdict(a, b):
    """"same", "unsure" or "distinct" when both fingerprints are of one type and version and can tell; else None."""
    if not a or not b or a.get("type") != b.get("type") or a.get("v") != VERSION or b.get("v") != VERSION:
        return None
    kind = a["type"]
    if kind == "text":
        return _text_verdict(a, b)
    if kind == "web":
        return _web_verdict(a, b)
    if kind == "image":
        return _image_verdict(a, b)
    if kind == "audio":
        return _sequence_verdict(a, b, 16, 50, .3)  # 5 s windows; copies 2 % faster still match, other works ~0.45
    if kind == "frames":
        return _sequence_verdict(a, b, 64, 10, .2)
    return None


def same(a, b):
    """True (same or unsure: one work for counting evidence), False (distinct), None (cannot tell)."""
    v = verdict(a, b)
    return None if v is None else v != DISTINCT
