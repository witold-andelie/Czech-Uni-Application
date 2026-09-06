from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]/'outputs/czech-study-platform'
def append(path,text):
 p=root/path;p.write_text(p.read_text(encoding='utf-8')+'\n'+text+'\n',encoding='utf-8')
def dump(path,data):
 (root/path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
append('docs/PRODUCT.md','''## 学校性质、中留服参考与多轮申请

学校卡片、项目详情、比较表显著标明公立／私立／国立／待核验；筛选保留捷克法定性质，不强行二分。科研机构若不是高校，性质标为科研机构适用类别，不套大学性质。
中留服信息单列“中留服认证参考”：已在官方认证院校查询中核实的学校显示“中留服查询可查”，附来源和查询日期；未查到与待核验分别显示。不得标“保证认证”。官方风险公告单列，不能用绿色可查标签覆盖风险。
授课语言始终是第一分类，学校性质和认证参考是后置筛选。
学位项目与科研岗位均展示申请开始、截止、状态；官网公布轮次时显示第 N 轮和原文轮次名称。未写轮次则显示“未公布轮次”，不自动当第一轮。
同一专业按年度、语言轨道、适用申请人和轮次分别保存。第一轮截止但第二轮开放时，仍显示该专业可申请并突出第二轮；补录仅在有名额时开放，未确认时显示条件说明。
岗位关闭与某一申请轮次结束分别判断；只结束一个轮次且后续轮次开放的岗位不整体下架。详见 RECOGNITION_AND_WINDOWS.md。''')
append('docs/UI_RULES.md','''## 必显学校标签与申请窗口

学校名下并列性质标签和中留服参考状态，鼠标悬浮不是唯一查看说明的方式；手机可点击查看证据和日期。
认证状态文案：“中留服查询可查 / 官方查询暂未查到 / 待核验”；若有官方特别提示，优先展示并说明适用范围。禁止“100% 可认证”或“公立必认证”。
项目与岗位卡片均展示“开始日期 — 截止日期”和官网有依据的轮次。起始未知显示“开始日期未公布”，不能隐藏已有截止日期。
列表突出当前开放轮次，详情按时间展开所有已核验轮次。多轮同时开放则明确适用人群；不得混合成一个虚假的连续申请区间。
固定文案示意：“第 2 轮 · 2027-04-01 至 2027-05-31”仅为设计示例，不能当真实招生记录。''')
append('docs/DATA_MODEL.md','''## 学校性质与中留服证据

Institution.ownership：public / private / state / unknown；ownershipEvidenceId 为官方学校性质证据。此字段与大学类型及应用导向独立。
Institution.cscseReference：lookupStatus（listed / not_found / unverified）、officialMatchedName、matchedAwardingInstitutionId、lookupUrl、checkedAt、sourceVersion、evidenceId、reviewer、matchConfidence。
认证参考匹配以官方颁证学校为准，曾用名、校区、合作办学不得仅靠名称模糊匹配。风险公告另存 notices，含适用项目、模式、时间范围与有效状态；新公告不因 lookupStatus=listed 被隐藏。
当前未实际逐校完成查询，禁止批量赋值 listed。not_found 不代表不可认证，unverified 不得通过搜索推断为已列出。

## 通用申请轮次

ApplicationWindow：id、ownerType（offering / research_job）、ownerId、academicYear（岗位可空）、roundNumber（可空）、roundLabelOriginal、roundType（regular/supplementary/rolling/unspecified）、applicantScope、opensAt/closesAt（各自允许未知）、timezone、datePrecision、status、conditionalOnVacancies、applicationUrl、sourceEvidenceId。
每个窗口保存独立链接与三语说明，项目语言轨道不同不得混用费用／时间；岗位的招聘轮次与“第几轮面试”分开，面试轮次不作为申请轮次。
窗口结束只关闭对应窗口。有未来确认窗口则标“下一轮尚未开始”；有当前开放窗口则保留公开机会；雇主明确整个岗位招满或撤回则整体关闭，优先级高于未来旧时间表。
官网只有月日而没有年份时不得擅自补当年；保留原文并人工核验后才启用精确计时。''')
append('docs/CRAWLING_RULES.md','''## 新增字段采集

每五天采集高校相关信息时同时提取官方性质、申请开始／结束、年度和原文轮次名，保留申请人范围与补录条件。不能只抓页面最大截止日期。
中留服参考使用官方认证院校查询服务和正式公告，每五天尝试复查已登记参考；受到验证码／访问限制时进入人工核验，不绕过限制、不把失败当作未列入。学校名匹配需人工复核或可靠官方标识。
中留服年度查询数据变化不自动代表学校资格变化。来源及口径见 RECOGNITION_AND_WINDOWS.md。''')
append('AGENTS.md','''## 学校参考与轮次

学校必须标公立／私立／国立及证据；中留服只发布有官方证据的参考状态，不保证个人认证。项目和岗位展示申请起止与官方已公布轮次；不把第一轮结束当作整个项目结束。执行 docs/RECOGNITION_AND_WINDOWS.md。''')
append('docs/REFRESH_POLICY.md','''## 多轮申请对下架的补充

计时与下架以 ApplicationWindow 为单位先判定，再汇总所属机会。当前轮次结束但下一轮开放时，自动切换到当前有效轮次，不下架整个机会；只有未来轮次时标未开放并禁用当前申请入口。
官网明确整个岗位关闭／招满优先于历史轮次安排。标题直达当前适用窗口的官方链接，多个窗口同时开放且人群不同，应提供各自标明人群的直达链接，不能任意选择错误轮次。''')
append('docs/DECISIONS.md','''- D14 用户确定：显著标注学校性质及中留服认证相关信息；采用官方查询参考和来源日期，不能承诺个人获认证。
- D15 用户确定：项目／岗位申请起止时间、官方存在的轮次必须显示。未知不补造，轮次关闭和整个机会关闭分别处理。''')
append('handoff/GROK_BUILD.md','''新增要求：读 docs/RECOGNITION_AND_WINDOWS.md。学校性质和中留服官方参考状态必须显著显示；项目、岗位均记录申请起止及官方轮次。实现多轮开放汇总和正确申请链接，不因第一轮截止误下架仍在下一轮招生的机会。''')
append('README.md','新增规则入口：[中留服参考、学校性质与申请轮次](docs/RECOGNITION_AND_WINDOWS.md)。对应基础契约：[申请窗口 schema](schemas/application-window.schema.json)。')
append('docs/ACCEPTANCE.md','''## 学校参考与轮次验收

| ID | 行为 | 模型 |
|---|---|---|
| A22 | 公立／私立／国立有官方证据，三语卡片、比较、详情一致；未知不推断 | SD6 |
| A23 | 中留服 listed 有正确颁证学校匹配和查询日期；not_found 不显示不可认证；公告提示不被标签覆盖 | SD6 |
| A24 | 项目和岗位分别展示起止和有据轮次；未知／滚动／补录／未来轮次文案准确 | SD5 / SD6 |
| A25 | 第一轮结束、第二轮开放不整体下架；链接指向正确人群／轮次；整岗关闭优先于旧未来计划 | SD3 / SD5 |

增加样本：名单未查到、同名校区、合作颁证学校、官方风险公告、公立国立区别、多轮同时开放、只有截止无开始、未公布轮次、面试轮次、录满提前关闭、补录待定。''')
append('docs/SOURCES.md','''
## 中留服新增官方依据（2026-09-06 查阅）

- 认证院校查询说明：https://portal.cscse.edu.cn/lxfwzx/xlxwrz/rzyxcxmd/
- 如何判断国外院校是否可以通过认证：https://www.cscse.edu.cn/zwfw/lxfwzxwsfwdt2020/xlxwrz32/cjwt/2026042823384080651/index.html
- 查询数据更新说明：https://www.cscse.edu.cn/zwfw/lxfwzxwsfwdt2020/xlxwrz32/tzgg61/2026042823372796219/index.html
- 官方认证院校查询入口：http://yxcx.cscse.edu.cn/rzyxmd

此次核验的是查询口径，未逐一查询捷克学校，未生成任何学校“可认证”的事实断言。''')
keys={
 'institution.ownership':['学校性质','Institution ownership','Typ zřizovatele školy'],
 'institution.public':['公立','Public','Veřejná'],
 'institution.private':['私立','Private','Soukromá'],
 'institution.state':['国立','State','Státní'],
 'recognition.label':['中留服认证参考','CSCSE recognition reference','Informace k uznávání vzdělání CSCSE'],
 'recognition.listed':['中留服查询可查','Listed in the CSCSE institution lookup','Uvedeno ve vyhledávání institucí CSCSE'],
 'recognition.notFound':['官方查询暂未查到','Not found in the official lookup','V oficiálním vyhledávání nenalezeno'],
 'recognition.unverified':['待核验','Not yet verified','Dosud neověřeno'],
 'application.opens':['申请开始','Applications open','Začátek podávání přihlášek'],
 'application.closes':['申请截止','Application deadline','Termín podání přihlášky'],
 'application.round':['申请轮次','Application round','Kolo přijímacího řízení'],
 'application.roundUnknown':['未公布轮次','Round not published','Kolo nebylo zveřejněno'],
 'application.rolling':['滚动申请','Rolling applications','Průběžné podávání přihlášek'],
}
for index,l in enumerate(['zh-CN','en','cs']):
 p=root/f'locales/{l}.json';values=json.loads(p.read_text(encoding='utf-8'));values.update({k:v[index] for k,v in keys.items()});dump(f'locales/{l}.json',values)
dump('schemas/application-window.schema.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Application Window — foundational contract','type':'object','required':['id','ownerType','ownerId','roundNumber','roundLabelOriginal','opensAt','closesAt','timezone','status','sourceEvidenceId'],'properties':{'id':{'type':'string','minLength':1},'ownerType':{'enum':['offering','research_job']},'ownerId':{'type':'string','minLength':1},'roundNumber':{'type':['integer','null'],'minimum':1},'roundLabelOriginal':{'type':['string','null']},'roundType':{'enum':['regular','supplementary','rolling','unspecified']},'opensAt':{'type':['string','null'],'description':'ISO date or datetime; validate precision and timezone together'},'closesAt':{'type':['string','null']},'timezone':{'type':['string','null']},'status':{'enum':['upcoming','open','closed','conditional','unknown']},'conditionalOnVacancies':{'type':'boolean'},'applicationUrl':{'type':['string','null'],'format':'uri'},'sourceEvidenceId':{'type':'string','minLength':1}},'description':'基础契约；跨字段时间顺序、证据与精度规则由实现补充验证，不是完整生产模型。'})
p=root/'opm/model.json';m=json.loads(p.read_text(encoding='utf-8'))
for i,en,zh in [('ownership','Institution Ownership','学校性质：公立／私立／国立'),('recognition','CSCSE Reference Status','中留服官方查询参考状态'),('window','Application Window','申请时间段与官方轮次')]:
 m['nodes'][i]={'id':i,'kind':'object','en':en,'zh':zh}
