"""learnkit regressions from independent review: evidence gates, part geometry, cache keys and sense edge cases."""
import json
import math
import time
import unicodedata
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw
import learnkit.store
from learnkit import api, senses
from test_learnkit import cohort, export, launch, make_audio, make_image, prose


@pytest.fixture
def lab(tmp_path):
    learnkit.store.configure(tmp_path / "learnkit")
    return tmp_path


def blueprint(ids, cmp_id, **over):
    return {"title": "Ask in the hero", "kind": "web", "domain": "gadget landing page", "purpose": "Turn a visit into a purchase.",
            "structure": [{"role": "hero"}],
            "targets": [{"feature": "hero_cta", "range": [1, 3], "provenance": "comparison", "comparison_id": cmp_id},
                        {"feature": "social_proof_mentions", "range": [3, 50], "provenance": "comparison", "comparison_id": cmp_id}],
            "steps": ["Put the main call to action in the hero."], "when_to_use": "Single-product pages.", "avoid": "Comparison shopping.",
            "exemplars": ids, "comparisons": [cmp_id], **over}


def test_gates_need_distinct_successful_separated_evidence(lab):
    ids = cohort(lab)
    with pytest.raises(ValueError, match="twice"):
        api.learn("compare", {"winners": [ids[-1]] * 5, "controls": ids[:5]})
    good = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    assert good["separated_on"]["metric"] == "conversions"
    with pytest.raises(ValueError, match="twice"):
        api.learn("distill", {"blueprint": blueprint([ids[-1]] * 3, good["id"])})
    # Flops (below their baseline) are not evidence of success, however many are cited.
    flops = api.learn("distill", {"blueprint": blueprint(ids[:5], good["id"], title="Flops")})
    assert flops["level"] == "observation" and "above its baseline" in flops["next_level"]["needs"][0]
    # Explicit groups that are not separated on success cannot back a rule.
    mixed = api.learn("compare", {"winners": ids[-5:-2] + ids[:2], "controls": ids[2:5] + ids[-2:], "metric": "conversions"})
    assert mixed["separated_on"] is None and any("cannot back a rule" in c for c in mixed["confounders"])
    weak = api.learn("distill", {"blueprint": blueprint(ids[-5:], mixed["id"], title="Mixed")})
    assert weak["eligible_level"] == "observation" and "not grounded" in weak["next_level"]["needs"][0]  # no difference there
    # A split that would cut through tied values is refused.
    for i in ids[3:7]:
        api.learn("signals", {"exemplar_id": i, "signals": [{"metric": "tied", "value": 2, "baseline": 1, "baseline_note": "x"}]})
    with pytest.raises(ValueError, match="tie"):
        api.learn("compare", {"exemplars": ids[3:7], "split": {"metric": "tied", "top": .5, "bottom": .5}})


def test_applications_must_be_new_current_and_active(lab):
    ids = cohort(lab, 24)
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    bp = blueprint(ids[-5:], c["id"])
    saved = api.learn("distill", {"blueprint": bp})
    win = {"metric": "conversions", "value": 5000, "baseline": 1000, "baseline_note": "store median"}
    own = learnkit.core.load(ids[-1])["source"]["path"]
    copy = lab / "copy.html"
    copy.write_bytes(open(own, "rb").read() + b"\n")  # one byte more, same page
    for path in (own, copy):
        r = api.learn("apply", {"blueprint_id": saved["id"], "path": str(path), "outcome": [win], "note": "self test"})
        assert r["recorded"]["duplicate_of"] == ids[-1] and r["unverified"]
    fresh = [launch(lab, f"new{k}", 70 + k) for k in range(8)]
    # Losses count: 2 wins in 6 tries is what chance gives.
    for k, value in enumerate((5000, 700, 820, 4000, 650, 900)):
        r = api.learn("apply", {"blueprint_id": saved["id"], "path": str(fresh[k]), "note": "real launch",
                                "outcome": [{**win, "value": value}]})
    assert r["trials"] == {"judged": 6, "beat": 2, "p": .8906, "series": 1} and r["eligible_level"] == "rule"
    # A loss stays a loss: reporting the work again, withdrawing it or editing a target's note does not remove it.
    for k in range(1, 6):
        api.learn("apply", {"blueprint_id": saved["id"], "path": str(fresh[k]), "outcome": [win], "kept": False, "note": "again"})
    noted = {**bp, "targets": [{**bp["targets"][0], "note": "edited"}] + bp["targets"][1:]}
    r = api.learn("distill", {"blueprint": noted, "blueprint_id": saved["id"], "base_revision": 1})
    assert r["trials"] == {"judged": 6, "beat": 2, "p": .8906, "series": 1}
    for k in (6, 7):
        r = api.learn("apply", {"blueprint_id": saved["id"], "path": str(fresh[k]), "outcome": [win], "note": "real launch"})
    assert r["trials"]["beat"] == 4 and r["eligible_level"] == "rule" and r["outcomes_reported_by_caller"] == 10
    # Starting over is a new series of trials, and every series shares the .05: now 2 series, so .025 each.
    again = {**bp, "title": "Ask in the hero, second try"}
    second = api.learn("distill", {"blueprint": again})["id"]
    pages = [launch(lab, f"try{k}", 90 + k) for k in range(8)]
    for k in range(5):
        r = api.learn("apply", {"blueprint_id": second, "path": str(pages[k]), "outcome": [win], "note": "launch"})
    assert r["trials"] == {"judged": 5, "beat": 5, "p": .0312, "series": 2}  # 5 of 5 is not enough at .025
    typed = {**export(lab, "typed", 3900), "baselines": {"conversions": {"baseline": 1000, "baseline_note": "typed"}}}
    typed.pop("baseline")
    r = api.learn("apply", {"blueprint_id": second, "path": str(pages[5]), "note": "export, typed baseline", "outcome_csv": typed})
    assert r["trials"]["p"] < .025 and r["eligible_level"] == "rule"  # a file whose baseline the caller typed is still typed
    with pytest.raises(ValueError, match="read from a file"):
        api.learn("distill", {"blueprint": {**again, "level": "standard"}, "blueprint_id": second, "base_revision": 1})
    r = api.learn("apply", {"blueprint_id": second, "path": str(pages[6]), "note": "the month's export", "outcome_csv": export(lab, "two", 3900)})
    assert r["verified_works"] == 7 and r["eligible_level"] == "standard"
    with pytest.raises(ValueError, match="other rows"):
        api.learn("apply", {"blueprint_id": second, "path": str(pages[7]), "note": "x", "outcome_csv": export(lab, "short", 3900, usual=(900,))})
    # Changing the targets voids applications measured against the old ones.
    changed = {**bp, "targets": bp["targets"][:1]}
    after = api.learn("distill", {"blueprint": changed, "blueprint_id": saved["id"], "base_revision": 2})
    assert after["verified_works"] == 0 and after["trials"]["judged"] == 0 and after["eligible_level"] == "rule"
    retired = api.learn("distill", {"blueprint": {**changed, "state": "retired"}, "blueprint_id": saved["id"], "base_revision": 3})
    assert retired["level"] is None and retired["state"] == "retired"
    with pytest.raises(ValueError, match="retired"):
        api.learn("apply", {"blueprint_id": saved["id"], "path": str(fresh[0]), "outcome": [win], "note": "again"})


