"""Durable craft memory, grounded retrieval, subtitle attribution and current render evidence."""
import copy
import json
import pytest
from editvideo import store, learning, beatmap
from editvideo.media import sha256


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.initialize(recover=False)
    source = tmp_path / "reference.mp4"
    source.write_bytes(b"reference identity (no decoding needed for memory)")
    identity = sha256(source)
    study_id = "study-" + identity[:16]
    root = store.DATA / "observations" / study_id
    report = {"source": str(source), "source_sha256": identity, "duration_s": 60, "transcript": {"path": str(root / "transcript.txt")},
              "techniques_mentioned": {"editing": {"dissolve": {"at": ["00:12"], "count": 1}}}}
    store.write_json(root / "study.json", report)
    (root / "transcript.txt").write_text("[00:12] A dissolve transition suggests a passage of time.\n[00:30] Colour grading balances exposure.", encoding="utf-8")
    return study_id, source, root


def note(study_id):
    return {"title": "Chuyển cảnh diễn đạt thời gian", "principle": "Dissolve có thể gợi thời gian trôi qua.",
            "when_to_use": "Hai cảnh cùng chủ đề nhưng khác thời điểm.", "avoid": "Không làm mờ chữ cần đọc hoặc dùng ở mọi điểm cắt.",
            "steps": ["Xem chuyển động ở hai phía điểm cắt.", "Thử dissolve ngắn và so với cắt thẳng."],
            "tags": ["chuyển cảnh", "documentary"], "sources": [{"study_id": study_id, "start": 10, "end": 18}]}


def test_bilingual_retrieval_links_the_relevant_timestamp_and_pages(library):
    sid, _, root = library
    r = learning.library("chuyển cảnh", limit=1)
    assert r["total"] == 1 and r["inventory"] == {"studies": 1, "lessons": 0}
    assert r["items"][0]["id"] == sid
    assert r["items"][0]["moments"][0] == {"at": 12.0, "text": "A dissolve transition suggests a passage of time.", "inspect": [10.0, 18.0]}
    saved = learning.remember(note(sid))
    r = learning.library("chuyen canh", limit=1)
    assert r["total"] == 2 and r["next_offset"] == 1
    assert len(learning.library("chuyen canh", offset=1, limit=1)["items"]) == 1
    detail = learning.library(item_id=saved["id"])
    assert detail["card"]["sources"][0]["source_sha256"] == sha256(library[1])
    assert detail["card"]["revision"] == 1
    assert detail["artifacts"][0]["status"] == "unchanged"
    library[1].write_bytes(b"new version")
    assert learning.library(item_id=saved["id"])["artifacts"][0]["status"] == "changed"
    assert learning.library("quantum-marmalade")["total"] == 0


def test_lesson_idempotence_revision_conflict_and_retirement(library):
    sid, _, _ = library
    original = note(sid)
    first = learning.remember(original)
    assert learning.remember(original)["unchanged"]
    changed = {**original, "avoid": "Avoid dissolves on fast action."}
    with pytest.raises(ValueError, match="revision conflict"):
        learning.remember(changed, first["id"])
    update = learning.remember(changed, first["id"], 1)
    assert update["revision"] == 2
    learning.remember({**changed, "state": "retired"}, first["id"], 2)
    assert learning.library(kind="lesson")["total"] == 0
    assert learning.library(kind="lesson", include_retired=True)["total"] == 1
    assert learning.library(item_id=first["id"], include_retired=True)["card"]["revision"] == 3


def test_source_changes_bad_windows_and_fake_tools_are_rejected(library):
    sid, source, _ = library
    bad = note(sid)
    bad["sources"][0]["end"] = 99
    with pytest.raises(ValueError, match="duration"):
        learning.remember(bad)
    bad = note(sid)
    bad["sources"][0]["study_id"] = "../../private"
    with pytest.raises(ValueError, match="handle"):
        learning.remember(bad)
    bad = note(sid)
    bad["examples"] = [{"tool": "editvideo_magic", "arguments": {}}]
    with pytest.raises(ValueError, match="Unknown example tool"):
        learning.remember(bad, registry={})
    source.write_bytes(b"replaced source")
    with pytest.raises(ValueError, match="changed"):
        learning.remember(note(sid))


