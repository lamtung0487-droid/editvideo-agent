"""learnkit content fingerprints: copies, edits, trims, re-encodes and excerpts are one work; template siblings and episodes are not."""
import io
import subprocess
import wave
import numpy as np
import pytest
from PIL import Image, ImageDraw
import learnkit.store
from learnkit import api, core, fingerprint as fp, senses
from learnkit.senses.audio import ffmpeg
from test_learnkit import prose

R = 22050


@pytest.fixture
def lab(tmp_path):
    learnkit.store.configure(tmp_path / "learnkit")
    return tmp_path


def test_text_copies_edits_and_excerpts_are_one_work_but_template_siblings_are_not():
    boiler = prose(900, 60)  # the same intro and sign-off on every document of a series
    docs = [fp.text(boiler + " " + prose(i, 160) + " " + boiler) for i in range(20)]
    assert sum(fp.verdict(docs[i], docs[j]) != "distinct" for i in range(20) for j in range(i + 1, 20)) == 0
    body = prose(3, 300)
    base, w = fp.text(body), body.split(" ")
    assert fp.verdict(base, fp.text(body + "   \n")) == "same"
    assert fp.verdict(base, fp.text(body + " " + prose(77, 30))) == "same"  # 10 % padding
    assert fp.verdict(base, fp.text(" ".join(w[60:240]))) == "same"  # an excerpt is part of the same work
    assert fp.verdict(fp.text(" ".join(w[:150])), fp.text(" ".join(w[150:]))) == "distinct"  # two halves are not each other
    for k in (10, 20, 40):  # light edits (a word in k pluralised) are unsure, and count as the same work
        assert fp.same(base, fp.text(" ".join(x + "s" if i % k == 0 else x for i, x in enumerate(w)))), k
    for disguise in (body.replace("o", "o\u200b"), body.replace("o", "\u043e"), body.upper(), body.replace("o", "o\ufe0e"),
                     body.replace("o", "o\u034f"), body.replace(" ", " \u3164"), body.replace("o", "\u0585"), body.replace("e", "\u1d07")):
        # invisible marks, variation selectors, a blank letter, Cyrillic/Armenian look-alikes, small capitals, case
        assert fp.verdict(base, fp.text(disguise)) == "same"
    assert fp.verdict(fp.text(""), fp.text("!!! ...")) is None  # nothing to compare


def test_web_fingerprint_reads_the_page_not_the_site_chrome(tmp_path):
    chrome = "<header><nav><a href='/'>Home</a> " + prose(901, 40) + "</nav></header>"
    foot = "<footer><p>" + prose(902, 60) + "</p></footer>"

    def page(name, body, head=chrome, tail=foot):
        path = tmp_path / name
        path.write_text(f"<html><body>{head}<section><h1>Title</h1><p>{body}</p></section>{tail}</body></html>", encoding="utf-8")
        return senses.get("web").fingerprint(path)
    a = page("a.html", prose(1, 200))
    bare = lambda name, app: (tmp_path / name).write_text(f"<html><body><div id='{app}'></div><script src='{app}.js'></script></body></html>",
                                                           encoding="utf-8") and tmp_path / name
    assert fp.verdict(senses.get("web").fingerprint(bare("e1.html", "a")), senses.get("web").fingerprint(bare("e2.html", "b"))) is None
    # pages that render in the browser (no text in the file): nothing to compare
    assert not fp.same(a, page("b.html", prose(2, 200)))  # one site, two pages
    menu = "<div class='site-menu'>" + prose(904, 140) + "</div>"
    foot2 = "<div id='site-footer'>" + prose(905, 140) + "</div>"
    own = [page(f"d{k}.html", prose(10 + k, 80), head=menu, tail=foot2) for k in range(4)]  # chrome built from divs
    assert all(fp.verdict(own[i], own[j]) == "distinct" for i in range(4) for j in range(i + 1, 4))
    wrapped = tmp_path / "wrapped.html"  # the whole page inside an element named like furniture is still the page
    wrapped.write_text(f"<html><body class='has-sidebar footer-top-visible'><div class='menu-wrap'>{chrome}<section><h1>Title</h1>"
                       f"<p>{prose(1, 200)} One more sentence.</p></section>{foot}</div></body></html>", encoding="utf-8")
    assert fp.verdict(a, senses.get("web").fingerprint(wrapped)) == "same"
    assert fp.same(a, page("c.html", prose(1, 200), head="<header><nav>" + prose(903, 30) + "</nav></header>", tail=""))  # redesigned chrome


