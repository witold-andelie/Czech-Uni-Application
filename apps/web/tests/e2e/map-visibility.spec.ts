import { expect, test } from "@playwright/test";
import { LOCALES, STUB_PNG, msg } from "./helpers";

// A88: the interactive renderer must keep a real, nonzero area on every
// stated viewport — before and after selecting/closing a school — with
// stubbed tiles and with tiles blocked (SVG fallback).
const SIZES = [
  { width: 390, height: 844 },
  { width: 1280, height: 500 },
  { width: 1440, height: 600 },
  { width: 1440, height: 900 },
];

async function expectVisibleMap(page: import("@playwright/test").Page, minH = 300) {
  const box = await page.locator(".map-viewport-container").boundingBox();
  expect(box, "map viewport container must exist").toBeTruthy();
  expect(box!.height, `map area must exceed ${minH}px`).toBeGreaterThan(minH);
  expect(box!.width).toBeGreaterThan(200);
}

for (const locale of LOCALES) {
  for (const size of SIZES) {
    test(`map keeps nonzero area at ${size.width}x${size.height} (${locale}, stubbed tiles)`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.route("https://tile.openstreetmap.org/**", (route) =>
        route.fulfill({ status: 200, contentType: "image/png", body: STUB_PNG }),
      );
      await page.goto(`/${locale}/map`);
      await expect(
        page.getByRole("link", { name: msg(locale, "institutions.open") }).first(),
      ).toBeVisible({ timeout: 20_000 });
      await expectVisibleMap(page);

      const pick = page.locator(".map-school-pick:not([disabled])").first();
      await pick.click();
      await expect(page.locator(".map-selected-card")).toBeVisible();
      await expectVisibleMap(page);

      await page.locator(".map-selected-card").getByRole("button").first().click();
      await expect(page.locator(".map-selected-card")).toHaveCount(0);
      await expectVisibleMap(page);
    });

    test(`svg fallback keeps nonzero area at ${size.width}x${size.height} (${locale})`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());
      await page.goto(`/${locale}/map`);
      await expect(
        page.getByRole("link", { name: msg(locale, "institutions.open") }).first(),
      ).toBeVisible({ timeout: 20_000 });
      await expectVisibleMap(page);
    });
  }
}

test("mouse wheel without modifiers zooms the svg map", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());
  await page.goto("/en/map");
  await expect(page.locator(".map-viewport").first()).toBeVisible({ timeout: 20_000 });
  const viewport = page.locator(".map-viewport").first();
  const box = await viewport.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  const before = await page.evaluate(() => {
    const world = document.querySelector(".map-world") as HTMLElement | null;
    return world?.style.getPropertyValue("--map-scale") || "";
  });
  await page.mouse.wheel(0, -240);
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => {
    const world = document.querySelector(".map-world") as HTMLElement | null;
    return world?.style.getPropertyValue("--map-scale") || "";
  });
  expect(before).not.toEqual("");
  expect(after).not.toEqual(before);
});
