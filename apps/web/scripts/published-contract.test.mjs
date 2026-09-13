import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { after, describe, it } from "node:test";
import { prepareBrowserAssets, ROOT, selectActiveSnapshot, validateSnapshot, WEB_ROOT } from "./published-contract.mjs";

const scratchRoot = path.resolve(WEB_ROOT, ".generated");
fs.mkdirSync(scratchRoot, { recursive: true });
const scratch = fs.mkdtempSync(path.resolve(scratchRoot, "publication-contract-test-"));
after(() => fs.rmSync(scratch, { recursive: true, force: true }));

function digest(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

describe("immutable browser publication selection", () => {
  it("keeps a build pinned after current.json changes", () => {
    const selected = selectActiveSnapshot({ root: ROOT });
    const isolatedRoot = path.resolve(scratch, "repo");
    const isolatedPublished = path.resolve(isolatedRoot, "data/published");
    const isolatedSnapshot = path.resolve(isolatedPublished, "snapshots", selected.version);
    fs.mkdirSync(path.dirname(isolatedSnapshot), { recursive: true });
    fs.cpSync(selected.snapshotRoot, isolatedSnapshot, { recursive: true });
    fs.writeFileSync(
      path.resolve(isolatedPublished, "current.json"),
      JSON.stringify({ activeVersion: selected.version, snapshotDir: `snapshots/${selected.version}` }),
    );

    const pinned = selectActiveSnapshot({ root: isolatedRoot });
    fs.writeFileSync(
      path.resolve(isolatedPublished, "current.json"),
      JSON.stringify({ activeVersion: "v2099-01-01.1", snapshotDir: "snapshots/v2099-01-01.1" }),
    );
    const result = validateSnapshot(pinned);
    assert.equal(result.passed, true, result.errors.join("\n"));
    assert.equal(pinned.version, selected.version);
  });

  it("generates the versioned browser asset only from the pinned snapshot", () => {
    const selected = selectActiveSnapshot({ root: ROOT });
    const webRoot = path.resolve(scratch, "web");
    const legacy = path.resolve(webRoot, "public/data/nine-hei-inventory.json");
    fs.mkdirSync(path.dirname(legacy), { recursive: true });
    fs.writeFileSync(legacy, "{\"polluted\":true}\n");

    const generated = prepareBrowserAssets(selected, { webRoot });
    const asset = path.resolve(generated, `data/published/${selected.version}/browse/nine-hei-inventory.json`);
    const immutable = path.resolve(selected.snapshotRoot, "browse/nine-hei-inventory.json");
    assert.equal(digest(asset), digest(immutable));
    assert.notEqual(digest(asset), digest(legacy));
  });

  it("rejects an impossible published position workload", () => {
    const selected = selectActiveSnapshot({ root: ROOT });
    const snapshotRoot = path.resolve(scratch, "invalid-workload", selected.version);
    fs.cpSync(selected.snapshotRoot, snapshotRoot, { recursive: true });
    const jobsPath = path.resolve(snapshotRoot, "browse/nine-hei-jobs.json");
    const jobs = JSON.parse(fs.readFileSync(jobsPath, "utf8"));
    jobs.jobs[0].employmentFte = 1.5;
    fs.writeFileSync(jobsPath, JSON.stringify(jobs));

    const result = validateSnapshot({ ...selected, snapshotRoot });
    assert.equal(result.passed, false);
    assert.ok(result.errors.some((error) => error.includes("employmentFte must be null or a number in (0, 1]")), result.errors.join("\n"));
  });

  it("rejects the shared A52/A53 contract corpus in Node", () => {
    const cases = JSON.parse(fs.readFileSync(path.resolve(ROOT, "tests/contracts/cases.json"), "utf8"));
    const selected = selectActiveSnapshot({ root: ROOT });
    for (const item of cases.cases) {
      const snapshotRoot = path.resolve(scratch, "corpus", item.id, selected.version);
      fs.cpSync(selected.snapshotRoot, snapshotRoot, { recursive: true });
      for (const mutation of item.mutations || []) {
        const target = path.resolve(snapshotRoot, ...mutation.file.split("/"));
        const payload = JSON.parse(fs.readFileSync(target, "utf8"));
        let cursor = payload;
        const parts = mutation.path.split(".");
        for (const part of parts) {
          cursor = part === "-1" ? cursor[cursor.length - 1] : /^\d+$/.test(part) ? cursor[Number(part)] : cursor[part];
        }
        for (const key of mutation.delete || []) delete cursor[key];
        Object.assign(cursor, mutation.set || {});
        fs.writeFileSync(target, JSON.stringify(payload));
        const manifestPath = path.resolve(snapshotRoot, "manifest.json");
        const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
        manifest.checksums[mutation.file] = "sha256:" + digest(target);
        fs.writeFileSync(manifestPath, JSON.stringify(manifest));
      }
      const result = validateSnapshot({ ...selected, snapshotRoot });
      const codes = new Set(result.errors.map((error) => error.split(":")[0]));
      if (item.expect === "accept") {
        assert.equal(result.passed, true, `${item.id} should accept:\n${result.errors.join("\n")}`);
      } else {
        assert.equal(result.passed, false, `${item.id} should reject`);
        for (const rule of item.rules) {
          assert.ok(codes.has(rule), `${item.id} missing ${rule} in ${result.errors.join(" | ")}`);
        }
      }
    }
  });
});
