"""Controlled video signals and immutable/cached generation iteration."""
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from editvideo import store, motion, generation, generation_cache, media_tasks
from editvideo.media import command, FFMPEG, sha256, probe


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path);store.initialize()
    return tmp_path


def test_motion_separates_global_translation_and_aligned_change():
    import cv2
    rng=np.random.default_rng(7)
    rgb=cv2.GaussianBlur(rng.integers(20,230,(144,256,3),dtype=np.uint8),(5,5),0)
    shifted=cv2.warpAffine(rgb,np.array([[1.,0.,3.],[0.,1.,2.]]),(256,144),borderMode=cv2.BORDER_REFLECT)
    measured,_,mask,_=motion.measure_pair(rgb,shifted)
    assert mask.mean()>.85
    matrix=np.array(measured['camera_affine_previous_to_current'])
    assert np.allclose(matrix[:,2],[3,2],atol=.3)
    assert measured['aligned_rgb_residual']<measured['raw_rgb_change']*.2
    assert measured['non_camera_motion_pixels_p95']<1
    # A lighting change must remain visible even after correspondence alignment.
    brighter=np.clip(shifted.astype(int)+10,0,255).astype('uint8')
    m,_,_,_=motion.measure_pair(rgb,brighter)
    assert 8<m['aligned_rgb_residual']<12


def test_cut_resets_flow_and_fft_reports_real_frequency():
    a=np.full((96,160,3),20,np.uint8);b=np.full_like(a,220)
    m,_,mask,_=motion.measure_pair(a,b)
    assert m['cut_candidate'] and not mask.any() and m['aligned_rgb_residual'] is None
    # Different hue with nearly identical gray luma must also reset correspondence.
    a[:]=[255,0,0];b[:]=[0,130,0]
    assert motion.measure_pair(a,b)[0]['cut_candidate']
    s=motion.spectrum(120+5*np.sin(2*np.pi*3*np.arange(96)/24),24)
    assert s['peaks'][0]['frequency_hz']==3
    assert s['resolution_hz']==.25 and s['nyquist_hz']==12
    assert motion.spectrum(np.ones(96)*120,24)['peaks']==[]


def signal_video(root):
    frames=root/'fixture';frames.mkdir()
    for i in range(96):
        rgb=np.full((144,256,3),round(120+5*np.sin(2*np.pi*3*i/24)),np.uint8)
        Image.fromarray(rgb).save(frames/f'{i:06}.png')
    video=root/'signal.mp4'
    command([FFMPEG,'-y','-v','error','-framerate',24,'-i',frames/'%06d.png','-c:v','libx264','-crf',0,'-pix_fmt','yuv444p',video])
    return video


def test_temporal_packet_paging_and_actual_lens_video(workspace):
    video=signal_video(workspace)
    packet=motion.analyze(video,0,4,sampling_fps=24,width=256,evidence_frames=4)
    assert packet['sample_count']==96 and 'pairs' not in packet
    assert packet['luma_spectrum']['peaks'][0]['frequency_hz']==3
    rows=motion.read(packet['manifest'],0,10)
    assert rows['total']==95 and len(rows['pairs'])==10 and rows['next_offset']==10
    assert not (Path(packet['manifest']).parent/'frames.rgb').exists()
    lens=motion.temporal_lens(video,0,4,sampling_fps=24,width=256,low_hz=2.5,high_hz=3.5,gain=3)
    assert lens['clipped_channel_fraction']==0 and probe(lens['video'])['streams'][0]['width']==512
    # Compare decoded mid-row pixels: selected temporal amplitude increases.
    import cv2
    capture=cv2.VideoCapture(lens['video']);left=[];right=[]
    while True:
        ok,frame=capture.read()
        if not ok:break
        left.append(frame[60,60].mean());right.append(frame[60,316].mean())
    capture.release()
    assert len(left)==96 and np.std(right)>np.std(left)*2.5
    with pytest.raises(ValueError):motion.temporal_lens(video,0,4,high_hz=12)
    with pytest.raises(ValueError):motion.read(str(video))


