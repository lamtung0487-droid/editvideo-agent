"""One entry point for hosts: learn(action, request). An empty action returns the contract."""
from . import blueprint, compare, core, senses


def contract():
    return {
        "loop": "register works that succeeded (and some that did not) -> signals (evidence, with a baseline) -> anatomy (label "
                "parts with roles) -> evidence (look at a span) -> compare (winners vs controls) -> distill (blueprint) -> make "
                "your work -> conform (measure it against the blueprint) -> apply (log its real outcome)",
        "kinds": senses.kinds(),
        "spans": {"t": "[start_s, end_s] (video, audio, timed text)", "box": "[x, y, w, h] fractions (image, web screenshot)",
                  "chars": "[a, b] character offsets in the NFC, LF-newline text (its length is feature text_chars)",
                  "section": "block index (web page; see parts)"},
        "actions": {
            "register": {"path": "local file", "kind?": "inferred from the extension", "domain": "e.g. 'tiktok product ad'",
                         "title?": "", "usage?": "licence/limits", "options?": "{'screenshot': png} for a web page", "sidecar?": "yt-dlp .info.json"},
            "signals": {"exemplar_id": "ex-…", "signals?": [{"metric": "views", "value": 0, "unit": "", "baseline": "same metric for "
                        "the usual work", "baseline_note": "what the baseline is", "source": "|".join(("platform_metadata", "analytics_export",
                        "caller_report", "sales", "ab_test", "award", "survey")), "as_of": "YYYY-MM-DD"}],
                        "ytdlp?": "info.json path", "csv?": {"path": "export.csv", "metrics?": {"name": "column"}, "row?": {"column": "", "equals": ""},
                                                             "decimal?": ". or ,", "baseline?": "others: median of the other rows",
                                                             "baselines?": {"name": {"baseline": 0, "baseline_note": ""}},
                                                             "curve?": {"time": "column", "value": "column", "meaning": ""}}},
            "anatomy": {"exemplar_id": "ex-…", "parts": [{"role": "hook|problem|demo|proof|offer|cta|…", "span": {}, "note": ""}]},
            "evidence": {"exemplar_id": "ex-…", "span": {}},
            "compare": {"winners+controls": ["ex-…"], "or split": {"metric": "views", "relative": True, "top": .33, "bottom": .33},
                        "exemplars?|kind?|domain?": "the pool for a split", "features?": ["names to show (all are tested)"]},
            "distill": {"blueprint": {"title": "", "kind": "", "domain": "", "purpose": "", "structure": [{"role": "", "share": [0, 1],
                                      "start": [0, 1]}], "targets": [{"feature": "", "range": [0, 1], "provenance": "comparison|exemplars|chosen",
                                      "comparison_id": "cmp-…"}], "steps": [""], "principles": "", "when_to_use": "", "avoid": "",
                                      "exemplars": ["ex-…"], "comparisons": ["cmp-…"], "level?": "observation|candidate|rule|standard"},
                        "blueprint_id?": "bp-… to update", "base_revision?": 0},
            "conform": {"blueprint_id": "bp-…", "path": "your work", "options?": {}, "anatomy?": [{"role": "", "span": {}}]},
            "apply": {"blueprint_id": "bp-…", "path": "your work", "outcome": [{"metric": "", "value": 0, "baseline": 0, "baseline_note": ""}],
                      "outcome_csv?": {"path": "export.csv", "metrics": {"name": "column"}, "row": {"column": "", "equals": ""},
                                       "baseline": "others (the median of the other rows, read here)", "decimal?": ""},
                      "kept": True, "note": "what changed and how it was received"},
            "library": {"query?": "", "kind?": "", "item_id?": "ex-…|cmp-…|bp-…", "offset?": 0, "limit?": 10}},
        "levels": blueprint.__doc__.split("Levels", 1)[1].split("conform measures", 1)[0].strip(),
        "rules": ["Evidence of success needs a baseline: raw reach mostly measures audience size.",
                  "Look at the evidence before generalising; comparisons are associations in small samples, not causes.",
                  "Never reuse a studied work's imagery, audio or text; write blueprints in your own words.",
                  "Downloading new works needs the user's approval for each batch (name, source, size)."]}


def learn(action="", request=None):
    request = request or {}
    if not action:
        return contract()
    if action == "register":
        return core.register(request)
    if action == "signals":
        return core.add_signals(request)
    if action == "anatomy":
        return core.anatomy(request)
    if action == "evidence":
        return core.evidence(request)
    if action == "compare":
        return compare.compare(request)
    if action == "distill":
        extra = set(request) - {"blueprint", "blueprint_id", "base_revision"}
        if extra or "blueprint" not in request:
            raise ValueError("distill takes {blueprint, blueprint_id?, base_revision?}")
        return blueprint.distill(request["blueprint"], request.get("blueprint_id"), request.get("base_revision"))
    if action == "conform":
        return blueprint.conform(request.get("blueprint_id"), request.get("path"), request.get("options"), request.get("anatomy"))
    if action == "apply":
        return blueprint.apply(request)
    if action == "library":
        return core.library(request)
    raise ValueError("action is one of register, signals, anatomy, evidence, compare, distill, conform, apply, library (empty: contract)")
