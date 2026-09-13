import { pathToFileURL } from "node:url";
import { selectActiveSnapshot, validateSnapshot } from "./published-contract.mjs";

export function verifyActiveSnapshot() {
  const selection = selectActiveSnapshot();
  const result = validateSnapshot(selection);
  if (!result.passed) {
    const error = new Error("Published snapshot integrity and business validation failed");
    error.validationErrors = result.errors;
    throw error;
  }
  return { selection, result };
}

function main() {
  try {
    const { selection, result } = verifyActiveSnapshot();
    console.log(
      `OK: immutable snapshot ${selection.version} passed checksums, references, URLs, and review gates (${result.counts.jobs} jobs).`,
    );
  } catch (error) {
    console.error(`FATAL: ${error.message}`);
    for (const detail of error.validationErrors || []) console.error(`  - ${detail}`);
    process.exitCode = 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) main();
