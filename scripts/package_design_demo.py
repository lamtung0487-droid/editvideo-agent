"""Bundle actual atlas render sources and visual specimens for review/reuse."""
import hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs'
record=json.loads((OUT/'design-atlas.json').read_text(encoding='utf-8'))
files=[ROOT/'docs/DESIGN_LIBRARY.md',OUT/'design-atlas.json',OUT/'design-font-browser-proof.json',OUT/'design-engine-comparison.json',OUT/'design-verification.json',OUT/'design-test-log.txt']
for engine,entry in record['engines'].items():
 source=Path(entry['report']['source_manifest']).parent/'delivery.zip'
 copied=OUT/f'design-library-{engine}.zip';shutil.copyfile(source,copied)
 with zipfile.ZipFile(copied) as archive:assert archive.testzip() is None
 files.extend([copied,Path(entry['video'])])
files.extend((OUT/'design-previews').glob('*.png'));files.extend((OUT/'design-previews').glob('*.jpg'))
files.extend(OUT.glob('design-*-sheet.jpg'))
target=OUT/'design-library-demo.zip'
manifest={}
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
 for file in sorted(set(files)):
  relative=file.relative_to(ROOT).as_posix();archive.write(file,relative);manifest[relative]=hashlib.sha256(file.read_bytes()).hexdigest()
 archive.writestr('DEMO_MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(target) as archive:assert archive.testzip() is None
result={'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size,'files':len(manifest),'scope':'Silent60s dual-engine dictionary, editable source exports include local font files/licenses; previews and guide. No model weights or API keys. Absolute observation paths in JSON identify this machine; use bundled previews for portable review.'}
(OUT/'design-demo-package.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