def test_registry_validates_examples_without_executing_them(library):
    from editvideo import mcp_server as m
    request = note(library[0])
    request["examples"] = [{"tool": "editvideo_create_silent_project", "arguments": {"profile": "square", "seconds": 12}}]
    before = len(store.list_projects())
    result = m.editvideo_remember_lesson(request)
    assert len(store.list_projects()) == before
    assert m.editvideo_learning_library(item_id=result["id"])["card"]["examples"]
    request["examples"][0]["arguments"]["profile"] = "not-a-profile"
    with pytest.raises(ValueError):
        m.editvideo_remember_lesson(request)
    hits = m.editvideo_discover_tools("học kinh nghiệm", include_schema=True)
    assert any(x["name"] == "editvideo_learning_library" for x in hits["items"])


def test_corrupt_report_is_counted_and_unlinked_transcript_is_not_read(library):
    _, _, root = library
    report = store.read_json(root / "study.json")
    report["transcript"] = None
    store.write_json(root / "study.json", report)
    corrupt = store.DATA / "observations" / ("study-" + "a" * 16) / "study.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{bad", encoding="utf-8")
    r = learning.library("exposure")
    assert r["total"] == 0 and r["skipped_count"] == 1


@pytest.mark.parametrize("change", ["cues", "overlays", "width", "captions", "source", "revision", "added_source"])
def test_sentence_strips_never_reuse_stale_pictures(library, monkeypatch, change):
    pid = store.create_project({"title": "A", "renderer": "remotion", "captions": True})["id"]
    t = {"width": 640, "height": 360, "total_frames": 60, "fps": 30, "shots": [], "layers": [], "cues": [{"text": "old"}], "overlays": []}
    job = {"id": "render", "state": "completed", "kind": "final", "revision": 1}
    folder = store.folder(pid)
    work = folder / "jobs" / "render"
    store.write_json(work / "timeline.json", t)
    store.write_json(work / "source" / "input.json", {"config": store.get_project(pid)["config"]})
    code = folder / "code" / "remotion"
    code.mkdir(parents=True)
    (code / "runtime.js").write_text("original", encoding="utf-8")
    (work / "source" / "runtime.js").write_text("original", encoding="utf-8")
    (work / "final.mp4").write_bytes(b"test identity")
    monkeypatch.setattr(store, "jobs", lambda _: [job])
    assert beatmap._latest_render(pid, t)[0] == work / "final.mp4"
    revised = copy.deepcopy(t)
    if change in ("cues", "overlays"):
        revised[change] = [{"text": "new"}]
    elif change == "width":
        revised["width"] = 1080
    elif change == "source":
        (code / "runtime.js").write_text("custom code changed without revision", encoding="utf-8")
    elif change == "added_source":
        (code / "style.css").write_text("new stylesheet", encoding="utf-8")
    elif change == "captions":
        with store.connection() as db:
            import json
            db.execute("UPDATE projects SET config=? WHERE id=?", (json.dumps({"title": "A", "renderer": "remotion", "captions": False}), pid))
    else:
        job["revision"] = 0
    assert beatmap._latest_render(pid, revised) == (None, None)


def add_study(tmp_path, name, transcript, duration=60, info=None, segments=None, transitions=None):
    """A study report bound to a small file whose hash is its identity (no decoding needed for memory)."""
    folder = tmp_path / name
    folder.mkdir()
    source = folder / "video.mp4"
    source.write_bytes(("reference " + name).encode())
    if info is not None:
        (folder / "video.info.json").write_text(json.dumps(info), encoding="utf-8")
    identity = sha256(source)
    study_id = "study-" + identity[:16]
    root = store.DATA / "observations" / study_id
    report = {"source": str(source), "source_sha256": identity, "duration_s": duration, "transcript": {"path": "t"},
              "segments": segments or []}
    if transitions is not None:
        report["transitions"] = {"events": transitions}
    store.write_json(root / "study.json", report)
    (root / "transcript.txt").write_text(transcript, encoding="utf-8")
    return study_id


