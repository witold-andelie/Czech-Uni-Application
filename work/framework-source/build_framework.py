from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1] / 'outputs' / 'czech-study-platform'
def write(path, value):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(value, encoding='utf-8')
def js(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')

nodes = {}
def obj(i, en, zh, states=None, physical=False, external=False):
    nodes[i] = dict(id=i, kind='object', en=en, zh=zh, physical=physical, external=external)
    for s, se, sz in states or []:
        nodes[s] = dict(id=s, kind='state', owner=i, en=se, zh=sz)
def proc(i, en, zh):
    nodes[i] = dict(id=i, kind='process', en=en, zh=zh)
obj('user','Applicant','申请者',physical=True,external=True)
obj('editor','Content Reviewer','内容审核者',physical=True,external=True)
obj('platform','Czech Opportunity Platform','捷克留学与科研平台')
obj('need','Opportunity Need','机会需求')
obj('shortlist','Opportunity Shortlist','机会候选清单')
obj('catalog','Published Catalogue','已发布目录')
obj('source','Official Source','官方来源',external=True)
obj('evidence','Source Evidence','来源证据')
obj('facts','Structured Record','结构化记录',[
 ('draft','draft','待核验'),('verified','verified','已核验'),('rejected','rejected','不符合发布要求')])
obj('snapshot','Publication Snapshot','发布快照',[
 ('live','current','当前版本'),('stale','needs review','待复核'),('archived','archived','已归档')])
obj('bundle','Translation Bundle','三语内容包',[
 ('translated','draft','翻译草稿'),('reviewed','reviewed','三语已复核')])
obj('quality','Content Rules','数据与翻译发布规则')
obj('locale','UI Locale','界面语言',[
 ('zh','zh-CN','简体中文'),('enui','en','English'),('csui','cs','Čeština')])
obj('language','Teaching Language Choice','授课语言选择',[
 ('unset','unset','尚未选择'),('english','English','英语授课'),('czech','Czech','捷克语授课'),('alllang','all','全部授课语言')])
obj('query','Search Criteria','检索条件')
obj('results','Programme Results','专业检索结果')
obj('detail','Opportunity Detail','机会详情')
obj('selection','Comparison Selection','比较项选择')
obj('comparison','Comparison View','比较视图')
obj('intent','Locale Choice','用户界面语言选择')
obj('context','Browsing Context','浏览上下文与收藏')
obj('screen','Localized Interface','当前语言界面')
obj('tokens','Design Rules','UI 设计规则')
obj('deadline','Deadline and Source Change','截止与源更新信号')
obj('request','Acquisition Request','采集请求',[
 ('pending','pending','待提取'),('difficult','difficult','正文缺失或动态页面'),('acquired','acquired','已获取正文'),('failed','failed','尝试后仍失败')])
obj('gettool','Scrapling GET','本机 Scrapling 普通提取')
obj('fetchtool','Scrapling DynamicFetcher','本机 Scrapling 动态提取')
obj('queue','Manual Review Queue','人工核验队列')
obj('rules','Extraction Rules','提取与访问规则')
obj('jobs','Research Job Record','科研岗位记录',[
 ('uncheckedjob','unchecked','资格未核验'),('eligiblejob','master eligible and paid','硕士可申请且确认带薪'),('otherjob','other or unresolved','其他资格或证据不足')])
obj('jobcriteria','Job Criteria','工作语言与博士注册偏好')
obj('jobresults','Research Job Results','带薪科研检索结果')
obj('degree','Degree Requirement','学位要求')
obj('phd','Doctoral Enrollment Requirement','博士注册要求')
obj('pay','Compensation Terms','报酬与工时口径')
obj('worklang','Working Languages','工作语言')
obj('institution','Institution','独立高校或科研机构')
obj('programme','Programme','学术项目')
obj('offering','Programme Offering','语言轨道与年度方案')
obj('round','Admission Round','申请轮次')
obj('teaching','Teaching Languages','方案授课语言')
obj('extra','Additional Language Requirements','实习与临床等额外语言要求')
obj('web','Public Website','三语公网站')
obj('admin','Editorial Console','审核后台')
obj('ingestion','Ingestion Service','采集服务')
obj('db','PostgreSQL Database','PostgreSQL 数据库（建议 Supabase）')
obj('cache','Published Data Cache','发布数据缓存')
obj('dbdecision','Database Choice','数据库选择建议')
obj('private','Editorial Data Store','内部核验数据')

for args in [
 ('support','Opportunity Finding','寻找留学与科研机会'),
 ('discover','Programme Discovering','发现学位项目'),
 ('maintain','Catalogue Maintaining','维护可信目录'),
 ('render','Interface Presenting','呈现三语界面'),
 ('research','Research Opportunity Finding','寻找带薪科研机会'),
 ('choose_en','English Teaching Choosing','选择英语授课'),
 ('choose_cs','Czech Teaching Choosing','选择捷克语授课'),
 ('choose_all','All Teaching Choosing','选择全部授课语言'),
 ('filter','Programme Filtering','按语言优先筛选'),
 ('inspect','Detail Inspecting','查看资格与来源'),
 ('save','Opportunity Saving','收藏机会'),
 ('compare','Opportunity Comparing','比较机会'),
 ('switch','Locale Switching','切换界面语言'),
 ('present','Localized Page Rendering','渲染当前语言页面'),
 ('acquire','Evidence Acquiring','获取官方证据'),
 ('normalize','Record Structuring','结构化来源事实'),
 ('verify','Record Verifying','核验关键字段'),
 ('reject','Record Rejecting','标记不符合发布要求'),
 ('translate','Content Translating','生成三语译文'),
 ('review','Translation Reviewing','复核三语内容'),
 ('publish','Snapshot Publishing','发布一致版本'),
 ('invalidate','Snapshot Invalidating','标记源更新待复核'),
 ('archive','Snapshot Archiving','归档截止或撤回记录'),
 ('retry','Record Repreparing','准备新核验版本'),
 ('simple','Ordinary Evidence Fetching','普通页面提取成功'),
 ('detect','Difficult Page Detecting','识别难提取页面'),
 ('dynamic','Dynamic Evidence Fetching','Scrapling 动态提取成功'),
 ('fail','Acquisition Failure Recording','记录动态提取失败'),
 ('escalate','Manual Review Queuing','登记人工处理'),
 ('jobverify','Master Eligibility Verifying','核验硕士资格与带薪证据'),
 ('jobother','Other Eligibility Recording','记录其他资格或未知'),
 ('jobfilter','Research Job Filtering','按工作语言与博士要求筛选'),
 ('store','Reviewed Data Storing','存储核验数据'),
 ('export','Public Snapshot Exporting','导出公网站快照'),
]: proc(*args)

diagrams=[]
def diagram(i,title,parent,edges,requirements,notes):
    diagrams.append(dict(id=i,title=title,parent=parent,edges=[dict(source=s,target=t,type=k) for s,t,k in edges],requirements=requirements,notes=notes))
diagram('SD','系统环境与主要价值',None,[
 ('user','support','agent'),('platform','support','instrument'),('need','support','instrument'),
 ('catalog','support','instrument'),('support','shortlist','result')],[],
 '平台帮助申请者形成候选清单；申请者自行通过官方入口申请。SD0 展开主过程。')
diagram('SD0','机会发现主过程展开','support',[
 ('user','discover','agent'),('catalog','discover','instrument'),('need','discover','instrument'),('platform','discover','instrument'),('discover','shortlist','effect'),
 ('user','research','agent'),('catalog','research','instrument'),('need','research','instrument'),('platform','research','instrument'),('research','shortlist','effect'),
 ('user','render','agent'),('platform','render','instrument'),('catalog','render','instrument'),('render','screen','result')],['A01','A02','A10'],
 '主过程的三个子过程；项目与岗位是替代任务路径，不要求先选择授课语言才能找工作。shortlist 首次使用时由父过程创建，子过程更新。')
diagram('SD1','按授课语言优先发现项目','discover',[
 ('user','choose_en','agent'),('choose_en','english','output'),('unset','choose_en','input'),
 ('user','choose_cs','agent'),('choose_cs','czech','output'),('unset','choose_cs','input'),
 ('user','choose_all','agent'),('choose_all','alllang','output'),('unset','choose_all','input'),
 ('language','filter','instrument'),('query','filter','instrument'),('catalog','filter','instrument'),('filter','results','result'),
 ('results','inspect','instrument'),('user','inspect','agent'),('inspect','detail','result'),
 ('detail','save','instrument'),('user','save','agent'),('save','shortlist','effect'),
 ('selection','compare','instrument'),('catalog','compare','instrument'),('compare','comparison','result')],['A01','A04','A05','A06','A07','A15'],
 '展示首次选择；后续改选用相同 Choosing 过程的 effect 变体，不强制退回首页。filter 必须先读取语言状态，unset 时展示选择控件不执行限定语言查询。英语入口默认仅英语独立轨道。')
diagram('SD2','界面语言独立切换与呈现','render',[
 ('user','switch','agent'),('intent','switch','instrument'),('switch','locale','effect'),
 ('locale','present','instrument'),('context','present','instrument'),('language','present','instrument'),
 ('reviewed','present','instrument'),('tokens','present','instrument'),('catalog','present','instrument'),('present','screen','result')],['A02','A03','A13','A14','A16'],
 'switch 仅改变 UI Locale，不改变 Teaching Language Choice 或 Browsing Context；locale 三个状态互斥。翻译包已复核状态是界面呈现所需资源，原文附录允许保留源语言。')
diagram('SD3','可信目录维护与三语发布','maintain',[
 ('source','acquire','instrument'),('acquire','evidence','result'),
 ('evidence','normalize','instrument'),('normalize','draft','result'),
 ('draft','verify','input'),('verify','verified','output'),('editor','verify','agent'),('evidence','verify','instrument'),('quality','verify','instrument'),
 ('draft','reject','input'),('reject','rejected','output'),('editor','reject','agent'),
 ('verified','translate','instrument'),('translate','translated','result'),
 ('translated','review','input'),('review','reviewed','output'),('editor','review','agent'),('evidence','review','instrument'),
 ('verified','publish','instrument'),('reviewed','publish','instrument'),('quality','publish','instrument'),('publish','live','result'),('publish','catalog','effect'),
 ('live','invalidate','input'),('invalidate','stale','output'),('deadline','invalidate','instrument'),
 ('live','archive','input'),('archive','archived','output'),('deadline','archive','instrument'),('archive','catalog','effect'),
 ('stale','retry','instrument'),('evidence','retry','instrument'),('retry','draft','result')],['A03','A06','A08','A11'],
 '维护是独立支撑过程，不是用户发现过程的子过程。verified 与 reviewed 必须指向相同源哈希，发布为 AND 条件。更新创建新内容版本，旧快照保留审计。过期状态可优先更新，不能继续表示开放。')
diagram('OPS','目录维护的支撑环境',None,[
 ('editor','maintain','agent'),('platform','maintain','instrument'),('source','maintain','instrument'),('quality','maintain','instrument'),('maintain','catalog','effect')],['A08','A09'],
 '独立支撑过程的上下文，SD3 展开 maintain；采集与审核不阻塞在线用户查询。')
diagram('SD4','官方采集与 Scrapling 升级','acquire',[
 ('source','simple','instrument'),('gettool','simple','instrument'),('pending','simple','input'),('simple','acquired','output'),('simple','evidence','result'),
 ('source','detect','instrument'),('rules','detect','instrument'),('pending','detect','input'),('detect','difficult','output'),
 ('source','dynamic','instrument'),('fetchtool','dynamic','instrument'),('difficult','dynamic','input'),('dynamic','acquired','output'),('dynamic','evidence','result'),
 ('fetchtool','fail','instrument'),('source','fail','instrument'),('difficult','fail','input'),('fail','failed','output'),
 ('failed','escalate','instrument'),('escalate','queue','effect')],['A09'],
 '成功与失败分支互斥，判定依赖真实响应和正文完整性；不以 HTTP 200 作为成功充分条件。动态失败前必须有真实 Scrapling 尝试日志，来源始终作为 instrument，绝不被消耗。')
diagram('SD5','硕士可申请的带薪科研资格','research',[
 ('jobs','degree','exhibition'),('jobs','phd','exhibition'),('jobs','pay','exhibition'),('jobs','worklang','exhibition'),
 ('uncheckedjob','jobverify','input'),('jobverify','eligiblejob','output'),('evidence','jobverify','instrument'),('editor','jobverify','agent'),
 ('uncheckedjob','jobother','input'),('jobother','otherjob','output'),('evidence','jobother','instrument'),('editor','jobother','agent'),
 ('eligiblejob','jobfilter','instrument'),('jobcriteria','jobfilter','instrument'),('catalog','jobfilter','instrument'),('jobfilter','jobresults','result'),
 ('jobresults','save','instrument'),('user','save','agent'),('save','shortlist','effect')],['A07','A10','A11'],
 '资格核验部分属于科研支撑细化；检索只使用同一岗位的已发布当前版本。硕士资格不代表无需读博，unspecified 不能当 not_required，工资数值未公开也须有带薪证据。')
diagram('SD6','平台与数据的对象结构',None,[
 ('platform','web','aggregation'),('platform','admin','aggregation'),('platform','ingestion','aggregation'),('platform','db','aggregation'),('platform','cache','aggregation'),
 ('catalog','institution','aggregation'),('catalog','programme','aggregation'),('catalog','jobs','aggregation'),
 ('programme','offering','aggregation'),('offering','round','aggregation'),('offering','teaching','exhibition'),('offering','extra','exhibition'),
 ('db','store','instrument'),('verified','store','instrument'),('store','private','effect'),
 ('catalog','export','instrument'),('export','cache','effect')],['A12'],
 '对象结构视图；catalog 中这些是记录集合的组成类别而非单个实例数量。PostgreSQL 为逻辑持久层，Supabase 是建议托管方式。store 只更新内部核验数据，公开可见性由 SD3 publish 决定。')

js('opm/model.json',dict(standard='ISO 19450:2024',notation='Explicit OPM semantic mapping to Graphviz DOT',nodes=nodes,diagrams=diagrams))

tokens=dict(color=dict(background='#F5F7FB',surface='#FFFFFF',text='#16263D',muted='#526175',primary='#174DA6',border='#CBD5E1',focus='#145FC0',success='#176447',warning='#875208',error='#B42318'),spacing=[4,8,12,16,24,32,48,64],radius=dict(control=8,card=12),layout=dict(maxWidth=1200,mobilePadding=16,desktopPadding=32),type=dict(bodySize=16,smallSize=14,lineHeight=1.6,fontFamily='system-ui, Segoe UI, Microsoft YaHei, PingFang SC, sans-serif'))
js('design/tokens.json',tokens)
messages={
 'nav.programmes':['学位项目','Degree programmes','Studijní programy'],
 'nav.research':['带薪科研','Paid research jobs','Placené výzkumné pozice'],
 'nav.guides':['申请指南','Application guides','Průvodce přihláškou'],
 'nav.saved':['我的清单','My shortlist','Můj seznam'],
 'locale.label':['界面语言','Interface language','Jazyk rozhraní'],
 'teaching.label':['授课语言','Language of instruction','Vyučovací jazyk'],
 'teaching.prompt':['你想用哪种语言学习？','Which language would you like to study in?','V jakém jazyce chcete studovat?'],
 'teaching.en':['英语授课','Study in English','Studium v angličtině'],
 'teaching.cs':['捷克语授课','Study in Czech','Studium v češtině'],
 'teaching.all':['查看全部授课语言','View all teaching languages','Zobrazit všechny vyučovací jazyky'],
 'teaching.joint':['包含必需双语项目','Include programmes requiring both languages','Zahrnout programy vyžadující oba jazyky'],
 'teaching.additional':['其他语言要求','Additional language requirements','Další jazykové požadavky'],
 'search.placeholder':['搜索专业、学校或城市','Search programmes, institutions or cities','Hledat programy, školy nebo města'],
 'filter.apply':['应用筛选','Apply filters','Použít filtry'],
 'filter.clear':['清空筛选','Clear filters','Vymazat filtry'],
 'action.save':['收藏','Save','Uložit'],
 'action.compare':['比较','Compare','Porovnat'],
 'action.official':['去官网申请','Apply on the official website','Podat přihlášku na oficiálním webu'],
 'status.unknown':['未公布','Not published','Nezveřejněno'],
 'status.review':['待核验','Awaiting verification','Čeká na ověření'],
 'status.closed':['已截止','Closed','Uzavřeno'],
 'status.open':['申请开放','Applications open','Přihlášky otevřeny'],
 'source.label':['官方来源','Official source','Oficiální zdroj'],
 'source.verified':['最后核验','Last verified','Naposledy ověřeno'],
 'empty.title':['没有符合条件的结果','No matching results','Žádné odpovídající výsledky'],
 'empty.help':['试试移除部分筛选条件','Try removing some filters','Zkuste odebrat některé filtry'],
 'error.retry':['加载失败，请重试','Could not load. Please try again.','Načtení se nezdařilo. Zkuste to znovu.'],
 'jobs.master':['硕士可申请','Open to master’s graduates','Pro absolventy magisterského studia'],
 'jobs.phd':['博士注册要求','Doctoral enrollment requirement','Požadavek na zápis do doktorského studia'],
 'jobs.phd.required':['必须注册博士','Doctoral enrollment required','Zápis do doktorského studia je povinný'],
 'jobs.phd.optional':['读博可选','Doctoral enrollment optional','Zápis do doktorského studia je volitelný'],
 'jobs.phd.no':['不要求注册博士','Doctoral enrollment not required','Zápis do doktorského studia není vyžadován'],
 'jobs.phd.unknown':['公告未说明','Not specified in the vacancy','V nabídce neuvedeno'],
 'jobs.language':['工作语言','Working languages','Pracovní jazyky'],
 'jobs.gross':['税前工资','Gross salary','Hrubá mzda'],
}
for n,locale in enumerate(['zh-CN','en','cs']):
    js(f'locales/{locale}.json',{k:v[n] for k,v in messages.items()})
js('locales/glossary.json',dict(status='draft_requires_domain_review',terms=[dict(key=k,**dict(zip(['zh-CN','en','cs'],v))) for k,v in messages.items() if k.startswith(('teaching.','jobs.'))]))

js('schemas/offering.schema.json',{
 '$schema':'https://json-schema.org/draft/2020-12/schema','title':'Programme Offering — foundational contract',
 'type':'object','required':['id','programmeId','academicYear','teachingLanguages','languageMode','languageEvidenceUrl'],
 'properties':{
 'id':{'type':'string','minLength':1},'programmeId':{'type':'string','minLength':1},
 'academicYear':{'type':'string','pattern':'^[0-9]{4}/[0-9]{4}$'},
 'teachingLanguages':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string','pattern':'^[a-z]{2,3}(-[A-Za-z0-9]+)*$'}},
 'languageMode':{'enum':['single','joint_required']},
 'languageEvidenceUrl':{'type':'string','format':'uri'},
 'additionalLanguageRequirements':{'type':'array','items':{'type':'object','required':['language','context','requirement','evidenceUrl'],'properties':{'language':{'type':'string'},'context':{'enum':['admission','placement','clinical','other']},'requirement':{'enum':['required','optional','unknown']},'evidenceUrl':{'type':'string','format':'uri'}}}},
 },'allOf':[{'if':{'properties':{'languageMode':{'const':'single'}}},'then':{'properties':{'teachingLanguages':{'maxItems':1}}}},{'if':{'properties':{'languageMode':{'const':'joint_required'}}},'then':{'properties':{'teachingLanguages':{'minItems':2}}}}],
 'description':'基础语言轨道契约，非完整生产数据库 schema；其余实体按 DATA_MODEL 实施。'})
js('schemas/ui-context.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','required':['uiLocale','teachingLanguage'],'properties':{'uiLocale':{'enum':['zh-CN','en','cs']},'teachingLanguage':{'enum':['en','cs','all',None]},'includeJointRequired':{'type':'boolean','default':False},'savedIds':{'type':'array','uniqueItems':True,'items':{'type':'string'}}}})

