"""Evidence that a work succeeded, kept apart from what the work is.

A signal is a number with its source, date and, ideally, a baseline (the same metric for the channel's/brand's/category's
usual work), because raw success mostly measures reach: views follow channel size, age and topic. The ratio to the
baseline is what comparisons use when it exists. The grade says how the number arrived: "imported" means learnkit read
it from a file (yt-dlp metadata, an analytics export); "reported" means the caller typed it.

An attention curve (YouTube's "most replayed" heatmap, an analytics retention curve) is kept as a time series so
learning windows can be laid on it; a replay heatmap is relative replay intensity, not retention.
"""
import csv
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store

SOURCES = ("platform_metadata", "analytics_export", "caller_report", "sales", "ab_test", "award", "survey")


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(default="", max_length=24)
    baseline: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    baseline_note: str = Field(default="", max_length=160)
    baseline_from: Literal["caller", "export"] = "caller"  # "export": learnkit computed it from the same file's other rows
    source: Literal[SOURCES] = "caller_report"
    source_detail: str = Field(default="", max_length=200)
    as_of: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def baseline_explained(self):
        if self.baseline is not None and not self.baseline_note:
            raise ValueError(f"signal {self.metric}: say what the baseline is (baseline_note)")
        return self


def stamp(signal, grade):
    row = signal.model_dump() if isinstance(signal, Signal) else Signal.model_validate(signal).model_dump()
    row["grade"] = grade
    if grade != "imported":
        row["baseline_from"] = "caller"  # only learnkit's own reading of a file says a baseline came from it
    if row["baseline"]:
        row["vs_baseline"] = round(row["value"] / row["baseline"], 4)
    return row