def test_prompt_cache_integrity_and_model_invalidation(workspace):
    records=[{'path':'/model/text_encoder/config.json','sha256':'a'*64},
             {'path':'/model/tokenizer/spiece.model','sha256':'b'*64}]
    key=generation_cache.prompt_key('forest',records,'fp8')
    assert key!=generation_cache.prompt_key('forest moving',records,'fp8')
    changed=[{**r,'sha256':'c'*64} for r in records]
    assert key!=generation_cache.prompt_key('forest',changed,'fp8')
    arrays=np.ones((1,256,4096),np.float32);mask=np.ones((1,256),np.uint8)
    generation_cache.save(key,arrays,mask,11,'fp8')
    a,m,r=generation_cache.load(key)
    assert np.array_equal(a,arrays) and np.array_equal(m,mask) and r['prompt_tokens']==11
    path=generation_cache.cache_root()/(key+'.npz')
    with path.open('r+b') as f:f.seek(-100,2);f.write(b'changed')
    assert generation_cache.load(key) is None
    with pytest.raises(ValueError):generation_cache.save(key,arrays[:,:10],mask,11,'fp8')


def test_reference_posterior_cache_keys_and_integrity(workspace):
    from editvideo import reference_cache
    image=Image.new('RGB',(256,160),'green')
    key=reference_cache.key(image,'a'*64,'b'*64)
    assert key!=reference_cache.key(image,'c'*64,'b'*64)
    assert key!=reference_cache.key(Image.new('RGB',image.size,'red'),'a'*64,'b'*64)
    parameters=np.ones((1,256,1,5,8),np.float32)
    reference_cache.save(key,parameters,image.size)
    assert np.array_equal(reference_cache.load(key,image.size),parameters)
    assert reference_cache.load(key,(512,320)) is None
    path=reference_cache._path(key);path.write_bytes(b'corrupt')
    assert reference_cache.load(key,image.size) is None


def test_reference_geometry_alpha_and_local_controls(workspace):
    image=workspace/'reference.png';Image.new('RGBA',(400,200),(255,0,0,128)).save(image)
    rgb,g=generation_cache.prepare_reference(image,256,256,'cover')
    assert rgb.size==(256,256) and g['source_crop_pixels']==[100,0,300,200]
    assert rgb.getpixel((100,100))[0] in (135,136)
    _,g=generation_cache.prepare_reference(image,256,256,'cover',[0,0,.5,1])
    assert g['source_crop_pixels']==[0,0,200,200]
    for preset,expected in [('draft',(384,256,49)),('detail',(768,448,121))]:
        req=generation.GenerationRequest(provider='local_ltx',prompt='leaves',preset=preset)
        assert (req.width,req.height,req.frame_count)==expected
    req=generation.GenerationRequest(provider='local_ltx',prompt='leaves',reference_image=str(image),reference_frames=[{'path':str(image),'frame_index':72}])
    assert req.reference_frames[0].frame_index==72
    for change in ({'reference_frames':[{'path':str(image),'frame_index':0}]}, {'reference_crop':[0,0,2,1]}, {'reference_strength':0}):
        with pytest.raises(ValueError):generation.GenerationRequest(**{**req.model_dump(),**change})
    with pytest.raises(ValueError):generation.GenerationRequest(provider='runway',prompt='leaves',reference_strength=.5)


def test_reference_snapshot_and_refinement_lineage(workspace,monkeypatch):
    monkeypatch.setattr(generation,'validate_request',lambda req:generation.GenerationRequest(**req))
    reference=workspace/'ref.png';Image.new('RGB',(256,144),'green').save(reference)
    req={'provider':'local_ltx','prompt':'leaves','reference_image':str(reference),
         'reference_frames':[{'path':str(reference),'frame_index':72}]}
    parent=media_tasks.submit('generate',req,launch=False)
    image=Path(parent['request']['reference_image']);anchor=Path(parent['request']['reference_frames'][0]['path'])
    original=sha256(reference);Image.new('RGB',(256,144),'red').save(reference)
    assert sha256(image)==sha256(anchor)==original
    media_tasks.update(parent['id'],'completed',1,result={'video_sha256':'c'*64,'reference_sha256':original,
        'reference_frames_sha256':[{'frame_index':72,'sha256':original}]})
    monkeypatch.setattr(media_tasks,'launch_task',lambda tid:media_tasks.get(tid))
    child=generation.refine(parent['id'],{'image_cond_noise_scale':.03})
    lineage=store.read_json(media_tasks.folder(child['id'])/'refinement.json')
    assert lineage['parent_task_id']==parent['id'] and lineage['seed_preserved']
    assert child['request']['image_cond_noise_scale']==.03
    Image.new('RGB',(256,144),'blue').save(image)
    with pytest.raises(ValueError,match='reference changed'):generation.refine(parent['id'],{'seed':9})
