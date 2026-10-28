"""Executable source selects, frame budgets and declared multi-shot continuity (no model/network)."""
import copy
from pathlib import Path
import pytest
from editvideo import store, agent, sequence, film_world
from editvideo.media import FFMPEG, command


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    return tmp_path


@pytest.fixture
def sources(local):
    paths = []
    for colour, frequency in [("red", 440), ("blue", 880)]:
        path = local / (colour + ".mp4")
        command([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=160x90:r=30:d=6",
                 "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=6", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path])
        paths.append(path)
    return paths


def candidate(path, name, a, b, relevance=1):
    return {"id": name, "path": str(path), "start": a, "end": b, "relevance": relevance, "reason": "Caller inspected this whole action."}


def test_budget_search_keeps_all_beats_and_is_not_greedy(sources):
    a, b = sources
    r = sequence.run({"title": "Short", "budget_seconds": 5, "minimum_seconds": 5,
                      "beats": [{"id": "hook", "purpose": "Show outcome", "candidates": [candidate(a, "long", 0, 4), candidate(a, "short", 0, 2, .8)]},
                                {"id": "payoff", "purpose": "Explain", "candidates": [candidate(b, "explain", 0, 3)]}]})
    assert r["total_frames"] == 150 and [s["id"] for s in r["selected"]] == ["short", "explain"]
    assert r["selected"][1]["start_frame"] == 60
    assert r["unused_budget_s"] == 0


def test_multisource_build_preserves_audio_and_retry_is_idempotent(sources):
    r = sequence.run({"title": "Audio selects", "budget_seconds": 4, "beats": [
        {"id": "hook", "purpose": "A", "candidates": [candidate(sources[0], "a", 1, 3)]},
        {"id": "payoff", "purpose": "B", "candidates": [candidate(sources[1], "b", 2, 4)]}]})
    before = len(store.list_projects())
    built = sequence.run(plan_id=r["plan_id"], create=True)
    p = agent.read(built["project_id"])
    t = p["timeline"]
    assert len(store.list_projects()) == before + 1
    assert [s["source_start"] for s in t["shots"]] == [1, 2]
    assert [s["start_frame"] for s in t["shots"]] == [0, 60]
    assert len({s["asset_id"] for s in t["shots"]}) == 2
    assert len(t["audio_clips"]) == 2 and all(not c["duck_under_voice"] for c in t["audio_clips"])
    assert sequence.run(plan_id=r["plan_id"], create=True)["project_id"] == p["id"]
    assert len(store.list_projects()) == before + 1


def test_overlap_and_chronology_can_be_intentionally_relaxed(sources):
    q = {"title": "Same source", "budget_seconds": 6, "beats": [
        {"id": "a", "purpose": "A", "candidates": [candidate(sources[0], "a", 2, 4)]},
        {"id": "b", "purpose": "B", "candidates": [candidate(sources[0], "b", 1, 3)]}]}
    with pytest.raises(ValueError, match="No feasible sequence"):
        sequence.run(q)
    assert sequence.run({**q, "prevent_source_overlap": False})["total_frames"] == 120
    with pytest.raises(ValueError, match="No feasible sequence"):
        sequence.run({**q, "prevent_source_overlap": False, "chronological": True})


def test_changed_sources_and_invalid_windows_are_rejected(sources):
    q = {"title": "A", "budget_seconds": 2, "beats": [{"id": "a", "purpose": "A", "candidates": [candidate(sources[0], "a", 0, 2)]}]}
    p = sequence.run(q)
    sources[0].write_bytes(b"modified")
    with pytest.raises(ValueError, match="changed"):
        sequence.run(plan_id=p["plan_id"], create=True)
    q["beats"][0]["candidates"] = [candidate(sources[1], "outside", 5, 8)]
    with pytest.raises(ValueError, match="exceeds duration"):
        sequence.run(q)
    with pytest.raises(ValueError, match="handle"):
        sequence.run(plan_id="../escape")


