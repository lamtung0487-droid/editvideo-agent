"""Creative directions: machine-readable style blocks that make a whole film consistent and let styles differ for real.

A direction fixes the look (bundled fonts/palette and type tweaks), the motion language (curve, entrance/exit timing,
stagger, ambient idle, camera push), pacing (seconds per idea, dwell), the transition vocabulary (one primary, few
accents, share of straight cuts), title and caption tone, finishing layers and composition rules plus a negative list.
apply() writes the block into design.direction; recipes and audit_timeline read it. Values come from common
motion-design practice (entrances ease out, exits ease in, camera push 4–8%, dwell 1.5–2.5 s on hero moments,
stagger shorter than the animation, overshoot on transforms only). They are starting points, not rules of taste.
"""
import copy
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import agent

FPS = 30
CAPTION_TONES = {
    "hype": {"typography": "heavy sans", "size_px": [72, 96], "mode": "box", "future_opacity": .45, "animation": "scale-pop word highlight"},
    "corporate": {"typography": "clean sans", "size_px": [56, 72], "mode": "color", "future_opacity": .7, "animation": "fade and slide"},
    "tutorial": {"typography": "monospace", "size_px": [48, 64], "mode": "underline", "future_opacity": .65, "animation": "typewriter"},
    "storytelling": {"typography": "serif", "size_px": [44, 56], "mode": "color", "future_opacity": .55, "animation": "slow fade"},
    "social": {"typography": "rounded", "size_px": [56, 80], "mode": "box", "future_opacity": .6, "animation": "bounce"},
}


def D(id, name, genres, mood, energy, look, motion, pacing, transitions, titles, captions, finish, composition, negative, hero):
    return {"id": id, "name": name, "genres": genres, "mood": mood, "energy": energy, "look": look, "motion": motion, "pacing": pacing,
            "transitions": transitions, "titles": titles, "captions": captions, "finish": finish, "composition": composition,
            "negative": negative, "hero_techniques": hero}


def M(ease, entrance_s, stagger=.12, idle=0.0, push=.05, hold="ambient", overshoot=False, exit_ease="ease_in", exit_s=.35):
    return {"ease": ease, "entrance_s": entrance_s, "exit_ease": exit_ease, "exit_s": exit_s, "stagger_ratio": stagger,
            "ambient_idle": idle, "camera_push": push, "hold": hold, "overshoot_transforms": overshoot}