def test_accented_vietnamese_never_matches_english_homographs(library, tmp_path):
    noise = add_study(tmp_path, "noise", "[00:01] I can show you what I am doing with this man here.")
    mix = add_study(tmp_path, "mix", "[00:05] Balance the audio levels so dialogue sits above the music.")
    r = learning.library("cân bằng âm lượng", kind="study")
    assert [i["id"] for i in r["items"]] == [mix]
    assert r["items"][0]["moments"][0]["at"] == 5.0
    # Typed without accents the words are ambiguous; the lexicon phrase still ranks the real match first.
    assert learning.library("can bang am luong", kind="study")["items"][0]["id"] == mix
    assert noise not in [i["id"] for i in learning.library("cân bằng âm lượng", kind="study")["items"]]


def test_lexicon_accents_overlaps_and_unmatched_words(library):
    assert learning.query_concepts("này") == []  # "this" is a stop word, not "nảy" (bounce)
    assert "bounce" in learning.query_concepts("nảy")[0]
    assert not any("bounce" in c for c in learning.query_concepts("nay"))  # bare "nay" is ambiguous: accents required
    concepts = learning.query_concepts("thay màn hình điện thoại")
    assert any("§screen replacement" in c for c in concepts) and any("§phone screen" in c for c in concepts)
    assert [c[1:] for c in learning.query_concepts("cắt J và cắt L")] == [["§j cut"], ["§l cut"]]
    r = learning.library("chữ nhảy múa")
    assert r["total"] == 0 and r["unmatched"] and "English" in r["hint"]


def test_reference_title_is_indexed_and_cache_follows_the_sidecar(library, tmp_path):
    info = {"title": "Speed ramping secrets", "channel": "C", "formats": [{"url": "x"}] * 3, "description": "spam"}
    sid = add_study(tmp_path, "ramp", "[00:03] Today we cut a video for social media.", info=info)
    r = learning.library("speed ramping", kind="study")
    assert r["items"][0]["id"] == sid and r["items"][0]["title"] == "Speed ramping secrets" and "description" not in r["items"][0]
    (tmp_path / "ramp" / "video.info.json").write_text(json.dumps({"title": "Colour grading in five minutes, a long title"}), encoding="utf-8")
    assert learning.library("speed ramping", kind="study")["total"] == 0
    assert learning.library("colour grading", kind="study")["items"][0]["id"] == sid


def observed(sid, start=10, end=18):
    return {"study_id": sid, "start": start, "end": end, "observed": "Two scenes overlap for about a second while the sky changes colour."}


def test_levels_are_gated_by_evidence_and_promotion_is_explicit(library, tmp_path):
    sid = library[0]
    plain = learning.remember(note(sid))
    assert plain["level"] == "observation" and "observed" in plain["next_level"]["needs"][0]
    request = {**note(sid), "title": "Seen dissolve", "sources": [observed(sid)]}
    card = learning.remember(request)
    assert card["level"] == "candidate" and card["eligible_level"] == "candidate"
    with pytest.raises(ValueError, match="second independent source"):
        learning.remember({**request, "level": "rule"}, card["id"], card["revision"])
    other = add_study(tmp_path, "other", "[00:20] A slow cross dissolve between two times of day.", segments=[
        {"start": 0, "duration": 21}, {"start": 21, "duration": 4}, {"start": 25, "duration": 35}],
        transitions=[{"type": "dissolve", "start": 20.5, "end": 21.6, "duration_s": 1.1}])
    two = {**request, "sources": [observed(sid), observed(other, 19, 27)], "level": "rule"}
    promoted = learning.remember(two, card["id"], card["revision"])
    assert promoted["level"] == "rule" and promoted["revision"] == 2
    stored = learning.library(item_id=card["id"])
    window = stored["card"]["sources"][1]["measured"]
    assert window["cuts"] == [21, 25] and window["transitions"][0]["type"] == "dissolve"
    assert stored["card"]["sources"][0]["measured"]["transitions"] is None  # older study: says it was not measured
    with pytest.raises(ValueError, match="needs"):
        learning.remember({**two, "level": "standard"}, card["id"], 2)


