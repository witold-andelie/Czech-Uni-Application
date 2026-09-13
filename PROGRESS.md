# 最新进展

## 覆盖扩张最小试验与 Flash 执行手册（2026-09-13）

交接：[FLASH_AGENT_COVERAGE_RUNBOOK_2026-09-13.md](docs/FLASH_AGENT_COVERAGE_RUNBOOK_2026-09-13.md)。将任务拆成离线复现、逐条事实表、分类修复、单校安全合并、三语审核发布、逐校扩张六个执行包，附可直接发送给另一 agent 的提示词。

- UHK `uhk-central-selection` 实网 Scrapling 试验：1 列表 + 9 详情，10 次请求全部 HTTP 200；现有发现器产出 7 候选、2 隔离。5 条候选有带薪/博士学历证据和 2026-10-02 截止，主要为博士后，不能计入硕士可申请带薪博士岗。
- 发现生物方向候选正文为博士后，但 track=post_master/isPostdoc=false；明确列为下一 agent 首个有保存页面夹具的分类修复。其 doctorateRequired=true 已正确解析。
- 离线完整结构化 + 现有 `merge_sharded_jobs`：暂存 128→135 条，原有记录修改/删除均为 0。注意直接采集返回的是单校 payload，必须合并，不能覆盖全国库。
- 证据、脚本和暂存差异：`work/coverage-pilot-2026-09-13/`；`verify.py` 验证通过。正式候选、审核、发布指针及调度状态哈希均未改变；未发布新岗位、未启动或联系另一 agent。


## 第六轮改进复核与公网测试部署准备（2026-09-13）

交接：[PUBLIC_BETA_READINESS_2026-09-13.md](docs/PUBLIC_BETA_READINESS_2026-09-13.md)。本次为复核和部署建议，未修改生产代码或发布、未创建仓库或推送。

- 独立复测：Python 194 passed、Web 101 passed、Astro 0 errors/warnings/hints；构建 15,299 页（1m38s），产物 203,546,792 bytes；两 worker Playwright 79 passed。活动不可变快照验证通过，仍为 v2026-09-12.6/10 岗位。
- 残留：安全轮询首次新鲜后，同代际重复响应超过 30 分钟仍 stale=false（`work/predeploy-2026-09-13/safety-aging.json`）；多岗位工资比例阈值仍不是角色拆分；候选 ledger 的未知字段、过滤资格和发布阻塞需分开。岗位覆盖仍为 13 已登记有成功记录 / 9 已登记无成功记录 / 32 未评估。
- 建议先上线诚实标注覆盖与时间的 GitHub Pages 静态 beta，后台 Go 调度/Python 采集单独部署。先修状态过期、确定根站或仓库子路径、整理可干净检出的提交，再扩展既有 CI 部署已测试制品。
- 当前没有 Git remote，关键工作流/源文件/快照仍有未跟踪内容；未验证托管 CI 或公开部署。账号/仓库地址待用户提供。当前根相对链接及 JSON fetch 不能直接部署到仓库子路径。


## 第六轮全面审计（2026-09-13，仅审计与交接）

报告：[Czech_Uni_Apply_第六轮全面审计_2026-09-13.md](Czech_Uni_Apply_第六轮全面审计_2026-09-13.md)。英文详细任务、第五轮逐项复核、54 校矩阵及证据位于 `work/audit6-2026-09-13/`。本轮未修改生产代码、来源或发布快照。

- 实查活动版本 `v2026-09-12.6`：10 条公开岗位（CZU 4、MUNI 4、CUNI 2）。岗位来源仅覆盖 22/54 校，32 校未登记；9 所已登记高校无成功调度时间；全校来源范围完整评估为 0。高校/项目名录全覆盖不能当作岗位全扫描。
- 90 条当前候选中，77 条支持范围候选含 69 条待审核；公开数量增长仍集中在已有重点学校。下一轮必须交付全校来源评估、真实运行凭据和逐候选处理结论。
- 官网核实 UTB 多岗位公告存在角色事实关联问题；VŠB advert 61 与旧 `job-vsb-cnt-phd` 很可能同岗，旧记录仅指招聘总页且带薪未确认。通用解析在 Job Description 前截断，漏读待遇和截止等正文事实；须关联详情并核实身份，不可重复造岗。
- 新回归：`safetyStatus.ts:242` 类型检查失败；同版本冲突内容可清除关闭记录、重复旧状态可消除过期标记。手机 390×844 捷克语 MapLibre 容器实测高度 0，卡片已可见但地图消失。
- 独立验证：Python 183 passed、Web 97 passed、Go 两服务通过、构建 15,299 页、实际两 worker 浏览器 54 passed、发布/来源/框架验证通过；Astro **1 error**。浏览器绿灯未覆盖上述地图高度故障。Hosted CI、公开部署及持续调度仍未验证。


## 逐校清账 + 接入批次 2（2026-09-13，发布 v2026-09-13.4）

公开岗位 **21 → 26**（快照 `v2026-09-13.4`）。候选总量 112 current / 26 approved / 86 blocked。

- **台账阻塞逻辑修正（所有者方向）**：学位未注明/博士注册未注明不再作为阻塞项——记录为 unknown 属性（unknownAttributeCounts: degree 45 / enrollment 100）供筛选与展示；发布阻塞只保留：带薪证据不足、范围外、证据变化、缺三语审核。
- **UJEP 清账**：3 条过期（08-21/08-16/06-30,各自页面证据）、1 条内聘（interní VŘ,截止 10-07）、1 条无截止缺逐条要求→维持 blocked;closesAt 已按各自页面回填。
- **OSU Přednosta×3 清账发布**：广告实为"科主任**暨**教授/副教授"学术任命（科研领导职责+Ph.D. 要求）→三语审核发布（`rev-2026-09-13-clear-*`）。
- **TUL postdoc 清账**：PDF 写明 100% FTE/关税工资/无截止;Ph.D. 要求数据行缺失→维持 blocked（不虚构布尔值）。
- **UHK 2 条清账发布**：FIM（1.0 全职+Ph.D.+英授,截止 10-08）与健康学科（硕士、捷 C1/C2、定期雇佣按关税计薪,截止 10-16）——带薪证据=雇佣合同+关税工资,**数额官方未公布→amount null 诚实展示**;健康页附件 JS 渲染后经官方 PDF（všeobecne-osetrovatelstvi.pdf）复核无数额。
- **接入批次 2**：ZČU FES 修正域名仍失败（DNS）、VETUNI 公告板 0、AMU/AVU/警察学院深层路径无岗位匹配——全部如实记为"需逐站人工评估"（`onboarding-batch2-2026-09-13.json`）。
- 验证：Python 197 / Web 102 / e2e 86 / Astro 0 errors / publish --check（24→26 jobs 全过）。

## UI 规则：筛选栏随页滚动钉在左侧（2026-09-13，所有者要求）

学位项目与带薪科研两列表页,桌面宽度（≥1024px）下左侧筛选卡 `position: sticky; top: 12px; align-self: start; max-height: calc(100vh-24px); overflow-y: auto`——下滑时钉在左侧,过高时卡片内部滚动;移动端抽屉/悬浮按钮行为不变。e2e `filter-rail.spec.ts`（5 用例）通过,全量 e2e **91 passed**。
- **修正（同日,所有者复核）**：上一轮 sticky 补丁误将桌面两栏 grid 规则覆盖为单列——已恢复"筛选左栏 272px + 结果右栏"两栏布局,并将两栏+钉住断点从 1024px 降至 **768px**（FilterDrawer.desktopQuery、sheet 显隐同步 768/767）;390px 手机保持底部抽屉。e2e 新增 768px 两栏几何断言（rail 在左、宽>200、滚动后 top≤20px）。

