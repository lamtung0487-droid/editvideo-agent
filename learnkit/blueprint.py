"""Blueprints: the caller's distilled way of making one kind of work, behind evidence gates, checked on new work.

A blueprint has a structure (ordered roles with share/position ranges), measurable targets (feature ranges, each with
its provenance), steps, principles, when/avoid, and the exemplars and comparisons it rests on.

Levels (the runtime checks them, from the evidence as it stands when read; promotion is explicit, readers see
min(stored, supported)):
    observation  cites at least one exemplar
    candidate    3+ distinct cited works of its kind with a signal above its baseline and an anatomy; most targets
                 grounded: a comparison target whose comparison shows a medium+ effect with a range holding the winners'
                 median and excluding the controls', or an exemplars target whose range holds those successful works'
                 median and excludes the median of 3+ registered works of this domain that did not beat their baseline
    rule         every comparison target on a measured feature holds on the top vs the bottom third of ALL registered
                 works of this kind and domain by the comparison's metric relative to its baseline (re-split when read,
                 so groups cannot be hand-picked; 5+ distinct works each; audience size not confounded): a medium+
                 effect, a range holding the winners' median and excluding the controls', and either p_holm <= .05 (Holm
                 over the sense's measurements) or confirmation — the same feature, direction, metric and range stated
                 before, then tested one-sided on works registered after it (copies of older works excluded) at .05
                 divided by every hypothesis stated for this kind, domain and metric before those works came in
                 — or trials: of the distinct new works it was applied to (conformed, outcome judged; each work's
                 first judged report counts, withdrawn or not), so many beat their baseline that chance (half) is
                 unlikely (one-sided sign test at .05 divided by the series of trials run in this kind and domain —
                 every blueprint and targets version is a series), with every target grounded on this domain. Targets on labelled roles are confirmed only by trials:
                 labels are the caller's, made knowing the outcome.
    standard     the comparison route of rule, and trials as above with at least one winning outcome whose value and
                 baseline were both read from a file (apply outcome_csv with baseline="others")

"Distinct" means not the same work: same bytes, or per kind a content fingerprint that says same or unsure (a copy,
re-encode, trim, excerpt, light edit); measurements alike within 2 % decide only when no fingerprint can. Once a work
has evidence of success its kind and domain are fixed, and a metric measured against a baseline keeps one, so works
cannot be moved out of a pool after their outcome is known. conform measures a work against the blueprint; unmeasured
targets count as misses. Applications are judged again whenever the blueprint is read (copy status, success metrics).
"""
import json
import math
import statistics
from pathlib import Path
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import compare as cmp, core, senses, signals as sig, store

LEVELS = ("observation", "candidate", "rule", "standard")
CONFORM_MIN = .7
ALPHA = .05
MIN_GROUP = 5  # distinct works per side of the re-run split
MEDIUM = .33
_APP_FP = {}  # (kind, sha) -> fingerprint recomputed for application rows logged with an older one


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: str = Field(pattern=core.ROLE)
    share: list[float] | None = Field(default=None, min_length=2, max_length=2)
    start: list[float] | None = Field(default=None, min_length=2, max_length=2)
    required: bool = True
    note: str = Field(default="", max_length=300)


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    feature: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    range: list[float] = Field(min_length=2, max_length=2)
    provenance: Literal["comparison", "exemplars", "chosen"]
    comparison_id: str | None = None
    note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def ordered(self):
        if not (store.finite(self.range[0]) and store.finite(self.range[1]) and self.range[0] <= self.range[1]):
            raise ValueError(f"target {self.feature}: range is a finite [low, high]")
        if (self.provenance == "comparison") != bool(self.comparison_id):
            raise ValueError(f"target {self.feature}: provenance=comparison names its comparison_id (and only then)")
        return self