def test_part_geometry_is_bounded_ordered_and_per_kind(lab):
    body = "Hook line here.\n\nThe middle part of the script.\n\nBuy it now."
    text = lab / "s.md"
    text.write_text(body, encoding="utf-8")  # CRLF on Windows: spans still count one character per newline
    cta = body.index("Buy")
    r = api.learn("register", {"path": str(text), "domain": "ad script"})
    parts = api.learn("anatomy", {"exemplar_id": r["id"], "parts": [{"role": "cta", "span": {"chars": [cta, len(body)]}},
                                                                   {"role": "hook", "span": {"chars": [0, 15]}}]})["parts"]
    assert [p["role"] for p in parts] == ["hook", "cta"] and parts[0]["share"] == round(15 / len(body), 4)
    with pytest.raises(ValueError, match="ends after"):
        api.learn("anatomy", {"exemplar_id": r["id"], "parts": [{"role": "hook", "span": {"chars": [0, 999]}}]})
    bp = api.learn("distill", {"blueprint": {"title": "Hook first", "kind": "text", "domain": "ad script", "purpose": "Sell.",
                                             "structure": [{"role": "hook"}, {"role": "cta"}],
                                             "targets": [{"feature": "role_share_hook", "range": [.1, .4], "provenance": "chosen"}],
                                             "steps": ["Open with the hook."], "when_to_use": "Ads.", "avoid": "Essays.", "exemplars": [r["id"]]}})
    report = api.learn("conform", {"blueprint_id": bp["id"], "path": str(text),
                                   "anatomy": [{"role": "cta", "span": {"chars": [0, 15]}}, {"role": "hook", "span": {"chars": [cta, len(body)]}}]})
    assert report["order_ok"] is False  # order is read from the work, not from the order of the list
    audio = make_audio(lab / "a.wav", seconds=6)
    ra = api.learn("register", {"path": str(audio), "domain": "jingle"})
    with pytest.raises(ValueError, match="ends after"):
        api.learn("anatomy", {"exemplar_id": ra["id"], "parts": [{"role": "intro", "span": {"t": [0, 999]}}]})
    page = lab / "p.html"
    page.write_text("<html><body><section><h1>Big</h1><p>one two three four</p></section><section><p>five six</p></section></body></html>",
                    encoding="utf-8")
    rp = api.learn("register", {"path": str(page), "domain": "page"})
    sec = api.learn("anatomy", {"exemplar_id": rp["id"], "parts": [{"role": "body", "span": {"section": 1}}]})["parts"][0]
    assert sec["share"] == round(2 / 7, 4) and sec["start_share"] == round(5 / 7, 4)


def test_measurements_follow_kind_and_options(lab):
    page = lab / "p.html"
    page.write_text("<html><body><section><h1>Hi</h1><a class='btn' href='/b'>Buy</a></section></body></html>", encoding="utf-8")
    as_text = api.learn("register", {"path": str(page), "kind": "text", "domain": "page"})
    assert "cta" not in as_text["features"]
    as_web = api.learn("register", {"path": str(page), "kind": "web", "domain": "page", "usage": "client's own page"})
    assert as_web["features"]["cta"] == 1 and as_web["kind"] == "web"
    shot = make_image(lab / "shot.png", size=(1366, 2000))
    again = api.learn("register", {"path": str(page), "domain": "page", "options": {"screenshot": str(shot)}})
    assert "fold_contrast" in again["features"] or again["features_total"] > as_web["features_total"]
    item = api.learn("library", {"item_id": as_web["id"]})["item"]
    assert item["usage"] == "client's own page"  # kept when a later registration does not restate it
    with pytest.raises(ValueError, match="no such file"):
        api.learn("register", {"path": str(page), "domain": "page", "options": {"screenshot": str(lab / "missing.png")}})
    with pytest.raises(ValueError, match="Unknown item"):
        api.learn("library", {"item_id": "ex-0123456789abcdef"})
    with pytest.raises(ValueError, match="offset"):
        api.learn("library", {"offset": -1})


def test_web_counts_real_asks_and_finds_the_hero(lab):
    page = lab / "w.html"
    page.write_text("""<html lang="vi"><body><header><nav><a href="/">Trang chủ</a><button class="menu-toggle">Menu</button></nav>
        <button id="cookie-accept">OK</button></header>
        <section><h1>Tai nghe mới</h1><p>Âm thanh rõ.</p><a href="/mua"><span>Mua ngay</span></a></section>
        <section><p>Giá chỉ 1.290.000 ₫. Hơn 2.000 khách hàng tin dùng.</p></section></body></html>""", encoding="utf-8")
    f = senses.numeric(senses.for_path(page).measure(page)["features"])
    assert f["cta"] == 1 and f["hero_cta"] == 1 and f["hero_index"] == 1 and f["price_mentions"] >= 1 and f["social_proof_mentions"] >= 2
    deep = lab / "deep.html"
    deep.write_text("<html><body>" + "<div>" * 20000 + "x" + "</div>" * 20000 + "</body></html>", encoding="utf-8")
    t0 = time.perf_counter()
    senses.for_path(deep).measure(deep)
    assert time.perf_counter() - t0 < 2.5


