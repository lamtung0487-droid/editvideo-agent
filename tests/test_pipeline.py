import math
import wave
from pathlib import Path
import pytest
from pydantic import ValidationError
from editvideo import store
from editvideo.audio import parse_srt, restore_display_text, group_words
from editvideo.models import ProjectInput, Timeline, Shot
from editvideo.media import FFMPEG, command, register
from editvideo.planner import plan, validate_sources, make_beats
from editvideo.jobs import Worker
from PIL import Image


def test_narration_whitespace_does_not_discard_measured_timing(workspace,monkeypatch):
    from editvideo import audio
    async def voice(text,config,target,cancelled):
        target.write_bytes(b'fixture');return [{'start':.1,'end':.4,'text':'Xin'},{'start':.5,'end':.9,'text':'chào'}]
    def normalize(source,target,cancelled,log):
        with wave.open(str(target),'wb') as f:f.setparams((1,2,48000,0,'NONE','not compressed'));f.writeframes(bytes(48000*2))
    monkeypatch.setattr(audio,'edge_voice',voice);monkeypatch.setattr(audio,'normalize_audio',normalize)
    p=store.create_project(ProjectInput(script='Xin\nchào.',spoken_text='Xin chào.').model_dump());work=workspace/'audio';work.mkdir()
    _,cues,method=audio.prepare_audio(p['id'],p['config'],work,lambda:False,lambda *args:None)
    assert method=='tts_word_boundaries' and cues==[{'start':.1,'end':.9,'text':'Xin chào.'}]


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DATA",tmp_path)
    for key in ("EDITVIDEO_LLM_API_KEY","EDITVIDEO_LLM_BASE_URL","EDITVIDEO_LLM_MODEL"):
        monkeypatch.delenv(key,raising=False)
    store.initialize()
    return tmp_path


def fixture_project():
    config=ProjectInput(title="Kiểm thử quang hợp",script="Cây xanh biến ánh sáng thành năng lượng.").model_dump()
    project=store.create_project(config);pid=project["id"]
    folder=store.folder(pid)/"assets";folder.mkdir()
    image=folder/"image.png";Image.new("RGB",(720,1280),"#2f704b").save(image)
    register(pid,image,"Cây xanh","cây xanh ánh sáng năng lượng")
    voice=folder/"voice.wav"
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=2.43",voice])
    a=register(pid,voice,"Test signal — không phải giọng đọc","kiểm thử")
    music=folder/"music.wav"
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i","sine=frequency=130:sample_rate=48000:duration=1",music])
    m=register(pid,music,"Music test","nhạc")
    config["narration_id"]=a["id"];config["music_id"]=m["id"]
    store.update_project(pid,config)
    return pid


def test_srt_and_punctuation():
    cues=parse_srt("1\n00:00:00,200 --> 00:00:01,000\nCây xanh.\n\n2\n00:00:01,100 --> 00:00:02,000\nÁnh sáng!")
    assert cues[0]["text"]=="Cây xanh."
    restored=restore_display_text([{"start":0,"end":.3,"text":"Cây"},{"start":.3,"end":.6,"text":"xanh"}],"Cây xanh.")
    assert group_words(restored)[0]["text"]=="Cây xanh."
    assert restore_display_text(restored,"Cây đỏ.") is None
    with pytest.raises(ValueError):
        parse_srt("1\n00:00:00,000 --> 00:00:02,000\nA\n\n2\n00:00:01,000 --> 00:00:03,000\nB")
    tokens=["Cây","dùng","ánh","sáng","tạo","chất","hữu","cơ."]
    grouped=group_words([{"text":t,"start":i*.2,"end":(i+1)*.2} for i,t in enumerate(tokens)],max_words=2)
    assert any("ánh sáng" in c["text"] for c in grouped)
    assert any("chất hữu cơ." in c["text"] for c in grouped)