def test_parameters_and_template_examples(library):
    from editvideo import mcp_server as m
    sid = library[0]
    request = {**note(sid), "sources": [observed(sid)], "parameters": [
        {"name": "dissolve_frames", "range": [24, 48], "unit": "frames@30fps", "provenance": "chosen", "note": "for this demo"}]}
    bad = {**request, "parameters": [{"name": "dissolve_frames", "value": 42, "unit": "frames", "provenance": "measured"}]}
    with pytest.raises(ValueError, match="names the source window"):
        learning.remember(bad)
    bad["parameters"][0]["source"] = 3
    with pytest.raises(ValueError, match="not one of"):
        learning.remember(bad)
    template = {"tool": "editvideo_patch_timeline", "arguments": {"project_id": "{{project_id}}", "base_revision": "{{base_revision}}",
                "operations": [{"op": "update_shot", "shot_id": "{{shot_id}}", "changes": {"transition": {"name": "dissolve", "duration_frames": 36}}}]}}
    saved = m.editvideo_remember_lesson({**request, "examples": [template]})
    assert saved["level"] == "candidate" and "warnings" not in saved
    pinned = {**template, "arguments": {**template["arguments"], "project_id": "a59bd27f-2588-4f98-8b10-f33e9a37e194", "base_revision": 6}}
    warned = m.editvideo_remember_lesson({**request, "title": "Pinned", "examples": [pinned]})
    assert "placeholders" in warned["warnings"][0]
    with pytest.raises(ValueError, match="Unknown placeholder"):
        m.editvideo_remember_lesson({**request, "title": "Typo", "examples": [{**template, "arguments": {"project_id": "{{projet_id}}"}}]})
    assert "levels" in m.editvideo_remember_lesson()  # no arguments: the contract


def rendered(pid, state="completed", kind="final"):
    """A render job record for the project's current revision with the timeline snapshot the worker would copy into its
    folder (job bookkeeping only; nothing is rendered)."""
    from editvideo import agent
    job = store.create_job(pid, kind)
    work = store.folder(pid) / "jobs" / job["id"]
    store.write_json(work / "timeline.json", agent.read(pid)["timeline"])
    store.write_json(work / "output.json", {"video": "final.mp4", "revision": job["revision"]})
    store.job_progress(job["id"], state, 1, "test")
    return job["id"]


def with_dissolve(pid):
    """Split the silent carrier into two shots joined by a dissolve, so the audit inventory shows the technique."""
    from editvideo import agent, mcp_server as m
    t = agent.read(pid)["timeline"]
    base = t["shots"][0]
    half = t["total_frames"] // 2
    t["shots"] = [{**base, "id": "a", "start_frame": 0, "end_frame": half, "source_start": 0},
                  {**base, "id": "b", "start_frame": half, "end_frame": t["total_frames"], "source_start": 0,
                   "transition": {"name": "dissolve", "duration_frames": 12, "mode": "live"}}]
    m.editvideo_patch_timeline(pid, store.get_project(pid)["revision"], [{"op": "replace_timeline", "timeline": t}])
    return store.get_project(pid)["revision"]