## OSU 批次（2026-09-13，发布 v2026-09-13.2）

探针候选安全合并 + OSU 逐校审核发布。公开岗位 **15 → 21**（快照 `v2026-09-13.2`）。

- **Packet 4b（泛化合并）**：OSU/UJEP/TUL 三校探针离线重放（重放使用已存响应,零新增请求），`merge_sharded_jobs` 链式合并,锁内基线哈希验证后原子写入。135→**150**：OSU +9、UJEP +5（1 条过期截止被管线自动剔除）、TUL +1（28 条历史截止 PDF 被自动跳过——TUL 公告板挂的是历史通知,这是对官方板的诚实状态记录）。**9 条导航误报不入库**（VŠTE 3、ZČU 5、JAMU 1、VŠUP 1——通用解析器把导航条目当候选的适配器缺陷,已留证待修复）。凭证 `merge-receipt-2026-09-13-probes.json`。
- **Packet 5（OSU 审核）**：9 条中 6 条完成正文证据审核发布（`rev-2026-09-13-pkt5-osu-01..06`）——Lektor 精神病学（博士不要求、读博优势→optional、英 B2/捷 C1C2）、Andrologie 助理教授（要 Ph.D.、1.0）、Laborant×2（other/bachelor）、Postdoc I、VP4 junior/postdoc（选聘语言捷克语/英捷）。3 条 Přednosta 临床科室主任维持待审（管理职责范围待确认）。TUL 29 条全部为历史截止→管线/台账按 expired 处理;UJEP 5 条缺截止日期事实→维持 blocked。
- 浏览器验收 `osu-publish.spec.ts`：硕士默认结果含血液肿瘤实验室岗（bachelor）、不含博士后与仅博士岗;postdoc 轨道可见 VP4;详情页三语标题+官方 osu.cz 链接。e2e **86 passed**。

## Packet 3–6 执行（2026-09-13，发布 v2026-09-13.1）

按 runbook 完成首个完整垂直切片并启动覆盖扩张。公开岗位 **15 →（CZU 4 + MUNI 4 + CUNI 2 + UHK 5）= 15 条**，活动快照 `v2026-09-13.1`。

- **Packet 3（分类修复）**：`classify_track` 增加正文级 postdoc 检测（强短语 "postdoctoral position/researcher/fellow/scientist"，含导师句排除——"supervising postdoctoral researchers" 的高级岗不会误判）。UHK 生物页夹具（`uhk-biology-2026-09-13.html` + meta）锁定：track=postdoc、isPostdoc=true、paid=confirmed、截止 2026-10-02、薪资 46 000 CZK/毛月；负例（硕士岗辅导博士生、要求 PhD 的高级岗）不误判。全库 195→197 测试通过，其余 134 条记录未受影响。
- **Packet 4（安全合并）**：刷新锁（FileMutex）内验证基线哈希后原子合并，UHK 7 条进入正式候选文件（128→135），removedIds/changedExistingIds 均为空，凭证 `merge-receipt-2026-09-13.json`；指针未动；评估矩阵与处置台账随后重建（97 current / 15 approved / 82 blocked）。
- **Packet 5（审核+发布）**：五条 UHK 博士后实网复核（Scrapling，5×200，时间戳与哈希存 `pkt5-recheck-provenance.json`）后逐条真实三语审核（`rev-2026-09-13-pkt5-01..05`，事实/证据哈希绑定）；工作语言修正为 und（此前 "Czech Republic" 触发了 cs 误检）；发布 `v2026-09-13.1`（15 jobs），`--check`/`--check-sources`/Node verify 全过。浏览器验收 `uhk-publish.spec.ts`：三语标题正确、全部轨道可见、官方申请链接指向 uhk.cz、**不出现在资助博士筛选**。 CITY 城市映射补齐 13 所（此前 UHK 等城市为 null 导致详情页构建崩溃），详情/卡片对 null 城市防御渲染。
- **Packet 6（扩张，只读）**：8 校探针（上轮）+ 本轮新增：ZČU 按院枚举（FPE 3 条、FF 2 条真实候选；FES/LAV 域名解析失败待修正；FAV/FST/FDU 面板空，页面加载 200）；VETUNI 确认为 Cloudflare Turnstile 人工验证墙——**不做自动绕过**，走官方接口或人工采集路径；艺术/警察批次：JAMU 真实岗位板 1 条候选，AMU/AVU/警察学院首页导航无直接岗位链接需更深评估，VŠUP 定位到博士生页面待复核。全部产出在 `work/coverage-pilot-2026-09-13/`（逐校 decisions JSON + `zcu-faculty-enumeration.json` + `art-state-batch-2026-09-13.json`）。

- 验证：Python **197 passed**；Web 单元 **102 passed**；e2e **85 passed**（--workers=2）；Astro 0 errors；`publish.py --check`（15 jobs）通过。**未完成**：其余 ~30 所学校的逐校接入、8 校探针候选（47 条）与其他学校候选的安全合并、FIM/健康页薪资证据（正文无数额，需附件/院长决定）、VETUNI 人工采集、GitHub Pages 部署（见 PUBLIC_BETA_READINESS）。

## 第六轮审计 A82–A91 实施（2026-09-13）

按第六轮 Task 0 → Task 3 顺序实施，发布门禁全部恢复绿色。活动发布保持 `v2026-09-12.6`（本轮未发新快照，VŠB 候选增强为下一批审核内容）。

- **A89（P0）**：`safetyStatus.ts` 的空值收窄修复（显式非空局部变量，不用 as/!），`jobSearchPublished.test.ts` 未使用导入移除；`npm run check` **0 errors / 0 hints**。
- **A87（P0）**：安全状态轮询按审计要求重写——代际与内容不可变绑定（`overlayContentDigest`）：同代际但内容冲突时保留已接受闭包并报 `generation-content-conflict` 错误；同代际相同内容（重复体）不再清除 stale；新鲜度改由 `sourceCheckedAt` 心跳决定（空/非法/未来时间戳即 stale，超过 30 分钟阈值即 stale）；失败保留已接受闭包。审计要求的反例全部成为测试：初始陈旧心跳、同代际冲突、低代际、延迟高代际、心跳过期与恢复。审计的 `safety-probe.mjs` 三个缺陷场景全部转为通过。
- **A88（P1）**：地图容器同一条规则里 `min-height: clamp(...)` 被 `min-height: 0` 覆盖导致 390×844 移动端 MapLibre 渲染高度为 0；删除冗余覆盖。新增 `map-visibility.spec.ts`（25 用例）：三语 × 4 尺寸 × 瓦片成功/阻断，断言渲染区 >300px、选校/关闭前后保持、SVG 模式真实滚轮（无修饰键）改变缩放。
- **A91（P2）**：README 更新为 v2026-09-12.6/10 岗位；PRODUCT 移除账号同步路线；I18N_RULES 断网验收句去掉比较/收藏。
- **A84（P0）**：`entity_scope` 增加段标题黑名单（"Job Description:" 等不再被当作下一则广告边界），VŠB 广告 61 的范围从 1,123 恢复到 4,730 字符；`extract_employment_fte` 支持 "Full-Time Equivalent Full-time (1.0)"（修复 `\)\b` 在空格前不成立的正则缺陷）；fixed-term contract/pracovní poměr 计入带薪证据。真实页面解析结果：paid=confirmed、截止 2026-09-20、FTE 1.0、到岗 2026-10-01、金额与学位保持未知。审计 HTML 冻结为 `services/ingestion/tests/fixtures/vsb-advert-61.html` 夹具测试。**实网核实后增强 `job-vsb-cnt-phd`**：详情 URL 关联到 procedureId=61 规范地址（时间戳与哈希记录于 `work/raw/2026-09-13/`），未新建重复记录；仍 review-pending 待三语审核。VŠB 英文列表页为 JS 渲染、静态 HTML 无 advert 链接——该发现差距留证（`work/raw/2026-09-13/vsb-listing-en.html`），列表遍历属 Task 2。
- **A85（P1）**：同一公告内出现比例悬殊（<0.7）的多份薪资时，金额置空并标记 `notice_bundle`，`job_record` 保持学位/注册未知隔离；CZU 60,000/48,000（比例 0.8）的单基准不受影响。UTB 双角色夹具测试锁定"不同角色薪资不互挂、共享截止保留"。
- **A86（P0）**：`worker.discover_all_jobs` 的全源成功时间戳现在要求证明：expected==complete、无 deferred、无未观测源；缺失源记入 `unaccountedSourceIds`、`allSourceComplete=false`。四个反例测试（静默缺失/deferred/complete 不足/完整通过）先于行为修复写入。
- **A90（部分）**：搜索精确断言迁移到带日期固定夹具 `data/fixtures/job-search-fixture.json`（CZU/MUNI 别名等值、资助博士事实过滤、短词不子串匹配、postdoc/自费不漏入），活动发布只保留不变式检查（CZU 别名结果只含 CZU 雇主）——后续新增资助岗位或关闭不再破坏 CI。
- **A82/A83（框架先行）**：新增 `build_job_source_assessment.py` → `data/sources/coverage/job-source-assessment.json`：54 行诚实状态（registered_executed 13 / registered_never_executed 9 / not_assessed 32，与审计矩阵一致），逐源绑定调度成功时间戳，claim boundary 明确否认全校覆盖。新增 `build_disposition_ledger.py` → `candidate-disposition.json`：90 条 current 候选一行一决定（approved_public 10 / blocked 80），逐条 blocker（未证实带薪 28、范围未指定 11、学位未注明 41、注册未指定 73、证据变化 2、缺三语审核 78），按最近截止+学校排序。两者均有确定性测试。

