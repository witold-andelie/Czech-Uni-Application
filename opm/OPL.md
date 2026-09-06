# OPL semantic companion

Generated from model.json, together with DOT. English sentences express the same typed relations. State pairs below are a readable OPL subset, not a certified OPL parser export.

## SD — 系统环境与主要价值

Refines: Context / structural view

平台帮助申请者形成候选清单；申请者自行通过官方入口申请。SD0 展开主过程。

- Applicant handles Opportunity Finding.
- Opportunity Finding requires Czech Opportunity Platform.
- Opportunity Finding requires Opportunity Need.
- Opportunity Finding requires Published Catalogue.
- Opportunity Finding yields Opportunity Shortlist.

## SD0 — 机会发现主过程展开

Refines: Opportunity Finding

主过程的三个子过程；项目与岗位是替代任务路径，不要求先选择授课语言才能找工作。shortlist 首次使用时由父过程创建，子过程更新。

- Applicant handles Programme Discovering.
- Programme Discovering requires Published Catalogue.
- Programme Discovering requires Opportunity Need.
- Programme Discovering requires Czech Opportunity Platform.
- Programme Discovering affects Opportunity Shortlist.
- Applicant handles Research Opportunity Finding.
- Research Opportunity Finding requires Published Catalogue.
- Research Opportunity Finding requires Opportunity Need.
- Research Opportunity Finding requires Czech Opportunity Platform.
- Research Opportunity Finding affects Opportunity Shortlist.
- Applicant handles Interface Presenting.
- Interface Presenting requires Czech Opportunity Platform.
- Interface Presenting requires Published Catalogue.
- Interface Presenting yields Localized Interface.

## SD1 — 按授课语言优先发现项目

Refines: Programme Discovering

展示首次选择；后续改选用相同 Choosing 过程的 effect 变体，不强制退回首页。filter 必须先读取语言状态，unset 时展示选择控件不执行限定语言查询。英语入口默认仅英语独立轨道。

- Teaching Language Choice can be unset, English, Czech, all.
- Applicant handles English Teaching Choosing.
- English Teaching Choosing changes Teaching Language Choice from unset to English.
- Applicant handles Czech Teaching Choosing.
- Czech Teaching Choosing changes Teaching Language Choice from unset to Czech.
- Applicant handles All Teaching Choosing.
- All Teaching Choosing changes Teaching Language Choice from unset to all.
- Programme Filtering requires Teaching Language Choice.
- Programme Filtering requires Search Criteria.
- Programme Filtering requires Published Catalogue.
- Programme Filtering yields Programme Results.
- Detail Inspecting requires Programme Results.
- Applicant handles Detail Inspecting.
- Detail Inspecting yields Opportunity Detail.
- Opportunity Saving requires Opportunity Detail.
- Applicant handles Opportunity Saving.
- Opportunity Saving affects Opportunity Shortlist.
- Opportunity Comparing requires Comparison Selection.
- Opportunity Comparing requires Published Catalogue.
- Opportunity Comparing yields Comparison View.

## SD2 — 界面语言独立切换与呈现

Refines: Interface Presenting

switch 仅改变 UI Locale，不改变 Teaching Language Choice 或 Browsing Context；locale 三个状态互斥。翻译包已复核状态是界面呈现所需资源，原文附录允许保留源语言。

- Translation Bundle can be draft, reviewed.
- Teaching Language Choice can be unset, English, Czech, all.
- UI Locale can be zh-CN, en, cs.
- Applicant handles Locale Switching.
- Locale Switching requires Locale Choice.
- Locale Switching affects UI Locale.
- Localized Page Rendering requires UI Locale.
- Localized Page Rendering requires Browsing Context.
- Localized Page Rendering requires Teaching Language Choice.
- Localized Page Rendering requires Translation Bundle in state reviewed.
- Localized Page Rendering requires Design Rules.
- Localized Page Rendering requires Published Catalogue.
- Localized Page Rendering yields Localized Interface.

