"""Compare works that succeeded with works that did not, feature by feature, without pretending to know why.

Groups are given explicitly (winners/controls) or split by a success metric (by default its ratio to the baseline,
so a big channel does not win by size alone). For every comparable feature: group medians and spreads, Cliff's delta
(a rank effect size that needs no distribution assumption and suits small groups: |d| < .147 negligible, < .33 small,
< .474 medium, else large; Romano et al. 2006) and how consistently winners sit above or below the controls' median.
Small groups are marked exploratory, and a baseline that differs between the groups is reported as a confounder.
Differences are leads for the caller to inspect, not causes.

Copies count once: every statistic is computed on distinct works (one representative per group of copies, the median
of its members); a work whose copies sit on both sides (A/B variants of one work) is left out of the groups and its
variants are compared within the work instead (a sign test across such works). Every feature both groups measure is
tested (asking for some features only narrows what is shown), each with an exact permutation test of Cliff's delta
(a normal approximation past 80 works), and corrected for testing them all, in two families: the sense's own
measurements, and the roles the caller labelled (labels are the caller's, so they never dilute the correction of the
measurements). q is Benjamini-Hochberg (a false-discovery rate, for reading); p_holm is Holm's adjusted p (what gates
use: adding look-alike or invented features cannot lower it).
"""
import math
import statistics
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import core, fingerprint, signals as sig, store

EXACT_MAX_WORKS = 80  # exact null distribution of the rank sum up to this many distinct works, normal approximation above
EVAL_VERSION = "4"
TEST = ("two-sided permutation test of Cliff's delta on distinct works (exact to 80 works, then normal approximation); "
        "per family (sense measurements, labelled roles): q Benjamini-Hochberg, p_holm Holm")


