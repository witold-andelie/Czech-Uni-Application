import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { isModifiedLocaleClick, switchLocalePath } from "./localePath.ts";

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
    assert.equal(switchLocalePath(pathname, search, "cs"), "/cs/programmes?teachingLanguage=en&includeJoint=1");
    assert.equal(switchLocalePath("/404", "", "en"), "/en/");
    assert.equal(switchLocalePath("/zh-CN/404", "", "cs"), "/cs/");
  });

  it("replaces history on a plain locale click and leaves modified clicks to the browser", () => {
    assert.equal(isModifiedLocaleClick({ button: 0 }), false);
    assert.equal(isModifiedLocaleClick({ button: 0, ctrlKey: true }), true);
    assert.equal(isModifiedLocaleClick({ button: 0, metaKey: true }), true);
    assert.equal(isModifiedLocaleClick({ button: 1 }), true);
    const src = readFileSync(resolve(root, "apps/web/src/components/LocaleSwitcher.svelte"), "utf8");
    assert.match(src, /location\.replace/);
    assert.match(src, /isModifiedLocaleClick/);
  });

  it("keeps the CSCSE disclaimer in all three languages", () => {
    const zh = load("zh-CN.json");
    const en = load("en.json");
    const cs = load("cs.json");
    assert.match(zh["recognition.disclaimer"], /中留服/);
    assert.match(en["recognition.disclaimer"], /CSCSE/);
    assert.match(cs["recognition.disclaimer"], /CSCSE/);
    assert.match(zh["recognition.notFound.help"], /不等于/);
    assert.match(zh["recognition.operatorProvenance"], /不是对中留服网站的现场查询/);
    assert.match(en["recognition.operatorProvenance"], /not a live query/);
    assert.match(cs["recognition.operatorProvenance"], /Nejde o živý dotaz/);
  });
});
