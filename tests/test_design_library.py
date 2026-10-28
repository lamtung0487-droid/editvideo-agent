import json,subprocess,unicodedata
from pathlib import Path
import pytest
from fontTools.ttLib import TTFont
from editvideo import agent,store,design_library as dl
from editvideo.code_engine import scaffold,refresh_payload
from editvideo.models import Design,Layer,TypeStyle
from editvideo.media import sha256
from test_pipeline import workspace
from test_agent import planned

def test_real_font_glyphs_weights_license_and_palette_evidence():
 manifest=dl.font_manifest();chars={chr(i) for i in range(0x1ea0,0x1efa)}|set('ĐđƠơƯư')
 assert len(manifest['fonts'])==16
 for item in manifest['fonts']:
  assert sha256(dl.FONT_ROOT/item['license_file'])==item['license_sha256']
  for face in item['faces']:
   path=dl.FONT_ROOT/face['file'];assert sha256(path)==face['sha256']
   with TTFont(path) as f:assert all(ord(c) in f.getBestCmap() for c in chars)
 for row in dl.STYLE_ROWS:Design.model_validate(dl.tokens(row[0]))
 for row in dl.PALETTE_ROWS:assert min(dl.palette(row[0])['contrast'].values())>=4.5
 assert dl.contrast('#000000','#ffffff')==21
 with pytest.raises(ValueError):TypeStyle(font_id='bevietnampro',weight=900)
 with pytest.raises(ValueError):TypeStyle(font_id='manrope',italic=True)
 probe=dl.layout_text('bevietnampro',unicodedata.normalize('NFD','Tiếng Việt có khoảng thở.'),64,420,600)
 assert not probe['missing_glyphs'] and len(probe['lines'])>=2 and all(v<=420 for v in probe['line_widths'])
 assert dl.derive_palette('#000000','triadic')['roles']['on_accent']=='#ffffff'
 narrow=dl.layout_text('notosans','Tiếng Việt cần khoảng thở',54,1500,400,variation_axes={'wdth':75})
 wide=dl.layout_text('notosans','Tiếng Việt cần khoảng thở',54,1500,400,variation_axes={'wdth':100})
 assert narrow['line_widths'][0]<wide['line_widths'][0]
 with pytest.raises(ValueError):TypeStyle(font_id='notosans',variation_axes={'wdth':1000})

def test_style_component_atomicity_and_offline_source(workspace):
 if not (store.ROOT/"engines/node_modules/three").exists():pytest.skip("engine packages not installed (run setup: npm ci in engines/)")
 pid=planned();p=agent.read(pid);voice=sha256(store.folder(pid)/'plan/voice.wav')
 p=dl.apply(pid,p['revision'],{'style_id':'documentary'})
 p=agent.read(pid);dl.compose(pid,p['revision'],{'component':'title','id':'story','end_frame':60,'text':'Rõ một ý','detail':'Một ví dụ','pattern':'grid'})
 p=agent.read(pid);code=Path(scaffold(pid,'remotion')['directory']);entry=code/'index.tsx';original=entry.read_bytes();fonts=store.read_json(code/'input.json')['fonts']
 assert fonts and all((code/'public'/f['src']).is_file() for f in fonts)
 for f in fonts:assert sha256(code/'public'/f['src'])==f['sha256']
 with pytest.raises(ValueError):dl.apply(pid,p['revision'],{'style_id':'short_bold','layer_roles':{'does-not-exist':'title'}})
 assert agent.read(pid)['revision']==p['revision']
 dl.compose(pid,p['revision'],{'component':'lower_third','id':'speaker','end_frame':60,'text':'Nguyễn Ánh','detail':'Người trình bày\nVí dụ minh họa'})
 p=agent.read(pid);layers={l['id']:l for l in p['timeline']['layers']}
 plate=layers['speaker-plate'];detail=layers['speaker-detail'];heading=layers['speaker-heading']
 assert heading['y']+heading['height']<detail['y'] and detail['y']+detail['height']<plate['y']+plate['height']
 with pytest.raises(ValueError):dl.compose(pid,p['revision'],{'component':'lower_third','end_frame':60,'text':'Một tên','detail':'Dòng giải thích dài.\n'*20})
 assert agent.read(pid)['revision']==p['revision']
 with pytest.raises(ValueError):agent.patch(pid,p['revision'],[{'op':'set_design','design':{'typography':{}}}])
 assert agent.read(pid)['revision']==p['revision']
 dl.compose(pid,p['revision'],{'component':'title','id':'story','end_frame':60,'text':'Một ý mới'})
 p=agent.read(pid);assert not any(l['id']=='story-detail' for l in p['timeline']['layers'])
 refresh_payload(pid,code,p['timeline'],p['config']);assert entry.read_bytes()==original
 assert sha256(store.folder(pid)/'plan/voice.wav')==voice
 with pytest.raises(ValueError):dl.compose(pid,p['revision'],{'component':'statistic','end_frame':60,'text':'Sai thiếu nguồn','value':12})
 assert agent.read(pid)['revision']==p['revision']

def test_grapheme_stagger_role_scaling_and_procedural_assets(tmp_path):
 for kind,items in [('pattern',dl.PATTERNS),('icon',dl.ICONS)]:
  for name in items:Layer(id=name,kind=kind,start_frame=0,end_frame=60,data={kind:name})
 with pytest.raises(ValueError):Layer(id='x',kind='icon',start_frame=0,end_frame=60,data={'icon':'<bad>'})
 fx=tmp_path/'fx.cjs';fx.write_bytes((store.ROOT/'engines/effects.js').read_bytes());ds=tmp_path/'ds.cjs';ds.write_bytes((store.ROOT/'engines/design.js').read_bytes())
 code="""const f=require(process.argv[1]),d=require(process.argv[2]);const item={kind:'text',text:'Tiếng <Việt>',typography_role:'headline',effects:[{name:'character_reveal',start_frame:4,end_frame:24,params:{amount:20}}]};const a=f.widget(item,12);f.widget(item,2);const before=f.widget(item,2),after=f.widget(item,24);const role=d.resolve(item,{typography:{headline:{font_id:'bevietnampro',size:84,weight:700,line_height:1.3,tracking:0}}},640,360);console.log(JSON.stringify({a,before,after,stable:a===f.widget(item,12),role,pat:f.widget({id:'p',kind:'pattern',data:{pattern:'speckles',seed:7}},12)}));"""
 out=json.loads(subprocess.check_output(['node','-e',code,str(fx),str(ds)],text=True,encoding='utf-8'))
 assert out['stable'] and '&lt;' in out['after'] and '<Vie' not in out['a'] and 'opacity:0' in out['before']
 assert out['role']['font_size']==28 and out['role']['_type']['fontWeight']==700
 assert 'patternUnits="userSpaceOnUse"' in out['pat']
