import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const LOCALES = ["zh-CN", "en", "cs"] as const;
export type TestLocale = (typeof LOCALES)[number];

export const VIEWPORTS = {
  phone: { width: 390, height: 844 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1440, height: 900 },
} as const;

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const bundles = {
  "zh-CN": JSON.parse(readFileSync(resolve(root, "locales/zh-CN.json"), "utf8")) as Record<string, string>,
  en: JSON.parse(readFileSync(resolve(root, "locales/en.json"), "utf8")) as Record<string, string>,
  cs: JSON.parse(readFileSync(resolve(root, "locales/cs.json"), "utf8")) as Record<string, string>,
};

export function msg(locale: TestLocale, key: string, vars: Record<string, string | number> = {}): string {
  const template = bundles[locale][key];
  if (!template) throw new Error(`Missing ${key} for ${locale}`);
  return Object.entries(vars).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), template);
}

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);
  expect(overflow, "page content overflowed horizontally").toBeFalsy();
}

export async function waitForProgrammeResults(page: Page, locale: TestLocale): Promise<void> {
  await expect(page.getByText(msg(locale, "inventory.loading"))).toHaveCount(0, { timeout: 30_000 });
}

export function filterOpenButton(page: Page, locale: TestLocale) {
  return page.getByRole("button", { name: new RegExp(`^${escapeRegExp(msg(locale, "filter.drawer"))}`) });
}

export async function focusedInsideDialog(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"][aria-modal="true"]');
    return Boolean(dialog && document.activeElement && dialog.contains(document.activeElement));
  });
}

export const STUB_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);
