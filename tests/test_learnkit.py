"""learnkit: senses for text, image, audio and web; evidence of success; anatomy; cohort comparison; blueprints."""
import json
import wave
import numpy as np
import pytest
from PIL import Image, ImageDraw
import learnkit.store
from learnkit import api, senses

SCRIPT = """# Stop losing your keys

Do you lose your keys every morning? You are not alone: 3 in 5 people do.

Tag clips on in 2 seconds. Your phone rings it from 30 metres away.

Order today and get 20% off. Try it free for 30 days.
"""

PAGE = """<!doctype html><html lang="en"><head><title>Tag — find your keys</title>
<meta name="description" content="A small tag that finds your keys."><script src="a.js"></script></head>
<body><header><nav><a href="/">Home</a> <a href="/shop">Shop</a></nav></header>
<section class="hero"><h1>Never lose your keys again</h1><p>Clip it on. Ring it from your phone.</p>
<a class="btn" href="/buy">Get yours</a></section>
<section><h2>Trusted by 20,000 customers</h2><blockquote>Five stars, found my keys in seconds.</blockquote>
<img src="a.png"><img src="b.png" alt="tag on keys"></section>
<section><h2>Pricing</h2><p>Only $19 or $29 for two.</p><form><input name="email"><input type="submit" value="Buy now"></form></section>
<footer><p>Contact us</p></footer></body></html>"""


@pytest.fixture
def lab(tmp_path):
    learnkit.store.configure(tmp_path / "learnkit")
    return tmp_path


VOCAB = ("morning door bag wallet light battery map sound small metal quick daily home work car travel friend gift simple "
         "strong water safe pocket key chain clip ring phone signal range tiny loud quiet green blue black white walk park "
         "office school train bus coffee table desk chair window garden street city river weekend holiday family child "
         "dog cat bike run note list plan week month year early late soon often never always every other first last").split()


def prose(seed, words):
    """Distinct, neutral filler (no call to action, proof or price words): each seed is a different text."""
    r = np.random.default_rng(seed + 1000)
    out = []
    while len(out) < words:
        out += [*r.choice(VOCAB, int(r.integers(6, 12))), "."]
    return " ".join(out[:words]).replace(" .", ".") + "."


def make_image(path, focus=(0.7, 0.3), text=True, size=(640, 360)):
    im = Image.new("RGB", size, (24, 30, 46))
    d = ImageDraw.Draw(im)
    x, y = int(focus[0] * size[0]), int(focus[1] * size[1])
    d.ellipse([x - 50, y - 50, x + 50, y + 50], fill=(250, 200, 40))
    if text:
        for k in range(3):
            d.text((30, 220 + 30 * k), "BIG SALE TODAY 50% OFF", fill=(255, 255, 255))
    im.save(path)
    return path


def make_audio(path, bpm=120, seconds=12, quiet_intro=2.0):
    rate = 22050
    t = np.arange(int(seconds * rate)) / rate
    y = np.zeros_like(t)
    for beat in np.arange(quiet_intro, seconds, 60 / bpm):
        i = int(beat * rate)
        y[i:i + 400] += np.hanning(400) * .8
    y += .02 * np.sin(2 * np.pi * 220 * t) * (t > quiet_intro)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return path


def test_text_sense_measures_structure_hook_and_calls_to_action(lab):
    p = lab / "script.md"
    p.write_text(SCRIPT, encoding="utf-8")
    m = senses.for_path(p).measure(p)
    f = senses.numeric(m["features"])
    assert f["headings"] == 1 and f["cta_phrases"] >= 2 and f["question_share"] > 0 and f["second_person_per_100_words"] > 5
    assert f["numbers_per_100_words"] > 5 and len(m["parts"]) == 4
    vi = lab / "vi.txt"
    vi.write_text("Bạn có hay quên chìa khóa không? Đặt ngay hôm nay để nhận ưu đãi.", encoding="utf-8")
    mv = senses.for_path(vi).measure(vi)
    assert "language: vi" in mv["notes"] and senses.numeric(mv["features"])["cta_phrases"] == 1
    srt = lab / "talk.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHello there friends\n\n2\n00:00:12,000 --> 00:00:14,000\nBuy it now\n", encoding="utf-8")
    ms = senses.for_path(srt).measure(srt)
    fs = senses.numeric(ms["features"])
    assert fs["first_words_at_s"] == .5 and fs["longest_pause_s"] == 10 and fs["words_first_10s"] == 3


