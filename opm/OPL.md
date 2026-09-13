# OPL semantic companion

Generated from model.json, together with DOT. English sentences express the same typed relations. State pairs below are a readable OPL subset, not a certified OPL parser export.

## SD — 系统环境与主要价值

Refines: Context / structural view

平台帮助申请者浏览、筛选并核对官方信息；申请者自行通过官方入口申请。SD0 展开主过程。

- Applicant handles Opportunity Finding.
- Opportunity Finding requires Czech Opportunity Platform.
- Opportunity Finding requires Opportunity Need.
- Opportunity Finding requires Published Catalogue.
- Opportunity Finding yields Programme Results.

## SD0 — 机会发现主过程展开

Refines: Opportunity Finding

主过程的三个子过程；项目与岗位是替代任务路径，不要求先选择授课语言才能找工作。

- Applicant handles Programme Discovering.
- Programme Discovering requires Published Catalogue.
- Programme Discovering requires Opportunity Need.
- Programme Discovering requires Czech Opportunity Platform.
- Applicant handles Research Opportunity Finding.
- Research Opportunity Finding requires Published Catalogue.
- Research Opportunity Finding requires Opportunity Need.
- Research Opportunity Finding requires Czech Opportunity Platform.
- Applicant handles Interface Presenting.
- Interface Presenting requires Czech Opportunity Platform.
- Interface Presenting requires Published Catalogue.
- Interface Presenting yields Localized Interface.
- Programme Discovering yields Programme Results.
- Research Opportunity Finding yields Research Job Results.

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

独立支撑过程的上下文，SD3 展开 maintain；采集与审核不阻塞在线用户查询。稳定来源保持 120 小时全覆盖，高波动任务分别以 1 小时复核已知岗位状态、4 小时发现全部已登记岗位目录、2 小时刷新 DZS 项目目录、2 小时刷新 CZU 英语本科／硕士目录及窗口、2 小时刷新 CZU 捷克入口本科／硕士目录、2 小时刷新 CZU 博士学院证据。普通漏跑等到下一个同余日；超过 120 小时未成功才做单分片 SLA 补跑。官方高校名录是覆盖分母；覆盖报告分开表示来源完整、学校接入、current／supported 候选与正式发布，单源刷新不能冒充全源成功。CZU 两条本科／硕士来源各自按官网声明范围报告完整性并保留交叉差异；博士来源以 MŠMT 60 个 offering 和六学院年度证据为边界，未知开始日、条件轮次及未公告轮次不推断为开放。候选仍受三语和来源哈希发布门禁约束。持久队列在操作系统互斥锁内改变；租约带拥有者、续期与过期回收。锁顺序为 refresh → publish → safety。已核验关闭走独立安全状态覆盖，网络失败不是关闭。幂等官方读取只对短暂失败作两次有限请求重试，并尊重 Retry-After；过长延迟交给调度。最终抓取或解析失败不推进成功时间，按逐来源退避时间重试，不触发目录缺席归档，并继续参加 SLA 监测。成功和失败、租约释放和到期是互斥分支。

