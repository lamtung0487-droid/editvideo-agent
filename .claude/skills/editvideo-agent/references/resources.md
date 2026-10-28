## Resources, sources and credits

Read [resources](../../../../docs/RESOURCES.md). `resources(query, kind)` searches the local library (textures, models, geodata, footage) with licence/credit; import by absolute path. `geo(name, outline_only)` gives Natural Earth outlines for globe borders or projected SVG maps for map_journey.

New media: `find_sources(query, provider wikimedia|nasa, media)` returns candidates only (licence, author, size, page). Present file, source, licence and size to the user and wait for explicit approval per file/batch; then `fetch_source(..., expected_bytes)`. Register files you create from library items with `register_resource(path, derived_from=id)`; record unknown licences as `unknown`, never guess. Before delivery, `project_credits(project_id)` compiles credits by tracing each asset through imports and media tasks.
