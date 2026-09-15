import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
await writeFile(path.join(dist, "_headers"), `/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
/data/safety-status.json
  Cache-Control: no-store
/publication-provenance.json
  Cache-Control: no-cache
/_astro/*
  Cache-Control: public, max-age=31536000, immutable
`);
const site = new URL(process.env.SITE_URL || "https://czech-uni-application.com");
if (!["https:", "http:"].includes(site.protocol)) throw new Error("SITE_URL must be HTTP(S)");
const base = (process.env.SITE_BASE || "/").replace(/\/$/, "");
const urls = [];
const escapeXml = (value) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
let count = 0;
async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) await inspect(file);
    else {
      if (!entry.isFile()) throw new Error(`Unsupported deployment entry: ${file}`);
      if ((await stat(file)).size > 25 * 1024 * 1024) throw new Error(`Cloudflare asset exceeds 25 MiB: ${file}`);
      if (entry.name.endsWith(".html")) {
        const relative = path.relative(dist, file).split(path.sep).join("/");
        if (/^(zh-CN|en|cs)\//.test(relative) && !/\/(saved|compare|404)(\/|\.)/.test(relative)) {
          const html = await readFile(file, "utf8");
          if (!/<meta[^>]+(?:noindex|http-equiv=["']refresh)/i.test(html)) {
            const route = relative.replace(/index\.html$/, "").replace(/\.html$/, "");
            const url = new URL(`${base}/${route}`, site).href;
            if (!html.includes(`rel="canonical" href="${url}"`)) throw new Error(`Missing or incorrect canonical: ${relative}`);
            for (const locale of ["zh-CN", "en", "cs"]) {
              const equivalent = new URL(`${base}/${route.replace(/^[^/]+/, locale)}`, site).href;
              if (!html.includes(`href="${equivalent}"`)) throw new Error(`Missing language equivalent: ${relative} (${locale})`);
            }
            const json = html.match(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/);
            if (!json || JSON.parse(json[1]).url !== url) throw new Error(`Invalid page metadata: ${relative}`);
            urls.push(url);
          }
        }
      }
      count++;
    }
  }
}
await inspect(dist);
await writeFile(path.join(dist, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.sort().map((url) => `<url><loc>${escapeXml(url)}</loc></url>`).join("\n")}</urlset>\n`);
await writeFile(path.join(dist, "robots.txt"), `User-agent: *\nAllow: /\nSitemap: ${new URL(`${base}/sitemap.xml`, site).href}\n`);
count += 2;
// Leave room for the provenance document added by CI after the build.
if (count >= 20000) throw new Error(`Cloudflare free file limit reached: ${count}`);
console.log(`Static host ready: ${count} files; closure status will not be cached.`);
