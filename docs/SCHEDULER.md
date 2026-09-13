# 调度与候选世代

当前可运行的是 Python 文件调度：`schedule.py`、`worker.py`、`file_lock.py`。这不是已部署的 Go/PostgreSQL 任务系统。自动采集尚未开启。

## 锁顺序

1. `work/runs/refresh.lock`：候选写入、岗位复核、候选世代钉扎
2. `data/published/.publish.lock`：不可变快照版本分配与 `current.json`
3. `data/published/safety/.safety.lock`：安全状态覆盖

发布时先在 refresh 锁内对 `requiredFiles` 计算校验和并复制，再释放 refresh 锁，然后才做昂贵校验与指针切换。复制后的字节必须与钉扎校验和一致，否则拒绝。清单写入 `candidateGeneration`。不要假设所有来源同时刷新；被选中的组合必须显式可审查。

Worker 不获取 publish 锁。回滚只切换快照指针，不持有 safety 锁，因此不能撤销之后的关闭覆盖。

## 漏跑与 120 小时目标

普通漏跑：当天 1/5 分片等到下一个同余日，不把五天工作叠进一天。

SLA 补跑：某分片距上次成功已超过 120 小时，才进入 `overdue_catchup`，每次唤醒优先最久未成功的一个分片。`--catch-up` 走这条路径。这是为了满足用户要求的 120 小时全覆盖，不是把历史批次一次性重放。

高波动任务（1/4/2 小时）独立到期，不等待学校分片。

## 分片分配

初始映射是官方 id 排序后按下标取模。学校集合变化时，排序取模会移动邻居。因此 `assign_shards_stable` 把已有 id 留在原分片，新 id 加入当前最小分片，并持久化到 `work/runs/shard-assignments.json`。没有这份映射时不能声称“同一学校永远同一分片”。

## 部署后的 Go 调度器

Go 只调度现有 Python 命令，不把解析器改写成 Go。计划表见 `apps/api/migrations/002_scheduler.sql`。

| 任务 | 命令 | 超时起点 |
|---|---|---|
| 稳定分片 | `py -3 services/ingestion/src/worker.py --once` | 数小时 |
| 岗位复核 | `--recheck-jobs` | 短；可随后激活 safety overlay |
| 岗位发现 | `--discover-jobs` | 数小时 |
| DZS / CZU 高波动 | `--refresh-programme-availability` 等 | 数小时 |

每条运行记录：lease owner/token、attempt、last success、retry deadline、expected source set、complete/partial、artifact digest、candidate generation id。失败不推进成功。过期租约可回收。两个 runner、进程死亡和租约过期必须在部署环境用数据库 fencing 测试；现有 OS 锁测试只证明本机互斥。

短周期调度与完整 120 小时观察是不同证据。在持久环境跑完之前不得声称持续覆盖已经完成。