def test_image_sense_finds_focus_text_and_palette(lab):
    a = make_image(lab / "a.png", focus=(.68, .32))
    m = senses.for_path(a).measure(a)
    f = senses.numeric(m["features"])
    assert abs(f["focus_x"] - .68) < .15 and abs(f["focus_y"] - .32) < .15 and f["focus_to_thirds"] < .15
    assert f["text_like_regions"] > 0 and f["aspect"] == pytest.approx(640 / 360, rel=1e-3)
    assert m["features"]["palette"]["value"][0]["share"] > .5 and m["parts"]
    plain = make_image(lab / "plain.png", text=False)
    assert senses.numeric(senses.for_path(plain).measure(plain)["features"])["text_like_share"] < f["text_like_share"]


def test_audio_sense_hears_tempo_intro_and_sections(lab):
    p = make_audio(lab / "beat.wav", bpm=120, seconds=14, quiet_intro=3.0)
    m = senses.for_path(p).measure(p)
    f = senses.numeric(m["features"])
    assert abs(f["tempo_bpm"] - 120) < 4 and f["intro_s"] >= 2.4 and f["duration_s"] == pytest.approx(14, abs=.1)
    assert f["onsets_per_s"] > 1 and m["parts"]


def test_web_sense_reads_structure_ctas_proof_and_price(lab):
    p = lab / "page.html"
    p.write_text(PAGE, encoding="utf-8")
    m = senses.for_path(p).measure(p)
    f = senses.numeric(m["features"])
    assert f["h1"] == 1 and f["h2"] == 2 and f["cta"] == 2 and f["first_cta_at_share"] < .5
    assert f["price_mentions"] >= 2 and f["social_proof_mentions"] >= 1 and f["forms"] == 1 and f["form_fields"] == 1
    assert f["images_without_alt_share"] == .5 and [x["role_hint"] for x in m["parts"]][:2] == ["header", "hero"]
    shot = make_image(lab / "shot.png", size=(1366, 2400))
    ms = senses.for_path(p).measure(p, {"screenshot": str(shot)})
    assert "fold_contrast" in ms["features"] and senses.numeric(ms["features"])["page_height_screens"] > 3


def cohort(lab, n=10):
    """n landing pages: the better half asks early (CTA in the hero) and shows proof; views vs a 1000 baseline."""
    ids = []
    for i in range(n):
        good = i >= n // 2
        hero = '<section><h1>Fast tags</h1><a class="btn" href="/buy">Buy</a></section>' if good else "<section><h1>Fast tags</h1></section>"
        proof = "<section><h2>Reviews</h2><p>" + "Trusted by customers. " * (3 + i) + "</p></section>"
        filler = "<section><p>" + prose(i, 100 + 35 * i) + "</p></section>"
        body = hero + (proof if good else "") + filler + '<section><a class="btn" href="/buy">Buy</a></section>'
        p = lab / f"page{i}.html"
        p.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
        r = api.learn("register", {"path": str(p), "domain": "gadget landing page"})
        views = (3000 + 200 * i) if good else (600 + 50 * i)
        api.learn("signals", {"exemplar_id": r["id"], "signals": [{"metric": "conversions", "value": views, "baseline": 1000,
                              "baseline_note": "store median monthly conversions", "source": "caller_report"}]})
        api.learn("anatomy", {"exemplar_id": r["id"], "parts": [{"role": "hero", "span": {"section": 0}}]})
        ids.append(r["id"])
    return ids


def export(lab, name, value, usual=(940, 1010, 990, 1060)):
    """An analytics export: the work's month and the store's usual months; the baseline is read from the same file."""
    p = lab / f"{name}.csv"
    p.write_text("month,conversions\n" + "".join(f"2026-0{k + 1},{v}\n" for k, v in enumerate(usual)) + f"launch,{value}\n", encoding="utf-8")
    return {"path": str(p), "metrics": {"conversions": "conversions"}, "row": {"column": "month", "equals": "launch"}, "baseline": "others"}


def launch(lab, name, seed):
    """A new page made by the "ask in the hero, show proof" blueprint: its own words, so a distinct work."""
    p = lab / f"{name}.html"
    p.write_text(f'<html><body><section><h1>{name} tag</h1><a class="btn" href="/b">Buy</a></section><section><p>'
                 + "Trusted by customers. Customer reviews. Rated by users. " * 2 + prose(seed, 90) + "</p></section></body></html>",
                 encoding="utf-8")
    return p


def test_compare_finds_what_winners_share_and_flags_small_samples(lab):
    ids = cohort(lab)
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    diff = {d["feature"]: d for d in c["differences"]}
    assert diff["hero_cta"]["delta"] == 1 and diff["hero_cta"]["magnitude"] == "large"
    assert diff["social_proof_mentions"]["delta"] > .9 and not c["exploratory"] and c["winners"] == c["controls"] == 5
    small = api.learn("compare", {"winners": ids[-2:], "controls": ids[:2]})
    assert small["exploratory"]
    with pytest.raises(ValueError, match="both groups"):
        api.learn("compare", {"winners": ids[:2], "controls": ids[:2]})