## OPS — 目录维护的支撑环境

Refines: Context / structural view

独立支撑过程的上下文，SD3 展开 maintain；采集与审核不阻塞在线用户查询。 每 120 小时触发全覆盖采集，失败逐源重试；官方高校名录为覆盖分母。

- Content Reviewer handles Catalogue Maintaining.
- Catalogue Maintaining requires Czech Opportunity Platform.
- Catalogue Maintaining requires Official Source.
- Catalogue Maintaining requires Content Rules.
- Catalogue Maintaining affects Published Catalogue.
- Coverage Refresh Scheduling requires Five Day Schedule.
- Coverage Refresh Scheduling requires Official Institution Source Registry.
- Coverage Refresh Scheduling yields Crawl Run.
- Catalogue Maintaining requires Crawl Run.

## SD3 — 可信目录维护与三语发布

Refines: Catalogue Maintaining

维护是独立支撑过程，不是用户发现过程的子过程。verified 与 reviewed 必须指向相同源哈希，发布为 AND 条件。更新创建新内容版本，旧快照保留审计。过期状态可优先更新，不能继续表示开放。 archive 同步更新公开目录和三语缓存，关闭岗位下架但保留归档；已知截止不等待下一轮五天采集。 轮次结束与整个机会关闭分别判断，第二轮仍开放不整体下架。

- Translation Bundle can be draft, reviewed.
- Structured Record can be draft, verified, rejected.
- Publication Snapshot can be current, needs review, archived.
- Evidence Acquiring requires Official Source.
- Evidence Acquiring yields Source Evidence.
- Record Structuring requires Source Evidence.
- Record Structuring yields Structured Record in state draft.
- Record Verifying changes Structured Record from draft to verified.
- Content Reviewer handles Record Verifying.
- Record Verifying requires Source Evidence.
- Record Verifying requires Content Rules.
- Record Rejecting changes Structured Record from draft to rejected.
- Content Reviewer handles Record Rejecting.
- Content Translating requires Structured Record in state verified.
- Content Translating yields Translation Bundle in state draft.
- Translation Reviewing changes Translation Bundle from draft to reviewed.
- Content Reviewer handles Translation Reviewing.
- Translation Reviewing requires Source Evidence.
- Snapshot Publishing requires Structured Record in state verified.
- Snapshot Publishing requires Translation Bundle in state reviewed.
- Snapshot Publishing requires Content Rules.
- Snapshot Publishing yields Publication Snapshot in state current.
- Snapshot Publishing affects Published Catalogue.
- Snapshot Invalidating changes Publication Snapshot from current to needs review.
- Snapshot Invalidating requires Deadline and Source Change.
- Snapshot Archiving changes Publication Snapshot from current to archived.
- Snapshot Archiving requires Deadline and Source Change.
- Snapshot Archiving affects Published Catalogue.
- Record Repreparing requires Publication Snapshot in state needs review.
- Record Repreparing requires Source Evidence.
- Record Repreparing yields Structured Record in state draft.

## SD4 — 官方采集与 Scrapling 升级

Refines: Evidence Acquiring

成功与失败分支互斥，判定依赖真实响应和正文完整性；不以 HTTP 200 作为成功充分条件。动态失败前必须有真实 Scrapling 尝试日志，来源始终作为 instrument，绝不被消耗。

- Acquisition Request can be pending, difficult, acquired, failed.
- Ordinary Evidence Fetching requires Official Source.
- Ordinary Evidence Fetching requires Scrapling GET.
- Ordinary Evidence Fetching changes Acquisition Request from pending to acquired.
- Ordinary Evidence Fetching yields Source Evidence.
- Difficult Page Detecting requires Official Source.
- Difficult Page Detecting requires Extraction Rules.
- Difficult Page Detecting changes Acquisition Request from pending to difficult.
- Dynamic Evidence Fetching requires Official Source.
- Dynamic Evidence Fetching requires Scrapling DynamicFetcher.
- Dynamic Evidence Fetching changes Acquisition Request from difficult to acquired.
- Dynamic Evidence Fetching yields Source Evidence.
- Acquisition Failure Recording requires Scrapling DynamicFetcher.
- Acquisition Failure Recording requires Official Source.
- Acquisition Failure Recording changes Acquisition Request from difficult to failed.
- Manual Review Queuing requires Acquisition Request in state failed.
- Manual Review Queuing affects Manual Review Queue.