def test_outcomes_need_a_render_and_the_technique_before_they_count(library):
    from editvideo import agent, agent_interface
    sid = library[0]
    check = {"uses": ["dissolve"], "codes": ["diacritic_collision"], "expect": "absent"}
    request = {**note(sid), "sources": [observed(sid)], "check": check}
    for bad, why in [({**check, "codes": ["no_such_code"]}, "never fire"), ({**check, "uses": []}, "uses"),
                     ({**check, "uses": ["dissolvee"]}, "not transition"), ({**check, "uses": ["null"]}, "not transition"),
                     ({**check, "codes": ["reading_hold"]}, "only as info"),
                     ({**check, "codes": ["static_ending"]}, "never"),  # a motion-audit code, not audit_timeline's
                     ({**check, "uses": ["iris"]}, "not named")]:  # a technique the card never mentions
        with pytest.raises(ValueError, match=why):
            learning.remember({**request, "check": bad})
    for code in ("reading_load", "soft_upscale", "narration_unclear"):  # conditional levels and the narration check are known
        assert code in learning.audit_registry()
    card = learning.remember(request)
    empty, a, b = (agent.create_silent("square", 60, "remotion", f"apply {i}")["id"] for i in range(3))
    rev = lambda pid: store.get_project(pid)["revision"]
    log = lambda pid, kept=True, job=None: learning.remember(lesson_id=card["id"], outcome={
        "project_id": pid, "revision": rev(pid), "kept": kept, "note": "Dissolve between two plates read clearly.", **({"job_id": job} if job else {})})
    with pytest.raises(ValueError, match="Unknown project"):
        learning.remember(lesson_id=card["id"], outcome={"project_id": "00000000-0000-4000-8000-000000000000", "revision": 1, "kept": True, "note": "x"})
    with pytest.raises(ValueError, match="cannot be later"):
        learning.remember(lesson_id=card["id"], outcome={"project_id": empty, "revision": rev(empty) + 1, "kept": True, "note": "x"})
    with pytest.raises(ValueError, match="either"):
        learning.remember(request, card["id"], outcome={"project_id": empty, "revision": 1, "kept": True, "note": "x"})
    # The caller's word alone is logged but opens nothing; neither does a render whose check shows the technique missing.
    assert log(empty)["unverified"]
    with pytest.raises(ValueError, match="completed render"):
        log(empty, job=rendered(empty, "failed"))
    plain = log(empty, job=rendered(empty))
    assert plain["recorded"]["check"]["uses_missing"] == ["dissolve"] and plain["unverified"] and plain["eligible_level"] == "candidate"
    with pytest.raises(ValueError, match="one verified use"):
        learning.remember({**request, "level": "rule"}, card["id"], 1)
    # Log lines are not evidence: a forged pass naming a real blank render is re-run on that render's timeline.
    blank_job = rendered(agent.create_silent("square", 30, "remotion", "forged")["id"])
    forged_pid = store.get_job(blank_job)["project_id"]
    with (store.DATA / "learning" / (card["id"] + ".outcomes.jsonl")).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"project_id": forged_pid, "revision": rev(forged_pid), "kept": True, "job": {"id": blank_job},
                            "check": {"passed": True}, "check_key": learning._check_key(check)}) + "\n")
        f.write('{"project_id": "typed", "revision": 1, "kept": true, "job": "yes"}\n')
    assert learning.library(item_id=card["id"])["applications"]["verified"] == 0
    for pid in (a, b):
        with_dissolve(pid)
        assert "unverified" not in log(pid, job=rendered(pid))
    assert learning.remember({**request, "level": "standard"}, card["id"], 1)["level"] == "standard"
    # Uses are re-verified against the CURRENT check on the rendered timelines: a check those renders fail drops the
    # card back, one they still satisfy keeps it (recorded results are never read back as evidence).
    other = {**request, "steps": [*request["steps"], "Or try a wipe_left between the plates."], "check": {**check, "uses": ["wipe_left"]}}
    with pytest.raises(ValueError, match="verified uses"):
        learning.remember({**other, "level": "standard"}, card["id"], 2)
    stored = learning.library(item_id=card["id"])["card"]
    assert learning._applications(card["id"], {**stored, "check": {**check, "codes": ["text_boxes_overlap"]}})["verified"] == 2
    # ...and its note or list order is not part of what it tests.
    assert learning._check_key({**check, "note": "x", "codes": list(reversed(check["codes"]))}) == learning._check_key(check)
    # Later reverted uses demote what readers see, keep the stored level visible, and never block retiring.
    for pid in (empty, a, b, forged_pid):
        log(pid, kept=False)
    assert learning.remember({**request, "level": "standard"}, card["id"], 2)["unchanged"]  # a retry is a no-op
    listed = learning.library("dissolve", kind="lesson")["items"][0]
    assert listed["level"] == "candidate" and listed["contested"] and listed["applications"]["reverted"] == 4
    detail = learning.library(item_id=card["id"])
    assert detail["stored_level"] == "standard" and len(detail["recent_outcomes"]) == 5
    boot = agent_interface.bootstrap("dựng chuyển cảnh thời gian cho phim tài liệu")
    assert boot["lessons"]["items"][0] == {"id": card["id"], "title": request["title"], "level": "candidate", "contested": True}
    retired = learning.remember({**request, "level": "standard", "state": "retired"}, card["id"], 2)
    assert retired["revision"] == 3 and learning.library(kind="lesson")["total"] == 0
    assert "lessons" not in agent_interface.bootstrap("dựng chuyển cảnh thời gian cho phim tài liệu")
    # Retiring never stores a level the evidence does not support, so re-activating cannot promote.
    back = learning.remember({**request, "state": "active"}, card["id"], 3)
    assert back["level"] == "candidate" and "stored_level" not in back


