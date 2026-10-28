# Token economy for a Claude-driven video-editing MCP server (~137 tools)

Scope: how to cut tokens and latency for Claude (via MCP, Python FastMCP, local machine) editing and reviewing video, without starving the model of what it must see or hear. Sources fetched 2026-10-27. Docs pages carry no publish date; they are cited as "fetched 2026-10-27". Engineering posts carry their own dates.

Local context, taken from the session's tool list and memory rather than from the web: the EditVideo server already exposes only a router surface to Claude (`editvideo_bootstrap`, `editvideo_discover_tools`, `editvideo_execute_tool`, `editvideo_get_job`, `editvideo_get_media_task`, `editvideo_observe_media`, `editvideo_read_design_preview`), and the current model is Claude Opus 5.5. Opus 5.5 is on the high-resolution image tier, so the image numbers below use that tier unless stated otherwise.

## 1. How Claude counts image tokens, and the cheapest way to show video evidence

### Takeaway
On current Claude models an image costs `ceil(w/28) x ceil(h/28)` tokens. On Claude 4.7 and later, including Opus 5.5, the cap is 2,576 px on the long edge and 4,784 tokens, so a full-HD frame costs 2,691 tokens, about 1.7x the old 1,560 cap. Cost depends only on pixel area: a contact sheet costs the same per pixel as separate frames. What saves tokens is fewer, smaller and better-chosen pixels. The video-LLM literature shows that about 6 to 8 well-chosen frames answer most questions about a whole clip, that frame choice matters more than resolution, and that halving resolution costs under half a point of accuracy.

