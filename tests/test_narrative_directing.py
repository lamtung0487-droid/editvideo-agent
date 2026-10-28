"""Meaning survives compact context; stale plans cannot silently edit a changed film."""
import copy
import json
from pathlib import Path
import pytest
from editvideo import agent,store,narrative,directing


@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path/'store');store.initialize(recover=False)
    return agent.read(agent.create_silent('landscape',900,'remotion','Meaning test')['id'])


def binding(p,**extra):
    return {'project_id':p['id'],'base_revision':p['revision'],'message':'Explain a change using a named record.',
            'source':'Authored script test','beats':[{'id':'b1','start_frame':0,'end_frame':300,
            'text':'Một quyết định đã thay đổi cuộc sống.','purpose':'Show the supported consequence.','role':'consequence',
            'timing':'authored_window','shot_ids':[p['timeline']['shots'][0]['id']]}],**extra}


def decision(p,technique='chapter_route'):
    items={'chapter_route':[{'label':'1945–1954','detail':'Kháng chiến chống Pháp'},{'label':'1954–1975','detail':'Hai miền · chiến tranh','at':2}],
           'quantity_focus':[{'label':'Tỷ trọng ngân sách','value':'37%','percent':37,'detail':'Theo nguồn được ghi rõ.'}],
           'evidence_compare':[{'label':'Hồ sơ thứ nhất','detail':'Một ghi chép có ngày tháng.','source':'Hồ sơ A'},
                               {'label':'Hồ sơ thứ hai','detail':'Một ghi chép khác được đối chiếu.','source':'Hồ sơ B','at':2}]}
    return {'id':'example','technique':technique,'base_revision':p['revision'],'heading':'HIỂU MỘT BƯỚC NGOẶT',
            'viewer_question':'Điều gì đã thay đổi?','rationale':'Cho người xem đọc từng bằng chứng.','items':items[technique]}


def test_compact_context_retains_authored_meaning_and_never_invents_word_times(project):
    from editvideo import workbench,mcp_server,beatmap
    narrative.bind(binding(project))
    c=workbench.scene(project['id'],0,8)
    assert c['meaning']['beats'][0]['text']=='Một quyết định đã thay đổi cuộc sống.'
    assert c['meaning']['beats'][0]['purpose'] and c['craft'][0]['id']=='quantity_focus'
    n=mcp_server.editvideo_read_narration(project['id'])
    assert n['total_words']==0 and n['meaning']['total']==1
    assert beatmap.beat_map(project['id'])['sentences']==1
    assert 'no word alignment' in beatmap.beat_map(project['id'])['timing']


def test_binding_checks_real_ids_bounds_and_separate_revision(project):
    q=binding(project);q['beats'][0]['audio_ids']=['imaginary']
    with pytest.raises(ValueError,match='missing'):narrative.bind(q)
    q=binding(project);q['beats'][0]['timing']='clip_bounds'
    with pytest.raises(ValueError,match='actual audio'):narrative.bind(q)
    r=narrative.bind(binding(project));assert Path(r['version']).exists()
    with pytest.raises(ValueError,match='binding conflict'):narrative.bind(binding(project))
    assert store.get_project(project['id'])['revision']==project['revision']


def test_layer_changes_keep_meaning_but_media_timing_changes_mark_it_stale(project):
    narrative.bind(binding(project))
    t=copy.deepcopy(project['timeline']);t['layers'].append({'id':'style-only'})
    t['shots'][0].update(source_start=0,playback_rate=1)
    assert narrative.document(project['id'],t)[1]=='ready'
    t['shots'][0]['playback_rate']=2
    assert narrative.context(project['id'],t,0,8)['status']=='stale_media_or_timing'
    assert not narrative.context(project['id'],t,0,8)['beats']


@pytest.mark.parametrize('technique',['chapter_route','quantity_focus','evidence_compare'])
def test_scene_compilers_create_real_valid_layers_and_fit_bundled_glyphs(project,technique):
    r=directing.compile_scene(project,0,10,decision(project,technique))
    assert 1<len(r['operations'])<=100 and Path(r['path']).exists()
    assert all(not m['fit']['missing_glyphs'] for m in r['measurements'])
    assert agent.read(project['id'])['timeline']==project['timeline'] # dry run
    from editvideo.mcp_server import editvideo_patch_timeline
    editvideo_patch_timeline(project['id'],project['revision'],direction_plan=r['id'])
    assert agent.read(project['id'])['timeline']['layers']
    with pytest.raises(ValueError,match='stale'):
        editvideo_patch_timeline(project['id'],project['revision'],direction_plan=r['id'])


