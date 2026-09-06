# 编程语言与运行性能约束

依据用户新增要求：各模块综合考虑性能和启动速度。选型必须评估用户首屏、服务启动、查询延迟、批处理吞吐和维护成本，不能只比较语言基准测试。

## 默认选型

| 模块 | 语言／工具 | 原因与边界 |
|---|---|---|
| 三语公网站 | TypeScript + Astro 静态生成；Svelte 局部交互；HTML/CSS | 首屏直接是已生成内容；只给筛选、比较等交互区域加载 JS |
| 审核后台界面 | TypeScript + Svelte，与公网站共享组件 | 不重复引入 React；后台作为同域受控 API 的客户端 |
| 在线 API 与发布控制 | Go，优先标准库 net/http 与小型依赖集合 | 编译部署、并发 I/O、部署简单；不依赖运行时解释器加载完整应用 |
| 目录规则与任务调度 | Go，同一代码库内部包／子命令 | 复用数据契约、连接池与错误处理；不拆无必要的微服务 |
| 网页采集与动态网页处理 | Python + 本机 Scrapling | 复用用户已安装工具；运行在独立离线 worker，浏览器和网络通常是主要耗时 |
| 数据存储与查询 | SQL / PostgreSQL，Supabase 托管可选 | 关系、外键、事务、索引、语言轨道与版本查询 |
| 图文模型与辅助验证 | DOT + Python | 开发期辅助，不位于用户访问路径 |

Go 是在线默认建议，不声称它在所有基准上快于 Rust/C++。Rust 可用于未来已测得的 CPU 热点，但初期额外跨语言边界、构建和维护成本不划算。Python 也不进入在线请求链路；这是对 Scrapling 生态与性能的综合权衡。

## 运行拓扑

浏览器 → 本域静态页面／缓存 → 同域 Go API → PostgreSQL 连接池。
Python 采集 worker → 官方网页 → 原始证据 → Go 入库／核验接口或受控导入 → PostgreSQL。
审核发布 → 三语快照与静态页面构建 → 原子部署版本。

Node.js 仅用于 Astro/Svelte 构建，不作为第一版线上 SSR 服务。长页面在构建时生成 HTML；语言切换用 locale 路由和已存上下文。
动态筛选由轻量 JS 调同域分页 API，不能把所有学校、项目、三语全文塞进首屏 HTML。
小数据试运行可由前端读取按语言分片的索引；超过预算后切服务器检索，不能无限扩大客户端载荷。
开发期可以用本机 PostgreSQL／Supabase；Supabase 暂停不是 Go 启动慢，两个问题分别监控。

## 具体性能预算（目标，尚未实测）

- Go 服务进程启动到本地 healthz：<= 500 ms，目标 1 vCPU / 512 MB 环境；独立记录 DNS、数据库握手和 readyz 时间。
- Go warm API p95：缓存命中 <= 100 ms，常见数据库筛选 <= 300 ms，以客户端位于同区域、20 并发、1 万 offering 和 5 千岗位的测试集为起点。记录设备、缓存、数据规模和网络条件，不能把目标当结果。
- 首屏压缩 JS <= 100 KB；列表交互首批压缩 JS <= 150 KB；按页面拆分，不加载地图和后台代码到所有页面。
- 首屏 HTML 不内嵌整个目录；列表每次默认 20 条，单次 API 页上限 100 条。
- 首批列表数据压缩 <= 100 KB，详情按需读取；图片延迟加载且指定宽高，核心文字不等待图片。
- UI 性能及真实大陆线路目标见 UI_RULES 与 ACCEPTANCE。
- 采集任务有独立并发和内存限额；浏览器实例按批复用，不为每个字段重启浏览器，不无限提高并发。

## 查询与启动约束

Go 发布使用预编译 release 二进制，不在线执行 go run；启动时不抓网页、不翻译、不扫描全部数据、不跑破坏性迁移。
迁移和静态构建独立执行。连接池有上限、超时和重试退避，查询参数化且有上下文取消。
PostgreSQL 为 language / degree / deadline 等常用组合设计索引，用真实查询计划核验；禁止请求内 N+1。
英文、捷克文和中文搜索需分别验证；不要认为默认 PostgreSQL 英文全文索引天然解决中文分词。初期用经审核别名、规范化搜索字段和限量匹配，按测量决定扩展。
Supabase 的持久 Go 服务优先匹配网络条件使用直接连接或 session pooler；IPv4-only 环境可用官方共享 session pooler，不因不支持 IPv6 立即购买附加项。

## 官方资料

- Astro 静态输出：https://docs.astro.build/en/guides/on-demand-rendering/
- Astro islands：https://docs.astro.build/en/concepts/islands/
- Go 编译与设计：https://go.dev/doc/faq
- Supabase PostgreSQL：https://supabase.com/docs/guides/database/overview
- 数据库连接：https://supabase.com/docs/guides/database/connecting-to-postgres

资料查阅日期 2026-09-06；具体框架版本在实施时锁定。
