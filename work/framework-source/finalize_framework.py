from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[1]/'outputs/czech-study-platform'
p=root/'opm/model.json'
m=json.loads(p.read_text(encoding='utf-8'))
for i,lang in {'web':'TypeScript / Astro / Svelte','admin':'TypeScript / Svelte','ingestion':'Python / Scrapling','db':'SQL / PostgreSQL; Supabase','cache':'Static HTML / JSON'}.items():
    m['nodes'][i]['implementation']=lang
    m['nodes'][i]['zh'] += '\n'+lang
m['nodes']['api']={'id':'api','kind':'object','en':'Online API Service','zh':'在线 API 服务\nGo','physical':False,'external':False,'implementation':'Go'}
for d in m['diagrams']:
    if d['id']=='SD6':
        d['edges'].append({'source':'platform','target':'api','type':'aggregation'})
        d['notes']+=' 模块语言以 LANGUAGE_STACK.md 为准；Go 在线服务、Python 离线采集、静态前台分离。'
        d['requirements'].append('A17')
m['diagrams'].sort(key=lambda d:['SD','SD0','SD1','SD2','OPS','SD3','SD4','SD5','SD6'].index(d['id']))
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for folder,text in {'apps/web':'TypeScript + Astro 静态三语页面；Svelte 局部交互。','apps/admin':'TypeScript + Svelte，复用组件；Go 后台 API。','services/catalog':'Go 领域包，编入 apps/api，不部署为独立微服务。','services/ingestion':'Python + Scrapling 离线采集，隔离浏览器资源。'}.items():
    (root/folder/'README.md').write_text(f'# {folder}\n\n{text}\n\n当前未实现；见 docs/LANGUAGE_STACK.md 与 ARCHITECTURE.md。\n',encoding='utf-8')
backlog=root/'opm/backlog.json'
b=json.loads(backlog.read_text(encoding='utf-8'))
b.append({'id':'T08','title':'在线启动、查询与前端载荷性能验证','dependsOn':['T03','T06'],'models':['SD6'],'acceptance':['A17'],'status':'not_started'})
backlog.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Synchronized module language decisions with model and task framework.')