def test_images_of_any_mode_and_size(lab):
    tiny = make_image(lab / "tiny.png", size=(10, 10), text=False)
    f = senses.numeric(senses.for_path(tiny).measure(tiny)["features"])
    assert "empty_space_share" not in f and f["width_px"] == 10
    rgba = Image.new("RGBA", (200, 100), (255, 255, 255, 0))
    ImageDraw.Draw(rgba).rectangle([20, 20, 60, 60], fill=(200, 20, 20, 255))
    rgba.save(lab / "logo.png")
    fl = senses.numeric(senses.for_path(lab / "logo.png").measure(lab / "logo.png")["features"])
    assert fl["transparent_share"] > .8 and .3 < fl["luminance_mean"] < .6  # shown over grey, not its hidden white
    grad = Image.fromarray((np.tile(np.linspace(0, 65535, 256), (64, 1))).astype(np.uint16))
    grad.save(lab / "grad.png")
    fg = senses.numeric(senses.for_path(lab / "grad.png").measure(lab / "grad.png")["features"])
    assert .4 < fg["luminance_mean"] < .6
    rng = np.random.default_rng(3)
    misses = 0
    for i in range(30):
        W, H = 640, 360
        im = Image.new("RGB", (W, H), (30, 30, 40))
        w, h = (60, 60) if i % 2 else (140, 45)
        x, y = int(rng.integers(0, W - w)), int(rng.integers(0, H - h))
        ImageDraw.Draw(im).rectangle([x, y, x + w, y + h], fill=(240, 220, 60))
        im.save(lab / "shape.png")
        fs = senses.numeric(senses.for_path(lab / "shape.png").measure(lab / "shape.png")["features"])
        misses += math.hypot(fs["focus_x"] - (x + w / 2) / W, fs["focus_y"] - (y + h / 2) / H) > .15
    assert misses <= 1


def test_text_normalises_vietnamese_reads_utf16_and_counts_only_asks(lab):
    nfc = "Bạn hãy đăng ký ngay hôm nay. Bạn sẽ nhận quà."
    a, b = lab / "nfc.txt", lab / "nfd.txt"
    a.write_text(nfc, encoding="utf-8")
    b.write_text(unicodedata.normalize("NFD", nfc), encoding="utf-8")
    fa, fb = (senses.numeric(senses.for_path(p).measure(p)["features"]) for p in (a, b))
    assert fa == fb and fa["cta_phrases"] == 1 and fa["second_person_per_100_words"] > 0
    story = lab / "story.txt"
    story.write_text("They start the film and call it a day, then share it with friends who join the club.", encoding="utf-8")
    assert senses.numeric(senses.for_path(story).measure(story)["features"])["cta_phrases"] == 0
    srt = lab / "u16.srt"
    srt.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nXin chào các bạn\n".encode("utf-16"))
    assert senses.numeric(senses.for_path(srt).measure(srt)["features"])["words"] == 4


def test_signals_refuse_ambiguous_numbers_and_skip_bad_metadata(lab):
    img = make_image(lab / "t.png")
    (lab / "t.info.json").write_text(json.dumps({"view_count": "lots", "like_count": True, "comment_count": 5, "epoch": "x"}), encoding="utf-8")
    r = api.learn("register", {"path": str(img), "domain": "thumbnail"})
    assert set(r["signals"]) == {"comments"}
    csv = lab / "export.csv"
    csv.write_text("Video,Views,CTR\nA,\"1.234\",\"4,5%\"\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguous"):
        api.learn("signals", {"exemplar_id": r["id"], "csv": {"path": str(csv), "metrics": {"views": "Views"}}})
    out = api.learn("signals", {"exemplar_id": r["id"], "csv": {"path": str(csv), "metrics": {"views": "Views", "ctr": "CTR"}, "decimal": ","}})
    assert out["signals"]["views"]["value"] == 1234 and out["signals"]["ctr"]["value"] == 4.5


def test_audio_evidence_reaches_the_caller_as_audio(lab, monkeypatch, tmp_path):
    from editvideo import mcp_server as m, store
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    p = make_audio(tmp_path / "jingle.wav", seconds=6)
    r = json.loads(m.editvideo_learn("register", {"path": str(p), "domain": "jingle"})[0].text)
    blocks = m.editvideo_learn("evidence", {"exemplar_id": r["id"], "span": {"t": [1, 4]}})
    assert blocks[1].type == "audio" and blocks[1].mimeType == "audio/wav"
    tempo = senses.numeric(senses.for_path(make_audio(tmp_path / "f140.wav", bpm=140, seconds=16)).measure(tmp_path / "f140.wav")["features"])
    assert abs(tempo["tempo_bpm"] - 140) < 4 and abs(tempo["tempo_half_bpm"] - 70) < 2


def page(path, words, proof=0, cta=True, extra="", seed=0):
    hero = '<section><h1>Tag</h1><a class="btn" href="/b">Buy</a></section>' if cta else "<section><h1>Tag</h1></section>"
    body = hero + "<section><p>" + "Trusted by customers. " * proof + prose(seed, 2 * words) + "</p></section>" + extra
    path.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    return path