class Blueprint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=40)
    domain: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=1000)  # what the work must do for its audience
    structure: list[Slot] = Field(default_factory=list, max_length=24)
    targets: list[Target] = Field(default_factory=list, max_length=40)
    steps: list[str] = Field(min_length=1, max_length=16)
    principles: str = Field(default="", max_length=1800)
    when_to_use: str = Field(min_length=1, max_length=1000)
    avoid: str = Field(min_length=1, max_length=1000)
    exemplars: list[Annotated[str, Field(pattern=r"^ex-[0-9a-f]{16}$")]] = Field(min_length=1, max_length=200)
    comparisons: list[Annotated[str, Field(pattern=r"^cmp-[0-9a-f]{16}$")]] = Field(default_factory=list, max_length=20)
    level: Literal["observation", "candidate", "rule", "standard"] | None = None
    state: Literal["active", "retired"] = "active"

    @model_validator(mode="after")
    def distinct(self):
        for name, values in (("exemplars", self.exemplars), ("comparisons", self.comparisons),
                             ("structure roles", [s.role for s in self.structure]), ("target features", [t.feature for t in self.targets])):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} list an item twice; each counts once")
        return self


class Apply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    blueprint_id: str
    path: str
    options: dict = Field(default_factory=dict)
    anatomy: list[core.Part] = Field(default_factory=list, max_length=24)
    outcome: list[dict] = Field(default_factory=list, max_length=12)  # signals of THIS work, each with a baseline
    outcome_csv: dict | None = None  # {path, metrics: {name: column}, row?, decimal?, baseline: "others" | baselines: {name: {..}}}
    kept: bool = True
    note: str = Field(min_length=1, max_length=600)


def _apps_path(bp_id):
    return store.root() / "blueprints" / (bp_id + ".applications.jsonl")


def targets_key(bp):
    """Identity of what a blueprint asks for (features and ranges, structure); notes and citations are not part of it.
    Applications logged against other targets/structure are another series of trials."""
    targets = sorted([t["feature"], [round(float(v), 6) for v in t["range"]]] for t in bp.get("targets") or [])
    structure = [[s.get("role"), s.get("share"), s.get("start"), s.get("required", True)] for s in bp.get("structure") or []]
    return store.digest(bp.get("kind"), targets, structure)


def reports(bp_id):
    """Every report logged for a blueprint, oldest first; a later report never replaces an earlier one."""
    path, rows = _apps_path(bp_id), []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("work_sha256"), str):
                rows.append(row)
    return sorted(rows, key=lambda r: r.get("at") or "")


def applications(bp_id):
    path, rows = _apps_path(bp_id), []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("work_sha256"), str):
                rows.append(row)
    return list({r["work_sha256"]: r for r in rows}.values())  # latest report per work


def _comparisons(bp):
    out = {}
    for cid in bp.get("comparisons") or []:
        p = store.path_for(cid)
        if p.is_file():
            out[cid] = store.read(p)
    return out


def _cited(bp):
    out = []
    for i in dict.fromkeys(bp["exemplars"]):
        try:
            ex = core.load(i)
        except ValueError:
            continue
        if ex["kind"] == bp["kind"]:  # a work re-registered as another kind no longer counts
            out.append(ex)
    return out


def success_metrics(bp):
    """What outcomes are judged on: the metrics the comparisons split on, else those the cited exemplars beat their baselines on."""
    metrics = {c["metric"] for c in _comparisons(bp).values() if c.get("metric")}
    return metrics or {r["metric"] for e in _cited(bp) for r in e.get("signals") or [] if (r.get("vs_baseline") or 0) > 1}


def judge(bp, outcome, metrics=None):
    """Which outcome signals count (the success metrics, with a baseline) and whether they beat it."""
    metrics = success_metrics(bp) if metrics is None else metrics
    judged = [o for o in outcome if o.get("vs_baseline") is not None and (not metrics or o["metric"] in metrics)]
    return {"metrics": sorted(metrics), "judged": judged, "beat": bool(judged) and all(o["vs_baseline"] > 1 for o in judged),
            "from_export": any(o.get("grade") == "imported" and o.get("baseline_from") == "export" for o in judged)}


def _row_identity(a, kind=None):
    fp = a.get("fingerprint")
    from . import fingerprint
    if kind and (not isinstance(fp, dict) or fp.get("v") != fingerprint.VERSION):
        key = (kind, a["work_sha256"])
        if key not in _APP_FP:
            path, fresh = Path(a.get("work") or ""), None
            try:
                if path.is_file() and store.sha256(path) == a["work_sha256"]:
                    fresh = core._fingerprint(senses.get(kind), path, None)
            except (OSError, ValueError):
                fresh = None
            _APP_FP[key] = fresh
        fp = _APP_FP[key] or fp
    return a["work_sha256"], fp, a.get("features") or {}


