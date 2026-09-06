from pathlib import Path
import re,json,collections,hashlib
p=Path(__file__).with_name('guanfu-reference.html')
s=p.read_text(encoding='utf-8')
arrays={}
for m in re.finditer(r'window\.(\w+)\s*=\s*',s):
    try:
        value,end=json.JSONDecoder().raw_decode(s[m.end():])
        if isinstance(value,list): arrays[m.group(1)]=value
    except ValueError: pass
summary={'source':'https://www.guanfu.online/','checked':'2026-09-06','extraction':'Scrapling 0.4.9 GET, HTTP 200','htmlBytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'arrays':{k:{'count':len(v),'fields':list(v[0]) if v else []} for k,v in arrays.items()},'externalScripts':re.findall(r'<script[^>]+src="([^"]+)"',s),'fetchCalls':len(re.findall(r'\bfetch\s*\(',s)),'publicRepositoryLinks':re.findall(r'https://github.com/[^\s"<>]+',s)}
unis=arrays.get('__UNIS__',[])
summary['institutionTypes']=dict(collections.Counter(x.get('typ') for x in unis))
summary['institutionsWithProgrammes']=sum((x.get('studiengang_count') or 0)>0 for x in unis)
summary['fhWithProgrammes']=sum(x.get('typ')=='FH' and (x.get('studiengang_count') or 0)>0 for x in unis)
summary['inlineLogicExcerpts']=[line.strip()[:180] for line in s.splitlines() if len(line)<1000 and re.search(r'__UNIS__|__PROGS__|\.filter\(|function apply|function render|filterPrograms|filterUnis',line)][:18]
out=p.parents[1]/'outputs/czech-study-platform/docs/reference-inspection.json'
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