def world():
    return {"title": "The key", "premise": "A courier finds a door.", "look": "Warm light, restrained camera, original fictional characters.",
            "entities": [{"id": "linh", "kind": "character", "description": "Short black hair, green coat", "voice": "Quiet low voice",
                          "initial_state": {"holds": "nothing", "coat": "green"}},
                         {"id": "key", "kind": "prop", "description": "Brass key", "initial_state": {"location": "table"}}],
            "shots": [{"id": "pick", "scene": "room", "purpose": "Discovery", "action": "Linh picks up the brass key.", "seconds": 2,
                       "entities": ["linh", "key"], "axis_id": "table", "axis_side": "A", "screen_direction": "right",
                       "changes": {"linh": {"holds": "key"}, "key": {"location": "hand"}}},
                      {"id": "walk", "scene": "room", "purpose": "Approach", "action": "Linh walks to the door holding the key.", "seconds": 3,
                       "entities": ["linh", "key"], "requires": {"linh": {"holds": "key"}},
                       "axis_id": "table", "axis_side": "B", "screen_direction": "left", "continuous_action": True}]}


def test_film_state_prompt_reference_history_and_live_generation_schema(local):
    from editvideo.generation import GenerationRequest
    r = film_world.run(world())
    assert {n["kind"] for n in r["continuity_notes"]} == {"axis_cross", "direction_reversal"}
    packet = film_world.run(world_id=r["world_id"], shot_id="walk")
    assert packet["state_before"]["linh"]["holds"] == "key"
    assert "green coat" in packet["prompt"] and "Brass key" in packet["prompt"]
    assert packet["reference_history"][0]["previous_appearance"] == "pick"
    assert packet["cast"][0]["voice"] == "Quiet low voice"
    gen = packet["generation_call"]["arguments"]["request"]
    GenerationRequest.model_validate(gen)
    assert gen["frame_count"] / gen["fps"] >= 3
    assert packet["finishing"]["trim_to_frames_30fps"] == 90
    assert film_world.run(world_id=r["world_id"], detail=True)["world"]["title"] == "The key"


def test_state_mismatch_is_a_question_and_explicit_reset_can_resolve_it(local):
    q = world()
    q["shots"][1]["requires"]["linh"]["coat"] = "red"
    r = film_world.run(q)
    assert any(n["kind"] == "state_mismatch" for n in r["continuity_notes"])
    q["shots"][1]["reset_state"] = {"linh": {"coat": "red"}}
    q["shots"][1]["motivated_axis_cross"] = True
    q["shots"][1]["screen_direction"] = "right"
    r2 = film_world.run(q, world_id=r["world_id"], base_revision=1)
    assert r2["revision"] == 2 and r2["total_notes"] == 0
    with pytest.raises(ValueError, match="revision conflict"):
        film_world.run(q, world_id=r["world_id"], base_revision=1)


@pytest.mark.parametrize("change", ["missing_reference", "too_long", "short_frames", "bad_options"])
def test_generation_packet_never_silently_weakens_unsupported_requests(local, change):
    q = world()
    s = q["shots"][0]
    if change == "missing_reference":
        s["reference_image"] = str(local / "missing.png")
    elif change == "too_long":
        s["seconds"] = 12
    elif change == "short_frames":
        s["seconds"] = 4
        s["generation"] = {"provider": "local_ltx", "frame_count": 49}
    else:
        s["generation"] = {"provider": "unknown"}
    r = film_world.run(q)
    packet = film_world.run(world_id=r["world_id"], shot_id="pick")
    assert packet["generation_call"] is None and packet["generation_notes"]


def test_unknown_entities_and_invalid_layouts_do_not_enter_memory(local):
    q = world()
    q["shots"][0]["entities"] = ["someone_else"]
    with pytest.raises(ValueError, match="unknown entity"):
        film_world.run(q)
    q = world()
    q["shots"][0]["layout"] = {"linh": [0, 0, 2, 1]}
    with pytest.raises(ValueError, match="normalized"):
        film_world.run(q)


def test_long_film_summaries_are_paged_and_exact_shots_remain_readable(local):
    q = world()
    template = q["shots"][0]
    q["shots"] = [{**template, "id": f"s-{i}", "purpose": "p" * 800} for i in range(30)]
    r = film_world.run(q)
    assert r["total_shots"] == 30 and len(r["shots"]) == 12 and r["next_offset"] == 12
    page = film_world.run(world_id=r["world_id"], offset=24, limit=12)
    assert len(page["shots"]) == 6 and page["next_offset"] is None
    packet = film_world.run(world_id=r["world_id"], shot_id="s-29")
    assert packet["shot"]["purpose"] == "p" * 800