def test_blueprints_are_gated_and_conformance_is_measured(lab):
    ids = cohort(lab, 24)  # a rule is judged on the domain's top vs bottom third: 8 vs 8 here
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    bp = {"title": "Ask in the hero", "kind": "web", "domain": "gadget landing page", "purpose": "Turn a visit into a purchase.",
          "structure": [{"role": "hero"}],
          "targets": [{"feature": "hero_cta", "range": [1, 3], "provenance": "comparison", "comparison_id": c["id"]},
                      {"feature": "social_proof_mentions", "range": [3, 50], "provenance": "comparison", "comparison_id": c["id"]}],
          "steps": ["Put the main call to action in the first block.", "Show proof before the details."],
          "when_to_use": "Single-product pages.", "avoid": "Pages whose visitors need to compare first.",
          "exemplars": ids[-5:], "comparisons": [c["id"]]}
    saved = api.learn("distill", {"blueprint": bp})
    assert saved["level"] == "candidate" and saved["eligible_level"] == "rule"
    with pytest.raises(ValueError, match="needs"):
        api.learn("distill", {"blueprint": {**bp, "level": "standard"}, "blueprint_id": saved["id"], "base_revision": 1})
    rule = api.learn("distill", {"blueprint": {**bp, "level": "rule"}, "blueprint_id": saved["id"], "base_revision": 1})
    assert rule["level"] == "rule"
    with pytest.raises(ValueError, match="no cited exemplar"):
        api.learn("distill", {"blueprint": {**bp, "title": "x", "targets": [{"feature": "nonsense", "range": [0, 1], "provenance": "chosen"}]}})
    mine = lab / "mine.html"
    mine.write_text('<html><body><section><h1>Our tag</h1><a class="btn" href="/b">Buy</a></section>'
                    "<section><p>Trusted by customers. Reviews from customers. Rated by users.</p></section></body></html>", encoding="utf-8")
    report = api.learn("conform", {"blueprint_id": saved["id"], "path": str(mine), "anatomy": [{"role": "hero", "span": {"section": 0}}]})
    assert report["conformance"] == 1 and report["structure"][0]["present"] and report["order_ok"]
    weak = api.learn("apply", {"blueprint_id": saved["id"], "path": str(mine), "note": "Launched; numbers pending."})
    assert weak["unverified"]
    for k in range(5):  # five new works, each beating the store's usual month in its own analytics export
        done = api.learn("apply", {"blueprint_id": saved["id"], "path": str(launch(lab, f"launch{k}", 50 + k)), "note": "Ran a month.",
                                   "outcome_csv": export(lab, f"launch{k}", 1500)})
    assert "unverified" not in done and done["trials"] == {"judged": 5, "beat": 5, "p": .0312, "series": 1} and done["eligible_level"] == "standard"
    std = api.learn("distill", {"blueprint": {**bp, "level": "standard"}, "blueprint_id": saved["id"], "base_revision": 2})
    assert std["level"] == "standard"
    lib = api.learn("library", {"query": "hero"})
    assert any(x["type"] == "blueprint" and x["level"] == "standard" for x in lib["items"])


def test_registration_reads_ytdlp_signals_and_attention_and_detects_changes(lab):
    img = make_image(lab / "thumb.png")
    info = {"view_count": 50000, "like_count": 2500, "comment_count": 100, "channel_follower_count": 10000, "upload_date": "20260101",
            "epoch": 1767225600 + 86400 * 50, "extractor_key": "Youtube",
            "heatmap": [{"start_time": 0, "end_time": 5, "value": .2}, {"start_time": 5, "end_time": 10, "value": 1.0}]}
    (lab / "thumb.info.json").write_text(json.dumps(info), encoding="utf-8")
    r = api.learn("register", {"path": str(img), "domain": "youtube thumbnail"})
    assert r["signals"]["views"]["vs_baseline"] == 5 and r["signals"]["views"]["grade"] == "imported"
    assert r["signals"]["views_per_day"]["value"] == pytest.approx(1000, rel=.01) and r["attention_peaks"][0]["t"] == [5, 10]
    ev = api.learn("evidence", {"exemplar_id": r["id"], "span": {"box": [.5, 0, .5, .6]}})
    assert ev["items"][0]["type"] == "image"
    with pytest.raises(ValueError, match="take spans"):
        api.learn("evidence", {"exemplar_id": r["id"], "span": {"t": [0, 1]}})
    img.write_bytes(img.read_bytes() + b"x")
    with pytest.raises(ValueError, match="changed"):
        api.learn("evidence", {"exemplar_id": r["id"], "span": {"box": [0, 0, .5, .5]}})
    assert "loop" in api.learn()
    import subprocess
    import sys
    from pathlib import Path
    probe = "import sys, learnkit.api; learnkit.api.learn(); print(sorted(m for m in sys.modules if m.startswith('editvideo')))"
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == "[]"  # the core imports no host package
