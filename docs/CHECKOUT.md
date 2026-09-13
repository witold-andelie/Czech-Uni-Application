# 干净检出与 CI 制品

状态：**CI configured; local checks passed; hosted CI/CD not verified.**

本仓库尚未配置已授权的 Git remote、托管运行或公网部署。`.github/workflows/ci.yml` 是可在本机等价执行的确定性检查与制品配方，不能写成 GitHub 已经跑过或已经上线。

## 干净检出需要的文件

`config/checkout-manifest.json` 列出测试与构建的最低文件。检查：

```powershell
py -3 scripts/checkout_inventory.py --check
```

必须存在：

- 活动指针 `data/published/current.json` 及其不可变快照目录中的全部发布必需文件
- 安全状态指针与空覆盖 `data/published/safety/`
- 锁文件 `apps/web/package-lock.json`、`apps/api/go.sum`、`services/catalog/go.sum`、`services/ingestion/requirements-ci.txt`
- 三语 `locales/`、`opm/model.json`、发布政策

不要把 `data/sources/` 的可变候选直接 import 进浏览器。构建只读活动快照。

## 不要提交

- 运行时锁：`data/published/.publish.lock*`、`data/published/safety/.safety.lock*`
- 暂存与废弃镜像：`data/published/staging/`、`data/published/current/`
- 采集原文与审计草稿：`work/`
- 编译产物：`apps/api/server.exe`、`apps/web/dist/`、`apps/web/.generated/`

禁止对当前工作区执行 `git add --all`。

## 本机等价检查

```powershell
py -3 scripts/checkout_inventory.py --check
py -3 -m pytest services/ingestion/tests -q
py -3 scripts/sync_locales.py
py -3 services/ingestion/src/publish.py --check
py -3 services/ingestion/src/publish.py --check-sources
py -3 scripts/check_framework.py
cd services/catalog; go test ./...
cd ..\..\apps\api; go test ./...
cd ..\..\apps\web; npm ci; npm test; npm run check; npm run verify:published; npm run build
npx playwright install chromium
npm run test:e2e
py -3 scripts/checkout_inventory.py --write-provenance apps/web/dist/publication-provenance.json
```

浏览器验收针对已构建的 `apps/web/dist`：`scripts/preview-e2e.mjs` 在固定 `127.0.0.1:4173` 提供静态文件，并返回站点 `404.html`。它不使用开发服务器。缺少 `dist` 时该脚本直接失败。Playwright 失败轨迹在 `apps/web/test-results/`，不提交。

制品必须带上活动快照版本，并与 `current.json` 和 `manifest.json` 对照，而不是只看“构建成功”。

## 托管 CI/CD

尚未授权远端仓库或部署目标。配置远端之后仍须：

1. 对指定 revision 跑托管 CI，保存 run URL 与制品摘要
2. 把 Data and ingestion、Go services、Web checks and static build、Browser acceptance 设为 required checks（平台能力允许时）。YAML 本身不是分支保护证据。
3. 部署已测制品，不要在另一环境重编不同字节
4. 采集调度单独部署；静态托管不能因为能提供网页就运行 Python worker 或 Go 调度器

在此之前继续报告：`CI configured; local checks passed; hosted CI/CD not verified`。购买域名不是准备这些文件的前提。
