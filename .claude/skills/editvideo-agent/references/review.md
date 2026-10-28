## Evidence review loop

Read [review and evidence](../../../../docs/REVIEW_AND_EVIDENCE.md). Stills cannot show judder and eyes miss corner reveals; use measurements:

1. `audit_timeline(project_id)` before rendering — camera stops/oscillation, magnified textures, photo-plane edges in view, projected 3D label collisions, reading load, small text, overlapping text boxes, safe regions, static holds, transition repeats, bloom/leak coverage. Each finding: level, measurement, threshold, next step.
2. `review_frames(project_id, frames, layer_ids)` on the frames audit or recipes name — glyph-level visible/covered/same-as-background fractions, WCAG contrast against the real plate, overlay image (cyan visible, red covered, yellow <3:1).
3. Render, then `motion_audit(path, project_id=...)` — duplicate frames (24/25p cadence), periodic judder, near-static spans, calm shots relative to the film, brightness jumps. Grain/encoder noise is filtered out.
4. `cut_audit(path, project_id)` — eye-trace jump, cutting on action and shot-length rhythm per cut, with a contact sheet.
5. `storyboard(check=true, render_path)` — drift from the saved plan (reveals, techniques, negative list, breather).
6. `project_credits(project_id)` for credits traced through provenance.

Findings are evidence, not verdicts: decide from intent, fix with patch/recipes, re-measure the same frames.
