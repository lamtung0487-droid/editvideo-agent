# Contributing

This project gives an AI capabilities (senses, hands, composition skills); changes are judged by what they let a model
do reliably per token, not by UI.

- **Keep the runtimes in step.** `engines/effects.js` and `engines/scene3d.js` are shared by Remotion and HyperFrames;
  a new layer field or effect needs the Pydantic model (`editvideo/models.py`), validation, the runtime and a test.
- **Measure, then claim.** New analysis comes with a synthetic ground-truth test (see `tests/synth_*.py`); new visual
  behaviour with a node-level numeric test of the runtime and a real snapshot.
- **Respect the token budget.** Tool descriptions stay short (tests enforce a total budget); large results go to disk
  behind a handle; catalogs list compact rows until an exact id is asked for.
- **Fix at the system level.** When a render shows a defect, change the recipe, default or audit check so no future
  video repeats it; run the independent reviewer (`.claude/agents/editvideo-reviewer.md`) on the result.
- Run `python -m pytest -q` before sending a change. Media tests refuse to run with less than ~2 GB free where their
  temporary folders live; on a full system drive point pytest elsewhere: `python -m pytest -q --basetemp D:/tmp/pytest`.
- Do not commit `data/`, `outputs/`, models or media.
