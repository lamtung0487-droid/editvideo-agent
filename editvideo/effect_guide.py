"""How effects combine: per-effect pairing and avoid notes, plus rendered combination recipes.

The catalog says what an effect does; this says when it helps and what it fights with, so a model choosing among 91
effects can stack two or three that agree instead of many that compete. Family defaults cover every effect; specific
notes override them. Combos are small, rendered stacks (see assets/previews/effect-atlas.json) with the parameters
that held up, the purpose they serve and what to avoid around them.
"""

FAMILY = {
    "entrance": {"pairs": ["fade_in"], "avoid": "Three or more moves at once (audit: compound_motion); a different entrance on every sibling; entrances on body text being read mid-sentence."},
    "exit": {"pairs": ["fade_in"], "avoid": "Exits longer than the entrance; exiting before the line has been read."},
    "camera": {"pairs": ["vignette"], "avoid": "Two camera moves fighting (handheld + shake, focus_zoom + zoom_in); pushes on text that must be read."},
    "motion": {"pairs": ["fade_in"], "avoid": "Loops on text being read; several looping elements competing for the eye in one frame."},
    "reveal": {"pairs": ["fade_in"], "avoid": "Two reveals at once in different directions; reveals on footage that must stay readable as evidence."},
    "text": {"pairs": ["shadow"], "avoid": "More than one text animation on a line; character animations on long sentences (reading time doubles)."},
    "light": {"pairs": ["vignette"], "avoid": "Glows on light/white backgrounds (they wash out); stacking bloom, highlight_glow and halation all strong."},
    "grade": {"pairs": ["vignette"], "avoid": "Creative looks on evidence footage (keep it to technical correction); a different look per shot (audit: color_consistency)."},
    "mask": {"pairs": ["fade_in"], "avoid": "Hard mask edges on organic footage without feather; masking text so it reads as cropped."},
    "texture": {"pairs": ["vignette"], "avoid": "Heavy textures under small text; animated textures on a calm documentary beat."},
    "frame": {"pairs": ["vignette"], "avoid": "Letterbox plus border plus vignette together (the frame shrinks twice)."},
    "data": {"pairs": ["fade_in"], "avoid": "Animating numbers past their final value (overshoot on data reads as error)."},
}

# Specific notes (the effects the first atlas lacked first; then the most-used ones).
NOTES = {
    "slide_spring": {"pairs": ["motion_blur", "tracking", "shadow"], "avoid": "Adding fade_in (it carries its own short opacity ramp); amounts that start the text far outside the frame on a vertical canvas; springs on several lines at once."},
    "bloom": {"pairs": ["highlight_glow", "radial_glow"], "avoid": "Bright full-frame footage (everything glows); amount above ~24 on body text."},
    "boil": {"pairs": ["jitter", "paper_grain"], "avoid": "Clean corporate/data graphics; boil on photographs (it reads as a broken encode)."},
    "char_spring": {"pairs": ["shadow", "tracking"], "avoid": "Sentences longer than ~4 words; pairing with another character animation."},
    "clock_wipe": {"pairs": ["progress", "fade_in"], "avoid": "Reveals of rectangular cards (a radial sweep on a box looks arbitrary); amount != ±1 for a full turn."},
    "color_to": {"pairs": ["fade_in", "rise"], "avoid": "A colour flash the palette does not contain; colour arrivals on every line."},
    "decode": {"pairs": ["rgb_split", "scanlines"], "avoid": "Calm documentary or luxury tones; decoding Vietnamese words with marks the scramble glyphs lack (keep ASCII titles)."},
    "gate_weave": {"pairs": ["tritone", "halation", "paper_grain"], "avoid": "Modern UI graphics; weave on top of handheld (two wobbles)."},
    "glitch": {"pairs": ["rgb_split", "scanlines"], "avoid": "More than one burst every few seconds; glitch on evidence footage."},
    "halation": {"pairs": ["tritone", "gate_weave", "bloom"], "avoid": "Footage with no highlights (nothing to scatter); strong halation together with strong bloom."},
    "handheld": {"pairs": ["focus_zoom", "vignette"], "avoid": "Graphics and text plates (they should feel locked); amounts above ~8 px for documentary."},
    "heat_distortion": {"pairs": ["luma_alpha", "radial_glow"], "avoid": "Text and faces (it melts them); amounts above ~10 px."},
    "highlight_glow": {"pairs": ["bloom", "light_sweep"], "avoid": "Low threshold on bright footage (whole frame glows); anamorphic streaks in a calm documentary."},
    "jitter": {"pairs": ["boil", "paper_grain"], "avoid": "Readable body text; jitter on photographs of people."},
    "light_wrap": {"pairs": ["shadow", "tint_fill"], "avoid": "params.color not sampled from the actual backdrop; wraps on layers that are not cut out."},
    "luma_alpha": {"pairs": ["heat_distortion", "bloom"], "avoid": "Content that is not on black (mid-greys turn half transparent); light content over a white backdrop."},
    "mask_reveal": {"pairs": ["tracking", "shadow"], "avoid": "Single long lines that wrap; pairing with fade_in (the mask already reveals)."},
    "motion_blur": {"pairs": ["slide_spring", "spring", "rise"], "avoid": "Static layers (it does nothing); shutter above 270 on slow moves (smear without speed)."},
    "rgb_split": {"pairs": ["glitch", "decode", "scanlines"], "avoid": "Small text (fringes make it unreadable); amounts above ~6 px outside a glitch accent."},
    "text_animate": {"pairs": ["shadow", "tracking"], "avoid": "Animating every unit of a long paragraph; mixing modes in one line."},
    "tint_fill": {"pairs": ["light_wrap", "shadow"], "avoid": "Layers without alpha (the whole box fills); tinting faces."},
    "tracking": {"pairs": ["fade_in", "mask_reveal"], "avoid": "Body text; tracking Vietnamese words wide enough that marks drift from their letters."},
    "tritone": {"pairs": ["gate_weave", "halation", "paper_grain"], "avoid": "Evidence where colour carries meaning (maps, charts, skin); mixing tritone shots with full-colour shots in one sequence."},
    "progress": {"pairs": ["fade_in", "clock_wipe"], "avoid": "Progress on a static picture with nothing to count; use the counter layer kind for numbers."},
    "focus_zoom": {"pairs": ["handheld", "vignette"], "avoid": "Pushing on text that must be read; combining with zoom_in on the same layer."},
    "typewriter": {"pairs": ["shadow"], "avoid": "Paragraphs (reading time explodes); typewriter plus another text animation."},
    "word_reveal": {"pairs": ["shadow", "underline_draw"], "avoid": "Long sentences on screen with narration (they compete)."},
    "shake": {"pairs": ["flash"], "avoid": "Using it as constant motion; shake plus handheld."},
    "flash": {"pairs": ["shake", "glitch"], "avoid": "More than one flash per beat (photosensitivity); flashes on white frames."},
    "vignette": {"pairs": ["tritone", "focus_zoom"], "avoid": "Strong vignettes on data graphics or UI."},
    "blur_in": {"pairs": ["fade_in"], "avoid": "Long blur-ins on text (it is unreadable while blurred)."},
}

