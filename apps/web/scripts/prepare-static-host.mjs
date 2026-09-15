import { readdir, stat, writeFile } from "node:fs/promises";
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
let count = 0;
async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) await inspect(file);
    else {
      if (!entry.isFile()) throw new Error(`Unsupported deployment entry: ${file}`);
      if ((await stat(file)).size > 25 * 1024 * 1024) throw new Error(`Cloudflare asset exceeds 25 MiB: ${file}`);
      count++;
    }
  }
}
await inspect(dist);
// Leave room for the provenance document added by CI after the build.
if (count >= 20000) throw new Error(`Cloudflare free file limit reached: ${count}`);
console.log(`Static host ready: ${count} files; closure status will not be cached.`);