for i,en,zh in [('listed','listed','官方查询可查'),('notfound','not found','官方查询暂未查到'),('unverifiedrecognition','unverified','待核验')]:
 m['nodes'][i]={'id':i,'kind':'state','owner':'recognition','en':en,'zh':zh}
for d in m['diagrams']:
 if d['id']=='SD6':
  d['edges'] += [{'source':s,'target':t,'type':'exhibition'} for s,t in [('institution','ownership'),('institution','recognition'),('round','window'),('jobs','window')]]
  d['requirements'] += ['A22','A23','A24'];d['notes']+=' 中留服参考不是个人认证保证；学校性质独立标注。申请窗口记录起止及官网轮次，未知不补造。'
 if d['id']=='SD5': d['requirements'] += ['A24','A25'];d['notes']+=' 申请直达目标按当前适用的申请轮次选择，岗位面试轮次不冒充申请轮次。'
 if d['id']=='SD3': d['requirements'].append('A25');d['notes']+=' 轮次结束与整个机会关闭分别判断，第二轮仍开放不整体下架。'
dump('opm/model.json',m)
p=root/'opm/backlog.json';b=json.loads(p.read_text(encoding='utf-8'));b.append({'id':'T11','title':'学校性质、中留服参考和多轮申请窗口','dependsOn':['T02','T05','T10'],'models':['SD3','SD5','SD6'],'acceptance':['A22','A23','A24','A25'],'status':'not_started'});dump('opm/backlog.json',b)
print('Updated recognition evidence, ownership, application windows, locales and OPM.')