def series(kind, domain):
    """Every series of trials run in this kind and domain: one per blueprint and targets version with a judged outcome.
    Restarting (new targets, a new blueprint) starts a new series, and every series shares the .05."""
    found, key = set(), core.domain_key(domain)
    for d in core._all("blueprints")[0]:
        for a in reports(d["id"]):
            row_kind, row_domain = a.get("kind") or d.get("kind"), a.get("domain") or core.domain_key(d.get("domain"))
            if row_kind == kind and row_domain == key and any(o.get("vs_baseline") is not None for o in a.get("outcome") or []):
                found.add((d["id"], a.get("targets_key"), tuple(a.get("judged_on") or ())))
    return len(found)


def trials(bp):
    """The blueprint's applications as a test: each distinct new work it was applied to (conformed, with an outcome judged
    on the success metric) counts once, by its first judged report, wins and losses alike; withdrawing a work afterwards
    or reporting it again does not remove the result."""
    key, metrics, kind = targets_key(bp), success_metrics(bp), bp["kind"]
    exemplar_ids = [(e.get("created_at") or "", core.identity(e)) for e in core.exemplars(kind)]
    judged_on = sorted(metrics)
    rows = []
    for a in reports(bp["id"]):
        if a.get("conformance", 0) < CONFORM_MIN or a.get("targets_key") != key or a.get("judged_on") != judged_on:
            continue  # another series: other targets, or judged on another success metric
        verdict = judge(bp, a.get("outcome") or [], metrics)
        if not verdict["judged"]:
            continue  # no outcome on the success metric yet
        ident = _row_identity(a, kind)
        if any(at < (a.get("at") or "") and core.same_content(*ident, *i) for at, i in exemplar_ids):
            continue  # a copy of a work registered before it was applied is not a new work; registering it later changes nothing
        rows.append({**a, "beat": verdict["beat"], "from_export": verdict["beat"] and verdict["from_export"], "_ident": ident})
    works = [g[0] for g in core.group(rows, lambda x, y: core.same_content(*x["_ident"], *y["_ident"]))]  # first report counts
    n, k = len(works), sum(w["beat"] for w in works)
    p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n if n else 1.0
    m = max(1, series(kind, bp["domain"])) if n else 1
    return {"works": works, "judged": n, "beat": k, "p": p, "series": m, "alpha": ALPHA / m,
            "from_export": any(w["from_export"] for w in works)}


def verified_works(bp):
    return [w for w in trials(bp)["works"] if w["beat"]]


def successful(ex):
    """Evidence of success: at least one signal above its baseline (raw numbers without a baseline mostly measure reach)."""
    return any((r.get("vs_baseline") or 0) > 1 for r in ex.get("signals") or [])


def unsuccessful(ex):
    """Measured against a baseline and never above it."""
    rows = [r for r in ex.get("signals") or [] if r.get("vs_baseline") is not None]
    return bool(rows) and all(r["vs_baseline"] <= 1 for r in rows)


def _held_by_exemplars(t, reps, others):
    """An exemplars target: its range holds the successful works' median and excludes the median of 3+ that were not."""
    lo, hi = t["range"]
    vals = [r[t["feature"]] for r in reps if t["feature"] in r]
    rest = [r[t["feature"]] for r in others if t["feature"] in r]
    return bool(vals) and len(rest) >= 3 and lo <= statistics.median(vals) <= hi and not lo <= statistics.median(rest) <= hi


def _holds(row, t):
    lo, hi = t["range"]
    return bool(row) and abs(row["delta"]) >= MEDIUM and lo <= row["median_winners"] <= hi and not lo <= row["median_controls"] <= hi


def _domain_works(bp):
    return core.pool(bp["kind"], bp["domain"])


def _ledger():
    return store.root() / "ledger" / "hypotheses.jsonl"