- Research Job Record can be unchecked, master eligible and paid, other or unresolved.
- Refresh Lease can be available, held, expired.
- Persistent Schedule Queue can be idle, scheduled, running, failed.
- Source Refresh Attempt can be attempted, succeeded, failed.
- Dynamic Vacancy Candidate can be discovered, scoped and attributable, quarantined, unavailable, outside supported catalogue scope.
- Content Reviewer handles Catalogue Maintaining.
- Catalogue Maintaining requires Czech Opportunity Platform.
- Catalogue Maintaining requires Official Source.
- Catalogue Maintaining requires Content Rules.
- Catalogue Maintaining affects Published Catalogue.
- Coverage Refresh Scheduling requires Five Day Schedule.
- Coverage Refresh Scheduling requires Official Institution Source Registry.
- Coverage Refresh Scheduling changes Persistent Schedule Queue from idle to scheduled.
- Coverage Refresh Scheduling yields Crawl Run.
- Refresh Lease Acquiring requires Operating System File Mutex.
- Refresh Lease Acquiring changes Refresh Lease from available to held.
- Refresh Lease Expiring requires Five Day Schedule.
- Refresh Lease Expiring changes Refresh Lease from held to expired.
- Expired Lease Reclaiming requires Operating System File Mutex.
- Expired Lease Reclaiming requires Five Day Schedule.
- Expired Lease Reclaiming changes Refresh Lease from expired to held.
- Refresh Lease Releasing requires Operating System File Mutex.
- Refresh Lease Releasing changes Refresh Lease from held to available.
- Source Attempt Starting changes Persistent Schedule Queue from scheduled to running.
- Source Attempt Starting requires Refresh Lease in state held.
- Source Attempt Starting requires Official Source.
- Source Attempt Starting yields Source Refresh Attempt in state attempted.
- Source Success Recording changes Persistent Schedule Queue from running to idle.
- Source Success Recording changes Source Refresh Attempt from attempted to succeeded.
- Source Failure Recording changes Persistent Schedule Queue from running to failed.
- Source Failure Recording changes Source Refresh Attempt from attempted to failed.
- Source Retry Scheduling changes Persistent Schedule Queue from failed to scheduled.
- Source Retry Scheduling changes Source Refresh Attempt from failed to attempted.
- Source Retry Scheduling requires Five Day Schedule.
- Source SLA Monitoring requires Persistent Schedule Queue.
- Source SLA Monitoring requires Five Day Schedule.
- Source SLA Monitoring yields SLA Breach Log.
- Job Status Rechecking requires One Hour Job Status Check.
- Job Status Rechecking requires Official Institution Source Registry.
- Job Status Rechecking requires Operating System File Mutex.
- Job Status Rechecking yields Job Status Inspection.
- Job Status Rechecking affects Research Job Record.
- Registered Vacancy Discovering requires Four Hour Job Discovery.
- Registered Vacancy Discovering requires Official Institution Source Registry.
- Registered Vacancy Discovering requires Operating System File Mutex.
- Registered Vacancy Discovering yields Dynamic Vacancy Candidate in state discovered.
- Programme Availability Refreshing requires Two Hour Programme Availability Refresh.
- Programme Availability Refreshing requires Official Source.
- Programme Availability Refreshing requires Official Institution Source Registry.
- Programme Availability Refreshing requires Operating System File Mutex.
- Programme Availability Refreshing yields DZS Programme Candidate Directory.
- CZU Programme Window Refreshing requires Two Hour CZU Programme Window Refresh.
- CZU Programme Window Refreshing requires Official Source.
- CZU Programme Window Refreshing requires Official Institution Source Registry.
- CZU Programme Window Refreshing requires Operating System File Mutex.
- CZU Programme Window Refreshing yields CZU English Programme Candidate Directory.
- CZU Czech Portal Programme Refreshing requires Two Hour CZU Czech Portal Programme Refresh.
- CZU Czech Portal Programme Refreshing requires Official Source.
- CZU Czech Portal Programme Refreshing requires Official Institution Source Registry.
- CZU Czech Portal Programme Refreshing requires Operating System File Mutex.
- CZU Czech Portal Programme Refreshing yields CZU Czech Portal Programme Candidate Directory.
- CZU Doctoral Faculty Evidence Refreshing requires Two Hour CZU Doctoral Faculty Refresh.
- CZU Doctoral Faculty Evidence Refreshing requires Official Source.
- CZU Doctoral Faculty Evidence Refreshing requires Official Institution Source Registry.
- CZU Doctoral Faculty Evidence Refreshing requires Operating System File Mutex.
- CZU Doctoral Faculty Evidence Refreshing yields CZU Doctoral Candidate Directory.
- Source Coverage Calculating requires Official Institution Source Registry.
- Source Coverage Calculating requires DZS Programme Candidate Directory.
- Source Coverage Calculating requires CZU English Programme Candidate Directory.
- Source Coverage Calculating requires CZU Czech Portal Programme Candidate Directory.
- Source Coverage Calculating requires CZU Doctoral Candidate Directory.
- Source Coverage Calculating requires Research Job Record.
- Source Coverage Calculating requires Published Catalogue.
- Source Coverage Calculating yields Denominator Bound Coverage Report.
- Catalogue Maintaining requires Crawl Run.