def test_display_numerals_keep_measured_tts_boundaries():
    spoken=[{"text":t,"start":i*.3,"end":i*.3+.25} for i,t in enumerate("quy tắc hai mươi hai mươi hai mươi cứ mỗi hai mươi phút khoảng sáu mét".split())]
    mapped=restore_display_text(spoken,"Quy tắc 20-20-20. Cứ mỗi 20 phút, khoảng 6 mét.")
    assert [w["text"] for w in mapped]==["Quy","tắc","20-20-20.","Cứ","mỗi","20","phút,","khoảng","6","mét."]
    assert (mapped[2]["start"],mapped[2]["end"])==(spoken[2]["start"],spoken[7]["end"])
    assert (mapped[8]["start"],mapped[8]["end"])==(spoken[14]["start"],spoken[14]["end"])
    assert restore_display_text(spoken,"Một câu hoàn toàn khác.") is None
    cues=group_words(mapped,max_words=7)
    assert cues[0]["text"]=="Quy tắc 20-20-20." and cues[0]["end"]==spoken[7]["end"]


def test_caption_pages_follow_clauses_without_orphans():
    tokens="Mắt mỏi, khô và nhòe là dấu hiệu quen thuộc.".split()
    words=[{"text":t,"start":i*.25,"end":i*.25+.22} for i,t in enumerate(tokens)]
    assert [c["text"] for c in group_words(words,max_words=7)]==["Mắt mỏi, khô và nhòe","là dấu hiệu quen thuộc."]


def test_beat_cut_sits_inside_measured_pause():
    cues=[{"start":0,"end":2.4,"text":"Câu thứ nhất đủ dài."},{"start":3.2,"end":5,"text":"Câu thứ hai."}]
    beats=make_beats(cues,150,"energetic")
    assert beats[0]["end_frame"]==84 and beats[1]["start_frame"]==84


def test_meaningful_beat_does_not_orphan_sentence():
    cues=[{"start":0,"end":5.8,"text":"Cây sử dụng ánh sáng để tạo ra chất"},
          {"start":5.9,"end":6.6,"text":"hữu cơ."},
          {"start":6.7,"end":9,"text":"Ô-xy được giải phóng."}]
    beats=make_beats(cues,270,"documentary")
    assert len(beats)==2
    assert beats[0]['text'].endswith('chất hữu cơ.')


def test_voice_first_integer_frames_and_unrelated_asset(workspace):
    pid=fixture_project();c=store.get_project(pid)["config"]
    voice=Path(store.find_asset(pid,c["narration_id"])["path"])
    timeline,_=plan(c,voice,[{"start":0,"end":2.43,"text":c["script"]}],"supplied_srt",store.assets(pid),lambda *a:None)
    assert timeline.total_frames==73
    assert timeline.shots[0].asset_id=="image"
    timeline2,_=plan(c,voice,[{"start":0,"end":2.43,"text":"Lịch sử của máy bay"}],"supplied_srt",store.assets(pid),lambda *a:None)
    assert timeline2.shots[0].asset_id is None
    broken=timeline.model_dump();broken["shots"][0]["start_frame"]=1
    with pytest.raises(ValidationError):Timeline.model_validate(broken)


def test_job_duplicate_cancel_and_revision(workspace):
    pid=fixture_project();j=store.create_job(pid,"plan")
    with pytest.raises(ValueError):store.create_job(pid,"plan")
    with pytest.raises(ValueError):store.update_project(pid,store.get_project(pid)["config"])
    store.cancel(j["id"])
    Worker().run(j["id"])
    assert store.get_job(j["id"])["state"]=="cancelled"
    store.update_project(pid,store.get_project(pid)["config"])
    j=store.create_job(pid,"plan");Worker().run(j["id"])
    assert store.get_job(j["id"])["state"]=="completed"
    store.update_project(pid,{**store.get_project(pid)["config"],"script":"Đổi lời đọc"})
    render_job=store.create_job(pid,"preview");Worker().run(render_job["id"])
    assert store.get_job(render_job["id"])["state"]=="failed"
    assert "đã đổi" in store.get_job(render_job["id"])["error"]


