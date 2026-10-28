# Documentation map

You do not need to read this folder to start. Install ([INSTALL.md](../INSTALL.md)), render the demo, then read the
one guide for the task in front of you. An AI host needs even less: `editvideo_bootstrap(task)` routes it to the right
tools and guide, and the skill ([SKILL.md](../.claude/skills/editvideo-agent/SKILL.md)) lists one route per task.
Guides marked (vi) are in Vietnamese.

## Start

| Read | When |
|---|---|
| [SPEC.md](SPEC.md) | What the system is: parts, contracts, limits, how quality is kept |
| [FAST_AI_WORKFLOW.md](FAST_AI_WORKFLOW.md) | The working loop: scene context, edits, bounded repairs, delivery |
| [MODEL_INTEGRATION.md](MODEL_INTEGRATION.md) (vi) | Connecting Claude, Codex or another MCP host; the compact 7-tool mode |
| [AI_ERGONOMICS.md](AI_ERGONOMICS.md) | Why results are compact and how to keep context small |

## By task

| Task | Guide |
|---|---|
| A narrated or explainer video | [EXPLAINER_KIT.md](EXPLAINER_KIT.md), [NARRATION_STYLE.md](NARRATION_STYLE.md) |
| Choosing a look and a technique | [STYLE_DIRECTIONS.md](STYLE_DIRECTIONS.md) (vi), [CINEMATIC_TECHNIQUES.md](CINEMATIC_TECHNIQUES.md) (vi), [AESTHETIC_DIRECTION.md](AESTHETIC_DIRECTION.md) (vi) |
| Typography, colour, layout, effects | [DESIGN_LIBRARY.md](DESIGN_LIBRARY.md) (vi) |
| Cutting, pacing, music, sound, colour order | [PRO_WORKFLOWS.md](PRO_WORKFLOWS.md), [EDITING_CRAFT.md](EDITING_CRAFT.md) (vi), [PROFESSIONAL_VIDEO_PLAYBOOK.md](PROFESSIONAL_VIDEO_PLAYBOOK.md) (vi) |
| Short-form (TikTok, Reels, Shorts) and multi-shot AI films | [SHORTFORM_AND_FILM_RESEARCH.md](SHORTFORM_AND_FILM_RESEARCH.md) |
| Managed colour, HDR, LUTs, depth, 3D scenes, Blender | [COLOR_DEPTH_3D.md](COLOR_DEPTH_3D.md) (vi) |
| Reading footage over time; image-to-video | [IMAGE_VIDEO_AND_TEMPORAL_READING.md](IMAGE_VIDEO_AND_TEMPORAL_READING.md) (vi) |
| Tracking, masks, inpainting, generated footage | [SUBJECTS_AND_GENERATION.md](SUBJECTS_AND_GENERATION.md) (vi) |
| Exact timeline operations | [AGENT_RECIPES.md](AGENT_RECIPES.md) (vi) |
| Sources, licences, credits, maps | [RESOURCES.md](RESOURCES.md) (vi) |
| Checking a render: audits, frame review, motion | [REVIEW_AND_EVIDENCE.md](REVIEW_AND_EVIDENCE.md) (vi), [REVIEW_RUBRIC.md](REVIEW_RUBRIC.md) |
| Learning from reference videos and from work that succeeded | [LEARNING_FROM_REFERENCES.md](LEARNING_FROM_REFERENCES.md), [LEARNKIT.md](LEARNKIT.md) |

## History (not needed to use the system)

The system grew in rounds of study and building; some guides, test files (`tests/test_round*.py`) and the changelog
still name them. These pages record how it got here: [BUILD_SCOPE.md](BUILD_SCOPE.md) (vi),
[RESEARCH_AND_UPGRADE.md](RESEARCH_AND_UPGRADE.md) (vi), [VERIFICATION.md](VERIFICATION.md) (vi) and the research notes
in [research/](research/).