## SD3 — 可信目录维护与三语发布

Refines: Catalogue Maintaining

维护是独立支撑过程，不是用户发现过程的子过程。verified、reviewed 与逐语种 hash bound 审核记录是发布的 AND 条件；源内容哈希变化使旧审核记录失效。更新创建新内容版本，旧快照保留审计。过期状态可优先更新，不能继续表示开放。archive 同步更新公开目录和三语缓存，关闭岗位下架但保留归档；已知截止不等待下一轮五天采集。轮次结束与整个机会关闭分别判断，第二轮仍开放不整体下架。SD3A 展开原子发布与构建固定版本。

- Translation Bundle can be draft, reviewed.
- Structured Record can be draft, verified, rejected.
- Locale Review Record can be pending, hash bound, invalidated.
- Publication Snapshot can be current, needs review, archived, staged, validated.
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
- Content Translating yields Locale Review Record in state pending.
- Translation Reviewing changes Translation Bundle from draft to reviewed.
- Content Reviewer handles Translation Reviewing.
- Translation Reviewing requires Source Evidence.
- Source Evidence exhibits Source Content Hash.
- Locale Review Binding changes Locale Review Record from pending to hash bound.
- Content Reviewer handles Locale Review Binding.
- Locale Review Binding requires Source Content Hash.
- Locale Review Binding requires Source Evidence.
- Locale Review Invalidating changes Locale Review Record from hash bound to invalidated.
- Locale Review Invalidating requires Deadline and Source Change.
- Locale Review Invalidating requires Source Content Hash.
- Snapshot Publishing requires Structured Record in state verified.
- Snapshot Publishing requires Translation Bundle in state reviewed.
- Snapshot Publishing requires Locale Review Record in state hash bound.
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

资格核验部分属于科研支撑细化；检索只使用同一岗位的已发布当前版本。硕士资格不代表无需读博，unspecified 不能当 not_required，工资数值未公开也须有带薪证据。salary.basisFte 只表达薪资基准，employmentFte 表达岗位实际工时，employmentStartsAt 表达可到岗日期；三者分别记录，缺失不推断。 岗位标题和主按钮直接打开经核验的官方申请目标，站内解读为次级入口。 申请直达目标按当前适用的申请轮次选择，岗位面试轮次不冒充申请轮次。

- Research Job Record can be unchecked, master eligible and paid, other or unresolved.
- Working Languages can be specified by the vacancy, not specified (BCP 47 und).
- Research Job Record exhibits Degree Requirement.
- Research Job Record exhibits Doctoral Enrollment Requirement.
- Research Job Record exhibits Compensation and Workload Terms.
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
- Applicant handles Application Opening.
- Application Opening requires Research Job Results.
- Application Opening requires Official Application Target.
- Application Opening yields External Navigation.

## SD6 — 平台与数据的对象结构

Refines: Context / structural view

对象结构视图；catalog 中这些是记录集合的组成类别而非单个实例数量。PostgreSQL 为逻辑持久层，Supabase 是建议托管方式。store 只更新内部核验数据，公开可见性由 SD3 publish 决定。 模块语言以 LANGUAGE_STACK.md 为准；Go 在线服务、Python 离线采集、静态前台分离。 中留服官方查询与运营方名单分字段保存；没有官方查询证据时公开状态为 unverified。申请窗口记录起止及官网轮次，未知不补造。

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

## SD2A — 交互地图聚合与失败回退

Refines: Localized Page Rendering

正式交互层当前使用 OpenStreetMap 在线栅格瓦片，并保留项目内置的捷克 14 州概览图。连续瓦片错误或 12 秒超时会切换至内置图，列表与筛选继续可用，用户可以重试。低缩放用原生按钮聚合相邻学校，键盘激活后放大；近景恢复独立按钮并展开同坐标点。桌面端鼠标位于地图时，普通滚轮直接缩放，不要求 Ctrl、Command、Shift 或 Alt。该模型不表示大陆运营商与真机验收已经完成，也不把当前栅格实现描述成自托管 PMTiles。

