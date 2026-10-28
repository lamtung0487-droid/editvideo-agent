"""What kind of picture each shot is, and how a film mixes them: archive film, present-day footage, stage performance,
painterly or AI-made imagery, 3D graphics, maps and cards, interviews, aerial landscapes, an audience. Round 13: the owner
sent a CCTV gala that mixes stage, LED video, archive and AI imagery, and asked the system to learn how such films combine
them. The sense is zero-shot (SigLIP base/16-224, local), so it is an estimate: each category comes with its strongest
shots as evidence, for Claude to look at before trusting a share.
"""
import numpy as np

# Each category is an average of a few English prompts (SigLIP reads English best); the order is the report's order.
CATEGORIES = {
    "archive": ["old black and white archival film footage", "grainy vintage newsreel footage", "faded historical colour film from the 1960s"],
    "present_footage": ["modern documentary footage of a city street", "present-day colour video of people outdoors", "a sharp modern video of a landscape"],
    "stage": ["a stage performance in a theater with dancers and stage lights", "singers performing on a concert stage",
              "performers in front of a giant LED screen on a stage"],
    "painterly_ai": ["an AI-generated digital painting", "a painterly illustration with dramatic light", "a surreal digital artwork",
                     "a traditional ink wash painting"],
    "cgi": ["a 3D computer graphics render", "a computer-animated scene", "a video game style 3D scene"],
    "graphic": ["a map with arrows and labels", "an infographic with numbers and charts", "a title card with text on a dark background"],
    # a filmed drama with actors is neither archive nor present-day reality: a gala's or a docudrama's reconstruction
    "reenactment": ["a cinematic historical drama scene with actors in period military uniforms",
                    "a film still of soldiers in a historical reenactment with dramatic lighting"],
    "performance_closeup": ["a close-up of a singer performing with emotion on stage", "an actor in costume singing in close-up under stage lights"],
    "interview": ["a news interview with a person sitting and talking to a reporter", "a talking head interview in an office or a home"],
    "aerial": ["an aerial drone shot of a landscape", "a wide aerial view of mountains and rivers"],
    "audience": ["an audience in a theater watching a show", "a crowd of people applauding in an auditorium"],
}
MIN_MARGIN = .004  # cosine gap between the top two categories under which a shot counts as "mixed"


def category_vectors():
    from .semantic import _text_vector
    out = {}
    for k, prompts in CATEGORIES.items():
        v = np.mean([_text_vector(p) for p in prompts], axis=0)
        out[k] = v / np.linalg.norm(v)
    return out


def classify(shot_vectors, cats):
    """shot_vectors: (n, d) unit vectors, one per shot; cats: {name: unit vector}. Returns per shot (category, margin),
    "mixed" where the top two are within MIN_MARGIN."""
    names = list(cats)
    m = np.stack([cats[k] for k in names])
    sims = shot_vectors @ m.T
    out = []
    for row in sims:
        o = np.argsort(row)[::-1]
        margin = float(row[o[0]] - row[o[1]])
        out.append((names[o[0]] if margin >= MIN_MARGIN else "mixed", round(margin, 4), float(row[o[0]])))
    return out


def mix(shots, labels):
    """shots: [(start, end)]; labels: [(category, margin, score)]. Shares of runtime per category, how often a cut changes
    category, and the median run of shots in one category."""
    total = sum(b - a for a, b in shots) or 1.0
    share = {}
    for (a, b), (c, _, _) in zip(shots, labels):
        share[c] = share.get(c, 0.0) + (b - a) / total
    cats = [c for c, _, _ in labels]
    switches = sum(1 for x, y in zip(cats, cats[1:]) if x != y)
    runs, n = [], 1
    for x, y in zip(cats, cats[1:]):
        if x == y:
            n += 1
        else:
            runs.append(n); n = 1
    runs.append(n)
    pairs = {}
    for x, y in zip(cats, cats[1:]):
        if x != y:
            pairs[f"{x}>{y}"] = pairs.get(f"{x}>{y}", 0) + 1
    return {"share": {k: round(v, 3) for k, v in sorted(share.items(), key=lambda kv: -kv[1])},
            "switch_share": round(switches / max(1, len(cats) - 1), 3), "median_run_shots": float(np.median(runs)) if runs else 0.0,
            "pairs": dict(sorted(pairs.items(), key=lambda kv: -kv[1])[:12])}  # how the film moves between kinds of picture


def measure(path, shots, fps=None):
    """Classify every shot [(start, end)] of `path` from its frames' SigLIP vectors (semantic.embeddings over the whole
    video, cached; three square crops per frame averaged) and return the mix, the per-shot labels and, per category, its
    three strongest shots as evidence. fps defaults to 1, fewer on long films (about 1,500 frames at most)."""
    from .semantic import embeddings
    from .media import probe
    if fps is None:
        dur = float(probe(str(path))["format"].get("duration") or 0)
        fps = round(min(1.0, max(.1, 1500 / max(dur, 1.0))), 3)
    times, vecs = embeddings(str(path), fps, whole=True)
    times = np.asarray(times, float)
    vecs = vecs.astype(np.float32).mean(axis=1)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    keep, shot_vecs = [], []
    for a, b in shots:
        idx = np.where((times >= a) & (times < b))[0]
        if not len(idx):
            idx = np.array([int(np.argmin(np.abs(times - (a + b) / 2)))])
        v = vecs[idx].mean(axis=0)
        shot_vecs.append(v / (np.linalg.norm(v) + 1e-9))
        keep.append((a, b))
    labels = classify(np.stack(shot_vecs), category_vectors())
    out = mix(keep, labels)
    best = {}
    for (a, b), (c, margin, score) in zip(keep, labels):
        best.setdefault(c, []).append((score, round(a, 2), round(b, 2)))
    out["evidence"] = {c: [[a, b] for _, a, b in sorted(v, reverse=True)[:3]] for c, v in best.items()}
    out["shots"] = [{"t": [round(a, 2), round(b, 2)], "category": c, "margin": m} for (a, b), (c, m, _) in zip(keep, labels)]
    out["method"] = ("SigLIP base/16-224 zero-shot at 1 fps, prompts averaged per category, frames averaged per shot; an estimate "
                     "to verify on the evidence shots")
    return out
