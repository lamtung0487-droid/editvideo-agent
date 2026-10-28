"""Web pages and landing pages (a saved .html, optionally with a screenshot): heading structure, length, calls to
action and how early the first one comes, the hero (the block holding the first h1), forms, images, price and
social-proof cues, landmarks, and the page split into blocks (header, hero, sections, footer). With a screenshot, the
image sense also measures the whole page and the first screen ("above the fold").

The page is parsed locally with the standard library: no network, no script execution, nothing fetched. Layout is
only known from a screenshot the caller supplies.
"""
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from . import feature, register
from .text import CTA, WORD, decode, language

LANDMARKS = {"header", "nav", "main", "section", "article", "aside", "footer"}
SKIP = {"script", "style", "noscript", "template", "svg", "head"}
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr", "area", "base", "col", "embed", "param", "track"}
PRICE = re.compile(r"(?:[$€£¥₫]\s?\d|\d[\d.,]*\s?(?:đ|₫|vnđ|vnd|usd|eur|k|tr|triệu|nghìn|ngàn)(?![^\W_])|"
                   r"/\s?(?:mo|month|year|yr|tháng|năm)(?![^\W_]))", re.I)
PROOF = re.compile(r"(?<![^\W_])(?:customers?|reviews?|rated|ratings?|trusted|testimonials?|clients?|users?|stars?|★|"
                   r"khách hàng|đánh giá|tin dùng|người dùng)(?![^\W_])", re.I)
# Controls that run the page, not the offer: menus, cookie banners, dialogs, search, accordions, carousels, quantities.
CHROME = {"menu", "nav", "navbar", "cookie", "cookies", "consent", "gdpr", "close", "dismiss", "toggle", "toggler", "hamburger",
          "search", "modal", "dialog", "lang", "language", "accordion", "faq", "collapse", "carousel", "slider", "swiper", "slick",
          "play", "pause", "qty", "quantity", "increment", "decrement", "plus", "minus", "prev", "previous", "next", "tab", "tabs"}
FOLD = 768 / 1366  # first screen of a common laptop viewport, as a share of the page width


# Site furniture around a page's own content, by role or by class/id word (a site's menu and footer built from divs).
FRAME_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search"}
FRAME_WORDS = {"nav", "navbar", "navigation", "menu", "menubar", "header", "masthead", "topbar", "footer", "sidebar",
               "breadcrumb", "breadcrumbs", "cookie", "cookies", "consent"}


# Asks strong enough to count even as a plain menu link ("Shop" or "Home" in a menu are navigation).
STRONG = re.compile(r"\b(?:sign up|get started|buy now|shop now|order now|start (?:your )?free trial|book a demo|request a demo|try (?:it )?free)\b|"
                    r"(?<![^\W_])(?:đăng ký|mua ngay|đặt ngay|dùng thử)(?![^\W_])", re.I)