- 验证：Python ingestion+OPM **194 passed**；Web 单元 **101 passed**；Astro check **0 errors/0 hints**；`publish.py --check`/`--check-sources`（10 jobs）与框架检查通过；Go 两模块通过；Playwright **79 passed**（`--workers=2`）；静态构建 15,299 页。**仍未完成**：Task 1 的 54 校逐一官方评估（本轮仅框架+当前状态快照）、Task 2 的实跑凭证、Task 4 的跨校审核清理、Task 5 的资助博士通道、Task 6 的托管 CI/调度实跑。VŠB 英文列表 JS 渲染导致静态遍历无 advert 链接的发现差距已留证。

## 第五轮审计 A67–A81 实施（2026-09-12）

按第五轮审计执行顺序完成 Gate 0 + Gate 1 及 A76/A77/A79/A80。活动快照推进为 **v2026-09-12.6**（先 .5 后 .6，均为不可变新快照，未改写旧快照）。

- **A74**：cooldown 测试改为注入时钟（到期前/到期时/到期后三段断言），`discover_registered_candidates`/`harvest_with_registered_discovery` 增加 `now` 参数；生产语义不变。
- **A75**：`bind_review_payloads` 不再静默重绑已 fact-v1 绑定的记录：事实/证据变化返回 conflict 报告（当前数据正确报告 `job-41000-1601` evidence-changed），遗留条目迁移必须显式提供逐岗 legacy source hash 与候选文件期望 generatedAt，否则拒绝。123456 变更复现无法再保留 approved。
- **A67**：金额提取重写（`parse_money_number`/`extract_salary_facts`）：完整数字 token + 千分位/小数分离（30,000 / 30 000 / 48.000 / 1,234.56 / 25,50 / 60 000,- 全覆盖），81701 审计 token 30,000 CZK 不再读成 0；amount/currency/cycle/tax/basisFte/range 独立提取，薪资词句上下文为必需，negative control（项目预算、差旅报销、场地费）不进薪资。`job_record` 不再凭空默认 month/gross；无周期金额发布为 cycle=unspecified、tax=unknown。新增候选/岗位字段 `salaryAmountMin/Max`、`fundingType`（受控词表 employment/stipend/mixed/unknown，Python+Node 双验证器校验，仅字段存在时）。
- **A68**：MSc 或等同学位（缩写前置语序）、Ph.D. fellowship/candidate 标题变体→博士注册 required、"4-year Ph.D. programme with financial support"/"Part-time contract complemented by a PhD stipend"→paid confirmed + fundingType mixed、"Working Hours: 0,5 FTE"→employmentFte 0.5。81700 的 enrollment 保持 unspecified。句界对 "Ph.D." 与数字内点号（"2.000-2.600"）做等长掩码，不再截断句子。
- **A69**：`--replay-candidates [--source-ids] [--raw-dir]` 在 refresh 锁内原子合并；记录 `parserVersion`/`sourceFetchedAt`/`factsExtractedAt` 三个时间戳，离线重放不更新 fetched 时间、不改生命周期；事实变化经 `apply_translation_review` 自动降级 review-pending；missing raw/unparseable 明确报告不伪造；重放幂等（二次运行 0 changed）。已对全库 90 条 current 候选执行一次重放。
- **A70**：实网重取 MUNI 4 页与 CZU 1601（时间戳记录于 `work/raw/2026-09-12/a70-review-provenance.json`），新抓页面与审计捕获事实一致（0 差异）。完成 4 条 MUNI（81652 截止 2026-09-20、81369→2026-11-30、81701/81700→2027-01-08）+ CZU A2 的新审核（当前公告无截止，窗口 unknown 不推断为开放；1.0 FTE、到岗 2026-10-01）；CUNI 两条博士后按修正后事实复审（d3s 2,900 EUR gross 无周期→unspecified；cenmas 2,000–2,600 EUR/月区间）。发布 v2026-09-12.6：**岗位 10 条**（CZU 4 + MUNI 4 + CUNI 2），`publish.py --check`/`--check-sources`/Node verify 全过。MUNI 官网正集 4/4 已有正确公开记录；3 条带薪博士正集均为 required+confirmed。
- **A71**：审核版机构别名表（CZU/ČZU/MUNI/MU/CTU/ČVUT 等官方缩写+正式名+中文名，等短语匹配不做任意子串）；岗位搜索改词条化（短拉丁词仅整词/别名命中，"MU" 不再命中 "Multidisciplinary"）；索引含标题×3、originalText、实验室、城市×3、雇主名；新增 funded-doctoral 派生筛选（URL 参数 funded=1，仅 confirmed+required+非 postdoc）；岗位页搜索占位与空结果改为岗位专属三语文案。测试：CZU 别名/全名同 ID 集、MUNI 4 条可检索、postdoc/未明确岗位不漏入 funded 结果、URL 往返。
- **A80**：纯浏览决定落地：nav/路由/组件（SaveButton/CompareButton/ShortlistView/CompareView）/存储函数全移除；`/[locale]/saved`、`/[locale]/compare` 重定向至项目列表（静态 meta-refresh 页）；i18n 337 键三语对齐（删除 nav.saved/compare、action.save*、compare.*、saved.*，改写 guides.intro）；OPM 模型移除 Opportunity Saving/Shortlist/Comparing 及比较对象，SD/SD0 改连 results/jobresults，重生成 12 图，check_framework 通过；AGENTS/README/PRODUCT/UI_RULES/ACCEPTANCE/ARCHITECTURE/DECISIONS/I18N_RULES 同步更新，DECISIONS 记录 dated 决定；e2e 断言导航仅剩浏览入口、卡片/详情无 save/compare 链接、旧 URL 落到浏览列表。
- **A79**：地图布局按审计方案重构：选中学校卡移出 overflow:hidden 容器成为独立区域（宽屏 ≥1024px 且高 ≥701px 叠加地图左下，短窗口/移动端为文档流内正常区域，名称/关闭/动作永不裁剪）；消除视口高度冲突（唯一高度源 `clamp(440px, calc(100vh - 240px), 860px)`，父级不再另设 max-height，sticky 仅在高视口启用）；minmax(0,1fr) 轨道+收缩链+chip 换行修复 390px 捷克文横向溢出（文档宽 524→390）。地图列布局（列表左 340px / 地图右宽列）在所有 ≥1024px 宽度无条件保持，与窗口高度无关；高度门控仅作用于 sticky 与固定列表高。桌面两列 stretch 等高：地图自动填满与左列等高，右下无空白（实测四档窗口 stageBottom 与 listBottom 差均为 0）。1366×640 地图 746×744（此前 420）、1280×500 746×681、1440×900 746×650、1920×1080 746×830、390×844 324×604，均无横向溢出。曾出现的高度门控误伤列顺序（短桌面窗口地图落入左 340px 窄列）已修复。e2e 覆盖 1280×500/1440×600/390×844 × 三语，含卡片裁剪探针。
- **A76**：安全状态轮询按代际高水位排序（数值化 date+ordinal 比较，非词法后缀）；旧代际（并发/乱序/CDN 陈旧）不再接受；实体记录原子校验（畸形记录→整个 overlay 无效而非静默清空）；首次取失败报 unavailable/stale，后续失败保留最近接受的关闭并标 stale；statusPublishedAt 超过 30 分钟即使 200 也报 stale；测试覆盖乱序、陈旧空载荷、畸形、首败、复开（需更新代际）。
- **A77**：覆盖报告 `formallyPublishedFromThisCandidateSource` 由活动快照已审核 offerings 的 candidateIds 与各源候选联接计算（全局计一次、源间可重叠并注明），随 v2026-09-12.6 输出 CZU 英文源 2 / 捷克源 3 / 博士源 1（全局 4）；jobs 段新增 perSourceRunStatus（逐源 attempt/failed/lastAttemptAt/overdue，绑定源 ID 与 parser，单源刷新不得推进全源成功时间已有字段）；checkout 脚本措辞改为 "local inventory check passed"。
- **A78（部分）**：e2e 更新为 54 用例全过（removed-features 9、map-constrained 9 为新增；参考集查询/精确 ID 断言经由 jobSearchPublished 单元测试直读活动快照），`--workers=2`。真实设备与无障碍仍声称未验证。A72/A73/A81（全 54 校来源盘点、带薪博士联合发现路由、限速/条件刷新/来源级并发策略）未在本轮实施，维持审计原文为待办。

