import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST = path.join(WEB_ROOT, "dist");
const distIndex = path.join(DIST, "index.html");
if (!existsSync(distIndex)) {
  console.error("FATAL: missing apps/web/dist. Browser tests run against the built artifact; run npm run build first.");
  process.exit(1);
}

const HOST = "127.0.0.1";
const PORT = Number(process.env.E2E_PORT || 4173);
const MIME = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
};

function insideDist(filePath) {
  const relative = path.relative(DIST, filePath);
  return relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function resolveFile(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const raw = path.normalize(decoded).replace(/^([/\\])+/, "");
  const candidates = [];
  const direct = path.join(DIST, raw);
  candidates.push(direct);
  if (!path.extname(raw)) {
    candidates.push(path.join(direct, "index.html"));
    candidates.push(`${direct}.html`);
  }
  for (const candidate of candidates) {
    if (!insideDist(candidate) || !existsSync(candidate)) continue;
    const stat = statSync(candidate);
    if (stat.isFile()) return { status: 200, file: candidate };
    if (stat.isDirectory()) {
      const nested = path.join(candidate, "index.html");
      if (insideDist(nested) && existsSync(nested) && statSync(nested).isFile()) {
        return { status: 200, file: nested };
      }
    }
  }
  const notFound = path.join(DIST, "404.html");
  return { status: 404, file: existsSync(notFound) ? notFound : distIndex };
}

const server = http.createServer((req, res) => {
  const urlPath = req.url || "/";
  const resolved = resolveFile(urlPath);
  res.writeHead(resolved.status, {
    "Content-Type": MIME[path.extname(resolved.file)] || "application/octet-stream",
    "Cache-Control": "no-store",
  });
  createReadStream(resolved.file).pipe(res);
});

server.listen(PORT, HOST, () => {
  console.log(`e2e preview http://${HOST}:${PORT} (apps/web/dist)`);
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
process.on("SIGHUP", shutdown);
server.on("error", (error) => {
  console.error(`FATAL: ${error.message}`);
  process.exit(1);
});
