"""Validate the explicit OPM subset; generate DOT, SVG, PNG and parallel OPL.
Requires Python 3 and Graphviz dot on PATH. No network or application dependencies.
The checks cover this project's semantic mapping, not complete ISO conformance.
"""
from pathlib import Path
import html
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OPM = ROOT / 'opm'
model = json.loads((OPM / 'model.json').read_text(encoding='utf-8'))
N = model['nodes']
D = model['diagrams']
def q(value):
    return json.dumps(str(value), ensure_ascii=False)
def attrs(values):
    return ', '.join(f'{k}={q(v)}' for k,v in values.items())
def name(i):
    n = N[i]
    if n['kind'] == 'state':
        return f"{N[n['owner']]['en']} in state {n['en']}"
    return n['en']

def validate():
    errors=[]
    allowed={'agent','instrument','result','consumption','effect','input','output','aggregation','exhibition'}
    occurrences={e[x] for d in D for e in d['edges'] for x in ['source','target']}
    for d in D:
        if d['parent'] and d['parent'] not in occurrences:
            errors.append(f"{d['id']}: parent process not present in another diagram")
        pairs=set()
        transitions={}
        changed=set()
        processes=set()
        for e in d['edges']:
            s,t,k=e['source'],e['target'],e['type']
            if s not in N or t not in N or k not in allowed:
                errors.append(f"{d['id']}: unknown endpoint or relation {e}"); continue
            sk,tk=N[s]['kind'],N[t]['kind']
            processes.update(i for i in [s,t] if N[i]['kind']=='process')
            pair=(s,t,k)
            if pair in pairs: errors.append(f"{d['id']}: duplicate {pair}")
            pairs.add(pair)
            valid=True
            if k in {'agent','instrument','consumption'}:
                valid=sk in {'object','state'} and tk=='process'
                if k=='agent': valid=valid and sk=='object' and N[s].get('physical',False)
            elif k in {'result','effect'}:
                valid=sk=='process' and tk in {'object','state'}
            elif k=='input': valid=sk=='state' and tk=='process'
            elif k=='output': valid=sk=='process' and tk=='state'
            elif k in {'aggregation','exhibition'}: valid=sk=='object' and tk=='object'
            if not valid: errors.append(f"{d['id']}: invalid endpoint roles {e}")
            if k in {'result','effect','output'}: changed.add(s)
            if k in {'consumption','input'}: changed.add(t)
            if k in {'input','output'}:
                p=t if k=='input' else s
                state=s if k=='input' else t
                transitions.setdefault(p,{'input':set(),'output':set()})[k].add(N[state]['owner'])
        for p,sets in transitions.items():
            if sets['input'] != sets['output']:
                errors.append(f"{d['id']}: {p} input/output owner mismatch")
        for p in processes-changed: errors.append(f"{d['id']}: process {p} has no transformation")
    if errors: raise ValueError('\n'.join(errors))

def opl(e):
    s,t,k=e['source'],e['target'],e['type']
    a,b=name(s),name(t)
    return {
       'agent':f'{a} handles {b}.',
       'instrument':f'{b} requires {a}.',
       'result':f'{a} yields {b}.',
       'consumption':f'{b} consumes {a}.',
       'effect':f'{a} affects {b}.',
       'input':f'{b} requires input state {N[s]["en"]} of {N[N[s]["owner"]]["en"]}.' if N[s]['kind']=='state' else '',
       'output':f'{a} yields output state {N[t]["en"]} of {N[N[t]["owner"]]["en"]}.' if N[t]['kind']=='state' else '',
       'aggregation':f'{a} consists of {b}.',
       'exhibition':f'{a} exhibits {b}.',
    }[k]

