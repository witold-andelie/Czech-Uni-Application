// Pages-subpath smoke: serve dist under /Czech-Uni-Application/ and verify.
import { chromium } from "@playwright/test";
import http from "node:http";
import { createReadStream, existsSync as _es, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const DIST = path.join(ROOT, "apps/web/dist");
const REPO = "Czech-Uni-Application";
const target = DIST;

const server = http.createServer((req, res) => {
  const urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (urlPath !== `/${REPO}` && !urlPath.startsWith(`/${REPO}/`)) {
    res.writeHead(404); res.end("outside the deployed prefix"); return;
  }
  let rel = urlPath.slice(REPO.length + 1) || "/";
  let file = path.join(target, rel);
  if (!file.startsWith(target + path.sep) && file !== target) {
    res.writeHead(404); res.end("not found"); return;
  }
  let status = 200;
  const stat0 = _es(file) ? statSync(file) : null;
  if (!stat0 || stat0.isDirectory()) file = path.join(file, "index.html");
  if (!_es(file)) {
    // GH-style 404 document
    file = path.join(target, "404.html");
    status = 404;
  }
  if (!_es(file)) {
    res.writeHead(404); res.end("not found"); return;
  }
  const ext = path.extname(file);
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml" };
  res.writeHead(status, { "content-type": types[ext] || "application/octet-stream" });
  createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(4199, "127.0.0.1", r));

const base = `http://127.0.0.1:4199/${REPO}`;
const failures = [];
const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("requestfailed", (r) => failures.push(r.url()));
page.on("pageerror", (error) => errors.push(error.message));
page.on("response", (r) => {
  if (r.status() >= 400 && ["script", "stylesheet", "fetch", "xhr"].includes(r.request().resourceType())) failures.push(r.url());
});
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
out.notFoundStatus = (await page.goto(`${base}/no-such-page`, { waitUntil: "load" })).status();
out.notFoundHeading = await page.locator("h1").count();
out.requestFailures = failures.slice(0, 5);
out.consoleErrors = errors.slice(0, 5);
console.log(JSON.stringify(out, null, 1));
await browser.close();
server.close();
const problems = [];
if (out["zh-CN"] !== 200 || out.en !== 200 || out.cs !== 200) problems.push("locale status");
if (!(out.czuCards >= 4)) problems.push("CZU cards");
if (!(out.fundedCards >= 3)) problems.push("funded cards");
if (!String(out.savedRedirect || "").endsWith("/zh-CN/programmes")) problems.push("legacy redirect");
if (!(out.notFoundHeading >= 1) || out.notFoundStatus !== 404) problems.push("404 recovery");
if (out.requestFailures.length) problems.push("request failures");
if (out.consoleErrors.length) problems.push("console errors");
if (problems.length) {
  console.error("PAGES SMOKE FAILED:", problems.join("; "));
  process.exit(1);
}
console.log("PAGES SMOKE PASSED");
