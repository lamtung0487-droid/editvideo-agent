## Cinematic treatment

Read [cinematic techniques](../../../../docs/CINEMATIC_TECHNIQUES.md) before designing anything meant to impress. Call `cinematic_catalog(query, project_id)` for the technique atlas (purpose for the viewer, use/avoid, needs, proven parameters, failure modes, verification) with readiness against the library and project.

Method: state the film's single idea → choose ONE hero technique that carries it (journey → continuous space: globe_dive / map_journey / trajectory_3d; person or place → text_behind_subject; archive stills → photo_3d) plus at most 2–3 supporting ones → for every beat write what the viewer must understand, the technique and the frames you will inspect. Cut any technique that only decorates.

Build with `compose_cinematic(recipe, dry_run=true)` first: recipes compute what eyes guess badly (title y for a target share covered by the SAM2 foreground; camera distance/travel that keep a photo plane's border out of view; arrival frames of a traveller on a 3D path; a Natural Earth map per journey leg) and the dry run returns audit findings for the new layers. Apply, then follow the [review loop](review.md).

Known pitfalls: dense 3D camera keys need `camera_ease:"linear"`; globe needs sun_lat/sun_lon and altitude ≥1 radius for a 5400 px texture; text centred on a subject disappears; strong bloom turns lines into haze; light leaks belong on motivated transitions only.