COMBOS = {
    "archival_film": {"purpose": "Turn a clean image or 3D render into a believable archival plate (1960s-70s film).",
                      "stack": [{"name": "tritone", "params": {"amount": .6, "shadow_color": "#120c07", "color": "#8a6a46", "highlight_color": "#f3e4c8"}},
                                {"name": "halation", "params": {"amount": .7, "threshold": .72, "radius": 16}},
                                {"name": "gate_weave", "params": {"amount": 1.2}}, {"name": "vignette", "params": {"amount": .35}}],
                      "avoid": "Applying it to evidence you also show in colour; adding handheld on top."},
    "impact_title": {"purpose": "A title that lands hard on a beat: fast slide with shutter blur, tracking settling, highlight bloom.",
                     "stack": [{"name": "slide_spring", "params": {"amount": 260}}, {"name": "motion_blur", "params": {"amount": 220}},
                               {"name": "tracking", "params": {"amount": .04, "from_em": .3}}, {"name": "highlight_glow", "params": {"amount": .8, "threshold": .7, "radius": 18}}],
                     "target": "text",
                     "avoid": "Using it on more than one line at a time; a second entrance (fade_in) on the same title."},
    "neon_tech": {"purpose": "Tech/cyber accent: decoding title with a little chromatic fringe and soft neon bloom.",
                  "stack": [{"name": "decode", "params": {"amount": 1}}, {"name": "rgb_split", "params": {"amount": 3}}, {"name": "bloom", "params": {"amount": 14, "color": "#5ad1ff"}}],
                  "target": "text", "avoid": "Documentary or luxury tone; Vietnamese words with marks under decode (use ASCII or tracking)."},
    "handmade_collage": {"purpose": "Cut-out collage / zine feel: stepped tremble, line boil and paper texture.",
                         "stack": [{"name": "jitter", "params": {"amount": 3}}, {"name": "boil", "params": {"amount": 3}}, {"name": "paper_grain", "params": {"amount": .25}}],
                         "avoid": "Data graphics that must read precisely; mixing with smooth easing elsewhere in the same frame."},
    "fire_composite": {"purpose": "Fire, sparks or light leaks shot on black composited over a plate: luma key, additive blend, heat haze.",
                       "stack": [{"name": "luma_alpha", "params": {"amount": 1, "clip_black": .05, "clip_white": .6}}, {"name": "heat_distortion", "params": {"amount": 5}},
                                 {"name": "bloom", "params": {"amount": 12, "color": "#ff9a3c"}}],
                       "target": "fire", "avoid": "Keying content that is not on black; heat haze over faces or text."},
    "cutout_integration": {"purpose": "Make a cut-out subject sit in its backdrop: backdrop light wrapping its edges plus a contact shadow.",
                           "stack": [{"name": "light_wrap", "params": {"amount": .7, "radius": 14, "color": "#ffd7a0"}}, {"name": "shadow", "params": {"amount": 24}}],
                           "target": "cutout", "avoid": "A wrap colour that is not sampled from the backdrop; wraps without a matching shadow direction."},
    "documentary_push": {"purpose": "A calm observational push that keeps a still alive: slow focus zoom, slight handheld, soft vignette.",
                         "stack": [{"name": "focus_zoom", "params": {"amount": .12, "focus_x": .6, "focus_y": .45}}, {"name": "handheld", "params": {"amount": 3}},
                                   {"name": "vignette", "params": {"amount": .3}}],
                         "avoid": "Text that must be read inside the push; adding gate_weave (two wobbles)."},
}


def guide(effect_id, family):
    base = FAMILY.get(family, {"pairs": [], "avoid": ""})
    note = NOTES.get(effect_id, {})
    pairs = [p for p in note.get("pairs", base["pairs"]) if p != effect_id]
    return {"pairs_with": pairs, "avoid": note.get("avoid", base["avoid"])}


def combos(detail=False):
    if not detail:
        return [{"id": k, "purpose": v["purpose"], "stack": [e["name"] for e in v["stack"]]} for k, v in COMBOS.items()]
    return [{"id": k, **v} for k, v in COMBOS.items()]