def _asks(text):
    return bool(CTA["en"].search(text) or CTA["vi"].search(text))


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.open, self.blocks, self.title, self.meta, self.lang = [], Counter(), [], "", "", ""
        self.words_before_cta, self.words = None, 0
        self.counts = {k: 0 for k in ("h1", "h2", "h3", "links", "external_links", "images", "images_no_alt", "forms", "inputs",
                                      "buttons", "lists", "tables", "scripts", "stylesheets", "quotes")}
        self._new("top", 0)
        self._control = None  # a link or button being read; whether it is an ask is decided at its end tag
        self._closed = False  # a landmark just ended: what follows is a new block
        self.h1_block = None
        self.chunks, self._frame_at, self._frames = [], None, 0  # text with the site-furniture element it sits in, if any
        self.frame_content = set()  # furniture-named elements that hold the page's content (its h1, main or article)

    def _new(self, tag, depth):
        self.blocks.append({"tag": tag, "heading": "", "words": 0, "cta": 0, "images": 0, "forms": 0, "text": [], "depth": depth})
        self._closed = False

    @property
    def block(self):
        if self._closed:
            self._new("div", len(self.stack))
        return self.blocks[-1]

    def _skipping(self):
        return any(self.open[t] for t in SKIP)

    def _zone(self):
        return "footer" if self.open["footer"] else "chrome" if self.open["nav"] or self.open["header"] else "body"

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        if tag == "meta" and a.get("name", "").lower() == "description":
            self.meta = a.get("content", "")
        if tag == "script":
            self.counts["scripts"] += 1
        if tag == "link" and "stylesheet" in a.get("rel", "").lower():
            self.counts["stylesheets"] += 1
        if tag not in VOID:
            self.stack.append(tag)
            self.open[tag] += 1
            hint = set(re.split(r"[-_\s]+", " ".join([a.get("class", ""), a.get("id", "")]).lower()))
            if self._frame_at is None and tag not in ("html", "body", "main") and (
                    tag in ("header", "nav", "footer", "aside") or a.get("role", "").lower() in FRAME_ROLES or hint & FRAME_WORDS):
                self._frame_at, self._frames = len(self.stack), self._frames + 1
        if self._skipping():
            return
        depth = len(self.stack)
        if tag in LANDMARKS - {"main"} or tag in ("h1", "h2"):
            b = self.blocks[-1]
            if b["words"] or b["images"] or b["forms"] or b["cta"] or self._closed:
                self._new(tag, depth)
            elif b["tag"] == "top" and tag in LANDMARKS:
                b["tag"] = tag  # the first landmark names the empty opening block; a nav inside a header stays "header"
        if self._frame_at is not None and (tag in ("main", "article") or (tag == "h1" and not (self.open["header"] or self.open["nav"]))):
            self.frame_content.add(self._frames)
        if tag in ("h1", "h2", "h3"):
            self.counts[tag] += 1
            if tag == "h1" and self.h1_block is None and not self.open["header"]:  # an h1 in the header is the site's name
                self.h1_block = len(self.blocks) - 1
        tokens = set(re.split(r"[-_\s]+", " ".join([a.get("class", ""), a.get("id", ""), a.get("aria-label", ""), a.get("role", "")]).lower()))
        chrome = bool(tokens & CHROME) or "aria-expanded" in a or "aria-controls" in a
        styled = bool(tokens & {"btn", "button", "cta"}) or any(t.startswith("btn") for t in tokens)
        if tag == "a" and "href" in a:
            self.counts["links"] += 1
            self.counts["external_links"] += a["href"].startswith(("http://", "https://", "//"))
        if tag in ("a", "button"):
            self.counts["buttons"] += tag == "button"
            self._control = {"text": "", "chrome": chrome, "styled": styled, "zone": self._zone(), "words": self.words,
                             "block": len(self.blocks) - 1, "tag": tag}
        if tag == "input" and a.get("type", "").lower() in ("submit", "button") and not chrome:
            zone = self._zone()
            if zone == "body" or STRONG.search(a.get("value", "")):
                self._cta(len(self.blocks) - 1, self.words)
        if tag == "img":
            self.counts["images"] += 1
            self.counts["images_no_alt"] += not a.get("alt", "").strip()
            self.block["images"] += 1
        if tag == "form":
            self.counts["forms"] += 1
            self.block["forms"] += 1
        if tag in ("input", "select", "textarea") and a.get("type", "").lower() not in ("hidden", "submit", "button"):
            self.counts["inputs"] += 1
        if tag in ("ul", "ol"):
            self.counts["lists"] += 1
        if tag == "table":
            self.counts["tables"] += 1
        if tag == "blockquote":
            self.counts["quotes"] += 1

    def _cta(self, block, words):
        self.blocks[block]["cta"] += 1
        if self.words_before_cta is None or words < self.words_before_cta:
            self.words_before_cta = words

    def handle_endtag(self, tag):
        c = self._control
        if c and tag == c["tag"]:
            ask = _asks(c["text"])
            # In a menu only an ask counts ("Get started"); in the footer only a styled button; elsewhere a styled
            # control or an ask. Accordions, carousels, cookie banners and quantity steppers never count.
            menu_ask = (c["styled"] and ask) or bool(STRONG.search(c["text"]))
            if not c["chrome"] and (menu_ask if c["zone"] == "chrome" else c["styled"] if c["zone"] == "footer" else c["styled"] or ask):
                self._cta(c["block"], c["words"])
            self._control = None
        if self.open[tag]:
            while self.stack:
                top = self.stack.pop()
                self.open[top] -= 1
                if top == tag:
                    break
            if self._frame_at is not None and len(self.stack) < self._frame_at:
                self._frame_at = None
        if tag in LANDMARKS and not self._skipping() and not any(self.open[t] for t in LANDMARKS - {"main"}):
            self._closed = True  # a top-level landmark ended; a nav closing inside its header does not split the header

    def handle_data(self, data):
        if self.open["title"]:
            self.title += data
            return
        if self._skipping() or not data.strip():
            return
        n = len(WORD.findall(data))
        if self._control is not None:
            self._control["text"] += " " + data
        block = self.block
        if (self.open["h1"] or self.open["h2"] or self.open["h3"]) and not block["heading"]:
            block["heading"] = data.strip()[:120]
        self.words += n
        block["words"] += n
        block["text"].append(data.strip())
        self.chunks.append((None if self._frame_at is None else self._frames, data.strip(), n))