- **带薪科研页排版事故与修复（2026-09-12 晚，用户报告）**：A76 的 30 分钟状态时效阈值使静态 status 文件在每次加载都被判 stale，`jobs.safetyStale` 提示横幅常驻；该横幅作为 `.layout-list` 网格第一个子元素占掉 272px 筛选列，把筛选表单挤到第 2 列（840px）、结果列表掉进窄列——用户截图的混乱由我的改动与该潜伏网格缺陷叠加造成。修复：(1) `.layout-list > .notice` 改为跨全行（`grid-column: 1 / -1`），任何提示不再挤占栏位；(2) A76 阈值语义修正——构建发布的首个接受载荷是发布基线不按墙钟判旧，阈值仅作用于会话内出现的新代际（端点发布陈旧状态）与请求失败；(3) 顺带修复 `.filter-open-mobile` 被 `.btn.primary` 优先级压制而在桌面常显的既有问题。全站扫描 10 条路由 × 390/768/1043/1280/1920 共 50 组合：无横向溢出、无表单错位、按钮仅移动端显示；e2e 54/54、单元 97/97。

- **列表页顶部对齐修复（用户报告）**：桌面筛选卡顶部渲染了移动端抽屉的"关闭筛选"按钮——`button.btn`（特异度 0,1,1）压过 `.filter-sheet-close` 的 display:none（0,1,0），加上结果列计数行 14px 外边距，两列顶线视觉错开约 37px。修复：关闭按钮改用 `button.filter-sheet-close` 隐藏（仅移动端抽屉打开时显示），计数行 `:first-of-type` 外边距归零；两列顶线在 1440/1280 等宽度完全对齐（formTop == resultsTop）。e2e 54/54、单元 97/97。

- 验证：Python ingestion+OPM **183 passed**；Web 单元 **97 passed**；Astro check 53 文件 0 error；Go 两模块通过；`publish.py --check`/`--check-sources`/Node verify 通过（10 jobs）；`check_framework.py` 337 键×3、12 图通过；Playwright **54 passed**（`--workers=2`）；构建 15,299 页。托管 CI/CD、部署与 CDN 传播仍未验证。

## 第五轮审计补充（2026-09-12，历史记录）

报告：[第五轮全面审计与 Agent 执行指南](Czech_Uni_Apply_第五轮全面审计_2026-09-12.md)，证据：`work/audit5-2026-09-12/`。本轮实际核验 MUNI/CZU 官网、回放解析、构建及浏览器搜索，新增 A67–A81；没有激活新快照或修改业务代码。

- 当前 `v2026-09-12.4` 正式岗位 5，默认硕士结果 3，博士注册 required 结果 0；MUNI 4 条官网目标机会已在候选但全部未发布。发现金额、资助／博士注册识别、候选重放和审核发布瓶颈。
- `CZU` 搜索 0，学校完整英文名搜索 3；地图短窗口学校卡片／列表遮挡及捷克文移动端横向溢出已复现。
- **用户最新产品决定优先于下文历史需求：纯浏览；移除“我的清单”和“比较”；禁止公共用户注册私人账户。** 当前功能尚未移除，按第五轮 A80 同步修改代码、三语、文档、OPM 与验收。
- 最新复测：Web 85 通过，Astro 54 文件零错误，Go 两模块通过，构建通过；Python/OPM 合计 167 通过、1 个固定时间 cooldown 测试失败。浏览器初跑 38/39，固定两进程复跑 39/39。不得继续笼统声称所有本地检查通过。
- GitHub 策略及 guanfu.online 已核查，详见报告第 10 节；保留 Scrapling，重点改进可恢复任务、源级限速、变化检测和已知岗位复查。地图修复／模块移除／内容扩充均为后续实施任务。

更新日期：2026-09-12。本文只记录仓库中可核对的实现与验证结果，并分别标明候选采集、人工审核、不可变发布、本地调度和线上部署。数字必须带分母、时间和数据层级，不能把某个官方目录的完整读取写成全部招生或岗位齐全。

## A61 / A63（2026-09-12，第四轮审计 Batch 5）

- **A63** 岗位与项目列表共用 `FilterDrawer`／`ModalDialog`。手机宽度下筛选为 `role=dialog` 且 `aria-modal`：打开后焦点进入抽屉标题，Tab／Shift+Tab 封闭在抽屉内，背景 `inert`，Escape／关闭／遮罩／查看结果把焦点还给触发按钮。桌面 ≥1024px 仍是非模态侧栏。手机导航抽屉使用同一组件。
- **A61** `apps/web/tests/e2e/` 用 Playwright 1.63.0 测已构建制品（`astro preview` 固定 `127.0.0.1:4173`）。矩阵覆盖三语 × 390／768／1440 的授课语言入口、列表／详情、比较与收藏、语言保持、清空筛选、空结果、404、目录失败重试、抽屉键盘、地图瓦片桩与阻断回退。CI 增加 Browser acceptance；`main` 交付制品需要该任务成功。`scripts/check_framework.py` 现核对 DOT／OPL 与 `model.json` 一致，并用 SVG `<title>`／PNG 魔数做语义检查，不要求 Graphviz 字节相等。
- 验证：Web 单元 `85 passed`；Playwright e2e `39 passed`（含三语抽屉焦点、语言保持、失败重试、地图瓦片桩／阻断）；Astro 54 文件 0 errors；`check_framework.py` 与 `tests/test_opm_generation.py` 通过。口径：`CI configured; local checks passed; hosted CI/CD not verified`。未声称分支保护。未改写旧快照，未做实网采集发布。

