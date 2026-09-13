import { expect, test } from "@playwright/test";

// Owner UI rule: on desktop the filter rail stays pinned while the page
// scrolls, on both the programmes and research-jobs pages.
for (const route of ["/zh-CN/programmes?teachingLanguage=en", "/zh-CN/research-jobs"]) {
  test(`filter rail stays pinned on scroll (${route})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 800 });
    await page.goto(route);
    const rail = page.locator(".layout-list > .filters.card");
    await expect(rail).toBeVisible();

    const before = await rail.evaluate((el) => {
      el.scrollTop = 0;
      return Math.round(el.getBoundingClientRect().top);
    });

    await page.evaluate(() => window.scrollBy(0, 1200));
    await page.waitForTimeout(300);

    const after = await rail.evaluate((el) => ({
      top: Math.round(el.getBoundingClientRect().top),
      visible: el.getBoundingClientRect().bottom > 0 && el.getBoundingClientRect().top < window.innerHeight,
    }));
    expect(after.top, "rail pins near the viewport top while scrolled").toBeLessThanOrEqual(before);
    expect(after.top).toBeGreaterThanOrEqual(0);
    expect(after.visible, "rail still visible after scrolling").toBeTruthy();
    // The results column must have scrolled (page really scrolled).
    const scrolled = await page.evaluate(() => window.scrollY);
    expect(scrolled).toBeGreaterThan(400);
    // Rail remains interactive: a control inside it is clickable after scroll.
    const clear = rail.getByRole("button").first();
    await expect(clear).toBeEnabled();
  });
}

for (const route of ["/zh-CN/programmes?teachingLanguage=en", "/zh-CN/research-jobs"]) {
  test(`two-column rail layout already at 768px (${route})`, async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto(route);
    const rail = page.locator(".layout-list > .filters.card");
    await expect(rail).toBeVisible();
    const geo = await page.evaluate(() => {
      const rail = document.querySelector(".layout-list > .filters.card");
      const results = document.querySelector(".layout-list > div");
      const r = rail.getBoundingClientRect();
      const d = results.getBoundingClientRect();
      return { railLeft: Math.round(r.left), railW: Math.round(r.width), resultsLeft: Math.round(d.left), top: Math.round(r.top) };
    });
    expect(geo.railLeft).toBeLessThan(geo.resultsLeft, "rail sits left of results");
    expect(geo.railW).toBeGreaterThan(200);
    await page.evaluate(() => window.scrollBy(0, 900));
    await page.waitForTimeout(250);
    const top = await rail.evaluate((el) => Math.round(el.getBoundingClientRect().top));
    expect(top).toBeGreaterThanOrEqual(0);
    expect(top).toBeLessThanOrEqual(20);
  });
}

test("mobile sheet behaviour unchanged (rail hidden, floating open button)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/zh-CN/research-jobs");
  await expect(page.locator(".layout-list > .filters.card")).toBeHidden();
  const open = page.locator(".layout-list button.filter-open-mobile");
  await expect(open).toBeVisible();
});