class Split(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    relative: bool = True  # use the ratio to the baseline when the signal has one
    top: float = Field(default=1 / 3, gt=0, lt=1)
    bottom: float = Field(default=1 / 3, gt=0, lt=1)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    exemplars: list[str] = Field(default_factory=list, max_length=500)
    kind: str | None = None
    domain: str | None = None
    split: Split | None = None
    winners: list[str] = Field(default_factory=list, max_length=250)
    controls: list[str] = Field(default_factory=list, max_length=250)
    features: list[str] = Field(default_factory=list, max_length=60)
    metric: str | None = None  # with explicit groups: the success metric they should be separated on
    relative: bool = True
    note: str = Field(default="", max_length=400)

    @model_validator(mode="after")
    def distinct(self):
        for name in ("exemplars", "winners", "controls"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} lists an id twice; each work counts once")
        return self


def cliffs_delta(xs, ys):
    gt = sum(1 for x in xs for y in ys if x > y)
    lt = sum(1 for x in xs for y in ys if x < y)
    return (gt - lt) / (len(xs) * len(ys))


def magnitude(d):
    d = abs(d)
    return "negligible" if d < .147 else "small" if d < .33 else "medium" if d < .474 else "large"


def _midranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    ranks, i = [0.0] * len(v), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return np.array(ranks)


def _rank_sum_counts(doubled, n):
    """How many ways n of the pooled works reach each doubled rank sum (dynamic programming over the works)."""
    total = int(doubled.sum())
    ways = np.zeros((n + 1, total + 1))
    ways[0, 0] = 1
    for i, r in enumerate(int(v) for v in doubled):
        for k in range(min(i + 1, n), 0, -1):
            ways[k, r:] += ways[k - 1, :total + 1 - r]
    return ways[n]


def permutation_p(xs, ys, alternative="two-sided"):
    """p-value of Cliff's delta under every relabelling of the works (delta = 2U/nm - 1 from midranks, so ties count half).
    alternative "greater" / "less" asks whether the first group is higher / lower."""
    n, m = len(xs), len(ys)
    values = list(xs) + list(ys)
    ranks = _midranks(values)
    to_delta = lambda doubled_sum: 2 * (doubled_sum / 2 - n * (n + 1) / 2) / (n * m) - 1
    observed = to_delta(2 * ranks[:n].sum())
    if n + m <= EXACT_MAX_WORKS:
        counts = _rank_sum_counts(np.rint(2 * ranks).astype(int), n)
        d = to_delta(np.arange(len(counts)))
        hit = d >= observed - 1e-9 if alternative == "greater" else d <= observed + 1e-9 if alternative == "less" \
            else np.abs(d) >= abs(observed) - 1e-9
        return float(counts[hit].sum() / counts.sum())
    big = n + m
    ties = sum(c ** 3 - c for c in (values.count(v) for v in set(values)))
    sd = math.sqrt(n * m / 12 * ((big + 1) - ties / (big * (big - 1))))
    u = (observed + 1) * n * m / 2
    z_hi, z_lo = (u - n * m / 2 - .5) / (sd or 1e-9), (u - n * m / 2 + .5) / (sd or 1e-9)
    upper, lower = .5 * math.erfc(z_hi / math.sqrt(2)), 1 - .5 * math.erfc(z_lo / math.sqrt(2))
    return min(1.0, upper if alternative == "greater" else lower if alternative == "less" else 2 * min(upper, lower))


def holm(ps, m=None):
    """Holm's step-down adjusted p-values, in the order given, for a family of m tests (at least those given)."""
    m, out, prev = max(len(ps), m or 0), [1.0] * len(ps), 0.0
    for rank, i in enumerate(sorted(range(len(ps)), key=lambda i: ps[i])):
        prev = max(prev, min(1.0, (m - rank) * ps[i]))
        out[i] = prev
    return out


def family(feature):
    return "role" if feature.startswith("role_") else "sense"


def bh(ps):
    """Benjamini-Hochberg q-values, in the order given."""
    m, q, prev = len(ps), [1.0] * len(ps), 1.0
    for rank, i in reversed(list(enumerate(sorted(range(m), key=lambda i: ps[i]), 1))):
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def represent(group):
    """One distinct work's numbers: the median over its copies of each feature they measure."""
    feats = [core.exemplar_features(e) for e in group]
    return {k: statistics.median([f[k] for f in feats if k in f]) for k in sorted({k for f in feats for k in f})}


def _iqr(v):
    if len(v) < 2:
        return 0.0
    q = statistics.quantiles(v, n=4, method="inclusive")
    return q[2] - q[0]


def separation(win, ctl, metric, relative):
    """Are the groups split by success itself? Every winner above every control on the metric (from current signals)."""
    if not metric:
        return None
    vw = [sig.value(e.get("signals"), metric, relative) for e in win]
    vc = [sig.value(e.get("signals"), metric, relative) for e in ctl]
    if None in vw + vc or min(vw) <= max(vc):
        return None
    return {"metric": metric, "relative": relative, "winners_min": min(vw), "controls_max": max(vc)}


def reach_confounded(win, ctl):
    """Groups that differ strongly in audience size: their differences may come from reach, not craft."""
    bw = [v for v in (sig.value(e.get("signals"), "followers") for e in win) if v is not None]
    bc = [v for v in (sig.value(e.get("signals"), "followers") for e in ctl) if v is not None]
    if len(bw) >= 2 and len(bc) >= 2 and abs(cliffs_delta(bw, bc)) >= .474:
        return f"groups differ in followers (delta {cliffs_delta(bw, bc):+.2f}): differences may come from audience size"
    return None


def _variants(both, side):
    """Works with variants on both sides (an A/B test): winner variants against control variants within each work,
    then a two-sided sign test across those works."""
    pairs = [(represent([e for e in g if side[e["id"]] == "w"]), represent([e for e in g if side[e["id"]] == "c"])) for g in both]
    rows = []
    for name in sorted({k for w, c in pairs for k in w if k in c}):
        diffs = [w[name] - c[name] for w, c in pairs if name in w and name in c]
        up, down = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
        if up + down:
            n, k = up + down, max(up, down)
            rows.append({"feature": name, "works": n, "winner_higher": up, "winner_lower": down,
                         "sign_p": round(min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n), 5)})
    rows.sort(key=lambda r: (r["sign_p"], r["feature"]))
    return {"works": len(pairs), "features": rows[:12]} if pairs else None