edge_styles={
 'agent':dict(arrowhead='dot',color='#1F2937'),
 'instrument':dict(arrowhead='odot',color='#64748B'),
 'result':dict(arrowhead='normal',color='#166534'),
 'consumption':dict(arrowhead='normal',color='#9F1239'),
 'effect':dict(dir='both',arrowhead='normal',arrowtail='normal',color='#174DA6'),
 'input':dict(arrowhead='normal',color='#B45309'),
 'output':dict(arrowhead='normal',color='#166534'),
 'aggregation':dict(dir='back',arrowtail='normal',color='#475569'),
 'exhibition':dict(dir='none',color='#64748B',style='dashed'),
}

def dot(d):
    ids={e[x] for e in d['edges'] for x in ['source','target']}
    owners={N[i]['owner'] for i in ids if N[i]['kind']=='state'}
    owners.update(i for i in ids if any(n.get('owner')==i for n in N.values()))
    # State expression displays all states of each represented stateful object.
    for owner in list(owners):
        ids.add(owner)
        ids.update(i for i,n in N.items() if n.get('owner')==owner)
    lines=[f'digraph {d["id"]} {{',
      '// Explicit OPM-to-DOT mapping; see README.md. Layout is not execution order.',
      '  graph ['+attrs(dict(rankdir='LR',compound='true',bgcolor='#FFFFFF',pad='0.3',nodesep='0.38',ranksep='0.65',splines='spline',fontname='Microsoft YaHei',fontsize='18',labelloc='t',label=f'{d["id"]}  {d["title"]}\nISO 19450:2024 · OPM semantic mapping / DOT'))+'];',
      '  node [fontname="Microsoft YaHei", fontsize="11", margin="0.14,0.10", penwidth="1.3"];',
      '  edge [fontname="Segoe UI", fontsize="9", arrowsize="0.7", penwidth="1.1"];']
    for owner in sorted(owners):
        n=N[owner]
        lines.append(f'  subgraph cluster_{owner} {{')
        lines.append('    graph ['+attrs(dict(label=f'{n["zh"]}\n{n["en"]}',color='#64748B',style='solid',fontsize='12',opm_kind='object',opm_id=owner))+'];')
        if owner in {e[x] for e in d['edges'] for x in ['source','target']}:
            lines.append(f'    {owner} ['+attrs(dict(label='',shape='point',width='0.01',style='invis',opm_kind='object',opm_anchor='true'))+'];')
        for i in sorted(ids):
            sn=N[i]
            if sn.get('owner')==owner:
                lines.append(f'    {i} ['+attrs(dict(label=f'{sn["zh"]}\n{sn["en"]}',shape='box',style='rounded,filled',fillcolor='#FFF7E6',color='#B7791F',opm_kind='state',opm_owner=owner))+'];')
        lines.append('  }')
    for i in sorted(ids):
        n=N[i]
        if n['kind']=='state' or i in owners: continue
        values=dict(label=f'{n["zh"]}\n{n["en"]}',shape='ellipse' if n['kind']=='process' else 'box',style='filled',fillcolor='#EFF6FF' if n['kind']=='process' else '#F8FAFC',color='#174DA6' if n['kind']=='process' else '#64748B',opm_kind=n['kind'])
        if n.get('external'): values['style']='dashed,filled'
        if n.get('physical'): values['penwidth']='2.6'
        lines.append(f'  {i} ['+attrs(values)+'];')
    for e in d['edges']:
        st=dict(edge_styles[e['type']],label=e['type'],opm_relation=e['type'])
        if e['source'] in owners: st['ltail']='cluster_'+e['source']
        if e['target'] in owners: st['lhead']='cluster_'+e['target']
        lines.append(f'  {e["source"]} -> {e["target"]} ['+attrs(st)+'];')
    lines.append('}')
    return '\n'.join(lines)+'\n'