## A57 / A64 / A66（2026-09-12，第四轮审计 Batch 4）

覆盖报告 `data/sources/coverage/source-coverage.json` 绑定活动快照 `v2026-09-12.4`，生成于 `2026-09-12T17:26:51Z`，谓词版本 `coverage-predicates-v2`。同一输入再生成一次数字不变。

- **岗位来源（A57）**：生产发现入口现计入 `official_job_listing` 与先前未接入的候选适配器。登记官方岗位源 **24**（含 AVCR 1 个非高校源）；映射基线高校 **22/54（40.7%）**；无登记源 **32/54**。0 个学校宣称校内岗位全集。JCU／UPCE／UTB／VŠE／MENDELU 未重复建源。UJEP／UHK／TUL／OSU 只是把已有解析器接入生产入口。新登记五所官方列表：Slezská univerzita（`msmt-vs_19000`）、Veterinární univerzita Brno、Univerzita obrany、VŠTE、VŠPJ。解析器测试覆盖未出现在种子常量中的稳定 ID、限流冷却不请求、不因 429 下架。这五所尚未做全量实网发现，也没有新岗位进入正式快照。
- **候选口径（A66）**：candidate 文件 128 条；`currentCandidates`（非归档且非 closed/expired/unavailable）**90**；`supportedCandidates`（另要求 `catalogueScopeStatus=included`）**77**；未标范围 **13**。current 带薪硕士范围 **22**；supported 带薪硕士范围另计。正式快照公开带薪硕士岗 **3**（CZU A1／D1／T1）。单源刷新不能把 `lastSuccessAt` 写成全源成功。
- **Retry-After（A64）**：429／503 解析 delay-seconds 与 HTTP-date；>30 秒延迟写入主机冷却并 deferred；无头／非法头仍 3s／12s。限流不是关闭。
- 验证：Python ingestion `166 passed`。未跑五所学校的完整实网发现，也未发布新岗位。静态全量重建与托管 CI 仍未验证。

## A58 / A59 / A60 / A65（2026-09-12，第四轮审计 Batch 3）

- **A58** 版本化安全状态覆盖：`data/published/safety/` 独立于不可变快照。已核验整岗／单轮关闭写入覆盖；HTTP 503 不写关闭；快照回滚不能去掉之后的覆盖。列表、详情、收藏和申请按钮在 JS 路径上应用覆盖，墓碑保留。托管 CDN 五分钟传播仍未验证。
- **A59** 生产 Go API 默认读取 `data/published` 并校验清单哈希，拒绝 `ui_fixture`，除非 `CATALOG_ALLOW_FIXTURE=1`。`/readyz` 返回发布版本、记录数和 safety 世代。`httptest` 覆盖拒绝夹具、无效发布、筛选、locale、分页和方法错误。
- **A60** `config/checkout-manifest.json` + `scripts/checkout_inventory.py` 定义干净检出。CI 增加检出检查和制品 provenance。口径：`CI configured; local checks passed; hosted CI/CD not verified`。未执行 `git add --all`，未声称托管 CD。
- **A65** 发布在 `refresh.lock` 内钉扎候选世代并核对复制哈希，再释放锁做校验。分片分配持久化，名录增减不轮转邻居。漏跑：同余日等待；>120h 才单分片补跑。Go 调度计划表在 `apps/api/migrations/002_scheduler.sql`，只调度现有 Python 命令。
- 活动快照仍是 `v2026-09-12.4`，旧快照未改写。空安全覆盖世代 `s2026-09-12.0`。
- 验证：Python ingestion `157 passed`；Web `82 passed`；Astro 52 文件 0 errors；Go catalog 与 API `httptest` 通过；`publish.py --check` 与框架检查通过（348 个三语键、12 张 OPM 图）。未跑静态全量重建，也没有托管 CI run URL。浏览器点击关闭传播与 CDN 五分钟目标标未验证。

## A54 / A56 / A62（2026-09-12，第四轮审计 Batch 2）

- 新活动快照 `v2026-09-12.4`。登记库存仍是 5,019 条原文标题，`verifiedAt` 不再用目录生成日冒充审核日。正式招生摘录必须 `publicationStatus=approved` 且绑定 fact-v1。
- 第一批已审核 CZU 招生：**英语本科信息学** `inv-898e810ed190`、**英语硕士信息学** `inv-ac1fecbdfc9c`、**捷克语 GIS 本科** `inv-c50825f0199c`、**捷克语博士应用与景观生态学** `inv-330bf56297af`。学费双轨 3,200 / 500 EUR 来自英语项目页；捷克入口未公布学费不写成免费；UIS 标为通用入口。其余 CZU 36/129/60 候选仍待审。
- 查理大学／马萨里克示踪 4 条补了同等审核绑定，未审 tracer 不再进入招生摘录。
- 岗位列表和详情用本地化月薪／税前标签，不再渲染 `month (gross)`；无窗口的官方说明岗主按钮仍是“查看官方申请说明”，并写明打开公告不等于提交申请。岗位职责与材料在来源未提供时保持未知。
- 验证：Python 145；Web 78；Astro 49 文件 0 errors；`v2026-09-12.4` 双门禁通过。静态全量重建未跑。

## A52 / A53 / A55（2026-09-12，第四轮审计后第一批）

按第四轮执行顺序完成 Batch 1：收紧发布契约、绑定审核到事实／译文／证据，并停止把运营方中留服名单写成官方查询结论。旧不可变快照 `v2026-09-12.2` 未改写。

- 共享语料：`tests/contracts/cases.json`。Python 与 Node 均拒绝非法窗口、缺来源／证据 URL、改原文／中文标题／薪资／博士要求仍沿用旧审核、证据哈希不一致、负薪与不受控币种周期税码、`2026-02-30`、未审 tracer、缺审核角色、运营方名单冒充官方 listed。基线与仅更新抓取时间戳仍通过。
- 审核载荷版本 `fact-v1`：规范化事实哈希、逐语种译文哈希、证据哈希、`reviewer.role=operator_source_review`。该角色是既有内部来源／语言审核，不是新的外部人工认证。
- 中留服：公开 `lookupStatus=unverified`；`operatorListStatus` 单独保存 24 所匹配／30 所未出现在该名单；三语界面区分官方查询与运营方名单。
- 新活动快照 `v2026-09-12.3`。岗位 5 条：2 条 CUNI 博士后 + 3 条 CZU（A1/D1/T1）。`job-41000-1601`（A2）因候选源哈希已变为 `sha256:f54c86cf…`，与 2026-09-12 审核记录的 `sha256:c59db43a…` 不一致，按 A53 下架待重新审核，没有为了维持数量继续发布。
- 验证：Python ingestion `145 passed`；Web `77 passed`；Astro 48 文件 0 errors；`publish.py --check` 与 Node `verify:published` 均通过 `v2026-09-12.3`；Go catalog 测试通过；框架 326 个三语键、12 张 OPM 图通过。完整浏览器矩阵与静态重建未在本批重跑。

