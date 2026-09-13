# 来源与核验范围

基础资料首次查阅日期：2026-09-06；动态项目／岗位来源最近实跑日期：2026-09-11。以下为规划依据与采集起点，不代表已授权大规模复制或已导入全部数据。

| 来源 | 用途 |
|---|---|
| https://www.iso.org/standard/84612.html | 当前 ISO 19450:2024 标准身份与范围；取代 ISO/PAS 19450:2015 |
| https://dovdori.technion.ac.il/wp-content/uploads/2022/01/Casebolt-Dori-2016-CESUN2016-Business-Process-Improvement-Using-OPM-Rev-Final.pdf | OPM 创始人参与的论文，核查对象、状态、过程、结构和过程关系 |
| https://dovdori.technion.ac.il/wp-content/uploads/2021/09/OPM-as-Alternative-2nd-Rev-2021-07-29.pdf | OPM 的图文、细化及关系说明 |
| https://regvssp.msmt.cz/registrvssp/ | 教育部登记册首页；进入捷克高校或在捷外国高校两条 ASP.NET 入口 |
| https://regvssp.msmt.cz/registrvssp/cvslist.aspx | 《高校及实施中的学习项目登记册》名单；2026-09-06 Scrapling GET 得 54 所。同页 ASP.NET POST 可导出 CSV（VŠ）与 CSV（F） |
| https://regvssp.msmt.cz/registrvssp/cvsdet.aspx | 学校 Detail 回帖页；含官方英文名、IČO、官网、学院。专业在「CSV (SP/O)」或「Přehled studijních programů」 |
| https://regvssp.msmt.cz/registrvssp/inak.aspx | 机构认证（按教育领域）；387 条，不是招生专业目录，也没有申请窗口 |
| https://archiv.msmt.gov.cz/areas-of-work/tertiary-education/public-higher-education-institutions-websites | 归档的公立高校官网列表；仅当当日 CSV 无主机名时回退 |
| https://studyin.gov.cz/en/study-programmes/ | DZS 发现检索，AJAX `/ajax/programsearch/applyfilter`；不是法定名录，不能当学费／截止日期权威 |
| https://study.czu.cz/ | CZU 官方英语本科／硕士目录；REST 声明总数后逐项读取详情中的窗口、学费、学制和院系，只对该英语范围主张来源读取完整 |
| https://study.czu.cz/open-programmes/ | CZU 当前开放英语项目辅助信号；与逐项详情日期交叉核对，缺席本身不静默覆盖详情 |
| https://study.czu.cz/admission/ | CZU 官方通用招生说明、UIS 申请入口和申请费；通用入口不能冒充逐项目直达链接 |
| https://studuj.czu.cz/ | CZU 捷克入口本科／硕士目录；首页报告总数，详情分别标授课语言、窗口、学制、院系和申请目标 |
| https://studuj.czu.cz/programmes-sitemap.xml | CZU 捷克入口公开 programme sitemap；与首页总数和唯一详情 ID 独立核对目录边界 |
| https://studuj.czu.cz/prijimaci-rizeni/ | CZU 捷克文通用招生流程、UIS 入口和申请费；院系／项目详情仍是具体窗口来源 |
| https://www.af.czu.cz/dl/150405?lang=cs | CZU FAPPZ 2026/27 博士招生规则；项目、语言轨道和截止日证据 |
| https://www.pef.czu.cz/dl/113306?lang=en | CZU PEF 2026/27 博士招生规则；四个捷克语和四个英语轨道及窗口 |
| https://www.fzp.czu.cz/dl/151487?lang=cs | CZU FŽP 捷克语博士项目 2026/27 两阶段招生规则 |
| https://www.fzp.czu.cz/dl/151488?lang=en | CZU FŽP 英语博士项目 2026/27 两阶段招生规则 |
| https://www.fld.czu.cz/en/r-9414-study/r-10989-visual-study/admission-procedures-for-doctoral-study-for-the-2026-2027-ac.html | CZU FLD 2026/27 博士项目与捷克语／英语申请期限 |
| https://www.tf.czu.cz/cs/r-6970-veda-a-vyzkum/r-7923-aktuality-vav/prijimaci-rizeni-pro-doktorske-studium-v-akademickem-roce-20.html | CZU TF 2026/27 博士招生公告及官方扫描件入口 |
| https://www.tf.czu.cz/dl/152519?lang=cs | CZU TF 图像型 2026/27 博士规则；仅以精确哈希绑定的受审转录提取 |
| https://www.ftz.czu.cz/dl/147891?lang=en | CZU FTZ 2026/27 英语博士项目与三阶段规则；第三阶段是否启动取决于名额 |
| https://portal.studyin.cz/en/ | 旧门户；2026-09-06 HTTP 308 到 studyin.gov.cz |
| https://lkod.msmt.gov.cz/ | 教育部开放数据目录；A3791 是词汇表，不是可下载的专业清单 |
| https://www.studyin.cz/faq/ | 捷克高校类型与申请原则；2026-09-06 已重定向到 studyin.gov.cz，FAQ 路径 404 |
| https://www.vspj.cz/en/skola/obecne-informace | 应用／职业导向高校示例 |
| https://www.euraxess.cz/jobs/search | 招聘发现入口，必须依据实际工作国家筛选 |
| https://www.it.cas.cz/en/research-scientist-in-the-laboratory-of-rotational-laser-vibrometry/ | 硕士带薪科研历史样本，公告截止 2026-08-31 |
| https://www.eu.avcr.cz/en/news/Cosmological-Visionaries-Shamans-Scientists-and-Climate-Change-at-the-Ethnic-Borderlands-of-China-and-Russia/ | 硕士可申请的科研助理样本，公告截止 2026-09-15；不能永久视为开放 |
| https://www.guanfu.online/ | 信息检索参考，非本站数据权威来源 |

