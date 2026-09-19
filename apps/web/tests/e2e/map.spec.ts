import { expect, test } from "@playwright/test";
import { STUB_PNG, VIEWPORTS, msg } from "./helpers";

test("stubbed map tiles keep the institution list", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: STUB_PNG }),
  );
  await page.goto("/en/map");
  await expect(page.getByRole("heading", { level: 1, name: msg("en", "map.title") })).toBeVisible();
  await expect(page.getByRole("link", { name: msg("en", "institutions.open") }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(msg("en", "map.tilesFallback"))).toHaveCount(0);
  await expect(page.locator(".map-viewport.svg-basemap")).toBeVisible();
});

test("blocked map tiles fall back to the bundled overview", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.phone);
  await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());
  await page.goto("/zh-CN/map");
  const tiles = msg("zh-CN", "map.tilesFallback");
  const webgl = msg("zh-CN", "map.webglFallback");
  await expect(page.getByRole("status")).toBeVisible({ timeout: 20_000 });
  const text = await page.getByRole("status").innerText();
  expect(text.includes(tiles) || text.includes(webgl)).toBeTruthy();
  await expect(page.getByRole("link", { name: msg("zh-CN", "institutions.open") }).first()).toBeVisible();
});