def stated(kind, domain, metric=None, before=None, pending=()):
    """The distinct hypotheses stated for this kind and domain, whatever their metric (all blueprints, all revisions), up
    to `before`: every one that works registered by then could have been used to test. Read from the store-wide ledger
    and from the blueprints themselves, so a missing ledger file does not make the count smaller."""
    key = core.domain_key(domain)
    early = lambda h: before is None or (h.get("since") or h.get("at") or "") <= before
    keys = {h["key"] for h in pending if early(h)}
    for d in core._all("blueprints")[0]:
        if d.get("kind") == kind and core.domain_key(d.get("domain")) == key:
            keys |= {h["key"] for h in (d.get("hypotheses") or {}).values() if early(h)}
    path = _ledger()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                h = json.loads(line)
            except ValueError:
                continue
            if h.get("kind") == kind and h.get("domain") == key and early(h):
                keys.add(h.get("key"))
    return len(keys)


def _hypotheses(b, comps, old):
    """Each comparison target as a stated hypothesis: feature, direction (from the cited comparison the caller looked at),
    metric and range, dated when first stated. Changing any of them states a new one."""
    before = (old or {}).get("hypotheses") or {}
    out = {}
    for t in b.targets:
        c = comps.get(t.comparison_id) if t.comparison_id else None
        row = next((r for r in (c or {}).get("features") or [] if r["feature"] == t.feature), None)
        if not row or not c.get("metric"):
            continue
        lo, hi = t.range
        direction = "greater" if lo > row["median_controls"] else "less" if hi < row["median_controls"] else None
        if not direction:
            continue
        key = store.digest(b.kind, core.domain_key(b.domain), t.feature, direction, c["metric"], [round(lo, 6), round(hi, 6)])
        since = before[t.feature]["since"] if before.get(t.feature, {}).get("key") == key else store.now()
        out[t.feature] = {"key": key, "feature": t.feature, "direction": direction, "metric": c["metric"], "since": since}
    return out


def _target_checks(bp, grounded):
    """Per target: grounded (candidate), informative (holds on this domain's re-run split) and backed (also beats chance)."""
    targets = bp.get("targets") or []
    comps = _comparisons(bp)
    out, pool, splits = {}, None, {}
    if any(t["provenance"] == "exemplars" for t in targets):
        reps = [cmp.represent(g) for g in grounded]
        others = [cmp.represent(g) for g in core.clusters([e for e in _domain_works(bp) if unsuccessful(e)])]
    for t in targets:
        f = t["feature"]
        if t["provenance"] == "chosen":
            out[f] = {"grounded": False, "informative": False, "backed": False, "why": "chosen, not measured"}
            continue
        if t["provenance"] == "exemplars":
            ok = _held_by_exemplars(t, reps, others)
            out[f] = {"grounded": ok, "informative": ok, "backed": False,
                      "why": None if ok else "range must hold the successful works' median and exclude the median of 3+ works of "
                                             "this domain that did not beat their baseline"}
            continue
        c = comps.get(t["comparison_id"])
        stored = next((r for r in (c or {}).get("features") or [] if r["feature"] == f), None)
        check = {"grounded": _holds(stored, t), "informative": False, "backed": False, "why": None}
        out[f] = check
        if not c or not c.get("metric") or not c.get("relative") or c.get("kind") != bp["kind"] \
                or core.domain_key(c.get("domain")) != core.domain_key(bp["domain"]):
            check["why"] = "its comparison must split this kind and domain by a metric relative to its baseline"
            continue
        metric = c["metric"]
        if pool is None:
            pool = _domain_works(bp)
        if metric not in splits:
            high, low = cmp.canonical(bp["kind"], bp["domain"], metric, pool)
            splits[metric] = cmp.evaluate(high, low, metric, True) if high and low else None
        ev = splits[metric]
        if not ev or min(len(ev["cw"]), len(ev["cc"])) < MIN_GROUP:
            n = (len(ev["cw"]), len(ev["cc"])) if ev else (0, 0)
            check["why"] = f"top and bottom thirds of this domain's works by {metric} need {MIN_GROUP}+ distinct works each (now {n[0]}, {n[1]})"
            continue
        if ev["reach"]:
            check["why"] = ev["reach"]
            continue
        row = next((r for r in ev["rows"] if r["feature"] == f), None)
        if not _holds(row, t):
            check["why"] = "on this domain's top vs bottom third the effect is below medium, or the range does not hold the winners' median and exclude the controls'"
            continue
        check["informative"] = True
        if cmp.family(f) == "role":
            check["why"] = "a target on labelled roles is confirmed by trials only (labels are made knowing the outcome)"
            continue
        if row["p_holm"] <= ALPHA:
            check["backed"] = True
            continue
        hyp = (bp.get("hypotheses") or {}).get(f)
        if hyp and hyp["metric"] == metric:
            p_new, nw, nc, newest = _confirmation(bp, hyp, pool)
            m = stated(bp["kind"], bp["domain"], None, newest, (bp.get("hypotheses") or {}).values())
            if p_new is not None and min(nw, nc) >= MIN_GROUP and p_new <= ALPHA / max(1, m):
                check["backed"] = True
                continue
            check["why"] = (f"could be chance: p_holm {row['p_holm']:.3g}; confirmation on works registered since it was stated: "
                            f"{'p ' + format(p_new, '.3g') if p_new is not None else 'not enough'} ({nw} vs {nc} distinct works; "
                            f"needs {MIN_GROUP}+ each and p <= {ALPHA / max(1, m):.3g}, .05 over {m} hypotheses stated here, any metric)")
            continue
        check["why"] = f"could be chance: p_holm {row['p_holm']:.3g}; state it, then confirm it on works registered afterwards"
    return out