def test_near_copies_count_once_everywhere(lab):
    good = [page(lab / f"good{s}.html", 60, proof=6, seed=s) for s in (1, 11, 21)]
    bad = [page(lab / f"bad{s}.html", 20, cta=False, seed=s) for s in (2, 12, 22)]
    ids = {"w": [], "c": []}
    for side, sources, value in (("w", good, 5000), ("c", bad, 300)):
        for n, src in enumerate(sources):
            for k in range(2):
                copy = lab / f"{side}{n}-{k}.html"
                copy.write_text(src.read_text(encoding="utf-8") + " " * (k + 1), encoding="utf-8")  # trailing spaces only
                r = api.learn("register", {"path": str(copy), "domain": "page"})
                api.learn("signals", {"exemplar_id": r["id"], "signals": [{"metric": "sales", "value": value + 10 * n + k, "baseline": 1000,
                                                                            "baseline_note": "median"}]})
                api.learn("anatomy", {"exemplar_id": r["id"], "parts": [{"role": "hero", "span": {"section": 0}}]})
                ids[side].append(r["id"])
    c = api.learn("compare", {"winners": ids["w"], "controls": ids["c"], "metric": "sales"})
    assert c["distinct"] == {"winners": 3, "controls": 3} and c["exploratory"]
    rows = learnkit.store.read(learnkit.store.path_for(c["id"]))["features"]
    assert rows and all(r["n_winners"] <= 3 and r["n_controls"] <= 3 for r in rows)  # statistics on distinct works, not copies
    assert api.learn("distill", {"blueprint": blueprint(ids["w"], c["id"])})["eligible_level"] == "candidate"
    saved = api.learn("distill", {"blueprint": blueprint(ids["w"][:2], c["id"], title="one work twice")})
    assert saved["eligible_level"] == "observation" and "1 so far" in saved["next_level"]["needs"][0]
    # A work whose copies sit on both sides is left out of both, and said so.
    mixed = api.learn("compare", {"winners": ids["w"][:4] + ids["c"][:1], "controls": ids["c"][1:], "metric": "sales"})
    assert mixed["distinct"] == {"winners": 2, "controls": 2} and any("left out" in x for x in mixed["confounders"])
    with pytest.raises(ValueError, match="distinct"):
        api.learn("compare", {"winners": ids["w"][:2], "controls": [ids["w"][2], ids["c"][0], ids["c"][1]]})
    win = {"metric": "sales", "value": 4000, "baseline": 1000, "baseline_note": "median"}
    mine = page(lab / "mine.html", 45, proof=5, seed=3)
    first = api.learn("apply", {"blueprint_id": saved["id"], "path": str(mine), "outcome": [win], "note": "launch"})
    assert first["recorded"]["duplicate_of"] is None
    resaved = lab / "mine-again.html"
    resaved.write_bytes(mine.read_bytes() + b" ")
    again = api.learn("apply", {"blueprint_id": saved["id"], "path": str(resaved), "outcome": [win], "note": "same page re-saved"})
    assert again["recorded"]["duplicate_of"] == str(mine.resolve()) and again["verified_works"] <= 1
    one_word = lab / "good-plus.html"
    one_word.write_text(good[0].read_text(encoding="utf-8").replace("</p>", " today</p>", 1), encoding="utf-8")
    assert api.learn("apply", {"blueprint_id": saved["id"], "path": str(one_word), "outcome": [win], "note": "x"})["recorded"]["duplicate_of"]
    # Changing what is measured but not what the work says (a dozen extra images) does not make it a new work.
    decorated = lab / "good-decorated.html"
    decorated.write_text(good[1].read_text(encoding="utf-8").replace("</body>", "<section>" + "<img src='x.png'>" * 12 + "</section></body>"),
                         encoding="utf-8")
    assert api.learn("apply", {"blueprint_id": saved["id"], "path": str(decorated), "outcome": [win], "note": "x"})["recorded"]["duplicate_of"]


def test_rules_need_relative_live_separation_and_ranges_that_exclude_controls(lab):
    ids = cohort(lab, 24)
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    wide = blueprint(ids[-5:], c["id"], targets=[{"feature": "hero_cta", "range": [-1e9, 1e9], "provenance": "comparison", "comparison_id": c["id"]}])
    assert api.learn("distill", {"blueprint": wide})["eligible_level"] == "observation"  # the range also holds the controls
    with pytest.raises(ValueError, match="twice"):
        api.learn("distill", {"blueprint": blueprint(ids[-5:], c["id"], title="dup", targets=[wide["targets"][0]] * 2)})
    raw = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "relative": False, "top": .5, "bottom": .5}})
    assert any("raw metric" in x for x in raw["confounders"])
    assert api.learn("distill", {"blueprint": blueprint(ids[-5:], raw["id"], title="raw")})["eligible_level"] == "candidate"
    good = api.learn("distill", {"blueprint": blueprint(ids[-5:], c["id"], title="good")})
    assert good["eligible_level"] == "rule"
    for i in ids[:5]:  # the controls' evidence is corrected: they did better than the winners after all
        api.learn("signals", {"exemplar_id": i, "signals": [{"metric": "conversions", "value": 99000, "baseline": 1000, "baseline_note": "store median"}]})
    assert api.learn("library", {"item_id": good["id"]})["eligible_level"] == "candidate"


def test_conform_counts_unmeasured_targets_and_outcomes_use_the_success_metric(lab):
    ids = cohort(lab)
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    bp = blueprint(ids[-5:], c["id"], targets=blueprint(ids, c["id"])["targets"] + [
        {"feature": "role_share_hero", "range": [0, .5], "provenance": "chosen"}])
    saved = api.learn("distill", {"blueprint": bp})
    mine = page(lab / "mine.html", 30, proof=5, seed=4)
    report = api.learn("conform", {"blueprint_id": saved["id"], "path": str(mine)})
    assert report["unmeasured"] == ["role_share_hero"] and report["conformance"] == round(2 / 3, 3)
    other = api.learn("apply", {"blueprint_id": saved["id"], "path": str(mine), "note": "x", "anatomy": [{"role": "hero", "span": {"section": 0}}],
                                "outcome": [{"metric": "smiles", "value": 5, "baseline": 1e-12, "baseline_note": "invented"}]})
    assert other["recorded"]["beat_baseline"] is False and "judged on ['conversions']" in other["outcome_note"]


def test_web_hero_and_asks_on_common_layouts(lab):
    cases = {
        "no_h1": ("<header><nav><a href='/'>Home</a></nav></header><div class='hero'><p>Keys found in seconds, every time.</p>"
                  "<a class='btn' href='/b'>Buy now</a></div><footer><p>Contact</p></footer>", {"hero_cta": 1}),
        "logo_h1": ("<header><h1>Brand</h1><nav><a href='/a'>About</a></nav></header><section><h2>Find your keys</h2><p>Small tag, big help.</p>"
                    "<a class='btn' href='/b'>Get one</a></section>", {"hero_cta": 1}),
        "tagline": ("<section><h1>Find keys</h1><h2>Ring them from your phone</h2><a class='btn' href='/b'>Buy</a></section>"
                    "<section><h2>FAQ</h2><button class='accordion' aria-expanded='false'>How?</button>"
                    "<button class='carousel-next'>Next</button><button class='qty-plus'>+</button></section>", {"hero_cta": 1, "cta": 1}),
        "navbar": ("<header><nav><a href='/p'>Pricing</a><a href='/s'>Get started</a></nav></header><section><h1>Ship faster</h1></section>"
                   "<footer><a href='/jobs'>Join our team</a><a href='/x'>Follow us</a></footer>", {"cta": 1}),
    }
    for name, (body, want) in cases.items():
        p = lab / f"{name}.html"
        p.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
        f = senses.numeric(senses.for_path(p).measure(p)["features"])
        assert {k: f[k] for k in want} == want, (name, f)
    prices = lab / "prices.html"
    prices.write_text("<html><body><p>Chỉ 199k. Gói lớn 1,2 triệu. Giá 350.000 VNĐ.</p></body></html>", encoding="utf-8")
    assert senses.numeric(senses.for_path(prices).measure(prices)["features"])["price_mentions"] == 3


