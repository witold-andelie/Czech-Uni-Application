<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import {
    canApply,
    defaultFilterQuery,
    filterOfferings,
    filterQueryFromSearch,
    officialOfferingHref,
    primaryApplicationUrl,
    safeHttpUrl,
    searchFromFilter,
    uniqueCityOptions,
    uniqueFieldOptions,
    uniqueInstitutionOptions,
  } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import {
    degreeKey,
    extraContextKey,
    fieldSep,
    dataClassKey,
    formatTracerTuition,
    languageName,
    ownershipLabel,
    recognitionKey,
    roundLabel,
    teachingLanguageLabel,
    text,
    windowRange,
    windowStatusLabel,
  } from "../lib/format";
  import { saveTeachingLanguage } from "../lib/storage";
  import { subscribeNow } from "../lib/clock";
  import { fetchInventoryCatalog, loadCatalogShell } from "../lib/loadCatalogClient";
  import { findApplyPortal } from "../lib/loadApplyPortals";
  import type { CatalogSnapshot, FilterQuery, UiLocale } from "../lib/types";
  import { onMount } from "svelte";
  import OfficialLink from "./OfficialLink.svelte";
  import FilterDrawer from "./FilterDrawer.svelte";

  let { locale }: { locale: UiLocale } = $props();

  let catalog = $state<CatalogSnapshot>(loadCatalogShell());
  let inventoryLoading = $state(true);
  let inventoryError = $state(false);
  let query = $state<FilterQuery>(filterQueryFromSearch(""));
  let now = $state(new Date());
  let sheetOpen = $state(false);
  let inventoryGeneration = $state(0);

  function applySearch(search: string) {
    const parsed = filterQueryFromSearch(search);
    query = parsed;
    if (parsed.teachingLanguage) saveTeachingLanguage(parsed.teachingLanguage);
  }

  onMount(() => {
    applySearch(window.location.search);
    const onPop = () => applySearch(window.location.search);
    window.addEventListener("popstate", onPop);
    const stopClock = subscribeNow((value) => {
      now = value;
    }, () => catalog.windows);
    return () => {
      window.removeEventListener("popstate", onPop);
      stopClock();
    };
  });

  $effect(() => {
    const generation = inventoryGeneration;
    void generation;
    let cancelled = false;
    inventoryLoading = true;
    inventoryError = false;
    fetchInventoryCatalog()
      .then((full) => {
        if (!cancelled) {
          catalog = full;
          inventoryLoading = false;
        }
      })
      .catch(() => {
        if (!cancelled) {
          inventoryLoading = false;
          inventoryError = true;
        }
      });
    return () => {
      cancelled = true;
    };
  });

  let result = $derived(filterOfferings(catalog, query, now, locale));
  let fields = $derived(uniqueFieldOptions(catalog, locale));
  let cities = $derived(uniqueCityOptions(catalog, locale));
  let schools = $derived(uniqueInstitutionOptions(catalog, locale, query.city));
  let pageCount = $derived(Math.max(1, Math.ceil(result.total / query.pageSize)));

  function syncUrl(mode: "replace" | "push") {
    if (query.teachingLanguage) saveTeachingLanguage(query.teachingLanguage);
    const href = `${window.location.pathname}${searchFromFilter(query)}`;
    if (mode === "push") history.pushState(null, "", href);
    else history.replaceState(null, "", href);
    window.dispatchEvent(new Event("listquerychange"));
    if (query.teachingLanguage) document.documentElement.setAttribute("data-teaching", query.teachingLanguage);
    else document.documentElement.removeAttribute("data-teaching");
  }

  function patchQuery(patch: Partial<FilterQuery>, mode: "replace" | "push" = "replace") {
    const next = { ...query, ...patch };
    if (patch.page == null) next.page = 1;
    query = next;
    syncUrl(mode);
  }

  function toggleField(value: string) {
    patchQuery({ field: query.field === value ? "all" : value });
  }

  function toggleCity(value: string) {
    const city = query.city === value ? "all" : value;
    const allowed = uniqueInstitutionOptions(catalog, locale, city);
    const institutionId =
      query.institutionId && query.institutionId !== "all" && allowed.some((item) => item.value === query.institutionId)
        ? query.institutionId
        : "all";
    patchQuery({ city, institutionId });
  }

  function toggleInstitution(value: string) {
    patchQuery({ institutionId: query.institutionId === value ? "all" : value });
  }

  function clearFilters() {
    query = defaultFilterQuery({ teachingLanguage: query.teachingLanguage });
    syncUrl("replace");
  }

  function onSubmit(event: SubmitEvent) {
    event.preventDefault();
    syncUrl("replace");
  }
</script>

