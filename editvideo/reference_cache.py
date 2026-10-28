"""Cache deterministic VAE posterior parameters, never sampled latent noise.

Retaining the posterior lets Diffusers sample with the original generator and
sequence ordering on each call. Small CPU arrays avoid retaining GPU models.
"""
import hashlib
import json
import os
import uuid
import zipfile
from pathlib import Path
import numpy as np
from . import store
from .media import sha256

VERSION = "ltx095-posterior-bf16-tiling256-stride224-v1"


def key(image, checkpoint_sha, config_sha):
    from .generation_cache import runtime_versions
    identity = {'version':VERSION,'image_size':list(image.size),
                'pixels':hashlib.sha256(image.tobytes()).hexdigest(),
                'checkpoint':checkpoint_sha,'vae_config':config_sha,'runtime':runtime_versions()}
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


def _path(identity):
    if len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid reference cache key')
    return store.DATA/'generation-cache'/'references'/(identity+'.npz')


def _validate(parameters, size):
    if parameters.dtype!=np.float32 or parameters.shape!=(1,256,1,size[1]//32,size[0]//32) or not np.isfinite(parameters).all():
        raise ValueError('Invalid reference posterior parameters')


def load(identity,size):
    path=_path(identity)
    try:
        record=store.read_json(path.with_suffix('.json'))
        if record['key']!=identity or record['version']!=VERSION or not 0<path.stat().st_size<2_000_000 or sha256(path)!=record['sha256']:return None
        with np.load(path,allow_pickle=False) as arrays:parameters=arrays['parameters']
        _validate(parameters,size);os.utime(path,None)
        return parameters
    except (OSError,ValueError,KeyError,TypeError,EOFError,zipfile.BadZipFile):return None


def save(identity,parameters,size):
    _validate(parameters,size);path=_path(identity);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(identity+'-'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('wb') as f:np.savez(f,parameters=parameters)
        record={'key':identity,'version':VERSION,'sha256':sha256(tmp),'size':list(size)}
        os.replace(tmp,path);store.write_json(path.with_suffix('.json'),record)
        # At most 128 small reference entries; generation owns the GPU lock.
        for old in sorted(path.parent.glob('*.npz'),key=lambda p:p.stat().st_mtime_ns,reverse=True)[128:]:
            if old!=path:old.unlink(missing_ok=True);old.with_suffix('.json').unlink(missing_ok=True)
    finally:tmp.unlink(missing_ok=True)


def bind(vae,images,keys):
    """Return hook stats; preserve the upstream posterior sampling contract."""
    import torch
    from diffusers.models.autoencoders.vae import DiagonalGaussianDistribution
    from diffusers.models.modeling_outputs import AutoencoderKLOutput
    if len(images)!=len(keys):raise ValueError('Reference cache bindings mismatch')
    entries={k:load(k,im.size) for k,im in zip(keys,images)}
    all_cached=all(x is not None for x in entries.values())
    if all_cached:
        vae.encoder=None
    original=vae.encode;position=0
    stats={'version':VERSION,'hits':0,'misses':0,'encoder_omitted':all_cached,'keys':keys,
           'note':'Posterior cached before RNG sampling; same strength/seed/noise changes do not invalidate it'}
    def encode(data,*args,**kwargs):
        nonlocal position
        if position>=len(keys):raise ValueError('Unexpected reference encoder call')
        index=position;position+=1;identity=keys[index]
        parameters=entries[identity]
        if parameters is None:
            output=original(data,*args,**kwargs)
            parameters=output.latent_dist.parameters.detach().cpu().float().numpy()
            save(identity,parameters,images[index].size);entries[identity]=parameters;stats['misses']+=1
            return output
        stats['hits']+=1
        distribution=DiagonalGaussianDistribution(torch.from_numpy(parameters).to(device=data.device,dtype=data.dtype))
        return AutoencoderKLOutput(latent_dist=distribution) if kwargs.get('return_dict',True) else (distribution,)
    vae.encode=encode
    return stats
