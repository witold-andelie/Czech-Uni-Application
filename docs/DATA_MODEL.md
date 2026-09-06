# 数据与分类契约

## 实体

Institution：独立学校／研究机构；id、官方名称、多语显示名、国家、城市、性质、法定类型、官方链接。学院使用 parentInstitutionId，不能计为独立大学。
Programme：学术项目身份、学校、学院、官方代码、学位、学科、官方培养导向。
Offering：项目的具体授课方案、入学年度、校区、模式、授课语言集合。英语和捷克语是独立可选轨道时分为不同 offering；必需双语不可伪装为英语单语。
AdmissionRound：offeringId、轮次、开始／截止、时区、日期精度、材料及缴费期限、状态。新年度不得覆盖旧年度。
Requirement：类型、必要／可选／未知、原文证据、多语说明。分别记录入学语言、授课语言、实习和临床语言要求。
Tuition：金额、币种、周期、适用人群、额外费用、未知原因及证据；免费也需要来源。
ResearchJob：雇主、实验室、名称、最低学位、博士学位要求、博士注册要求、报酬证据、工资口径、合同期限、工时、工作语言、截止、申请入口。
SourceEvidence：URL、机构、提取时间、页面更新时间（若有）、原文片段、内容哈希、定位方法、证据支持的字段。
Translation：目标 locale、来源哈希、译文、审核状态、审核时间；同一实体三语共用事实字段。
ReviewRecord：审核人、字段、决定、理由、版本；PublishSnapshot：本次发布版本、三语内容及来源集合。
SavedItem / ComparisonSelection：稳定实体 ID；个人偏好不改写官方事实。

## 授课语言规则

- `teachingLanguages=["en"]` 是英语单语方案，`["cs"]` 是捷克语单语方案。
- `languageMode=joint_required` 且包含 en、cs 表示必须两种语言，默认英语入口不含此方案。
- 同一项目可自由选择英语或捷克语轨道：创建两个 offering，分别显示费用与申请条件。
- 英语单语结果仍展示其他非授课场景的语言要求，不隐藏临床／实习捷克语门槛。
- 语言未核实：留在审核库；不进入英语或捷克语已核验结果。用户主动查看未知线索时需清楚标注。
- “包含双语项目”必须是显式选项，切换语言界面不改变其值。

## 科研资格规则

doctorateRequired：true / false / unknown。
doctoralEnrollment：required / optional / not_required / unspecified。
minimumDegree：bachelor / master / doctorate / other / unknown。
硕士可申请判定：最低学历不高于硕士、有资格证据且未要求博士学位；仍需满足技能和经验条件。未知项不自动推断为可申请。
“无需注册博士”严格筛选只包含 not_required；optional 单独可选，unspecified 显示“公告未说明”。
paidStatus：confirmed / unconfirmed / unpaid；带薪主库仅 confirmed，金额可以未公布。
工资单独记录 basisFte，未说明 0.5–1.0 工时与金额的对应关系不得自动折算。

## 状态与时间

记录工作流：draft → verified → translated → published；源更新后为 needs_review；过期为 archived。
核验、翻译、发布资格应各自存字段，不能让一个字符串掩盖部分语言尚未复核。
截止状态依据明确时区和精度；只有日期的记录以“按公告日期已截止”表达，不能声称知道精确截止时刻。
截止与核验状态独立：已核验的过期记录仍能成为历史样本，但不属于正在开放。
金额、学历、截止等关键冲突进入人工队列；保存所有候选证据，不静默覆盖。

## 去重与分类

学校：官方机构代码／域名和法定身份核验；项目：官方代码＋学校；offering：项目＋语言方案＋年度＋地点／模式；招聘：雇主＋官方职位 ID，无 ID 时用规范链接和内容辅助。
应用／职业导向依据项目或官方描述，不以校名、排名缺失、私立性质推断。
VOŠ 独立分类，学位不可伪造为本科／硕士。

## 刷新、覆盖与岗位生命周期字段

CrawlRun：id、scheduledAt、startedAt、finishedAt、scopeVersion、expectedSources、successfulSources、failedSources、status（queued/running/partial/succeeded/failed）、retryCount。
SourceRegistry：institutionId、sourceType、sourceLanguage、officialUrl、adapter、lastAttemptAt、lastSuccessAt、nextDueAt、failureReason、coverageStatus。官方名录基线保存版本及日期。
ResearchJob 增加：sourceUrl、applicationUrl、applicationMethod（web_form/official_instructions）、applicationHostVerified、applicationUrlCheckedAt、lifecycleStatus（open/closed/expired/unavailable/unknown）、closedAt、closureReason、closureEvidenceId、lastStatusCheckedAt、nextStatusCheckAt、visibility。
所有关闭状态基于同一实体 ID 应用于三语视图、索引和缓存。未知和不可访问不能伪造为已关闭；临时不可访问可暂停展示并保留复核原因。
恢复招聘必须有新的官方开放证据；仅页面重新返回 HTTP 200 不够。若新的年度／职位身份成立则创建新记录。

## 学校性质与中留服证据

Institution.ownership：public / private / state / unknown；ownershipEvidenceId 为官方学校性质证据。此字段与大学类型及应用导向独立。
Institution.cscseReference：lookupStatus（listed / not_found / unverified）、officialMatchedName、matchedAwardingInstitutionId、lookupUrl、checkedAt、sourceVersion、evidenceId、reviewer、matchConfidence。
认证参考匹配以官方颁证学校为准，曾用名、校区、合作办学不得仅靠名称模糊匹配。风险公告另存 notices，含适用项目、模式、时间范围与有效状态；新公告不因 lookupStatus=listed 被隐藏。
当前未实际逐校完成查询，禁止批量赋值 listed。not_found 不代表不可认证，unverified 不得通过搜索推断为已列出。

## 通用申请轮次

ApplicationWindow：id、ownerType（offering / research_job）、ownerId、academicYear（岗位可空）、roundNumber（可空）、roundLabelOriginal、roundType（regular/supplementary/rolling/unspecified）、applicantScope、opensAt/closesAt（各自允许未知）、timezone、datePrecision、status、conditionalOnVacancies、applicationUrl、sourceEvidenceId。
每个窗口保存独立链接与三语说明，项目语言轨道不同不得混用费用／时间；岗位的招聘轮次与“第几轮面试”分开，面试轮次不作为申请轮次。
窗口结束只关闭对应窗口。有未来确认窗口则标“下一轮尚未开始”；有当前开放窗口则保留公开机会；雇主明确整个岗位招满或撤回则整体关闭，优先级高于未来旧时间表。
官网只有月日而没有年份时不得擅自补当年；保留原文并人工核验后才启用精确计时。
