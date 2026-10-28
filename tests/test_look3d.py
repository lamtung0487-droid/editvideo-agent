"""The 3D look's measurable rules (2026-10-27): the sun follows the light baked into imagery."""
import numpy as np


def test_the_light_baked_into_imagery_is_found(tmp_path):
    from PIL import Image
    from editvideo import terrain
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(3)
    h = gaussian_filter(rng.normal(0, 1, (256, 256)), 2.5) * 4000  # ridges a few samples wide, as a real DEM has
    bbox = (103.0, 21.2, 103.3, 21.5)
    cell = (bbox[2] - bbox[0]) * 111320 * np.cos(np.radians(21.35)) / 256
    shade = terrain.hillshade(h, cell, 150, 35)
    tex = np.clip(80 + 120 * shade + rng.normal(0, 6, shade.shape), 0, 255).astype(np.uint8)
    path = tmp_path / "t.jpg"
    Image.fromarray(tex).resize((768, 768)).save(path)
    az, r = terrain.imagery_light(path, h, bbox)
    assert abs(terrain._turn(az, 150)) <= 15 and r > .5
    assert terrain._turn(350, 10) == 20 and terrain._turn(10, 350) == -20
