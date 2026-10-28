# Editing, sound and finishing craft, plus delivery standards, for high-end historical documentaries

Scope: sourced rules and numbers an automated editing system can encode as defaults and checks. Researched 2026-10-27. Each figure is labelled by context: **broadcast** (EBU, ATSC, Ofcom), **streaming** (Netflix and other SVOD) or **web** (YouTube, music/podcast platforms, social). Several Netflix Partner Help pages now redirect to a JavaScript-only portal (studiopartner.netflix.net) that could not be read. Where a Netflix figure comes from an older help-page version or a trade article quoting it, that is said.

---

## 1. Editing craft: Murch's Rule of Six, documentary practice for archival films, shot lengths, Ken Burns' editors

### Takeaway
Murch's Rule of Six gives a weighted priority order for judging a cut: emotion 51, story 23, rhythm 10, eye-trace 7, 2D screen plane 5, 3D space 4. When criteria conflict, give up the lower ones first. Ken Burns' editors work audio-first. They build a "blind assembly" (a radio play of narration and interviews), put music in from day one, give each still a reason to be there (about 250 stills per cut), and leave "breathing room" after emotional beats, sized to the weight of the moment. No published, measured average shot length (ASL) for acclaimed archival documentaries was found.

### Cited Findings

**Rule of Six (Murch, *In the Blink of an Eye*, 2nd ed. 2001)**
- The six criteria and weights: emotion 51%, story 23%, rhythm 10%, eye-trace 7%, two-dimensional plane of screen 5%, three-dimensional space of action 4%. Emotion alone outweighs the other five combined. — [UT Austin RTF wiki, "Murch's Rule of Six"](https://cloud.wikis.utexas.edu/wiki/spaces/rtf318/pages/80022510/Murch+s+Rule+of+Six); [No Film School](https://nofilmschool.com/2016/11/6-rules-good-cutting-according-oscar-winning-editor-walter-murch)
- Sacrifice from the bottom of the list upward. A cut that is right on a higher criterion hides problems on lower ones, but not the reverse. — [UT Austin RTF wiki](https://cloud.wikis.utexas.edu/wiki/spaces/rtf318/pages/80022510/Murch+s+Rule+of+Six)
- Eye-trace means the location and movement of the audience's focus of interest within the frame, and how it carries across the cut. — [UT Austin RTF wiki](https://cloud.wikis.utexas.edu/wiki/spaces/rtf318/pages/80022510/Murch+s+Rule+of+Six)
- Sources label the sixth criterion differently: "three-dimensional space of action" in most, "three dimensional plane of screen" in a Vimeo summary. — [Vimeo "Walter Murch's Rule of Six"](https://vimeo.com/154554714)
- Blink theory: while cutting *The Conversation*, Murch noticed his cut points matched Gene Hackman's blinks. He treats a cut as a blink that punctuates a thought, and writes that real-life blink rates and film cutting rates are "close enough for comparison." — [Musicbed, "Editing secrets from Walter Murch"](https://musicbed.com/blog/filmmaking/editing/editing-secrets-from-legendary-editor-walter-murch)
- Murch does not treat the blink as a rule. He tells editors to find their own approach and "override this blinking thing" when that feels right. — [ProVideo Coalition, Murch Q&A](https://www.provideocoalition.com/aotc-murch-bcpc/)

**Ken Burns / Florentine Films editing practice**
- *The Vietnam War* opening began four and a half years earlier as a 28-minute "blind assembly," an audio-only radio play of possible narration, with Burns reading scratch narration to test phrasing and timing. — [MasterClass, "How Ken Burns edited The Vietnam War"](https://www.masterclass.com/articles/how-ken-burns-edited-the-vietnam-war-documentary) (search-result excerpt; page returned 403 when fetched)
- Craig Mellish (Florentine Films editor: *The National Parks*, *Lewis & Clark*, *The Dust Bowl*) — [ProVideo Coalition, "Art of the Cut: Craig Mellish"](https://www.provideocoalition.com/art-cut-ken-burns-doc-editor-craig-mellish-ace/amp/):
  - He times still moves in the Avid first, then frames and animates them in a separate program (MovingPicture) and imports the QuickTime. For broadcast, an assistant rebuilds the same moves in After Effects on the high-resolution masters.
  - A cut can hold about 250 stills. Each must earn its place: he swaps a weak image out rather than stacking alternatives. The *Vietnam* image archive was about 12,000 images.
  - Establishing and closing images often stay up longer, especially when the music resolves or fades.
  - Music goes in from day one and shapes the cut. It is not temp music replaced at the end. Themes are re-recorded at different tempos, moods and instrumentations, tied to characters, and brought back as callbacks. A scene can stay without music for weeks until the right track turns up.
  - Interview pauses are left in for long stretches when the subject is reflecting, but not when the subject is searching for words. When several people tell the same story, he keeps whoever tells it best.
  - Breathing room after an emotional moment is sized to how heavy the scene is: long enough to absorb it, short enough to keep the film's thread.
  - Interviews are sometimes cut first as a blind assembly (talking heads plus narration only). Blind assemblies of about 4 hours are cut to about 2. Working reels run 20 to 25 minutes, and episodes run 90 to 120 minutes or more.
  - Sound effects (gunfire, explosions, ambiences) are added to archival footage as "sweeteners" and to set the location. They also work as transitions, for example a passing jet or a helicopter taking off. The picture editor's effects are a template that the sound editors refine after lock.
- Picture editors on *The Vietnam War* cut footage in during an interviewee's pauses, with the sound designer's track shaped to the rhythm of his story. — [Motion Picture Association, interview with sound designer Jacob Ribicoff](https://www.motionpictures.org/2018/10/the-vietnam-war-sound-designer-on-enhancing-emotional-memories-of-the-war/)
- Editor Paul Barnes (*The Vietnam War*) calls the work "emotional archaeology": the goal is to evoke emotion so viewers connect with historical events. — [New Mexico PBS *¡COLORES!*, Paul Barnes interview](https://newmexicopbs.org/productions/colores/?p=3608)

**Shot length data**
- In the Cinemetrics-based dataset (films released 1997 to 2016, 1,037 submitters), documentaries have the fewest shots of any genre, averaging 491, against 1,913 for action. The article gives ASLs for action (4.0 s), adventure (5.1 s), sci-fi (6.2 s) and horror (15.7 s), but not for documentary. — [Stephen Follows, "How many shots are in the average movie?"](https://stephenfollows.com/many-shots-average-movie/)
- Cinemetrics reports minimum, maximum and median shot length and standard deviation, not only the mean. Its database held over 7,000 films when Film Comment covered it. — [Film Comment, "Site-specifics: Cinemetrics"](https://www.filmcomment.com/article/site-specifics-cinemetrics.lv?print)
- Methodology caveat: some shot-length studies measured only the first 1,800 seconds of a film, which can under- or over-estimate the whole-film mean. — [CINEJ Cinema Journal](https://cinej.pitt.edu/ojs/cinej/article/view/50/195)

### Inferences
- The Rule of Six can work as a weighted scoring rubric for automated cut review: score each candidate cut on the six axes with the 51/23/10/7/5/4 weights. A low emotion or story score blocks the cut. A low eye-trace or 3D-space score only produces a warning.
- An eye-trace check is feasible: compare the salient point or face centroid in the last frames of shot A with the first frames of shot B, and flag big jumps on fast cuts. Murch weights this only 7%, so it should be advisory.
- Burns-style workflow for an automated system: (1) build the narration and interview "radio cut" and lock its timing; (2) put music in from the start, not at the end; (3) give every still a declared purpose, and drop stills without one rather than duplicating coverage; (4) after emotional beats, add a pause that scales with an emotion-weight tag; (5) hold the opening and closing images of a sequence longer, timed to the music's resolution.
- Documentaries average about 491 shots against 1,900 for action. Over an 80 to 100 minute runtime that is roughly 10 to 12 seconds per shot. This is arithmetic on the Follows averages, not a measured documentary ASL, so treat it as a loose sanity range only. Per Cinemetrics practice, report the median and the spread as well as the mean.

### Gaps
- No measured ASL was found for Ken Burns films or other acclaimed archival documentaries. Cinemetrics database entries for specific titles (*The Civil War*, *The Vietnam War*, *They Shall Not Grow Old*) were not checked and would be the next source.
- No primary editor interview was found that gives explicit rules for J-cuts, L-cuts, sound bridges, match cuts or deliberate silence in archival documentaries. These techniques are standard practice, but this session found no citable numbers (for example a typical J-cut lead of N frames).
- The first-edition date of *In the Blink of an Eye* (1995) comes from prior knowledge and was not verified here. Only the 2nd edition (2001) was confirmed. One search summary said the framework dates from "the early 2000s", which is probably the 2nd edition date.
- The MasterClass Ken Burns lessons (sound design, editing process, Vietnam case study) are paywalled and returned 403.

---

## 2. Sound: loudness and dynamics delivery, LRA, dialogue intelligibility, music editing, archival sound design, narration over music

### Takeaway
Integrated loudness targets depend on the outlet. **Broadcast**: EBU R128 is −23 LUFS ±0.5 LU (±1 LU live) with true peak ≤ −1 dBTP; ATSC A/85 is −24 LKFS ±2 with a recommended −2 dBTP. **Streaming**: Netflix is −27 LKFS ±2 LU measured on dialogue (dialogue-gated, BS.1770-1), true peak ≤ −2 dBTP, with LRA guidance of 4 to 20 LU for 5.1, 4 to 18 LU for stereo and dialogue LRA ≤ 7 LU. **Web**: YouTube, Spotify, TIDAL and Amazon normalise to about −14 LUFS, Apple Music to −16 LUFS, all with −1 dBTP. AES TD1008 puts speech content at −18 LUFS. No standard ducking depth exists. The only sourced anchor is the UK DPP's requirement of at least 4 LU between dialogue and background. Ken Burns' sound team builds sound for silent (MOS) archive from scratch: literal layers first, then abstract ones, up to about 150 to 160 tracks.

### Cited Findings

**Broadcast: EBU R128 (Europe)**
- Programme loudness −23 LUFS. Target tolerance ±0.5 LU since R128 v3.0 (2014). The current version is v5.0 (21 Nov 2023), which adds a reference to supplement s4 on loudness for cinematic content. R128 also specifies the Loudness Range and Maximum True Peak descriptors. — [EBU, R 128 publication page](https://tech.ebu.ch/publications/r128)
- ±1 LU is allowed for less predictable material such as live programmes. True peak ≤ −1 dBTP. Meter windows: momentary 400 ms, short-term 3 s, integrated over the whole programme, with an absolute gate at −70 LUFS and a relative gate 10 LU below. — [Wikipedia, "EBU R 128"](https://en.wikipedia.org/wiki/EBU_R_128) (cites the EBU documents)
- R128 sets no maximum LRA. Limits are left to aesthetics or playback context; ARTE publishes its own LRA guidelines. Supporting documents: Tech 3341 (metering, "EBU Mode"), Tech 3342 (LRA), Tech 3343 (production guidelines), Tech 3344 (distribution guidelines). — [Wikipedia, "EBU R 128"](https://en.wikipedia.org/wiki/EBU_R_128)
- LRA is computed from 3-second blocks, discarding the bottom 10% and top 5% of the distribution. — [EBU R128 search summary via Flux MIRA metering docs](https://doc.flux.audio/mira/Metering_Loudness.html)
- ORF (Austria) uses −3 dBTP for data-reduced formats. — [Wikipedia, "EBU R 128"](https://en.wikipedia.org/wiki/EBU_R_128)

**Broadcast: ATSC A/85 (US)**
- −24 LKFS, true peak −2 dBTP (recommended). Mandatory for commercials under the CALM Act. Current document: A/85:2013 with Corrigendum 1 (2021). Uses an "anchor element" (dialogue) approach. — [Fora Soft, "LUFS targets per platform 2026"](https://www.forasoft.com/learn/audio-for-video/articles-audio/lufs-targets-per-platform-2026)
- Tolerance ±2 LU (ATSC A/85). — [EditingTools loudness page (Danish)](https://da.editingtools.io/loudness/) (secondary source)

**Broadcast: other LRA specs**
- UK DPP: programme LRA ≤ 18 LU, speech LRA ≤ 6 LU, and at least 4 LU between dialogue and background. Canadian broadcasters: LRA < 10 LU (some ask for 8) and −24 LUFS for both the programme and the dialogue stem. — [Production Expert, 30 Aug 2018](https://www.production-expert.com/home-page/2018/8/23/has-netflix-turned-the-clock-back-10-years-or-is-their-new-loudness-delivery-spec-a-stroke-of-genius)

**Streaming: Netflix**
- "Average loudness must be −27 LKFS +/− 2 LU dialog-gated." Meters set to "1770-1 dialog-gated", measured with Dolby Media Meter or NUGEN VisLM. The gate is Dolby Dialogue Intelligence, not the BS.1770-3/4 relative gate. Recommended dialogue range −25 to −29 LKFS. "Peaks must not exceed −2 dB True Peak." — [Production Expert, quoting Netflix Sound Mix Specifications & Best Practices](https://www.production-expert.com/home-page/2018/8/23/has-netflix-turned-the-clock-back-10-years-or-is-their-new-loudness-delivery-spec-a-stroke-of-genius); [Netflix Sound Mix Specifications & Best Practices v1.5](https://backlothelp.netflix.com/hc/en-us/articles/360001794307-Netflix-Sound-Mix-Specifications-Best-Practices-v1-5)
- Netflix recommends true-peak limiters on all beds and objects at −2.3 dBTP or lower. — [Netflix Sound Mix Specifications v1.5 (search excerpt)](https://backlothelp.netflix.com/hc/en-us/articles/360001794307-Netflix-Sound-Mix-Specifications-Best-Practices-v1-5)
- Netflix LRA guidance: 5.1 programme LRA 4 to 20 LU, 2.0 programme LRA 4 to 18 LU, dialogue LRA ≤ 7 LU, and "a 4 LU difference between FX and dialog". The exact wording of the last item was not seen. Netflix's stated reason is that titles with more limited dynamic range play best. — [Production Expert](https://www.production-expert.com/home-page/2018/8/23/has-netflix-turned-the-clock-back-10-years-or-is-their-new-loudness-delivery-spec-a-stroke-of-genius)
- Rationale for dialogue gating: under full-programme measurement, titles passed with near-inaudible dialogue because loud effects and music raised the average. Dialogue is the anchor. — [Production Expert](https://www.production-expert.com/home-page/2018/8/23/has-netflix-turned-the-clock-back-10-years-or-is-their-new-loudness-delivery-spec-a-stroke-of-genius)
- Print master QC thresholds in a separate Netflix article: true peak must not exceed −1 dBTP, and loudness −27 LKFS ±3 LKFS dialogue-gated (BS.1770-1). This is looser than the mix target. — [Netflix, "Original Language Mix for Streaming and Archive"](https://backlothelp.netflix.com/hc/en-us/articles/115001539991) (search excerpt)
- When a mix measures under 15% dialogue, program-gated measurement is used instead: −24 LKFS ±2 LU, BS.1770-3. — [Auphonic, "Dialog loudness normalization" (2020)](https://auphonic.com/blog/2020/10/08/dialog-loudness-normalization/) (search excerpt); consistent with [Fora Soft 2026](https://www.forasoft.com/learn/audio-for-video/articles-audio/lufs-targets-per-platform-2026), which cites Netflix Sound Mix Specifications v1.6
- Netflix's QC page "Loudness and True Peaks: How to Measure and When to Flag" exists but now redirects to a JavaScript portal that could not be read. — [Netflix help article 360050414014](https://backlothelp.netflix.com/hc/en-us/articles/360050414014-Loudness-and-True-Peaks-How-to-Measure-and-When-to-Flag)

**Web and other platforms (2026)**
- YouTube −14 LUFS, true peak −1 dBTP, turn-down only (never boosts). Spotify −14 (Loud −11 with limiter, Quiet −19). TIDAL, Amazon Music and SoundCloud −14. Deezer −15. Apple Music (Sound Check) −16, aligned to AES TD1008. Apple Podcasts −16 ±1 LU (about −19 for mono). AES TD1008 (2021) streaming: music −16, speech/news/drama −18, mixed/sports −17 LUFS, all at −1 dBTP. TikTok, Instagram and Meta publish no target (about −14 is an internal estimate) and advise −1 dBTP. — [Fora Soft, "LUFS targets per platform 2026" (published 2026-06-05)](https://www.forasoft.com/learn/audio-for-video/articles-audio/lufs-targets-per-platform-2026)
- Conflict: a 2021 Live Sound article lists YouTube at −13 LUFS. — [Live Sound International, April 2021](https://digital.livesoundint.com/april-2021/page-22)
- AES TD1008 normalises speech 2 to 3 LU quieter than music because speech reads louder on the BS.1770 meter. — [Fora Soft 2026](https://www.forasoft.com/learn/audio-for-video/articles-audio/lufs-targets-per-platform-2026)

**Ducking narration over music**
- Mixing handbooks and broadcaster recommendations do not define best practice for ducking depth. A University of Salford study measured ducking in TV documentaries and ran a listening test; its numbers could not be retrieved (403). — [Salford repository](https://salford-repository.worktribe.com/OutputFile/1489990) (search excerpt)
- A re-recording mixer notes that audible ducking is acceptable in documentary, unlike narrative drama, where it should go unnoticed. — [DVinfo forum](https://dvinfo.net/forum/archive/index.php/t-531177.html)
- Mix-minus practice: mix with the narration muted first, then ride a VCA around the narration. This keeps an unducked music and effects mix for foreign-language versions. — [Gearspace, "Mix-minus techniques"](https://gearspace.com/threads/mix-minus-techniques.868655/)

**Archival sound design (Ken Burns / *The Vietnam War*)**
- Sound designer and music editor Jacob Ribicoff: "rarely did any of the archival footage have sound that was usable." The team added Foley: footsteps, movement through jungle, night insects, daytime birds over rice paddies, helicopters, weapons. — [MPA interview with Jacob Ribicoff](https://www.motionpictures.org/2018/10/the-vietnam-war-sound-designer-on-enhancing-emotional-memories-of-the-war/)
- Treatment followed the footage's condition. Degraded North Vietnamese footage got "smudged" sounds, played "very quietly or mixed at a low level", unlike clearer American footage. — [MPA / Ribicoff](https://www.motionpictures.org/2018/10/the-vietnam-war-sound-designer-on-enhancing-emotional-memories-of-the-war/)
- A 2 to 3 day session in New York recorded Vietnamese voices of different genders and ages, from jungle whispers to a crowd during the fall of Saigon. — [MPA / Ribicoff](https://www.motionpictures.org/2018/10/the-vietnam-war-sound-designer-on-enhancing-emotional-memories-of-the-war/)
- Layering order: the first layer duplicates what is on screen. Chaotic footage (flares, handheld bomb blasts) gave "license to use echo, tones". For one veteran's account he mixed helicopter blades with a heartbeat that sped up and slowed toward the climax. — [MPA / Ribicoff](https://www.motionpictures.org/2018/10/the-vietnam-war-sound-designer-on-enhancing-emotional-memories-of-the-war/)
- Scale: Burns said the maximum track count in *The Vietnam War* was 160, mid-Tet Offensive. Vanity Fair reported battle scenes layered with up to 150 tracks. — [WHRO, "The Vietnam War music highlights unsung heroes"](https://whro.org/21-arts-entertainment/477-the-vietnam-war-music-highlight-unsung-heroes) (search excerpt)
- "Most of the footage we receive is MOS, without sound, and we have to build it from scratch." — [MasterClass, Ken Burns, "Sound Design" chapter](https://www.masterclass.com/classes/ken-burns-teaches-documentary-filmmaking/chapters/sound-design) (search excerpt)
- Emmy-nominated sound editing team for Episode 6 "Things Fall Apart" included Erik Ewers, Dave Mast, Jacob Ribicoff and Mariusz Glabinski (sound effects editor). — [Television Academy](https://televisionacademy.com/shows/vietnam-war)

### Inferences
- Encode loudness profiles as data, not constants:
  - `broadcast_ebu`: −23.0 LUFS integrated, ±0.5 LU, true peak ≤ −1.0 dBTP, LRA warning above about 18 LU (DPP).
  - `broadcast_atsc`: −24 LKFS ±2, true peak ≤ −2 dBTP.
  - `netflix`: dialogue-gated −27 LKFS ±2, true peak ≤ −2 dBTP (limiter at −2.3), LRA 4 to 20 (5.1) or 4 to 18 (2.0), dialogue LRA ≤ 7. Fall back to −24 program-gated when dialogue is under 15%.
  - `web_youtube`: about −14 LUFS, true peak ≤ −1 dBTP. A quieter master is not boosted, so −14 to −16 is safe.
  - `web_speech_aes`: −18 LUFS, true peak ≤ −1 dBTP.
- ffmpeg's `ebur128` and `loudnorm` filters implement BS.1770-4 relative gating, not Dolby Dialogue Intelligence. A local system can approximate Netflix's measure by measuring the narration and interview stem alone (the stem is effectively dialogue-gated). Treat the result as advisory, not a pass/fail Netflix verdict.
- Ducking default for narration over music, inferred from the DPP "≥ 4 LU dialogue-to-background" anchor and documentary practice: keep the music bed's short-term loudness at least 4 LU, preferably 8 to 12 LU, below narration short-term loudness while narration is active. Ramp in about 200 to 500 ms before the line and release over about 0.5 to 1.5 s. Allow audible ducking. The timing values are not sourced.
- Always render a mix-minus (music and effects without narration) alongside the full mix. It is needed for later Vietnamese/English re-voicing, which matches the project's "silent renders, voice later" approach.
- Archival sound layers, from the Ribicoff method: (1) a literal layer matching visible action; (2) ambience setting the location (insects, birds, wind); (3) a degradation pass that matches the sound's fidelity to the picture's condition (low-pass, lower level, "smudge") for poor footage; (4) an optional abstract or emotional layer (tones, echo, heartbeat) used sparingly on chaotic or emotional beats.

### Gaps
- The current Netflix Sound Mix Specification (v1.6 or later, 2026) could not be read directly; the portal requires JavaScript. The −27 / −2 dBTP / LRA figures come from v1.5-era quotes (2018) and a 2026 secondary table that cites v1.6.
- Exact EBU Tech 3343 LRA advice for documentaries was not retrieved. The EBU R128 PDF was not opened, so the −1 dBTP and ±1 LU live values come from Wikipedia citing the EBU.
- Apple TV+, Amazon Prime Video and Disney+ delivery loudness specs were not found. These are usually in partner-only specs.
- No sourced dB figure for documentary music ducking. The Salford study's numbers were blocked.
- Music editing rules (cutting on phrase boundaries, stingers, using silence) are covered only qualitatively by Mellish (music from day one, themes re-recorded at several tempos, images held as music resolves). No sourced numeric rule was found.
- Dialogue intelligibility metrics (for example STOI or speech-to-background ratios beyond the DPP 4 LU) were not found in primary documents.

---

## 3. Picture finishing: colour pipelines for archival + CG, grain matching, delivery specs, subtitles (Vietnamese/English)

### Takeaway
High-end documentaries put mixed sources into one scene-referred working space (ACES/ACEScct) and grade two deliberate looks, one for archive and one for new material. They then degrade modern or CG imagery (softening, grain, a slight chroma "video" feel) so it sits with the archive, rather than sharpening the archive. Netflix delivery is IMF Application #2E (SMPTE ST 2067-21), with HDR mastered in Dolby Vision; Dolby Vision, HDR10 and SDR streams are all derived from that master. For subtitles, Netflix uses 42 characters per line and 2 lines for both English and Vietnamese. Reading speed is 20 characters per second for English adult content but 17 for Vietnamese adult (13 children). Events last 5/6 s minimum and 7 s maximum, with a 2-frame minimum gap and a 12-frame shot-change rule. BBC uses 160 to 180 wpm and a line width of 68% of a 16:9 frame.

### Cited Findings

**Colour pipeline and archive/CG matching**
- *Faulkner* documentary: the colourist chose ACES because interviews were shot over many years on many cameras, and ACES "unified all those different log flavours into a single curve and gamut". Cinegrain print-film-emulation LUTs built for ACEScct were the starting point for the look. — [British Cinematographer, "Remastering History… Faulkner"](https://britishcinematographer.co.uk/?p=86870)
- *Hatton* documentary (Baselight): two looks were decided early, one for the large volume of archive and one for interviews. Archive from different dates and sources was intercut, so it had to be homogenised. The colourist added diffusion in blacks and shadows (Texture Equaliser) to soften rather than sharpen, and deliberately degraded some archive. Crisp modern drone shots needed extra work to sit with the archive. A little grain was added for consistency, plus subtle Chroma Warp for a "video" feel. — [FilmLight case study, Hatton](https://www.filmlight.ltd.uk/customers/case-studies/hatton.php)
- Film-emulation tooling: fylm.ai InviziGrain uses high-quality film scans as references and offers ACES print-film emulations. Its colour match transfers colour only, without changing contrast or exposure. — [fylm.ai InviziGrain](https://fylm.ai/invizigrain/)
- Matching a reference grade in Resolve: grade in ACEScct and work mainly with offset and log controls. — [ACES Central forum](https://community.acescentral.com/t/reverse-engineering-a-grade-aces-or-no/901)

**Delivery specs: streaming (Netflix)**
- Netflix Delivery Specification v5.1: all deliveries must comply with SMPTE ST 2067-21:2016 or :2020 IMF Application #2E. Immersive audio must also meet the IAB plug-in. IMF packages go in the highest quality available, HD and UHD. A 16-bit uncompressed TIFF mezzanine is recommended for creating the HDR IMF. Which assets apply comes from the title's Delivery Requirements List. — [Netflix Delivery Specification v5.1](https://backlothelp.netflix.com/hc/en-us/articles/7262346654995) (search excerpt)
- IMF App 2E covers lossy and lossless JPEG 2000, 12/16-bit RGB, and Rec.709 or Rec.2020. — [Digital Production, "IMF and what it's all about" (2018)](https://digitalproduction.com/2018/02/20/imf-and-what-its-all-about/)
- Netflix Originals delivering in HDR must master in Dolby Vision, delivered as Dolby Vision IMF. Netflix derives Dolby Vision, HDR10 and SDR streams from that package. — [Netflix, Dolby Vision HDR Mastering Guidelines](https://backlothelp.netflix.com/hc/en-us/articles/360000599948-Dolby-Vision-HDR-Mastering-Guidelines) (search excerpt; page now redirects to a JS portal)
- Most branded content is delivered as IMF App #2E. — [HPA 2019, Lemieux slides](https://hpaonline.com/wp-content/uploads/2019/02/2019-02-14-1620-Lemieux-v2.pdf)

**Subtitles: Netflix (streaming)**
- English (USA): maximum 42 characters per line and 2 lines. Keep text on one line unless it exceeds the limit, and use a bottom-heavy pyramid with no one or two words alone on the top line. Reading speed up to 20 cps for adult and 17 cps for children's programmes. Use an ellipsis only for pauses of 2 s or more. Spell out zero to ten, numerals above. Documentary speaker titles are translated once, at first appearance. Repeated speaker IDs are numbered ("[man 1]"). Forced-narrative duration should follow the on-screen text. Archive news tickers need no subtitle unless plot-relevant. — [Netflix English (USA) Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide)
- Vietnamese: 42 characters per line, 2 lines, bottom-heavy pyramid. **Reading speed 17 cps adult and 13 cps children's; SDH 20 cps adult and 17 cps children's.** Use the single ellipsis character U+2026. Dual speakers take a hyphen and space, one speaker per line. Decimal comma ("2,5 triệu"), thousands period ("1.000 đồng"). Spell out 1 to 10, numerals from 11. Convert units to metric unless the original unit matters to the plot. Acronyms take no periods, and common Vietnamese abbreviations (HLV, BTC, THPT) are allowed for reading speed. Keep diacritics in proper nouns. Translate a documentary speaker's title only the first time, and omit the name if it matches on-screen text. Follow Vietnamese capitalisation, not English. Forced narratives are ALL CAPS (sentence case for long prologues), never combined with dialogue in one event, and dropped when redundant. SDH: lowercase bracketed IDs such as [nam] or [nữ]. Avoid covering on-screen text, faces and mouths; raise subtitles only consistently, as a group. — [Netflix Vietnamese Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/220447048-Vietnamese-Timed-Text-Style-Guide)
- General timing: minimum 5/6 s per event (20 frames at 24 fps), maximum 7 s, minimum gap 2 frames at any frame rate. — [Netflix Timed Text Style Guide: General Requirements](https://backlothelp.netflix.com/hc/en-us/articles/215758617); [Netflix Subtitle Timing Guidelines](https://backlothelp.netflix.com/hc/en-us/articles/360051554394-Timed-Text-Style-Guide-Subtitle-Timing-Guidelines) (search excerpts). The 5/6 s minimum is 25 frames at 29.97 fps. — [Netflix Supplementals TTSG](https://backlothelp.netflix.com/hc/en-us/articles/115000239632-Timed-Text-Style-Guide-Supplementals-Marketing-Assets)
- Shot-change rules, from 3Play Media's reproduction of Netflix's diagrams (Jan 2019). Avoid crossing cuts. Timecodes go on the shot change or at least 12 frames from it. A start 8 to 11 frames before a cut moves to 12 frames before. A start 7 or fewer frames before moves onto the cut. An end 8 to 11 frames after a cut extends to 12 frames after. An end 7 or fewer frames after moves to the cut, keeping the 2-frame gap. Events are timed to audio, within 3 frames. The out-time may extend up to 12 frames past the end of the audio for reading time. — [3Play Media, "How to meet Netflix captioning specs"](https://www.3playmedia.com/?p=15170)

**Subtitles: BBC (broadcast)**
- Reading speed 160 to 180 wpm (0.33 to 0.375 s per word). Maximum line width 68% of a 16:9 frame (90% for 4:3). Normally 2 lines, 3 only when no important picture is covered. Timing may vary for shot changes, lip-readable words, humour and similar cases. — [Clevercast summary of BBC Subtitle Guidelines](https://clevercast.com/bbc-subtitling-guidelines)
- Minimum on-screen time of about 0.3 s per word (for example 1.2 s for a 4-word subtitle). — [First News subtitling guidelines (BBC-based)](https://help.firstnews.co.uk/video/video-subtitling-guidelines/)

### Inferences
- Default colour pipeline for an archival + 3D/CG documentary: ingest everything to ACEScct, or a single scene-referred log space, for grading. Keep two named looks, `archive` and `new/CG`. Apply a "degrade-to-match" pass to CG and modern footage (grain, mild diffusion in shadows, slight chroma softening and gate weave if needed) rather than sharpening or "restoring" the archive past its native look. Output through a Rec.709 (SDR) or PQ/Dolby Vision (HDR) display transform.
- For the project's 30 fps timeline: subtitle minimum = 25 frames (5/6 s), maximum = 210 frames (7 s), gap ≥ 2 frames, shot-change snap zone = 12 frames (snap when ≤ 7 frames away, extend to 12 when 8 to 11). These are all automatable checks.
- Vietnamese captions must use 17 cps adult, not English's 20 cps. Diacritics make Vietnamese lines visually denser. Count characters on Unicode NFC-normalised text so combining diacritics do not inflate the count.
- For web delivery, where captions are often burned in, keep subtitles inside the 68%-of-width zone (BBC) and above the lower-third safe area.

### Gaps
- Netflix's Dolby Vision mastering specifics could not be read (portal redirect). From prior knowledge, not verified here: P3-D65 primaries in a Rec.2020 PQ container, a mastering display of at least 1,000 nits, and Dolby Vision CM v4.0 trims.
- No sourced Netflix rule on upscaling or treating SD archival footage within UHD/HDR deliveries was found. Netflix's archival/non-original asset sections defer to the title's Delivery Requirements List.
- No sourced numeric grain-matching method (grain size or intensity matched to a film stock) was found. Case studies are qualitative.
- The BBC Subtitle Guidelines primary page (bbc.github.io/subtitle-guidelines) returned 404 and bbc.co.uk was blocked, so BBC figures come from secondary summaries. The often-quoted "37 characters per line" (teletext) for BBC could not be confirmed.
- No Vietnamese broadcaster (VTV) subtitle or loudness spec was found.

---

## 4. Measurable QC metrics: PSE (Harding/Ofcom), legal levels, black and frozen frames, audio phase

### Takeaway
The core automatable broadcast QC checks are photosensitive epilepsy and legal levels. **PSE** (Ofcom/ITU-R BT.1702-3/WCAG): fail when there are more than 3 flashes (pairs of opposing luminance changes) in any 1 s, with each change ≥ 20 cd/m² where the darker state is below 160 cd/m², over more than 25% of the screen. Saturated-red flashing and regular stripe patterns (more than 5 light-dark pairs) are checked separately. **Legal levels** (EBU R103): RGB −5% to 105%, luma −1% to 103%, with a typical broadcaster allowance of about 1% of the active picture in error. Netflix QC centres on IMF/Photon validation and Dolby Vision, with Harding PSE for some regions (UK, Japan). No sourced numeric thresholds were found for black frames, freeze frames or phase.

### Cited Findings

**Photosensitive epilepsy (broadcast; also used by streaming QC)**
- Ofcom treats a sequence as a breach only when all three conditions hold: a brightness change above a defined level, more than three pairs of opposing changes in any second, and more than 25% of the screen changing in brightness. — [ASA ruling, Citroën UK Ltd A11-164759](https://www.asa.org.uk/rulings/citroen-uk-ltd-a11-164759.html)
- The "Harding test" maximum is three flashes per second. — [Pinsent Masons, BBC Olympics logo ruling](https://www.pinsentmasons.com/out-law/news/bbc-broke-epilepsy-rule-with-flashing-olympics-logo-rules-ofcom)
- General flash per ITU-R BT.1702: a luminance change of 20 cd/m² or more where the darker image is below 160 cd/m². This applies to SDR and HDR. For HDR where the darker state is 160 cd/m² or more, a general flash is a Michelson contrast of 1/17 or greater. Saturated red has its own test because people are more sensitive to red flashing. — [W3C WCAG 2.2 Understanding SC 2.3.1](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html) (search excerpt)
- The current ITU-R BT.1702 version is BT.1702-3 (11/2023), in force. — [ITU-R BT.1702](https://www.itu.int/rec/R-REC-BT.1702)
- Regular patterns (Ofcom Annex 1, via a secondary quote): a potentially harmful pattern has clearly discernible stripes when there are more than five light-dark pairs in any orientation. Stripes that change direction, oscillate, flash or reverse contrast are more likely to be harmful than stationary ones. — [hellocatfood, "Potentially Harmful"](https://hellocatfood.com/blog/potentially-harmful/)
- Advertisers should pass a Harding FPA test "or other suitably robust equivalent test", but automated test equipment does not guarantee compliance with the Ofcom Guidance. — [ASA, "Flashing images in advertising"](https://www.asa.org.uk/news/flashing-images-in-advertising.html); [ASA Citroën ruling](https://www.asa.org.uk/rulings/citroen-uk-ltd-a11-164759.html)
- All UK TV stations use PSE testing. Japan uses PSE testing, especially for anime, since the 1997 Pokémon incident. — [Wikipedia, "Harding test"](https://en.wikipedia.org/wiki/Harding_test)

**Legal levels / gamut (broadcast)**
- EBU R103: material is acceptable if, after conversion to RGB, every channel lies within −5% to 105% and luminance within −1% to 103%. Measurement filter rise time 300 to 350 ns. — [EBU R103 v1.1](https://tech.ebu.ch/docs/r/r103v1_1.pdf) (search excerpt)
- v2.0 (2016) added numeric ranges for 8, 10, 12 and 16-bit systems. v3.0 (2020) added HDR and explains that broadcast uses "narrow" (video) range, keeping headroom for under- and overshoots. — [EBU R103 publication page](https://tech.ebu.ch/publications/r103); [EBU news, May 2020](https://tech.ebu.ch/news/2020/05/ebu-publishes-adds-fresh-advice-on-video-signals-and-hdr)
- The EBU warns that colour-gamut "legalisers" can create artefacts more visible than the gamut errors they fix. — [EBU R103](https://tech.ebu.ch/publications/r103) (search excerpt)
- Broadcaster practice: Eurosport allows a small tolerance if no more than 1% of the active picture is in error. — [Eurosport International Pan-Euro broadcast specifications](https://helpcenter.xr.global/hc/en-us/articles/28400502428180-Eurosport-International-Pan-Euro-Broadcast-Specifications-and-Requirements)

**Netflix QC (streaming)**
- Netflix QC areas: IMF App 2E compliance (asset map, packing list, CPL); Dolby Vision compliance; the Photon IMF validator (a failed package is not sent to Netflix); Harding PSE screening, which may be required for some content, especially deliveries to the UK and Japan; and general audio/video baseband artefact checks. No numeric thresholds are given. — [Venera Technologies, "Delivering to Netflix? QC requirements in a nutshell" (31 Jan 2020)](https://www.veneratech.com/delivering-to-netflix-qc-requirements-in-a-nutshell-and-how-to-comply-with-them/)
- Loudness and true-peak flag thresholds: see Section 2 (print master −1 dBTP, −27 ±3 LKFS). — [Netflix, Original Language Mix for Streaming and Archive](https://backlothelp.netflix.com/hc/en-us/articles/115001539991)

### Inferences
- PSE check: compute per-frame mean luminance in cd/m², converting SDR as 100% white = 100 to 200 cd/m² display luminance (a calibration assumption). Count opposing transitions of ≥ 20 cd/m² (darker side < 160) inside a sliding 1 s window, restricted to regions covering > 25% of the screen. Fail at more than 3 flashes per second. Add a saturated-red channel check, and a stripe-pattern check (> 5 light-dark pairs) for maps and graphic overlays. Treat a pass as "screened", not "certified"; the ASA warns that automated tools are not proof.
- Legal-range check: decode to RGB, flag pixels outside −5% to 105% (RGB) or −1% to 103% (luma), and fail when they exceed about 1% of the active picture area. This is cheap to run on sampled frames. Avoid blanket hard-clip legalisers; per the EBU, soft-clip or grade instead.
- Black and frozen frame checks are standard (for example ffmpeg `blackdetect` and `freezedetect`) but no sourced thresholds were found. A conservative project default would flag unintended black longer than 1 frame mid-programme and freezes longer than about 2 s outside deliberate still holds. This is an inference, not a spec, and Ken Burns-style still moves must not be flagged as freezes.
- Audio phase or mono compatibility: no sourced threshold was found. A common practice is to flag sustained negative stereo correlation on dialogue or narration stems; an unsourced default would be to warn when correlation stays below 0 for more than 1 s.

### Gaps
- Ofcom's own Guidance Note (Section Two, Annex 1) was not retrieved. The exact "defined level" of brightness change and the red-flash definition are sourced here via ITU-R BT.1702 and W3C, not Ofcom's text. Ofcom revises its definition periodically.
- No primary-source thresholds were found for black frames, frozen frames, digital hits, dropouts, audio phase or clicks in a Netflix or DPP QC spec. The DPP Technical Specification (AS-11 UK DPP HD) and Netflix's "Video QC" or "Audio QC" partner pages would hold them but were not reachable.
- The exact 8/10-bit narrow-range code values from EBU R103 v2/v3 (for example 10-bit luma 64 to 940 nominal, with the permitted 4 to 1019 excursions) come from prior knowledge of BT.709/BT.2100 and were not verified against the R103 PDF, which returned 403.
