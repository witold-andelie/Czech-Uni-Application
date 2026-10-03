import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { institutionFromResearch } from "./mergeBrowseCatalog.ts";

describe("public research institutions as employers", () => {
  it("states the register's facts and no degree recognition", () => {
    const institution = institutionFromResearch({
      id: "rvvi-68378271",
      officialName: "Fyzikální ústav AV ČR, v. v. i.",
      officialNameEn: "Institute of Physics of the CAS",
      legalType: "research_institute",
      ownership: "public",
      ico: "68378271",
      officialUrl: "http://www.fzu.cz",
      seat: "Na Slovance 1999/2, Praha 8, 182 00",
      city: "Praha",
      source: { registryUrl: "https://rvvi.msmt.cz/", detailUrl: "https://rvvi.msmt.cz/detail.php?ic=68378271" },
    });
    assert.equal(institution.legalType, "research_institute");
    assert.equal(institution.ownership, "public");
    assert.equal(institution.displayName.en, "Institute of Physics of the CAS");
    // No Chinese name is recorded: the official name, never an invented one.
    assert.equal(institution.displayName["zh-CN"], "Fyzikální ústav AV ČR, v. v. i.");
    assert.equal(institution.city.en, "Prague");
    assert.equal(institution.cscseReference.evidenceKind, "none");
    assert.equal(institution.registerUrl, "https://rvvi.msmt.cz/detail.php?ic=68378271");
  });
});
