"""Verify an actual inpaint result and report a limited same-pixel flicker comparison."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from editvideo import store,media_tasks,subjects
from editvideo.media import FFMPEG,command,probe,sha256

def main():
    p=argparse.ArgumentParser();p.add_argument('--task',default='fe6af504-2de7-49f3-a5e8-d2e38d153f1c');p.add_argument('--baseline',default='19660503-4930-447b-afe9-23fefaf5ca3a');p.add_argument('--output',default='temporal-verification.json');args=p.parse_args()
    task=media_tasks.get(args.task);baseline=media_tasks.get(args.baseline)
    assert task['state']==baseline['state']=='completed'
    req=subjects.MaskEditRequest.model_validate(task['request']);manifest,session=subjects.load_session(req.subject_task_id)
    root=media_tasks.folder(args.task);dest=Path(task['result']['frames_directory']);prior=None;prior_mask=None;metrics=[[],[]];outside_error=0;pixels=0
    for i in range(manifest['frames']):
        source=np.asarray(Image.open(root/'source-frames'/f'{i:06d}.png').convert('RGB'));h,w=source.shape[:2]
        mask=cv2.resize(subjects._mask(manifest,session,req.object_ids,i),(w,h),interpolation=cv2.INTER_NEAREST)
        if req.invert:mask=255-mask
        scale=w/manifest['mask_dimensions'][0];d=round(req.dilation*scale);f=round(req.feather*scale)
        dilated=cv2.dilate(mask,np.ones((2*d+1,2*d+1),np.uint8)) if d else mask
        alpha=dilated.astype(np.float32)/255
        if f:alpha=cv2.GaussianBlur(alpha,(f*2+1,f*2+1),0)
        images=[np.asarray(Image.open(Path(baseline['result']['frames_directory'])/f'{i:06d}.png').convert('RGB')).astype(float),np.asarray(Image.open(dest/f'{i:06d}.png').convert('RGB')).astype(float)]
        unchanged=alpha==0
        if unchanged.any():outside_error=max(outside_error,float(np.abs(images[1]-source)[unchanged].max()))
        hole=cv2.erode(mask,np.ones((9,9),np.uint8))>0
        if '1' in manifest['tracks'] and 1 not in req.object_ids:
            protect=cv2.resize(subjects._mask(manifest,session,[1],i),(w,h),interpolation=cv2.INTER_NEAREST)>0;hole&=~protect
        if prior is not None:
            region=hole&prior_mask;pixels+=int(region.sum())
            if region.any():
                for j in range(2):metrics[j].extend(np.abs(images[j]-prior[j])[region].mean(axis=1).tolist())
        prior=images;prior_mask=hole
    video=Path(task['result']['artifacts']['video']);command([FFMPEG,'-v','error','-xerror','-i',video,'-f','null','-'])
    info=probe(video);report={'task_id':args.task,'baseline_task_id':args.baseline,'frames':manifest['frames'],'source_dimensions':task['result']['dimensions'],'decoder_errors':0,'outside_feather_max_pixel_error':outside_error,'compared_hole_pixels':pixels,'same_pixel_adjacent_frame_mean_absolute_rgb_change':{'lama':float(np.mean(metrics[0])),'propainter':float(np.mean(metrics[1]))},'metric_limit':'Same-pixel residual on this mostly static camera sample, excluding the retained subject. Contains genuine background motion, mask changes and reconstruction errors. It is not an aesthetic score or a general quality guarantee.','video_sha256':sha256(video),'temporal':task['result']['temporal']}
    assert outside_error==0,report
    store.write_json(store.ROOT/'outputs'/args.output,report);print(json.dumps(report),flush=True)

if __name__=='__main__':main()
