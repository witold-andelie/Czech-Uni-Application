# 实施架构

## 模块边界

- apps/web：TypeScript + Astro 静态三语页面，Svelte 用于筛选和地图等局部交互（收藏/比较按 A80 移除）。公网站构建只读取一次固定的不可变发布快照。
- apps/admin：审核后台的预留边界；当前只有说明文件，来源注册、待核验队列、逐语种复核和发布 UI 尚未实施。
- services/ingestion：Python 离线采集、动态岗位发现、变化检测、本地调度参考实现和发布门禁；不进入在线请求链路。
- services/catalog：Go 实现学校、项目、offering、申请轮次和科研岗位读写规则，作为 apps/api 内部模块，不另起微服务。
- apps/api：Go 常驻服务骨架，提供同域查询 API 边界；完整后台认证、数据库发布控制与生产调度尚未部署。
- locales：静态 UI 词条和术语表；动态译文属于内容数据。
- schemas：基础契约；实施时扩展实体校验，禁止删去未知状态和证据字段。
- data/sources：采集候选与来源注册表；data/published/snapshots：不可变发布版本；data/published/current.json：唯一活动版本指针；work：原文、日志、调度状态与验收证据。
- design：共享视觉变量。
- opm：模型源、DOT、SVG、对应 OPL、需求追踪与实施任务。

## 综合性能与启动速度的方案（不是已实现依赖）

Web 采用 TypeScript + Astro 静态输出和 Svelte 局部交互；在线服务采用 Go；数据库采用 PostgreSQL，初期建议 Supabase Free；离线采集使用 Python + Scrapling。具体比较和启动性能预算见 LANGUAGE_STACK.md。
小规模初版可以发布静态 JSON 快照并使用轻量搜索；生产阶段保留同一数据契约迁移到服务端索引。
实施时查询官方文档并固定具体版本，不能将此文当作最新 API 文档。Node.js 只在构建阶段使用；第一版不添加 Node SSR 常驻运行时。应用与后台不采用两个前端组件框架。
采集与翻译在后台批量执行，经过审核发布事务后才对公众可见；不把抓取失败传给访客作为空项目。
列表 URL 保存过滤条件；语言切换仅替换 locale，并用 `location.replace` 覆盖当前历史项，后退不回到另一种界面语言的同一页。
域名、托管、数据库、邮件分开配置。主访问市场以中国大陆为重要验收区域；位置与后缀不能替代实测。

## 可靠性

发布候选先复制到唯一 staging，随后运行 `publication_contract.py`。门禁固定必需文件集合，并验证清单、路径、哈希、记录数量、唯一 ID、外键、申请窗口、证据引用、安全 URL、资格状态和逐语种审核记录。岗位审核按 locale 绑定源内容哈希；源资格内容变化后旧审核失效。

门禁通过后候选成为 `data/published/snapshots/<version>/` 下的不可变目录；最后只原子替换 `current.json`。失败候选留在 staging，原活动指针不变，`--force` 也不能绕过业务规则。发布和回滚共用操作系统文件互斥锁。

`apps/web/scripts/run-with-published.mjs` 在构建开始时解析一次活动版本，将 `@published` 固定到该绝对快照，并把浏览器需要的库存资源生成到 `.generated/public/<version>/data/published/<version>/`。浏览器 URL 含版本号；构建不读取 `data/sources/` 或遗留 `apps/web/public/data/`。构建期间切换活动指针不会混入新版本。

发布必须原子化绑定事实、三语译文及证据版本；不可出现语言 A 新费用、语言 B 旧费用。
后台可发布“已截止／撤回”状态覆盖，立即停止开放标识，同时保留旧内容核验记录。
UI 搜索与详情可通过本域名缓存或预渲染输出；不得依赖 Google 服务才能看到文字。
后台凭据仅服务端保存；公网站不暴露采集登录信息或用户申请材料。

动态岗位发现由 `data/sources/registry.json` 驱动列表、分页、详情和附件提取。Charles 解析器调用官方 AJAX 端点并用 `p` 参数读取真分页；VUT 从校级门户公开配置读取 GraphQL 全分页和逐项全文；CTU 校级公告板核对精确总数并提取 PDF，扫描件走有大小／页数上限的本地 OCR；CZU 同时读取 WP Job Manager 公共分页与同站 REST 全文，并按 WordPress 岗位 ID、标题和详情 URL 交叉核对。其他适配器把相对／绝对链接、捷克语路径和重复页归一为稳定 ID。AVCR 聚合页只有辨认实际研究所雇主后才能进入核验，无法归属的候选隔离。只有源级完整性成立时，旧候选从目录消失才转为 `unavailable`；仍在列表但全文不符合研究／技术范围的记录标为 `catalogueScopeStatus=excluded`。所有新候选仍要经过资格证据和三语人工复核才能发布。来源记录另存 `coverageScope` 与 `sourceCoverageClaim`，使校级聚合、院系局部和独立研究网络不会被合并成“学校岗位完整覆盖”。

