"""Counts quoted in README.md, generated from the live registries (tests/test_round6.py checks the README against them).
Usage: python scripts/repo_facts.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def facts():
    from editvideo import mcp_server, effects, explainer, titles, professional, __version__
    from editvideo.models import Layer
    from editvideo import design_library as dl
    kinds = Layer.model_fields["kind"].annotation.__args__
    fonts = json.loads((ROOT / "assets/fonts/manifest.json").read_text(encoding="utf-8"))
    families = fonts.get("fonts") or fonts.get("families") or fonts
    return {"version": __version__, "tools": len(mcp_server.TOOL_REGISTRY), "effects": effects.catalog()["total"], "layer_kinds": len(kinds),
            "explainer_recipes": len(explainer.RECIPES), "title_recipes": len(titles.RECIPES), "font_families": len(families),
            "palettes": len(dl.PALETTE_ROWS), "style_kits": len(dl.STYLE_ROWS), "luts": len(json.loads((ROOT / "assets/luts/manifest.json").read_text(encoding="utf-8"))["luts"])}


if __name__ == "__main__":
    print(json.dumps(facts(), indent=1))
