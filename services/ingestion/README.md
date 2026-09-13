# services/ingestion

Python + Scrapling 离线采集。公网站请求路径不会启动抓取。本地调度参考实现按 UTC 固定分片：稳定高校资料每天处理 **五分之一**，五天覆盖全集；高波动任务独立按 1 小时岗位状态、4 小时岗位目录、2 小时 DZS 项目目录、2 小时 CZU 英语目录、2 小时 CZU 捷克入口本科／硕士目录和 2 小时 CZU 博士学院证据运行。常驻调度尚未部署。

```powershell
py -3 services/ingestion/src/worker.py --dry-run
py -3 services/ingestion/src/worker.py --once
py -3 services/ingestion/src/worker.py --loop
```

已实现：从教育部官方登记册收获 54 所高校基线（名单 + CSV 官网／IČO／学院），生成 53 所学校的 5,019 条登记项目库存、54 条招生入口与坐标，以及查理大学、马萨里克大学录取页示踪。登记库存不是招生窗口；没有官方开放证据时保持未知。

CZU 英语适配器核对官方 WordPress REST 的总数和页数，再按 post ID 读取全部本科／硕士详情、开放项目页及通用招生页。2026-09-11 真实运行取得 36/36 详情：10 个本科、26 个硕士、36 条完整窗口，当前 0 条开放、35 条即将开放、1 条旧轮次关闭。CZU 捷克入口的 REST 受限，因此另一适配器核对首页总数、公开 programme sitemap 与唯一 post ID 后读取全部详情；同日取得 129/129，含本科 55、硕士 74、捷克语 94、英语 35，128 条完整窗口、34 条即将开放、94 条关闭、1 条未公布窗口。它与英语入口的英语记录不完全一致：两个标题变体，英语入口另有一条双学位记录。数字只对各自官网暴露的本科／硕士范围成立；这两条来源本身不含博士，输出仍是候选层。

CZU 博士适配器以 MŠMT 紧凑库存中的 60 个博士 offering 为固定分母，逐项匹配六个学院的官方 2026/27 招生证据。2026-09-11 真实运行取得 9/9 个官方资产、60/60 项匹配，捷克语与英语各 30 项，六学院均有项目和窗口证据；截至抓取时 60 项均已截止并等待下一学年窗口。缺少开始日、附带“视名额而定”的轮次及尚未公告的新轮次都不会推断为开放；技术学院图像 PDF 的人工转录绑定精确 SHA-256，源文件改变即失败。该完整性只覆盖上述基线与已配置的 2026/27 学院证据，候选仍须逐语种审核后才能发布。

研究与技术岗位入口由 `data/sources/registry.json` 驱动已登记官方列表、分页与详情发现。Charles 读取 AJAX 真分页；VUT 读取公开 GraphQL 列表和详情；CTU 对公告 PDF 使用有上限的本地 OCR；CZU 将 WP Job Manager 公共分页与 REST 全文按岗位 ID 交叉核对。新候选先做正文定界、法定雇主归属、研究／技术职责、学历、博士注册与薪酬提取；教学、行政和研究支持岗位不能只因背景文字提到研究而进入候选，AVCR 雇主不明候选隔离，分页或附件不完整不触发消失下架。动态发现不会自动发布。幂等官方 HTML／PDF 读取遇传输失败或 408／425／429／500／502／503／504 时，在 3 秒、12 秒后有限重试两次；若响应带有效 Retry-After 则以其为最早重试，过长延迟写入主机冷却并交给调度，不得把限流写成关闭。

来源成功与高校覆盖是两个指标。2026-09-11 的一次实跑当时 10 个已登记来源全部成功、映射 8/54 所，那是该日运行证据，不是当前注册表。当前覆盖报告绑定 `v2026-09-12.4`：24 个官方岗位源、22/54 所高校有登记源、0 个完整声明；candidate 层 current 90 与 supported 77 使用不同谓词。固定分母审计由 `build_source_coverage.py` 生成，不能把来源运行成功写成岗位齐全。

```powershell
py -3 services/ingestion/src/harvest_baseline.py
py -3 services/ingestion/src/worker.py --harvest-baseline
py -3 services/ingestion/src/harvest_register_exports.py
py -3 services/ingestion/src/harvest_programme_csv.py
py -3 services/ingestion/src/harvest_cscse24_programmes.py
py -3 services/ingestion/src/parse_msmt_programmes.py
py -3 services/ingestion/src/harvest_cuni_admissions.py
py -3 services/ingestion/src/parse_cuni_sis.py
py -3 services/ingestion/src/harvest_muni_admissions.py
py -3 services/ingestion/src/parse_muni_fi.py
py -3 services/ingestion/src/harvest_apply_portals.py
py -3 services/ingestion/src/clean_apply_portals.py
py -3 services/ingestion/src/apply_cscse_list.py
py -3 services/ingestion/src/worker.py --discover-jobs
py -3 services/ingestion/src/worker.py --recheck-jobs
py -3 services/ingestion/src/worker.py --refresh-programme-availability
py -3 services/ingestion/src/worker.py --refresh-czu-programmes
py -3 services/ingestion/src/worker.py --refresh-czu-czech-programmes
py -3 services/ingestion/src/worker.py --refresh-czu-doctoral-programmes
py -3 services/ingestion/src/build_source_coverage.py
py -3 services/ingestion/tests/test_apply_cscse_list.py
py -3 services/ingestion/tests/test_parse_msmt_register.py
py -3 services/ingestion/tests/test_parse_msmt_csv.py
py -3 services/ingestion/tests/test_parse_msmt_detail.py
py -3 services/ingestion/tests/test_parse_msmt_programmes.py
py -3 services/ingestion/tests/test_parse_cuni_sis.py
py -3 services/ingestion/tests/test_parse_muni_fi.py
py -3 services/ingestion/tests/test_apply_portals.py
```

输出：

- 原始 HTML／CSV：`work/raw/2026-09-06/`
- 结构化基线：`data/sources/msmt-hei-baseline.json`
- 学院：`data/sources/msmt-faculties.json`
- 候选数据：`data/sources/`
- 固定分母覆盖审计：`data/sources/coverage/source-coverage.json`
- 运行、原文和失败日志：`work/`
- 不可变发布版本：`data/published/snapshots/<version>/`
- 唯一活动版本指针：`data/published/current.json`

录取页示踪写入 `data/sources/admissions/`，其中 `catalogKind: tracer_not_published` 表示“不是完整正式招生目录”，不表示文件不能进入版本化发布包。公网站会把四条有限范围示踪覆盖到匹配的登记库存记录，并明确标注其范围；不会把缺开始日期当成开放，也不会把冲突的申请费压成一个数字。

发布必须先把候选复制到唯一 staging，再通过 `publication_contract.py` 的固定文件、关系、证据、URL、资格及逐语种源哈希审核门禁。门禁通过后写入不可变快照并原子切换 `current.json`；worker 不能直接改变活动版本。

```powershell
py -3 -m pytest services/ingestion/tests -q
py -3 services/ingestion/src/publish.py --check
```

当前活动快照及未完成边界见仓库根目录 `PROGRESS.md`。
