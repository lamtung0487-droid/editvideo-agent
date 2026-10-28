"""Verified delivery, exact incremental GOP splice, caption reading time and dead-worker recovery."""
import copy
import json
import os
import shutil
from pathlib import Path
import pytest
from editvideo import store, subtitles, delivery, media_tasks, agent
from editvideo.media import FFMPEG, command, probe, sha256


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path / 'data')
    store.initialize(recover=False)
    return tmp_path


def video(path, seconds=4, colour='red'):
    command([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color={colour}:s=320x180:r=30:d={seconds}',
             '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={seconds}',
             '-c:v', 'libx264', '-g', '30', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', path])


def test_readability_is_computed_from_real_times_and_words_survive_reflow():
    rows = [{'start': 0, 'end': 1, 'text': 'This is a moderately long introductory sentence.', 'cps': 0},
            {'start': 1.05, 'end': 5.5, 'text': 'The ending gives the viewer enough time to read it.'}]
    assert subtitles.report(rows)['too_fast'] == 1
    new = subtitles.readable(rows, 8)
    assert ' '.join(c['text'] for c in new).split() == ' '.join(c['text'] for c in rows).split()
    assert not subtitles.report(new)['too_fast']
    assert all(0 <= c['start'] < c['end'] <= 8 for c in new)
    assert all(a['end'] <= b['start'] for a, b in zip(new, new[1:]))
    with pytest.raises(ValueError, match='Overlapping'):
        subtitles.readable([rows[0], {**rows[1], 'start': .5}], 8)


def test_readability_does_not_merge_raised_translation_with_normal_caption():
    rows = [{'start': 0, 'end': 2, 'text': 'One phrase.', 'raise': True}, {'start': 2.1, 'end': 4, 'text': 'A different voice.'}]
    new = subtitles.readable(rows, 5)
    assert new[0]['raise'] and not new[1].get('raise')


def test_gop_splice_has_exact_frame_grid_and_expected_pixels(workspace):
    import subprocess
    import numpy as np
    base, patch, final = [workspace / n for n in ('base.mp4', 'patch.mp4', 'final.mp4')]
    video(base, 6, 'red'); video(patch, 2, 'blue')
    assert delivery.keyframe_window(base, [65, 110], 180) == (60, 120)
    grid = delivery.splice(base, patch, 60, 120, 180, final)
    assert grid['frames'] == 180 and grid['irregular_count'] == 0
    command([FFMPEG, '-v', 'error', '-xerror', '-i', final, '-f', 'null', '-'])
    for at, channel in ((1, 0), (3, 2), (5, 0)):
        raw = subprocess.check_output([FFMPEG, '-v', 'error', '-ss', str(at), '-i', str(final), '-frames:v', '1', '-vf', 'scale=16:10', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        rgb = np.frombuffer(raw, np.uint8).reshape(-1, 3).mean(0)
        assert rgb[channel] > 240


def test_reuse_contract_rejects_picture_changes_outside_declared_layer_edit():
    old = {'shots': [{'id': 'a'}], 'layers': [{'id': 't', 'kind': 'text', 'start_frame': 0, 'end_frame': 90, 'text': 'A'}]}
    new = copy.deepcopy(old); new['shots'][0]['id'] = 'different'
    with pytest.raises(ValueError, match='layer edits'): delivery.delta_ranges(old, new)
    new = copy.deepcopy(old); new['layers'][0]['text'] = 'B'
    assert delivery.delta_ranges(old, new) == [[0, 90]]


def base_job(workspace):
    pid = agent.create_silent('landscape', 120, 'remotion', 'Delivery test')['id']
    p = agent.read(pid); job = store.create_job(pid, 'final')
    out = store.folder(pid) / 'jobs' / job['id']; out.mkdir(parents=True)
    video(out / 'final.mp4')
    store.write_json(out / 'timeline.json', p['timeline'])
    store.write_json(out / 'source/input.json', {'timeline': p['timeline'], 'config': p['config'], 'media': {}})
    store.write_json(out / 'technical.json', {'decoded': True, 'frames': 120, 'sha256': sha256(out / 'final.mp4')})
    store.job_progress(job['id'], 'completed', 100, 'Ready')
    return p, job, out


def test_dead_worker_only_recovers_a_hash_verified_complete_artifact(workspace, monkeypatch):
    p, job, out = base_job(workspace)
    with store.connection() as db: db.execute("UPDATE jobs SET state='running',owner_pid=999999 WHERE id=?", (job['id'],))
    monkeypatch.setattr(store, 'process_alive', lambda _: False)
    assert store.get_job(job['id'])['state'] == 'completed'
    with store.connection() as db: db.execute("UPDATE jobs SET state='running',owner_pid=999999 WHERE id=?", (job['id'],))
    (out / 'final.mp4').write_bytes(b'partial')
    assert store.get_job(job['id'])['state'] == 'interrupted'


def test_delivery_real_audio_and_selectable_captions_travel_in_zip(workspace):
    import zipfile
    p, job, out = base_job(workspace)
    caps = workspace / 'english.json'
    store.write_json(caps, [{'start': .1, 'end': 3.5, 'text': 'An English subtitle with enough time.'}])
    task = media_tasks.submit('delivery', {'project_id': p['id'], 'base_revision': p['revision'], 'base_job_id': job['id'], 'caption_path': str(caps)}, launch=False)
    # The task snapshots captions: later edits to the original input do not affect it.
    store.write_json(caps, [])
    result = media_tasks.run(task['id'])
    assert result['state'] == 'completed', result.get('error')
    r = result['result']; info = probe(r['video'])
    assert next(s for s in info['streams'] if s['codec_type'] == 'subtitle')['tags']['language'] == 'eng'
    assert r['report']['rendered_frames'] == 0 and r['report']['decoded']
    assert float(r['report']['audio_attempts'][-1]['measured']['input_tp']) <= -1.45
    with zipfile.ZipFile(r['artifacts']['package']) as z:
        assert 'English subtitle' in z.read('final.eng.srt').decode('utf-8')
        assert 'captions.srt' not in z.namelist()


def test_blender_cache_tracks_bytes_not_timestamp_or_task_path(workspace):
    from editvideo.blender import _digest
    script = workspace / 'script.py'; script.write_text('test')
    a, b = workspace / 'a.png', workspace / 'b.png'
    a.write_bytes(b'aaa'); b.write_bytes(b'aaa')
    first = _digest({'texture': str(a)}, script, [a])
    assert first == _digest({'texture': str(b)}, script, [b])
    timestamp = a.stat().st_mtime_ns
    a.write_bytes(b'bbb'); os.utime(a, ns=(timestamp, timestamp))
    assert first != _digest({'texture': str(a)}, script, [a])


def test_workbench_is_bounded_and_exact_schema_is_optional(workspace):
    from editvideo import workbench
    p, _, _ = base_job(workspace)
    r = workbench.scene(p['id'], 0, 3, 'số liệu có nguồn')
    assert r['revision'] == p['revision'] and len(r['inspect_frames']) == 3
    assert len(r['techniques']) == 3 and r['techniques'][0]['recipe'] == 'data_story'
    assert 'recipe_schema' not in r
    assert workbench.scene(p['id'], 0, 3, recipe='night_log')['recipe_schema']['properties']['nights']
    with pytest.raises(ValueError, match='window'): workbench.scene(p['id'], 0, 10)


def test_normal_renderer_guards_the_encoded_peak_not_only_a_wav(workspace):
    from editvideo.renderer import encoded_audio_guard
    path = workspace / 'onset.mp4'
    video(path, 2)
    # Force a visibly loud AAC signal; the guard must preserve picture while correcting the final encoded sound.
    loud = workspace / 'loud.mp4'
    command([FFMPEG,'-y','-v','error','-i',path,'-c:v','copy','-af','volume=24dB','-c:a','aac',loud])
    report = encoded_audio_guard(loud, -1.5, workspace)
    assert report['corrected'] and float(report['after']['input_tp']) <= -1.45
    assert next(s for s in probe(loud)['streams'] if s['codec_type']=='video')['nb_frames'] == '60'


def test_3d_contract_matches_templates_and_rejects_bad_camera_before_launch():
    from editvideo.render3d import Render3DRequest, contract
    params = {'frames': 30, 'camera': [{'frame': 0, 'lat': 21, 'lon': 105, 'altitude': 3}]}
    assert Render3DRequest(template='globe_shot', params=params).params['frames'] == 30
    assert 'places[' in str(contract()['globe_shot']['optional'])
    with pytest.raises(ValueError, match='require'):
        Render3DRequest(template='globe_shot', params={**params, 'camera': [{'frame': 0, 'lat': 21, 'lon': 105, 'radius': 3}]})
    with pytest.raises(ValueError, match='frame_step'):
        Render3DRequest(template='globe_shot', params={**params, 'frame_step': 2})
    terrain = Render3DRequest(template='terrain_shot', params={'frames': 30, 'bbox': [104,20,106,22],
        'camera': [{'frame': 0, 'lat': 21, 'lon': 105, 'alt_m': 3000, 'look_lon': 105, 'look_lat': 21}]})
    assert terrain.params['sun']['azimuth'] == 140 and terrain.params['sky']['horizon']
    dom = Render3DRequest(template='domino_shot', params={'frames': 60, 'bbox': [91, -5, 113, 23], 'map': 'map.png', 'paths': [[[106, 21], [103, 18]]]})
    assert dom.params['paths'] and 'mist' in str(contract()['terrain_shot']['optional'])
    with pytest.raises(ValueError, match='paths'):
        Render3DRequest(template='domino_shot', params={'frames': 60, 'bbox': [91, -5, 113, 23], 'map': 'map.png'})
