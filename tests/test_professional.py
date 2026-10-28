import json
import shutil
import subprocess
import wave
from pathlib import Path
import numpy as np
import pytest
from editvideo import agent,store,professional,sound
from editvideo.models import Layer,AudioMix
from editvideo.media import FFMPEG,command,sha256
from test_pipeline import workspace
from test_agent import planned


def test_recipe_applies_with_revision_and_word_timing(workspace):
 pid=planned();p=agent.read(pid);voice=store.folder(pid)/'plan/voice.wav';original=sha256(voice)
 result=professional.compose(pid,p['revision'],{'recipe':'lower_third','start_frame':0,'end_frame':60,'text':'Nguyễn An','secondary_text':'Ví dụ chuyên gia'},True)
 assert not result['applied'] and agent.read(pid)['revision']==p['revision']
 result=professional.compose(pid,p['revision'],{'recipe':'hook_card','end_frame':60,'text':'Một câu hỏi rõ'})
 assert result['applied'] and result['revision']==p['revision']+1 and sha256(voice)==original
 with pytest.raises(ValueError):professional.compose(pid,p['revision'],{'recipe':'hook_card','end_frame':60,'text':'stale'})
 p=agent.read(pid)
 with pytest.raises(ValueError,match='Word timestamps'):professional.compose(pid,p['revision'],{'recipe':'word_captions','end_frame':60})
 agent.patch(pid,p['revision'],[{'op':'replace_cues','cues':[{'start':0,'end':1,'text':'Một câu rõ.'},{'start':1,'end':2,'text':'Dễ đọc.'}]}])
 p=agent.read(pid)
 supplied=[{'text':t,'start':a,'end':b} for t,a,b in [('Một',0,.3),('câu',.3,.6),('rõ.',.6,1),('Dễ',1,1.5),('đọc.',1.5,2)]]
 result=professional.compose(pid,p['revision'],{'recipe':'word_captions','end_frame':60,'word_timings':supplied,'timing_source':'controlled fixture'})
 layers=[op['layer'] for op in result['operations'] if op['op']=='upsert_layer']
 cap=layers[0];assert len(cap['data']['pages'])==2 and cap['kind']=='caption'
 assert len(layers)==1 and cap['data']['pages'][1]['words'][0]['start_frame']==30
 assert sha256(voice)==original
 p=agent.read(pid)
 professional.compose(pid,p['revision'],{'recipe':'lower_third','id':'speaker','end_frame':60,'text':'An','secondary_text':'Expert'})
 p=agent.read(pid)
 professional.compose(pid,p['revision'],{'recipe':'lower_third','id':'speaker','end_frame':60,'text':'An'})
 assert not any(l['id']=='speaker-role' for l in agent.read(pid)['timeline']['layers'])


def test_callout_caption_validation_and_frame_determinism(tmp_path):
 pages=[{'start_frame':i*30,'end_frame':(i+1)*30,'words':[{'text':str(i),'start_frame':i*30,'end_frame':(i+1)*30}]} for i in range(1001)]
 long=Layer(id='long',kind='caption',start_frame=0,end_frame=30030,data={'pages':pages})
 assert len(long.data['pages'])==1001
 with pytest.raises(ValueError):Layer(id='c',kind='caption',start_frame=0,end_frame=30,data={'words':[{'text':'x','start_frame':0,'end_frame':31}]})
 with pytest.raises(ValueError):Layer(id='c',kind='callout',start_frame=0,end_frame=30,data={'target':[.5,.5],'label_point':[1.2,.1]})
 src=tmp_path/'effects.cjs';src.write_bytes((store.ROOT/'engines/effects.js').read_bytes())
 code="""const fx=require(process.argv[1]);const cap={kind:'caption',data:{pages:[{start_frame:0,end_frame:30,words:[{text:'<A>',start_frame:0,end_frame:15},{text:'B',start_frame:15,end_frame:30}]}]}};const call={kind:'callout',width:1,height:1,text:'target',font_size:32,data:{target:[.2,.2],label_point:[.05,.05],target_keyframes:[{frame:0,x:.2,y:.2},{frame:30,x:.8,y:.8}]}};const a=fx.widget(call,15);fx.widget(call,2);console.log(JSON.stringify({a,deterministic:a===fx.widget(call,15),cap:fx.widget(cap,16),blank:fx.widget(cap,31),shape:fx.widget({kind:'shape',data:{shape:'rectangle'}},0),zero:fx.styleAt({effects:[{name:'focus_zoom',end_frame:30,params:{amount:0}}]},15)}));"""
 result=json.loads(subprocess.check_output(['node','-e',code,str(src)],text=True))
 assert result['deterministic'] and result['blank']=='' and '&lt;A&gt;' in result['cap']
 assert 'cx="960"' in result['a'] and 'cy="540"' in result['a']
 assert 'scale(1)' in result['zero']['transform']
 assert 'preserveAspectRatio="none"' in result['shape']