def test_long_text_does_not_silently_overflow_or_delete_a_longer_layer(project):
    q=decision(project,'evidence_compare');q['items'][0]['detail']='too long '*100
    with pytest.raises(ValueError):directing.compile_scene(project,0,10,q)
    q=decision(project);q['replace_layer_ids']=['missing']
    with pytest.raises(ValueError,match='Replacement'):directing.compile_scene(project,0,10,q)


def test_sampling_has_coverage_and_evidence_is_cached_without_rehash(project,tmp_path,monkeypatch):
    from editvideo import media
    path=tmp_path/'sample.mp4'
    media.command([media.FFMPEG,'-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=4','-f','lavfi','-i',
                   'sine=frequency=440:sample_rate=16000:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',path])
    first=directing.evidence(path,project['timeline'],0,4,4,320,True)
    assert first['audio_window']==[0,4]
    assert len(first['times'])==4 and first['times'][0]==0 and first['times'][-1]==119/30
    assert Path(first['audio']).is_file() and Path(first['sheet']).is_file()
    monkeypatch.setattr(media,'sha256',lambda _:pytest.fail('cached evidence should not rehash video'))
    assert directing.evidence(path,project['timeline'],0,4,4,320,True)['cached']
    t=copy.deepcopy(project['timeline']);t['shots']=[{'start_frame':0},{'start_frame':60}]
    assert {59,62}<=set(directing.sample_frames(t,0,4,4))


def test_portrait_layouts_are_checked_against_real_font_metrics(project):
    p=copy.deepcopy(project);p['timeline'].update(width=1080,height=1920)
    for technique in ('chapter_route','evidence_compare','quantity_focus'):
        r=directing.compile_scene(p,0,10,decision(p,technique))
        assert r['measurements'] and all(m['font_size']>=18 for m in r['measurements'])
    q=decision(p,'quantity_focus');q['footage_asset_id']=p['timeline']['shots'][0]['asset_id']
    r=directing.compile_scene(p,0,10,q)
    video=next(o['layer'] for o in r['operations'] if o['layer']['id']=='example-footage')
    assert video['y']==.67 and video['width']==.89


def test_corrupt_optional_meaning_does_not_break_the_existing_scene_reader(project):
    narrative.path(project['id']).write_text('{broken',encoding='utf8')
    from editvideo import workbench
    assert workbench.scene(project['id'],0,3)['meaning']['status']=='unreadable_binding'


def test_reference_picture_is_invalidated_by_custom_code_without_project_revision(project):
    from editvideo.media import safe_asset_path
    reference=safe_asset_path(project['id'],project['timeline']['shots'][0]['asset_id'])
    narrative.bind(binding(project,reference_render=str(reference)))
    assert narrative.context(project['id'],project['timeline'],0,3)['reference_render']['matches_current_picture']
    folder=store.folder(project['id'])/'code/remotion';folder.mkdir(parents=True,exist_ok=True)
    (folder/'custom.js').write_text('changed pixels',encoding='utf8')
    assert not narrative.context(project['id'],project['timeline'],0,3)['reference_render']['matches_current_picture']


def test_native_word_timing_survives_when_on_screen_captions_are_disabled(project):
    store.write_json(store.folder(project['id'])/'plan/words.json',{'method':'actual_tts_words','words':[
        {'text':'Một','start':0,'end':.3},{'text':'câu.','start':.3,'end':.8}]})
    c=narrative.context(project['id'],project['timeline'],0,2)
    assert c['beats'][0]['text']=='Một câu.' and c['beats'][0]['timing']=='timed_words'


def test_final_ffmpeg_zip_preserves_the_narrative_snapshot(tmp_path,monkeypatch):
    import zipfile
    from editvideo.jobs import Worker
    monkeypatch.setattr(store,'DATA',tmp_path/'store');store.initialize(recover=False)
    p=agent.read(agent.create_silent('landscape',30,'ffmpeg','Meaning archive')['id'])
    q=binding(p);q['beats'][0]['end_frame']=30;narrative.bind(q)
    job=store.create_job(p['id'],'final');Worker().run(job['id'])
    result=store.get_job(job['id']);assert result['state']=='completed',result.get('error')
    with zipfile.ZipFile(store.folder(p['id'])/'jobs'/job['id']/'delivery.zip') as z:
        assert json.loads(z.read('meaning.json'))['beats'][0]['text']==q['beats'][0]['text']
