# ISO 19450 对象过程模型 · DOT 交付

用户已指定 ISO 19450；本模型采用当前 ISO 19450:2024 的对象、状态、过程、结构与变换语义。
ISO 官方介绍：https://www.iso.org/standard/84612.html 。模型参考依据见 ../docs/SOURCES.md。

## 文件

- index.html：本地可浏览图集，打开 SVG 可放大。
- SD.dot：最高层系统环境与受益对象。
- SD0.dot：Opportunity Finding 主过程展开。
- SD1.dot：Programme Discovering 展开，授课语言优先。
- SD2.dot：Interface Presenting 展开，三语界面独立切换。
- OPS.dot：目录维护的支撑环境。
- SD3.dot：Catalogue Maintaining 展开，核验、三语复核、版本发布与归档。
- SD4.dot：Evidence Acquiring 展开，Scrapling 与失败队列。
- SD5.dot：科研机会与资格核验细化视图。
- SD6.dot：平台及数据的对象结构视图。
- OPL.md：与图同源生成的英文关系描述。
- model.json：稳定对象／过程 ID、状态所属、图层级、边类型、规则追踪。
- backlog.json：实施工作项；它不是 OPM 对象模型的替代。

## DOT 映射约定

这是 OPM 语义到 Graphviz DOT 的显式映射，不是 ISO 原生文件格式，也不是普通流程图套上 OPM 名称。

| OPM 概念 | DOT 表达 |
|---|---|
| Object | 方框；opm_kind=object |
| Process | 椭圆；opm_kind=process；英文采用动作名词 |
| State | 所属对象边界内的圆角方框；opm_owner 指明对象 |
| Physical / environmental object | 物理对象粗线，环境对象虚线；此处是清楚标注的 DOT 近似 |
| agent | 人类对象 → 过程，实心圆端点 |
| instrument | 对象／特定状态 → 过程，空心圆端点；对象不被消耗 |
| consumption | 对象 → 过程，箭头；本模型主要保留证据，通常不用此关系 |
| result | 过程 → 对象／初始状态，表示创建 |
| input / output | 输入状态 → 过程 → 同一对象输出状态，表示状态改变而非对象销毁重建 |
| effect | 过程 ↔ 对象，未展开具体状态的改变 |
| aggregation | 整体 → 部件，实心三角端位于整体；OPL 明确 consists of |
| exhibition | 对象与属性之间的有标签虚线；这是 DOT 可读性映射，不冒充标准原生端点符号 |

状态属于对象，不给过程标“待执行／执行中／完成”状态。程序运行状态应另建 Job 等对象。
每个过程必须创建、消耗或改变至少一个对象。不能以 process → process 箭头代替对象变换。
所有边都有 opm_relation 属性和可见英文标签，不能只凭颜色理解关系。
用于布局的 cluster 是对象状态容器；图间的 in-zooming 由 parent 过程 ID 和 OPL 说明表达，未用嵌套巨大椭圆逼近所有原生绘图语法。
默认多个不同对象使能条件同时满足；可选成功／失败和授课语言分支互斥，详见图注。未编码完整 OPM 事件逻辑或可执行仿真。
SD5 是科研领域细化，包含后台资格核验与前台检索的不同职责，不能理解为用户每次搜索都等待审核。

## 与需求关联

- 语言优先：SD1 → A01 / A04 / A05。
- UI 与授课语言解耦：SD2 → A02 / A03。
- 三语一致发布：SD3 → A08。
- 难页面 Scrapling：SD4 → A09。
- 硕士带薪岗位：SD5 → A07 / A10 / A11。
- 独立学校和语言轨道：SD6 → A12。

## 重生成与检查

在项目根运行：

```powershell
py -3 scripts/render_opm.py
```

Python 3 与 Graphviz dot 即可，无需联网。编辑 model.json 后重新生成；若直接调整 DOT 视觉布局，应同步生成器，以免下次覆盖。
validation.json 记录本项目的对象／过程类型、状态配对、过程变换和 Graphviz 解析结果；不代表经过完整 ISO 合规审计。
当前未取得标准完整付费正文；采用公开标准介绍与作者资料，因此不作逐条合规认证声明。
