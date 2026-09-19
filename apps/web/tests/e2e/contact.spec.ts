import { expect, test } from "@playwright/test";
import { LOCALES, msg, assertNoHorizontalOverflow } from "./helpers";

for (const locale of LOCALES) {
  for (const width of [390, 1280]) {
    test(`author contact ${locale} ${width}`, async ({ page, context }) => {
      await context.grantPermissions(["clipboard-read", "clipboard-write"]);
      await page.setViewportSize({ width, height: 720 });
      await page.goto(`/${locale}/map/`);
      const contact = page.locator(".author-contact");
      const trigger = contact.locator("summary");
      await expect(trigger).toHaveText(msg(locale, "contact.author"));
      await expect(contact).not.toHaveAttribute("open", "");
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await trigger.click();
      await expect(contact.getByText(msg(locale, "contact.intro"))).toBeVisible();
      await expect(contact.locator('a[href="mailto:andelie1892@gmail.com"]')).toBeVisible();
      await contact.getByRole("button", { name: msg(locale, "contact.copy"), exact: true }).click();
      await expect(contact.getByRole("status")).toHaveText(msg(locale, "contact.copied"));
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("CZ_1892");
      await assertNoHorizontalOverflow(page);
      await page.screenshot({ path: `../../work/contact-${locale}-${width}.png` });
      await page.keyboard.press("Escape");
      await expect(trigger).toBeFocused();
      await expect(contact).not.toHaveAttribute("open", "");
    });
  }
}
