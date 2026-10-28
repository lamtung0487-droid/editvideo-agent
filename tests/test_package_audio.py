"""Portable delivery must retain narration/master stored outside source/public."""
import hashlib,json,zipfile
from editvideo import agent,store
from editvideo.code_engine import package
from test_pipeline import workspace

def test_portable_audio_roundtrip_and_lean_package(workspace):
    pid=agent.create({'title':'Portable audio','script':'A spoken idea.'})['id']
    work=store.folder(pid)/'jobs'/'package-proof';source=work/'source';source.mkdir(parents=True)
    (source/'input.json').write_text('{}',encoding='utf-8')
    masters={'voice.wav':b'RIFF original locked narration','mix.wav':b'RIFF final audio with accents'}
    for name,data in masters.items():(work/name).write_bytes(data)
    full=package(pid,work,source,include_media=True)
    with zipfile.ZipFile(full) as archive:
        manifest=json.loads(archive.read('media-manifest.json'))
        for name,data in masters.items():
            assert archive.read(name)==data
            assert manifest['audio_sha256'][name]==hashlib.sha256(data).hexdigest()
    lean=package(pid,work,source,include_media=False)
    with zipfile.ZipFile(lean) as archive:
        assert not set(masters).intersection(archive.namelist())
        assert json.loads(archive.read('media-manifest.json'))['audio_sha256']=={}
