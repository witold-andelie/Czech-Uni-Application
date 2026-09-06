from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]/'outputs/czech-study-platform'
def append(path,text):
    p=root/path
    p.write_text(p.read_text(encoding='utf-8')+'\n'+text+'\n',encoding='utf-8')
def replace(path,a,b):
    p=root/path
    s=p.read_text(encoding='utf-8')
    assert a in s,path
    p.write_text(s.replace(a,b),encoding='utf-8')
replace('docs/CRAWLING_RULES.md','建议频率：院校身份每月；项目每周，开放申请期每日；正在招聘的职位每日，临近截止按合理频率复核。上线配置可调整。','固定策略：每隔五天（120 小时）启动一轮覆盖全体已登记捷克高校相关信息的采集。包含院校、专业、招生和已登记招聘来源；失败单独重试，不能把部分成功报为全量完成。岗位关闭另设轻量状态核查与已知截止计时，详见 REFRESH_POLICY.md。')
replace('docs/PRODUCT.md','博士后不进入默认硕士可申请结果。截止岗位默认归档，仍可明确标记后查看。','博士后不进入默认硕士可申请结果。确认关闭／截止的岗位自动从公开招聘列表下架，保留内部归档；旧收藏与详情只显示关闭状态并禁用申请。岗位标题及“立即申请”直接链接官方申请页，站内解释通过独立“查看本站解读”入口提供。')
append('docs/PRODUCT.md','''## 五天刷新、广覆盖与申请直达

按 docs/REFRESH_POLICY.md 执行。高校范围以捷克现行官方名录为基线，覆盖公立、国立、私立与应用／职业导向高校，不按排名排除学校，不因缺英语页面漏掉捷克语来源。
学校名录覆盖、已接入来源覆盖、项目收录完整度分别统计，不用学校数量冒充项目覆盖。
五天采集属于待实现的网站后台任务，不是本地聊天提醒。任务在部署环境持续运行，不依赖个人电脑开机。
岗位卡片标题和主要动作一键到官方申请页；不要求本站登录或先进入本站详情。无独立申请系统而仅接受邮件时，跳转明确给出申请办法的官方公告，显示“查看官方申请说明”，不伪造申请表。''')
append('docs/UI_RULES.md','''## 岗位卡片直达规则（用户新增要求）

- 岗位标题和“立即申请”使用真实 applicationUrl 的普通链接，点击直接打开官方申请目标，不经过本站登录或中间广告页。
- 可另设“查看本站解读”次级入口，不能替代标题直达行为；收藏按钮不得嵌套在标题链接中。
- 显示外部链接提示与官方目标域名；官方指定第三方招聘系统属于可接受申请入口，须有官方来源证明。
- 缺独立表单而采用邮件申请时，明确标为“查看官方申请说明”并链接公告；邮件发送始终由用户操作。
- 已关闭岗位从公开列表移除。旧收藏可显示“已关闭”，禁用申请并提供移除收藏操作。
- 静态缓存同样遵循关闭状态覆盖和过期时间，三语同步下架，不允许一种语言仍可申请。''')
append('docs/DATA_MODEL.md','''## 刷新、覆盖与岗位生命周期字段

CrawlRun：id、scheduledAt、startedAt、finishedAt、scopeVersion、expectedSources、successfulSources、failedSources、status（queued/running/partial/succeeded/failed）、retryCount。
SourceRegistry：institutionId、sourceType、sourceLanguage、officialUrl、adapter、lastAttemptAt、lastSuccessAt、nextDueAt、failureReason、coverageStatus。官方名录基线保存版本及日期。
ResearchJob 增加：sourceUrl、applicationUrl、applicationMethod（web_form/official_instructions）、applicationHostVerified、applicationUrlCheckedAt、lifecycleStatus（open/closed/expired/unavailable/unknown）、closedAt、closureReason、closureEvidenceId、lastStatusCheckedAt、nextStatusCheckAt、visibility。
所有关闭状态基于同一实体 ID 应用于三语视图、索引和缓存。未知和不可访问不能伪造为已关闭；临时不可访问可暂停展示并保留复核原因。
恢复招聘必须有新的官方开放证据；仅页面重新返回 HTTP 200 不够。若新的年度／职位身份成立则创建新记录。''')
append('AGENTS.md','''## 刷新与岗位发布硬规则

每隔五天（120 小时）全覆盖轮询官方来源，遵循 docs/REFRESH_POLICY.md。高校名录不能只收名校或只收有英语网站的学校。
确认关闭或截止的岗位自动下架并保留归档；岗位标题和主按钮直达官方申请目标，本站详情只是次级入口。
调度器属于部署后的 Go 后台任务；当前框架不得被报告成已开启自动采集。''')
append('docs/ARCHITECTURE.md','''## 后台调度与下架

Go 调度器持久化 UTC 锚点，每 120 小时派发一次全覆盖 CrawlRun，Python worker 分来源执行；PostgreSQL 保存游标、任务锁、重试和运行结果。不要用每月日号 */5 的 cron 表达“每隔五天”。
岗位已知截止本地计时检查；补充每日轻量官方开放状态／申请链接检查，不替代五天全量采集。
关闭事务写入数据库并生成公共状态覆盖，主动失效列表、搜索、三语静态页与缓存。公开接口过滤 closed/expired，静态快照应用同一覆盖；缓存失效目标不超过 5 分钟。
需要外部证据才发现的提前关闭，最多存在一个状态核查周期加重试延迟；不得对外宣称实时同步雇主。无数据库连接时仍按已有截止保守过滤，并显示数据更新时间。''')
append('docs/DECISIONS.md','''- D11 用户确定：每隔五天自动采集高校相关信息，高校覆盖必须广。
- D12 用户确定：关闭的岗位自动下架，岗位点击直达官方申请页面。
- D13 实施细化：以 120 小时间隔持久调度；已知截止即时计时，补充每日岗位轻量核查；网络失败与真实关闭分开处理。''')
append('handoff/GROK_BUILD.md','''新增必须实施的策略：读 docs/REFRESH_POLICY.md 与 config/refresh-policy.json。每 120 小时轮询广覆盖来源，真实关闭／截止自动下架，标题和主要按钮直达官方申请页。原来只做“站内岗位详情后再点申请”的流程已不满足要求。当前配置是部署蓝图，没有实际开启采集。''')
replace('README.md','| [docs/CRAWLING_RULES.md](docs/CRAWLING_RULES.md) | 官方源采集、Scrapling 升级流程 |','| [docs/CRAWLING_RULES.md](docs/CRAWLING_RULES.md) | 官方源采集、Scrapling 升级流程 |\n| [docs/REFRESH_POLICY.md](docs/REFRESH_POLICY.md) | 每五天采集、广覆盖、岗位关闭下架与申请直达 |')
replace('docs/ACCEPTANCE.md','## 测试样本必须覆盖','''## 新增策略验收

| ID | 行为 | 关联模型 |
|---|---|---|
| A18 | 120 小时调度跨月／夏令时不漂移；重启补跑一次，锁防止重复全量任务 | OPS |
| A19 | 官方基线名录逐校登记，公立／国立／私立／应用导向与语言覆盖分项报告，失败可追踪 | OPS |
| A20 | 到期、官方提前关闭自动下架，三语及缓存一致；429／超时不得误判关闭 | SD3 |
| A21 | 岗位标题与主动作直接到正确官方申请目标，官方 ATS 与邮件说明分支可用，无本站登录阻拦 | SD5 |

## 测试样本必须覆盖''')
config={'status':'design_only_not_deployed','universityRefresh':{'intervalHours':120,'anchorUtc':None,'scope':'all_registered_official_czech_hei_sources','overlapPolicy':'single_run_with_persistent_lock','missedRuns':'coalesce_to_one_catch_up'},'jobStatusRefresh':{'intervalHours':24,'purpose':'lightweight_closure_and_application_link_check'},'deadlineSweep':{'intervalSeconds':60,'sourceTimezone':'preserve_per_record'},'publication':{'closedJobsVisibleInPublicLists':False,'archiveRecords':True,'cacheInvalidationTargetSeconds':300,'primaryJobClick':'direct_official_application','requireSiteLoginToApply':False},'coverageTargets':{'officialInstitutionBaselineRegistrationPercent':100,'institutionSourceMappingPercent':95,'cycleSourceSuccessPercent':90},'failurePolicy':{'networkFailureMeansClosed':False,'http404MeansClosedWithoutCorroboration':False,'retryBackoffSeconds':[300,1800,7200]}}
(root/'config').mkdir(exist_ok=True)
(root/'config/refresh-policy.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=root/'opm/backlog.json';b=json.loads(p.read_text(encoding='utf-8'))
b += [{'id':'T09','title':'五天调度、广覆盖和失败重试','dependsOn':['T04','T05'],'models':['OPS'],'acceptance':['A18','A19'],'status':'not_started'},{'id':'T10','title':'岗位自动下架、缓存同步与官方申请直达','dependsOn':['T06','T09'],'models':['SD3','SD5'],'acceptance':['A20','A21'],'status':'not_started'}]
p.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=root/'opm/model.json';m=json.loads(p.read_text(encoding='utf-8'));n=m['nodes']
for i,en,zh,kind in [('clock','Five Day Schedule','每五天调度（120 小时）','object'),('registry','Official Institution Source Registry','捷克官方高校来源名录','object'),('run','Crawl Run','采集批次与覆盖报告','object'),('schedule','Coverage Refresh Scheduling','派发全覆盖采集','process'),('application','Official Application Target','官方申请目标','object'),('navigation','External Navigation','官方申请页导航','object'),('navigate','Application Opening','直达官方申请页','process')]:
    n[i]={'id':i,'kind':kind,'en':en,'zh':zh}
def e(s,t,k):return {'source':s,'target':t,'type':k}
for d in m['diagrams']:
    if d['id']=='OPS':
        d['edges'] += [e('clock','schedule','instrument'),e('registry','schedule','instrument'),e('schedule','run','result'),e('run','maintain','instrument')]
        d['requirements'] += ['A18','A19'];d['notes']+=' 每 120 小时触发全覆盖采集，失败逐源重试；官方高校名录为覆盖分母。'
    elif d['id']=='SD3':
        d['requirements'].append('A20');d['notes']+=' archive 同步更新公开目录和三语缓存，关闭岗位下架但保留归档；已知截止不等待下一轮五天采集。'
    elif d['id']=='SD5':
        d['edges'] += [e('user','navigate','agent'),e('jobresults','navigate','instrument'),e('application','navigate','instrument'),e('navigate','navigation','result')]
        d['requirements'].append('A21');d['notes']+=' 岗位标题和主按钮直接打开经核验的官方申请目标，站内解读为次级入口。'
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Updated refresh policy, application flow, model and acceptance requirements.')