{#if query.teachingLanguage != null}
  <div class="layout-list" class:sheet-open={sheetOpen}>
    <FilterDrawer bind:open={sheetOpen} {locale} labelledBy="programme-filter-title" resultCount={result.total} id="programme-filter-drawer" onsubmit={onSubmit}>
        <p class="disclaimer">{t(locale, "filter.live")}</p>
        <div class="chip-group">
          <span class="field-label">{t(locale, "filter.field")}</span>
          <div class="chip-row" role="group" aria-label={t(locale, "filter.field")}>
            <button type="button" class="chip" aria-pressed={!query.field || query.field === "all"} onclick={() => patchQuery({ field: "all" })}>
              {t(locale, "filter.all")}
            </button>
            {#each fields as field}
              <button type="button" class="chip" aria-pressed={query.field === field.value} onclick={() => toggleField(field.value)}>
                {field.label}
              </button>
            {/each}
          </div>
        </div>
        <div class="chip-group">
          <span class="field-label">{t(locale, "filter.city")}</span>
          <div class="chip-row" role="group" aria-label={t(locale, "filter.city")}>
            <button type="button" class="chip" aria-pressed={query.city === "all"} onclick={() => patchQuery({ city: "all", institutionId: query.institutionId })}>
              {t(locale, "filter.all")}
            </button>
            {#each cities as city}
              <button type="button" class="chip" aria-pressed={query.city === city.value} onclick={() => toggleCity(city.value)}>
                {city.label}
              </button>
            {/each}
          </div>
        </div>
        <div class="chip-group">
          <span class="field-label">{t(locale, "filter.institution")}</span>
          <div class="chip-row chip-row-scroll" role="group" aria-label={t(locale, "filter.institution")}>
            <button type="button" class="chip" aria-pressed={!query.institutionId || query.institutionId === "all"} onclick={() => patchQuery({ institutionId: "all" })}>
              {t(locale, "filter.all")}
            </button>
            {#each schools as school}
              <button type="button" class="chip" aria-pressed={query.institutionId === school.value} onclick={() => toggleInstitution(school.value)}>
                {school.label}
              </button>
            {/each}
          </div>
        </div>
        <label class="checkbox-row">
          <input type="checkbox" bind:checked={query.includeJointRequired} onchange={() => patchQuery({})} />
          {t(locale, "teaching.joint")}
        </label>
        <label>
          {t(locale, "filter.degree")}
          <select bind:value={query.degree} onchange={() => patchQuery({})}>
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="bachelor">{t(locale, "degree.bachelor")}</option>
            <option value="master">{t(locale, "degree.master")}</option>
            <option value="doctorate">{t(locale, "degree.doctorate")}</option>
          </select>
        </label>
        <label>
          {t(locale, "filter.orientation")}
          <select bind:value={query.orientation} onchange={() => patchQuery({})}>
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="research">{t(locale, "orientation.research")}</option>
            <option value="applied">{t(locale, "orientation.applied")} ({t(locale, "orientation.applied.unverified")})</option>
          </select>
        </label>
        <label>
          {t(locale, "filter.ownership")}
          <select bind:value={query.ownership} onchange={() => patchQuery({})}>
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="public">{t(locale, "institution.public")}</option>
            <option value="private">{t(locale, "institution.private")}</option>
            <option value="unknown">{t(locale, "institution.unknown")}</option>
          </select>
        </label>
        <label class="checkbox-row">
          <input type="checkbox" bind:checked={query.listedOnly} onchange={() => patchQuery({})} />
          {t(locale, "filter.recognition.listedOnly")}
        </label>
        <label>
          {t(locale, "filter.status")}
          <select bind:value={query.status} onchange={() => patchQuery({})}>
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="open">{t(locale, "status.open")}</option>
            <option value="conditional">{t(locale, "status.conditional")}</option>
            <option value="upcoming">{t(locale, "status.upcoming")}</option>
            <option value="closed">{t(locale, "status.closed")}</option>
          </select>
        </label>
        <label>
          {t(locale, "sort.default")}
          <select bind:value={query.sort} onchange={() => patchQuery({})}>
            <option value="default">{t(locale, "sort.default")}</option>
            <option value="deadline">{t(locale, "sort.deadline")}</option>
          </select>
        </label>
        <button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button>
    </FilterDrawer>

    <div>
      <button
        type="button"
        class="btn primary filter-open-mobile"
        aria-expanded={sheetOpen}
        aria-controls="programme-filter-drawer"
        onclick={() => (sheetOpen = true)}
      >
        {t(locale, "filter.drawer")} · {t(locale, "filter.count", { n: result.total })}
      </button>
      <div class="results-head">
        <p>
          {#if query.teachingLanguage === "en"}{t(locale, "teaching.selected.en")}
          {:else if query.teachingLanguage === "cs"}{t(locale, "teaching.selected.cs")}
          {:else}{t(locale, "teaching.selected.all")}{/if}
          · {t(locale, "filter.count", { n: result.total })}
          {#if result.total > 0}
            · {t(locale, "pagination.pageOf", { n: query.page, total: pageCount })}
          {/if}
          {#if inventoryLoading}
            · {t(locale, "inventory.loading")}
          {/if}
          {#if inventoryError}
            · {t(locale, "error.partialCatalog")}
          {/if}
        </p>
        <a href={withBase(`/${locale}/programmes`)}>{t(locale, "teaching.change")}</a>
      </div>

      {#if inventoryError}
        <div class="empty card">
          <h2>{t(locale, "error.loadFailed")}</h2>
          <p>{t(locale, "error.partialCatalog")}</p>
          <p>
            <button class="btn" type="button" onclick={() => (inventoryGeneration += 1)}>{t(locale, "error.retry")}</button>
          </p>
        </div>
      {:else if result.total === 0}
        <div class="empty card">
          {#if query.orientation === "applied"}
            <h2>{t(locale, "orientation.applied.statusTitle")}</h2>
            <p>{t(locale, "orientation.applied.statusHelp")}</p>
          {:else}
            <h2>{t(locale, "empty.title")}</h2>
            <p>{t(locale, "empty.help")}</p>
          {/if}
          <p>
            <button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button>
          </p>
        </div>
      {:else}
        <div class="card-grid">
          {#each result.page as view}
            {@const applyUrl = safeHttpUrl(primaryApplicationUrl(view.summary, view.offering.applicationUrl))}
            {@const officialUrl = officialOfferingHref(view.offering, view.institution, findApplyPortal(view.institution.id))}
            {@const current = view.summary.current[0]}
            <article class="card result-card">
              <div class="card-head">
                <p class="muted">{text(view.institution.displayName, locale)} · {text(view.institution.city, locale)}</p>
                <span class={`status-badge status-${view.summary.opportunityStatus}`}>{windowStatusLabel(view.summary.opportunityStatus, locale)}</span>
              </div>
              <h3>
                <a href={withBase(`/${locale}/programmes/${view.offering.id}`)}>{text(view.offering.title, locale)}</a>
              </h3>
              {#if text(view.offering.field, locale) && text(view.offering.field, locale) !== text(view.offering.title, locale)}
                <p class="muted">{t(locale, "inventory.faculty")}{fieldSep(locale)}{text(view.offering.field, locale)}</p>
              {/if}
              <div class="card-metrics">
                <div>
                  <p class="metric-label">{t(locale, "detail.tuition")}</p>
                  {#each formatTracerTuition(view.offering.tuition, locale) as line}
                    <p class="metric-value">{line}</p>
                  {/each}
                </div>
                <div>
                  <p class="metric-label">{t(locale, "detail.duration")}</p>
                  <p class="metric-value">
                    {view.offering.durationSemesters
                      ? t(locale, "detail.semesters", { n: view.offering.durationSemesters })
                      : t(locale, "status.unknown")}
                  </p>
                </div>
              </div>
              <div class="tags tags-secondary">
                <span class="tag">{teachingLanguageLabel(view.offering.teachingLanguages, view.offering.languageMode, locale)}</span>
                <span class="tag">{t(locale, degreeKey(view.offering.degree))}</span>
                <span class={`tag ownership-${view.institution.ownership}`}>{ownershipLabel(view.institution.ownership, locale)}</span>
                <span class={`tag cscse-${view.institution.cscseReference.lookupStatus}`}>{t(locale, recognitionKey(view.institution.cscseReference.lookupStatus))}</span>
                <span class="tag">{t(locale, dataClassKey(view.offering.dataClass))}</span>
              </div>
              {#if current}
                <p>
                  <strong>{roundLabel(current, locale)}</strong>
                  · {windowRange(current, locale)}
                </p>
              {:else}
                <p>{t(locale, "application.opensUnknown")}</p>
              {/if}
              {#each view.offering.additionalLanguageRequirements as extra}
                {#if extra.requirement === "required"}
                  <p class="notice">{extra.note ? text(extra.note, locale) : `${t(locale, extraContextKey(extra.context))}${fieldSep(locale)}${languageName(extra.language, locale)}`}</p>
                {/if}
              {/each}
              {#each view.institution.cscseReference.notices.filter((item) => item.active) as notice}
                <p class="notice">{t(locale, "recognition.notice")}{fieldSep(locale)}{text(notice.text, locale)}</p>
              {/each}
              <div class="actions">
                {#if applyUrl && canApply(view.summary)}
                  <OfficialLink {locale} href={applyUrl} label={t(locale, "action.official")} primary />
                  {#if officialUrl && officialUrl !== applyUrl}
                    <OfficialLink {locale} href={officialUrl} />
                  {/if}
                {:else if officialUrl}
                  <OfficialLink {locale} href={officialUrl} />
                {/if}
                <a class="btn" href={withBase(`/${locale}/programmes/${view.offering.id}`)}>{t(locale, "action.siteInterpretation")}</a>
              </div>
              <p class="disclaimer">{t(locale, "detail.notSubmitted")}</p>
            </article>
          {/each}
        </div>
        {#if pageCount > 1}
          <p class="actions">
            {#if query.page > 1}
              <button class="btn" type="button" onclick={() => patchQuery({ page: query.page - 1 }, "push")}>{t(locale, "pagination.prev")}</button>
            {/if}
            <span>{t(locale, "pagination.pageOf", { n: query.page, total: pageCount })}</span>
            {#if query.page < pageCount}
              <button class="btn" type="button" onclick={() => patchQuery({ page: query.page + 1 }, "push")}>{t(locale, "pagination.next")}</button>
            {/if}
          </p>
        {/if}
      {/if}
    </div>
  </div>
{/if}
