<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import { safeHttpUrl } from "../lib/catalog";
  import { legalTypeLabel, operatorListKey, ownershipLabel, recognitionKey } from "../lib/format";
  import { t } from "../lib/i18n";
  import {
    defaultInstitutionQuery,
    filterBaselineInstitutions,
    institutionDisplayName,
    institutionQueryFromSearch,
    operatorListStatus,
    searchFromInstitutionQuery,
    uniqueBaselineCities,
    type InstitutionQuery,
  } from "../lib/institutions";
  import { loadBaseline, type BaselineInstitution } from "../lib/loadBaseline";
  import type { UiLocale } from "../lib/types";
  import ExternalIcon from "./ExternalIcon.svelte";

  let { locale }: { locale: UiLocale } = $props();

  const baseline = loadBaseline();
  const all = baseline.institutions;
  let query = $state<InstitutionQuery>(defaultInstitutionQuery());

  $effect(() => {
    const onPop = () => {
      query = institutionQueryFromSearch(window.location.search);
    };
    onPop();
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
    };
  });

  let visible = $derived(filterBaselineInstitutions(all, query));
  let cities = $derived(uniqueBaselineCities(all, locale));

  function syncUrl() {
    const href = `${window.location.pathname}${searchFromInstitutionQuery(query)}`;
    history.replaceState(null, "", href);
    window.dispatchEvent(new Event("listquerychange"));
  }

  function toggleCity(value: string) {
    query.city = query.city === value ? "all" : value;
    syncUrl();
  }

  function toggleOwnership(value: InstitutionQuery["ownership"]) {
    query.ownership = query.ownership === value ? "all" : value;
    syncUrl();
  }

  function toggleCscse(value: InstitutionQuery["cscse"]) {
    query.cscse = query.cscse === value ? "all" : value;
    syncUrl();
  }

  function clearFilters() {
    query = defaultInstitutionQuery();
    history.replaceState(null, "", window.location.pathname);
    window.dispatchEvent(new Event("listquerychange"));
  }

  function secondaryLine(item: BaselineInstitution): string {
    const names = [item.officialName, item.officialNameEn, item.cscseReference?.listedNameZh, item.cscseReference?.listedNameEn]
      .filter((name): name is string => Boolean(name && name.trim()))
      .filter((name, index, rows) => rows.indexOf(name) === index && name !== institutionDisplayName(item, locale));
    return names.slice(0, 2).join(" · ");
  }
</script>

<div class="directory-toolbar">
  <div class="chip-group">
    <span class="field-label">{t(locale, "filter.city")}</span>
    <div class="chip-row" role="group" aria-label={t(locale, "filter.city")}>
      <button type="button" class="chip" aria-pressed={query.city === "all"} onclick={() => { query.city = "all"; syncUrl(); }}>
        {t(locale, "filter.all")}
      </button>
      {#each cities as city}
        <button type="button" class="chip" aria-pressed={query.city === city.value} onclick={() => toggleCity(city.value)}>
          {city.label}
        </button>
      {/each}
    </div>
  </div>
  <div class="chip-row" role="group" aria-label={t(locale, "filter.ownership")}>
    <button type="button" class="chip" aria-pressed={query.ownership === "public"} onclick={() => toggleOwnership("public")}>
      {t(locale, "institution.public")}
    </button>
    <button type="button" class="chip" aria-pressed={query.ownership === "private"} onclick={() => toggleOwnership("private")}>
      {t(locale, "institution.private")}
    </button>
  </div>
  <div class="chip-row" role="group" aria-label={t(locale, "filter.recognition")}>
    <button type="button" class="chip" aria-pressed={query.cscse === "operator_listed"} onclick={() => toggleCscse("operator_listed")}>
      {t(locale, "recognition.operatorListed")}
    </button>
    <button type="button" class="chip" aria-pressed={query.cscse === "listed"} onclick={() => toggleCscse("listed")}>
      {t(locale, "recognition.listed")}
    </button>
  </div>
  <p class="muted">{t(locale, "filter.count", { n: visible.length })} · {t(locale, "institutions.count", { n: all.length })}</p>
  {#if query.city !== "all" || query.ownership !== "all" || query.cscse !== "all"}
    <button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button>
  {/if}
</div>

{#if visible.length === 0}
  <div class="empty card">
    <h2>{t(locale, "empty.title")}</h2>
    <p>{t(locale, "empty.help")}</p>
    <p><button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button></p>
  </div>
{:else}
  <div class="institution-grid">
    {#each visible as item}
      {@const href = safeHttpUrl(item.officialUrl)}
      {@const extra = secondaryLine(item)}
      <article class="card institution-card">
        <p class="muted">{item.msmtCode} · {item.region}</p>
        <h2>
          <a href={withBase(`/${locale}/institutions/${item.id}`)}>{institutionDisplayName(item, locale)}</a>
        </h2>
        {#if extra}
          <p class="muted">{extra}</p>
        {/if}
        <div class="tags">
          <span class={`tag ownership-${item.ownership}`}>{ownershipLabel(item.ownership, locale)}</span>
          <span class="tag">{legalTypeLabel(item.legalType, locale)}</span>
          <span class={`tag cscse-${item.cscseLookupStatus}`}>{t(locale, recognitionKey(item.cscseLookupStatus))}</span>
          <span class={`tag ${operatorListStatus(item) === "listed" ? "cscse-operator-listed" : "cscse-operator-absent"}`}>{t(locale, operatorListKey(operatorListStatus(item)))}</span>
        </div>
        <div class="actions">
          <a class="btn" href={withBase(`/${locale}/institutions/${item.id}`)}>{t(locale, "institutions.open")}</a>
          {#if href}
            <a class="btn external" href={href} rel="noopener noreferrer" target="_blank">
              {t(locale, "institutions.website")}
              <ExternalIcon />
              <span class="visually-hidden">{t(locale, "action.external")}</span>
            </a>
          {:else}
            <span class="muted">{t(locale, "institutions.noWebsite")}</span>
          {/if}
        </div>
      </article>
    {/each}
  </div>
{/if}
