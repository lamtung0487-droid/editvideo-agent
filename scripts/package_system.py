"""Pack the agent system source; exclude credentials, caches and user projects."""
import hashlib
import json
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"outputs";OUTPUT.mkdir(exist_ok=True)
target=OUTPUT/"editvideo-agent-system.zip"
top=["README.md","requirements.txt","requirements.lock.txt","requirements.vision.txt","requirements.temporal.txt","run.py","setup.ps1","start.ps1",".mcp.json",".mcp.compact.example.json","pytest.ini"]
folders=["editvideo","docs","tests","scripts",".agents/skills/editvideo-agent",".claude/skills/editvideo-agent"]
files=[ROOT/name for name in top]
for name in folders:
    files.extend(p for p in (ROOT/name).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py",".tsx",".md",".yaml",".json",".ps1"))
files.extend(p for p in (ROOT/"engines").iterdir() if p.is_file() and p.suffix in (".js",".mjs",".tsx",".json"))
# Include only registry-listed open fonts and their license/copyright notices.
font_root=ROOT/'assets/fonts';font_manifest=json.loads((font_root/'manifest.json').read_text(encoding='utf-8'))
files.append(font_root/'manifest.json')
for family in font_manifest['fonts']:
    files.append(font_root/family['license_file'])
    files.extend(font_root/f['file'] for f in family['faces'])
    copyright=font_root/family['id']/'COPYRIGHT.txt'
    if copyright.exists():files.append(copyright)
lut_root=ROOT/'assets/luts';lut_manifest=json.loads((lut_root/'manifest.json').read_text(encoding='utf-8'))
files.append(lut_root/'manifest.json');files.extend(lut_root/lut['file'] for lut in lut_manifest['luts'])
hashes={}
with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        relative=path.relative_to(ROOT).as_posix();archive.write(path,relative);hashes[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    archive.writestr("SOURCE_MANIFEST.json",json.dumps(hashes,indent=2))
manifest={"source_zip":str(target),"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"files":len(hashes),"bytes":target.stat().st_size,
    "notes":"Source, locks, skills, verified open fonts/licenses and 6 original display-BT709 LUTs. Run setup.ps1, adjust machine-specific .mcp.json paths, connect Claude/Codex; compact configuration is optional. Large models, user media, credentials and browser caches excluded."}
(OUTPUT/"system-package.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(manifest))
