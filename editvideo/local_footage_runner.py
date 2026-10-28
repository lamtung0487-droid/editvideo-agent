"""LTX 2B distilled with CPU offload, bounded video dimensions and an exact schedule."""
import gc
import sys
import time
from pathlib import Path

def main(task_id):
    import_started=time.monotonic()
    import torch
    from accelerate import cpu_offload,init_empty_weights
    from accelerate.utils import set_module_tensor_to_device
    from transformers import T5EncoderModel,T5TokenizerFast,T5Config
    from diffusers import AutoencoderKLLTXVideo,LTXVideoTransformer3DModel,LTXPipeline,LTXConditionPipeline,FlowMatchEulerDiscreteScheduler
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
    from PIL import Image
    from . import store
    from .generation import GenerationRequest
    from .local_footage import root,MODEL,installation
    from .media_tasks import folder,check,update
    from .media import FFMPEG,command
    from .model_prefetch import warm,tensor_ranges
    out=folder(task_id);req=GenerationRequest.model_validate(store.read_json(out/"local-request.json"))
    if not torch.cuda.is_available():raise ValueError("Local LTX requires a CUDA GPU; configured remote adapters remain available")
    started=time.monotonic();device=torch.device("cuda:0");dtype=torch.bfloat16
    from . import generation_cache
    stages={'runtime_import_seconds':round(time.monotonic()-import_started,3)};stage_start=time.monotonic();cache_hints={}
    # Seed VAE/decoder operations too, rather than only the initial latent noise.
    torch.manual_seed(req.seed);torch.cuda.manual_seed_all(req.seed)
    key=generation_cache.prompt_key(req.prompt,installation()['artifacts'],installation().get('text_encoder_precision','fp32'))
    cached=generation_cache.load(key)
    if cached is not None:
        import numpy as np
        arrays,mask,record=cached
        embeds=torch.from_numpy(arrays).to(dtype);attention=torch.from_numpy(mask)
        token_count=record['prompt_tokens'];text_precision=record['precision']
        update(task_id,progress=.13,message="Reusing verified prompt embedding; skipping T5 model load")
    else:
        tokenizer=T5TokenizerFast.from_pretrained(str(root()/"tokenizer"),local_files_only=True)
        check(task_id);fp8=root()/"t5xxl_fp8_e4m3fn.safetensors"
        if installation().get("text_encoder_precision")=="fp8":
            update(task_id,progress=.03,message="Preparing cached prompt encoder")
            cache_hints['text_encoder']=warm(fp8,lambda:check(task_id))
            from safetensors import safe_open
            config=T5Config.from_pretrained(str(root()/"text_encoder"),local_files_only=True)
            with init_empty_weights():text=T5EncoderModel(config)
            expected=set(text.state_dict())
            linear_weights={name+'.weight' for name,module in text.named_modules() if isinstance(module,torch.nn.Linear)}
            with safe_open(str(fp8),framework="pt",device="cpu") as weights:
                if set(weights.keys())!=expected:raise ValueError("Cached T5 encoder tensor keys do not match configured architecture")
                for name in sorted(expected):
                    if name=="encoder.embed_tokens.weight":continue
                    check(task_id);storage_dtype=torch.float8_e4m3fn if name in linear_weights else dtype
                    set_module_tensor_to_device(text,name,"cpu",value=weights.get_tensor(name).to(storage_dtype),dtype=storage_dtype)
            text.encoder.embed_tokens.weight=text.shared.weight
            from .low_memory_t5 import patch
            patch(text).eval();text_precision="FP8 E4M3 linear storage, BF16 embedding/norm/computation (per-module casting)"
        else:
            text=T5EncoderModel.from_pretrained(str(root()/"text_encoder"),torch_dtype=dtype,local_files_only=True,low_cpu_mem_usage=True).eval();text_precision="FP32 checkpoint, BF16 computation"
        cpu_offload(text,execution_device=device)
        tokens=tokenizer(req.prompt,return_tensors="pt",padding="max_length",max_length=256,truncation=True)
        token_count=len(tokenizer(req.prompt).input_ids)
        check(task_id);update(task_id,progress=.12,message="Encoding prompt locally")
        with torch.inference_mode():embeds=text(tokens.input_ids.to(device),attention_mask=tokens.attention_mask.to(device)).last_hidden_state.cpu()
        attention=tokens.attention_mask
        check(task_id)
        generation_cache.save(key,embeds.float().numpy(),attention.numpy().astype('uint8'),token_count,text_precision)
        del text,tokenizer,tokens;gc.collect();torch.cuda.empty_cache();check(task_id)
    stages['prompt_seconds']=round(time.monotonic()-stage_start,3)
    prompt_cache={'hit':cached is not None,'key':key,'version':generation_cache.VERSION,
                  'skipped_encoder_weight_bytes':sum(r['bytes'] for r in installation()['artifacts'] if 'safetensors' in r['path'] and ('t5xxl' in r['path'] or 'text_encoder' in r['path'])) if cached is not None else 0}
    conditioned=bool(req.reference_image or req.reference_frames)
    stage_start=time.monotonic()
    references=[]
    if conditioned:
        anchors=([{'path':req.reference_image,'frame_index':0,'strength':req.reference_strength}] if req.reference_image else [])+[r.model_dump() for r in req.reference_frames]
        conditions=[]
        for i,anchor in enumerate(sorted(anchors,key=lambda r:r['frame_index'])):
            image,geometry=generation_cache.prepare_reference(anchor['path'],req.width,req.height,req.reference_fit,req.reference_crop)
            dest=out/f"prepared-reference-{i:02}.png";image.save(dest)
            from .media import sha256
            references.append({**geometry,'frame_index':anchor['frame_index'],'strength':anchor['strength'],
                               'source_sha256':sha256(anchor['path']),'prepared_sha256':sha256(dest),'prepared_path':str(dest)})
            conditions.append(LTXVideoCondition(image=image,frame_index=anchor['frame_index'],strength=anchor['strength']))
    checkpoint=str(root()/MODEL)
    update(task_id,progress=.14,message="Preparing cached LTX checkpoint")
    prefixes=('model.diffusion_model.','vae.decoder.','vae.per_channel_statistics.')
    if conditioned:prefixes+=('vae.encoder.',)
    cache_hints['ltx']=warm(checkpoint,lambda:check(task_id),tensor_ranges(checkpoint,prefixes))
    transformer=LTXVideoTransformer3DModel.from_single_file(checkpoint,config=str(root()/"config"),subfolder="transformer",torch_dtype=dtype,local_files_only=True)
    vae=AutoencoderKLLTXVideo.from_single_file(checkpoint,config=str(root()/"config"),subfolder="vae",torch_dtype=dtype,local_files_only=True)
    if not conditioned:
        # Text-to-video decodes latents only. Removing the unused encoder also
        # stops whole-model CPU offload from reading/transferring its 1.4GB.
        vae.encoder=None
    # Diffusers 0.35 passes uniform sigmas even when custom timesteps are supplied.
    # Bind the distilled model's schedule at the scheduler boundary instead.
    sigmas=[1.0,.9937,.9875,.9812,.975,.9094,.725,.4219]
    class DistilledSchedule(FlowMatchEulerDiscreteScheduler):
        def set_timesteps(self,num_inference_steps=None,device=None,sigmas=None,mu=None,timesteps=None):
            return super().set_timesteps(device=device,sigmas=[1.0,.9937,.9875,.9812,.975,.9094,.725,.4219])
    scheduler=DistilledSchedule.from_config(str(root()/"config/scheduler/scheduler_config.json"),use_dynamic_shifting=False,shift=1.0)
    cls=LTXConditionPipeline if conditioned else LTXPipeline
    pipe=cls(transformer=transformer,vae=vae,text_encoder=None,tokenizer=None,scheduler=scheduler)
    pipe.vae.enable_tiling(tile_sample_min_height=256,tile_sample_min_width=256,tile_sample_min_num_frames=16,tile_sample_stride_height=224,tile_sample_stride_width=224,tile_sample_stride_num_frames=8)
    reference_cache_stats=None
    if conditioned:
        from . import reference_cache
        from .local_footage import verified_artifacts
        from .media import sha256
        checkpoint_sha=verified_artifacts()[str((root()/MODEL).resolve())]['sha256']
        config_sha=sha256(root()/'config/vae/config.json')
        images=[c.image for c in conditions]
        keys=[reference_cache.key(im,checkpoint_sha,config_sha) for im in images]
        reference_cache_stats=reference_cache.bind(vae,images,keys)
    pipe.enable_model_cpu_offload(gpu_id=0)
    stages['model_load_seconds']=round(time.monotonic()-stage_start,3)
    frames=req.frame_count or ((req.duration*req.fps-1)//8*8+1)
    step_times=[];denoise_started=None;last_step=None
    def step(p,i,t,values):
        nonlocal denoise_started,last_step
        now=time.monotonic()
        if denoise_started is None:denoise_started=now
        if last_step is not None:step_times.append(round(now-last_step,3))
        last_step=now
        message="Decoding local footage" if i+1==len(sigmas) else f"Local LTX denoising {i+1}/{len(sigmas)}"
        check(task_id);update(task_id,progress=.2+.6*(i+1)/len(sigmas),message=message)
        return values
    # Precomputed inputs are not moved by encode_prompt. Accelerate's model
    # offload hook moves inputs only on the first transfer, then skips it.
    # Keep embeddings/mask on CUDA for every denoising iteration.
    kwargs={"prompt_embeds":embeds.to(device),"prompt_attention_mask":attention.bool().to(device),"width":req.width,"height":req.height,"num_frames":frames,"frame_rate":req.fps,"num_inference_steps":len(sigmas),"guidance_scale":1.0,"decode_timestep":.05,"decode_noise_scale":.025,"generator":torch.Generator(device="cpu").manual_seed(req.seed),"callback_on_step_end":step,"max_sequence_length":256}
    if conditioned:
        kwargs['conditions']=conditions;kwargs['image_cond_noise_scale']=req.image_cond_noise_scale
    check(task_id);update(task_id,progress=.2,message="Generating local footage")
    # Loading initialized modules can consume RNG on a cache miss. Reset at the
    # inference boundary so a hit and miss use the same VAE/decoder stream.
    torch.manual_seed(req.seed);torch.cuda.manual_seed_all(req.seed)
    stage_start=time.monotonic()
    with torch.inference_mode():video=pipe(**kwargs).frames[0]
    finished=time.monotonic()
    stages['conditioning_denoise_decode_seconds']=round(finished-stage_start,3)
    stages['after_last_step_decode_seconds']=round(finished-last_step,3) if last_step is not None else None
    stages['steps_2_to_8_seconds']=step_times
    stage_start=time.monotonic()
    check(task_id);dest=out/"generated-frames";dest.mkdir(exist_ok=True)
    for i,frame in enumerate(video):check(task_id);frame.save(dest/f"{i:06d}.png")
    command([FFMPEG,"-y","-v","error","-framerate",req.fps,"-i",dest/"%06d.png","-c:v","libx264","-crf",18,"-pix_fmt","yuv420p",out/"provider-output.mp4"],timeout=120)
    metadata={"provider":"local_ltx","model":"ltxv-2b-0.9.8-distilled","text_encoder_precision":text_precision,"mode":"image_to_video" if conditioned else "text_to_video","seed":req.seed,"frames":len(video),"sigmas":sigmas,"guidance_scale":1.0,"decode_timestep":.05,"decode_noise_scale":.025,"prompt_tokens":token_count,"prompt_truncated":token_count>256,"seconds":round(time.monotonic()-started,2),"gpu":torch.cuda.get_device_name(),"peak_allocated_bytes":torch.cuda.max_memory_allocated(),"cpu_offload":True,"source":"https://huggingface.co/Lightricks/LTX-Video"}
    stages['frame_export_encode_seconds']=round(time.monotonic()-stage_start,3)
    metadata.update(cache_hints=cache_hints,prompt_cache=prompt_cache,reference_cache=reference_cache_stats,stage_timings=stages,reference_frames=references,
                    preset=req.preset,image_cond_noise_scale=req.image_cond_noise_scale,seed_scope='CPU and CUDA RNG plus latent generator; same runtime/hardware, not a cross-hardware bit-exact guarantee')
    metadata['timing_scope']='seconds measures post-import inference/export; worker_wall_seconds includes process imports/exit and is measured by parent'
    metadata['runtime_versions']=generation_cache.runtime_versions()
    store.write_json(out/"local-generation.json",metadata)

if __name__=="__main__":main(sys.argv[1])
