import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { prepareBrowserAssets, selectActiveSnapshot, validateSnapshot, WEB_ROOT } from "./published-contract.mjs";

const TEST_FILES = [
  "scripts/published-contract.test.mjs",
  "src/lib/catalog.test.ts",
  "src/lib/i18n.test.ts",
  "src/lib/storage.test.ts",
  "src/lib/institutions.test.ts",
  "src/lib/inventory.test.ts",
  "src/lib/mapProjection.test.ts",
  "src/lib/safetyStatus.test.ts",
  "src/lib/modal.test.ts",
];

function run(command, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: WEB_ROOT, env, stdio: "inherit", windowsHide: true });
    child.on("error", reject);
    child.on("exit", (code, signal) => {
      if (signal) reject(new Error(`${command} terminated by ${signal}`));
      else resolve(code ?? 1);
    });
  });
}

async function main() {
  const mode = process.argv[2];
  if (!["build", "check", "dev"].includes(mode)) throw new Error("Usage: run-with-published.mjs <build|check|dev> [args]");
  const selection = selectActiveSnapshot();
  const validation = validateSnapshot(selection);
  if (!validation.passed) {
    console.error(`FATAL: immutable snapshot ${selection.version} failed publication validation:`);
    for (const error of validation.errors) console.error(`  - ${error}`);
    process.exitCode = 1;
    return;
  }
  const publicDir = prepareBrowserAssets(selection);
  const env = { ...process.env, CZECH_UNI_PUBLISHED_VERSION: selection.version, CZECH_UNI_PUBLISHED_DIR: selection.snapshotRoot, CZECH_UNI_PUBLIC_DIR: publicDir };
  console.log(`Pinned ${mode} to immutable publication ${selection.version}.`);

  if (mode === "build") {
    const testCode = await run(process.execPath, ["--experimental-strip-types", "--test", ...TEST_FILES], env);
    if (testCode !== 0) {
      process.exitCode = testCode;
      return;
    }
  }
  const astroCli = path.resolve(WEB_ROOT, "node_modules/astro/bin/astro.mjs");
  const astroArgs = [mode, ...process.argv.slice(3)];
  process.exitCode = await run(process.execPath, [astroCli, ...astroArgs], env);
}

main().catch((error) => {
  console.error(`FATAL: ${error.message}`);
  process.exitCode = 1;
});
