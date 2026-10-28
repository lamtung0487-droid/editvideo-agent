"""Optional numerical checks for the installed heavy runtime, no model download."""
import os
import pytest

@pytest.mark.skipif(os.environ.get('EDITVIDEO_RUN_RUNTIME_TESTS')!='1',reason='optional Torch/Transformers runtime')
def test_fp8_t5_storage_preserves_bf16_quantized_computation():
    import copy
    import torch
    from transformers import T5Config,T5EncoderModel
    from editvideo.low_memory_t5 import patch
    torch.manual_seed(7)
    model=T5EncoderModel(T5Config(vocab_size=128,d_model=32,d_ff=64,d_kv=8,num_heads=4,num_layers=2,feed_forward_proj='gated-gelu',dropout_rate=0)).eval().to(torch.bfloat16)
    for module in model.modules():
        if isinstance(module,torch.nn.Linear):module.weight.data=module.weight.data.to(torch.float8_e4m3fn).to(torch.bfloat16)
    optimized=copy.deepcopy(model)
    for module in optimized.modules():
        if isinstance(module,torch.nn.Linear):module.weight.data=module.weight.data.to(torch.float8_e4m3fn)
    patch(optimized)
    ids=torch.tensor([[1,9,17,24,2]])
    with torch.inference_mode():
        expected=model(ids).last_hidden_state;actual=optimized(ids).last_hidden_state
    assert torch.equal(actual,expected)
    bytes_of=lambda m:sum(p.numel()*p.element_size() for p in m.parameters())
    assert bytes_of(optimized)<bytes_of(model)*.75


@pytest.mark.skipif(os.environ.get('EDITVIDEO_RUN_RUNTIME_TESTS')!='1',reason='optional Torch/Diffusers runtime')
def test_reference_cache_preserves_posterior_rng_sampling(tmp_path,monkeypatch):
    import torch
    from PIL import Image
    from diffusers.models.autoencoders.vae import DiagonalGaussianDistribution
    from diffusers.models.modeling_outputs import AutoencoderKLOutput
    from editvideo import store,reference_cache
    monkeypatch.setattr(store,'DATA',tmp_path)
    image=Image.new('RGB',(256,160),'green')
    parameters=torch.randn((1,256,1,5,8),generator=torch.Generator().manual_seed(71)).to(torch.bfloat16)
    class VAE:
        encoder=True
        calls=0
        def encode(self,data):
            self.calls+=1
            return AutoencoderKLOutput(latent_dist=DiagonalGaussianDistribution(parameters))
    key=reference_cache.key(image,'a'*64,'b'*64)
    vae=VAE();stats=reference_cache.bind(vae,[image,image],[key,key])
    data=torch.zeros((1,3,1,160,256),dtype=torch.bfloat16)
    miss=vae.encode(data).latent_dist.sample(torch.Generator().manual_seed(12))
    hit=vae.encode(data).latent_dist.sample(torch.Generator().manual_seed(12))
    assert torch.equal(miss,hit) and vae.calls==1 and stats['hits']==stats['misses']==1
    cached=VAE();stats=reference_cache.bind(cached,[image],[key])
    out=cached.encode(data).latent_dist.sample(torch.Generator().manual_seed(12))
    assert torch.equal(out,miss) and cached.calls==0 and cached.encoder is None and stats['encoder_omitted']
