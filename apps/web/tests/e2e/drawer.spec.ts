import { expect, test } from "@playwright/test";
import {
  LOCALES,
  VIEWPORTS,
  filterOpenButton,
  focusedInsideDialog,
  msg,
  waitForProgrammeResults,
} from "./helpers";

async function openFilterDrawer(page, locale, path: string) {
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto(path);
  if (path.includes("/programmes")) await waitForProgrammeResults(page, locale);
  const trigger = filterOpenButton(page, locale);
  await expect(trigger).toBeVisible();
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  expect(await focusedInsideDialog(page)).toBeTruthy();
  return { trigger, dialog };
}

for (const locale of LOCALES) {
  for (const path of [`/${locale}/research-jobs`, `/${locale}/programmes?teachingLanguage=en`]) {
    test(`mobile filter drawer traps focus and restores it (${locale} ${path})`, async ({ page }) => {
      const { trigger, dialog } = await openFilterDrawer(page, locale, path);
      for (let i = 0; i < 12; i += 1) {
        await page.keyboard.press("Tab");
        expect(await focusedInsideDialog(page), `Tab ${i + 1} left the dialog`).toBeTruthy();
      }
      for (let i = 0; i < 12; i += 1) {
        await page.keyboard.press("Shift+Tab");
        expect(await focusedInsideDialog(page), `Shift+Tab ${i + 1} left the dialog`).toBeTruthy();
      }
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();

      await trigger.click();
      await expect(dialog).toBeVisible();
      await dialog.locator(".filter-sheet-bar .btn.primary").click();
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();

      await trigger.click();
      await page.locator(".sheet-backdrop").click({ position: { x: 20, y: 20 } });
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
    });
  }

  test(`mobile nav drawer traps focus (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.phone);
    await page.goto(`/${locale}/`);
    const toggle = page.getByRole("button", { name: msg(locale, "nav.openMenu") });
    await toggle.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    expect(await focusedInsideDialog(page)).toBeTruthy();
    for (let i = 0; i < 8; i += 1) {
      await page.keyboard.press("Tab");
      expect(await focusedInsideDialog(page)).toBeTruthy();
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(toggle).toBeFocused();
  });
}

test("desktop filters stay nonmodal and tab can reach results", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.goto("/en/research-jobs");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("form.filters")).toBeVisible();
  await page.locator("form.filters select").first().focus();
  let reachedResult = false;
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press("Tab");
    reachedResult = await page.evaluate(() => Boolean(document.activeElement?.closest("article.result-card")));
    if (reachedResult) break;
  }
  expect(reachedResult).toBeTruthy();
});

test("resizing to desktop closes the sheet and leaves a visible focus target", async ({ page }) => {
  const { dialog } = await openFilterDrawer(page, "en", "/en/research-jobs");
  await page.setViewportSize(VIEWPORTS.desktop);
  await expect(dialog).toHaveCount(0);
  await expect(page.locator("form.filters")).toBeVisible();
  const focusValid = await page.evaluate(() => {
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || active === document.body) return true;
    const style = window.getComputedStyle(active);
    return style.display !== "none" && style.visibility !== "hidden";
  });
  expect(focusValid).toBeTruthy();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
});

test("filter changes update the URL without closing the mobile sheet", async ({ page }) => {
  const { dialog } = await openFilterDrawer(page, "en", "/en/research-jobs");
  const search = dialog.getByRole("searchbox");
  await search.fill("engineer");
  await expect(page).toHaveURL(/q=engineer/);
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".filter-sheet-bar .btn.primary")).toBeVisible();
});

test("200% zoom and long Czech filter labels stay usable at 390px", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto("/cs/research-jobs");
  await filterOpenButton(page, "cs").click();
  const dialog = page.getByRole("dialog");
  const close = dialog.getByRole("button", { name: msg("cs", "filter.close") });
  await expect(close).toBeVisible();
  await expect(dialog.locator(".filter-sheet-bar .btn.primary")).toBeVisible();
  const sheetOverflow = await dialog.evaluate((el) => el.scrollWidth > el.clientWidth + 2);
  expect(sheetOverflow, "filter sheet overflowed horizontally at 390px").toBeFalsy();
  await page.setViewportSize({ width: 320, height: 568 });
  await expect(dialog).toBeVisible();
  await expect(close).toBeVisible();
  const narrowOverflow = await dialog.evaluate((el) => el.scrollWidth > el.clientWidth + 2);
  expect(narrowOverflow, "filter sheet overflowed horizontally when zoomed/narrow").toBeFalsy();
});