def test_mix_only_changes_keep_locked_audio_and_timeline(workspace):
    pid=fixture_project()
    j=store.create_job(pid,"plan");Worker().run(j["id"])
    path=store.folder(pid)/"plan"/"plan-meta.json"
    original=store.read_json(path)
    config={**store.get_project(pid)["config"],"music_volume":.22,"title":"Tên mới"}
    project=store.update_project(pid,config)
    after=store.read_json(path)
    assert after['revision']==project['revision']
    assert after['audio_hash']==original['audio_hash']
    assert after['timeline_hash']==original['timeline_hash']


def test_actual_render_captions_music_and_delivery(workspace):
    pid=fixture_project();worker=Worker()
    for kind in ("plan","preview"):
        j=store.create_job(pid,kind);worker.run(j["id"])
        assert store.get_job(j["id"])["state"]=="completed",store.get_job(j["id"])["error"]
    path=store.folder(pid)/"jobs"/j["id"]
    technical=store.read_json(path/"technical.json")
    assert technical["decoded"] and technical["frames"]==73
    assert technical["width"]==360 and technical["height"]==640
    assert (path/"storyboard.jpg").is_file()
    assert "Cây xanh" in (path/"captions.srt").read_text(encoding="utf-8")
    # Intermediates are removed once the muxed output exists.
    assert not any((path/n).exists() for n in ("visual.mp4","mixed.wav","base-mix.wav")) and not list(path.glob("shot-*.mp4"))


def test_short_video_source_rejected(workspace):
    pid=fixture_project();project=store.get_project(pid)
    j=store.create_job(pid,"plan");Worker().run(j["id"])
    t=Timeline.model_validate(store.read_json(store.folder(pid)/"plan"/"timeline.json"))
    t.shots[0].asset_id="too-short"
    with pytest.raises(ValueError,match="không đủ dài"):
        validate_sources(pid,t,[{"id":"too-short","kind":"video","duration":.5}])


def test_lean_source_package_and_engine_env(workspace,monkeypatch):
    import json,zipfile
    from editvideo.code_engine import package,engine_env
    pid=fixture_project()
    work=workspace/"job";snap=work/"source"
    (snap/"public"/"fonts").mkdir(parents=True)
    (snap/"index.tsx").write_text("export {}",encoding="utf-8")
    (snap/"public"/"clip.mp4").write_bytes(b"\0"*4096)
    (snap/"public"/"fonts"/"a.woff2").write_bytes(b"font")
    (work/"timeline.json").write_text("{}",encoding="utf-8")
    with zipfile.ZipFile(package(pid,work,snap)) as z:
        names=set(z.namelist());manifest=json.loads(z.read("media-manifest.json"))
    assert {"source/index.tsx","source/public/fonts/a.woff2","timeline.json"}<=names and "source/public/clip.mp4" not in names
    assert manifest["media_included"] is False and len(manifest["assets"])==len(store.assets(pid))
    assert all(a["sha256"] for a in manifest["assets"])
    with zipfile.ZipFile(package(pid,work,snap,include_media=True)) as z:
        assert z.getinfo("source/public/clip.mp4").compress_type==zipfile.ZIP_STORED
    monkeypatch.setenv("EDITVIDEO_GL","swangle");monkeypatch.setenv("EDITVIDEO_CHUNK_FRAMES","120");monkeypatch.setenv("EDITVIDEO_LLM_API_KEY","secret")
    env=engine_env(pid)
    assert env["EDITVIDEO_GL"]=="swangle" and env["EDITVIDEO_CHUNK_FRAMES"]=="120" and "EDITVIDEO_LLM_API_KEY" not in env
    assert env["EDITVIDEO_BUNDLE_CACHE"].endswith(pid) and int(env.get("EDITVIDEO_MEM_AVAILABLE_MB","1"))>0
