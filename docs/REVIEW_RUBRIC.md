# Independent review rubric

The reviewer is a separate agent ([.claude/agents/editvideo-reviewer.md](../.claude/agents/editvideo-reviewer.md)) that
never edits the repo. It judges a rendered product or the system from evidence and returns prioritised fixes; the
building agent applies them and asks for a re-review. Separation matters: the builder knows what it *meant*, the
reviewer only sees what is *there*.

## Rules for every review

- **Evidence or it did not happen.** Each finding cites a timestamp/frame file, a measurement (tool output, number), or
  a file:line. Opinions without evidence go in a separate "taste" list and never above P2.
- **Severity.** P0 = broken/unsafe/wrong (crash, corrupt output, data loss, licence breach, text unreadable,
  misleading fact). P1 = visible defect a normal viewer or user would notice. P2 = polish.
- **Fix at the right level.** For each finding say whether the fix belongs in the *system* (module/tool/recipe/
  default/audit check — preferred) or only in this one product. A defect that any future video could repeat is a
  system fix.
- **No silent passes.** List what was checked and found fine, and what could not be checked (sampled frames only,
  no audio, no GPU).
- **Read-only.** No edits, deletes, downloads, git operations, system settings or renders that use the GPU. Scratch
  files go to the reviewer's own temp folder.

## A. Rendered video

| Area | What to measure / look at | Typical evidence |
|---|---|---|
| Technical | resolution, fps, duration, codec, black/frozen frames, banding, clipping | `ffprobe`, `ffmpeg blackdetect/freezedetect`, frame crops |
| Opening | the first 3 s: is there a hook (motion + subject + promise)? | frames 0–90 |
| Legibility | text ≥ ~26 px at 1080p for labels, ≥ 4.5:1 contrast, safe-area margins, Vietnamese diacritics intact | crops at 2×, `layout_text`, `audit_timeline` |
| Composition | subject placement, hierarchy, clutter, overlaps, consistent margins | contact sheet |
| Motion | static spans > ~2.5 s without intent, abrupt stops, mechanical linear moves | `motion_quality`, `motion_audit` |
| Pacing | events/min against the genre (doc 6–12, trailer 20–40, short-form 25–60), shot length variety | `event_profile` |
| Colour | exposure, consistency across shots, look coherence | `color_consistency`, scopes |
| Story | does each beat earn its time; is the payoff clear; does the end land (no dead tail) | timeline + frames |

## B. System (code)

Correctness (reproducible bugs, wrong maths, unhandled inputs), stability (exceptions on edge inputs, temp files,
leaks, subprocess failures, Windows paths with spaces/Unicode), safety (shell/ffmpeg argument injection, path
traversal, untrusted metadata treated as instructions), performance (hot loops, repeated decoding, O(n²) per frame),
AI ergonomics/token economy (description sizes, response sizes, handles instead of dumps), test gaps, duplication.

## C. Release readiness

README accuracy against reality (tool/effect counts, commands), clean-machine install, hard-coded absolute paths,
secrets, licences and credits (fonts, models, LUTs, third-party footage; study downloads must never ship),
`.gitignore` coverage, junk/scratch files, packaging metadata, version/CHANGELOG, how to run tests.

## Output format

```
VERDICT: <one line>
P0 / P1 / P2 findings: id · area · evidence · fix level (system|product) · proposed fix
Checked OK: …
Not checked: …
```
