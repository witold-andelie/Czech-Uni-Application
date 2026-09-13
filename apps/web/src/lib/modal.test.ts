import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { cycleTabIndex } from "./modal.ts";

describe("modal tab cycle", () => {
  it("wraps forward from the last control to the first", () => {
    assert.equal(cycleTabIndex(4, 3, false), 0);
    assert.equal(cycleTabIndex(4, 0, false), 1);
  });

  it("wraps reverse from the first control to the last", () => {
    assert.equal(cycleTabIndex(4, 0, true), 3);
    assert.equal(cycleTabIndex(4, 2, true), 1);
  });

  it("sends focus that escaped the dialog back to an edge control", () => {
    assert.equal(cycleTabIndex(3, -1, false), 0);
    assert.equal(cycleTabIndex(3, -1, true), 2);
    assert.equal(cycleTabIndex(3, 99, false), 0);
    assert.equal(cycleTabIndex(0, 0, false), -1);
  });
});
