import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

export default defineConfig({
  output: "static",
  integrations: [svelte()],
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
      },
    },
  },
});