def test_text_asks_and_edge_inputs(lab):
    from learnkit.senses.text import asks
    assert asks("Add to cart. Contact us today. Get 50% off!", "en") == 3
    assert asks("Mua sắm cuối năm thật vui. Thử thách mới bắt đầu từ hôm qua.", "vi") == 0
    assert asks("Khám phá ngay bộ sưu tập. Inbox ngay để được tư vấn.", "vi") == 2
    f = senses.numeric(senses.for_path(make_image(lab / "strip.png", size=(400, 1), text=False)).measure(lab / "strip.png")["features"])
    assert f["width_px"] == 400 and "text_like_share" not in f
    arr = np.tile(np.linspace(0, 1, 128, dtype=np.float32), (32, 1))
    Image.fromarray(arr, mode="F").save(lab / "float.tif")
    ff = senses.numeric(senses.for_path(lab / "float.tif").measure(lab / "float.tif")["features"])
    assert .4 < ff["luminance_mean"] < .6
    from learnkit.signals import number
    assert number("0.500")[0] == .5
    text = lab / "s.txt"
    text.write_text("Short text.", encoding="utf-8")
    r = api.learn("register", {"path": str(text), "domain": "x"})
    assert r["features"]["text_chars"] == 11
    with pytest.raises(ValueError, match="ends after"):
        api.learn("evidence", {"exemplar_id": r["id"], "span": {"chars": [0, 40]}})


