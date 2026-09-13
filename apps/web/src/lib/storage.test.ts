import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  readTeachingLanguage,
  saveTeachingLanguage,
} from "./storage.ts";

const memory = new Map<string, string>();

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem(key: string) {
      return memory.has(key) ? memory.get(key)! : null;
    },
    setItem(key: string, value: string) {
      memory.set(key, value);
    },
    removeItem(key: string) {
      memory.delete(key);
    },
    clear() {
      memory.clear();
    },
  },
});

describe("browser storage", () => {
  it("reads a saved teaching-language choice and ignores junk", () => {
    memory.clear();
    assert.equal(readTeachingLanguage(), null);
    saveTeachingLanguage("en");
    assert.equal(readTeachingLanguage(), "en");
    saveTeachingLanguage("not-a-language");
    assert.equal(readTeachingLanguage(), "en");
  });

  it("no longer exposes shortlist or comparison storage (A80 owner decision)", async () => {
    memory.clear();
    // A80: the browsing utilities remain, the shortlist/compare store is gone.
    const mod = await import("./storage.ts");
    assert.equal("toggleSaved" in mod, false);
    assert.equal("toggleCompare" in mod, false);
    assert.equal("loadSavedIds" in mod, false);
    assert.equal("loadCompareIds" in mod, false);
  });
});
