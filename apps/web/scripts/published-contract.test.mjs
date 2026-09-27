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

function applyPath(payload, path) {
  let cursor = payload;
  for (const part of path.split(".")) {
    cursor = part === "-1" ? cursor[cursor.length - 1] : /^\d+$/.test(part) ? cursor[Number(part)] : cursor[part];
  }
  return cursor;
}

// Corpus cases resolve these against the snapshot itself, so a case never
// hard-codes an inventory row id that the next register update would break.
function resolveTokens(values, snapshotRoot) {
  const inventory = JSON.parse(fs.readFileSync(path.resolve(snapshotRoot, "browse/nine-hei-inventory.json"), "utf8"));
  const baseline = JSON.parse(fs.readFileSync(path.resolve(snapshotRoot, "msmt-hei-baseline.json"), "utf8"));
  const school = inventory.schools[0];
  const row = school.rows[0];
  const officialUrl = baseline.institutions.find((item) => item.id === school.id)?.officialUrl;
  const resolve = (value) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [resolve(key), resolve(item)]));
    }
    if (value === "$FIRST_ROW_ID") return row[0];
    if (value === "$FIRST_ROW_SCHOOL_URL") {
      assert.ok(officialUrl, "the baseline institution owning the first row has no officialUrl");
      return officialUrl;
    }
    return value;
  };
  return resolve(values);
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
        const cursor = mutation.path ? applyPath(payload, mutation.path) : payload;
        for (const key of mutation.delete || []) delete cursor[key];
        Object.assign(cursor, resolveTokens(mutation.set || {}, snapshotRoot));
        fs.writeFileSync(target, JSON.stringify(payload));
        // manifest.json is not one of the checksummed required files, and it is
        // not its own checksum entry: a corpus case may mutate the manifest's
        // declared counts (the Python runner in services/ingestion has the same
        // guard), but it must not leave a checksum key behind for it.
        if (mutation.file !== "manifest.json") {
          const manifestPath = path.resolve(snapshotRoot, "manifest.json");
          const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
          manifest.checksums[mutation.file] = "sha256:" + digest(target);
          fs.writeFileSync(manifestPath, JSON.stringify(manifest));
        }
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
