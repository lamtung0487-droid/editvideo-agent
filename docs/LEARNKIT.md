# learnkit: learning from finished work that succeeded

An AI can make a video, a page or an image; whether it works for an audience is another question. People learn that
from finished work the market has already judged, and from trying their own work on real audiences. `learnkit` gives
Claude the senses and the method for both, for any kind of work, without training a model:

1. **Hands** — register a finished work (a file), with its source and usage limits. Downloading new works always goes
   through a list the user approves (name, source, size).
2. **Senses** — measure it with numbers that have units, split it into parts, and pull evidence (frames, crops, clips,
   text) for Claude to look at or listen to. One adapter per kind of work, all with the same three verbs.
3. **Evidence of success** — platform metrics, analytics exports, replay/retention curves, sales, tests, awards, each
   with its source, grade (imported from a file / reported by the caller), date and baseline.
4. **Anatomy** — Claude labels the parts (hook, demo, proof, offer, cta…); each part is measured by the same sense.
5. **Comparison** — winners against controls, feature by feature, with effect sizes, sample sizes and confounders.
6. **Blueprint** — Claude's distilled way of making that kind of work: structure, steps, measurable targets and the
   evidence they rest on, behind evidence gates.
7. **Conformance and outcome** — a new work is measured against the blueprint; its real result, logged later, is what
   finally makes a blueprint trusted.

The core (`learnkit/`) imports no host package; EditVideo is one host. Through MCP it is one tool, `editvideo_learn`
(`action` + `request`; an empty action returns the full contract).

## Senses