## SD5 — 硕士可申请的带薪科研资格

Refines: Research Opportunity Finding

资格核验部分属于科研支撑细化；检索只使用同一岗位的已发布当前版本。硕士资格不代表无需读博，unspecified 不能当 not_required，工资数值未公开也须有带薪证据。 岗位标题和主按钮直接打开经核验的官方申请目标，站内解读为次级入口。 申请直达目标按当前适用的申请轮次选择，岗位面试轮次不冒充申请轮次。

- Research Job Record can be unchecked, master eligible and paid, other or unresolved.
- Research Job Record exhibits Degree Requirement.
- Research Job Record exhibits Doctoral Enrollment Requirement.
- Research Job Record exhibits Compensation Terms.
- Research Job Record exhibits Working Languages.
- Master Eligibility Verifying changes Research Job Record from unchecked to master eligible and paid.
- Master Eligibility Verifying requires Source Evidence.
- Content Reviewer handles Master Eligibility Verifying.
- Other Eligibility Recording changes Research Job Record from unchecked to other or unresolved.
- Other Eligibility Recording requires Source Evidence.
- Content Reviewer handles Other Eligibility Recording.
- Research Job Filtering requires Research Job Record in state master eligible and paid.
- Research Job Filtering requires Job Criteria.
- Research Job Filtering requires Published Catalogue.
- Research Job Filtering yields Research Job Results.
- Opportunity Saving requires Research Job Results.
- Applicant handles Opportunity Saving.
- Opportunity Saving affects Opportunity Shortlist.
- Applicant handles Application Opening.
- Application Opening requires Research Job Results.
- Application Opening requires Official Application Target.
- Application Opening yields External Navigation.

## SD6 — 平台与数据的对象结构

Refines: Context / structural view

对象结构视图；catalog 中这些是记录集合的组成类别而非单个实例数量。PostgreSQL 为逻辑持久层，Supabase 是建议托管方式。store 只更新内部核验数据，公开可见性由 SD3 publish 决定。 模块语言以 LANGUAGE_STACK.md 为准；Go 在线服务、Python 离线采集、静态前台分离。 中留服参考不是个人认证保证；学校性质独立标注。申请窗口记录起止及官网轮次，未知不补造。

- Structured Record can be draft, verified, rejected.
- Research Job Record can be unchecked, master eligible and paid, other or unresolved.
- CSCSE Reference Status can be listed, not found, unverified.
- Czech Opportunity Platform consists of Public Website.
- Czech Opportunity Platform consists of Editorial Console.
- Czech Opportunity Platform consists of Ingestion Service.
- Czech Opportunity Platform consists of PostgreSQL Database.
- Czech Opportunity Platform consists of Published Data Cache.
- Published Catalogue consists of Institution.
- Published Catalogue consists of Programme.
- Published Catalogue consists of Research Job Record.
- Programme consists of Programme Offering.
- Programme Offering consists of Admission Round.
- Programme Offering exhibits Teaching Languages.
- Programme Offering exhibits Additional Language Requirements.
- Reviewed Data Storing requires PostgreSQL Database.
- Reviewed Data Storing requires Structured Record in state verified.
- Reviewed Data Storing affects Editorial Data Store.
- Public Snapshot Exporting requires Published Catalogue.
- Public Snapshot Exporting affects Published Data Cache.
- Czech Opportunity Platform consists of Online API Service.
- Institution exhibits Institution Ownership.
- Institution exhibits CSCSE Reference Status.
- Admission Round exhibits Application Window.
- Research Job Record exhibits Application Window.