def _confirmation(bp, hyp, pool):
    """The stated hypothesis tested on works registered after it, leaving out copies of any older work of this kind."""
    since = hyp["since"]
    older = [core.identity(e) for e in core.exemplars(bp["kind"]) if (e.get("created_at") or "") <= since]
    fresh = []
    for e in pool:
        if (e.get("created_at") or "") > since:
            mine = core.identity(e)
            if not any(core.same_content(*mine, *i) for i in older):
                fresh.append(e)
    high, low = cmp.canonical(bp["kind"], bp["domain"], hyp["metric"], fresh)
    newest = max((e.get("created_at") or "" for e in high + low), default=None)
    return (*cmp.one_feature(high, low, hyp["feature"], hyp["direction"]), newest)


def gates(bp):
    """What each level still needs (empty = met), the highest level the evidence supports, and the verified works."""
    exs = _cited(bp)
    grounded = core.clusters([e for e in exs if successful(e) and e.get("anatomy")])
    targets = bp.get("targets") or []
    need = {"observation": [] if exs else [f"at least one registered {bp['kind']} exemplar"]}
    cand = list(need["observation"])
    if len(grounded) < 3:
        cand.append(f"3+ distinct exemplars (copies count once) with a signal above its baseline and an anatomy ({len(grounded)} so far)")
    checks = _target_checks(bp, grounded)
    weak = [f for f, c in checks.items() if not c["grounded"]]
    if targets and len(weak) > len(targets) / 2:
        cand.append("most targets grounded: a comparison's medium+ effect with a range holding the winners' median and excluding "
                    "the controls', or an exemplars range holding the successful works' median and excluding the median of 3+ "
                    f"works of this domain that did not beat their baseline (not grounded: {weak[:8]})")
    need["candidate"] = cand
    tried = trials(bp) if bp.get("id") else {"works": [], "judged": 0, "beat": 0, "p": 1.0, "series": 1, "alpha": ALPHA,
                                               "from_export": False}
    by_comparison = [f for t in targets if t["provenance"] == "comparison" for f in [t["feature"]] if not checks[f]["backed"]]
    if not any(t["provenance"] == "comparison" for t in targets):
        by_comparison = ["(no comparison targets)"]
    trials_hold = tried["judged"] > 0 and tried["p"] <= tried["alpha"]
    by_trials = trials_hold and targets and all(c["informative"] for c in checks.values())
    record = (f"{tried['beat']} of {tried['judged']} distinct new works beat their baseline (sign test p {tried['p']:.3g}; needs "
              f"<= {tried['alpha']:.3g}: .05 over {tried['series']} series of trials in this domain)")
    rule = list(cand)
    if by_comparison and not by_trials:
        why = {f: checks[f]["why"] for f in by_comparison if f in checks}
        rule.append("every comparison target holding on this domain's top vs bottom third (5+ distinct works each) with a medium+ "
                    "effect, a range holding the winners' median and excluding the controls', and p_holm <= .05 or confirmation "
                    "on works registered after it was stated — or trials: enough of the distinct new works it was applied to beat "
                    f"their baseline that chance is unlikely (p <= .05: 5 of 5, 7 of 8), every target grounded here ({record}). "
                    f"Not yet: {why or by_comparison}")
    need["rule"] = rule
    standard = list(rule)
    if by_comparison:
        standard.append("the comparison route of rule (trials alone make a rule, not a standard)")
    if not trials_hold:
        standard.append(f"trials: p <= .05 on distinct new works, wins and losses alike ({record})")
    elif not tried["from_export"]:
        standard.append("at least one winning outcome whose value and baseline were both read from a file "
                        "(apply outcome_csv with baseline=\"others\"), not typed")
    need["standard"] = standard
    return need, LEVELS[max(i for i, lv in enumerate(LEVELS) if not need[lv])], tried