def test_cards_without_a_check_never_rule_on_a_render_and_shot_effects_count(library):
    from editvideo import agent
    sid = library[0]
    request = {**note(sid), "sources": [observed(sid)]}
    card = learning.remember(request)
    pid = agent.create_silent("square", 30, "remotion", "no check")["id"]
    r = learning.remember(lesson_id=card["id"], outcome={"project_id": pid, "revision": store.get_project(pid)["revision"], "kept": True,
                                                         "note": "Rendered, but nothing measures what the lesson teaches.", "job_id": rendered(pid)})
    assert "no usable check" in r["unverified"] and r["eligible_level"] == "candidate"
    with pytest.raises(ValueError, match="one verified use"):
        learning.remember({**request, "level": "rule"}, card["id"], 1)
    t = agent.read(pid)["timeline"]
    t["shots"][0]["effects"] = [{"name": "letterbox", "start_frame": 0, "end_frame": 30}]
    check = {"uses": ["letterbox"], "codes": ["diacritic_collision"], "expect": "absent"}
    assert learning._run_check(check, pid, t)["passed"] is True
    # A one-frame effect or a transparent layer does not show a technique; an empty snapshot is not the plan.
    t["shots"][0]["effects"] = [{"name": "letterbox", "start_frame": 0, "end_frame": 1}]
    t["layers"] = [{"id": "s", "kind": "shape", "start_frame": 0, "end_frame": 30, "opacity": 0}]
    assert learning.visible_techniques(t) == set()
    assert learning._run_check(check, pid, {})["passed"] is None


def test_damaged_or_changed_snapshots_void_a_use_without_breaking_listings(library):
    from editvideo import agent, agent_interface
    sid = library[0]
    request = {**note(sid), "sources": [observed(sid)], "check": {"uses": ["dissolve"], "codes": ["diacritic_collision"], "expect": "absent"}}
    card = learning.remember(request)
    pid = agent.create_silent("square", 60, "remotion", "snapshot")["id"]
    with_dissolve(pid)
    job = rendered(pid)
    r = learning.remember(lesson_id=card["id"], outcome={"project_id": pid, "revision": store.get_project(pid)["revision"], "kept": True,
                                                         "note": "Dissolve rendered and read clearly.", "job_id": job})
    assert "unverified" not in r and r["applications"]["verified"] == 1
    snap = store.folder(pid) / "jobs" / job / "timeline.json"
    snap.write_text('{"shots": [', encoding="utf-8")  # torn after the fact
    assert learning.library(item_id=card["id"])["applications"]["verified"] == 0
    assert learning.library("dissolve", kind="lesson")["total"] == 1
    assert agent_interface.bootstrap("chuyển cảnh cho phim tài liệu")["lessons"]["items"][0]["id"] == card["id"]


def test_bootstrap_needs_a_craft_match_and_damaged_cards_are_skipped(library):
    from editvideo import agent_interface
    sid = library[0]
    card = learning.remember({**note(sid), "steps": ["Hold each plate 30 frames before the overlap; make a video of it."]})
    assert learning.related_lessons("make a 30 second video about my bakery") == []
    assert learning.related_lessons("make a video about my cat") == []
    assert learning.related_lessons("chuyển cảnh cho phim tài liệu")[0]["id"] == card["id"]
    log = store.DATA / "learning" / (card["id"] + ".outcomes.jsonl")
    log.write_text('{"project_id": "p", "revision": 1, "kept": true}\n{"torn', encoding="utf-8")
    assert learning.library(item_id=card["id"])["recent_outcomes"] == [{"project_id": "p", "revision": 1, "kept": True}]
    good = store.read_json(store.DATA / "learning" / (card["id"] + ".json"))
    damaged = [{"level": "legendary"}, {"sources": [{**good["sources"][0], "observed": 5}]},
               {"examples": [{"tool": "editvideo_x", "arguments": 7}]}, {"demonstration": {"path": "x.mp4"}}]
    for i, change in enumerate(damaged):
        store.write_json(store.DATA / "learning" / (f"lesson-{i:020d}.json"), {**good, **change})
    r = learning.library(kind="lesson")
    assert r["total"] == 1 and r["skipped_count"] == 4 and all("valid lesson" in s["error"] for s in r["skipped"])
    assert agent_interface.bootstrap("chuyển cảnh cho phim tài liệu")["lessons"]["items"][0]["id"] == card["id"]


