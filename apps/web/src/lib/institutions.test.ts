import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  filterBaselineInstitutions,
  institutionDisplayName,
  institutionQueryFromSearch,
  searchFromInstitutionQuery,
  uniqueBaselineCities,
} from "./institutions.ts";
import type { BaselineInstitution } from "./loadBaseline.ts";
import { cityFromBaseline } from "./mergeBrowseCatalog.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const baseline = JSON.parse(readFileSync(resolve(root, "data/sources/msmt-hei-baseline.json"), "utf8")) as {
  institutions: BaselineInstitution[];
};

describe("institution directory search", () => {
  const items = baseline.institutions;

  it("finds Charles University from Chinese, English, and Czech names", () => {
    for (const needle of ["查理大学", "Charles University", "Univerzita Karlova"]) {
      const found = filterBaselineInstitutions(items, { search: needle, city: "all", ownership: "all", cscse: "all" });
      assert.ok(found.some((item) => item.id === "msmt-vs_11000"), needle);
    }
  });

  it("filters public operator-list matches without dropping Charles or claiming an official lookup", () => {
    const found = filterBaselineInstitutions(items, { search: "", city: "all", ownership: "public", cscse: "operator_listed" });
    assert.ok(found.every((item) => item.ownership === "public" && item.cscseReference?.operatorListStatus === "listed"));
    assert.ok(found.every((item) => item.cscseLookupStatus === "unverified"));
    assert.ok(found.some((item) => item.id === "msmt-vs_11000"));
    assert.ok(!found.some((item) => item.ownership === "private"));
  });

  it("puts operator-list matches first, then Prague, Brno, Olomouc, Ostrava, other cities", () => {
    const found = filterBaselineInstitutions(items, { search: "", city: "all", ownership: "all", cscse: "all" });
    const listedEnd = found.findIndex((item) => item.cscseReference?.operatorListStatus !== "listed");
    assert.ok(listedEnd > 0);
    assert.ok(found.slice(0, listedEnd).every((item) => item.cscseReference?.operatorListStatus === "listed"));
    assert.ok(found.slice(listedEnd).every((item) => item.cscseReference?.operatorListStatus !== "listed"));
    const listed = found.slice(0, listedEnd);
    const charles = listed.findIndex((item) => item.id === "msmt-vs_11000");
    const masaryk = listed.findIndex((item) => item.id === "msmt-vs_14000");
    const palacky = listed.findIndex((item) => item.id === "msmt-vs_15000");
    const vsb = listed.findIndex((item) => item.id === "msmt-vs_27000");
    const jcu = listed.findIndex((item) => item.id === "msmt-vs_12000");
    assert.ok(charles >= 0 && charles < masaryk);
    assert.ok(masaryk < palacky);
    assert.ok(palacky < vsb);
    assert.ok(vsb < jcu);
    const avu = found.findIndex((item) => item.id === "msmt-vs_52000");
    assert.ok(avu >= listedEnd);
    assert.equal(found[0].cscseLookupStatus, "unverified");
    assert.ok((found[0].seat ?? "").toLowerCase().includes("praha") || found[0].region === "Praha");
  });

  it("round-trips directory chips through the query string", () => {
    const query = institutionQueryFromSearch("?q=Charles&city=Prague&ownership=public&cscse=operator_listed");
    assert.equal(query.search, "Charles");
    assert.equal(query.city, "Prague");
    assert.equal(searchFromInstitutionQuery(query), "?q=Charles&city=Prague&ownership=public&cscse=operator_listed");
    assert.equal(institutionDisplayName(items.find((item) => item.id === "msmt-vs_11000")!, "zh-CN"), "查理大学");
  });

  it("filters the directory by register city and ignores state ownership in the URL", () => {
    const prague = filterBaselineInstitutions(items, { search: "", city: "Prague", ownership: "all", cscse: "all" });
    assert.ok(prague.some((item) => item.id === "msmt-vs_11000"));
    assert.ok(prague.every((item) => cityFromBaseline(item).en === "Prague"));
    const parsed = institutionQueryFromSearch("?ownership=state&city=Brno");
    assert.equal(parsed.ownership, "all");
    assert.equal(parsed.city, "Brno");
    const cities = uniqueBaselineCities(items, "zh-CN");
    assert.ok(cities.some((item) => item.value === "Prague"));
    assert.ok(cities.some((item) => item.value === "Brno"));
    const dirSrc = readFileSync(resolve(root, "apps/web/src/components/InstitutionResults.svelte"), "utf8");
    const mapSrc = readFileSync(resolve(root, "apps/web/src/components/InstitutionMap.svelte"), "utf8");
    assert.match(dirSrc, /uniqueBaselineCities/);
    assert.equal(dirSrc.includes('type="search"'), false);
    assert.equal(dirSrc.includes('toggleOwnership("state")'), false);
    assert.equal(mapSrc.includes('type="search"'), false);
    assert.equal(mapSrc.includes('toggleOwnership("state")'), false);
  });
});
