# Aesthetic judgement and artistry for an AI video-editing agent (measure, encode taste, critique-and-revise)

Scope note: research done 2026-10-27. Sources are 2023–2026 unless flagged "[older classic]". Several sources are 2026 arXiv preprints (not yet peer reviewed); they are flagged. Licences were checked against repository files where possible; "NC" = non-commercial only.

## 1. Learned aesthetic and quality predictors usable locally on an RTX 3060 12 GB

### Takeaway
The single best local option found is **Q-ReAlign** (Q-Future, 2026): one Qwen3.5-VL-based scorer for image quality, image aesthetics and video quality, in 0.8B / 4B / 9B sizes, **Apache-2.0**, available through pyiqa; the 0.8B model matches the older Q-Align (avg SRCC 0.879 vs 0.869) with ~2.2 GB of weights. DOVER is still the cleanest way to split a video score into "aesthetic" vs "technical", but it, Q-Align, CLIP-IQA and the pyiqa wrapper itself are **non-commercial** licences. Every predictor tops out around SRCC ≈ 0.8 on AVA aesthetics (vs ≈ 0.94 on technical quality), so aesthetic scores should be used as relative, genre-calibrated signals, never as absolute pass/fail gates.

### Cited Findings
**Q-Align / OneAlign (ICML 2024)**
- Q-Align teaches an LMM to output discrete text levels (excellent/good/fair/poor/bad) instead of numbers; one unified model "OneAlign" covers image quality (IQA), image aesthetics (IAA) and video quality (VQA) — [Q-Align paper](https://arxiv.org/html/2312.17090v1); [GitHub](https://github.com/Q-Future/Q-Align)
- AVA aesthetics: Q-Align SRCC 0.798 / PLCC 0.796 — [Q-ReAlign model card comparison table](https://huggingface.co/q-future/Q-ReAlign-Mini-0.8B); a leaderboard lists OneAlign at SRCC 0.823 on AVA (discrepancy unresolved; likely different model variant) — [Papers with Code](https://ml.paperswithcode.com/paper/q-align-teaching-lmms-for-visual-scoring-via)
- Licence: **S-Lab License 1.0 — non-commercial only; commercial use requires contacting the authors** — [Q-Align LICENSE](https://raw.githubusercontent.com/Q-Future/Q-Align/main/LICENSE)
- Fine-tuning: LoRA on OneAlign "only requires 2 RTX3090 GPUs"; full training needs 4×A6000 / 2×A100 or more; inference example is fp16 with `device_map="auto"`, no quantisation guidance — [GitHub](https://github.com/Q-Future/Q-Align)

**Q-ReAlign (2026, successor to Q-Align)**
- Same "rate with words, take probability-weighted level" method: probability on excellent/good/fair/poor/bad is weighted [1.0, 0.75, 0.5, 0.25, 0.0] into a 0–1 score — [pyiqa Q-ReAlign docs](https://iqa-pytorch.readthedocs.io/en/latest/autoapi/pyiqa/archs/qrealign_arch/index.html)
- Three checkpoints: Mini 0.8B, Lite 4B, Pro 9B; Pro reaches avg SRCC 0.896 vs Q-Align 0.869 — [pyiqa docs](https://iqa-pytorch.readthedocs.io/en/latest/autoapi/pyiqa/archs/qrealign_arch/index.html)
- Mini 0.8B per-dataset SRCC/PLCC (vs Q-Align): KonIQ 0.935/0.938 (0.942/0.944); SPAQ 0.931/0.933 (0.932/0.933); KADID 0.903/0.907; AGI (AI-generated images) 0.811/0.848 (0.738/0.781); AVA aesthetics 0.797/0.794 (0.798/0.796); LSVQ video 0.869/0.869 (0.867/0.866); average 0.879/0.880 (0.869/0.873) — [HF model card](https://huggingface.co/q-future/Q-ReAlign-Mini-0.8B)
- **Licence Apache-2.0**; weights ≈ 2.2 GB bf16 safetensors; video handled by sampling 8 frames as an image sequence; throughput 26.7 img/s at batch 4 on an RTX 4090; needs transformers ≥ 5.0 — [HF model card](https://huggingface.co/q-future/Q-ReAlign-Mini-0.8B)
- Added to pyiqa June 2026 as `qrealign` (three sizes) — [IQA-PyTorch README](https://github.com/chaofengc/IQA-PyTorch)

**DOVER / DOVER-Mobile (ICCV 2023) — aesthetic vs technical video quality**
- Treats user-generated-video quality as two perspectives: technical (distortion perception) and aesthetic (content preference); built DIVIDE-3k dataset showing human judgements are shaped by both — [ICCV 2023 paper](https://openaccess.thecvf.com/content/ICCV2023/html/Wu_Exploring_Video_Quality_Assessment_on_User_Generated_Contents_from_Aesthetic_ICCV_2023_paper.html)
- Outputs are **relative**: per-perspective percentile rank and a score normalised to N(0,1) against several UGC datasets; README states absolute scores are not meaningful across datasets; fused score in [0,1] "converted via ITU standards" (formula not given) — [DOVER GitHub](https://github.com/vqassessment/DOVER)
- PLCC: DOVER KoNViD-1k 0.883, LIVE-VQC 0.854, LSVQ_test 0.889, LSVQ_1080p 0.830; DOVER-Mobile 0.853 / 0.835 / 0.867 / 0.802 — [DOVER GitHub](https://github.com/vqassessment/DOVER)
- Cost: DOVER ≈ 3.6 s/video on CPU, DOVER-Mobile ≈ 1.4 s; DOVER-Mobile 9.86M params, < 1.9 GB GPU memory — [DOVER GitHub](https://github.com/vqassessment/DOVER)
- **Licence S-Lab 1.0: non-commercial only** — [DOVER S-Lab-LICENSE](https://raw.githubusercontent.com/vqassessment/DOVER/master/S-Lab-LICENSE)
- Reproducibility caveat: a third-party Replicate wrapper reports it could not replicate the repo's precise scores despite copying the implementation and fixing seeds — [Replicate README](https://replicate.com/turian/dover-video-quality-assessment/readme)

**LAION aesthetic predictor (v2 and v2.5)**
- v2.5 is SigLIP-based, scores 1–10, README says **5.5+ is "a great aesthetic score"** (so older v2 thresholds don't transfer); improved for wider domains incl. illustrations; training data not described; **licence AGPL-3.0** — [aesthetic-predictor-v2-5](https://github.com/discus0434/aesthetic-predictor-v2-5)
- The original LAION-Aesthetics Predictor is an MLP on CLIP embeddings trained on three sets (AVA, SAC, LAION-Logos) with architecture/data mix chosen by its author's taste; a Jan 2026 audit found it disproportionately keeps images whose captions mention women and filters out those mentioning men or LGBTQ+ people (2026 preprint) — [Algorithmic Gaze audit](https://arxiv.org/pdf/2601.09896)
- VBench's "Aesthetic Quality" dimension = LAION linear predictor on CLIP ViT-L/14 per frame, averaged; "Imaging Quality" = MUSIQ (SPAQ-trained) for blur/noise/exposure (secondhand descriptions; normalisation differs across papers) — [ForgeWM paper describing VBench metrics](https://arxiv.org/pdf/2608.14022); [VBench overview](https://www.emergentmind.com/topics/vbench)

**CLIP-IQA, MUSIQ, NIMA via pyiqa**
- CLIP-IQA assesses "look and feel" (quality and abstract perception) with antonym prompt pairs; **NTU S-Lab License 1.0** — [CLIP-IQA GitHub](https://github.com/IceClear/CLIP-IQA)
- pyiqa (IQA-PyTorch) bundles NIMA (incl. AVA-trained), MUSIQ, TOPIQ, DBCNN, BRISQUE, NIQE, QualiCLIP, Q-Align/Q-ReAlign etc.; each metric exposes `lower_better`; README states **PolyForm Noncommercial 1.0.0 plus S-Lab for some components** (a conflicting "MIT" label appears in file navigation); datasets are "for academic, research, and educational purposes only" — [IQA-PyTorch](https://github.com/chaofengc/IQA-PyTorch)

**Video reward models (human-preference, built for generated video)**
- VideoReward/VideoAlign: trained on ~182k human-annotated pairs from 12 T2V models across visual quality, motion quality, text alignment (Bradley-Terry with ties) — [Improving Video Generation with Human Feedback](https://arxiv.org/html/2501.13918v2)
- VideoScore2 is a generative evaluator for visual quality, text alignment and physical/common-sense consistency; a 2026 benchmark maps VideoReward's motion score to consistency/action/rhythm — [RewardVerse (2026 preprint)](https://arxiv.org/pdf/2609.22947)

**MLLM aesthetic perception vs experts**
- AesBench (2,800 images, 8,400 QA pairs, 2,800 expert interpretations) found "a significant gap between MLLMs and humans in image aesthetics perception" (2024) — [AesBench](https://arxiv.org/abs/2401.08276v1)

### Inferences
- Ceiling: all models cluster at SRCC ≈ 0.80 on AVA aesthetics but ≈ 0.93–0.94 on KonIQ/SPAQ technical quality (same table). Technical-quality scores can gate (blur, noise, exposure); aesthetic scores should only rank alternatives or flag outliers.
- RTX 3060 fit (estimate from weight sizes, not measured): Q-ReAlign Mini (2.2 GB bf16) and DOVER-Mobile (< 1.9 GB) fit with room to spare and can run alongside rendering; Lite 4B should fit in bf16 (~8 GB); Pro 9B (~18 GB bf16) needs 4-bit quantisation, untested. A 3060 is slower than a 4090, so expect well under the 26.7 img/s reported.
- Commercial-safe stack: Q-ReAlign (Apache-2.0) as the main scorer; LAION v2.5 (AGPL — fine for internal use, but obligations if served over a network); DOVER/Q-Align/CLIP-IQA/pyiqa are NC. If the owner monetises output, call Q-ReAlign directly from HF/transformers rather than through pyiqa, or get a licence opinion.
- Failure cases to expect: (a) Archive grain/B&W. Every model here was trained on consumer photos (KonIQ, SPAQ), photo-contest images (AVA) or UGC video (LSVQ), so grain and B&W will probably read as "noise" or "low quality". Use within-genre percentiles against a reference set of acclaimed archival documentaries (the same idea as DOVER's percentile output), and score the treatment (framing, motion, typography) rather than source fidelity. (b) Text-heavy frames: LAION-Logos is part of LAION predictor training, and LVLM judges inflate scores for text overlays (see section 4), so explainer and short-form frames full of text need text-specific checks, not a generic aesthetic score.
- Video vs frame: Q-ReAlign's VQA mode samples only 8 frames, so it cannot see cut rhythm or motion design. Pacing has to be measured separately (section 3).

### Gaps
- No published evaluation was found of any of these models on archival or grainy B&W footage, or on text-heavy graphic frames. Measuring this on the owner's own references is necessary.
- Q-ReAlign Lite/Pro per-dataset numbers, real VRAM use, and the base Qwen3.5 licence terms were not confirmed.
- MUSIQ and NIMA official weight licences were not checked (pyiqa hosts its own weights).
- The licence of the original LAION v2 predictor ("improved-aesthetic-predictor") and of VideoReward weights was not verified.
- No source gave correlation of these predictors with professional editors' judgements on edited, finished videos (all benchmarks are UGC or photo datasets).

## 2. Composition, colour and typography craft as checkable rules

### Takeaway
Some craft rules are reliably measurable from pixels: subject isolation/clarity, sharpness, exposure, text reading speed and size, safe zones, and contrast. Others, the rule of thirds above all, correlate only weakly with how good people judge an image to be and should be soft hints, not gates. The strongest classic evidence (subject-focused features separating professional from amateur shots) points to measuring subject clarity and background simplicity rather than grid placement.

### Cited Findings
- [older classic, 2008] Luo & Tang: professional vs amateur photos differ in "clear topic, attention on subject, removal of distractions"; they extract the subject region via blur detection and compute subject-clarity, lighting, composition and colour features; 93% classification vs 72% for the previous best, and >95% precision at reasonable recall for both photo and video — [ECCV 2008 entry](https://mlanthology.org/eccv/2008/luo2008eccv-photo/); [CUHK project page](https://mmlab.ie.cuhk.edu.hk/project_photo_quality.html)
- [older, 2014] Rule of thirds: aesthetic ratings correlated only weakly with subjective rule-of-thirds scores and **not at all with computed rule-of-thirds values**; highly rated photos and paintings scored about as low on computed RoT as photos ignoring the rule; authors conclude RoT "plays only a minor, if any, role" in high-quality images — [Amirshahi et al., Art & Perception 2014](https://uniklinikum-jena.de/anatomie1_media/Inhalte/AmirshahiARTP2014-font-1.pdf)
- Reading speed caps (Netflix Timed Text Style Guides): adult 17 characters/s (Slovak, Indonesian), 12 cps Korean, 9 cps Chinese, 22 cps Telugu; children's ~13 cps for Latin-script languages — [Slovak TTSG](https://backlothelp.netflix.com/hc/en-us/articles/115002812588-Slovak-Timed-Text-Style-Guide); [Korean TTSG](https://backlothelp.netflix.com/hc/en-us/articles/216001127); [Simplified Chinese TTSG](https://backlothelp.netflix.com/hc/en-us/articles/215986007-Chinese-Simplified-Timed-Text-Style-Guide); a forum post cites 20 cps for English adult programmes (secondhand) — [RWS community](https://community.rws.com/product-groups/trados-portfolio/trados-studio/f/subtitling/33163/subtitling-qa-settings-for-german/109304)
- TikTok official ad guidance (updated June 2025): "We recommend displaying 5-10 words per second when using text"; keep content in the UI safe zone per ad specs; 9:16, ≥720p — [TikTok creative best practices](https://ads.tiktok.com/help/article/creative-best-practices?lang=en). This conflicts with subtitle reading-speed norms (17–20 cps ≈ 3–4 English words/s, by inference), so it probably refers to short punchy overlays rather than sentences.
- Safe zone in practice: third-party vertical-ad guides recommend keeping key text/visuals in the centre ~80% and clear of the right-side icon column (like/comment/share/follow) and the bottom username/caption bar. This is a community recommendation, not official numbers, and the exact guide behind the 80% figure was not pinned down — e.g. [Tiger Pistol vertical ad best practices](https://tigerpistol.com/vertical-video-ad-best-practices/); [Stackmatix TikTok production tips](https://www.stackmatix.com/blog/tiktok-video-ad-production-tips)

### Inferences
- Pixel-checkable rules worth implementing (cheap, deterministic):
  - subject sharpness vs background sharpness ratio (Luo & Tang idea; use a segmentation/saliency mask from tools the system already has);
  - exposure clipping percentage and luminance histogram spread;
  - text contrast ratio against the local background behind each glyph box. WCAG 2.x thresholds (4.5:1 body, 3:1 large text) are the standard reference, not re-verified in this session;
  - characters per second per caption block against a per-language cap;
  - minimum text x-height as a fraction of frame height;
  - safe-zone overlap for 9:16;
  - number of simultaneous text blocks and type sizes per frame (hierarchy: at most 2–3 levels).
- Rule of thirds should be a soft "subject not dead-centre unless symmetric/intentional" hint, not a score; the evidence does not support it as a quality predictor.
- Colour harmony: no recent evidence was retrieved. A practical approach is to measure the palette of each reference board (dominant hues, saturation, contrast, skin-tone vector) and score drift from that genre target, rather than applying abstract harmony templates.

### Gaps
- No 2023–2026 study was found validating computational colour-harmony scores (e.g., hue-template methods) against expert ratings for video grading. Genre-specific grading targets would need to be measured from reference films.
- No research source on kinetic-typography timing (hold durations per word, in/out durations) was found beyond reading-speed caps and UI motion tokens.
- Netflix's Vietnamese (and English) Timed Text Style Guide cps values were not retrieved. Get them before setting the per-language cap.
- Visual-weight/negative-space metrics: no validated metric found.

## 3. Motion design principles and edit-rhythm craft (pacing, shot-length data)

### Takeaway
Shot lengths are strongly right-skewed (roughly log-normal), have shortened from about 10 s (1930s–40s) to under 4 s (post-2000) in English-language features, and shorter shots carry more motion, most strongly in action. These facts give the system measurable pacing targets: median and log-spread of shot length, plus a motion-vs-length relationship, set per genre. Murch's ordered priorities (emotion > story > rhythm > eye-trace > 2D plane > 3D space) are the standard craft hierarchy for choosing a cut. UI-motion tokens give defensible defaults for easing and duration.

### Cited Findings
- Cutting et al. (2011, i-Perception; 160 English-language films 1935–2010): ASL "about 10 s in the 1930s and 1940s", "below 4 s after 2000"; extremes *The Seven Year Itch* (1955) 26.2 s and *Rocky IV* (1985) 2.2 s; shot durations are "strongly skewed" and log-transforming gives roughly normal distributions; across films shot length vs within-shot motion r = −.46 (only in later films; independent in 1935–1960); by genre strongest in action (r = −.54), comedy (−.49), adventure (−.40), weak in drama (−.24) and animation (−.03); decline reliable in all five genres [older, 2011] — [Cutting et al. 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3485803/)
- Cinemetrics-derived genre figures (films 1997–2016, 1,037 submitters): average shots per film 1,045; action 1,913 shots and ASL 4 s; adventure 5.1 s; sci-fi 6.2 s; horror reported at 15.7 s (surprisingly long; treat with caution); documentaries have the fewest shots (491 per film) — [Stephen Follows](https://stephenfollows.com/many-shots-average-movie/)
- Cinemetrics records each cut and reports min, max, median, SD of shot length, not only the mean — [Film Comment on Cinemetrics](https://www.filmcomment.com/article/site-specifics-cinemetrics.lv?print)
- Music videos: a case study of "I Took a Pill in Ibiza" found mostly close shots averaging ~2 s, with shot length scaling with shot size (single video) — [Pérez Rufí & Rodríguez-López 2017](https://ariasmontano.uhu.es/entities/publication/7b058a26-32fb-4329-b388-8a0822f99aa8); a 40-video study found performative vs concept videos each associated with a characteristic ASL (figures not retrieved) — [Revista Latina study](https://nuevaepoca.revistalatinacs.org/index.php/revista/article/download/807/1228/3965)
- Historical documentary: Ken Burns describes stills as "the building block" of his narrative construction — [MasterClass](https://www.masterclass.com/classes/ken-burns-teaches-documentary-filmmaking/chapters/visual-storytelling-cinematic-techniques)
- Murch's Rule of Six [older classic, 1995/2001]: emotion 51%, story 23%, rhythm 10%, eye-trace 7%, 2D screen plane 5%, 3D space 4%; summaries stress the order matters more than the exact percentages — [No Film School](https://nofilmschool.com/2016/11/6-rules-good-cutting-according-oscar-winning-editor-walter-murch); [Filmdaft 2025](https://filmdaft.com/walter-murchs-rule-of-six-the-editors-formula-for-choosing-the-right-cut/)
- Motion tokens (Material 3, via Flutter mirror): emphasized 500 ms, emphasized-decelerate 400 ms for elements entering, emphasized-accelerate 200 ms for exiting, standard 300 ms, standard-decelerate 250 ms; duration tokens 50–1000 ms — [Flutter/M3 token mirror](https://design.kpay-group.com/docs/motion/type/flutter-type/flutter-intro); Material's own customisation page uses emphasized easing at 650 ms for a long transition (beta guidance) — [material.io](https://material.io/design/motion/customization.html)
- Older Material guidance: tablet durations ~30% longer than mobile, wearables ~30% shorter, desktop 150–200 ms; dismiss/close transitions shorter than open — [Material 1 duration & easing](https://m1.material.io/motion/duration-easing.html)

### Inferences
- Pacing metrics to compute from the edit decision list: median shot length, log-SD of shot length, the pacing curve (rolling median over time), and the correlation between optical-flow magnitude and shot length. Use the median, not the mean: the distributions are log-normal-like (Cutting), so the mean is dominated by a few long shots.
- Starting genre targets (to refine against the owner's reference boards): feature action ≈ 4 s ASL; music video ≈ 2 s; documentaries markedly slower (fewest shots per film), with archival stills held longer; horror slow. Short-form vertical and ads probably sit closer to music video, but no measured dataset was found (gap).
- "Shorter shot ⇒ more motion" is a checkable craft rule: flag short shots with little motion (choppy without energy) and long shots with heavy camera motion in fast-genre edits.
- UI motion tokens are for interface elements. For video titles and lower-thirds, use them as defaults: decelerate on enter, accelerate on exit, exits shorter than entries, no linear easing. Scale up for 4K/large-screen viewing, by analogy with the "tablet +30%" rule.
- Murch's ordering suggests the judge prompt should rank cut candidates on emotion and story before rhythm and continuity. Pixel checks can only cover the bottom three (eye-trace position continuity across the cut, screen-direction/180° consistency, spatial continuity).

### Gaps
- No measured shot-length data was found for TikTok/Reels/Shorts, product ads, travel films, or explainers specifically. A Cinemetrics-style measurement of 20–50 reference videos per genre with the system's own shot detector would fill this.
- No published Ken Burns/archival-documentary ASL figures were found.
- No source quantified Disney-style principles (anticipation, overlap, follow-through) for motion graphics; only UI easing tokens were found.
- Bordwell's "intensified continuity" figures and Barry Salt's long-run data appeared only in secondhand coverage and are not cited here.

## 4. How to give an AI "taste": style bibles, reference boards, pairwise judging, VLM-as-judge reliability, critique logs

### Takeaway
Evidence favours **pairwise and anchored comparison over absolute scoring**. VLM judges rank reasonably but their absolute scores are too uncertain to trust. Pairwise judging carries position bias, so swap order and require agreement. LVLM judges are systematically fooled by surface edits (text overlays, bounding boxes, padding, brightness), which matters for an editor that adds titles. The most transferable recipe is EditDuet's: a GPT-4o pairwise judge comparing two timelines as keyframe grids plus durations agreed with majority human preference 80.6% of the time, slightly above human–human agreement (78.7%). "Taste" is then encoded as reference anchors per genre (Compare2Score-style), measured targets, and rubric dimensions, not as a single aesthetic number.

### Cited Findings
- VLM judges "can rank but cannot score" (2026 preprint): conformal intervals on score-token log-probs cover ~40% of the score range for aesthetics/natural images and ~70% for chart/math reasoning; example ChartQA Pearson 0.507 yet interval width 3.08 on a 5-point scale; multi-annotator-averaged labels give 4.5× tighter intervals than single-annotator labels; recommendation: trust absolute scores only when interval width < ~1.0, fall back to pairwise/relative ranking when > ~3.0; judges included LLaVA-Critic and Gemini 2.5 Flash — [VLM Judges Can Rank but Cannot Score](https://www.alphaxiv.org/abs/2604.25235)
- Visual biases (FRAME benchmark, EMNLP 2025): nine LVLM judges (GPT-4.1, GPT-4.1-mini, GPT-4o, GPT-4o-mini, o3, LLaVA-1.5-13B, LLaVA-NeXT-8B, LLaVA-OneVision-7B, Qwen2.5-VL-32B) all inflated scores for manipulated images; instruction-text overlay had "the most pronounced impact" (LLaVA-1.5-13B +109.6% on animals; GPT-4o +44.1% indoor); bounding boxes raised GPT-4o scores up to +80.2%; black padding +17.1% (GPT-4.1-mini); brightness/gamma mostly < 12%; attack success 64.7% (GPT-4o-mini), 67.7% (GPT-4o); bias-aware prompts and chain-of-thought reduced but did not remove the effects; **pairwise evaluation was similarly fooled**; stacked biases compound (+17.1% → +23.3% with three) — [Fooling the LVLM Judges](https://arxiv.org/html/2505.15249v2)
- Position bias: a 2026 benchmark measured 23.3% position bias in pairwise VLM judging and needed swap-augmented re-runs; pointwise scoring showed scale drift across sessions and middle-of-scale compression (2026 preprint, single benchmark) — [Looks Right, Works Right](https://arxiv.org/pdf/2607.28645)
- VLM judges can favour "informative-sounding" answers without actually looking at the image; enforcing image attention mitigates it (2026 preprint) — [Informativeness bias](https://arxiv.org/pdf/2604.17768)
- Anchored comparison: Compare2Score (NeurIPS 2024) trains an LMM to compare, then scores a test image by its likelihood of being preferred over several fixed anchor images, converting a probability matrix to a score by MAP estimation; beats prior IQA models on nine datasets, and the conversion also helps zero-shot general LMMs — [Compare2Score](https://arxiv.org/html/2405.19298v1)
- EditDuet (Adobe, SIGGRAPH 2025): Editor and Critic agents (Llama-3.1-8B) edit B-roll; the GPT-4o pairwise judge sees **keyframe grids plus durations** of two timelines; judge–majority-human agreement 80.6% vs human–human 78.7% (PABAK 0.61 vs 0.57); professional human cuts were still preferred over EditDuet 75.1% of the time under that judge — [EditDuet](https://arxiv.org/html/2509.10761v1)
- Preference datasets as taste: VideoReward's 182k pairwise labels split into visual quality, motion quality and text alignment, i.e. taste decomposed into dimensions — [VideoReward](https://arxiv.org/html/2501.13918v2)
- Platform taste can invert "polish": TikTok recommends a "DIY or not overly polished style" so ads blend with user content, plus creators/employees/customers on camera — [TikTok creative best practices](https://ads.tiktok.com/help/article/creative-best-practices?lang=en)

### Inferences
- A workable "taste stack" for the agent:
  1. **Style bible per genre**: rules plus measured targets (median shot length, motion–length slope, palette, contrast, type scale, cps cap, transition vocabulary allowed/banned).
  2. **Reference board per genre**: 10–30 owner-approved frames/clips used as Compare2Score-style anchors. A candidate is judged "would this sit comfortably next to the anchors?", never scored in isolation.
  3. **Pairwise judge** for A/B choices (two cuts, two grades, two title treatments): show keyframe grid + durations (EditDuet recipe), run both orders, accept only order-consistent verdicts, treat disagreement as a tie.
  4. **Rubric dimensions** scored separately (story/emotion, rhythm, composition, colour, typography, technical), following the Murch order and VideoReward's decomposition.
- Because text overlays and boxes inflate LVLM judgements, the judge should see the **clean plate and the composited frame separately**, or text-bearing frames should be judged only on typography-specific rubric items. Debug overlays (bounding boxes, guides) must never be in frames sent to a judge.
- Absolute 1–10 VLM scores are not reliable enough to drive stop/accept decisions. Use them only as coarse triage, and only on dimensions with narrow uncertainty (aesthetics was among the narrower ones).
- Critique logs → rules: each owner critique should be stored as (frame/clip, dimension, verdict, reason). Recurring reasons become deterministic checks (e.g., "text too fast" → cps cap) or new anchors on the reference board. This mirrors how preference datasets were built (pairwise, per-dimension), but at the owner's scale.

### Gaps
- No study was found that measured whether a style bible plus reference board improves an editing agent's output versus a generic prompt; the recommendation is inferred from the anchor (Compare2Score) and pairwise-judge (EditDuet) evidence.
- Few-shot personal-taste adaptation from a small critique log (tens of examples) for video was not researched in depth.
- No data on position bias specifically for video-frame grids.

## 5. Genre specifics: what reads as high-end vs cheap

### Takeaway
Hard evidence here is thin. Craft sources agree that "cheap" mostly comes from **default, stacked, unmotivated effects** (preset transitions, repeated speed ramps), while "premium" comes from controlled light, a deliberate grade and restraint. Short-form is the exception: the platform itself recommends a less polished, native style, a strong early hook and readable overlays. Genre targets should therefore be learned from the owner's reference boards and measured, rather than taken from published rules.

### Cited Findings
- Travel/transition craft: Insta360 says reaching for a flashy preset "usually backfires", that "a well-timed whip pan or a clean match cut will almost always read as more cinematic than a timeline full of stock effects", and that the secret to speed-ramp transitions "is moderation" — [Insta360 film transitions guide](https://www.insta360.com/blog/tips/how-to-create-film-transitions.html)
- Short-form (TikTok official, June 2025): hook within the first 6 s; introduce the core proposition in the first 3 s; 9:16, ≥720p, sound on; use captions/text overlays (5–10 words/s); use transitions, stickers, graphics to retain engagement; "DIY or not overly polished" style; test 3–5 very different creatives per ad group — [TikTok creative best practices](https://ads.tiktok.com/help/article/creative-best-practices?lang=en)
- Product/commercial grading is a specialist pass: example premium spot shot on ARRI Alexa and graded in Baselight (condensed screen capture of the session) — [L'Oréal Garnier grading breakdown (2014)](https://www.photographybay.com/2014/10/27/video-grading-breakdown-of-loreal-garnier-commercial/); collection of professional before/after grading breakdowns — [Jonny Elwyn](https://jonnyelwyn.co.uk/film-and-video-editing/cool-videos-films-projects-creative-work/professional-colour-grading-breakdowns/)
- Music video pacing: ~2 s average shots dominated by close shots (single case study) — [Pérez Rufí & Rodríguez-López 2017](https://ariasmontano.uhu.es/entities/publication/7b058a26-32fb-4329-b388-8a0822f99aa8)
- Historical documentary: built around stills (Burns) and has the fewest shots per film of any genre — [MasterClass](https://www.masterclass.com/classes/ken-burns-teaches-documentary-filmmaking/chapters/visual-storytelling-cinematic-techniques); [Stephen Follows](https://stephenfollows.com/many-shots-average-movie/)
- Subject clarity/isolation and lighting separation distinguish professional from amateur shots [older classic] — [Luo & Tang ECCV 2008](https://mlanthology.org/eccv/2008/luo2008eccv-photo/)

### Inferences
- Checkable "cheapness" signals:
  - **effect density**: transitions of the same type per minute, the share of cuts that are non-hard cuts, and speed ramps per minute;
  - **repetition**: the same transition or preset used back-to-back;
  - **unmotivated effects**: a whip or ramp not aligned with camera motion or a music beat (checkable with optical flow and beat times);
  - **template feel**: identical title layout and timing every time;
  - **stock look**: low subject isolation, flat midday light (low local contrast and no subject–background separation), generic palette far from the genre board.
- Genre style bibles, starting points to verify against references:
  - **historical documentary**: long holds on stills with slow, motivated moves; restrained typography; a period-appropriate grade; archive grain kept, not "cleaned" by quality scorers;
  - **travel**: motion-matched transitions used sparingly, with golden-hour/subject separation weighted in the rubric;
  - **music video**: ~2 s median shots and cuts on beat;
  - **product/ad**: subject isolation, controlled specular highlights, minimal transitions, clean grade;
  - **explainer**: typographic hierarchy and reading-speed caps dominate;
  - **short-form**: hook in ≤ 3–6 s, native look, overlays inside safe zones.
- For short-form, an aesthetic predictor trained on photo-contest images (AVA) may penalise exactly the native look TikTok recommends, so its weight in the short-form rubric should be low.

### Gaps
- No systematic study (academic or industry) was found that defines what makes product ads, travel films or music videos look "premium" vs "cheap"; colourist breakdowns exist but are case demonstrations, not measured criteria.
- No measured data on speed-ramp or transition frequency in award-winning vs amateur travel/MV edits.
- YouTube Shorts and Instagram Reels official creator guidance was not retrieved (only TikTok's).

## 6. Do automated critique-and-revise loops raise quality, how many iterations, and at what cost?

### Takeaway
Loops help when the critic has **external, grounded feedback**: rendered output, measurements, tool results, comparison to references. Without it, models often fail to self-correct and can get worse. Published loops that work use 3–5 rounds (Idea2Img T=3; a 2026 video-generation loop used 5). Gains are largest with stronger generators and first appear from going from 1 to several rounds. No source measured per-round diminishing returns precisely, so a cap of about 3 rounds with an order-consistent pairwise "did it get better?" stop rule is the defensible default.

### Cited Findings
- Huang et al. (ICLR 2024): with only intrinsic self-correction (no external feedback), "performance after self-correction even deteriorates in most instances"; earlier positive results relied on oracle labels; external feedback (e.g., code execution results) does help — [LLMs Cannot Self-Correct Reasoning Yet](https://arxiv.org/html/2310.01798v1)
- Self-Refine (NeurIPS 2023): ~20% absolute average improvement across seven tasks over one-step generation — [Self-Refine](https://arxiv.org/abs/2303.17651)
- Idea2Img (ECCV 2024): GPT-4V loop with max 3 iterations; user preference vs manual prompts rose from 8.6–14.4% to 46.2–56.7%; gain of 3 rounds over 1 round: SDXL +26.9 points, IF +16.3, SDXL-img2img +16.3, IF-img2img +14.4, SD 2.1 +5.8, SD 1.5 +4.8, so stronger generators gained more; no T=2 or T>3 data — [Idea2Img](https://ar5iv.labs.arxiv.org/html/2310.08541)
- EditDuet: adding a Critic agent plus exploration cut failure rate from 19.5% (Editor–Critic without exploration) to 8.2%, with 89.8% time coverage; inference cost ~2.6 min on 8×H100 per B-roll sequence; exploration ~82 min one-time; residual failures were hallucinated function calls and unsupported feedback; they did not use a VLM critic because of context length — [EditDuet](https://arxiv.org/html/2509.10761v1)
- A 2026 creator-driven video-generation system refines over five iterations using movie-critic and audience-persona agents (2026 preprint; details not verified) — [Creator-Driven Recurrent Video Generation](https://arxiv.org/pdf/2606.18591)
- Paid-judge cost (Gemini): `media_resolution` caps tokens per media item; audio has a fixed per-second rate — [Gemini media resolution docs](https://ai.google.dev/gemini-api/docs/media-resolution); docs give ~263 tokens/s for video and 32 for audio — [Gemini token docs](https://ai.google.dev/gemini-api/docs/tokens); third-party breakdowns: ~258 tokens/frame at default resolution vs ~66 at low, i.e. ~300 vs ~100 tokens/s with audio — [Fora Soft 2026](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/video-vlms-frame-sampling-token-streaming-2026); ~353k tokens/hour at low vs ~1.04M at default (Gemini 2.5 Flash) — [Mixpeek](https://mixpeek.com/guides/how-many-tokens-is-an-hour-of-video); a third-party article cites $0.75 per million input tokens (introductory Flash rate), ≈ $0.36 per hour of low-res video (unverified pricing) — [HowAIWorks](https://howaiworks.ai/blog/google-gemini-agentic-video-2026); release notes describe an "agentic video" mode that loads only needed frames/transcript, reporting up to 88% fewer input tokens (best case) — [Gemini docs release mirror](https://techdevnotes.com/releases/gemini-docs/20260901-180346Z-4a33992aa23f)

### Inferences
- Design rule: every critique round must cite evidence the critic did not generate, for example:
  - the rendered frames/grid;
  - measured metrics (shot-length median vs target, cps violations, safe-zone hits, Q-ReAlign/DOVER deltas);
  - a pairwise result against the previous version and against references.
  "Make it more cinematic" without evidence is the intrinsic self-correction that Huang et al. found unreliable.
- Iteration budget: default max 3 rounds per scope (shot, sequence, whole video). Stop early when the swap-consistent pairwise judge prefers the new version less than ~60% of the time, or when no rubric dimension improved. Escalate to the owner rather than run round 4+. This follows Idea2Img's T=3 and the absence of evidence for more.
- Cost per round, local (estimate): deterministic checks are milliseconds per frame; DOVER-Mobile ≈ 1–4 s per clip; Q-ReAlign Mini on 8–16 sampled frames is seconds on a 3060. Local scoring is effectively free, so run it every round.
- Cost per round, paid VLM judge (estimate): a 60 s cut sent as a keyframe grid (one image) costs on the order of hundreds to a few thousand tokens; as low-res video, ~6k tokens (100 tokens/s × 60 s). Both orders for position-bias control double it. Even at full video resolution, a few rounds on a short cut cost cents, by these third-party figures. The real cost is latency and judge error, not money.
- Where the loop pays most: choices among discrete alternatives (which shot, which grade, which title layout) via pairwise comparison. Open-ended "improve this" requests pay least.

### Gaps
- No source gave per-iteration curves (round 1 → 2 → 3 → 4) for editing or video generation; Self-Refine's iteration-level results were not retrieved (only the abstract).
- No study compared local small scorers vs paid frontier VLM judges for edited-video quality on the same human labels.
- Exact current Gemini/Claude/GPT pricing for video and image input was not verified from official price pages (third-party figures only); model names and the "agentic video" mode come from a docs mirror.
- No evidence on whether owner-in-the-loop critique (rather than an AI judge) at round 1 vs round 3 gives better final quality per minute of owner time.
