import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { isLocale } from "./catalog.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");

function load(name: string): Record<string, string> {
  return JSON.parse(readFileSync(resolve(root, "locales", name), "utf8")) as Record<string, string>;
}

describe("locale parity", () => {
  it("keeps identical non-empty keys in zh-CN, en, and cs", () => {
    const zh = load("zh-CN.json");
    const en = load("en.json");
    const cs = load("cs.json");
    assert.deepEqual(Object.keys(zh).sort(), Object.keys(en).sort());
    assert.deepEqual(Object.keys(zh).sort(), Object.keys(cs).sort());
    for (const table of [zh, en, cs]) {
      for (const [key, value] of Object.entries(table)) {
        assert.ok(value.trim(), key);
      }
    }
  });

  it("switches only the locale segment and keeps query state", () => {
    const pathname = "/zh-CN/programmes";
    const search = "?teachingLanguage=en&includeJoint=1";
    const parts = pathname.split("/");
    if (parts[1] && isLocale(parts[1])) parts[1] = "cs";
    assert.equal(`${parts.join("/")}${search}`, "/cs/programmes?teachingLanguage=en&includeJoint=1");
  });

  it("keeps the CSCSE disclaimer in all three languages", () => {
    const zh = load("zh-CN.json");
    const en = load("en.json");
    const cs = load("cs.json");
    assert.match(zh["recognition.disclaimer"], /中留服/);
    assert.match(en["recognition.disclaimer"], /CSCSE/);
    assert.match(cs["recognition.disclaimer"], /CSCSE/);
    assert.match(zh["recognition.notFound.help"], /不等于/);
  });
});
