"""Decode the actual delivered film and verify its locked narration/timing/assets."""
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editvideo import store
from editvideo.media import FFMPEG,FFPROBE,command,probe,sha256

def main():
    rec=store.read_json(store.ROOT/'outputs/temporal-demo-project.json')
    project=store.folder(rec['project_id']);timeline=store.read_json(project/'plan/timeline.json')
    video=store.ROOT/'outputs/ai-video-complete.mp4'
    command([FFMPEG,'-v','error','-xerror','-i',video,'-f','null','-'],timeout=300)
    info=probe(video);v=next(s for s in info['streams'] if s['codec_type']=='video')
    a=next(s for s in info['streams'] if s['codec_type']=='audio')
    assert [v['width'],v['height']]==[timeline['width'],timeline['height']]
    assert v['r_frame_rate']==f"{timeline['fps']}/1"
    assert int(v['nb_frames'])==timeline['total_frames']
    assert int(a['sample_rate'])==48000
    assert abs(float(v['duration'])-timeline['total_frames']/timeline['fps'])<.001
    assert abs(float(a['duration'])-float(v['duration']))<.06
    assert all(0<=c['start']<c['end']<=float(v['duration'])+.001 for c in timeline['cues'])
    assert sha256(project/'plan/voice.wav')==rec['narration_before_sha256']
    mix=command([FFMPEG,'-hide_banner','-i',video,'-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],timeout=120)
    levels=json.loads(mix[mix.rfind('{'):mix.rfind('}')+1])
    package=store.ROOT/'outputs/ai-video-complete.zip'
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert z.read('voice.wav')==(project/'plan/voice.wav').read_bytes()
        source_audio=[n for n in names if '/public/' in n and Path(n).suffix.lower() in ('.wav','.mp3','.m4a')]
        assert source_audio,'Editable source must include the media used for narration/music'
    report={'project_id':rec['project_id'],'job_id':rec['job']['id'],
            'video':str(video),'frames':int(v['nb_frames']),'dimensions':[v['width'],v['height']],
            'fps':v['r_frame_rate'],'duration':float(v['duration']),
            'audio_sample_rate':int(a['sample_rate']),'audio_duration':float(a['duration']),
            'full_decode_errors':0,'captions':len(timeline['cues']),
            'narration_sha256':sha256(project/'plan/voice.wav'),
            'video_sha256':sha256(video),'package_sha256':sha256(package),
            'package_source_audio':source_audio,'loudness':levels}
    store.write_json(store.ROOT/'outputs/complete-video-verification.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
