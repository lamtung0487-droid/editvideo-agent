# Measured reference sequences (own measurements, 2026-10-27)

Method: local study copies (YouTube uploads, internal research only) in `<data drive>/EditVideo-data/study_refs/news_montage/`.
Hard cuts by FFmpeg `scdet` (threshold 10, 480 px wide); dissolves and graphic wipes are NOT counted, so a sequence
built on dissolves (Godzilla 2014) shows few cuts. Loudness by FFmpeg `ebur128` (momentary 400 ms, every 100 ms) on
the upload's audio; uploads may be re-mastered, so absolute LUFS are indicative, the shape (rise, dips) is reliable.
Contact sheets every 1.5-2 s were inspected by eye. Script: a production script kept out of the public repository.

## World War Z (2013) opening titles — `wwz_opening/kQaSS1_EnI0.mp4`, 127.5 s
- 78 hard cuts, ASL 1.61 s, median shot 1.5 s, p10 0.46 s, p90 2.33 s, shortest 0.17 s.
- Acceleration by thirds: ASL 2.36 s → 1.63 s → 1.25 s; the last 10 s before the title: ASL 0.56-0.62 s (8-9 cuts per 5 s).
- No 1-2-frame flash frames detected; 2 shots ≤ 6 frames.
- Loudness: a continuous crescendo, momentary mean ≈ −47 LUFS in the first 5 s, −41 by 10-25 s, −33 by 30-85 s,
  −23 by 90-120 s: about +25 LU over 2 minutes, steepest in the last 35 s. First ~14 s nearly silent (credits on black).
- Structure seen on the sheet: credits on black (0-10 s) → a calm sunrise → everyday life (cities, suburbs, subway,
  airports' departure boards) intercut with news (market tickers, TV anchors, "DOLPHINS STRANDED" lower thirds, a
  scientist talking head) and nature swarms/predators (starlings, ants, crocodiles, wolves, fish shoals) → crowds,
  traffic jams, protests → the title assembles from fragments. Credits sit on black slanted wedges (a black panel cut
  diagonally) beside the footage, every few shots. One caller-transcript caption appears late ("CALLER: ...").

## Kong: Skull Island (2017) main titles — `monsterverse_titles/Fa5Ov1AetqY.mp4` 124-222 s, 98 s
- 146 hard cuts, ASL 0.67 s, median shot 0.50 s, p90 1.41 s; only 8 shots ≥ 2 s.
- Shot-length histogram: 45 shots of ≤ 2 frames (flash/leader frames, film-gate flicker), 53 ≤ 6 frames, 20 of 0.2-0.5 s,
  39 of 0.5-1 s, 27 of 1-2 s, 8 ≥ 2 s. By thirds ASL 0.80 → 0.63 → 0.62 s: fast from the start, not accelerating.
- Loudness: a 10 s intro rising from −38 to −21 LUFS, then flat at about −20 LUFS (LRA 5.6 LU): the music drives at
  constant intensity; the energy comes from cutting, not from a crescendo.
- Look: real 1945-1973 newsreel (Japan surrender headline, Truman, Eisenhower, Sputnik, Castle Bravo, DNA model,
  moon landing, civil rights march, Vietnam helicopters and troops); every shot keeps its period texture; many shots
  are shown as a projected film frame with rounded corners and gate edges on black, slightly off-centre; red/orange
  leader and flash frames between shots; occasional headline type full-screen ("JAPAN SURRENDER", "U.S. UNVEILS EARTH
  SATELLITE"); a fictional overlay ("DIRECTIVE 27 — CASTLE BRAVO TEST AND DESTROY") stamped over real footage.
- Text: small, widely tracked capitals in a warm yellow, centred, for both credits and date supers ("MAY 1949",
  "SEPTEMBER 1953", "JUNE 1956", "DECEMBER 1947"); the dates walk the viewer through time.

## Godzilla (2014) main titles — `godzilla2014_titles/NBQJjqnG1iI.mp4` (official WB upload), 127 s
- Only 11 hard cuts (ASL 10.6 s) because transitions are dissolves and pushes; visually ≈ 50+ distinct images.
- Loudness: a steady crescendo from about −28 LUFS (0-5 s) to −15 LUFS (90-95 s) (+13 LU), then the blast and three
  quiet dips (98.5-99.2 s, 102.8-105 s, 108.3-112.9 s, momentary < −40 LUFS) around a white-out; integrated −18.8 LUFS,
  LRA 14 LU (wide: the silence matters).
- Structure on the sheet: 0-12 s very dark macro moves over engravings, Darwin's title page, old charts and sea-monster
  sketches → 14-30 s newspapers ("CAPTURED ON SONAR", "GOVERNMENT DENIES REPORTS OF THIRD MISSING"), telegrams,
  typewritten pages → 30-60 s black-and-white 1950s footage (boats, scientists, "RADIATION AREA" sign, MONARCH "EYES
  ONLY" stamp, sonar rings, islands from the air) → 60-90 s colour-tinted 1950s military footage (observers in goggles,
  the bomb on its tower) → 90-100 s nuclear blasts, mushroom clouds → 100-112 s white-out, near silence, then the small,
  widely spaced title "GODZILLA" on pale grey → cut to jungle.
- Text: every credit is a line of document text whose words are covered by white/grey redaction bars, leaving only the
  name; names sit in the footage's negative space (left-centre); small, light weight. Palette: desaturated green-grey,
  heavy vignette, dark.

## Dawn of the Planet of the Apes (2014) opening — `dawn_apes_opening/QgHATo0d3YA.mp4`, 132.6 s
- 0 hard cuts: one continuous move over a dark world map; news footage plays INSIDE the land masses (continents act
  as a matte), red flight-path arcs and red dots spread and multiply; colour moves from cold blue-grey to red and
  orange fire, then drains; final ~40 s the map darkens to near black with a few red dots left (lights going out).
- Loudness: mostly −35 to −41 LUFS momentary with many short dips (sparse score and news voices), then fades to
  −60 LUFS over the last 15 s: an ending by draining, not a slam.

## Inferences for the system (mine)
- Three different archetypes, each a separate recipe:
  1. "Flood" (Kong/WWZ): ASL 0.6-1.6 s with flash frames, either constant (Kong, music at a flat −20 LUFS) or
     accelerating (WWZ, ASL 2.4 → 1.25 s by thirds and 0.6 s at the end, with +25 LU crescendo).
  2. "Dossier" (Godzilla): slow dissolves over documents and footage, redaction bars as the text system, a
     13 LU crescendo, a white-out and 5-10 s of near silence before a small title.
  3. "Map matte" (Dawn): continuous camera over a map, footage visible through the land, spreading red network,
     ends by draining to dark.
- Shared: real archive keeps its period texture per source; dates/places in small tracked capitals; the threat
  shown early; the climax is followed by a quiet beat.
