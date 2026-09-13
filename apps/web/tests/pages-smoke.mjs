// Pages-subpath smoke: serve dist under /Czech-Uni-Application/ and verify.
import { chromium } from "@playwright/test";
import http from "node:http";
import { createReadStream, existsSync as _es, statSync } from "node:fs";
import { cpSync, existsSync, rmSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1")), "../../..");
const DIST = path.join(ROOT, "apps/web/dist");
const REPO = "Czech-Uni-Application";
const SERVE_ROOT = path.join(ROOT, "apps/web/.generated/pages-root");
const target = path.join(SERVE_ROOT, REPO);
if (existsSync(SERVE_ROOT)) rmSync(SERVE_ROOT, { recursive: true, force: true });
cpSync(DIST, target, { recursive: true });

const server = http.createServer((req, res) => {
  const urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let rel = urlPath.replace(new RegExp("^/" + REPO), "") || "/";
  let file = path.join(target, rel);
  const stat0 = _es(file) ? statSync(file) : null;
  if (!stat0 || stat0.isDirectory()) file = path.join(file, "index.html");
  if (!_es(file)) {
    // GH-style 404 document
    file = path.join(target, "404.html");
  }
  if (!_es(file)) {
    res.writeHead(404); res.end("not found"); return;
  }
  const ext = path.extname(file);
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml" };
  res.writeHead(200, { "content-type": types[ext] || "application/octet-stream" });
  createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(4199, "127.0.0.1", r));

const base = `http://127.0.0.1:4199/${REPO}`;
const failures = [];
const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("requestfailed", (r) => failures.push(r.url()));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 120)); });
const out = {};
for (const loc of ["zh-CN", "en", "cs"]) {
  const resp = await page.goto(`${base}/${loc}/`, { waitUntil: "load" });
  out[loc] = resp.status();
}
await page.goto(`${base}/zh-CN/research-jobs?applied=1&q=CZU`, { waitUntil: "load" });
await page.waitForTimeout(2500);
out.czuCards = await page.locator("article.result-card").count();
await page.goto(`${base}/zh-CN/research-jobs?applied=1&funded=1`, { waitUntil: "load" });
await page.waitForTimeout(1500);
out.fundedCards = await page.locator("article.result-card").count();
await page.goto(`${base}/zh-CN/saved`, { waitUntil: "load" });
await page.waitForTimeout(900);
out.savedRedirect = page.url();
await page.goto(`${base}/zh-CN/research-jobs/job-18000-0b0de28455a7`, { waitUntil: "load" });
await page.waitForTimeout(500);
out.detailH1 = (await page.locator("h1").innerText()).slice(0, 70);
await page.goto(`${base}/no-such-page`, { waitUntil: "load" });
out.notFoundHeading = await page.locator("h1").count();
out.requestFailures = failures.slice(0, 5);
out.consoleErrors = errors.slice(0, 5);
console.log(JSON.stringify(out, null, 1));
await browser.close();
server.close();