tasks=[
 ('T01','三语界面与语言优先入口',[],['SD1','SD2'],['A01','A02','A03']),
 ('T02','项目实体与语言轨道数据契约',['T01'],['SD6'],['A04','A05','A12']),
 ('T03','项目检索、详情、比较收藏',['T02'],['SD1'],['A06','A07','A15']),
 ('T04','官方采集与 Scrapling 适配',['T02'],['SD4'],['A09']),
 ('T05','审核、三语翻译和一致发布',['T04'],['SD3'],['A08','A11']),
 ('T06','硕士带薪科研与博士要求筛选',['T05'],['SD5'],['A07','A10','A11']),
 ('T07','响应式、可访问性和大陆线路验收',['T03','T06'],['SD2'],['A13','A14','A16']),
]
js('opm/backlog.json',[dict(id=i,title=t,dependsOn=d,models=m,acceptance=a,status='not_started') for i,t,d,m,a in tasks])
js('data/sources/registry.json',[
 dict(id='studyin',url='https://portal.studyin.cz/en/',purpose='programme discovery',official=True,collectionStatus='not_started'),
 dict(id='euraxess',url='https://www.euraxess.cz/jobs/search',purpose='vacancy discovery; filter actual country',official=True,collectionStatus='not_started'),
 dict(id='vspj',url='https://www.vspj.cz/en/skola/obecne-informace',purpose='institution classification',official=True,collectionStatus='not_started')])
for folder,desc in {
 'apps/web':'三语公共页面、语言优先搜索、详情、比较与收藏；当前未实现。',
 'apps/admin':'官方证据、待核验、三语审核和发布；当前未实现。',
 'services/ingestion':'Python 与本机 Scrapling 采集适配；当前未实现。',
 'services/catalog':'目录规则、资格判定、版本发布与搜索数据；当前未实现。',
 'data/published':'仅放经核验的正式发布记录。目前没有正式数据。',
 'work':'项目实施时的临时原始网页、日志与分析；不作为正式发布数据。',
 'schemas':'基础契约。尚非完整生产 schema；实施时依 DATA_MODEL 扩展。',
}.items(): write(f'{folder}/README.md',f'# {folder}\n\n{desc}\n')
print('Generated model, seed dictionaries, schemas, tokens and project module scaffold.')
