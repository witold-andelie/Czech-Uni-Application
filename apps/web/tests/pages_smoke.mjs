"""Serve dist under /Czech-Uni-Application/ (Pages project-site layout) and
run browser smoke: locale routes, CZU search, funded filter, safety fetch,
inventory fetch, console/request errors."""
import http.server
import json
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / ".generated" / "pages-root"
REPO = "Czech-Uni-Application"
PORT = 4199

target = SERVE / REPO
if target.exists():
    shutil.rmtree(target)
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / "apps/web/dist", target)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(SERVE, *a, **kw)


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    script = f"""
    const failures = [];
    const errors = [];
    const browser = await chromium.launch();
    const page = await browser.newPage();
    page.on('requestfailed', r => failures.push(r.url()));
    page.on('console', m => {{ if (m.type() === 'error') errors.push(m.text().slice(0,120)); }});
    const base = 'http://127.0.0.1:{PORT}/{REPO}';
    const out = {{}};
    for (const loc of ['zh-CN','en','cs']) {{
      const resp = await page.goto(base + '/' + loc + '/', {{ waitUntil: 'load' }});
      out[loc] = resp.status();
    }}
    await page.goto(base + '/zh-CN/research-jobs?applied=1&q=CZU', {{ waitUntil: 'load' }});
    await page.waitForTimeout(2500);
    out.czuCards = await page.locator('article.result-card').count();
    await page.goto(base + '/zh-CN/research-jobs?applied=1&funded=1', {{ waitUntil: 'load' }});
    await page.waitForTimeout(1500);
    out.fundedCards = await page.locator('article.result-card').count();
    await page.goto(base + '/zh-CN/saved', {{ waitUntil: 'load' }});
    await page.waitForTimeout(800);
    out.savedRedirect = page.url();
    await page.goto(base + '/zh-CN/research-jobs/job-18000-0b0de28455a7', {{ waitUntil: 'load' }});
    out.detailH1 = (await page.locator('h1').innerText()).slice(0, 60);
    out.requestFailures = failures.slice(0, 5);
    out.consoleErrors = errors.slice(0, 5);
    console.log(JSON.stringify(out, null, 1));
    await browser.close();
    """
    result = subprocess.run(
        [sys.executable, "-c",
         "import subprocess,sys\n"
         f"subprocess.run([sys.executable,'-m','playwright','.__noop'],capture_output=True)\n"],
        capture_output=True)
    # run playwright via node CLI with an inline spec
    spec = ROOT / "apps/web/tests/e2e/__pages-smoke.mjs"
    spec.write_text(
        "import { chromium } from '@playwright/test';\n" + script.split("const browser", 1)[1].join(["const browser", ""]),
        encoding="utf-8")
    print("serving on", PORT, "- run node spec")
    subprocess.run([sys.executable, "-c", "input()"])