DIRECTIONS = {d["id"]: d for d in [
    D("cinematic_documentary", "Phim tài liệu điện ảnh", ["documentary", "history", "travel essay", "science story"], "trầm, nhân văn", "calm",
      {"style_id": "documentary", "palette_id": "ink_gold", "type": {"display": {"weight": 600, "tracking": -.01}}},
      # measured (round 13): Real Time History's Điện Biên Phủ 7.7 s average shot, 6 cuts/min median, 28 % of shots over
      # 10 s; Epic History 16.6 s; RealLifeLore 41 s (maps). 3-6 s per idea read as a constant 14 cuts/min: overwhelming
      M("smooth", .8, .12, .012, .05), {"seconds_per_idea": [6, 8], "dwell_s": [3, 5], "min_shot_s": 3.5, "short_share_max": .1},
      {"primary": "dissolve", "accents": ["flash", "burn"], "duration_frames": 24, "cut_ratio": .6},
      {"effect": "reveal", "role": "display", "case": "sentence"}, {"tone": "storytelling"},
      {"grain": .18, "leaks": "accents", "leak_colors": ["#ffb347", "#ff5a3c"], "vignette": .35, "looks": []},
      ["one focal element per beat", "lower-left titles with generous negative space", "source line on evidence"],
      ["glitch", "emoji", "bouncy text", "rainbow gradients"], ["globe_dive", "map_journey", "photo_3d"]),
    D("travel_energy", "Du lịch năng lượng", ["travel vlog", "city guide", "event recap"], "vui, háo hức", "high",
      {"style_id": "short_bold", "palette_id": "terracotta", "type": {"display": {"weight": 800}}},
      M("snappy", .35, .08, .015, .06, overshoot=True), {"seconds_per_idea": [1.5, 3], "dwell_s": [1.5, 2]},
      {"primary": "whip_right", "accents": ["zoom_through", "flash"], "duration_frames": 10, "cut_ratio": .5, "mode": "live"},
      {"effect": "spring", "role": "display", "case": "upper"}, {"tone": "hype"},
      {"grain": .15, "leaks": "accents", "leak_colors": ["#ffb347", "#ff3c6e"], "vignette": .25, "looks": []},
      ["subject-led framing", "text behind subject for place names", "route map in a corner between places"],
      ["slow dissolves", "holds longer than 3 s without motion", "serif body text"], ["map_journey", "text_behind_subject", "speed_ramp"]),
    D("premium_product", "Sản phẩm cao cấp", ["product launch", "brand film", "luxury retail"], "tinh tế, tự tin", "calm",
      {"style_id": "minimal_explainer", "palette_id": "noir", "type": {"display": {"weight": 300, "tracking": .12, "line_height": 1.15}, "headline": {"weight": 400, "tracking": .06}}},
      M("dramatic", 1.0, .15, .01, .04), {"seconds_per_idea": [3, 5], "dwell_s": [2, 2.5]},
      {"primary": "dissolve", "accents": ["zoom_in"], "duration_frames": 22, "cut_ratio": .3},
      {"effect": "tracking", "role": "display", "case": "upper"}, {"tone": "corporate"},
      {"grain": 0, "leaks": "none", "vignette": .2, "looks": []},
      ["centred hero object with wide negative space", "one accent colour used once", "slow camera push on the hero"],
      ["bouncy easing", "emoji", "saturated multi-colour", "shake", "film dust"], ["hero_object_3d", "photo_3d", "kinetic_title"]),
    D("tech_launch", "Ra mắt công nghệ", ["SaaS", "app feature", "developer tool", "AI product"], "sắc nét, tương lai", "medium",
      {"style_id": "data_report", "palette_id": "indigo", "heading_font_id": "inter", "body_font_id": "inter", "type": {"display": {"weight": 800, "tracking": -.03}, "label": {"font_id": "ibmplexmono", "weight": 600}}},
      M("snappy", .4, .09, .01, .06, overshoot=True), {"seconds_per_idea": [1.5, 3], "dwell_s": [1.5, 2]},
      {"primary": "push_left", "accents": ["zoom_through", "flash"], "duration_frames": 12, "cut_ratio": .45, "mode": "live"},
      {"effect": "reveal", "role": "display", "case": "sentence"}, {"tone": "corporate"},
      {"grain": .06, "leaks": "none", "vignette": .15, "looks": []},
      ["UI cards on a grid with three depth layers", "mono labels for specs", "one glowing accent"],
      ["paper texture", "serif type", "warm light leaks"], ["hero_object_3d", "tracked_callout", "kinetic_title"]),
    D("editorial_magazine", "Tạp chí biên tập", ["essay", "culture", "long read", "opinion"], "suy tư, có chủ kiến", "medium",
      {"style_id": "editorial_paper", "palette_id": "paper", "type": {"display": {"weight": 700, "tracking": -.02, "line_height": 1.12}}},
      M("ease_in_out", .6, .1, 0, .03, hold="still"), {"seconds_per_idea": [3, 5], "dwell_s": [2, 3]},
      {"primary": "push_up", "accents": ["wipe_left"], "duration_frames": 14, "cut_ratio": .55},
      {"effect": "reveal", "role": "display", "case": "sentence"}, {"tone": "storytelling"},
      {"grain": .1, "leaks": "none", "vignette": 0, "looks": []},
      ["two-colour discipline: paper ground, ink type; emphasis by size or inversion", "asymmetric 60/40 columns with hairline rules", "big numerals"],
      ["glow", "neon", "3D chrome", "a third accent colour"], ["kinetic_title", "map_journey", "photo_3d"]),
    D("swiss_minimal", "Swiss tối giản", ["architecture", "design", "corporate report", "museum"], "lý trí, rõ ràng", "medium",
      {"style_id": "monochrome_focus", "palette_id": "noir", "colors": {"accent": "#e63b2e"}, "type": {"display": {"weight": 800, "tracking": -.04, "line_height": 1.1}}},
      M("ease_in_out", .3, .06, 0, 0, hold="still"), {"seconds_per_idea": [2, 4], "dwell_s": [1.5, 2]},
      {"primary": "cut", "accents": ["wipe_left"], "duration_frames": 8, "cut_ratio": .8},
      {"effect": "reveal", "role": "display", "case": "sentence"}, {"tone": "corporate"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["strict grid, flush-left", "display type about one tenth of frame width", "red used for one element per frame"],
      ["gradients", "glow", "drop shadows", "rounded corners", "serif"], ["kinetic_title", "map_journey"]),
    D("kinetic_hype", "Chữ động bùng nổ", ["social hook", "music promo", "announcement", "sports"], "hưng phấn", "high",
      {"style_id": "short_bold", "palette_id": "magenta", "type": {"display": {"weight": 900, "tracking": -.04, "line_height": 1.1}}},
      M("snappy", .22, .05, .02, .08, overshoot=True), {"seconds_per_idea": [1, 2.5], "dwell_s": [1, 1.5]},
      {"primary": "zoom_through", "accents": ["flash", "whip_left"], "duration_frames": 8, "cut_ratio": .5},
      {"effect": "spring", "role": "display", "case": "upper"}, {"tone": "hype"},
      {"grain": .1, "leaks": "none", "vignette": .2, "looks": []},
      ["one huge word per beat", "beat-synced accents", "text interacting with subject"],
      ["slow dissolves", "holds over 2.5 s", "small body text"], ["kinetic_title", "text_behind_subject"]),
    D("data_journalism", "Báo chí dữ liệu", ["data story", "economics", "report", "explainer with numbers"], "đáng tin, rõ ràng", "medium",
      {"style_id": "data_report", "palette_id": "slate"},
      M("smooth", .5, .1, 0, .03, hold="still"), {"seconds_per_idea": [3, 6], "dwell_s": [2, 3]},
      {"primary": "dissolve", "accents": ["push_up"], "duration_frames": 14, "cut_ratio": .6},
      {"effect": "reveal", "role": "headline", "case": "sentence"}, {"tone": "corporate"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["chart plus a one-line takeaway", "source line always visible", "two colours plus one highlight"],
      ["3D pies", "bouncing counters", "decorative particles", "truncated axes without label"], ["map_journey", "tracked_callout"]),
    D("flat_vector_explainer", "Minh họa phẳng giải thích", ["explainer", "education", "how it works", "kids science"], "thân thiện, dễ hiểu", "medium",
      {"style_id": "friendly_learning", "palette_id": "cobalt"},
      M("bouncy", .45, .1, .015, .02, overshoot=True), {"seconds_per_idea": [2.5, 4], "dwell_s": [1.5, 2]},
      {"primary": "push_left", "accents": ["iris"], "duration_frames": 14, "cut_ratio": .4},
      {"effect": "spring", "role": "headline", "case": "sentence"}, {"tone": "social"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["icons and simple shapes, one idea per scene", "patterned background", "objects arrive in the order they are explained"],
      ["photoreal grain", "noir grading", "thin hairline type"], ["kinetic_title", "map_journey"]),
    D("retro_vhs", "Băng VHS thập niên 80-90", ["nostalgia", "music", "gaming", "throwback"], "hoài niệm, vui", "medium",
      {"style_id": "technical_blueprint", "palette_id": "magenta", "heading_font_id": "oswald", "body_font_id": "ibmplexmono", "type": {"display": {"weight": 700, "tracking": .04}}},
      M("ease_out", .3, .08, .01, .03), {"seconds_per_idea": [1.5, 3.5], "dwell_s": [1.5, 2]},
      {"primary": "cut", "accents": ["flash", "zoom_in"], "duration_frames": 6, "cut_ratio": .7},
      {"effect": "type", "role": "display", "case": "upper"}, {"tone": "tutorial"},
      {"grain": .15, "leaks": "none", "vignette": .3, "looks": [{"type": "vhs", "intensity": .4}]},
      ["timestamp/REC chrome in a corner", "saturated magenta and cyan accents", "jump cuts"],
      ["clean glass UI", "thin serif", "long smooth dissolves"], ["kinetic_title", "speed_ramp"]),
    D("crt_terminal", "Màn hình CRT / hacker", ["cyber", "security", "coding", "retro computing"], "bí ẩn, kỹ thuật", "medium",
      {"style_id": "technical_blueprint", "palette_id": "forest", "heading_font_id": "ibmplexmono", "body_font_id": "ibmplexmono"},
      M("stepped", .4, .07, 0, 0, hold="still"), {"seconds_per_idea": [2, 4], "dwell_s": [1.5, 2]},
      {"primary": "cut", "accents": ["flash"], "duration_frames": 4, "cut_ratio": .85},
      {"effect": "type", "role": "headline", "case": "upper"}, {"tone": "tutorial"},
      {"grain": .08, "leaks": "none", "vignette": .45, "looks": [{"type": "scanlines", "intensity": .3}]},
      ["monospace grid, left aligned", "blinking cursor as continuity element", "green-on-black with one amber warning colour"],
      ["serif", "pastel", "bouncy motion", "light leaks"], ["kinetic_title", "tracked_callout"]),
    D("film_noir", "Film noir đen trắng", ["mystery", "true crime", "dramatic history"], "căng thẳng, u tối", "calm",
      {"style_id": "monochrome_focus", "palette_id": "noir", "heading_font_id": "oswald", "body_font_id": "lora", "type": {"display": {"weight": 600, "tracking": .08}}},
      M("dreamy", 1.0, .15, 0, .04, hold="still"), {"seconds_per_idea": [4, 7], "dwell_s": [2.5, 3.5]},
      {"primary": "dissolve", "accents": ["iris"], "duration_frames": 24, "cut_ratio": .5},
      {"effect": "tracking", "role": "display", "case": "upper"}, {"tone": "storytelling"},
      {"grain": .28, "leaks": "none", "vignette": .55, "looks": [{"type": "dust", "intensity": .3}], "grade": "grayscale+contrast"},
      ["hard shadows, low-key frames", "titles small and wide-spaced", "slow pushes into faces/objects"],
      ["colour accents (except one deliberate red)", "bouncy motion", "emoji"], ["photo_3d", "kinetic_title"]),
    D("nature_calm", "Thiên nhiên thư giãn", ["nature", "meditation", "wellness", "slow travel"], "yên bình", "calm",
      {"style_id": "ocean_calm", "palette_id": "ocean", "type": {"display": {"weight": 500}}},
      M("dreamy", 1.2, .2, .012, .04), {"seconds_per_idea": [4, 8], "dwell_s": [3, 4]},
      {"primary": "dissolve", "accents": [], "duration_frames": 30, "cut_ratio": .2},
      {"effect": "tracking", "role": "display", "case": "sentence"}, {"tone": "storytelling"},
      {"grain": .08, "leaks": "accents", "leak_colors": ["#ffe0a8", "#ffb38a"], "vignette": .2, "looks": []},
      ["horizon on thirds", "few words, long holds with ambient motion", "sound-led pacing"],
      ["flash", "whip", "shake", "hype captions"], ["photo_3d", "globe_dive"]),
    D("corporate_clean", "Doanh nghiệp sạch sẽ", ["company update", "training", "B2B explainer"], "chuyên nghiệp", "medium",
      {"style_id": "minimal_explainer", "palette_id": "studio_white"},
      M("ease_out", .4, .08, 0, .03, hold="still"), {"seconds_per_idea": [2.5, 4], "dwell_s": [1.5, 2]},
      {"primary": "push_left", "accents": ["dissolve"], "duration_frames": 12, "cut_ratio": .5},
      {"effect": "reveal", "role": "headline", "case": "sentence"}, {"tone": "corporate"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["lower thirds for people", "icons for steps", "brand accent on one element"],
      ["grain", "glitch", "hype slams"], ["kinetic_title", "tracked_callout"]),
    D("tutorial_code", "Hướng dẫn lập trình", ["coding tutorial", "PR walkthrough", "devlog"], "tập trung", "medium",
      {"style_id": "technical_blueprint", "palette_id": "electric", "heading_font_id": "inter", "body_font_id": "ibmplexmono"},
      M("snappy", .3, .06, 0, 0, hold="still"), {"seconds_per_idea": [3, 6], "dwell_s": [2, 3]},
      {"primary": "cut", "accents": ["push_up"], "duration_frames": 10, "cut_ratio": .7},
      {"effect": "type", "role": "headline", "case": "sentence"}, {"tone": "tutorial"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["code panel with highlighted lines", "cursor/selection as the focal motion", "diff colours only"],
      ["light leaks", "cinematic grain", "decorative 3D"], ["tracked_callout", "kinetic_title"]),
    D("collage_zine", "Collage / zine thủ công", ["art", "music", "youth culture", "fashion street"], "thô, sáng tạo", "high",
      {"style_id": "editorial_paper", "palette_id": "citrus", "heading_font_id": "oswald", "body_font_id": "lora", "type": {"display": {"weight": 700, "tracking": 0}}},
      M("stepped", .4, .15, 0, .02, hold="still", exit_ease="stepped"), {"seconds_per_idea": [1.5, 3], "dwell_s": [1, 2]},
      {"primary": "cut", "accents": ["wipe_up", "flash"], "duration_frames": 6, "cut_ratio": .75},
      {"effect": "word", "role": "display", "case": "upper"}, {"tone": "social"},
      {"grain": .2, "leaks": "none", "vignette": .1, "looks": [{"type": "dust", "intensity": .35}]},
      ["cut-out photos with hard edges", "stop-motion holds on 2-frame steps", "tape/marker accents"],
      ["glossy gradients", "3D chrome", "perfectly smooth motion"], ["kinetic_title", "photo_3d"]),
    D("action_trailer", "Trailer hành động", ["trailer", "sports highlight", "game launch", "event teaser"], "kịch tính", "high",
      {"style_id": "monochrome_focus", "palette_id": "crimson", "heading_font_id": "oswald", "type": {"display": {"weight": 700, "tracking": .08, "line_height": 1.1}}},
      M("dramatic", .5, .08, 0, .08), {"seconds_per_idea": [1, 2.5], "dwell_s": [1.5, 2.5]},
      {"primary": "flash", "accents": ["burn", "zoom_through"], "duration_frames": 8, "cut_ratio": .5},
      {"effect": "tracking", "role": "display", "case": "upper"}, {"tone": "hype"},
      {"grain": .15, "leaks": "accents", "leak_colors": ["#ff7a2e", "#ff2e3c"], "vignette": .5, "looks": [], "grade": "contrast", "letterbox": True},
      ["accelerating cut rhythm toward the title", "title cards on black between shots", "one silence before the climax"],
      ["pastel", "rounded fonts", "bouncy easing"], ["speed_ramp", "kinetic_title", "globe_dive"]),
    D("luxury_fashion", "Thời trang sang trọng", ["fashion", "beauty", "hospitality", "jewellery"], "thanh lịch", "calm",
      {"style_id": "culture_story", "palette_id": "rose", "heading_font_id": "lora", "body_font_id": "manrope", "type": {"display": {"weight": 400, "tracking": .18}, "label": {"tracking": .2}}},
      M("dreamy", 1.0, .18, .008, .03), {"seconds_per_idea": [3, 6], "dwell_s": [2.5, 3]},
      {"primary": "dissolve", "accents": ["iris"], "duration_frames": 24, "cut_ratio": .35},
      {"effect": "tracking", "role": "display", "case": "upper"}, {"tone": "storytelling"},
      {"grain": .1, "leaks": "none", "vignette": .25, "looks": []},
      ["letterspaced small caps", "symmetry and centred lockups", "muted palette, skin tones untouched"],
      ["heavy weights", "saturated colour", "bouncing", "flash cuts"], ["photo_3d", "text_behind_subject"]),
    D("kids_playful", "Vui nhộn cho trẻ", ["kids", "family", "toy", "learning game"], "vui tươi", "high",
      {"style_id": "friendly_learning", "palette_id": "citrus"},
      M("springy", .5, .1, .02, .03, overshoot=True), {"seconds_per_idea": [2, 3.5], "dwell_s": [1.5, 2]},
      {"primary": "iris", "accents": ["push_left", "zoom_in"], "duration_frames": 14, "cut_ratio": .3},
      {"effect": "spring", "role": "display", "case": "sentence"}, {"tone": "social"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["big rounded shapes", "characters/objects bounce on arrival", "bright primary accents"],
      ["dark grading", "grain", "harsh flashes", "small text"], ["kinetic_title", "map_journey"]),
    D("breaking_news", "Tin nóng", ["news", "update", "alert", "live event"], "khẩn trương", "high",
      {"style_id": "data_report", "palette_id": "crimson", "heading_font_id": "archivo", "type": {"headline": {"weight": 800}}},
      M("snappy", .25, .06, 0, .03, hold="still"), {"seconds_per_idea": [2, 3.5], "dwell_s": [1.5, 2]},
      {"primary": "push_left", "accents": ["wipe_left"], "duration_frames": 10, "cut_ratio": .6},
      {"effect": "reveal", "role": "headline", "case": "upper"}, {"tone": "corporate"},
      {"grain": 0, "leaks": "none", "vignette": 0, "looks": []},
      ["lower third with source/time", "red label for the live element only", "map for location"],
      ["light leaks", "slow dissolves", "decorative motion"], ["map_journey", "tracked_callout"]),
]}


def catalog(query="", energy=None, limit=30):
    words = [w for w in query.casefold().split() if w]
    out = []
    for d in DIRECTIONS.values():
        if energy and d["energy"] != energy:
            continue
        hay = " ".join([d["id"], d["name"], d["mood"], " ".join(d["genres"])]).casefold()
        if words and not any(w in hay for w in words):
            continue
        if len(words) != 1 or words[0] != d["id"]:  # browsing: one row each; an exact id returns the card
            out.append({"id": d["id"], "name": d["name"], "energy": d["energy"], "mood": d["mood"]})
            continue
        out.append({"id": d["id"], "name": d["name"], "genres": d["genres"], "mood": d["mood"], "energy": d["energy"],
                    "motion": f"{d['motion']['ease']} {d['motion']['entrance_s']}s, stagger {d['motion']['stagger_ratio']}, hold {d['motion']['hold']}",
                    "pacing_s": d["pacing"]["seconds_per_idea"], "transitions": [d["transitions"]["primary"], *d["transitions"]["accents"]],
                    "caption_tone": d["captions"]["tone"], "finish": {k: v for k, v in d["finish"].items() if v}, "hero_techniques": d["hero_techniques"]})
    return {"directions": out[:limit], "caption_tones": CAPTION_TONES,
            "how_to_choose": "Pick by audience, platform and the film's single idea, not by trend. Energy sets pacing before easing. "
                             "apply_direction writes the block into design.direction; recipes and audit_timeline follow it. Override any field."}


def get(direction_id):
    if direction_id not in DIRECTIONS:
        raise ValueError(f"Unknown direction {direction_id}; see style_directions()")
    return copy.deepcopy(DIRECTIONS[direction_id])


def merged(direction_id, overrides=None):
    d = get(direction_id)
    for k, v in (overrides or {}).items():
        if k not in d:
            raise ValueError(f"Unknown direction field {k}")
        d[k] = {**d[k], **v} if isinstance(d[k], dict) and isinstance(v, dict) else v
    return d


ENTRANCE = {"fade_in", "rise", "drop", "slide_left", "slide_right", "pop", "blur_in", "rotate_in", "flip_x", "flip_y", "wipe_left", "wipe_right",
            "wipe_up", "wipe_down", "iris", "tracking_in", "mask_reveal", "char_spring", "word_reveal", "line_reveal", "character_reveal",
            "marker_reveal", "underline_draw", "soft_edge_reveal", "diagonal_reveal", "diamond_reveal", "slide_spring", "spring", "decode", "typewriter"}
OPACITY_ONLY = {"fade_in"}
OVERSHOOT = {"bouncy", "springy"}


def restyle_ops(t, d):
    """Rewrite entrance/exit timing and curves to the direction, stagger simultaneous entrances (focal first, irregular
    offsets shorter than the animation), and add ambient idle to hero titles when the direction holds with life."""
    mo = d["motion"]
    ent = max(4, round(mo["entrance_s"] * FPS))
    ex = max(3, round(mo["exit_s"] * FPS))
    typo = (t.get("design") or {}).get("typography") or {}
    ops, changed = [], {"curves": 0, "staggered": 0, "idle": 0}
    layers = {l["id"]: copy.deepcopy(l) for l in t["layers"]}
    for l in layers.values():
        if l["kind"] in ("film", "scene3d", "video", "caption", "pattern"):
            continue
        dur = l["end_frame"] - l["start_frame"]
        touched = False
        for e in l.get("effects", []):
            if e["name"] in ENTRANCE and e.get("start_frame", 0) <= 2:
                curve = mo["ease"]
                if curve in OVERSHOOT and (e["name"] in OPACITY_ONLY or l["kind"] == "counter" or not mo["overshoot_transforms"]):
                    curve = "snappy"  # overshoot belongs to transforms, never to opacity or numbers
                length = round(ent * (1.4 if e["name"] in ("mask_reveal", "char_spring", "word_reveal", "line_reveal", "character_reveal") else 1))
                e.update(easing=curve, end_frame=max(e.get("start_frame", 0) + 1, min(dur - 1, e.get("start_frame", 0) + length)))
                touched = True
            elif e["name"] == "fade_out":
                start = max(0, dur - 1 - ex)
                e.update(easing=mo["exit_ease"] if mo["exit_ease"] != "stepped" else "stepped", start_frame=start, end_frame=dur - 1)
                touched = True
        if touched:
            changed["curves"] += 1
    # Stagger: layers of one shot that enter on the same frame. Focal (largest type / area) keeps its cue.
    groups = {}
    for l in layers.values():
        if l["kind"] in ("text", "shape", "icon", "svg", "counter", "image") and any(e["name"] in ENTRANCE for e in l.get("effects", [])):
            groups.setdefault((l.get("attach_shot"), l["start_frame"]), []).append(l)
    for (_, start), group in groups.items():
        if len(group) < 2:
            continue
        size = lambda l: (typo.get(l.get("typography_role") or "", {}).get("size") or l.get("font_size", 0)) if l["kind"] == "text" else l["width"] * l["height"] * 400
        group.sort(key=size, reverse=True)
        step = max(2, round(ent * mo["stagger_ratio"] * 1.6))
        acc = 0
        for i, l in enumerate(group[1:], 1):
            acc += max(2, round(step * (1 + .35 * ((i * 7) % 3 - 1))))  # irregular: never two identical offsets in a row
            acc = min(acc, ent - 1) if ent > 2 else acc
            if l["start_frame"] + acc < l["end_frame"] - 8:
                l["start_frame"] += acc
                for e in l.get("effects", []):
                    if e.get("start_frame", 0) > 0:
                        e["start_frame"] = max(0, e["start_frame"] - acc)
                        e["end_frame"] = max(e["start_frame"] + 1, e["end_frame"] - acc)
                changed["staggered"] += 1
    if mo["hold"] == "ambient" and mo["ambient_idle"] > 0:
        for l in layers.values():
            if l["kind"] == "text" and l.get("typography_role") in ("display", "headline") and not any(e["name"] in ("pulse", "float") for e in l.get("effects", [])):
                dur = l["end_frame"] - l["start_frame"]
                if dur > ent + 45 and len(l.get("effects", [])) < 15:
                    l.setdefault("effects", []).append({"name": "pulse", "start_frame": ent, "end_frame": dur - 1, "easing": "linear",
                                                         "params": {"amount": mo["ambient_idle"], "cycles": max(1, round((dur - ent) / FPS / 4))}})
                    changed["idle"] += 1
    for lid, l in layers.items():
        orig = next(x for x in t["layers"] if x["id"] == lid)
        if l != orig:
            ops.append({"op": "upsert_layer", "layer": l})
    return ops, changed


def finish_ops(t, d):
    f = d["finish"]
    N = t["total_frames"]
    ops = []
    if f.get("grain"):
        ops.append({"op": "upsert_layer", "layer": {"id": "dir-grain", "kind": "film", "start_frame": 0, "end_frame": N, "x": 0, "y": 0, "width": 1, "height": 1,
                                                    "z": 900, "blend": "overlay", "data": {"type": "grain", "intensity": f["grain"], "scale": .9}}})
    for i, look in enumerate(f.get("looks", [])):
        ops.append({"op": "upsert_layer", "layer": {"id": f"dir-look{i}", "kind": "film", "start_frame": 0, "end_frame": N, "x": 0, "y": 0, "width": 1, "height": 1,
                                                    "z": 905 + i, "blend": "normal" if look["type"] != "dust" else "screen", "data": {**look, "seed": 11 + i}}})
    if f.get("leaks") == "accents":
        accents = set(d["transitions"]["accents"]) | ({d["transitions"]["primary"]} if d["transitions"]["primary"] in ("flash", "burn") else set())
        at = [s["start_frame"] for s in t["shots"] if (s.get("transition") or {}).get("name") in accents]
        colors = f.get("leak_colors") or ["#ffb347", "#ff5a3c"]
        for i, fr in enumerate(at[:6]):
            a, b = max(0, fr - 26), min(N, fr + 40)
            ops.append({"op": "upsert_layer", "layer": {"id": f"dir-leak{i}", "kind": "film", "start_frame": a, "end_frame": b, "x": 0, "y": 0, "width": 1,
                                                        "height": 1, "z": 890, "blend": "screen",
                                                        "data": {"type": "light_leak", "intensity": .7, "color": colors[0], "secondary_color": colors[1], "speed": 2, "seed": 3 + 4 * i},
                                                        "effects": [{"name": "fade_in", "end_frame": 14}, {"name": "fade_out", "start_frame": int((b - a) * .6), "end_frame": b - a - 1}]}})
    return ops


def apply(pid, base_revision, direction_id, overrides=None, restyle=False, finish=False, dry_run=False):
    from .design_library import tokens
    from .models import Design
    d = merged(direction_id, overrides)
    p = agent.read(pid)
    t = p.get("timeline")
    if not t or p["revision"] != base_revision:
        raise ValueError("Read the current project revision (locked plan) before applying a direction")
    look = d["look"]
    design = tokens(look["style_id"], look.get("palette_id"), look.get("heading_font_id"), look.get("body_font_id"))
    for role, ch in (look.get("type") or {}).items():
        if role in design["typography"]:
            design["typography"][role].update(ch)
    for role, color in (look.get("colors") or {}).items():
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Direction colours use #RRGGBB")
        design["color_roles"][role] = color
    design["direction"] = {k: d[k] for k in ("id", "name", "energy", "motion", "pacing", "transitions", "titles", "captions", "finish", "composition", "negative")}
    Design.model_validate({**(t.get("design") or {}), **design})
    ops = [{"op": "set_design", "design": design}]
    summary = {}
    future = copy.deepcopy(t)
    future["design"] = {**(t.get("design") or {}), **design}
    if restyle:
        r_ops, summary = restyle_ops(future, d)
        ops += r_ops
    if finish:
        ops += finish_ops(t, d)
    if len(ops) > 100:
        raise ValueError(f"{len(ops)} operations; apply in two steps (restyle then finish)")
    revision = None if dry_run else agent.patch(pid, base_revision, ops)["revision"]
    tr = d["transitions"]
    return {"revision": revision, "direction": d["id"], "restyled": summary, "operations": len(ops), "dry_run": dry_run,
            "follow": {"transitions": f"primary {tr['primary']} for most seams ({tr['duration_frames']} frames{', live' if tr.get('mode') == 'live' else ''}), "
                                      f"accents {tr['accents']} only at pivots; about {int(tr['cut_ratio'] * 100)}% straight cuts",
                       "pacing": f"{d['pacing']['seconds_per_idea'][0]}–{d['pacing']['seconds_per_idea'][1]} s per idea, dwell {d['pacing']['dwell_s']} s on hero beats, one breather",
                       "titles": d["titles"], "captions": {**CAPTION_TONES[d["captions"]["tone"]], "tone": d["captions"]["tone"]},
                       "composition": d["composition"], "negative": d["negative"], "hero_techniques": d["hero_techniques"]},
            **({"ops": ops} if dry_run else {}),
            "next": "Transitions and pacing stay the AI's decision per seam: apply them with update_shot using the vocabulary above; "
                    "audit_timeline then reports drift from the direction."}