def from_ytdlp(path):
    """Signals and the replay curve from a yt-dlp .info.json (read locally; never fetched)."""
    info = store.read(path)
    if not isinstance(info, dict):
        raise ValueError("Not a yt-dlp info.json")
    num = lambda k: info[k] if store.finite(info.get(k)) else None  # strings, booleans and NaN are not counts
    when = num("epoch") or Path(path).stat().st_mtime
    as_of = datetime.fromtimestamp(when, timezone.utc).strftime("%Y-%m-%d")
    detail = f"yt-dlp metadata ({info.get('extractor_key') or 'platform'}), {Path(path).name}"
    views, likes, comments, followers = (num(k) for k in ("view_count", "like_count", "comment_count", "channel_follower_count"))
    rows = []

    def add(metric, value, unit, baseline=None, note=""):
        if isinstance(value, (int, float)) and math.isfinite(value):
            rows.append(stamp({"metric": metric, "value": float(value), "unit": unit, "baseline": baseline, "baseline_note": note,
                               "source": "platform_metadata", "source_detail": detail, "as_of": as_of}, "imported"))
    add("views", views, "views", followers if followers else None, "channel followers when the metadata was read" if followers else "")
    add("likes", likes, "likes")
    add("comments", comments, "comments")
    add("followers", followers, "followers")
    if views and (likes is not None or comments is not None):
        add("engagement_rate", ((likes or 0) + (comments or 0)) / views, "share of views")
    upload = info.get("upload_date")
    if views and isinstance(upload, str) and re.fullmatch(r"\d{8}", upload):
        days = max(1.0, (when - datetime.strptime(upload, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()) / 86400)
        add("views_per_day", views / days, "views/day since upload")
    curve = None
    heat = info.get("heatmap")
    if isinstance(heat, list) and heat:
        points = [[float(h["start_time"]), float(h["end_time"]), float(h["value"])] for h in heat
                  if isinstance(h, dict) and all(isinstance(h.get(k), (int, float)) for k in ("start_time", "end_time", "value"))]
        if points:
            curve = {"source": "most replayed (YouTube heatmap via yt-dlp)", "meaning": "relative replay intensity, not retention",
                     "as_of": as_of, "points": points}
    return rows, curve


def number(text, decimal=None):
    """A number as exports write it. With decimal="," (e.g. Vietnamese exports) "1.234,5" is 1234.5; with "." it is
    "1,234.5". Without one, a value whose separator could be either ("4,5", "1.234", "1,234") is refused."""
    raw = str(text).strip().replace("\u00a0", "").replace(" ", "")
    pct = raw.endswith("%")
    raw = raw.rstrip("%")
    if decimal is None:
        dots, commas = raw.count("."), raw.count(",")
        if dots and commas:
            decimal = "." if raw.rfind(".") > raw.rfind(",") else ","
        elif (dots + commas == 1 and re.fullmatch(r"-?[1-9]\d{0,2}[.,]\d{3}", raw)) or (commas == 1 and not dots and not re.fullmatch(r"-?0,\d+", raw)):
            raise ValueError(f"{text!r} is ambiguous: give csv.decimal ('.' or ',')")
        elif dots > 1 or commas > 1:
            decimal = "," if dots > 1 else "."
        else:
            decimal = "," if commas == 1 and not dots else "."
    thousands = "," if decimal == "." else "."
    value = float(raw.replace(thousands, "").replace(decimal, "."))
    return value, pct


def from_csv(path, metrics=None, row=None, curve=None, decimal=None, baselines=None, baseline=None):
    """Signals (one row picked by row={'column','equals'}, or the only row) and/or a curve
    (curve={'time': column, 'value': column, 'meaning': text}) from an analytics export the caller saved.
    decimal="," or "." says how its numbers are written (ambiguous values are refused without it).
    baselines={metric: {baseline, baseline_note}} gives an imported metric a typed baseline; baseline="others" makes it the
    median of the same column over the file's other rows (3+), computed here: the usual result, read from the same export."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        table = list(csv.DictReader(f))
    if not table:
        raise ValueError("The CSV has no rows")
    detail = f"analytics export {Path(path).name}"
    out, series = [], None
    if decimal not in (None, ".", ","):
        raise ValueError("csv.decimal is '.' or ','")
    num = lambda v: number(v, decimal)[0]
    if metrics:
        if row:
            hits = [r for r in table if str(r.get(row.get("column", ""), "")).strip() == str(row.get("equals", "")).strip()]
            if len(hits) != 1:
                raise ValueError(f"row filter matched {len(hits)} rows; it must match exactly one")
            picked = hits[0]
        elif len(table) == 1:
            picked = table[0]
        else:
            raise ValueError("Several rows: say which one with row={'column','equals'}")
        for metric, column in metrics.items():
            if column not in picked:
                raise ValueError(f"No column {column!r}; columns: {list(picked)[:20]}")
            value, pct = number(picked[column], decimal)
            base = (baselines or {}).get(metric) or {}
            if not isinstance(base, dict) or set(base) - {"baseline", "baseline_note"}:
                raise ValueError(f"baselines.{metric} is {{baseline, baseline_note}}")
            if baseline is not None:
                if baseline != "others" or not row:
                    raise ValueError('baseline="others" takes the median of the other rows; pick the work\'s row with row={column, equals}')
                others = []
                for r in table:
                    if r is not picked:
                        try:
                            others.append(num(r[column]))
                        except (KeyError, ValueError):
                            continue
                if len(others) < 3 or statistics.median(others) <= 0:
                    raise ValueError(f"baseline='others' needs 3+ other rows with a positive median of {column!r}")
                base = {"baseline": statistics.median(others), "baseline_from": "export",
                        "baseline_note": f"median of the other {len(others)} rows of {Path(path).name}"}
            out.append(stamp({"metric": metric, "value": value, "unit": "%" if pct else "", "source": "analytics_export",
                              "source_detail": detail, **base}, "imported"))
    if curve:
        pts = []
        for r in table:
            try:
                pts.append([num(r[curve["time"]]), num(r[curve["value"]])])
            except (KeyError, ValueError):
                continue
        if len(pts) < 2:
            raise ValueError("The curve columns gave fewer than two numeric rows")
        pts.sort()
        series = {"source": detail, "meaning": str(curve.get("meaning", "audience retention"))[:120],
                  "points": [[a, b, v] for (a, v), (b, _) in zip(pts, pts[1:] + [[pts[-1][0] + (pts[-1][0] - pts[-2][0]), 0]])]}
    if not out and not series:
        raise ValueError("Give metrics={name: column} and/or curve={'time','value'}")
    return out, series


def merge(old, new):
    """Latest value per metric wins; older ones are kept as history. A metric measured against a baseline keeps one: a
    new value without a baseline would quietly take the work out of every comparison by that metric."""
    rows = {r["metric"]: r for r in old or []}
    history = []
    for r in new:
        if r["metric"] in rows:
            if rows[r["metric"]].get("baseline") and not r.get("baseline"):
                raise ValueError(f"signal {r['metric']}: it had a baseline; give the new value one too")
            history.append(rows[r["metric"]])
        rows[r["metric"]] = r
    return list(rows.values()), history


def value(signals, metric, relative=False):
    for r in signals or []:
        if r["metric"] == metric:
            return r.get("vs_baseline") if relative else r["value"]
    return None


def curve_peaks(curve, n=3):
    """The n most replayed/retained stretches, as (start, end, value), strongest first."""
    pts = sorted(curve.get("points") or [], key=lambda p: -p[2])
    out = []
    for a, b, v in pts:
        if all(b <= x or a >= y for x, y, _ in out):
            out.append((a, b, v))
        if len(out) == n:
            break
    return out