| Kind | Reads | Measures (examples) | Spans | Evidence |
|---|---|---|---|---|
| text | .txt .md .srt .vtt | words, sentence length and long-sentence share, questions, numbers, second person, calls to action, headings, lists, lexical diversity; timed text: words/min, words in the first 10 s, first words, longest pause | `chars`, `t` | text excerpt |
| image | .png .jpg .webp … | size/aspect, luminance, contrast, saturation, colourfulness, edge density, empty space, text-like regions (MSER, not OCR), frontal faces, saliency focus and its distance to the thirds/centre, symmetry, palette | `box` | crop |
| audio | .wav .mp3 .m4a … | RMS level (not LUFS), peak, crest, loudness range, silence, onsets/s, tempo estimate + confidence, brightness, intro length, level at 25/50/75 %, where the energy peaks, sections | `t` | clip (≤30 s) |
| web | .html (+ screenshot) | words, blocks, h1/h2/h3, first heading, title/meta length, calls to action, how early the first one comes, hero words/CTA, forms/fields, images without alt, links, prices, social proof, quotes; with a screenshot: page height in screens and the first screen's tone/colour/text | `section`, `box` | block text, screenshot crop |
| video (EditVideo) | .mp4 .mov … | cuts/min, median shot, shot-length variation, first cut, edit events/min (punch-ins, graphic pops), gradual transitions, luminance, dark share, narration words/min, cuts on the beat, text/UI share; the look of the picture (`editvideo.look` medians over 2 s windows every ~8 s: detail, isolation, noise, shake, contrast, exposure level, saturation, warmth, upscale, and the shares graded A and C); `repeat_share` (shots whose middle frame shows another's scene again: thumbnails, or ORB features with a RANSAC homography, which see the same scene from a slightly different moment) | `t` | 8 frames (≤30 s) |

Parts are detected per kind (paragraphs, salient regions, audio sections, page blocks, 5/30 s video buckets) and
can be replaced by Claude's own anatomy. Everything a sense reads is data, not instructions.

A host adds a kind with `learnkit.senses.register(sense)`: an object with `kind`, `extensions`, `spans`, and
`measure(path, options)`, `measure_span(path, span, options)`, `evidence(path, span, out_dir, options)`, and optionally
`fingerprint(path, options)` (see `learnkit/fingerprint.py`; without one, measurements decide whether two works are one).

## Evidence of success

Raw success mostly measures reach: views follow channel size, age and topic. A signal therefore carries a
**baseline** with a note saying what it is (the channel's median views, the store's usual conversion rate…), and
comparisons split by the ratio to it by default. yt-dlp metadata next to a work is read automatically (views, likes,
comments, followers, views/day since upload, engagement rate, and YouTube's "most replayed" heatmap — relative replay
intensity, not retention). Analytics exports load from CSV (one row's metrics and/or a retention curve); a metric's
baseline can be read from the same file (`baseline: "others"`: the median of that column over the other rows, so the
usual result comes from the export, not from the caller). Numbers the caller types are graded `reported`.

## Comparison

`compare` takes explicit winners and controls, or splits a pool by a metric — for exploring. Copies count once:
statistics use one representative per distinct work (the median of its copies); a work whose variants sit on both
sides (an A/B test) is left out of the groups and its variants are compared within it instead (`variants`, a sign test
across such works). For **every** feature both groups measure (`features` only narrows what is shown) it reports both
medians and spreads, Cliff's delta with its magnitude (negligible < .147 ≤ small < .33 ≤ medium < .474 ≤ large), how
consistently winners sit on their side, an exact permutation p-value (normal approximation past 80 works), and two
corrections for testing them all, per family — the sense's own measurements, and the roles the caller labelled (labels
are the caller's, so they never dilute the measurements' correction): a Benjamini–Hochberg q (for reading) and Holm's
`p_holm` (what gates use: adding look-alike or invented features cannot lower it). With 5 vs 5 works the smallest
possible p is 0.008, so one perfect difference among 30 measurements has p_holm ≈ 0.24. Groups under 5 are
**exploratory**; a baseline that differs strongly between groups (followers), unknown audience sizes and mixed domains
are reported as confounders. These are associations in small samples, not causes — look at the works.

A rule is never judged on the groups the caller chose. The gate re-splits **every registered work of the blueprint's
kind and domain** into the top and bottom thirds by the comparison's metric relative to its baseline (works tied with a
group's last one join it), so hand-picked groups or a convenient split cannot back a rule; the cited comparison only
says which metric. The pool cannot be reshaped afterwards: once a work has evidence of success its kind and options
stay as they are (a refused re-registration changes nothing), its domain too unless nothing else uses the old one (a
typo, corrected and logged — and a work moved after its outcome was known is left out of every pool), a metric measured
against a baseline keeps one, domains match exactly (case and spacing aside), and a copy belongs to the pool of the
work that had evidence first — re-saving hand-picked works under a new domain makes no new pool (registration says
`same_work_as`). A blueprint keeps its kind and domain too. It can still be thinned beforehand — by never
registering the works that did badly — and nothing here can see that.

A feature that does not survive Holm can be **confirmed**. Each comparison target is a stated hypothesis — feature,
direction (from the comparison the caller looked at), metric and range — dated when first stated; changing any of them
states a new one, and every hypothesis goes into a store-wide ledger that only grows. Works registered after the date
(copies of any older work of the kind left out) are split the same way and tested for that one feature in that
direction, one-sided, at .05 divided by the number of hypotheses stated for this kind and domain, whatever their
metric, before those works came in (counted from the ledger and from the blueprints themselves) — so stating many and
keeping the one that fits pays for all of them. learnkit cannot know whether the
caller had seen those works' outcomes before registering them; register confirmation works as they come in.

## Blueprints and their levels

| Level | Needs |
|---|---|
| observation | cites a registered exemplar |
| candidate | 3+ distinct cited works of its kind with a signal above its baseline and an anatomy; most targets grounded: a comparison target whose comparison shows a medium+ effect with a range holding the winners' median and excluding the controls', or an `exemplars` target whose range holds those works' median and excludes the median of 3+ registered works of this domain that did not beat their baseline |
| rule | every comparison target on a measured feature holds on the domain's re-split (5+ distinct works each, audience size not confounded): a medium+ effect, a range holding the winners' median and excluding the controls', and p_holm ≤ .05 or confirmation — or **trials**: of the distinct new works it was applied to, so many beat their baseline that chance is unlikely (one-sided sign test at .05 divided by the series of trials run in this kind and domain: with one series 5 of 5, 7 of 8, 9 of 11…), with every target grounded on this domain. Targets on labelled roles are confirmed by trials only: labels are the caller's, usually made knowing the outcome |
| standard | the comparison route of rule, and trials as above with at least one winning outcome whose value *and baseline* were read from a file (`outcome_csv` with `baseline: "others"`) |

**Distinct** means not the same work, decided per kind from content, with three verdicts — same, unsure, distinct — of
which gates count *unsure* as the same work, so an edit cannot pass for new evidence:

- text and web pages: normalised (NFKC; format characters, combining marks, variation selectors and blank letters
  dropped; Cyrillic, Greek, Armenian and Cherokee look-alikes and Latin small capitals folded; case folded), then MinHash
  of 5-word shingles (*same*: a copy, padding, an excerpt) and of word pairs (*unsure*: a light edit, one word in ten
  or fewer changed on synthetic prose; a fifth changed reads as distinct); a web page by its own text, without its site
  furniture (header, nav, footer, aside, and elements whose role or class/id names a menu, navigation, masthead,
  sidebar, breadcrumb or footer — never html, body or main, and never one that holds the page's h1, main or article),
  so one site's pages stay apart; a page whose own text lies inside another page's whole text is the same work (a copy
  can hide its content in elements named like furniture); pages with under 20 shingles of their own get no verdict;
- images: pHash + dHash after stripping uniform borders, also mirrored and as the centre square (flips and square
  recrops of a wide picture are *same*);
- audio (band-energy bits every 0.1 s) and video (frame dHashes, 2 per second): matched in 5 s windows, each aligned on
  its own, so trims, excerpts of 5 s or more and speed changes of 2 % line up; *same* when 80 % of the shorter work's
  windows are found in the other, *distinct* at a third or less (a shared intro), *unsure* between (half shared).

Measured: 20 documents sharing a 60-word intro and sign-off, 0 of 190 pairs merged; 435 pairs of unrelated texts from one
100-word vocabulary, 0 merged; 8 product pages inside 280 words of div-built site chrome, 0 of 28 merged; 20 images
sharing one layout, 0 of 190 merged; audio copies (off-grid trims, 5 dB SNR noise, AAC/MP3/Opus, 2 % faster) all
*same*, other works and episodes sharing a 10 s intro of 60 s *distinct*; a pair of different 10-minute recordings is
told apart in about 3 ms. Works with nothing to compare (empty text, a page that is only site furniture, silence, a
plain image, one still frame) get no verdict, and measurements (every shared one within 2 %) decide for them and for
senses without fingerprints. Content verdicts are kept on disk per pair of files; older measurements and application
logs get a current fingerprint the first time they are compared. This holds in exemplar counts, comparison groups and
applications.

Promotion is explicit and refused with what is missing; readers see the lower of the stored and the supported
level; retiring never promotes. `conform` measures any work against a blueprint (each target in or out of range, with
the gap; structure and order when the work's parts are labelled). `apply` logs a real use: learnkit measures the work's
conformance and fingerprint itself. A use enters the **trials** when the work conformed (≥ 70 % of the targets as they
were when it was applied), has an outcome on the success metric with a baseline — the comparisons' metric, or without
one the metrics the cited exemplars beat their baselines on — and is a new work: not the same work as a registered
exemplar of that kind registered before it was applied. Each work counts once, by its first judged report (copies
included): reporting it again, withdrawing it (`kept: false`), editing a note or registering it as an exemplar later
does not remove a loss, so report outcomes when they are final. Changing the targets' features, ranges or structure,
judging on another success metric, or starting a new blueprint starts a new series of trials (each report records its
kind, domain and metric), and every series in the kind and domain shares the .05. Wins and losses both count, so trying until two succeed does not
make a rule. Copy status and success metrics
are judged again whenever the blueprint is read. A typed baseline is the caller's word (the status counts typed
outcomes); a baseline read from a file is computed by learnkit from the file's other rows — consistent, but only as
honest as the file. A retired blueprint has no level and cannot be applied. That is the trial-and-error loop with real
audiences, recorded.

Ids are counted once (a list naming a work twice is refused), a split that would cut through tied values is refused,
and comparisons record whether their groups are separated on the success metric (`separated_on`); explicit groups can
name that metric. Parts' shares and positions come from each sense's own units (seconds, characters of the
newline-normalised text, words of a page block, frame area) and must lie inside the work; order is read from the
work. A measurement is reused only when the same kind, options and sense version made it.

## Example (MCP)

```text
learn("register", {"path": "ads/a1.mp4", "domain": "vertical product ad"})          -> ex-…
learn("signals",  {"exemplar_id": "ex-…", "csv": {"path": "a1.csv", "metrics": {"views": "Views"}}})
learn("anatomy",  {"exemplar_id": "ex-…", "parts": [{"role": "hook", "span": {"t": [0, 2]}}, …]})
learn("evidence", {"exemplar_id": "ex-…", "span": {"t": [0, 4]}})                    -> 8 frames to look at
learn("compare",  {"domain": "vertical product ad", "split": {"metric": "views"}})   -> cmp-…
learn("distill",  {"blueprint": {…, "targets": [{"feature": "role_start_offer", …, "comparison_id": "cmp-…"}]}})
learn("conform",  {"blueprint_id": "bp-…", "path": "my_ad.mp4", "anatomy": […]})
learn("apply",    {"blueprint_id": "bp-…", "path": "my_ad.mp4", "outcome": [{"metric": "views", "value": 12000,
                   "baseline": 4000, "baseline_note": "my channel's median"}], "note": "…"})
learn("apply",    {"blueprint_id": "bp-…", "path": "my_ad.mp4", "note": "…", "outcome_csv": {"path": "videos.csv",
                   "metrics": {"views": "Views"}, "row": {"column": "Title", "equals": "my ad"}, "baseline": "others"}})
```

## Limits

- Evidence gates make chance, copies, hand-picked groups, restated hypotheses and selective trials hard to mistake for
  craft. They cannot see works that were never registered, cannot check numbers, files or labels the caller supplies,
  and cannot know what the caller had seen before stating a hypothesis.
- Fingerprints: an image cropped by more than about 4 % a side, a text with many of its words changed, audio sped up by
  3 % or more or buried under noise louder than its quiet passages can read as a different work. Different
  voice-overs over the same, louder music bed, half-shared episodes and A/B variants of one page or thumbnail can read as
  one work (A/B variants are compared within the work instead). An excerpt registered on its own joins the works it
  was cut from, which errs towards fewer distinct works. A video's fingerprint decodes the whole file once at
  registration; a file that cannot be decoded gets none and is compared by its measurements.
- A pool's first comparison pair by pair is slow for long media (the reviewer measured 2–5 ms per audio or video pair,
  about 50–100 s for 200 works); verdicts are then kept (about 150 bytes a pair), so later reads compare only new works.
  With 1,000 web pages in other domains a blueprint read takes about 0.4 s.
- Several works under one typo'd domain cannot be moved once they have evidence, and copies of them belong to the
  first pool, so check domains before adding outcomes.
- Whether a use enters the trials still depends on the anatomy and options given when it is applied, and on the caller
  reporting it at all; learnkit sees only the uses it is told about.

- Senses measure surfaces (pixels, levels, structure, words), not meaning or taste; Claude judges with the evidence.
- Text-like regions are a heuristic (no OCR); faces are frontal only; the focus point is saliency weighted by contrast
  to the background (on synthetic shapes within 0.15 of the shape; real scenes are harder); transparent pixels are shown
  over grey; levels are RMS not LUFS; tempo is an onset estimate (±3 % on click tracks from 62 to 190 BPM) reported with
  its half- and double-time readings, and none without a clear pulse; out-of-phase stereo is flagged because the mono
  downmix cancels; a web page's layout is known only from a screenshot; on a page, menu links count only as strong asks
  ("Get started"), footer links only when styled as buttons, and accordions, carousels, cookie banners and quantity
  steppers never (a restaurant's "menu" button is lost with them); the hero is the block with the first content h1 and
  its tagline; text calls to action count only as asks (opening a clause, after "please"/"hãy", before "now"/"ngay");
  video leans on `study_video`.
- Caller-typed values, baselines and outcomes cannot be verified; the gates require baselines, separation, distinct
  works and repeated real outcomes, and the status shows what was reported rather than imported.
- Analytics numbers whose separator could be thousands or decimals ("1.234", "4,5") are refused unless the export's
  `decimal` is given.
- Market signals are confounded (audience size, timing, topic, platform changes) and often self-reported; the gates
  ask for baselines, comparisons and repeated real outcomes for that reason, and still only show association.
- Nothing is fetched: works and metadata are local files; new downloads need the user's approval per batch.
