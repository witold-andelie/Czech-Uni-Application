import { expect, test } from "@playwright/test";
import { assertNoHorizontalOverflow, LOCALES, msg } from "./helpers";

// A79: selecting a school on the map must keep the selected-school card
// reachable — name, close button and actions never clipped by an ancestor —
// at the exact reported constrained sizes, in all three locales.
const SIZES = [
  { width: 1280, height: 500 },
  { width: 1440, height: 600 },
  { width: 390, height: 844 },
];

for (const locale of LOCALES) {
  for (const size of SIZES) {
    test(`selected school card stays usable at ${size.width}x${size.height} (${locale})`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto(`/${locale}/map`);
      await expect(
        page.getByRole("link", { name: msg(locale, "institutions.open") }).first(),
      ).toBeVisible({ timeout: 20_000 });

      // The school list and the map region must stay separate normal-flow
      // regions: no page-level horizontal overflow even with long labels.
      await assertNoHorizontalOverflow(page);

      // Select the first selectable school in the list.
      const schoolButton = page.locator(".map-school-pick:not([disabled])").first();
      await schoolButton.click();
      await expect(page.locator(".map-selected-card")).toBeVisible();

      const card = page.locator(".map-selected-card");
      await expect(card.getByRole("heading")).toBeVisible();
      await expect(card.getByRole("button", { name: msg(locale, "map.closeCard") })).toBeVisible();
      await expect(card.getByRole("link", { name: new RegExp(msg(locale, "institutions.open")) })).toBeVisible();

      // Nothing on the card may be clipped by an overflow-hidden ancestor:
      // every essential control must have a fully visible bounding box.
      const clipped = await card.evaluate((element) => {
        const probe = (node: Element) => {
          const box = node.getBoundingClientRect();
          if (box.width === 0 || box.height === 0) return true;
          let ancestor = node.parentElement;
          while (ancestor) {
            const style = getComputedStyle(ancestor);
            if (style.overflow === "hidden" || style.overflowX === "hidden" || style.overflowY === "hidden") {
              const ancestorBox = ancestor.getBoundingClientRect();
              if (
                box.top < ancestorBox.top - 1 ||
                box.bottom > ancestorBox.bottom + 1 ||
                box.left < ancestorBox.left - 1 ||
                box.right > ancestorBox.right + 1
              ) {
                return true;
              }
            }
            ancestor = ancestor.parentElement;
          }
          return false;
        };
        const heading = element.querySelector("h3");
        const close = Array.from(element.querySelectorAll("button")).find((button) =>
          (button.getAttribute("aria-label") || "").length > 0,
        );
        const action = element.querySelector(".card-actions a");
        return [heading, close, action].some((node) => node && probe(node));
      });
      expect(clipped, "selected card content is clipped by an ancestor").toBeFalsy();
    });
  }
}