## 第四轮全面审计（2026-09-12）

最新审计与后续 agent 逐步执行指南：[Czech_Uni_Apply_第四轮全面审计_2026-09-12.md](Czech_Uni_Apply_第四轮全面审计_2026-09-12.md)。本轮仅新增审计证据与报告，没有修复业务代码、修改来源数据、切换正式快照或部署。

- 现有 Python 143 项、Web 76 项、Astro 48 文件检查通过，不代表业务门禁完整。新增隔离反例确认非法窗口、缺必需 URL、变更事实／译文但沿用旧审核、证据哈希不一致和未审 tracer 等仍可通过；A32／A39 应理解为部分完成，详见新审计 A52–A55。
- 当前注册表实际有 **15 个岗位来源，映射 13/54 所高校（24.1%），尚缺 41 所**。下方 10 来源、8/54、46 所缺口属于历史／过时口径；不能继续用于当前工作分配。重新计算的报告仅保存在 `work/audit4-2026-09-12/coverage-recomputed.json`，未覆盖原始历史报告。
- 当前 128 条候选中，77 条符合“非归档且显式 included”，其中 73 条待审；覆盖生成器的另一谓词报告 90 条 currentCandidates。两者不是相同统计口径，须按 A66 统一定义和来源运行范围。
- 本轮三语 × 390/768/1440 × 六类路由共 54 次浏览器加载无 pageerror／横向溢出，但复现了手机筛选抽屉焦点逃逸及岗位详情薪资枚举未本地化。完整职责、资格证据与申请说明仍不足，详见 A62／A63。
- 优先按报告修正发布／审核契约，再让已审核 CZU 项目窗口进入三语网页，并补齐关闭状态传播、可复现 CI/CD 与常驻调度。地图提前集成继续视为用户授权决策，普通滚轮与既有回退实现保留。

## 当前正式发布边界

- 唯一活动指针是 `data/published/current.json`，当前选择不可变快照 `v2026-09-12.4`。废弃的 `data/published/current/` 兼容副本不参与构建、浏览器资源或覆盖统计。旧快照 `v2026-09-12.2` 与 `v2026-09-12.3` 仍保留且未改写。
- 活动快照含 54 所高校、54 条招生／申请入口、5,019 条 MŠMT 登记项目库存、53 所有库存学校、54 条坐标、5 条已审核岗位和 4 条已审核招生摘录。默认硕士可申请岗位仍为 CZU A1／D1／T1。A2 因源哈希变化待重审。
- 54 所高校的公开中留服 `lookupStatus` 均为 unverified。运营方名单匹配 24 所、未出现在该名单 30 所，单独标注，不是官方 listed／not_found。
- 登记项目库存说明项目获准／正在实施，不等于该入学年度正在招生；没有学校／院系申请窗口证据时保持未知。网页当前未把 DZS 候选或待审岗位绕过门禁写入活动快照。
- Python 与独立 Node 发布检查均通过。该结论覆盖结构、关系、证据、URL、窗口日历／时区和审核绑定规则，不替代每条事实的人工核验。

## 2026-09-12 网页内容与 CI/CD

- CZU 岗位源在 `2026-09-12T12:46:54Z` 再次完整读取：公开结果、REST 全文和 6 个活动 WordPress ID 对齐；混在返回片段中的过期行被显式识别并跳过，不会使整个活动源误判失败。5 条进入支持范围，1 条行政岗位隔离；其中 4 条完成三语与源哈希审核并正式发布。
- 网页默认岗位列表现为 CZU 工程学院 A2、A1、D1、T1 四条。官方公告中的全职薪资基准均为每月税前 60,000 CZK；岗位实际工时分别为 1.0、0.5、1.0、0.8 FTE，可到岗日期均为 2026-10-01。`salary.basisFte`、`employmentFte` 与 `employmentStartsAt` 已分字段保存和显示；公告未写工作语言时显示 BCP 47 `und` 对应的“公告未说明”。
- 两条旧 CUNI 硕士后岗位因最新目录证据包不再提供岗位级学历、带薪与工作语言依据，其旧审核已撤销，没有为了维持数量继续发布。当前 6 条正式岗位由 2 条 CUNI 博士后和 4 条 CZU 硕士可申请岗位组成。
- `.github/workflows/ci.yml` 在 pull request、`main` 提交和手动触发时运行 Python 全套采集测试、三语一致性、活动快照及下一发布选择门禁、OPM／文档框架、两个 Go 模块、Web 测试、Astro／TypeScript 检查、独立 Node 发布检查和静态构建。只有 `main` 的前置作业全部成功才上传绑定提交 SHA、保留 14 天的 `apps/web/dist` 制品；外部 Action 固定到完整提交 SHA，Dependabot 每周检查 Actions、npm、pip 与两个 Go 模块。
- CI 不访问实时高校来源，避免上游波动令代码验证随机失败；实时采集由部署后的短周期／五天调度承担。仓库当前没有 Git remote、托管站点或域名，因此这里是已配置并通过本机等价检查的持续集成与制品交付流程，尚不能声称 GitHub 托管执行、分支保护或公网自动部署已经启用。

## 2026-09-11 高波动来源实跑

