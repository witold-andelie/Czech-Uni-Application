# 关闭状态的公共传递契约

已核验的岗位关闭必须能在完整快照重发之前到达公开列表、详情、收藏和申请按钮。网络失败不是关闭。快照回滚不能重新打开之后核验的关闭。

## 选择的机制

使用独立于 `data/published/snapshots/` 的**版本化安全状态覆盖**：

- 指针：`data/published/safety/current.json`
- 不可变世代：`data/published/safety/generations/sYYYY-MM-DD.N.json`
- 浏览器与 API 读取副本：`data/published/safety-status.json` 和 `/data/safety-status.json`

覆盖只携带状态（整岗关闭、单轮关闭、不可用），不改写岗位正文、薪资或审核。普通内容审核门禁不因此放宽。

本地文件替换后，JS 客户端最多 60 秒轮询一次；API 每次请求重新读取覆盖。五分钟目标按 `propagationTargetSeconds=300` 计算。托管 CDN 缓存失效仍标“未验证”。

无脚本的静态 HTML 使用构建时写入的覆盖；构建之后的新关闭要等 JS 轮询或下一次静态重建。详情页保留墓碑，不从路由中消失。

## 允许的状态转移

| 现态 | 新态 | 条件 |
|---|---|---|
| open / unknown | closed / expired / unavailable | 实体级官方证据 |
| unavailable | closed / expired | 官方关闭或全部轮次结束 |
| closed | closed | 更高或相同世代 |
| closed / expired | open | 必须有 `reopenEvidenceId` |
| 任意 | closed from HTTP 503/429/timeout | **禁止** |

整岗关闭优先于仍写在快照里的未来轮次。一轮关闭而另一轮仍开放时，只覆盖该 `windowId`。

每条覆盖记录绑定：实体 ID、观察到的来源哈希、关闭时间与精度、原因／证据 URL、世代号。`sourceCheckedAt` 与 `statusPublishedAt` 分开保存。

## 缓存与失败

- `/api/safety-status`：`Cache-Control: max-age=60, must-revalidate`
- 状态接口失败时保留上次成功覆盖（last-known-safe），不把失败写成全部开放，也不编造关闭
- 监控应分别报告来源核查时间和状态发布时间

## 锁顺序

1. `work/runs/refresh.lock`：候选写入与世代钉扎
2. `data/published/.publish.lock`：快照版本分配与指针
3. `data/published/safety/.safety.lock`：覆盖激活

不得在持有 publish 锁时等待 refresh 锁。覆盖激活不持有 publish 锁，因此快照回滚不会改写覆盖。
