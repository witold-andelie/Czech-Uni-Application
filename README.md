# 捷克留学与带薪科研平台

状态：第一版三语浏览流程、本地发布链路和仓库 CI/CD 已落地。当前原子指针选择本地快照 `v2026-09-12.6`：54 所登记高校、54 条招生／申请入口、5,019 条登记项目库存、54 条坐标、10 条已审核科研岗位（CZU 4、MUNI 4、CUNI 2），以及 4 条已审核 CZU 招生摘录（英语本科／硕士信息学、捷克语 GIS 本科、捷克语应用与景观生态学博士）。5,019 不是已翻译或正在招生的项目数。中留服公开状态在取得官方查询证据前为待核验。更新时间：2026-09-13。

当前可运行的是静态公网站、发布门禁、离线采集 worker 和目录规则测试。查理大学与马萨里克大学的录取页示踪仍按其数据状态标注，不能当成完整招生覆盖。中留服标签来自运营方名单核对，不是中留服网站现场抓取，因此不能显示为官方可查或官方未收录。采集调度、审核后台和线上服务均未部署；本地快照通过门禁不等于网站已经上线。

地图由用户决定提前合并，用于观察主站集成效果。正式组件当前使用 OpenStreetMap 在线栅格瓦片，同时提供项目内置的捷克概览图；外部瓦片失败或超时会自动回退。聚合、键盘操作和离线回退已在本机浏览器验证，大陆运营商线路与真实移动设备仍未验证。当前实现不是自托管 PMTiles。

```powershell
cd apps/web
npm ci
npm test
npm run dev
```

浏览器打开 http://127.0.0.1:4321/zh-CN/ 。界面语言走 `/{locale}`，授课语言走 `teachingLanguage` 查询参数，两者互不推断。

