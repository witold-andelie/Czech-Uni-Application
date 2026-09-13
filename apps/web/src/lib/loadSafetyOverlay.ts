import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { emptySafetyOverlay, parseSafetyOverlay, type SafetyOverlay } from "./safetyStatus.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const publishedRoot = resolve(root, "data/published");

export function loadSafetyOverlayFromDisk(): SafetyOverlay {
  const publicCopy = resolve(publishedRoot, "safety-status.json");
  const pointerPath = resolve(publishedRoot, "safety/current.json");
  const candidates = [publicCopy];
  if (existsSync(pointerPath)) {
    try {
      const pointer = JSON.parse(readFileSync(pointerPath, "utf8")) as { generationDir?: string };
      if (typeof pointer.generationDir === "string") {
        candidates.unshift(resolve(publishedRoot, "safety", ...pointer.generationDir.split("/")));
      }
    } catch {
      /* last-known-safe is the public copy or empty overlay */
    }
  }
  for (const path of candidates) {
    if (!existsSync(path)) continue;
    try {
      const parsed = parseSafetyOverlay(JSON.parse(readFileSync(path, "utf8")));
      if (parsed) return parsed;
    } catch {
      continue;
    }
  }
  return emptySafetyOverlay();
}