CZU 项目高波动源独立于 DZS，也彼此独立调度。`study.czu.cz` 的 REST 总数和分页给出英语本科／硕士目录边界，36 个详情页提供申请起止、学制、原币学费、院系证据和当前申请按钮；开放项目页只作同时刻交叉信号。`studuj.czu.cz` 的公开 REST 受限，采集器改用首页结果数、programme sitemap 和唯一详情 ID 三重核对捷克入口本科／硕士边界，再逐页提取详情，并与英语源按标题／学位交叉核对。源间数量或标题不一致作为数据事实保留，不能强行合并成一致。第三个适配器以 MŠMT 的 60 个 CZU 博士 offering 为固定分母，匹配六学院的官方年度规则；未知开始日、条件轮次和未公告轮次采用保守状态，图像 PDF 转录绑定受审哈希。通用申请系统不冒充逐项目直达链接，三条来源各自只在声明范围内报告完整。原文、哈希和逐请求结果保存在 `work/`，结构化候选留在 `data/sources/`，三语审核前不会进入活动快照。

正式地图当前使用 MapLibre 和 OpenStreetMap 在线栅格瓦片。外部瓦片连续失败或 12 秒未完成时，组件切换至项目内置的捷克 14 州 SVG 概览图，列表和筛选继续工作；用户可手动切换或重试。低缩放用 Web Mercator 屏幕距离聚合相邻点位，聚合及单校点位均为原生按钮；街道级恢复独立点位并偏移完全同坐标学校。该设计满足核心流程不依赖国外地图，但大陆线路、真实移动设备、自托管瓦片容量与成本仍要实测。

## CI/CD

`.github/workflows/ci.yml` 是仓库的确定性持续集成与制品交付入口。Pull request、`main` 分支提交和手动触发都会运行 Python 采集测试、三语键一致性、活动快照完整性、下一发布候选门禁、OPM 语义与文档检查、两个 Go 模块测试、Web 单元测试、Astro／TypeScript 检查、浏览器资源检查和正式静态构建。Web 任务等待数据与 Go 任务成功；浏览器任务再对该构建制品做 Playwright 验收。`main` 的交付上传需要浏览器任务成功，因此语言保持或抽屉焦点回归会阻止交付制品。非法发布夹具仍由 Python／Node 发布门禁在构建前拒绝。YAML 不能单独证明分支保护或托管 CD 已经开启。

只有 `main` 的 push 在数据、Go、Web 与浏览器检查全部通过后上传 `apps/web/dist`，制品名绑定提交 SHA，保留 14 天；它是可部署的静态站点包。当前未配置远端仓库、托管平台、域名或生产环境，所以该流程不声称已部署公网。报告口径固定为 `CI configured; local checks passed; hosted CI/CD not verified`。干净检出清单见 [CHECKOUT.md](CHECKOUT.md)。配置远端后还须把 Data and ingestion、Go services、Web checks and static build、Browser acceptance、Delivery artifact 设为 `main` 的 required checks。Delivery artifact 只在 `main` 的 push 上运行；前四个应作为 PR 与 main 的必过检查。YAML 本身不是分支保护证据。

CI 不访问高校实时来源，也不运行高波动采集。实时性由部署后的 1／2／4／120 小时调度与发布事务提供；CI 只验证已提交候选、不可变活动快照和代码，从而避免外网失败随机阻塞合并。GitHub 官方 actions 固定到完整提交 SHA，依赖更新由 `.github/dependabot.yml` 每周提出，锁文件仍是可复现安装依据。

## 后台调度与下架

生产目标是 Go 调度器持久化 UTC 锚点，每 120 小时派发一次全覆盖 CrawlRun，Python worker 分来源执行，PostgreSQL 保存游标、任务锁、重试和运行结果。不要用每月日号 `*/5` 的 cron 表达“每隔五天”。Go 只调度现有 Python 命令，不重写解析器。当前仓库中的 `schedule.py` 是可测试的本地参考实现，自动任务尚未部署。计划表与锁顺序见 [SCHEDULER.md](SCHEDULER.md)。关闭状态另走版本化安全覆盖，见 [SAFETY_STATUS.md](SAFETY_STATUS.md)。
本地队列写入和 worker 运行共用跨平台操作系统文件互斥锁。租约保存拥有者和 token，支持续期、到期回收和按拥有者释放；状态文件以唯一临时文件原子替换。逐来源记录 attempt、抓取／解析结果、`lastSuccessAt`、`retryAt` 和 SLA，失败不推进成功时间，所有排队入口尊重退避时间。岗位采集的幂等 HTML／PDF 读取仅对传输失败与 408／425／429／500／502／503／504 作 3 秒、12 秒两次有限请求重试；最终失败再进入来源级退避，且不触发基于目录缺席的归档。
岗位已知截止本地计时检查；已知岗位状态与申请链接按 1 小时、全部登记岗位目录按 4 小时、DZS 项目候选目录按 2 小时、CZU 英语目录、CZU 捷克入口本科／硕士目录与 CZU 博士学院证据各按独立 2 小时分别调度，不替代稳定资料五天全覆盖。
关闭事务写入数据库并生成公共状态覆盖，主动失效列表、搜索、三语静态页与缓存。公开接口过滤 closed/expired，静态快照应用同一覆盖；缓存失效目标不超过 5 分钟。
需要外部证据才发现的提前关闭，最多存在一个状态核查周期加重试延迟；不得对外宣称实时同步雇主。无数据库连接时仍按已有截止保守过滤，并显示数据更新时间。
