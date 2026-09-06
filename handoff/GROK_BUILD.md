# Grok Build 实施交接

请在本项目中实施捷克留学与带薪科研平台。先读根 AGENTS.md，以及 docs/PRODUCT、UI_RULES、I18N_RULES、DATA_MODEL、CRAWLING_RULES、ACCEPTANCE。

使用 opm/index.html 查看模型，opm/*.dot 是可编辑的 DOT 交付，opm/OPL.md 是对应英文语义。opm/model.json 是同源模型登记，修改后运行 scripts/render_opm.py 重新生成图文，避免仅改单个 SVG。

实施语言按 docs/LANGUAGE_STACK.md：公网站 TypeScript/Astro 静态生成＋Svelte 局部交互；在线接口与目录逻辑 Go；采集 Python/Scrapling；数据库 SQL/PostgreSQL，初期建议 Supabase Free，具体费用、休眠和备份要求见 DATABASE.md。

不可改变：留学第一分类为英语授课／捷克语授课；界面内置简中、英语、捷克语；两套语言状态互不干扰；难页面使用本机 Scrapling；所有正式数据有来源与核验版本。

按 opm/backlog.json 的依赖顺序实施。先完成一个三语端到端浏览流程，再接官方数据核验、翻译发布和岗位库。使用共享 tokens 和三语词条，不把设计稿当作功能已实现。

上线前完成 docs/ACCEPTANCE.md，尤其是双语课程排除逻辑、英语项目附加捷克语要求、无 Google 服务、三语切换状态保留和大陆线路测试。

初始目录只定义模块职责，不包含可运行应用。创建实际应用前核验并固定依赖版本。缺失数据留空并标注，不使用未经标记的虚构项目撑页面。默认收藏可本地存储；外部申请跳转不得表现为本站已投递。

新增必须实施的策略：读 docs/REFRESH_POLICY.md 与 config/refresh-policy.json。每 120 小时轮询广覆盖来源，真实关闭／截止自动下架，标题和主要按钮直达官方申请页。原来只做“站内岗位详情后再点申请”的流程已不满足要求。当前配置是部署蓝图，没有实际开启采集。

新增要求：读 docs/RECOGNITION_AND_WINDOWS.md。学校性质和中留服官方参考状态必须显著显示；项目、岗位均记录申请起止及官方轮次。实现多轮开放汇总和正确申请链接，不因第一轮截止误下架仍在下一轮招生的机会。
