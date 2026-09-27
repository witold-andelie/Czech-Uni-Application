import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  LOCALES,
  VIEWPORTS,
  assertNoHorizontalOverflow,
  msg,
  waitForProgrammeResults,
  type TestLocale,
} from "./helpers";

/**
 * CZU: the school whose own programme pages the offline resolver proved. The
 * filter is by institution, so only this school's cards are on the page.
 */
const CZU = "msmt-vs_41000";
/** Only the school's own registrable domain, or a subdomain of it. */
const CZU_HOST = /(^|\.)czu\.cz$/i;
/** Another organisation, including the national study directory. */
const FOREIGN_ORGANISATION = /^https:\/\/(?:[a-z0-9-]+\.)*(?:studyin\.gov\.cz|cuni\.cz|muni\.cz|upol\.cz|cvut\.cz|vsb\.cz|utb\.cz)(?:\/|$)/i;

/** The English-taught CZU register rows, so the pages to walk are known. */
const EN_PAGES = 4;

type OfficialLink = { href: string; label: string };

/**
 * The label of an official link is its first text node: `OfficialLink.svelte`
 * renders the label, then the icon, then the host and a visually hidden note,
 * so `textContent` ends with the host and the note rather than the label.
 */
function readOfficialLinks(nodes: Element[]): OfficialLink[] {
  return nodes.map((node) => {
    const label = Array.from(node.childNodes)
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => (child.textContent || "").trim())
      .find((text) => text.length > 0);
    return { href: node.getAttribute("href") || "", label: label || "" };
  });
}

/** The official links of one result card. */
async function linksOfCard(card: Locator): Promise<OfficialLink[]> {
  return card.locator("a.btn.external").evaluateAll(readOfficialLinks);
}

/**
 * Every card states which of the two cases it is in, and the link it states it
 * for is the school's own page. A card that names no programme page at all -
 * or that names another organisation - fails here.
 */
