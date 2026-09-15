import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const publishedRoot = resolve(root, "data/published");

function selectedPublication(): { version: string; directory: string; publicDirectory: string } {
  let version = process.env.CZECH_UNI_PUBLISHED_VERSION;
  if (!version) {
    const pointer = JSON.parse(readFileSync(resolve(publishedRoot, "current.json"), "utf8")) as {
      activeVersion?: string;
      snapshotDir?: string;
    };
    version = pointer.activeVersion;
    if (!version || pointer.snapshotDir !== `snapshots/${version}`) {
      throw new Error("data/published/current.json does not select one immutable snapshot");
    }
  }
  if (!/^v\d{4}-\d{2}-\d{2}\.\d+$/.test(version)) throw new Error("Invalid publication version");
  const directory = resolve(publishedRoot, "snapshots", version);
  const publicDirectory = process.env.CZECH_UNI_PUBLIC_DIR || resolve(root, "apps/web/.generated/public", version);
  return { version, directory, publicDirectory };
}

const publication = selectedPublication();

const siteBase = process.env.SITE_BASE || "/";

export default defineConfig({
  site: process.env.SITE_URL || undefined,
  base: siteBase,
  output: "static",
  publicDir: publication.publicDirectory,
  integrations: [svelte()],
  // A80: legacy saved/compare routes are real base-aware redirect pages now
  // (src/pages/[locale]/saved|compare.astro) so the refresh target carries
  // the configured base path on any static host.
  vite: {
    server: {
      fs: {
        allow: [root],
      },
    },
    resolve: {
      alias: {
        "@locales": resolve(root, "locales"),
        "@fixtures": resolve(root, "data/fixtures"),
        "@published": publication.directory,
      },
    },
  },
});