def status(bp, judged=None):
    apps = applications(bp["id"])
    if bp.get("state") == "retired":
        return {"level": None, "state": "retired", "applications": len(apps), "note": "retired: not to be applied"}
    need, eligible, tried = judged or gates(bp)
    stored = bp.get("level") or "observation"
    level = LEVELS[min(LEVELS.index(stored), LEVELS.index(eligible))]
    out = {"level": level, "eligible_level": eligible, "applications": len(apps), "verified_works": tried["beat"],
           "trials": {"judged": tried["judged"], "beat": tried["beat"], "p": round(tried["p"], 4), "series": tried["series"]}}
    if level != stored:
        out["stored_level"] = stored
    nxt = LEVELS[min(3, LEVELS.index(level) + 1)]
    if nxt != level and need[nxt]:
        out["next_level"] = {"level": nxt, "needs": need[nxt]}
    reported = sum(1 for a in apps if any(o.get("grade") == "reported" for o in a.get("outcome") or []))
    if reported:
        out["outcomes_reported_by_caller"] = reported  # typed numbers cannot be checked here; say so
    return out


def distill(request, blueprint_id=None, base_revision=None):
    b = Blueprint.model_validate(request)
    for i in b.exemplars:
        if core.load(i)["kind"] != b.kind:
            raise ValueError(f"exemplar {i} is not a {b.kind} work")
    known = set()
    for i in b.exemplars:
        known |= set(core.exemplar_features(core.load(i)))
    for t in b.targets:
        if t.feature not in known and not t.feature.startswith("role_"):
            raise ValueError(f"target {t.feature}: no cited exemplar has this feature; see learn library item_id=<exemplar>")
        if t.comparison_id:
            if t.comparison_id not in b.comparisons:
                raise ValueError(f"target {t.feature}: cite {t.comparison_id} in comparisons")
            c = store.read(store.path_for(store.check_id(t.comparison_id, "cmp")))
            if c["kind"] != b.kind or not any(f["feature"] == t.feature for f in c["features"]):
                raise ValueError(f"target {t.feature}: comparison {t.comparison_id} did not compare this feature for {b.kind}")
    bp_id = blueprint_id or "bp-" + store.digest(b.title.lower(), b.kind, b.domain.lower())
    store.check_id(bp_id, "bp")
    path = store.path_for(bp_id)
    body = b.model_dump()
    with store.lock(path):
        old = store.read(path) if path.is_file() else None
        if old and (old.get("kind") != b.kind or core.domain_key(old.get("domain")) != core.domain_key(b.domain)):
            raise ValueError(f"This blueprint is for {old['kind']} work in {old['domain']!r}; its kind and domain stay as they are "
                             "(its trials belong there). Distill a new blueprint for another kind or domain.")
        level = b.level or (old or {}).get("level")
        hypotheses = _hypotheses(b, {c: store.read(store.path_for(c)) for c in b.comparisons if store.path_for(c).is_file()}, old)
        trial = {**body, "id": bp_id, "hypotheses": hypotheses}
        judged = gates(trial)
        need, eligible, _ = judged
        level = level or LEVELS[min(LEVELS.index(eligible), 1)]
        if need[level]:
            if b.state != "retired":
                raise ValueError(f"level {level} needs: " + "; ".join(need[level]) + f" (evidence supports {eligible})")
            level = LEVELS[min(LEVELS.index(level), LEVELS.index(eligible))]
        body["level"] = level
        if old:
            if {k: old.get(k) for k in body} == body:
                if old.get("hypotheses") != hypotheses:  # written before hypotheses were dated: date them now, same revision
                    old = {**old, "hypotheses": hypotheses}
                    store.write(path, old)
                    _log_hypotheses(old)
                return {"id": bp_id, "revision": old["revision"], "unchanged": True, **status(old, judged)}
            if base_revision != old["revision"]:
                raise ValueError("Blueprint revision conflict; read it before changing it")
        elif base_revision not in (None, 0):
            raise ValueError("Blueprint does not exist at base_revision")
        doc = {**body, "id": bp_id, "hypotheses": hypotheses, "revision": (old or {}).get("revision", 0) + 1,
               "created_at": (old or {}).get("created_at") or store.now(), "updated_at": store.now(),
               "authorship": "caller-authored from measured exemplars; not model training"}
        store.write(path, doc)
        _log_hypotheses(doc)
    return {"id": bp_id, "revision": doc["revision"], **status(doc, judged),
            "next": "Make the work, then learn conform to measure it against this blueprint, and apply once its real outcome is known."}