def test_tempo_reports_both_readings_and_no_pulse_no_tempo(lab):
    import wave
    rate = 22050
    t = np.arange(rate * 10) / rate
    with wave.open(str(lab / "sine.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.sin(2 * np.pi * 440 * t) * .5 * 32767).astype("<i2").tobytes())
    assert "tempo_bpm" not in senses.numeric(senses.for_path(lab / "sine.wav").measure(lab / "sine.wav")["features"])
    y = np.zeros(rate * 16)
    for k, b in enumerate(np.arange(.5, 15.5, 60 / 120)):
        i, n = int(b * rate), int(.12 * rate)
        env = np.exp(-np.arange(n) / rate * 28)
        y[i:i + n] += (np.sin(2 * np.pi * 60 * np.arange(n) / rate) * .9 if k % 2 == 0 else np.random.default_rng(k).standard_normal(n) * .5) * env
    with wave.open(str(lab / "ks.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    f = senses.numeric(senses.for_path(lab / "ks.wav").measure(lab / "ks.wav")["features"])
    assert any(abs(f.get(k, 0) - 120) < 4 for k in ("tempo_bpm", "tempo_double_bpm", "tempo_half_bpm")) and 0 <= f["tempo_confidence"] <= 1


def noise_cohort(lab, seed0, n=15, domain="gadget landing page", copy_of=None, images=lambda i, n: i >= n - n // 3):
    """n pages alike but for their words and one thing: by default the best third show 3 images; or re-saved copies of
    another cohort's pages. Outcomes rise with i; the best third beat the store's usual month."""
    ids = []
    for i in range(n):
        p = lab / f"n{seed0}-{i}.html"
        if copy_of:
            p.write_text(Path(learnkit.core.load(copy_of[i])["source"]["path"]).read_text(encoding="utf-8") + "  ", encoding="utf-8")
        else:
            imgs = "<img src='a.png' alt='tag'>" * 3 if images(i, n) else ""
            p.write_text('<html><body><section><h1>Fast tags</h1><a class="btn" href="/buy">Buy</a></section>'
                         f"<section><h2>Reviews</h2><p>Trusted by customers. {prose(seed0 + i, 40)}</p>{imgs}</section>"
                         f"<section><p>{prose(seed0 + 100 + i, 160)}</p></section></body></html>", encoding="utf-8")
        r = api.learn("register", {"path": str(p), "domain": domain})
        best = i >= n - n // 3
        api.learn("signals", {"exemplar_id": r["id"], "signals": [{"metric": "conversions", "value": (3000 + 50 * i) if best else (600 + 20 * i),
                              "baseline": 1000, "baseline_note": "store median monthly conversions"}]})
        api.learn("anatomy", {"exemplar_id": r["id"], "parts": [{"role": "hero", "span": {"section": 0}}]})
        ids.append(r["id"])
    return ids


def split(ids):
    return api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions"}})


def images_blueprint(ids, cmps, title="Show the tag"):
    return {"title": title, "kind": "web", "domain": "gadget landing page", "purpose": "Turn a visit into a purchase.",
            "structure": [{"role": "hero"}], "steps": ["Show three photos of the tag."], "when_to_use": "Single-product pages.",
            "avoid": "Comparison shopping.", "exemplars": ids, "comparisons": [c["id"] for c in cmps],
            "targets": [{"feature": "images", "range": [2, 5], "provenance": "comparison", "comparison_id": cmps[0]["id"]}]}


def test_a_difference_found_among_many_features_needs_correction_or_confirmation(lab):
    first = noise_cohort(lab, 300)
    c1 = split(first)
    row = next(r for r in learnkit.store.read(learnkit.store.path_for(c1["id"]))["features"] if r["feature"] == "images")
    assert c1["features_tested"] >= 20 and row["delta"] == 1 and row["p"] < .01 and row["p_holm"] > .05  # perfect, yet one of many tries
    bp = images_blueprint(first[-5:], [c1])
    alone = api.learn("distill", {"blueprint": bp})
    assert alone["eligible_level"] == "candidate" and "could be chance" in alone["next_level"]["needs"][-1]
    # Re-saved copies registered later are not new evidence, and another domain is not this one.
    noise_cohort(lab, 500, copy_of=first)
    noise_cohort(lab, 700, domain="kitchen landing page")
    assert learnkit.blueprint.status(learnkit.blueprint.load(alone["id"]))["eligible_level"] == "candidate"
    # New works registered after the target was set that show the same difference confirm it.
    noise_cohort(lab, 900)
    assert learnkit.blueprint.status(learnkit.blueprint.load(alone["id"]))["eligible_level"] == "rule"


def test_hand_picked_groups_and_invented_labels_cannot_make_a_rule(lab):
    rng = np.random.default_rng(1)
    shown = [bool(rng.random() < .5) for _ in range(30)]  # images unrelated to how pages did
    ids = noise_cohort(lab, 300, n=30, images=lambda i, n: shown[i])
    feats = {i: learnkit.core.exemplar_features(learnkit.core.load(i))["images"] for i in ids}
    best, rest = ids[-10:], ids[:-10]
    winners = [i for i in best if feats[i] > 0][:5]
    controls = [i for i in rest if feats[i] == 0][:5]
    picked = api.learn("compare", {"winners": winners, "controls": controls, "metric": "conversions"})
    assert next(d for d in picked["differences"] if d["feature"] == "images")["delta"] == 1  # chosen to differ
    bp = images_blueprint(winners, [picked], title="picked")
    assert api.learn("distill", {"blueprint": bp})["eligible_level"] != "rule"  # judged on the whole domain, it does not hold
    # Role labels placed by group do not dilute the correction of the sense's measurements.
    first = noise_cohort(lab, 600, domain="labelled pages")
    for k, i in enumerate(first):
        sec = 1 if k >= 10 else 2
        api.learn("anatomy", {"exemplar_id": i, "parts": [{"role": "hero", "span": {"section": 0}}] +
                              [{"role": r, "span": {"section": sec}} for r in ("proof", "story", "offer", "faq", "guarantee", "demo")]})
    c = split(first)
    row = next(r for r in learnkit.store.read(learnkit.store.path_for(c["id"]))["features"] if r["feature"] == "images")
    assert row["family"] == "sense" and row["p_holm"] > .05


def test_exemplar_targets_must_hold_the_successes_and_exclude_the_failures(lab):
    ids = noise_cohort(lab, 300)
    base = {**images_blueprint(ids[-5:], [split(ids)]), "comparisons": []}
    held = {**base, "targets": [{"feature": "images", "range": [2, 5], "provenance": "exemplars"}]}
    assert api.learn("distill", {"blueprint": held})["eligible_level"] == "candidate"
    for title, rng in (("misses the winners", [5, 9]), ("holds the flops too", [0, 5]), ("holds everything", [-1e9, 1e9])):
        bp = {**base, "title": title, "targets": [{"feature": "images", "range": rng, "provenance": "exemplars"}]}
        r = api.learn("distill", {"blueprint": bp})
        assert r["eligible_level"] == "observation" and "not grounded: ['images']" in r["next_level"]["needs"][0]


def test_template_siblings_are_distinct_works(lab):
    chrome = "<header><nav><a href='/'>Home</a> <a href='/shop'>Shop</a></nav></header>"
    ids = []
    for i in range(6):
        good = i < 3
        p = lab / f"sib{i}.html"
        cta = "<a class='btn' href='/b'>Buy</a>" if good else ""
        p.write_text(f"<html><body>{chrome}<section><h1>Tag model {i}</h1>{cta}</section>"
                     f"<section><p>Trusted by customers. {prose(40 + i, 150)}</p></section></body></html>", encoding="utf-8")
        r = api.learn("register", {"path": str(p), "domain": "page"})
        api.learn("signals", {"exemplar_id": r["id"], "signals": [{"metric": "sales", "value": 3000 if good else 400, "baseline": 1000,
                                                                    "baseline_note": "median"}]})
        api.learn("anatomy", {"exemplar_id": r["id"], "parts": [{"role": "hero", "span": {"section": 0}}]})
        ids.append(r["id"])
    assert len(learnkit.core.clusters([learnkit.core.load(i) for i in ids])) == 6  # one template, numbers alike, different works
    bp = {**blueprint(ids[:3], "cmp-0000000000000000"), "domain": "page", "comparisons": [],
          "targets": [{"feature": "cta", "range": [1, 3], "provenance": "exemplars"}]}
    assert api.learn("distill", {"blueprint": bp})["eligible_level"] == "candidate"


def test_verification_is_judged_again_when_read(lab):
    ids = cohort(lab)
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    saved = api.learn("distill", {"blueprint": blueprint(ids[-5:], c["id"])})
    work = lab / "launch.html"
    work.write_text('<html><body><section><h1>Launch</h1><a class="btn" href="/b">Buy</a></section><section><p>'
                    + "Trusted by customers. Customer reviews. " * 3 + prose(88, 120) + "</p></section></body></html>", encoding="utf-8")
    r = api.learn("apply", {"blueprint_id": saved["id"], "path": str(work), "note": "launch", "outcome": [
        {"metric": "conversions", "value": 4000, "baseline": 1000, "baseline_note": "store median monthly conversions"}]})
    assert r["verified_works"] == 1 and "unverified" not in r
    # Registering the launched work (here lightly edited) as an exemplar afterwards neither removes its result nor lets
    # a copy applied after that count as another new work.
    again = lab / "launch-copy.html"
    again.write_text(work.read_text(encoding="utf-8").replace("Launch", "Launch day"), encoding="utf-8")
    api.learn("register", {"path": str(again), "domain": "launch archive"})
    assert learnkit.blueprint.status(learnkit.blueprint.load(saved["id"]))["verified_works"] == 1
    late = api.learn("apply", {"blueprint_id": saved["id"], "path": str(again), "note": "the archived copy", "outcome": [
        {"metric": "conversions", "value": 4000, "baseline": 1000, "baseline_note": "store median monthly conversions"}]})
    assert late["recorded"]["duplicate_of"] and late["trials"]["judged"] == 1
    # Without a comparison, outcomes are judged on what the cited exemplars beat their baselines on.
    loose = {**blueprint(ids[-5:], c["id"], title="loose"), "comparisons": [],
             "targets": [{"feature": "hero_cta", "range": [1, 3], "provenance": "exemplars"}]}
    lid = api.learn("distill", {"blueprint": loose})["id"]
    other = lab / "other.html"
    other.write_text(work.read_text(encoding="utf-8").replace(prose(88, 120), prose(89, 120)), encoding="utf-8")
    off = api.learn("apply", {"blueprint_id": lid, "path": str(other), "note": "x", "outcome": [
        {"metric": "smiles", "value": 50, "baseline": 1, "baseline_note": "invented"}]})
    assert off["unverified"] and "judged on ['conversions']" in off["outcome_note"]


def test_a_stated_hypothesis_is_confirmed_on_later_works_and_counted_with_every_other(lab):
    weak = lambda i, n: i in (1, 3, 10, 12, 14)  # in the first pages, the better ones show images only a little more often
    for domain, more in (("shop pages", 0), ("shop pages b", 12)):
        first = noise_cohort(lab, 300 + 2000 * more, domain=domain, images=weak)
        c1 = split(first)
        stated = {**images_blueprint(first[-5:], [c1], title=f"show the tag {more}"), "domain": domain}
        bp = api.learn("distill", {"blueprint": stated})
        if more:  # twelve other hypotheses for this domain and metric, stated before the new works come in (other ranges count too)
            rows = [x for x in learnkit.store.read(learnkit.store.path_for(c1["id"]))["features"]
                    if x["family"] == "sense" and x["median_winners"] != x["median_controls"] and x["feature"] != "images"][:4]
            for k in range(3):
                mid = lambda x: (x["median_winners"] + x["median_controls"]) / 2
                api.learn("distill", {"blueprint": {**stated, "title": f"many {k}", "targets": [
                    {"feature": x["feature"], "provenance": "comparison", "comparison_id": c1["id"],
                     "range": [mid(x), 1e9 - k] if x["median_winners"] > x["median_controls"] else [-1e9 + k, mid(x)]} for x in rows]}})
            assert learnkit.blueprint.stated("web", domain, "conversions") == 13
        fresh = noise_cohort(lab, 900 + 2000 * more, domain=domain)  # new pages, where the difference is clear
        c2 = split(fresh)
        same = {**stated, "comparisons": [c1["id"], c2["id"]], "targets": [{**stated["targets"][0], "comparison_id": c2["id"]}]}
        r = api.learn("distill", {"blueprint": same, "blueprint_id": bp["id"], "base_revision": 1})
        doc = learnkit.blueprint.load(bp["id"])
        assert doc["hypotheses"]["images"]["since"] < min(learnkit.core.load(i)["created_at"] for i in fresh)  # still the old statement
        if not more:
            assert r["eligible_level"] == "rule"  # p_holm over the whole domain is not enough, the confirmation is
            # The same feature restated with another range after the new pages came in is a new hypothesis: they are older.
            moved = {**same, "targets": [{**same["targets"][0], "range": [2.5, 6]}]}
            r = api.learn("distill", {"blueprint": moved, "blueprint_id": bp["id"], "base_revision": 2})
            needs = learnkit.blueprint.gates(learnkit.blueprint.load(bp["id"]))[0]["rule"]
            assert r["eligible_level"] == "candidate" and "not enough" in needs[-1]
        else:
            needs = learnkit.blueprint.gates(doc)[0]["rule"]
            assert r["eligible_level"] == "candidate" and "over 13 hypotheses stated here" in needs[-1]


def test_role_labels_and_moving_works_out_of_a_pool_cannot_make_a_rule(lab):
    ids = noise_cohort(lab, 300, n=24, images=lambda i, n: False)
    for k, i in enumerate(ids):  # labels placed by how the page did, not by what it is
        api.learn("anatomy", {"exemplar_id": i, "parts": [{"role": "hero", "span": {"section": 0}},
                                                          {"role": "proof", "span": {"section": 1 if k >= 16 else 2}}]})
    c = split(ids)
    target = {"feature": "role_start_proof", "range": [0, .1], "provenance": "comparison", "comparison_id": c["id"]}
    r = api.learn("distill", {"blueprint": {**images_blueprint(ids[-5:], [c]), "targets": [target]}})
    assert r["eligible_level"] == "candidate" and "labelled roles" in r["next_level"]["needs"][-1]
    # Once a work has evidence, it cannot be moved to another domain or lose its baseline to leave the split.
    page = learnkit.core.load(ids[0])["source"]["path"]
    with pytest.raises(ValueError, match="stays as it is"):
        api.learn("register", {"path": page, "domain": "gadget landing page (old)"})
    assert api.learn("register", {"path": page, "domain": "  Gadget   Landing page "})["domain"] == "Gadget Landing page"
    with pytest.raises(ValueError, match="had a baseline"):
        api.learn("signals", {"exemplar_id": ids[0], "signals": [{"metric": "conversions", "value": 600}]})


def test_the_split_keeps_tied_works_together(lab):
    ids = noise_cohort(lab, 300, n=30)
    for i in ids[:11]:  # eleven pages sold nothing
        api.learn("signals", {"exemplar_id": i, "signals": [{"metric": "conversions", "value": 0, "baseline": 1000,
                                                              "baseline_note": "store median monthly conversions"}]})
    high, low = learnkit.compare.canonical("web", "gadget landing page", "conversions")
    assert len(low) == 11 and len(high) == 10 and not {e["id"] for e in high} & {e["id"] for e in low}


def test_a_pool_keeps_what_it_measured_and_copies_belong_to_their_first_pool(lab):
    ids = noise_cohort(lab, 300, n=15)
    page = learnkit.core.load(ids[0])["source"]["path"]
    before = learnkit.core.measurement(ids[0])
    with pytest.raises(ValueError, match="kind stays"):  # refused before anything is measured or written
        api.learn("register", {"path": page, "domain": "gadget landing page", "kind": "text"})
    assert learnkit.core.measurement(ids[0])["measured_with"] == before["measured_with"]
    shot = lab / "shot.png"
    Image.new("RGB", (1366, 2000), (240, 240, 240)).save(shot)
    with pytest.raises(ValueError, match="same options"):
        api.learn("register", {"path": page, "domain": "gadget landing page", "options": {"screenshot": str(shot)}})
    # Re-saved copies of hand-picked pages registered under a new domain stay in their first domain's pool.
    copies = []
    for i in ids[-5:] + ids[:5]:
        src = Path(learnkit.core.load(i)["source"]["path"])
        c = lab / f"copy-{src.name}"
        c.write_text(src.read_text(encoding="utf-8") + "  ", encoding="utf-8")
        r = api.learn("register", {"path": str(c), "domain": "gadget landing pages"})
        assert r["same_work_as"][0]["id"] == i
        copies.append(r["id"])
    assert learnkit.core.pool("web", "gadget landing pages") == []
    # A typo'd domain that nothing else uses can still be corrected, and the move is logged.
    lone = lab / "lone.html"
    lone.write_text("<html><body><section><h1>Lone</h1><p>" + prose(5, 120) + "</p></section></body></html>", encoding="utf-8")
    one = api.learn("register", {"path": str(lone), "domain": "gadgte landing page"})["id"]
    api.learn("signals", {"exemplar_id": one, "signals": [{"metric": "conversions", "value": 900, "baseline": 1000, "baseline_note": "median"}]})
    assert api.learn("register", {"path": str(lone), "domain": "gadget landing page"})["domain"] == "gadget landing page"
    assert learnkit.core.load(one)["domain_history"][0]["domain"] == "gadgte landing page"
    # Ids in a blueprint are checked: nothing outside the store can be cited.
    with pytest.raises(ValueError):
        api.learn("distill", {"blueprint": {**images_blueprint(ids[-5:], [split(ids)]), "comparisons": ["cmp-x/../../outside"]}})


def test_text_and_web_fingerprints_of_one_file_are_not_confused(lab):
    a, b = lab / "a.html", lab / "b.html"
    body = "<section><h1>Title</h1><p>" + prose(1, 200) + "</p></section>"
    a.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    b.write_text(f"<html><head><script>{prose(2, 300)}</script></head><body>{body}</body></html>", encoding="utf-8")
    t = [learnkit.core.load(api.learn("register", {"path": str(p), "domain": "x", "kind": "text"})["id"]) for p in (a, b)]
    learnkit.core.same_work(*t)  # cached as text
    w = [learnkit.core.load(api.learn("register", {"path": str(p), "domain": "x", "kind": "web"})["id"]) for p in (a, b)]
    assert learnkit.core.same_work(*w)  # as web pages they are one page (the script is not content)


def test_hypotheses_are_counted_across_metrics_and_the_ledger_is_not_the_only_record(lab, monkeypatch):
    ids = noise_cohort(lab, 300)
    c = split(ids)
    api.learn("distill", {"blueprint": images_blueprint(ids[-5:], [c])})
    for metric in ("sales", "signups"):
        for i in ids:
            v = learnkit.core.load(i)["signals"][0]
            api.learn("signals", {"exemplar_id": i, "signals": [{"metric": metric, "value": v["value"], "baseline": 1000, "baseline_note": "m"}]})
        cm = api.learn("compare", {"exemplars": ids, "split": {"metric": metric}})
        api.learn("distill", {"blueprint": {**images_blueprint(ids[-5:], [cm]), "title": f"by {metric}"}})
    assert learnkit.blueprint.stated("web", "gadget landing page") == 3
    monkeypatch.setattr(learnkit.blueprint, "_ledger", lambda: lab / "no-such-ledger.jsonl")
    assert learnkit.blueprint.stated("web", "gadget landing page") == 3  # read from the blueprints too


def test_a_trial_record_cannot_be_reshaped_afterwards(lab):
    ids = cohort(lab, 24)
    c = api.learn("compare", {"exemplars": ids, "split": {"metric": "conversions", "top": .5, "bottom": .5}})
    bp = blueprint(ids[-5:], c["id"])
    saved = api.learn("distill", {"blueprint": bp})
    pages = [launch(lab, f"l{k}", 300 + k) for k in range(6)]
    for k, value in enumerate((5000, 700, 4000, 650, 900, 4200)):
        r = api.learn("apply", {"blueprint_id": saved["id"], "path": str(pages[k]), "note": "launch", "outcome": [
            {"metric": "conversions", "value": value, "baseline": 1000, "baseline_note": "store median"},
            {"metric": "signups", "value": 5000, "baseline": 1000, "baseline_note": "store median"}]})
    assert r["trials"] == {"judged": 6, "beat": 3, "p": .6562, "series": 1}
    # Registering the losing pages as exemplars afterwards does not remove them.
    for k in (1, 3, 4):
        api.learn("register", {"path": str(pages[k]), "domain": "launch archive"})
    assert learnkit.blueprint.status(learnkit.blueprint.load(saved["id"]))["trials"]["judged"] == 6
    # Judging the same launches on another metric (citing another comparison) is another series, with no results yet.
    for i in ids:
        api.learn("signals", {"exemplar_id": i, "signals": [{"metric": "signups", "value": learnkit.core.load(i)["signals"][0]["value"],
                                                              "baseline": 1000, "baseline_note": "store median"}]})
    cs = api.learn("compare", {"exemplars": ids, "split": {"metric": "signups", "top": .5, "bottom": .5}})
    switched = {**bp, "comparisons": [cs["id"]], "targets": [{**t, "comparison_id": cs["id"]} for t in bp["targets"]]}
    r = api.learn("distill", {"blueprint": switched, "blueprint_id": saved["id"], "base_revision": 1})
    assert r["trials"]["judged"] == 0
    # A blueprint keeps its kind and domain, so its trials cannot be parked elsewhere.
    with pytest.raises(ValueError, match="stay as they are"):
        api.learn("distill", {"blueprint": {**switched, "domain": "parked"}, "blueprint_id": saved["id"], "base_revision": 2})


def test_moved_works_and_disguised_copies_do_not_shape_a_pool(lab):
    ids = noise_cohort(lab, 300, n=15)
    lone = noise_cohort(lab, 700, n=3, domain="gadget landing page store 1")
    page = learnkit.core.load(lone[0])["source"]["path"]
    with pytest.raises(ValueError, match="stays as it is"):  # its old domain has other works
        api.learn("register", {"path": page, "domain": "gadget landing page"})
    solo = noise_cohort(lab, 800, n=1, domain="a store of its own")[0]
    api.learn("register", {"path": learnkit.core.load(solo)["source"]["path"], "domain": "gadget landing page"})
    assert solo not in {e["id"] for e in learnkit.core.pool("web", "gadget landing page")}  # moved in after its outcome
    # Copies whose content is cut into blocks named like a sidebar, with a new paragraph, are still their originals.
    for i in ids[:3]:
        src = Path(learnkit.core.load(i)["source"]["path"]).read_text(encoding="utf-8")
        words = src.split("<section><p>")[-1].split("</p>")[0].split(" ")
        hidden = "".join(f"<div class='sidebar'>{' '.join(words[j:j + 25])}</div>" for j in range(0, len(words), 25))
        c = lab / f"hidden-{i}.html"
        c.write_text(src.replace(" ".join(words), "") + f"<section><p>{prose(9000 + len(i), 30)}</p></section>{hidden}", encoding="utf-8")
        assert learnkit.core.same_work(learnkit.core.load(api.learn("register", {"path": str(c), "domain": "copies"})["id"]),
                                       learnkit.core.load(i))


def test_one_stores_pages_with_a_big_footer_stay_distinct(tmp_path):
    foot = "<footer><p>" + prose(77, 200) + "</p></footer>"
    W = senses.get("web")
    fps = []
    for k in range(6):
        p = tmp_path / f"p{k}.html"
        p.write_text(f"<html><body><header><nav>Home Shop Cart</nav></header><section><h1>Product {k}</h1><p>{prose(100 + k, 80)}</p>"
                     f"</section>{foot}</body></html>", encoding="utf-8")
        fps.append(W.fingerprint(p))
    assert all(learnkit.fingerprint.verdict(fps[i], fps[j]) == "distinct" for i in range(6) for j in range(i + 1, 6))