async function assertCardsStateTheirLink(page: Page, pageLabel: string, fallbackLabel: string): Promise<{ withPage: number; withoutPage: number }> {
  const cards = page.locator("article.result-card");
  const total = await cards.count();
  expect(total, "no result cards on the page").toBeGreaterThan(0);
  let withPage = 0;
  let withoutPage = 0;
  for (let index = 0; index < total; index += 1) {
    const card = cards.nth(index);
    const title = ((await card.locator("h3").first().innerText()) || "").split("\n")[0].trim();
    const links = await linksOfCard(card);
    const labelled = links.filter((link) => link.label === pageLabel || link.label === fallbackLabel);
    expect(labelled.length, `${title}: the card does not say which official page it links`).toBe(1);
    const link = labelled[0];
    expect(link.href, `${title}: the official link is not https`).toMatch(/^https:\/\//i);
    expect(CZU_HOST.test(new URL(link.href).hostname), `${title}: ${link.href} is not a CZU page`).toBeTruthy();
    expect(FOREIGN_ORGANISATION.test(link.href), `${title}: ${link.href} is another organisation's page`).toBeFalsy();
    if (link.label === pageLabel) withPage += 1;
    else withoutPage += 1;
  }
  return { withPage, withoutPage };
}

/** The card of the first row that states `label`, so its detail can be opened. */
async function cardStatingLabel(page: Page, label: string): Promise<Locator> {
  const cards = page.locator("article.result-card");
  const total = await cards.count();
  for (let index = 0; index < total; index += 1) {
    const card = cards.nth(index);
    if ((await linksOfCard(card)).some((link) => link.label === label)) return card;
  }
  throw new Error(`no result card states "${label}"`);
}

/** The href of the detail link whose whole text is `label`, if it is there. */
async function officialHrefStating(page: Page, label: string): Promise<string | null> {
  return page.locator("a.external").evaluateAll(
    (nodes, wanted) => {
      for (const node of nodes) {
        if ((node.textContent || "").trim() === wanted) return node.getAttribute("href") || "";
      }
      return null;
    },
    label,
  );
}

const listUrl = (locale: TestLocale) => `/${locale}/programmes?teachingLanguage=en&institution=${CZU}`;

for (const locale of LOCALES) {
  test(`CZU rows name their own programme page or say so (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    const pageLabel = msg(locale, "programme.link.page");
    const fallbackLabel = msg(locale, "programme.link.fallback");
    // CZU publishes English-taught programme pages for some of its register
    // rows and not for others, so the list has to state both cases in its own
    // wording rather than collapse either into one "official link" label.
    let withPage = 0;
    let withoutPage = 0;
    for (let pageNumber = 1; pageNumber <= EN_PAGES; pageNumber += 1) {
      await page.goto(`${listUrl(locale)}&page=${pageNumber}`);
      await waitForProgrammeResults(page, locale);
      const seen = await assertCardsStateTheirLink(page, pageLabel, fallbackLabel);
      withPage += seen.withPage;
      withoutPage += seen.withoutPage;
      if (withPage > 0 && withoutPage > 0) break;
    }
    expect(withPage, "no card named the programme's own page").toBeGreaterThan(0);
    expect(withoutPage, "no card said the programme page was not found").toBeGreaterThan(0);
  });

  test(`the programme label and its fallback agree on the detail page (${locale})`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    const pageLabel = msg(locale, "programme.link.page");
    const fallbackLabel = msg(locale, "programme.link.fallback");

    await page.goto(listUrl(locale));
    await waitForProgrammeResults(page, locale);

    let card = await cardStatingLabel(page, pageLabel);
    await card.locator("h3 a").first().click();
    await expect(page).toHaveURL(new RegExp(`^/${locale}/programmes/[^/]+$`));
    const detailHref = await officialHrefStating(page, pageLabel);
    expect(detailHref, "the detail page does not name the programme page").toMatch(/^https:\/\//i);
    expect(CZU_HOST.test(new URL(String(detailHref)).hostname), `${detailHref} is not a CZU page`).toBeTruthy();

    await page.goto(listUrl(locale));
    await waitForProgrammeResults(page, locale);
    card = await cardStatingLabel(page, fallbackLabel);
    await card.locator("h3 a").first().click();
    await expect(page).toHaveURL(new RegExp(`^/${locale}/programmes/[^/]+$`));
    const fallbackHref = await officialHrefStating(page, fallbackLabel);
    expect(fallbackHref, "the detail page does not say it shows the university site").toMatch(/^https:\/\//i);
    expect(FOREIGN_ORGANISATION.test(String(fallbackHref)), `${fallbackHref} is another organisation's page`).toBeFalsy();
  });
}

test("CZU programme links fit a phone without horizontal overflow", async ({ page }) => {
  const locale: TestLocale = "zh-CN";
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto(`/${locale}/programmes?teachingLanguage=en&institution=${CZU}`);
  await waitForProgrammeResults(page, locale);
  await expect(page.locator("article.result-card").first()).toBeVisible();

  // Both labels are long sentences, so the check that they fit has to walk past
  // the first page until each of them has been seen.
  const labels = [msg(locale, "programme.link.page"), msg(locale, "programme.link.fallback")];
  const seen = new Set<string>();
  for (let pageNumber = 1; pageNumber <= EN_PAGES && seen.size < labels.length; pageNumber += 1) {
    await page.goto(`/${locale}/programmes?teachingLanguage=en&institution=${CZU}&page=${pageNumber}`);
    await waitForProgrammeResults(page, locale);
    const cards = page.locator("article.result-card");
    for (let index = 0; index < (await cards.count()); index += 1) {
      for (const link of await linksOfCard(cards.nth(index))) {
        if (labels.includes(link.label)) seen.add(link.label);
      }
    }
    await assertNoHorizontalOverflow(page);
  }
  for (const label of labels) {
    expect(seen.has(label), `no card on a phone states "${label}"`).toBeTruthy();
  }
});
