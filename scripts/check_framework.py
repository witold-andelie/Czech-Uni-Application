"""Check local links, locale parity, JSON readability and OPM outputs."""
from pathlib import Path
import json
import os
import re
import sys

root=Path(__file__).resolve().parents[1]
errors=[]
skip_dirs={'.git','.astro','.generated','node_modules','dist','work','staging','__pycache__','test-results','playwright-report','blob-report'}

def project_files(suffix):
    result=[]
    for directory, directories, files in os.walk(root):
        directories[:] = [name for name in directories if name not in skip_dirs]
        base=Path(directory)
        result.extend(base/name for name in files if name.endswith(suffix))
    return result

json_files=project_files('.json')
for p in json_files:
    try: json.loads(p.read_text(encoding='utf-8'))
    except Exception as ex: errors.append(f'{p.relative_to(root)}: {ex}')
locales=[json.loads((root/'locales'/f'{l}.json').read_text(encoding='utf-8')) for l in ['zh-CN','en','cs']]
if not all(set(x)==set(locales[0]) for x in locales): errors.append('Locale keys differ')
if any(not isinstance(v,str) or not v.strip() for d in locales for v in d.values()): errors.append('Empty locale translation')
for p in [q for q in project_files('.md') if q.name == 'README.md']:  # only tracked README is public; other docs stay local
    if p.name != 'README.md':
        continue
    for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if re.match(r'^[a-zA-Z]+:',link) or link.startswith('#'): continue
        target=link.split('#')[0].strip('<>')
        if target and not (p.parent/target).exists(): errors.append(f'{p.relative_to(root)} broken link {link}')
m=json.loads((root/'opm/model.json').read_text(encoding='utf-8'))
sys.path.insert(0, str(root/'scripts'))
from render_opm import check_generated
errors.extend(check_generated())
report={'status':'passed' if not errors else 'failed','jsonFilesChecked':len(json_files),'localeKeysPerLanguage':len(locales[0]),'diagramsChecked':len(m['diagrams']),'opmGenerationCheck':'semantic DOT/OPL/SVG titles and PNG magic; Graphviz metadata is not compared as bytes','errors':errors,'applicationTests':'run separately; see PROGRESS.md','formalIsoCertification':False}
(root/'work').mkdir(exist_ok=True)
(root/'work/framework-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
if errors: raise SystemExit(1)
