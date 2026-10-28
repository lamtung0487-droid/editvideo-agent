import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from editvideo import store
from editvideo.server import app


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DATA",tmp_path)
    with TestClient(app) as client:
        yield client


def test_project_upload_labels_and_input_validation(client):
    created=client.post('/api/projects',json={'title':'Kiến thức','script':'Một chiếc lá.'})
    assert created.status_code==200
    pid=created.json()['id']
    assert client.get('/api/projects/'+pid).json()['config']['title']=='Kiến thức'
    from PIL import Image
    import io
    stream=io.BytesIO();Image.new('RGB',(64,64),'green').save(stream,format='PNG')
    response=client.post(f'/api/projects/{pid}/assets',files={'file':('leaf.png',stream.getvalue(),'image/png')},data={'tags':'chiếc lá'})
    assert response.status_code==200,response.text
    asset=response.json()
    assert 'path' not in asset and 'thumbnail' not in asset
    assert client.get(f'/api/projects/{pid}').json()['revision']==2
    assert client.get(f'/api/projects/{pid}/assets/{asset["id"]}/file?thumbnail=true').status_code==200
    response=client.patch(f'/api/projects/{pid}/assets/{asset["id"]}',json={'tags':'lá cây xanh','role':'evidence'})
    assert response.status_code==200
    assert client.get(f'/api/projects/{pid}').json()['revision']==3
    assert client.post(f'/api/projects/{pid}/assets',files={'file':('bad.html',b'<script>','text/html')}).status_code==409
    assert client.post(f'/api/projects/{pid}/jobs',json={'kind':'final'}).status_code==409
    assert client.post(f'/api/projects/{pid}/captions',files={'file':('bad.srt',b'nonsense','text/plain')}).status_code==409
    assert client.put(f'/api/projects/{pid}',json={'title':'X','narration_id':asset['id']}).status_code==409


def test_origin_and_cross_project_files(client):
    assert client.post('/api/projects',json={'title':'Blocked'},headers={'Origin':'https://other.example'}).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    a=client.post('/api/projects',json={'title':'A'}).json()['id']
    b=client.post('/api/projects',json={'title':'B'}).json()['id']
    job=store.create_job(a,'plan')
    store.cancel(job['id'])
    assert client.get(f'/api/projects/{b}/jobs/{job["id"]}/timeline.json').status_code==404
    assert client.get(f'/api/projects/{a}/jobs/{job["id"]}/studio.db').status_code==404


def test_pipeline_error_and_restart_recovery(client):
    pid=client.post('/api/projects',json={'title':'Empty'}).json()['id']
    j=client.post(f'/api/projects/{pid}/jobs',json={'kind':'plan'}).json()
    for _ in range(50):
        result=client.get(f'/api/jobs/{j["id"]}').json()
        if result['state'] not in ('queued','running'):break
        time.sleep(.02)
    assert result['state']=='failed'
    assert 'kịch bản' in result['error']
    j=store.create_job(pid,'plan')
    store.initialize()
    # Another live client owns this job; initialization must preserve it.
    assert store.get_job(j['id'])['state']=='queued'
    with store.connection() as db:
        db.execute('UPDATE jobs SET owner_pid=99999999 WHERE id=?',(j['id'],))
    store.initialize()
    assert store.get_job(j['id'])['state']=='interrupted'