def main():
    validate()
    executable=shutil.which('dot')
    if not executable: raise RuntimeError('Graphviz dot is required on PATH.')
    opl_lines=['# OPL semantic companion','',
      'Generated from model.json, together with DOT. English sentences express the same typed relations. State pairs below are a readable OPL subset, not a certified OPL parser export.', '']
    cards=[]
    for d in D:
        base=OPM / d['id']
        base.with_suffix('.dot').write_text(dot(d),encoding='utf-8')
        for fmt in ['svg','png']:
            subprocess.run([executable,f'-T{fmt}',str(base.with_suffix('.dot')),'-o',str(base.with_suffix('.'+fmt))],check=True,capture_output=True,text=True)
        opl_lines += [f'## {d["id"]} — {d["title"]}', '', 'Refines: '+(name(d['parent']) if d['parent'] else 'Context / structural view'), '', d['notes'], '']
        represented={e[x] for e in d['edges'] for x in ['source','target']}
        represented.update(N[i]['owner'] for i in list(represented) if N[i]['kind']=='state')
        for i in sorted(represented):
            states=[n['en'] for n in N.values() if n.get('owner')==i]
            if states: opl_lines.append(f'- {name(i)} can be '+', '.join(states)+'.')
        # Replace paired state links with one state-change sentence.
        consumed=set()
        for e in d['edges']:
            if e['type']=='input':
                out=next(x for x in d['edges'] if x['type']=='output' and x['source']==e['target'] and N[x['target']]['owner']==N[e['source']]['owner'])
                opl_lines.append(f'- {name(e["target"])} changes {N[N[e["source"]]["owner"]]["en"]} from {N[e["source"]]["en"]} to {N[out["target"]]["en"]}.')
                consumed.add((out['source'],out['target'],'output'))
            elif e['type']!='output': opl_lines.append('- '+opl(e))
        opl_lines.append('')
        title=html.escape(f'{d["id"]} · {d["title"]}')
        cards.append(f'<section id="{d["id"]}"><h2>{title}</h2><p>{html.escape(d["notes"])}</p><p><a href="{d["id"]}.svg" target="_blank">打开可缩放 SVG</a> · <a href="{d["id"]}.dot">DOT 源码</a> · <a href="{d["id"]}.png">PNG</a></p><div class="figure"><img src="{d["id"]}.svg" alt="{title}"></div></section>')
    (OPM/'OPL.md').write_text('\n'.join(opl_lines),encoding='utf-8')
    nav=' · '.join(f'<a href="#{d["id"]}">{html.escape(d["id"])}</a>' for d in D)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>捷克留学与科研平台 · OPM 图集</title><style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#16263d;background:#f5f7fb;margin:0;line-height:1.7}main{max-width:1240px;margin:auto;padding:32px 20px}h1{font-size:30px}section{background:white;border:1px solid #cbd5e1;border-radius:12px;padding:24px;margin:24px 0}a{color:#174da6}nav{position:sticky;top:0;background:#f5f7fb;padding:12px 0}.figure{overflow:auto;border-top:1px solid #e2e8f0;padding-top:16px}.figure img{display:block;max-width:100%;height:auto}aside{border-left:4px solid #174da6;padding-left:16px}small{color:#526175}</style><main><h1>捷克留学与带薪科研平台</h1><p>ISO 19450:2024 · OPM 对象过程模型 · DOT 可编辑框架</p><aside>方框＝对象，椭圆＝过程，所属对象框内的圆角框＝状态。边上的标签是关系语义；图的排版不表示执行顺序。DOT 图形映射与标准原生符号存在差异，见 <a href="README.md">模型说明</a>。本图集是项目文档，不是最终产品界面。</aside><p><a href="OPL.md">对应英文 OPL</a> · <a href="../docs/UI_RULES.md">UI 约束</a> · <a href="../docs/DATABASE.md">数据库建议</a></p><nav>'''+nav+'</nav>'+''.join(cards)+'<small>生成日期：2026-09-06。所有图使用本地资源，无外部字体、翻译或脚本。</small></main></html>'
    (OPM/'index.html').write_text(page,encoding='utf-8')
    report=dict(result='passed',scope='Project OPM mapping checks and Graphviz syntax/rendering; not complete ISO certification',diagrams=len(D),relationships=sum(len(d['edges']) for d in D),dot=True,svg=True,png=True)
    (OPM/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__': main()
