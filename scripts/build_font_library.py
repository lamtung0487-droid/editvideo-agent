"""Acquire unmodified open fonts/notices from a pinned Google Fonts revision.

Development acquisition only; delivered system already contains these assets.
Uses the agent-reach documented GitHub CLI backend for repository discovery.
"""
import concurrent.futures,hashlib,json,subprocess,unicodedata
from pathlib import Path
from urllib.parse import quote
import httpx
from fontTools.ttLib import TTFont

ROOT=Path(__file__).resolve().parents[1]
REF='bd8f81ddb5c74d5c8897b36ad88b440266245103'
FAMILIES=[('bevietnampro','Be Vietnam Pro','sans','Vietnamese narration, captions, contemporary knowledge'),('notosans','Noto Sans','sans','Dense explanations, multilingual captions'),('notoserif','Noto Serif','serif','Documentary, quotations, editorial chapters'),('manrope','Manrope','sans','Clean technology, diagrams'),('archivo','Archivo','sans','Bold explanation, sports titles'),('oswald','Oswald','condensed','Short display titles, narrow labels; not long body text'),('bitter','Bitter','serif','Robust editorial statements'),('lora','Lora','serif','Literature, culture, quotations'),('ibmplexmono','IBM Plex Mono','mono','Code, units, technical labels; not paragraph captions'),('comfortaa','Comfortaa','rounded','Friendly introductory explainers'),('robotoslab','Roboto Slab','slab','Science and structured knowledge'),('inter','Inter','sans','Neutral modern education'),('sourcesans3','Source Sans 3','sans','Readable body and analytical charts'),('vollkorn','Vollkorn','serif','History and narrative chapters'),('lexend','Lexend','sans','Open letterforms for explanations'),('montserrat','Montserrat','sans','Display headings and clean geometry')]
SAMPLE='Tiếng Việt: Nguyễn Ánh, Trường học, kỹ thuật, dữ liệu, Ắ Ằ Ẳ Ẵ Ặ Ấ Ầ Ẩ Ẫ Ậ Ế Ề Ể Ễ Ệ Ố Ồ Ổ Ỗ Ộ Ớ Ờ Ở Ỡ Ợ Ứ Ừ Ử Ữ Ự Đ đ Ỳ Ỵ Ỷ Ỹ 0123456789'
def build(spec):
 fid,family,category,use=spec
 upstream_dir='apache' if fid=='robotoslab' else 'ofl'
 license_name='LICENSE.txt' if fid=='robotoslab' else 'OFL.txt'
 listing=json.loads(subprocess.check_output(['gh','api',f'repos/google/fonts/contents/{upstream_dir}/{fid}?ref={REF}'],text=True))
 names=[r['name'] for r in listing if r['name'].endswith('.ttf')]
 variable=[n for n in names if '[' in n and 'Italic' not in n]
 selected=variable[:1] or [n for n in names if any(n.endswith('-'+s+'.ttf') for s in ('Regular','Bold','SemiBold'))]
 if fid in ('bevietnampro','notoserif','lora'):
  selected += [n for n in names if ('Italic[' in n or n.endswith('-Italic.ttf'))][:1]
 folder=ROOT/'assets/fonts'/fid;folder.mkdir(parents=True,exist_ok=True)
 faces=[]
 with httpx.Client(timeout=90,follow_redirects=True) as client:
  for name in [*selected,license_name]:
   url=f'https://raw.githubusercontent.com/google/fonts/{REF}/{upstream_dir}/{fid}/{quote(name)}'
   response=client.get(url);response.raise_for_status();blob=response.content
   if len(blob)>6*1024*1024:raise ValueError('Unexpected oversized font')
   path=folder/name;path.write_bytes(blob)
   if name==license_name:continue
   with TTFont(path) as font:
    cmap=font.getBestCmap();missing=sorted({c for c in unicodedata.normalize('NFC',SAMPLE) if not c.isspace() and ord(c) not in cmap})
    if missing:raise ValueError(f'{family} lacks Vietnamese glyphs: {missing}')
    axes={a.axisTag:[a.minValue,a.defaultValue,a.maxValue] for a in font['fvar'].axes} if 'fvar' in font else {}
    weight=axes.get('wght',[font['OS/2'].usWeightClass]*3)
    faces.append({'file':f'{fid}/{name}','sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'weight':str(int(weight[0]))+' '+str(int(weight[2])) if weight[0]!=weight[2] else str(int(weight[0])),'style':'italic' if 'Italic' in name else 'normal','axes':axes,'source':url,'vietnamese_nfc_missing':missing})
 if upstream_dir=='apache':
  response=httpx.get(f'https://raw.githubusercontent.com/google/fonts/{REF}/apache/{fid}/COPYRIGHT.txt');response.raise_for_status();(folder/'COPYRIGHT.txt').write_bytes(response.content)
 return {'id':fid,'family':family,'category':category,'use':use,'license':'Apache License 2.0' if upstream_dir=='apache' else 'SIL Open Font License 1.1','license_file':f'{fid}/{license_name}','license_sha256':hashlib.sha256((folder/license_name).read_bytes()).hexdigest(),'faces':faces}
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:fonts=list(pool.map(build,FAMILIES))
 manifest={'upstream':'google/fonts','revision':REF,'coverage_sample':SAMPLE,'normalization':'NFC; this is a Vietnamese probe, not exhaustive Unicode coverage','fonts':fonts}
 (ROOT/'assets/fonts/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'families':len(fonts),'faces':sum(len(f['faces']) for f in fonts),'bytes':sum(x['bytes'] for f in fonts for x in f['faces'])}))