def test_sound_events_acoustic_timing_and_procedural_identity(workspace):
 a=sound.design('whoosh',.6,seed=81);b=sound.design('whoosh',.6,seed=81)
 assert sha256(a['path'])==sha256(b['path'])
 with wave.open(a['path']) as w:
  assert w.getframerate()==48000 and w.getnframes()==28800
  x=np.frombuffer(w.readframes(w.getnframes()),'<i2')/32768
  assert np.max(np.abs(x))<=10**(-18/20)
 path=workspace/'pulses.wav';t=np.arange(4*48000)/48000
 x=np.sin(2*np.pi*1000*t)*.25*((t>=1)&(t<1.2)|(t>=2.5)&(t<2.7))
 with wave.open(str(path),'wb') as w:w.setparams((1,2,48000,0,'NONE','not compressed'));w.writeframes((x*32767).astype('<i2').tobytes())
 r=sound.read_events(path,0,4)
 assert any(abs(e['timestamp']-1)<.05 for e in r['events']) and any(abs(e['timestamp']-2.5)<.05 for e in r['events'])
 assert r['loudness']['integrated_lufs'] is not None and r['quiet_intervals']


def test_audio_finish_settings_and_j_cut_handles(workspace):
 pid=planned();p=agent.read(pid)
 signal=workspace/'sound.wav';command([FFMPEG,'-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=4',signal])
 a=agent.import_media(pid,str(signal),preserve_plan=True,base_revision=p['revision']);p=agent.read(pid)
 with pytest.raises(ValueError,match='handles'):professional.compose(pid,p['revision'],{'recipe':'j_cut_audio','asset_id':a['asset']['id'],'start_frame':30,'cut_frame':30,'end_frame':60,'source_start':0})
 r=professional.compose(pid,p['revision'],{'recipe':'j_cut_audio','asset_id':a['asset']['id'],'start_frame':30,'cut_frame':30,'end_frame':60,'source_start':1},True)
 clip=r['operations'][0]['audio'];assert clip['start_frame']==18 and clip['source_start']==.6
 result=professional.compose(pid,p['revision'],{'recipe':'audio_finish','end_frame':60,'audio_mix':{'target_lufs':-18,'true_peak_db':-2,'music_ducking':{'ratio':5}}})
 assert agent.read(pid)['timeline']['audio_mix']['target_lufs']==-18
 from editvideo.renderer import mix_audio
 work=workspace/'finish';work.mkdir();shutil.copyfile(store.folder(pid)/'plan/voice.wav',work/'voice.wav')
 store.write_json(work/'timeline.json',agent.read(pid)['timeline'])
 mix_audio(pid,p['config'],work,agent.read(pid)['timeline']['total_frames']/30,lambda:False)
 settings=store.read_json(work/'audio-master.json')['settings'];assert settings['target_lufs']==-18
 with pytest.raises(ValueError):AudioMix(target_lufs=-1)


def test_short_form_caption_styles(workspace):
 pid=planned();p=agent.read(pid)
 agent.patch(pid,p['revision'],[{'op':'replace_cues','cues':[{'start':0,'end':1,'text':'Một câu rõ.'},{'start':1,'end':2,'text':'Dễ đọc.'}]}])
 p=agent.read(pid)
 supplied=[{'text':t,'start':a,'end':b} for t,a,b in [('Một',0,.3),('câu',.3,.6),('rõ.',.6,1),('Dễ',1,1.5),('đọc.',1.5,2)]]
 base={'recipe':'word_captions','end_frame':60,'word_timings':supplied,'timing_source':'fixture','platform':'tiktok','emphasis':['rõ'],'negative':['dễ'],'uppercase':True}
 build=professional.compose(pid,p['revision'],{**base,'caption_style':'build'},True)
 cap=[o['layer'] for o in build['operations'] if o['op']=='upsert_layer'][0]
 words=[w for pg in cap['data']['pages'] for w in pg['words']]
 assert cap['data']['future_opacity']==0 and all(w['text']==w['text'].upper() for w in words)
 assert {w['text']:w.get('color') for w in words}['RÕ.']=='#e4b866' and {w['text']:w.get('color') for w in words}['DỄ']=='#e80004'
 kw=professional.compose(pid,p['revision'],{**base,'caption_style':'keyword'},True)
 cap=[o['layer'] for o in kw['operations'] if o['op']=='upsert_layer'][0]
 assert [w['text'] for pg in cap['data']['pages'] for w in pg['words']]==['RÕ.','DỄ']
 Layer.model_validate(cap)
