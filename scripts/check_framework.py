"""Check local links, locale parity, JSON readability and model output presence."""
from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[1]
errors=[]
json_files=list(root.rglob('*.json'))
for p in json_files:
    try: json.loads(p.read_text(encoding='utf-8'))
    except Exception as ex: errors.append(f'{p.relative_to(root)}: {ex}')
locales=[json.loads((root/'locales'/f'{l}.json').read_text(encoding='utf-8')) for l in ['zh-CN','en','cs']]
if not all(set(x)==set(locales[0]) for x in locales): errors.append('Locale keys differ')
if any(not isinstance(v,str) or not v.strip() for d in locales for v in d.values()): errors.append('Empty locale translation')
for p in root.rglob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if re.match(r'^[a-zA-Z]+:',link) or link.startswith('#'): continue
        if not (p.parent/link.split('#')[0]).exists(): errors.append(f'{p.relative_to(root)} broken link {link}')
m=json.loads((root/'opm/model.json').read_text(encoding='utf-8'))
for d in m['diagrams']:
    for suffix in ['dot','svg','png']:
        p=root/'opm'/f'{d["id"]}.{suffix}'
        if not p.exists() or p.stat().st_size==0: errors.append(f'Missing output {p.name}')
report={'status':'passed' if not errors else 'failed','jsonFilesChecked':len(json_files),'localeKeysPerLanguage':len(locales[0]),'diagramsChecked':len(m['diagrams']),'errors':errors,'applicationTests':'not run: application is not implemented','formalIsoCertification':False}
(root/'docs/framework-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
if errors: raise SystemExit(1)