ISO 完整付费正文未取得；模型依据公开标准说明与作者资料构建，不能宣称已做逐条正式合规审计。
Scrapling 语法以本机 0.4.9 的 --help 为依据；Graphviz 本机版本 14.1.5。

## 动态岗位官方入口（2026-09-10 实跑）

| 范围 | 官方入口 | 提取边界 |
|---|---|---|
| Charles University | https://cuni.cz/UKEN-1573.html | 校级 AJAX 真分页与逐项详情；不声明校内完整 |
| Masaryk University | https://www.muni.cz/en/about-us/careers | 校级列表与逐项详情；不声明校内完整 |
| Palacký University | https://pracuj.upol.cz/ | 校级门户与逐项详情；不声明校内完整 |
| VŠB-TUO | https://www.vsb.cz/cs/univerzita/informacni-deska/pracovni-prilezitosti/ | 活动公告与已结束结果分离；不声明校内完整 |
| UCT Prague | https://www.vscht.cz/uredni-deska/vyberova-rizeni/akademicke-pozice | 同页岗位实体定界；不声明校内完整 |
| CTU Prague | https://eud.is.cvut.cz/pub/deska/36000002/ifis/?kategorie_id=66&pocet=100 | 校级人事公告精确总数、详情和 PDF/OCR；FEE 页面另作补充；不声明校内完整 |
| Brno University of Technology | https://vutbr.jobs.cz/ | 校级门户公开 GraphQL 全分页与逐项详情；不声明校内完整 |
| Czech University of Life Sciences Prague | https://jobs.czu.cz/ | 校级 WP Job Manager 公共页与同站 REST 全文按 ID 交叉核对；不声明校内完整 |
| Czech Academy of Sciences | https://www.avcr.cz/en/about-us/career/selection-procedures/ | 独立研究机构集合；法定雇主不明即隔离，不计入高校覆盖分母 |

以上对应注册表中的 10 个来源记录：CTU 有校级入口和 1 个 FEE 院系补充源。一次完整成功只证明这些已登记入口在该轮可完整读取，不能证明捷克 54 所高校及其全部院系岗位齐全。

## 真实高校怎么接（2026-09-06 已核验路径）

没有公开 REST「全部专业」API。接法按权威分层，不能把发现站写成招生目录。

1. **学校身份（已接）**

   `cvslist.aspx` HTML 表 → 54 所名称、公立／国立／私立、大学／非大学、州。
   同页 POST `CSV (VŠ)` → IČO、注册地址、官网主机名（当天 54/54 有 web）。编码 Windows-1250。
   POST `CSV (F)` → 学院（已去掉「celoškolské pracoviště」）。
   个别 Detail 回帖补充官方英文名。

2. **法定专业身份（登记册项目库存）**

   点学校 Detail → `cvsdet.aspx` → `csplist.aspx`「Přehled studijních programů」→ **Export CSV**。
   字段含名称、学位类型、学院、学习形式、ISCED、标准学制、**授课语言**、认证有效期。这是认证／实施清单，不是某一学年的招生窗口，也没有学费。
   当前本地发布快照 `v2026-09-09.1` 收录 53 所学校的 5,019 条库存 offering；没有官方招生窗口的记录保持未知，不冒充当前可申请项目，也不以库存数量宣称招生覆盖率。