- Institution Map View can be interactive street map, bundled overview.
- External Tile Health can be loaded, failed or timed out.
- Interactive Map Rendering requires Published Catalogue.
- Interactive Map Rendering requires OpenStreetMap Raster Tiles.
- Interactive Map Rendering yields Institution Map View in state interactive street map.
- Tile Failure Monitoring requires OpenStreetMap Raster Tiles.
- Tile Failure Monitoring yields External Tile Health in state failed or timed out.
- Map Overview Falling Back changes Institution Map View from interactive street map to bundled overview.
- Map Overview Falling Back requires External Tile Health in state failed or timed out.
- Map Overview Falling Back requires Bundled Czech Overview Layers.
- Interactive Map Retrying changes Institution Map View from bundled overview to interactive street map.
- Applicant handles Interactive Map Retrying.
- Interactive Map Retrying requires OpenStreetMap Raster Tiles.
- Nearby Marker Grouping requires Institution.
- Nearby Marker Grouping requires Institution Map View in state interactive street map.
- Nearby Marker Grouping yields Keyboard Map Marker Groups.
- Applicant handles Marker Group Expanding.
- Marker Group Expanding requires Keyboard Map Marker Groups.
- Marker Group Expanding affects Institution Map View.
- Applicant handles Map Wheel Zooming.
- Map Wheel Zooming requires Unmodified Mouse Wheel Input.
- Map Wheel Zooming requires Institution Map View in state interactive street map.
- Map Wheel Zooming affects Institution Map View.

## SD3A — 原子发布与不可变构建绑定

Refines: Snapshot Publishing

候选数据先在 refresh 锁内钉扎世代并复制到唯一 staging，再释放该锁，按固定文件集合、结构、关系、证据、URL、资格及逐语种哈希审核规则校验。窗口日期、时区、必需来源／证据 URL、受控薪资码和会被渲染的嵌套 tracer 窗口必须同时由 Python 与 Node 拒绝。岗位批准绑定事实哈希、译文哈希、证据哈希和审核角色，抓取时间戳单独保存。DZS 与 CZU 的来源完整性只说明各自声明范围抓取完整，不等于已经完成三语正式发布；CZU 英语目录和捷克入口本科／硕士候选必须逐字段保留来源证据、内容哈希及跨源差异，博士候选还须保留 MŠMT offering 匹配、六学院证据、窗口状态和图像 PDF 的受审哈希。岗位公告未说明工作语言时使用 BCP 47 und 状态，不从公告语言推断。只有合格候选才能成为不可变快照并通过单一原子指针激活；force 不能绕过门禁。已核验关闭另有独立安全状态覆盖，快照回滚不能重新打开之后的关闭。构建启动时只解析一次当前版本，固定到该快照，并只从该版本生成浏览器资源；发布、回滚或采集并发不会让一个构建混读版本。生产 API 绑定该不可变发布，拒绝 fixture。Pull request 与 main 提交运行固定依赖的确定性 CI；main 仅在数据、Go 与 Web 检查全部通过后生成绑定提交 SHA 的静态交付制品。该制品不代表已经部署公网；在托管 run 出现前报告 CI configured; local checks passed; hosted CI/CD not verified。