仓库 CI 在 pull request、`main` 提交和手动触发时验证 Python、Go、Web、三语、发布快照与 OPM。只有 `main` 全部通过后才上传绑定提交 SHA 的静态站点制品；当前没有配置公网部署目标。口径：`CI configured; local checks passed; hosted CI/CD not verified`。详见 [实施架构](docs/ARCHITECTURE.md#cicd) 与 [干净检出](docs/CHECKOUT.md)。

Go 在线 API（需本机安装 Go）。生产默认读取 `data/published` 的已校验快照，拒绝 `data/fixtures/catalog.json`，除非显式 `CATALOG_ALLOW_FIXTURE=1`：

```powershell
cd services/catalog
go test
cd ..\..\apps\api
go test ./...
go run ./cmd/server
```

只查看当天任务而不发起网络采集：

```powershell
py -3 services/ingestion/src/worker.py --dry-run
```

`--once` 会执行已登记来源的本地采集并只写 `data/sources/` 与 `work/`；它不会自动发布。候选数据必须另行通过 `publish.py` 的业务契约和人工审核门禁，才能切换 `data/published/current.json`。

规则来源包括 `docs/`、`opm/index.html`、`docs/RECOGNITION_AND_WINDOWS.md`，以及 `D:\chatgpt\2026-09-06` 中的框架生成脚本与 guanfu.online 公开页核查记录。参考站用无年份的月日判断申请窗、且在缺少开始日期时直接视为开放；本站不复制该判断。

目标：面向中文、英文、捷克文用户，帮助用户按授课语言查找捷克学位项目，并查找硕士可申请的带薪科研岗位。

## 不可妥协的产品要求

1. 网站内置简体中文、English、Čeština 三语，独立于 Google Translate 和浏览器翻译运行。
2. 留学入口的第一分类必须是“英语授课 / 捷克语授课”。界面语言与授课语言分别存储，互不推断。
3. 用户未选择授课语言时，先展示并列且同等醒目的两个选择，不擅自替用户选择。不强制登录；可主动选择“查看全部”。
4. 界面直观、美观、可访问，移动端与桌面端均须逐语言验收。
5. 申请要求、学费、截止日期、岗位资格必须来自可追溯的官方证据。缺失不是零、不要求或免费。
6. 难以提取或依赖 JavaScript 的公开网页必须尝试本机 Scrapling，记录结果和失败原因。

## 文件入口

| 文件 | 用途 |
|---|---|
| [AGENTS.md](AGENTS.md) | 后续 Grok Build / 编码代理的工作规则 |
| [docs/PRODUCT.md](docs/PRODUCT.md) | 产品范围、语言优先流程及页面要求 |
| [docs/UI_RULES.md](docs/UI_RULES.md) | 视觉、交互、可访问性与响应式硬约束 |
| [docs/I18N_RULES.md](docs/I18N_RULES.md) | 三语翻译、路由、格式和发布规则 |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | 数据实体、分类标准和证据模型 |
| [docs/CRAWLING_RULES.md](docs/CRAWLING_RULES.md) | 官方源采集、Scrapling 升级流程 |
| [docs/REFRESH_POLICY.md](docs/REFRESH_POLICY.md) | 每五天采集、广覆盖、岗位关闭下架与申请直达 |
| [docs/SAFETY_STATUS.md](docs/SAFETY_STATUS.md) | 已核验关闭的版本化安全覆盖 |
| [docs/SCHEDULER.md](docs/SCHEDULER.md) | 锁顺序、候选世代与 Go 调度 Python 的计划 |
| [docs/CHECKOUT.md](docs/CHECKOUT.md) | 干净检出与 CI 制品边界 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 应用、采集、审核、发布边界 |
| [docs/LANGUAGE_STACK.md](docs/LANGUAGE_STACK.md) | Go、TypeScript、Python 和 SQL 的性能与启动选型 |
| [docs/DATABASE.md](docs/DATABASE.md) | Supabase 省钱方案、额度与备份 |
| [docs/REFERENCE_AND_DOMAIN.md](docs/REFERENCE_AND_DOMAIN.md) | 参考站公开实现核查及域名费用比较 |
| [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) | 可执行的验收清单 |
| [docs/SOURCES.md](docs/SOURCES.md) | 前期核验过的官方资料与线索 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 已确定事项与未决事项 |
| [opm/README.md](opm/README.md) | ISO 19450:2024 的 OPM 语义与 DOT 映射说明 |
| [opm/index.html](opm/index.html) | 可直接浏览的模型图集 |
| [opm/backlog.json](opm/backlog.json) | 与模型及验收项关联的实施任务 |
| [handoff/GROK_BUILD.md](handoff/GROK_BUILD.md) | 可直接交接的实施说明 |
| [design/tokens.json](design/tokens.json) | 初始视觉变量 |
| [locales/](locales/) | 三语初始界面词条 |
| [schemas/](schemas/) | 语言与项目展示变体基础数据契约 |

## 开始顺序

先读 AGENTS.md、PRODUCT、UI_RULES、I18N_RULES、DATA_MODEL 与 ACCEPTANCE。
OPM 已由用户确认为 ISO 19450。本框架采用对象、状态、过程和类型化关系，用 DOT 表达，并附对应英文 OPL 描述。DOT 是交付编码，不是 ISO 原生交换格式；图形映射差异在 opm/README.md 中列明。
先实现一个具备三语和真实筛选的完整项目浏览流程，再扩展数据采集与科研岗位。

公网站、采集脚本和本地发布目录已可运行；持久调度、审核后台和线上部署仍未完成。当前数据量只能按快照清单及其口径报告，示踪、待审核候选和测试夹具不能计入正式开放项目或岗位覆盖。 产品边界为纯浏览：短清单与比较已于 2026-09-12（A80）按所有者决定整体移除，无公共用户账户。

最新实现边界、审计项状态和验证命令见 [PROGRESS.md](PROGRESS.md)。

新增规则入口：[中留服参考、学校性质与申请轮次](docs/RECOGNITION_AND_WINDOWS.md)。对应基础契约：[申请窗口 schema](schemas/application-window.schema.json)。