- DZS `studyin.gov.cz` 完整候选刷新在 `2026-09-11T19:30:20Z` 成功：英文和捷克文各 5,137 个相同 UUID，映射到 MŠMT 基线 54/54 所，未映射 0。其开放筛选本轮报告 0；这只表示 DZS 未报告开放，不能写成 5,137 个项目全部关闭。数据保存在 `data/sources/admissions/studyin-programmes.json`，状态为 `candidate_not_published`。
- CZU `study.czu.cz` 独立候选刷新在 `2026-09-11T19:31:12Z` 成功：REST 报告 36 条／1 页，实际唯一记录 36 条，详情解析 36/36；范围为英语本科 10、硕士 26，分属 6 个院系，36 条均有完整申请起止。按抓取时点，35 条将在 2026-09-14 或 09-15 开放，1 条 Danube AgriFood Master 仍为 2026-01-15 至 02-28 的旧关闭轮次；详情日期与官方开放页均为当前 0 条开放。36 个项目按钮当时均无链接，候选只保留经验证的通用 UIS 入口，不伪造逐项目申请目标。
- CZU `studuj.czu.cz` 捷克入口独立候选刷新在 `2026-09-11T19:33:42Z` 成功：首页总数、programme sitemap 详情数和实际唯一详情均为 129，解析 129/129；本科 55、硕士 74，捷克语授课 94、英语授课 35。128 条有完整申请起止，34 条将在 09-14 或 09-15 开放，94 条已关闭，Danube AgriFood Master 未公布窗口；127 条有项目级 UIS 链接，2 条只保留通用入口。与英语入口交叉核对发现两个轻微标题变体，英语入口还多一条双学位记录，故明确报告 `disagrees`。这两个本科／硕士来源本身不含博士，也未绕过三语门禁发布。
- CZU 博士学院证据独立候选刷新在 `2026-09-11T19:42:37Z` 成功：以 MŠMT 紧凑库存的 60 个博士 offering／六学院为固定分母，9/9 个官方资产 HTTP 200，60/60 项匹配，捷克语与英语各 30 项；60 项均有 2026/27 学院窗口证据，34 项至少有一个起止完整窗口，抓取时 60 项全部关闭并等待下一学年窗口。未知开始日、FTZ 条件阶段和未公告轮次均不推断为开放；TF 图像 PDF 转录绑定精确 SHA-256。该完整性只覆盖已配置的 2026/27 证据，60 条候选尚未完成三语审核或正式发布。
- 4 小时岗位目录发现在 `2026-09-11T19:24:00Z` 成功读取当时全部 10 个已登记官方来源：Charles University、MUNI、UPOL、VŠB-TUO、UCT Prague、CTU 校级公告板、CTU FEE、VUT、CZU 和 AVCR，失败来源 0。本轮发现 59 条范围内记录；该段数字保留为整轮实跑证据，不用 2026-09-12 的 CZU 单源刷新冒充新一轮全来源运行。当前候选文件共 128 条；按“非归档且属于支持范围”口径为 77 条，其中 73 条仍为 `review_pending`、4 条已发布，不能绕过事实与 zh-CN / en / cs 审核发布。
- 该岗位发现任务的第一次尝试只完成 8/10 个来源，CTU 校级公告板与 FEE 入口发生短暂传输失败，任务正确报告部分失败且未按缺席归档旧记录。对幂等官方 HTML／PDF 读取增加 3 秒、12 秒两次有限重试后，最终完整重跑恢复 10/10；CTU 校级公告板读取 20 条人事公告及其 PDF，扫描版继续使用有页数和大小上限的本地 OCR，任一附件最终不可读仍会使整源不完整。VUT 校级 Jobs.cz 组件通过公开 GraphQL 真分页读取 18 条列表和逐项详情。CZU 校级站的公开列表 7 条与 REST 全文 7 条按 WordPress ID 完全对齐；5 条进入研究／技术候选，其中 4 条明确硕士门槛、全职基准月薪 60,000 CZK，2 条行政支持岗位被隔离。
- 1 小时岗位状态复核在 `2026-09-11T19:43:39Z` 检查 64 条当前范围候选，HTTP 成功 64、失败 0、本轮新确认关闭 0。两条 VUT 支持类记录以 `catalogueScopeStatus=excluded` 和“超出支持范围”归档；只有确实从完整列表消失的记录保留 `unavailable` 语义。
- 岗位来源覆盖仍不齐全：10 个来源中 9 个映射到 8 所 MŠMT 高校，覆盖 8/54 所（14.8%）；AVCR 是独立研究机构集合。8 所均已有校级聚合入口，CTU 另有 1 个 FEE 院系补充源，且 0 个来源声明覆盖校内全部岗位。其余 46 所高校尚无已登记官方岗位来源，不能由“10/10 来源成功”推断为没有岗位。
- `data/sources/coverage/source-coverage.json` 在 `2026-09-11T19:46:56Z` 从活动指针、MŠMT 基线、来源注册表、候选、调度状态生成固定分母报告。它分别保存 DZS、CZU 两条本科／硕士来源的范围与交叉差异，以及 CZU 博士 60/60 基线匹配结果，并明确输出 `completeAdmissionsCatalogueClaim=false` 与 `completeSchoolJobCoverageClaim=false`。
- 当前本机只完成命令式实跑和调度状态记录；常驻 Go 后台任务、PostgreSQL 状态和线上站点尚未部署。稳定五天分片在本地状态中仍为 overdue，不能声称网站已持续自动刷新。

## 第三轮复审 A31–A41

| 审计项 | 当前状态 | 可核对结果 |
|---|---|---|
| A31 浏览器数据绕过快照 | **本地实现并自动化验证** | Web 构建启动时固定活动版本，`@published` 和版本化 browser asset 只从该不可变快照生成；测试覆盖源目录和遗留 public 目录不能污染构建。 |
| A32 门禁只验字节／数量 | **本地实现并自动化验证** | 固定 9 个必需文件，校验清单、路径、哈希、唯一 ID、外键、窗口、来源证据、安全 URL、资格和逐语种审核；空清单、缺文件、伪造 counts、未知雇主、缺语种、未审校、危险 URL 和过期审核测试均失败。 |
| A33 发布／回滚非原子 | **本地实现并自动化验证** | 唯一 staging → 业务校验 → 不可变 snapshot → 原子 `current.json` 指针；失败候选和 `--force` 不改变旧指针。发布锁、回滚、构建中切换指针及固定版本测试通过。 |
| A34 岗位复核丢多轮 | **本地实现并自动化验证** | 每个 window ID、原顺序、时区和日期精度独立保留；一轮关闭另一轮开放／未来、未知截止、整岗关闭优先和输入换序样本通过。请求失败保留 last-good。 |
| A35 失败被登记为成功 | **本地实现并自动化验证** | attempt、抓取／解析结果和成功时间分开；短暂传输失败及 408／425／429／5xx 的幂等读取只进行 3 秒、12 秒两次有限重试。最终 503、部分失败、解析为空与分页不完整均不推进 `lastSuccessAt`，所有入口尊重 `retryAt`，失败来源仍统计 SLA。 |
| A36 锁与租约竞态 | **本地实现并自动化验证** | worker 和调度状态使用跨平台 OS 文件互斥；租约含 owner/token、续期、过期回收和条件释放；两个独立进程竞争与采集／复核共锁测试通过。 |
| A37 动态发现未进真实流程 | **生产入口与真实来源运行通过；发布闭环待人工审核** | 注册表已驱动 10 个真实来源的列表、分页和详情发现；Charles AJAX、VUT GraphQL、CZU 公共分页 + REST 交叉核对、CTU 公告 PDF/OCR、UPOL 详情、完整消失和 AVCR 雇主隔离均进入生产入口。新候选仍未绕过三语审核。 |
| A38 跨岗位污染与资格猜测 | **本地实现并自动化验证** | Charles、UPOL、MFF、MUNI、VŠB、UCT、CTU、VUT、CZU 等页面使用实体边界或逐项全文；否定与备选资格优先，没有证据保持 `unknown / unspecified`。教学、行政、研究支持与科学传播岗位不会只因背景文字提到研究而进入候选；技术职责可由全文而非标题判定。 |
| A39 中文标题自动通过三语审核 | **门禁完成；候选审核仍待人工** | 审核按 locale 与源哈希记录；中文词典或专名原样保留不自动通过，源资格内容变化使旧审核失效。活动快照只含 6 条通过审核的岗位；两条失去岗位级证据的旧 CUNI 审核已撤销。 |
| A40 地图提前合并与叙述差距 | **提前合并是用户确认的集成评估决策；正式组件已继续修正** | 当前明确为 MapLibre + OpenStreetMap 在线栅格瓦片，并保留内置 14 州概览图；低缩放聚合和同坐标近景展开已在正式组件验证。没有声称 PMTiles、自托管、固定成本或大陆低延迟。 |
| A41 瓦片失败、键盘和移动回退 | **本地浏览器验收通过** | 交互模式表示 54 所学校；聚合与单校按钮支持 Enter／Space 并保留焦点。390×844 阻断外部瓦片后自动回退，内置图与列表仍各有 54 所，重试路径通过，无 pageerror。 |

## 新增 A42–A51

