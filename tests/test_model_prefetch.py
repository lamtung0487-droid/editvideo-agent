"""Range selection must not warm unused encoder weights or escape the file."""
import json
import struct
import pytest
from editvideo.model_prefetch import tensor_ranges

def test_selective_checkpoint_prefetch(tmp_path):
    path=tmp_path/'model.safetensors'
    header=json.dumps({'model.diffusion_model.weight':{'data_offsets':[0,16]},
                       'vae.decoder.weight':{'data_offsets':[16,32]},
                       'vae.encoder.weight':{'data_offsets':[32,64]},
                       'vae.per_channel_statistics.mean':{'data_offsets':[64,68]}}).encode()
    path.write_bytes(struct.pack('<Q',len(header))+header+bytes(68))
    start=len(header)+8
    regions=tensor_ranges(path,('model.diffusion_model.','vae.decoder.','vae.per_channel_statistics.'))
    assert regions==[(0,start+32),(start+64,start+68)]
    assert tensor_ranges(path,('model.diffusion_model.','vae.'))==[(0,path.stat().st_size)]
    with pytest.raises(ValueError,match='No requested tensors'):tensor_ranges(path,('missing.',))

def test_invalid_checkpoint_range_rejected(tmp_path):
    path=tmp_path/'model.safetensors'
    header=json.dumps({'vae.decoder.weight':{'data_offsets':[0,1000]}}).encode()
    path.write_bytes(struct.pack('<Q',len(header))+header+bytes(16))
    with pytest.raises(ValueError,match='Invalid safetensors tensor range'):
        tensor_ranges(path,('vae.decoder.',))