def parse(path):
    page = _Page()
    page.feed(decode(Path(path).read_bytes()))
    page.close()
    # An element named like furniture that holds the page's heading, main or article is the page, whatever its name.
    own = {None} | page.frame_content
    page.own = [t for f, t, _ in page.chunks if f in own]
    page.all = [t for _, t, _ in page.chunks]
    keep = [i for i, b in enumerate(page.blocks) if b["words"] or b["images"] or b["forms"] or b["cta"]]
    blocks = [page.blocks[i] for i in keep]
    first = keep.index(page.h1_block) if page.h1_block in keep else \
        next((k for k, b in enumerate(blocks) if b["tag"] not in ("header", "nav", "footer") and b["words"] >= 3), None)
    hero = []
    if first is not None:
        hero = [first]
        # A tagline (h2) and its button in the same container belong to the hero.
        for k in range(first + 1, len(blocks)):
            b = blocks[k]
            if b["tag"] == "h2" and b["depth"] >= blocks[first]["depth"] and sum(blocks[j]["words"] for j in hero) + b["words"] <= 80:
                hero.append(k)
            else:
                break
    page.blocks, page.hero, page.hero_blocks = blocks, first, hero
    return page


class WebSense:
    kind = "web"
    version = "4"
    features_max = 45  # with a screenshot (28 without): the size of the family a comparison corrects for
    extensions = (".html", ".htm", ".xhtml")
    spans = ("section", "box")

    def measure(self, path, options=None):
        page = parse(path)
        text = " ".join(" ".join(b["text"]) for b in page.blocks)
        lang = page.lang[:2].lower() if page.lang[:2].lower() in ("vi", "en") else language(text)
        c, words = page.counts, max(1, page.words)
        first_heading = next((b["heading"] for b in page.blocks if b["heading"]), "")
        hero_blocks = [page.blocks[k] for k in page.hero_blocks]
        hero = {"words": sum(b["words"] for b in hero_blocks), "cta": sum(b["cta"] for b in hero_blocks),
                "heading": hero_blocks[0]["heading"] if hero_blocks else ""}
        feats = {"words": feature(page.words, "words"), "blocks": feature(len(page.blocks), "blocks"),
                 "h1": feature(c["h1"], "headings"), "h2": feature(c["h2"], "headings"), "h3": feature(c["h3"], "headings"),
                 "first_heading_words": feature(len(WORD.findall(first_heading)), "words"),
                 "title_words": feature(len(WORD.findall(page.title)), "words"), "meta_description_chars": feature(len(page.meta.strip()), "chars"),
                 "cta": feature(sum(b["cta"] for b in page.blocks), "calls to action (menus and cookie buttons excluded)"),
                 "first_cta_at_share": feature(page.words_before_cta / words if page.words_before_cta is not None else None, "share of words before the first CTA"),
                 "cta_per_1000_words": feature(1000 * sum(b["cta"] for b in page.blocks) / words, "per 1000 words"),
                 "hero_index": feature(page.hero, "block holding the first content h1 (else the first content block)"),
                 "hero_words": feature(hero["words"], "words in the hero"), "hero_cta": feature(hero["cta"], "calls to action in the hero"),
                 "hero_heading_words": feature(len(WORD.findall(hero["heading"])), "words"),
                 "forms": feature(c["forms"], "forms"), "form_fields": feature(c["inputs"], "fields"),
                 "images": feature(c["images"], "images"), "images_without_alt_share": feature(c["images_no_alt"] / max(1, c["images"]), "share"),
                 "links": feature(c["links"], "links"), "external_link_share": feature(c["external_links"] / max(1, c["links"]), "share"),
                 "price_mentions": feature(len(PRICE.findall(text)), "mentions"), "social_proof_mentions": feature(len(PROOF.findall(text)), "mentions"),
                 "quotes": feature(c["quotes"], "blockquotes"), "lists": feature(c["lists"], "lists"),
                 "scripts": feature(c["scripts"], "script tags"), "stylesheets": feature(c["stylesheets"], "stylesheets"),
                 "words_per_block": feature(page.words / max(1, len(page.blocks)), "words")}
        notes = [f"language: {lang}", "parsed locally; no script ran, nothing was fetched"]
        shot = (options or {}).get("screenshot")
        if shot:
            feats.update(_screenshot(shot))
        else:
            notes.append("no screenshot: layout, colour and the first screen are unmeasured")
        parts = [{"span": {"section": i}, "role_hint": "hero" if i in page.hero_blocks else b["tag"], "heading": b["heading"],
                  "features": _block_features(b)} for i, b in enumerate(page.blocks[:40])]
        return {"features": feats, "parts": parts, "notes": notes}

    def _shot(self, options):
        shot = (options or {}).get("screenshot")
        if not shot:
            raise ValueError("A box span on a web page needs its screenshot (register with options.screenshot)")
        return shot

    def measure_span(self, path, span, options=None):
        if "box" in span:
            from .image import ImageSense
            return ImageSense().measure_span(self._shot(options), span)
        page = parse(path)
        i = span["section"]
        if i >= len(page.blocks):
            raise ValueError(f"The page has {len(page.blocks)} blocks")
        return {"features": _block_features(page.blocks[i])}

    def fingerprint(self, path, options=None):
        """The page's own content (header, nav and footer are template boilerplate shared across a site)."""
        from .. import fingerprint
        page = parse(path)
        return fingerprint.web(" ".join(page.own), " ".join(page.all))

    def geometry(self, path, span, features, options=None):
        if "box" in span:
            x, y, w, h = span["box"]
            return {"share": round(w * h, 4), "start_share": round(y, 4)}
        page = parse(path)
        i = span["section"]
        if i >= len(page.blocks):
            raise ValueError(f"The page has {len(page.blocks)} blocks")
        total = max(1, page.words)
        before = sum(b["words"] for b in page.blocks[:i])
        return {"share": round(page.blocks[i]["words"] / total, 4), "start_share": round(before / total, 4)}

    def evidence(self, path, span, out_dir, options=None):
        if "box" in span:
            from .image import ImageSense
            return ImageSense().evidence(self._shot(options), span, out_dir)
        page = parse(path)
        if span["section"] >= len(page.blocks):
            raise ValueError(f"The page has {len(page.blocks)} blocks")
        chunk = " ".join(page.blocks[span["section"]]["text"])
        return [{"type": "text", "text": chunk[:600] + ("…" if len(chunk) > 600 else "")}]


def _block_features(b):
    text = " ".join(b["text"])
    return {"words": feature(b["words"], "words"), "cta": feature(b["cta"], "calls to action"), "images": feature(b["images"], "images"),
            "forms": feature(b["forms"], "forms"), "price_mentions": feature(len(PRICE.findall(text)), "mentions"),
            "social_proof_mentions": feature(len(PROOF.findall(text)), "mentions")}


def _screenshot(path):
    from PIL import Image
    from .image import ImageSense
    sense = ImageSense()
    whole = sense.measure_span(path, {"box": [0, 0, 1, 1]})["features"]
    with Image.open(path) as im:
        W, H = im.size
    fold = min(1.0, FOLD * W / H)
    top = sense.measure_span(path, {"box": [0, 0, 1, fold]})["features"]
    out = {"page_height_screens": feature(H / (W * FOLD), "screens (1366x768 viewport)")}
    out.update({f"shot_{k}": v for k, v in whole.items() if k != "area_share"})
    out.update({f"fold_{k}": v for k, v in top.items() if k != "area_share"})
    return out


register(WebSense())