def test_old_cards_resend_unchanged_and_tone_placement_is_one_spelling(library):
    sid = library[0]
    saved = learning.remember(note(sid))
    path = store.DATA / "learning" / (saved["id"] + ".json")
    old = store.read_json(path)
    for key in ("parameters", "check", "level"):
        old.pop(key)
    for s in old["sources"]:
        s.pop("measured")
    store.write_json(path, old)  # as written before cards had levels
    again = learning.remember(note(sid))
    assert again["unchanged"] and again["level"] == "observation"
    assert learning.query_concepts("đồ hoạ thông tin") == learning.query_concepts("đồ họa thông tin")
    assert learning.query_concepts("khoá màu") == learning.query_concepts("khóa màu")
    assert not any("explosion" in c for c in learning.query_concepts("no music"))
    learning.remember({**note(sid), "title": "Hoà tan hai cảnh", "steps": ["Hoà tan khi hai cảnh cùng địa điểm."]})
    assert learning.library("hòa tan", kind="lesson")["items"][0]["title"] == "Hoà tan hai cảnh"
    r = learning.library("the a of 30")
    assert r["total"] == 0 and "stop words" in r["hint"]


def test_study_reads_are_lean_and_segments_page(library, tmp_path):
    segs = [{"start": i * 2.0, "end": i * 2.0 + 2, "duration": 2, "inspect_at": [i * 2.0 + 1]} for i in range(30)]
    sid = add_study(tmp_path, "lean", "[00:05] A dissolve between two times of day.", segments=segs)
    card = learning.library(item_id=sid)
    assert "segments" not in card["card"] and card["segments_total"] == 30 and "view=segments" in card["views"]
    page = learning.library(item_id=sid, view="segments", offset=25, limit=100)["segments"]
    assert page["items"][0] == [50.0, 52.0] and len(page["items"]) == 5 and page["next_offset"] is None
    with pytest.raises(ValueError, match="item_id"):
        learning.library(view="segments")
    with pytest.raises(ValueError, match="applies to a study"):
        learning.library(item_id=learning.remember(note(sid))["id"], view="candidates")


def test_worklist_ranks_undistilled_windows_with_their_evidence(library, tmp_path):
    lines = "\n".join(["[00:02] Welcome back to the channel.", "[00:30] Now hit enter to apply it.",
                        "[01:00] A slow dissolve shows that time has passed.", "[01:04] Keep the dissolve about a second long.",
                        "[02:00] Next a match cut on the shape of the moon.", "[03:00] Thanks for watching."])
    segs = [{"start": float(x), "end": float(x) + 1, "duration": 1} for x in range(0, 180, 1)]
    a = add_study(tmp_path, "teach", lines, duration=200, segments=segs, info={"title": "Transitions explained"},
                  transitions=[{"type": "dissolve", "start": 61.0, "end": 62.2}])
    store.write_json(store.DATA / "observations" / a / "events.json", {"events": [{"t": 61.5, "kind": "overlay_pop"}]})
    report = store.read_json(store.DATA / "observations" / a / "study.json")
    store.write_json(store.DATA / "observations" / a / "study.json", {**report, "sheet_samples": [[60.0, False], [121.0, True]]})
    b = add_study(tmp_path, "other", "[00:10] We talk about hitting deadlines.", duration=60)
    w = learning.library(view="candidates")
    item = next(i for i in w["items"] if i["id"] == a)
    assert item["title"] == "Transitions explained" and b not in [i["id"] for i in w["items"]] and w["without_windows"] == 1
    best = item["windows"][0]
    assert best["start"] == 56.0 and best["mentions"] == 2 and best["terms"][0] == "dissolve"
    assert best["transitions"] == [{"type": "dissolve", "at": 61.0}] and best["events"] == {"overlay_pop": 1}
    assert all("hit" not in x["terms"] for x in item["windows"])  # "hit enter" is a UI instruction
    assert "inspect_window" in w["inspect"]
    match = learning.library(item_id=a, view="candidates", query="match cut")
    assert match["windows"][0]["start"] == 116.0 and match["windows"][0]["query_hits"] == 2
    assert match["windows"][0]["ui_on_screen"] is True and match["windows_total"] == 1
    page = learning.library(item_id=a, view="candidates", limit=1, offset=1)
    assert page["windows"][0]["start"] == 116.0 and page["next_offset"] is None
    assert "hint" in learning.library(item_id=a, view="candidates", query="kerning")
    # A lesson on the dissolve window removes that window and the study from the to-do list.
    learning.remember({**note(a), "sources": [{"study_id": a, "start": 58, "end": 70}]})
    w = learning.library(view="candidates")
    assert a not in [i["id"] for i in w["items"]] and w["already_distilled"] == 1 and w["without_windows"] == 1
    windows = learning.library(item_id=a, view="candidates")["windows"]
    assert windows and all(x["end"] <= 58 or x["start"] >= 70 for x in windows)
    q = learning.library(view="candidates", query="tan cảnh")  # only undistilled studies that match are listed
    assert [i["id"] for i in q["items"]] == [library[0]]
    with pytest.raises(ValueError, match="kind=all or kind=study"):
        learning.library(view="candidates", kind="lesson")