3. **招生窗口、授课语言、学费、申请链接（两校示踪与 CZU 三条重点来源已接）**

   必须回到各校官方录取页。登记册和 Study in Czechia 都不能代替。缺开始日期不得自动视为开放；未公布学费不得写成 0。
   2026-09-06 已做查理大学与马萨里克大学共四条录取页示踪。示踪证据文件随当前不可变快照发布，浏览目录将其覆盖到匹配的登记库存记录；界面仍标“录取页示踪”，不是完整招生目录，也不能把能打开的申请系统当成当前开放。
   查理大学数物学院：英语 Computer Science 本科 SIS `id_obor=34738`（截止 2026-04-30，现不可申请，学费 7100 / 4200 EUR 分列）；捷克语 Informatika 本科 SIS `id_obor=34456`（截止 2026-03-31，现不可申请，无学费字段）。院系页 “Application server opens: December 2025” 只到月，不写入 `opensAt`。
   马萨里克大学信息学院：英语 Visual Informatics 硕士（9 月入学 2025-12-15–2026-04-15 已截止；2 月入学 2026-06-15–2026-10-15 仍开放；学费学院口径 4500 EUR／年）；捷克语 Informatika 本科（2025-11-01–2026-02-28 已截止；中央学费页写明捷克语授课免费，不是从高教法推断）。FI 本科只有捷克语。申请费院系页 800 与官方公告 900 未压成一个数。
   CZU 英语入口：2026-09-11 从官方 REST 核对 36 条本科／硕士记录并读取 36/36 详情，含 10 个本科、26 个硕士和 6 个院系；36 条都有完整申请起止。按抓取时点，35 条将在 2026-09-14 或 09-15 开放，1 条 Danube AgriFood Master 仍为 2026-01-15 至 02-28 的旧轮次；详情日期与开放项目页均报告当前 0 条开放。36 个页面的 “Apply now” 当时均无 `href`，因此只另存已验证的通用 UIS 入口，不生成虚假逐项目链接。
   CZU 捷克入口：公开 REST 受访问控制限制，改用首页总数、programme sitemap 和唯一详情 ID 三重核对。2026-09-11 三者均为 129，实际读取 129/129 详情：本科 55、硕士 74，捷克语授课 94、英语授课 35；128 条有完整窗口，34 条即将在 09-14 或 09-15 开放，94 条关闭，Danube AgriFood Master 未公布窗口。127 条有项目级 UIS 链接，另外 2 条只保留通用入口。与英语入口核对时出现两个轻微标题变体，英语入口还多一条双学位记录，故明确报告 `disagrees`，不强行对齐。两条本科／硕士来源本身不含博士，候选尚未进入三语正式快照。
   CZU 博士：以 MŠMT 紧凑库存的 60 个博士 offering 为固定分母，读取 FAPPZ、PEF、FŽP、FLD、TF 和 FTZ 的九个官方 2026/27 资产。2026-09-11 实跑为 9/9 HTTP 200、60/60 项匹配，捷克语与英语各 30 项；60 项均有学院窗口证据，34 项至少有一个起止完整窗口，抓取时 60 项全部关闭。只公布截止日的记录在截止前不标开放，FTZ 条件第三阶段不在未确认时标开放，TF 扫描件只由精确 SHA-256 绑定的受审转录读取。结果只完成候选采集，不能扩大为 2027/28 已全面检查或已完成三语正式发布。
   2026-09-06 已为登记册全部 54 所核验官方电子申请／招生页：只保存当天 HTTP 200 且无 not-found 文案的链接。警察学院当天网站不可达，不放置会 404 的申请按钮。能打开申请系统不等于窗口开放。

4. **发现层（仅线索）**

   `studyin.gov.cz/en/study-programmes/` 有 AJAX 过滤器。`portal.studyin.cz` 已 308。LKOD A3791 是词汇，不是专业 dump。SIMS 是学生矩阵，不是公共目录。

5. **中留服**

   2026-09-06 运营方提供 25 个可查校名，与登记册核对后 24 所 listed、30 所 not_found、1 个 unmatched（已停办、未建条目）。不是中留服网站现场抓取。公立身份不等于已列入。


## 中留服新增官方依据（2026-09-06 查阅）

- 认证院校查询说明：https://portal.cscse.edu.cn/lxfwzx/xlxwrz/rzyxcxmd/
- 如何判断国外院校是否可以通过认证：https://www.cscse.edu.cn/zwfw/lxfwzxwsfwdt2020/xlxwrz32/cjwt/2026042823384080651/index.html
- 查询数据更新说明：https://www.cscse.edu.cn/zwfw/lxfwzxwsfwdt2020/xlxwrz32/tzgg61/2026042823372796219/index.html
- 官方认证院校查询入口：http://yxcx.cscse.edu.cn/rzyxmd

2026-09-06 运营方另行提供 25 个“中留服认证高校”名称，由 `apply_cscse_list.py` 与教育部登记册核对。24 所匹配为 listed；登记册其余学校为 not_found（未出现在该名单）。政治与社会科学学院 / Academia Rerum Civilium 未出现在当天 54 所登记中，保持 unmatched，不编造现有高校。未打开中留服查询站逐校抓取。标签仍是查询参考，不是认证保证。