- Translation Bundle can be draft, reviewed.
- Structured Record can be draft, verified, rejected.
- Locale Review Record can be pending, hash bound, invalidated.
- Repository Revision can be awaiting CI, CI validated.
- Publication Snapshot can be current, needs review, archived, staged, validated.
- Snapshot Staging requires Structured Record in state verified.
- Snapshot Staging requires Translation Bundle in state reviewed.
- Snapshot Staging requires Locale Review Record in state hash bound.
- Snapshot Staging yields Publication Snapshot in state staged.
- Publication Contract Validating changes Publication Snapshot from staged to validated.
- Publication Contract Validating requires Publication Contract.
- Snapshot Activating changes Publication Snapshot from validated to current.
- Snapshot Activating requires Operating System File Mutex.
- Snapshot Activating affects Active Version Pointer.
- Build Version Pinning requires Publication Snapshot in state current.
- Build Version Pinning requires Active Version Pointer.
- Build Version Pinning yields Immutable Build Binding.
- Browser Asset Exporting requires Immutable Build Binding.
- Browser Asset Exporting requires Publication Snapshot in state current.
- Browser Asset Exporting yields Versioned Browser Asset.
- Browser Asset Exporting affects Published Data Cache.
- Continuous Integration Validating changes Repository Revision from awaiting CI to CI validated.
- Continuous Integration Validating requires Pinned CI Workflow.
- Continuous Integration Validating requires Publication Contract.
- Static Delivery Packaging requires Repository Revision in state CI validated.
- Static Delivery Packaging requires Versioned Browser Asset.
- Static Delivery Packaging requires Pinned CI Workflow.
- Static Delivery Packaging yields Commit-bound Delivery Artifact.

## SD4A — 注册来源驱动的动态岗位发现

Refines: Evidence Acquiring

来源注册表每 4 小时独立驱动已登记官方岗位列表、分页、详情和必要附件发现。Charles 使用官方 AJAX 真分页；VUT 读取公开 GraphQL 全分页与逐项详情；CTU 核对公告总数并提取 PDF，扫描件走有上限的本地 OCR；CZU 将 WP Job Manager 公共分页与同站 REST 全文按岗位 ID、标题和 URL 对齐。提取以逐项全文判断研究或技术职责、学历、博士注册与带薪证据，纯教学、行政、研究支持及科学传播岗位不因背景关键词进入候选；否定语义优先，缺证据保持 unknown。AVCR 中无法辨认实际研究所的候选进入隔离区。只有源级完整时，完整目录中缺席才记 unavailable；仍在目录但不符合范围则进入 outside supported catalogue scope 状态。覆盖报告区分校级聚合、院系局部、研究网络和有证据的完整声明；登记学校覆盖与已审核公开岗位覆盖必须分列，0 个完整声明不等于高校岗位齐全。动态发现仍须经过事实核验和三语人工审核，不能直接发布。

- Research Job Record can be unchecked, master eligible and paid, other or unresolved.
- Dynamic Vacancy Candidate can be discovered, scoped and attributable, quarantined, unavailable, outside supported catalogue scope.
- Registered Vacancy Discovering requires Official Source.
- Registered Vacancy Discovering requires Official Institution Source Registry.
- Registered Vacancy Discovering requires Paginated Vacancy Listing.
- Registered Vacancy Discovering requires Discovery Cursor and Completeness.
- Registered Vacancy Discovering yields Dynamic Vacancy Candidate in state discovered.
- Registered Vacancy Discovering yields Source Evidence.
- Vacancy Scope and Employer Resolving changes Dynamic Vacancy Candidate from discovered to scoped and attributable.
- Vacancy Scope and Employer Resolving requires Source Evidence.
- Vacancy Scope and Employer Resolving requires Official Vacancy Body and Attachment.
- Vacancy Scope and Employer Resolving requires Resolved Legal Employer.
- Unresolved Employer Quarantining changes Dynamic Vacancy Candidate from discovered to quarantined.
- Unresolved Employer Quarantining requires Official Institution Source Registry.
- Listing Disappearance Recording changes Dynamic Vacancy Candidate from scoped and attributable to unavailable.
- Listing Disappearance Recording requires Paginated Vacancy Listing.
- Listing Disappearance Recording requires Discovery Cursor and Completeness.
- Catalogue Scope Exclusion Recording changes Dynamic Vacancy Candidate from scoped and attributable to outside supported catalogue scope.
- Catalogue Scope Exclusion Recording requires Paginated Vacancy Listing.
- Catalogue Scope Exclusion Recording requires Official Vacancy Body and Attachment.
- Vacancy Candidate Structuring requires Dynamic Vacancy Candidate in state scoped and attributable.
- Vacancy Candidate Structuring requires Source Evidence.
- Vacancy Candidate Structuring yields Research Job Record in state unchecked.