def _family_floor(kind):
    """The most measurements a sense can make, so a family is not made smaller by leaving out an option (a web
    page's screenshot adds 17)."""
    from . import senses
    try:
        return int(getattr(senses.get(kind), "features_max", 0))
    except ValueError:
        return 0


def _stats(fw, fc, floor=0):
    rows = []
    for name in sorted({k for f in fw + fc for k in f}):
        xs, ys = [f[name] for f in fw if name in f], [f[name] for f in fc if name in f]
        if len(xs) < 2 or len(ys) < 2:
            continue
        d = cliffs_delta(xs, ys)
        med_c = statistics.median(ys)
        side_ok = [x > med_c for x in xs] if d >= 0 else [x < med_c for x in xs]
        rows.append({"feature": name, "family": family(name), "n_winners": len(xs), "n_controls": len(ys),
                     "median_winners": round(statistics.median(xs), 4), "median_controls": round(med_c, 4),
                     "iqr_winners": round(_iqr(xs), 4), "iqr_controls": round(_iqr(ys), 4), "delta": round(d, 3),
                     "magnitude": magnitude(d), "consistency": round(sum(side_ok) / len(side_ok), 2),
                     "p": round(permutation_p(xs, ys), 6)})
    for fam in ("sense", "role"):
        mine = [r for r in rows if r["family"] == fam]
        for row, q, h in zip(mine, bh([r["p"] for r in mine]), holm([r["p"] for r in mine], floor if fam == "sense" else 0)):
            row["q"], row["p_holm"] = round(min(1.0, q), 6), round(h, 6)
    rows.sort(key=lambda x: (x["p_holm"], x["q"], -abs(x["delta"]), x["feature"]))
    return rows


def _evaluate_key(win, ctl, metric, relative):
    parts = []
    for side, works in (("w", win), ("c", ctl)):
        for e in sorted(works, key=lambda e: e["id"]):
            m = core.measurement(e["id"])
            parts.append([side, e["id"], e["source"]["sha256"], e.get("domain"), m.get("measured_with"), (m.get("fingerprint") or {}).get("v"),
                          core.role_features(e), sig.value(e.get("signals"), metric, relative), sig.value(e.get("signals"), "followers")])
    return store.digest(EVAL_VERSION, fingerprint.VERSION, metric, relative, parts)


def evaluate(win, ctl, metric, relative):
    """The comparison as the works stand now (current signals, measurements and labels); gates re-run it when they read
    one. Results are cached by everything they depend on, so an unchanged comparison is not recomputed."""
    by_id = {e["id"]: e for e in win + ctl}
    cache = store.root() / "cache" / f"eval-{_evaluate_key(win, ctl, metric, relative)}.json"
    if cache.is_file():
        try:
            c = store.read(cache)
            cw, cc = [[by_id[i] for i in g] for g in c["cw"]], [[by_id[i] for i in g] for g in c["cc"]]
            return {**c, "cw": cw, "cc": cc, "works": [e for g in cw + cc for e in g]}
        except (OSError, ValueError, KeyError):
            pass
    side = {**{e["id"]: "w" for e in win}, **{e["id"]: "c" for e in ctl}}
    both, cw, cc = [], [], []
    for g in core.clusters(win + ctl):
        sides = {side[e["id"]] for e in g}
        (both if len(sides) == 2 else cw if sides == {"w"} else cc).append(g)
    kept_w, kept_c = [e for g in cw for e in g], [e for g in cc for e in g]
    kinds = {e["kind"] for e in win + ctl}
    floor = _family_floor(kinds.pop()) if len(kinds) == 1 else 0
    out = {"rows": _stats([represent(g) for g in cw], [represent(g) for g in cc], floor),
           "dropped": sorted(e["id"] for g in both for e in g), "variants": _variants(both, side),
           "separated": separation(kept_w, kept_c, metric, relative) if kept_w and kept_c else None,
           "reach": reach_confounded(kept_w, kept_c),
           "audience_unknown": sum(sig.value(e.get("signals"), "followers") is None for e in kept_w + kept_c)}
    store.write(cache, {**out, "cw": [[e["id"] for e in g] for g in cw], "cc": [[e["id"] for e in g] for g in cc]})
    return {**out, "cw": cw, "cc": cc, "works": kept_w + kept_c}