def series_image(seed, size=(480, 320)):
    r = np.random.default_rng(seed)
    im = Image.new("RGB", size, (30, 34, 48))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size[0], 40], fill=(200, 40, 60))  # the same banner on every image of the series
    d.text((12, 12), "WEEKLY DEAL", fill=(255, 255, 255))
    for _ in range(8):
        x, y = int(r.integers(0, size[0])), int(r.integers(50, size[1]))
        s = int(r.integers(20, 110))
        color = tuple(int(c) for c in r.integers(40, 255, 3))
        (d.ellipse if r.random() < .5 else d.rectangle)([x - s, y - s, x + s, y + s], fill=color)
    return im


def test_image_reencodes_crops_flips_and_borders_are_one_work_but_a_series_is_not():
    ims = [series_image(s) for s in range(20)]
    fps = [fp.image(np.asarray(im)) for im in ims]
    assert sum(fp.verdict(fps[i], fps[j]) != "distinct" for i in range(20) for j in range(i + 1, 20)) == 0
    for size in ((1, 1), (2, 2), (400, 1), (4000, 20)):  # plain images of any shape: no crash, no verdict
        assert fp.image(np.full((size[1], size[0], 3), 120, np.uint8)).get("flat")
    for k, im in enumerate(ims[:5]):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=55)
        jpeg = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        w, h = im.size
        crop = im.crop((int(.04 * w), int(.04 * h), int(.96 * w), int(.96 * h)))
        border = Image.new("RGB", (w + 24, h + 24), (255, 255, 255))
        border.paste(im, (12, 12))
        small = im.resize((w // 2, h // 2))
        side = min(w, h)
        square = im.crop(((w - side) // 2, 0, (w - side) // 2 + side, side)).resize((300, 300))
        for variant in (jpeg, crop, border, small, im.transpose(Image.FLIP_LEFT_RIGHT), square):
            assert fp.same(fps[k], fp.image(np.asarray(variant))), k


def dense(seed, seconds=30):
    r = np.random.default_rng(seed)
    y = np.zeros(int(seconds * R))
    for k in range(int(seconds * 4)):
        i = int(k * .25 * R)
        n = min(int(.5 * R), len(y) - i)
        chord = r.choice([196, 220, 247, 262, 294, 330, 349, 392, 440, 494, 523], 3, replace=False)
        t = np.arange(n) / R
        y[i:i + n] += .08 * sum(np.sin(2 * np.pi * f * t) + .5 * np.sin(4 * np.pi * f * t) for f in chord) * np.exp(-t * 3)
        if k % 2 == 0:
            m = min(1000, len(y) - i)
            y[i:i + m] += .2 * r.standard_normal(m) * np.exp(-np.arange(m) / 150)
    return y


def speech(seed, seconds=30):
    """Syllable-like bursts of a gliding harmonic voice with pauses: sparse, like a talk."""
    r = np.random.default_rng(seed)
    y, t0 = np.zeros(int(seconds * R)), 0.0
    while t0 < seconds - 1:
        dur = r.uniform(.12, .35)
        n, i, f0 = int(dur * R), int(t0 * R), r.uniform(110, 220)
        t = np.arange(n) / R
        ph = 2 * np.pi * np.cumsum(f0 * (1 + .15 * np.sin(np.pi * t / dur))) / R
        y[i:i + n] += .15 * sum(np.sin(h * ph) / h for h in range(1, 12)) * np.sin(np.pi * t / dur) ** 2
        t0 += dur + (r.uniform(.4, 1.0) if r.random() < .15 else r.uniform(.03, .1))
    return y


def write_wav(path, y):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(R)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return path


@pytest.mark.parametrize("make", [dense, speech])
def test_audio_copies_trims_noise_and_excerpts_are_one_work_but_episodes_are_not(tmp_path, make):
    works = [make(s, 40) for s in range(4)]
    F = lambda y: fp.audio(y, R)
    f0 = F(works[0])
    rms = np.sqrt(np.mean(works[0] ** 2))
    copies = {"trim off the step grid": works[0][int(.05 * R):], "trim 1.23 s": works[0][int(1.234 * R):],
              "gain -10 dB": works[0] * .316, "noise at 10 dB SNR": works[0] + rms / 10 ** .5 * np.random.default_rng(1).standard_normal(len(works[0])),
              "30 s excerpt": works[0][int(5 * R):int(35 * R)], "5 s excerpt": works[0][int(10 * R):int(15 * R)],
              "2 % faster": np.interp(np.arange(0, len(works[0]) - 1, 1.02), np.arange(len(works[0])), works[0])}
    for name, y in copies.items():
        assert fp.verdict(f0, F(y)) == "same", name
    assert all(fp.verdict(f0, F(w)) == "distinct" for w in works[1:])
    intro = works[0][:int(8 * R)]
    assert fp.verdict(F(np.r_[intro, works[1][int(8 * R):]]), F(np.r_[intro, works[2][int(8 * R):]])) == "distinct"  # a shared intro
    half = works[0][:int(20 * R)]
    assert fp.verdict(F(np.r_[half, works[1][int(20 * R):]]), F(np.r_[half, works[2][int(20 * R):]])) == "unsure"  # half shared
    clip = works[3][int(3 * R):int(5 * R)]  # a 2 s sound logo and a noisy copy of it
    assert fp.verdict(F(clip), F(clip + .002 * np.random.default_rng(2).standard_normal(len(clip)))) == "same"
    assert fp.audio(np.zeros(R * 5), R)["frames"] == [] and fp.verdict(fp.audio(np.zeros(R * 5), R), fp.audio(np.zeros(R * 9), R)) is None
    src = write_wav(tmp_path / "a.wav", works[0])
    out = tmp_path / "a.m4a"
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "96k", str(out)], check=True)
    sense = senses.get("audio")
    assert fp.same(sense.fingerprint(src), sense.fingerprint(out))  # through the sense: decode, re-encode, resample


def lavfi(path, source, seconds=12):
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", source, "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_video_frames_survive_reencodes_trims_and_rescaling_but_tell_videos_apart(tmp_path):
    src = lavfi(tmp_path / "a.mp4", "life=s=320x240:rate=25:seed=7:mold=10")
    F = lambda p: fp.video_file(p, ffmpeg())
    a = F(src)
    copy = tmp_path / "a_small.mp4"
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-ss", "1.3", "-i", str(src), "-vf", "scale=160:120", "-b:v", "150k", str(copy)], check=True)
    assert fp.verdict(a, F(copy)) == "same"
    others = [F(lavfi(tmp_path / f"o{k}.mp4", f"life=s=320x240:rate=25:seed={k}:mold=10")) for k in (1, 2)]
    assert all(fp.verdict(a, o) == "distinct" for o in others)
    still = F(lavfi(tmp_path / "still.mp4", "color=c=gray:s=320x240:rate=25", 6))
    assert still["frames"] == [] and fp.verdict(still, a) is None  # one still frame throughout: nothing to compare


def test_same_work_uses_content_then_falls_back_to_measurements_and_clusters_transitively(lab):
    body = prose(5, 400)
    paths = []
    for k, text in enumerate((body, body + " " + prose(6, 40), body + " " + prose(6, 40) + " " + prose(7, 40), prose(8, 400))):
        p = lab / f"t{k}.md"
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    ids = [api.learn("register", {"path": str(p), "domain": "essay"})["id"] for p in paths]
    groups = sorted(sorted(e["id"] for e in g) for g in core.clusters([core.load(i) for i in ids]))
    assert groups == sorted([sorted(ids[:3]), [ids[3]]])  # a copy of a copy joins; a different essay stays apart
    v = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 5.0}
    assert core.same_content("x", None, v, "y", None, dict(v)) is True  # no fingerprint: the measurements decide
    assert core.same_content("x", fp.text("one one one"), v, "y", fp.text("two two two"), dict(v)) is False  # content beats look-alike numbers