def test_windows_fit_the_video_cover_every_mention_and_survive_damage(library, tmp_path):
    lines = "\n".join(f"[{m:02d}:{s:02d}] Now a dissolve and a match cut." for m, s in ((5, 9), (5, 12), (5, 16), (5, 20), (5, 24), (5, 28)))
    sid = add_study(tmp_path, "edge", lines, duration=329.58, transitions=[{"type": None, "start": None, "end": 3}])
    windows = learning.library(item_id=sid, view="candidates", limit=20)["windows"]
    assert windows and all(w["end"] <= 329.58 and w["end"] - w["start"] <= 30 for w in windows)
    assert sum(w["mentions"] for w in windows) == 6  # each mention lies in exactly one window
    store.write_json(store.DATA / "observations" / sid / "events.json", {"events": 5})
    assert learning.library(item_id=sid, view="candidates")["windows"]
    report = store.read_json(store.DATA / "observations" / sid / "study.json")
    store.write_json(store.DATA / "observations" / sid / "study.json", {**report, "segments": [5, None], "duration_s": float("nan")})
    assert learning.library(view="candidates")["total"] >= 1  # the damaged study drops out, the rest still list


def test_titles_come_from_a_reference_set_index_without_sidecars(library, tmp_path):
    sid = add_study(tmp_path, "abc", "[00:03] Today we cut a video.")
    (tmp_path / "index.json").write_text(json.dumps([{"id": "abc", "title": "Speed ramping secrets", "channel": "C", "minutes": 1.0}]),
                                         encoding="utf-8")
    assert learning.library("speed ramping", kind="study")["items"][0]["id"] == sid
    assert learning.library(item_id=sid)["card"]["reference"]["title"] == "Speed ramping secrets"
    # A row that states another length (or names another study) is not this video's.
    (tmp_path / "index.json").write_text(json.dumps({"abc": {"title": "Wrong video", "duration_s": 600}}), encoding="utf-8")
    assert "reference" not in learning.library(item_id=sid)["card"]


def test_windows_stay_within_30_s_after_a_fractional_lesson_end(library, tmp_path):
    lines = "\n".join(f"[00:{x:02d}] A dissolve, then a match cut." for x in range(3, 40, 2))
    sid = add_study(tmp_path, "frac", lines, duration=90)
    learning.remember({**note(sid), "sources": [{"study_id": sid, "start": 0, "end": 2.2}]})
    windows = learning.library(item_id=sid, view="candidates", limit=20)["windows"]
    assert windows and all(round(w["end"] - w["start"], 6) <= 30 and w["start"] >= 2.2 for w in windows)
    unmeasured = learning.library(item_id=sid, view="candidates")["unmeasured"]
    assert "transitions" in unmeasured and "edit events" in unmeasured