def one_feature(win, ctl, feature, alternative):
    """One pre-stated test: is `feature` higher ("greater") or lower ("less") in winners, on distinct works?"""
    side = {**{e["id"]: "w" for e in win}, **{e["id"]: "c" for e in ctl}}
    groups = [g for g in core.clusters(win + ctl) if len({side[e["id"]] for e in g}) == 1]
    xs = [r[feature] for g in groups if side[g[0]["id"]] == "w" for r in [represent(g)] if feature in r]
    ys = [r[feature] for g in groups if side[g[0]["id"]] == "c" for r in [represent(g)] if feature in r]
    if len(xs) < 2 or len(ys) < 2:
        return None, len(xs), len(ys)
    return permutation_p(xs, ys, alternative), len(xs), len(ys)


def canonical(kind, domain, metric, pool=None, share=1 / 3):
    """The split a gate re-runs, so groups cannot be hand-picked: the top and bottom thirds of every registered work of
    this kind and domain by the metric's ratio to its baseline. Works tied with a group's last one join it (many works
    at zero form the bottom group), as long as the two groups stay apart."""
    if pool is None:
        pool = core.pool(kind, domain)
    scored = sorted(((v, e) for e in pool for v in [sig.value(e.get("signals"), metric, True)] if v is not None),
                    key=lambda x: (x[0], x[1]["id"]))
    k = int(len(scored) * share)
    if k < 2 or scored[k - 1][0] >= scored[-k][0]:
        return [], []
    low_cut, high_cut = scored[k - 1][0], scored[-k][0]
    return [e for v, e in scored if v >= high_cut], [e for v, e in scored if v <= low_cut]