| 验收项 | 当前状态 | 可核对结果 |
|---|---|---|
| A42 DZS 完整性与权威边界 | **真实网络运行通过；正式内容待审核** | 5,137 个 UUID、en/cs 集合一致、54/54 映射、0 未映射；任一分页或两语不一致均使任务失败。开放筛选缺席不触发关闭，输出只进入候选层。 |
| A43 高波动来源短周期 | **本地实现、测试及单次实跑通过；常驻部署未完成** | 调度版本 3.3 分别维护岗位状态 1 小时、岗位发现 4 小时、DZS 项目 2 小时、CZU 英语项目 2 小时、CZU 捷克入口本科／硕士项目 2 小时和 CZU 博士学院证据 2 小时；各自有租约、退避、成功时间和 nextDueAt，稳定分片仍保持 120 小时上限。 |
| A44 地图普通滚轮缩放 | **真实浏览器验收通过** | Chrome 在画布上收到 1 个不带 Ctrl／Command／Shift／Alt 的 wheel 事件，11 个地图控件位置发生可观察变化，54 所学校仍完整表示。 |
| A45 固定分母覆盖报告 | **本地实现并自动化验证** | 报告按 MŠMT 54 所基线分开计算 DZS 来源快照、CZU 声明范围、岗位来源接入、来源深度、来源运行成功、候选和活动快照；当前岗位学校来源接入为 8/54，8 所有校级聚合入口、CTU 另有 1 个院系补充源、0 个完整覆盖声明，而非 100%。 |
| A46 关闭状态到公开层 | **候选复核与发布隔离已验证；部署传播未完成** | 较早实跑已归档确认关闭／过期记录；最新一轮 64/64 状态页成功且无新增关闭，范围排除和官网消失使用不同生命周期理由。活动快照不含已关闭岗位。部署后仍须验证状态覆盖／新快照、三语页面和缓存能在目标时间内一致下架。 |
| A47 CZU 英语项目重点来源 | **真实网络全量运行通过；正式内容待三语审核** | REST 总数／页数、36 个稳定 ID 和 36/36 详情全部对齐；保存窗口、原币学费、学制、院系、来源哈希和通用／逐项目申请链接边界。完整性只对英语本科／硕士范围成立，当前候选未进入活动快照。 |
| A48 CZU 捷克入口重点来源 | **真实网络全量运行通过；正式内容待三语审核** | 首页、programme sitemap 与唯一详情均为 129，129/129 详情解析；按详情保存捷克语／英语、学位、院系、窗口、申请目标和证据哈希。与英语入口的 36／35 数量和标题差异明确保留；完整性只对该站本科／硕士范围成立，博士由独立 A49 来源处理。 |
| A49 CZU 博士重点来源 | **真实网络全量运行通过；正式内容待三语审核** | MŠMT 60 个博士 offering、六学院和 9/9 官方资产全部对齐，捷克语／英语各 30 项；60 项均有 2026/27 窗口证据且当前全部关闭。未知开始日、条件阶段与受审扫描件哈希保护测试通过；完整性不扩大到 2027/28 全网检查或正式发布。 |
| A50 仓库 CI/CD | **配置完成；本机等价检查通过；托管执行待远端** | PR、main 和手动触发执行数据、Python、Go、Web、三语、发布与 OPM 门禁；main 全部通过后才上传提交绑定的静态制品。CI 不实时抓高校。当前无 Git remote／托管目标，故不声称已公网部署。 |
| A51 薪资基准与岗位工时 | **正式数据、三语页面和双实现门禁完成** | CZU 60,000 CZK 的 1.0 FTE 薪资基准与岗位实际工时分字段保存。当前活动快照在 A53 后为 A1／D1／T1 三条；A2 因源哈希变化待重审。 |
| A52 完整业务 schema | **本地实现并自动化验证** | 共享语料由 Python 与 Node 同时拒绝非法窗口、缺必需 URL、负薪／不受控币种周期税码、不可能日期和非法嵌套 tracer 窗口。 |
| A53 审核绑定事实与译文 | **本地实现并自动化验证；6 条中的 1 条因源哈希变化被挡住** | 审核绑定 fact-v1 事实哈希、逐语种译文哈希、证据哈希和审核角色。改薪资／学历／原文／中文标题或去掉审核人后不能沿用旧批准。 |
| A55 中留服不得夸大证据 | **本地实现、快照与三语页面验证** | 运营方名单不再发布为官方 listed／not_found；公开状态 unverified，名单匹配单独标注。 |

地图验收结果在 `work/acceptance-2026-09-10/map-browser-results.json`；截图为 `map-interactive-clusters.png`、`map-interactive-local-tiles.png` 和 `map-external-tiles-blocked.png`。测试稳定验证 UI 分支，没有测量真实 OpenStreetMap 网络性能。

## 验证结果

| 检查 | 结果 |
|---|---|
| Python ingestion 全套 | `145 passed` |
| Web Node 测试 | `78 passed` |
| Astro / Svelte 检查 | 49 个文件，0 errors、0 warnings、0 hints |
| 正式静态构建 | 上一轮 `v2026-09-12.2` 生成 15,278 页；本批未重建静态制品，开发预览已钉在 `v2026-09-12.4` |
| Python 发布检查 | `OK`：活动快照 `v2026-09-12.4` 通过完整性与业务校验 |
| Node 独立发布检查 | 5 条岗位与 4 条已审核招生摘录通过 checksums、references、URLs 和审核门禁 |
| Go catalog / API | `go test ./...` 通过；API 包仍无测试文件 |
| OPM | 从 `opm/model.json` 生成 12 张 DOT/SVG/PNG 图和 OPL；317 条关系的语义与 Graphviz 校验通过 |
| 框架一致性 | 170 个 JSON 文件、三语 326 个键、12 张 OPM 图及本地 Markdown 链接检查通过 |
| 浏览器地图 | 普通滚轮、桌面交互、键盘聚合、三语控制、手机断瓦片自动回退均通过；无 pageerror |
| 浏览器目录边界 | 项目页显示活动版本、5,019 条登记库存、53/54 所库存学校及英语筛选 1,273 个结果；岗位页显示 6 条已审核、默认范围 4 条 CZU，并区分薪资基准、实际工时与可到岗日期；均无 pageerror |

## 仍需完成

1. 为其余 41 所尚无已登记岗位来源的 MŠMT 高校逐校登记官方招聘页，并进一步登记大型学校的院系／研究中心岗位页；没有岗位页的学校须保存“不适用”的官方证据。当前 15 个来源、13/54 所（24.1%）接入率和 0 个完整覆盖声明不能称齐全。
2. 对 73 条当前支持范围内的 `review_pending` 岗位候选、DZS 5,137 条项目候选、CZU 两条来源的 36／129 条本科／硕士记录及 60 条博士记录完成去重、事实与 zh-CN / en / cs 审核；CZU 博士还须在官方发布 2027/28 轮次后刷新窗口，其他学校继续接入院系窗口，随后通过不可变快照发布。
3. 配置 Git remote、分支保护和托管目标，实际运行 `.github/workflows/ci.yml`；随后在部署环境运行 Go 常驻调度、持久数据库／队列和公开状态传播，完成至少一轮真实 120 小时稳定覆盖。本机等价 CI 与命令式采集成功不等于托管流程或自动任务已经上线。
4. 在中国大陆电信、联通、移动真实线路和至少一台目标手机上记录地区、日期、设备、失败率、请求日志与 p95，再决定公共栅格服务、自托管瓦片或商业服务。
5. 完成 A16 的大陆全流程和 A17 的 Go 启动、查询 p95、前端载荷及采集隔离性能记录。

## 自检命令

```powershell
py -3 -m pytest services/ingestion/tests -q
py -3 services/ingestion/src/worker.py --status
py -3 services/ingestion/src/worker.py --refresh-czu-programmes
py -3 services/ingestion/src/worker.py --refresh-czu-czech-programmes
py -3 services/ingestion/src/worker.py --refresh-czu-doctoral-programmes
py -3 services/ingestion/src/build_source_coverage.py
py -3 services/ingestion/src/publish.py --check
py -3 services/ingestion/src/publish.py --check-sources
py -3 work/acceptance-2026-09-10/map_browser_probe.py
py -3 work/acceptance-2026-09-10/catalog_browser_probe.py
py -3 scripts/render_opm.py
py -3 scripts/check_framework.py

cd apps/web
npm test
npm run check
npm run build
node scripts/verify-published.mjs

cd ..\..\services\catalog
go test ./...

cd ..\..\apps\api
go test ./...
```