### Cited Findings
- **Formula.** Claude splits an image into 28x28-pixel patches, and each patch is one visual token, so cost = `ceil(width/28) x ceil(height/28)` — [Anthropic Vision docs, fetched 2026-10-27](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Two resolution tiers.** High-resolution tier (Claude 4.7 and later): max long edge 2,576 px, max 4,784 visual tokens. Standard tier (all other models): 1,568 px and 1,568 tokens. Larger images are downscaled with aspect ratio kept. High-res support is automatic, with no beta header — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Worked examples from the docs.** 200x200 = 64 tokens. 1000x1000 = 1,296. 1920x1080 = 1,560 on standard (downsized to 1456x819) but 2,691 on high-res (not resized). 3840x2160 = 1,560 on standard but 4,784 on high-res (downsized to 2576x1449) — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **The docs' own cost guidance.** High-res images "can use up to roughly three times more visual tokens" than on a standard-tier model. If you don't need that fidelity, downsample before sending. Resizing before upload also lowers latency — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Price examples from the docs.** Opus 5.5 input costs $4/MTok, so a 1000x1000 image is about $5.18 per thousand and a 4K image about $19.14 per thousand — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Image count limits.**
  - The API allows up to 600 images per request, or 100 for models with a 200k context.
  - Once a request holds more than 20 image blocks, a stricter per-image size limit applies to every image. The 20 includes images resent from earlier turns and images inside `tool_result` blocks.
  - The fix the docs give: keep every image at or under 2000 px per side, or keep 20 or fewer image blocks.
  - Request bodies are capped at 32 MB on standard endpoints.
  — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Quality guidance.**
  - Images under 200 px risk hallucination.
  - Resizing can make text illegible, so pre-resize and/or crop.
  - Heavy JPEG compression "can make text difficult to read", especially after several compression passes.
  - Images placed before the text prompt work best.
  - When sending several images, label each one ("Image 1:").
  — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Payloads in long sessions.** Every agent turn resends the whole history, so base64 images inflate request size and latency on every turn. The Files API `file_id` keeps payloads small (API-level advice) — [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Claude Code and MCP image results.** When an MCP tool returns PNG/JPEG/GIF/WebP, Claude sees an inline copy that "may be scaled down or compressed". Claude Code also saves the original bytes to the session's `tool-results` directory and gives Claude the path, so Claude can crop the full-resolution file later. Image-returning tools stay subject to `MAX_MCP_OUTPUT_TOKENS` (default 25,000) — [Claude Code MCP docs, fetched 2026-10-27](https://code.claude.com/docs/en/mcp)
- **Secondary source on the 2.7x jump.** A Towards AI article headlined "Claude sees screenshots sharper now; your agent can send 2.7x the tokens" covers the same formula and the higher cost of screenshots on new models — [Towards AI (secondary)](https://pub.towardsai.net/claude-sees-screenshots-sharper-now-your-agent-can-send-2-7x-the-tokens-73dabc991398)
- **Grids and contact sheets: IG-VLM (2024).**
  - Samples 6 frames (the first frame of each of six equal intervals) and tiles them into one 3x2 grid image for a single VLM.
  - Beat existing zero-shot methods on 9 of 10 video-QA benchmarks.
  — [IG-VLM, arXiv 2403.18406](https://arxiv.org/pdf/2403.18406)
- **Limit of grids.** T2SGrid (arXiv 2603.06973) notes that a keyframe grid models only coarse-grained events. It is not good for fine temporal grounding — [T2SGrid](https://www.alphaxiv.org/abs/2603.06973.md)
- **How many frames: VideoAgent (ECCV 2024).** An LLM agent that first looks at uniformly sampled frames and fetches more only when needed scored 54.1% on EgoSchema and 71.3% on NExT-QA, using on average only 8.4 and 8.2 frames — [VideoAgent, arXiv 2403.10517](https://arxiv.org/abs/2403.10517v1)
- **Frame choice versus resolution at a fixed token budget (Sept 2026).**
  - Frame selection is "the largest single lever": 8 frames selected for the query beat 16 uniformly spaced frames by 6.9 points on LongVideoBench's hour-long bin.
  - Halving each frame's spatial budget costs at most 0.44 points.
  - Spending the saved tokens on twice as many compressed frames, at no more than the original 8-frame cost, adds 2 to 3 points.
  - Orthogonal Matching Pursuit, an old algorithm used unmodified, matched purpose-built frame selectors to within one point.
  - Single-author paper; benchmark results from open MLLMs, not Claude.
  — [Select, Compress, Reinvest, arXiv 2609.03820](https://arxiv.org/abs/2609.03820)
- **Visual tokens are highly redundant.**
  - Training-free pruning methods report about 99.5% of performance retained while pruning 75% of video tokens (MMG-Vid; secondary summary, not checked against the primary paper).
  - VScan-style results put the best retention rates at about 17–25% at the encoder and about 33% inside the LLM.
  - These are model-internal techniques, which Claude API users cannot apply, but they show how little of a frame's pixel area carries the answer.
  — [Emergent Mind: MMG-Vid](https://www.emergentmind.com/topics/mmg-vid); [Emergent Mind: VScan](https://www.emergentmind.com/topics/vscan); survey: [Why Is Video Still So Expensive?, arXiv 2609.10355](https://arxiv.org/pdf/2609.10355)
- **Comparison point: Gemini 3/4 pricing.**
  - Video: 70 tokens per frame at low/medium resolution, 280 at high resolution, and high is recommended only for OCR or small details.
  - Images: 1,120 tokens by default, 280 at low.
  — [Gemini media_resolution docs, updated 2026-10-13](https://ai.google.dev/gemini-api/docs/media-resolution)

### Inferences
- **Token cost of common frame sizes on Opus 5.5** (high-res tier, computed with the documented formula):

  | Frame size | Tokens |
  |---|---|
  | 1920x1080 | 2,691 |
  | 1280x720 | 1,196 |
  | 960x540 | 700 |
  | 854x480 | 558 |
  | 640x360 | 299 |
  | 448x252 | 144 (exactly 16x9 patches) |
  | 1080x1920 (vertical) | 2,691 |

  So "one HD frame" costs about as much as nine 360p frames. Default to 360p–540p for story, composition and motion judgements. Spend high resolution only on crops.
- **Contact sheets save image blocks, not tokens per pixel.** A 3x3 sheet of 640x360 tiles (1920x1080) costs 2,691 tokens, the same as nine separate 640x360 images. It is still the better default:
  - it keeps the request under the 20-image threshold, after which every image must be at most 2000 px;
  - it gives the model all frames side by side, which IG-VLM found works well;
  - it avoids per-block overhead.
- **Snap tile sizes to multiples of 28 px.** The ceiling function otherwise wastes up to one patch row and one patch column per image. For example, 448x252 (16x9 patches, 144 tokens) instead of 450x253 (17x10 = 170 tokens). For a sheet, snap the whole canvas, because tokens are computed on the composite image.
- **Text legibility.** Do not judge text from a downscaled full frame. Send a crop of the text region at native or upscaled resolution: a 560x140 crop is 20x5 = 100 tokens. Use PNG or high-quality JPEG/WebP for glyph checks, because the docs warn that heavy JPEG hurts text, and avoid re-encoding twice. Keep text regions above 200 px on the short side where possible.
- **Faces.** Likewise send a face crop rather than a whole frame. Note that Claude will not identify people, so face checks can only cover framing, focus, expression and occlusion.
- **Suggested frame budgets per question** (heuristics; no source measures these for Claude):
  - *Whole scene or story:* 6–9 frames on one contact sheet (IG-VLM used 6, VideoAgent averaged about 8).
  - *A cut:* about 4–6 frames — the last 2–3 frames before and the first 2–3 after, at 360p, plus the numeric cut metadata.
  - *A pan, zoom or other camera move:* 4–6 evenly spaced frames, or a filmstrip, plus motion-vector or optical-flow numbers as text.
  - *Escalation:* fetch more frames only when the model asks, as VideoAgent does.
- **Choose frames by query, not uniformly.** Pick frames by scene change, motion peak, or text-on-screen detection. The 2609.03820 result (8 well-chosen frames beat 16 uniform frames by 6.9 points) suggests this improves quality as well as saving tokens.
- **Use Claude Code's saved originals.** Because Claude Code keeps the original bytes of MCP images on disk, the server can return a small preview inline and let Claude re-crop the original only when needed.

### Gaps
- No Anthropic source gives image-understanding accuracy at different resolutions or JPEG qualities for Claude. The 0.44-point figure for halving resolution comes from open MLLMs on long-video QA, not from Claude, and not from text-legibility tasks.
- No source found on how many frames are needed to judge a cut or a pan specifically. The budgets above are heuristics to be validated on EditVideo's own review set.
- I did not find whether `editvideo_observe_media` output is downscaled again by Claude Code on top of API downscaling. Claude Code's docs say only "may be scaled down or compressed".
- Older notes using `(w*h)/750` and a 1.15 MP cap describe a superseded scheme. I did not fetch an archived page to confirm when the patch formula replaced it.

## 2. MCP and tool-use design for large tool sets; prompt caching; context editing and compaction

### Takeaway
For a large server, the biggest savings come from three things:
- not loading tool definitions up front (tool search / deferred loading, about 85% fewer tokens, and higher accuracy);
- not passing intermediate data through the model (code execution / programmatic tool calling, 37% to 98% fewer tokens in Anthropic's examples);
- returning concise, handle-based results.

Claude Code already defers MCP tools by default. It cuts descriptions at 4,096 characters for upfront tools and 16,384 for deferred tools. It warns above 10,000 output tokens, and text results over 50,000 characters are saved to a file instead of shown in full. Prompt-cache reads on Opus 5.5 cost 0.05x the base input price, but any change to the tool definitions invalidates the whole cache.

### Cited Findings
- **Tool definition bloat.**
  - 58 tools across five servers cost about 55K tokens before the conversation starts, and Anthropic has seen 134K tokens of definitions.
  - With Tool Search: about 500 tokens up front plus about 3K for 3–5 discovered tools, about 8.7K in total versus about 77K. That is an 85% reduction.
  - Accuracy on MCP evals rose: Opus 4 from 49% to 74%, Opus 4.5 from 79.5% to 88.1%.
  - Recommended when definitions exceed 10K tokens or there are 10+ tools. Keep the 3–5 most-used tools loaded (`defer_loading: false`).
  - Deferral "doesn't break prompt caching", because deferred tools are left out of the initial prompt.
  — [Anthropic, "Introducing advanced tool use", Nov 24, 2025](https://www.anthropic.com/engineering/advanced-tool-use)
- **Programmatic Tool Calling.**
  - Average tokens on complex research tasks fell from 43,588 to 27,297 (37%).
  - In one example, about 200KB of raw data shrank to about 1KB of results.
  - Running 20+ calls in one code block removes 19+ inference passes.
  - Best for 3+ dependent calls, large data where only aggregates matter, and parallel, idempotent tools.
  — [Advanced tool use, Nov 24, 2025](https://www.anthropic.com/engineering/advanced-tool-use)
- **Tool Use Examples.** Accuracy on complex parameters rose from 72% to 90%. Use 1–5 examples per tool (minimal, partial, full). They cost tokens, so skip them for simple tools — [Advanced tool use, Nov 24, 2025](https://www.anthropic.com/engineering/advanced-tool-use)
- **Code execution with MCP.**
  - Tools are presented as code files, and the agent loads only what it needs. One workflow fell from 150,000 to 2,000 tokens (98.7%), an illustrative example rather than a benchmark.
  - A `search_tools` tool with a detail-level parameter (name only; name plus description; full schema) supports this progressive disclosure.
  - Filtering in code means the model sees, for example, a few rows of a 10,000-row sheet.
  - Saving intermediate results to files and keeping reusable code as skills are part of the same pattern.
  - Cost: it needs a sandboxed execution environment.
  — [Anthropic, "Code execution with MCP", Nov 4, 2025](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Writing tools for agents.**
  - Offer a `response_format` enum with "concise" and "detailed". In the example, detailed = 206 tokens and concise = 72, about one-third.
  - Claude Code caps tool responses at 25,000 tokens by default. Use pagination, range selection, filtering and truncation with sensible defaults, and when truncating, tell the agent how to narrow the query.
  - Resolve UUIDs into readable names or 0-indexed IDs, which reduced hallucination, but keep technical IDs available in the detailed format.
  - Merge chains of low-level calls into workflow tools (for example `search_logs`, which returns only relevant lines).
  - Namespace tool names with prefixes.
  - Write errors as actionable messages, not tracebacks.
  — [Anthropic, "Writing effective tools for agents", Sep 11, 2025](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **Claude Code tool-search behaviour.**
  - MCP tools are deferred by default.
  - `ENABLE_TOOL_SEARCH=auto` loads tools up front while their definitions total under 10% of the context window. `auto:N` sets a custom percentage, and `false` loads everything up front.
  - A server or tool can force upfront loading with `"anthropic/alwaysLoad": true` in the tool's `_meta`.
  - Server instructions become "more useful with tool search": they should say what tasks the server handles, when to search for its tools, and its key capabilities.
  — [Claude Code MCP docs, fetched 2026-10-27](https://code.claude.com/docs/en/mcp)
- **Claude Code description limits.**
  - Server instructions and the description of any upfront tool are cut at 4,096 characters.
  - Descriptions of tools loaded through tool search are cut at 16,384 characters.
  - Tool search matches only within the shorter limit, so search keywords and critical details belong near the start.
  - `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` overrides both limits. Before v2.1.296 the shorter limit was 2,048 characters.
  — [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)
- **Claude Code output limits.**
  - Warning above 10,000 tokens; default cap 25,000 tokens (`MAX_MCP_OUTPUT_TOKENS`).
  - Text results over the cap, or over 50,000 characters, are saved to a file and replaced by a path.
  - Per-tool `_meta["anthropic/maxResultSizeChars"]` raises the threshold, up to a ceiling of 500,000 characters.
  - Error text over about 11,000 characters keeps only its first and last 5,000 characters.
  - HTTP/SSE responses over 16 MiB fail.
  — [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)
- **Prompt caching: prices and minimums.**
  - TTL: 5 minutes by default, refreshed on each read, or 1 hour.
  - Writes cost 1.25x (5 min) or 2x (1 h). Reads cost 0.1x on most models, 0.05x on Opus 5.5 and Sonnet 5.5.
  - For Opus 5.5 that means $5 per MTok for a 5-minute write, $8 for a 1-hour write, and $0.20 for a read.
  - Minimum cacheable length is 512 tokens on Opus 5.5.
  — [Prompt caching docs, fetched 2026-10-27](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- **Prompt caching: breakpoints and lookback.**
  - Up to 4 explicit breakpoints; automatic caching uses one of them.
  - On a miss, the API looks back up to 20 block positions for an earlier write; consecutive tool_use or tool_result blocks count as one position.
  - If a single turn adds more than 20 blocks, the earlier cache entry falls outside that window.
  — [Prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- **Prompt caching: what invalidates it.**
  - Order is tools → system → messages. Any change to tool definitions invalidates all three.
  - Adding or removing images anywhere, or changing `tool_choice`, invalidates the messages cache.
  - Thinking and effort changes can also invalidate, depending on the model.
  - Mid-conversation, add tools via `tool_addition` blocks (beta `inline-tools-2026-09-15`) and system changes as `{"role":"system"}` messages, so the cached prefix survives.
  - Use stable key ordering in `tool_use` JSON. Cache hits are not counted against rate limits and improve time-to-first-token.
  — [Prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- **Context editing: tool result clearing.**
  - `clear_tool_uses_20250919` clears the oldest tool results first.
  - Defaults: trigger at 100,000 input tokens, keep 3 tool uses. `clear_at_least` (no default) makes clearing worth the cache invalidation it causes. `exclude_tools` protects named tools; `clear_tool_inputs` (default false) also clears the call parameters.
  - Response metadata reports `cleared_tool_uses` and `cleared_input_tokens`.
  - Beta header: `context-management-2025-06-27`.
  — [Context editing docs, fetched 2026-10-27](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- **Context editing: thinking, compaction and memory.**
  - `clear_thinking_20251015` manages old thinking blocks.
  - Server-side compaction (`compact_20260112`) is the primary recommendation for long conversations. In the example, a history of about 100k tokens became about 2–3k.
  - The memory tool (`memory_20250818`) warns Claude before clearing, so it can save results to files first.
  — [Context editing docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- **Context engineering.**
  - Aim for the "smallest possible set of high-signal tokens". Recall degrades as context grows ("context rot").
  - Keep lightweight identifiers (paths, queries) and load data just in time.
  - Tool result clearing is the lightest form of compaction.
  - Claude Code's compaction keeps the summary plus the 5 most recently accessed files.
  - Bloated tool sets are a common failure: "if a human engineer can't definitively say which tool should be used… an AI agent can't be expected to do better".
  — [Anthropic, "Effective context engineering for AI agents", Sep 29, 2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### Inferences
- **The router surface is right; the detail level of `discover_tools` is the next lever.** The 7-tool router (bootstrap / discover / execute / observe …) already matches Anthropic's recommended shape, with a few always-loaded core tools and the rest discovered.
  - `editvideo_discover_tools` should take a `detail` parameter (`names` | `summary` | `schema`), as in the code-execution-with-MCP pattern.
  - Default to `summary`: one line per tool, about 15–25 tokens each, roughly 2–3.5K tokens for all 137 tools.
  - Return the full schema only for the 1–3 tools the model is about to call.
  - The local memory note that a learnkit description budget sits at 39,956 of 40,000 characters suggests the descriptions themselves are the bulk of the cost. Check that no single upfront description or the server instructions exceed 4,096 characters, because Claude Code silently cuts them.
- **Put the searchable words first.** Claude Code's tool search reads only the first 4,096 characters, so each of the 7 router tools should open with what it does and when to use it. Reference material goes after.
- **Make `concise` the default response everywhere.** Return IDs and paths for frames, sheets, timelines and renders (for example `artifact_id`, `path`, `revision_sha`) plus a short structured summary. Detail goes behind `response_format="detailed"` or a follow-up `get_*` call.
- **Size budgets for results.** Keep text results under about 2–4K tokens, well below Claude Code's 10K warning. Never rely on the 50,000-character file fallback: it costs an extra Read round-trip and the model loses the structure.
- **Keep the tool list byte-stable within a session.** Never send `tools/list_changed` mid-task: any tool-definition change invalidates the tools, system and messages caches. Sort JSON keys deterministically in results and schemas.
- **Prefer workflow tools for 3+ dependent calls.** Combinations such as "render → probe → sample frames → contact sheet" can be one workflow tool, or a server-side plan executed in one call. This is the programmatic-tool-calling saving (37% on average) without needing a sandbox on the Claude side.
- **Use 1–5 input examples only for the few complex schemas.** Timeline patch, composition spec and keyframe lists are the candidates; this is where the 72% → 90% accuracy gain applies. Skip examples elsewhere.
- **Pruning old images breaks the messages cache.** Removing images invalidates it from that point on, so prune in batches (the logic of `clear_at_least`) rather than one image per turn.

### Gaps
- I did not verify whether Claude Code applies the API's context editing (`clear_tool_uses`) to MCP image results automatically. The Claude Code docs I read cover output caps and file persistence only.
- No source gives the token overhead of one MCP image content block beyond its pixel tokens.
- No published per-tool token measurements exist for FastMCP specifically. FastMCP schema generation (Pydantic → JSON Schema) can add verbose `title` and `anyOf` fields; this was not measured here and should be checked with a token count of `tools/list`.

## 3. Evidence compression for audio and timelines

### Takeaway
I found no source that measures transcripts against waveforms or loudness plots for an LLM judge. The only hard reference point is Gemini's 25 tokens per second of raw audio. Text evidence (word-timestamped transcript, loudness and peak numbers, a per-shot table) is cheaper and searchable. Timeline reads should be diffs keyed to revision IDs, an inference supported by Anthropic's guidance on concise, filtered, paginated results.

### Cited Findings
- Gemini 3/4 tokenizes audio at 25 tokens per second at every resolution, so 60 s of audio is about 1,500 tokens — [Gemini media_resolution docs, updated 2026-10-13](https://ai.google.dev/gemini-api/docs/media-resolution)
- Anthropic's example of passing a long transcript through the model: a 2-hour meeting transcript adds about 50,000 tokens, and passes through the model twice when copied from one tool to another. Keeping it in the execution environment avoids this — [Code execution with MCP, Nov 4, 2025](https://www.anthropic.com/engineering/code-execution-with-mcp)
- Anthropic recommends `search_logs`-style tools that return only relevant lines plus context instead of full reads, and filtering, pagination and range selection for large outputs — [Writing effective tools for agents, Sep 11, 2025](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Claude Code's compaction and tool-result clearing assume raw tool output can be dropped once used. Notes and identifiers should persist instead — [Effective context engineering, Sep 29, 2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### Inferences
- **Audio evidence ladder, cheapest first:**
  1. Numbers: integrated LUFS, true peak, LRA, music-under-speech ducking dB, and silence gaps longer than X ms, as about 50–150 tokens of JSON.
  2. A transcript with word or phrase timestamps, filtered to the window under review. Speech runs about 150 words per minute, so a filtered minute is a few hundred tokens. This is my estimate, not a sourced figure.
  3. A small loudness-curve or waveform image only when shape matters (pumping, clipping runs). A 560x112 strip is 20x4 = 80 tokens on Claude's formula.
  4. Raw audio last, and only if the client and model accept audio blocks.
- **Timeline reads.**
  - Return `{revision_sha, changed: [...], unchanged_count}` diffs against the last revision the model saw, and a full timeline only on request with pagination by track or time range.
  - The server already requires the latest revision/SHA for mutations, which makes "diff since SHA" cheap to support.
- **Per-shot fingerprints.** Keep a compact per-shot row computed once and cached server-side: id, in/out frames, duration, shot scale, dominant motion, mean luma/saturation, face count, OCR-text-present flag, transcript snippet, perceptual hash. About 30–60 tokens per shot lets the model reason about a whole cut list in a few thousand tokens. It then pulls pixels (sheets or crops) only for the shots it flags.

### Gaps
- No found source compares, for an LLM judge, timestamped transcripts against waveform images against loudness curves for detecting audio issues such as clipping, ducking, sync or pacing.
- I did not verify whether the Claude Messages API, or Claude Code's handling of MCP `audio` content blocks, accepts raw audio as of October 2026. The EditVideo server's own instructions mention "audio blocks", but I found no Anthropic doc in this session confirming that Claude consumes them.
- No external source on timeline diff formats or shot-fingerprint schemas for LLM agents. The recommendations above are design inferences.

## 4. Patterns from other agentic systems that measurably reduced tokens

### Takeaway
The patterns with numbers behind them:
- discovering tools on demand (−85% definition tokens);
- doing data work in code or on the server and returning aggregates (−37% average, −98.7% in one example);
- returning concise results (about 3x smaller);
- keeping only the last few screenshots (computer-use agents commonly keep 3);
- looking at a few frames first and fetching more only when needed (VideoAgent: about 8 frames per question);
- delegating heavy reads to sub-agents that return 1–2K-token summaries and write details to files.

Sub-agents are not free. Anthropic measured multi-agent research at about 15x the tokens of chat.

### Cited Findings
- **Multi-agent research system.**
  - Agents use about 4x the tokens of chat; multi-agent systems about 15x.
  - Token usage alone explained 80% of the variance in BrowseComp performance.
  - Multi-agent (Opus 4 lead, Sonnet 4 sub-agents) beat single-agent Opus 4 by 90.2% on the internal research eval.
  - Parallel tool calling and sub-agents cut research time by up to 90%.
  - Sub-agents write outputs to a filesystem and pass lightweight references to avoid the "game of telephone".
  - Effort scaling: simple tasks get 1 agent and 3–10 tool calls; comparisons 2–4 sub-agents with 10–15 calls each.
  - Not a fit when agents must share context or the task has many dependencies.
  — [Anthropic, "How we built our multi-agent research system", Jun 13, 2025](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Sub-agent summaries.** A sub-agent may use tens of thousands of tokens but returns "a condensed, distilled summary… (often 1,000–2,000 tokens)" — [Effective context engineering, Sep 29, 2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **Screenshot retention in computer-use agents.**
  - The Cua agent SDK's `only_n_most_recent_images` (example value 3) drops older screenshots automatically. It is also offered as an `ImageRetentionCallback`.
  - A Claude Code GitHub issue reports a resumed session resending its accumulated screenshots on every call and proposes keeping the last 2–3 (a user report, not a confirmed fix).
  — [Cua docs: cost saving](https://docs.trycua.com/docs/agent-sdk/callbacks/cost-saving); [claude-code issue #27869](https://github.com/anthropics/claude-code/issues/27869)
- **"Observe once, then retrieve on demand" for video.** VideoAgent views uniformly sampled frames, judges whether the information is enough, and only then retrieves more frames with CLIP, with captions from a VLM. It averaged about 8 frames per question — [VideoAgent, arXiv 2403.10517](https://arxiv.org/abs/2403.10517v1)
- **Grid-LoGAT.** A VLM transcribes each grid cell to text once, then a text-only LLM answers. It reported 65.9% on NExT-QA. This is caching perception as text — [Grid-LoGAT, arXiv 2505.24371](https://arxiv.org/html/2505.24371v3)
- **Programmatic and code-execution patterns** (orchestrating many calls in code, returning aggregates): −37% on average, about 200KB → 1KB in one example, and 150K → 2K tokens in another — [Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use); [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)

### Inferences
- **Observe once, act many.** Compute perceptual features (shot table, OCR text boxes, face boxes, motion and loudness stats, perceptual hashes) once per media revision and cache them keyed by SHA. Return them as text. Pixels go to Claude only for (a) final aesthetic judgement and (b) items the numbers flag, which is verification sampling.
- **Image retention policy for long sessions.** Keep at most about 3 recent evidence images per review thread. The 20-image threshold also makes this a correctness issue: past 20 image blocks in a request, every image must be at most 2000 px.
  - Cost of not doing it (my arithmetic, not a measurement): an agent that keeps every 1080p frame on Opus 5.5 carries 2,691 × N(N+1)/2 cumulative input tokens over N steps, about 323K tokens for 15 steps. Keeping the last 3 caps it near 2,691 × (1+2+3×13) ≈ 113K.
  - Cache reads at 0.05x soften the dollar cost, but not the context-rot cost.
- **Sub-agents for heavy reads.** Use them (for example the existing `editvideo-reviewer`) for full-render reviews: the sub-agent looks at many sheets and crops and returns a 1–2K-token verdict plus file paths. Because of the 15x multiplier, do not spawn sub-agents for single-shot checks.

### Gaps
- No published measurement found for a video-editing agent specifically, for example tokens per accepted edit.
- No measured figures from Anthropic's reference computer-use demo for the default image retention. The vendor claim that it trims old screenshots by default was not verified.

## 5. Measuring token use per task, and budgets per step

### Takeaway
The API gives exact per-request accounting: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`, and `cleared_input_tokens` when context editing runs. Anthropic recommends tracking accuracy, runtime, tool-call count, total tokens and tool errors per task. On a local FastMCP server, the server itself can log result size and the exact visual-token cost of every image it returns, because the formula is deterministic.

### Cited Findings
- Total input = `cache_read_input_tokens + cache_creation_input_tokens + input_tokens`. `cache_creation` splits into `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`. If both cache fields are 0, nothing was cached. Cache diagnostics compare consecutive requests and report where the prefix diverged — [Prompt caching docs, fetched 2026-10-27](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Context editing reports `cleared_tool_uses` and `cleared_input_tokens`. Token counting shows `original_input_tokens` against post-clearing `input_tokens` (example: 70,000 → 25,000). The token counting endpoint is the suggested fix when cached-read inflation would trigger compaction too early — [Context editing docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- **Metrics to track:**
  - Top-level accuracy; runtime per tool call and per task; total tool calls; total tokens; tool errors.
  - Many redundant calls point to pagination or limit defaults that need tuning; many invalid-parameter errors point to descriptions or examples that need fixing.
  — [Writing effective tools for agents, Sep 11, 2025](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Effort-scaling budgets used in production prompts: 3–10 tool calls for simple tasks, 10–15 per sub-agent for comparisons — [Multi-agent research system, Jun 13, 2025](https://www.anthropic.com/engineering/multi-agent-research-system)
- Claude Code thresholds usable as hard budget lines: 10,000-token warning and 25,000-token default cap per MCP result; 50,000 characters before text is saved to file — [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)

### Inferences
- **Server-side ledger.** For every tool response, log: tool name, `response_format`, text characters and estimated tokens (about chars/4 as a fast proxy; use the count_tokens endpoint for calibration), image count, each image's w×h, and visual tokens = `ceil(w/28)*ceil(h/28)` (high-res tier cap 4,784). Sum these per `bootstrap` task id. This gives exact, attributable cost without access to Claude Code's API usage.
- **Starting budgets per step** (to be tuned against the eval set):

  | Step | Tokens |
  |---|---|
  | `bootstrap` | ≤1.5K |
  | `discover_tools` summary | ≤3.5K |
  | Full schema per tool | ≤800 |
  | Ordinary execute result | ≤2K text |
  | Review observation | ≤1 contact sheet (≤2,691) + ≤2 crops (≤300 each) + ≤500 text |
  | Full-render review | sub-agent; ≤2K summary back to the lead |

  Fail loudly, with an actionable hint to narrow the request, when a tool would exceed its budget, rather than truncating silently.
- **Regression gate.** Run a fixed set of representative tasks (edit a cut, fix a title, review a render) and record tokens, tool calls and accuracy per task. Gate changes to tool descriptions and response shapes on these numbers, as Anthropic's tool-writing post recommends.

### Gaps
- I did not fetch Claude Code's OpenTelemetry/usage-export docs. Whether per-MCP-tool token attribution is available client-side was not verified, so the server-side ledger is the dependable option.
- No source gives Claude-specific numbers for "tokens per step" budgets in multimodal agents. The budgets above are derived from the cited limits and formulas, not measured.