def _log_hypotheses(doc):
    """Add the blueprint's newly stated hypotheses to the store-wide ledger (it only grows)."""
    path = _ledger()
    path.parent.mkdir(parents=True, exist_ok=True)
    with store.lock(path):
        known = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    known.add(json.loads(line).get("key"))
                except ValueError:
                    continue
        with path.open("a", encoding="utf-8") as f:
            for h in (doc.get("hypotheses") or {}).values():
                if h["key"] not in known:
                    f.write(json.dumps({**h, "kind": doc["kind"], "domain": core.domain_key(doc["domain"]), "blueprint": doc["id"],
                                        "at": store.now()}, ensure_ascii=False) + "\n")


def load(bp_id):
    p = store.path_for(store.check_id(bp_id, "bp"))
    if not p.is_file():
        raise ValueError(f"Unknown blueprint {bp_id}")
    return store.read(p)


def _gap(value, lo, hi):
    return 0.0 if lo <= value <= hi else round(value - (lo if value < lo else hi), 4)


def conform(blueprint_id, path, options=None, anatomy=None, _measured=None):
    """Measure a work against a blueprint: each target in or out of range (with the gap) — a target the work does not
    measure counts as a miss — and the structure (roles present, their shares/positions, their order on the work) when
    its parts are labelled. Nothing is saved."""
    bp = load(blueprint_id)
    if bp.get("state") == "retired":
        raise ValueError("This blueprint is retired")
    sense = senses.get(bp["kind"])
    work = Path(path).resolve(strict=True)
    options = core._options(options)
    m = _measured or sense.measure(work, options or None)
    feats = senses.numeric(m["features"])
    parts = []
    for p in anatomy or []:
        p = core.Part.model_validate(p)
        span = senses.check_span(sense, p.span)
        parts.append({"role": p.role, "span": span, **core.geometry(sense, work, span, feats, options)})
    parts.sort(key=lambda q: (q.get("start_share", 0), q["role"]))
    for p in parts:
        if "share" in p:
            feats.setdefault(f"role_share_{p['role']}", p["share"])
        if "start_share" in p:
            feats.setdefault(f"role_start_{p['role']}", p["start_share"])
    checks = []
    for t in bp.get("targets") or []:
        lo, hi = t["range"]
        v = feats.get(t["feature"])
        checks.append({"feature": t["feature"], "range": t["range"], "value": None if v is None else round(v, 4),
                       "in_range": None if v is None else lo <= v <= hi, "gap": None if v is None else _gap(v, lo, hi)})
    score = sum(bool(c["in_range"]) for c in checks) / len(checks) if checks else None
    out = {"blueprint": blueprint_id, "work": str(work), "conformance": None if score is None else round(score, 3),
           "targets": checks, "unmeasured": [c["feature"] for c in checks if c["in_range"] is None]}
    if bp.get("structure"):
        if parts:
            structure = []
            for slot in bp["structure"]:
                got = next((p for p in parts if p["role"] == slot["role"]), None)
                row = {"role": slot["role"], "present": bool(got)}
                if got and slot.get("share") and "share" in got:
                    row["share_ok"] = slot["share"][0] <= got["share"] <= slot["share"][1]
                if got and slot.get("start") and "start_share" in got:
                    row["start_ok"] = slot["start"][0] <= got["start_share"] <= slot["start"][1]
                structure.append(row)
            expected = [s["role"] for s in bp["structure"]]
            on_work = [p["role"] for p in parts if p["role"] in expected]
            out.update(structure=structure, order_ok=on_work == [r for r in expected if r in on_work])
        else:
            out["structure_note"] = "label the work's parts (anatomy) to check the structure"
    return out