def compare(request):
    r = Request.model_validate(request)
    if r.winners or r.controls:
        if not (r.winners and r.controls):
            raise ValueError("Give both winners and controls, or a split")
        if set(r.winners) & set(r.controls):
            raise ValueError("A work cannot be in both groups")
        win, ctl = [core.load(i) for i in r.winners], [core.load(i) for i in r.controls]
        how = "explicit groups"
        metric, relative = r.metric, r.relative
    else:
        if not r.split:
            raise ValueError("Give winners/controls, or split={metric, relative, top, bottom}")
        pool = [core.load(i) for i in r.exemplars] if r.exemplars else core.exemplars(r.kind, r.domain)  # domain: exact, any case
        scored = [(sig.value(e.get("signals"), r.split.metric, r.split.relative), e) for e in pool]
        missing = [e["id"] for v, e in scored if v is None]
        scored = sorted(((v, e) for v, e in scored if v is not None), key=lambda x: (x[0], x[1]["id"]))
        if len(scored) < 4:
            raise ValueError(f"Only {len(scored)} works have {r.split.metric}{' with a baseline' if r.split.relative else ''}; need 4+"
                             + (f" ({len(missing)} lack it)" if missing else ""))
        n_bottom, n_top = max(2, round(len(scored) * r.split.bottom)), max(2, round(len(scored) * r.split.top))
        if n_bottom + n_top > len(scored):
            n_bottom = n_top = len(scored) // 2
        if scored[n_bottom - 1][0] == scored[n_bottom][0] or scored[-n_top][0] == scored[-n_top - 1][0]:
            raise ValueError("Works tie on the split metric at a group boundary; the split would be arbitrary. Give explicit "
                             "groups or change top/bottom")
        ctl, win = [e for _, e in scored[:n_bottom]], [e for _, e in scored[-n_top:]]
        how = f"{'ratio to baseline of ' if r.split.relative else ''}{r.split.metric}: top {n_top} vs bottom {n_bottom} of {len(scored)}"
        metric, relative = r.split.metric, r.split.relative
    kinds = {e["kind"] for e in win + ctl}
    if len(kinds) != 1:
        raise ValueError(f"Compare works of one kind; got {sorted(kinds)}")
    ev = evaluate(win, ctl, metric, relative)
    cw, cc, rows, separated = ev["cw"], ev["cc"], ev["rows"], ev["separated"]
    if (len(cw) < 2 or len(cc) < 2) and not ev["variants"]:
        raise ValueError(f"Fewer than 2 distinct works left in a group ({len(cw)} winners, {len(cc)} controls)")
    distinct = min(len(cw), len(cc))
    confounders = []
    if ev["dropped"]:
        confounders.append(f"{len(ev['dropped'])} works are variants (or copies) of one work on both sides: left out of the groups "
                           f"and compared within their work (variants): {ev['dropped'][:6]}")
    if ev["reach"]:
        confounders.append(ev["reach"])
    elif ev["audience_unknown"]:
        confounders.append(f"audience size (followers) unknown for {ev['audience_unknown']} of {len(ev['works'])} works: reach is not ruled out")
    if len(cw) < sum(map(len, cw)) or len(cc) < sum(map(len, cc)):
        confounders.append(f"copies counted once: {len(cw)} distinct winners, {len(cc)} distinct controls")
    if not separated:
        confounders.append("groups are not separated on a success metric: this comparison cannot back a rule")
    elif not relative:
        confounders.append("split on a raw metric (reach), not its ratio to a baseline: this comparison cannot back a rule")
    domains = sorted({core.domain_key(e["domain"]) for e in ev["works"]})
    if len(domains) > 1:
        confounders.append(f"several domains mixed: {domains[:6]}")
    record = {"kind": kinds.pop(), "domain": domains[0] if len(domains) == 1 else "mixed", "how": how,
              "winners": [e["id"] for e in win], "controls": [e["id"] for e in ctl], "distinct": {"winners": len(cw), "controls": len(cc)},
              "dropped": ev["dropped"], "variants": ev["variants"], "features": rows, "n_tested": len(rows), "test": TEST,
              "metric": metric, "relative": relative, "separated_on": separated, "exploratory": distinct < 5,
              "confounders": confounders, "note": r.note}
    record["id"] = "cmp-" + store.digest(record["winners"], record["controls"], metric, relative, rows)
    record["created_at"] = store.now()
    store.write(store.path_for(record["id"]), record)
    wanted = set(r.features)
    shown = [lean(x) for x in rows if x["magnitude"] != "negligible" and (not wanted or x["feature"] in wanted)][:15]
    out = {"id": record["id"], "kind": record["kind"], "how": how, "winners": len(win), "controls": len(ctl), "distinct": record["distinct"],
           "exploratory": record["exploratory"], "separated_on": separated, "confounders": confounders, "differences": shown,
           "features_tested": len(rows), "holds_after_holm": sum(x["p_holm"] <= .05 for x in rows), "test": TEST,
           "next": "Inspect evidence where winners differ (learn evidence), then distill a blueprint citing this comparison. A rule is "
                   "judged on every registered work of the kind and domain (top vs bottom third), not on these groups alone.",
           "caution": "Associations in a small sample, not causes; look at the works before generalising."}
    if ev["variants"]:
        out["variants"] = ev["variants"]
    return out


def lean(row):
    return {k: row[k] for k in ("feature", "family", "median_winners", "median_controls", "delta", "magnitude", "p", "q", "p_holm")}