def _copy_of(work_sha, fp, feats, bp):
    """The registered exemplar (of this kind) or earlier application this work is the same work as."""
    for ex in core.exemplars(bp["kind"]):
        if core.same_content(work_sha, fp, feats, *core.identity(ex)):
            return ex["id"]
    for a in applications(bp["id"]):
        if a["work_sha256"] != work_sha and core.same_content(work_sha, fp, feats, *_row_identity(a)):
            return a["work"]
    return None


def _imported_outcome(spec):
    c = dict(spec)
    extra = set(c) - {"path", "metrics", "row", "decimal", "baselines", "baseline"}
    if extra or not c.get("path") or not c.get("metrics"):
        raise ValueError('outcome_csv takes {path, metrics: {name: column}, row?: {column, equals}, decimal?, baseline: "others" '
                         '(the median of the other rows) or baselines: {name: {baseline, baseline_note}}}')
    rows, _ = sig.from_csv(Path(c.pop("path")).resolve(strict=True), **c)
    return rows


def apply(request):
    """Log one real use of a blueprint: conformance measured here, outcome as given (each with a baseline)."""
    r = Apply.model_validate(request)
    bp = load(r.blueprint_id)
    if bp.get("state") == "retired":
        raise ValueError("This blueprint is retired; it is not to be applied")
    work = Path(r.path).resolve(strict=True)
    options = core._options(r.options)
    sense = senses.get(bp["kind"])
    m = sense.measure(work, options or None)
    fp = core._fingerprint(sense, work, options)
    report = conform(r.blueprint_id, work, options, [p.model_dump() for p in r.anatomy], _measured=m)
    outcome = [sig.stamp(s, "reported") for s in r.outcome] + (_imported_outcome(r.outcome_csv) if r.outcome_csv else [])
    verdict = judge(bp, outcome)
    sha = store.sha256(work)
    feats = senses.numeric(m["features"])
    row = {"at": store.now(), "work": str(work), "work_sha256": sha, "blueprint_revision": bp["revision"], "targets_key": targets_key(bp),
           "judged_on": verdict["metrics"], "kind": bp["kind"], "domain": core.domain_key(bp["domain"]),
           "conformance": report["conformance"] or 0, "kept": r.kept, "outcome": outcome, "note": r.note,
           "beat_baseline": verdict["beat"], "duplicate_of": _copy_of(sha, fp, feats, bp), "features": feats, "fingerprint": fp}
    with store.lock(store.path_for(bp["id"])):
        with _apps_path(bp["id"]).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    judged = gates(bp)
    out = {"blueprint": bp["id"], "recorded": {k: row[k] for k in ("work", "conformance", "kept", "beat_baseline", "duplicate_of")},
           "report": report, **status(bp, judged)}
    if outcome and len(verdict["judged"]) < len(outcome) and verdict["metrics"]:
        out["outcome_note"] = f"judged on {verdict['metrics']} (the success metrics, with a baseline); other signals are kept but not judged"
    if row["duplicate_of"] or not any(w["work_sha256"] == sha and w["beat"] for w in judged[2]["works"]):
        out["unverified"] = ("Counts as a win once a new work (not the same work as a registered exemplar; copies of one another "
                             "count once) conforms (>= 70 % of the current targets) and its first judged outcome on the success "
                             "metric beat its baseline; losses count in the trials too.")
    return out
