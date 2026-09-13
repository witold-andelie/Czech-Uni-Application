<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import {
    canApply,
    defaultJobFilterQuery,
    isMasterEligible,
    jobFilterFromSearch,
    jobTrackOf,
    filterJobs,
    officialJobHref,
    primaryApplicationUrl,
    safeHttpUrl,
    searchFromJobFilter,
  } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import { dataClassKey, fieldSep, formatDate, formatSalary, hostOf, jobSourceTitle, languageName, roundLabel, salaryTaxKey, text, windowRange, windowStatusLabel } from "../lib/format";
  import { subscribeNow } from "../lib/clock";
  import { loadCatalogShell } from "../lib/loadCatalogClient";
  import { applySafetyOverlay, subscribeSafetyOverlay, type SafetyOverlay } from "../lib/safetyStatus";
  import type { JobFilterQuery, JobTrackFilter, UiLocale } from "../lib/types";
  import { onMount } from "svelte";
  import ExternalIcon from "./ExternalIcon.svelte";
  import OfficialLink from "./OfficialLink.svelte";
  import FilterDrawer from "./FilterDrawer.svelte";

  let { locale, initialOverlay = null }: { locale: UiLocale; initialOverlay?: SafetyOverlay | null } = $props();

  const baseCatalog = loadCatalogShell();
  let overlay = $state<SafetyOverlay | null>(initialOverlay);
  let overlayStale = $state(false);
  let catalog = $derived(applySafetyOverlay(baseCatalog, overlay));
  let query = $state<JobFilterQuery>(jobFilterFromSearch(""));
  let now = $state(new Date());
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let sheetOpen = $state(false);

  onMount(() => {
    query = jobFilterFromSearch(window.location.search);
    const onPop = () => {
      query = jobFilterFromSearch(window.location.search);
    };
    window.addEventListener("popstate", onPop);
    const stopClock = subscribeNow((value) => {
      now = value;
    }, () => catalog.windows);
    const stopSafety = subscribeSafetyOverlay((value, meta) => {
      overlay = value ?? overlay;
      overlayStale = meta.stale;
    });
    return () => {
      window.removeEventListener("popstate", onPop);
      if (searchTimer) clearTimeout(searchTimer);
      stopClock();
      stopSafety();
    };
  });

  let result = $derived(filterJobs(catalog, query, now, locale));
  let pageCount = $derived(Math.max(1, Math.ceil(result.total / query.pageSize)));

  function syncUrl(mode: "replace" | "push") {
    const href = `${window.location.pathname}${searchFromJobFilter(query)}`;
    if (mode === "push") history.pushState(null, "", href);
    else history.replaceState(null, "", href);
    window.dispatchEvent(new Event("listquerychange"));
  }

  function patchQuery(patch: Partial<JobFilterQuery>, mode: "replace" | "push" = "replace") {
    const next = { ...query, ...patch };
    if (patch.page == null) next.page = 1;
    query = next;
    syncUrl(mode);
  }

  function onSearchInput(value: string) {
    query.search = value;
    query.page = 1;
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => syncUrl("replace"), 300);
  }

  function clearFilters() {
    query = defaultJobFilterQuery();
    history.replaceState(null, "", window.location.pathname);
    window.dispatchEvent(new Event("listquerychange"));
  }

  function onSubmit(event: SubmitEvent) {
    event.preventDefault();
    if (searchTimer) clearTimeout(searchTimer);
    syncUrl("replace");
  }
</script>

<div class="layout-list" class:sheet-open={sheetOpen}>
  {#if overlayStale}
    <p class="notice">{t(locale, "jobs.safetyStale")}</p>
  {/if}
  <FilterDrawer bind:open={sheetOpen} {locale} labelledBy="job-filter-title" resultCount={result.total} id="job-filter-drawer" onsubmit={onSubmit}>
    <p class="disclaimer">{t(locale, "filter.live")}</p>
    <div class="chip-row" role="group" aria-label={t(locale, "jobs.track")}>
      {#each [["master_eligible", "jobs.master"], ["assistant", "jobs.track.assistant"], ["post_master", "jobs.track.post_master"], ["postdoc", "jobs.track.postdoc"], ["all", "jobs.track.all"]] as [value, key]}
        <button
          type="button"
          class="chip"
          aria-pressed={query.track === value}
          onclick={() => patchQuery({ track: value as JobTrackFilter, masterEligible: value === "master_eligible" })}
        >
          {t(locale, key)}
        </button>
      {/each}
    </div>
    <p class="disclaimer">{t(locale, "jobs.postdocExcluded")}</p>
    <button
      type="button"
      class="chip"
      aria-pressed={query.fundedDoctoral}
      onclick={() => patchQuery({ fundedDoctoral: !query.fundedDoctoral })}
    >
      {t(locale, "jobs.fundedDoctoral")}
    </button>
    <p class="disclaimer">{t(locale, "jobs.fundedDoctoralHint")}</p>
    <label>
      {t(locale, "jobs.phd")}
      <select bind:value={query.doctoralEnrollment} onchange={() => patchQuery({})}>
        <option value="all">{t(locale, "filter.all")}</option>
        <option value="not_required">{t(locale, "jobs.phd.no")}</option>
        <option value="optional">{t(locale, "jobs.phd.optional")}</option>
        <option value="required">{t(locale, "jobs.phd.required")}</option>
        <option value="unspecified">{t(locale, "jobs.phd.unknown")}</option>
      </select>
    </label>
    <label>
      {t(locale, "jobs.language")}
      <select bind:value={query.workingLanguage} onchange={() => patchQuery({})}>
        <option value="all">{t(locale, "filter.all")}</option>
        <option value="en">{t(locale, "lang.en")}</option>
        <option value="cs">{t(locale, "lang.cs")}</option>
        <option value="und">{t(locale, "lang.und")}</option>
      </select>
    </label>
    <label>
      {t(locale, "jobs.search.placeholder")}
      <input type="search" name="q" value={query.search} oninput={(event) => onSearchInput(event.currentTarget.value)} />
    </label>
    <button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button>
  </FilterDrawer>

  <div>
    <button
      type="button"
      class="btn primary filter-open-mobile"
      aria-expanded={sheetOpen}
      aria-controls="job-filter-drawer"
      onclick={() => (sheetOpen = true)}
    >
      {t(locale, "filter.drawer")} · {t(locale, "filter.count", { n: result.total })}
    </button>
    <p class="muted">
      {t(locale, "filter.count", { n: result.total })}
      {#if result.total > 0}
        · {t(locale, "pagination.pageOf", { n: query.page, total: pageCount })}
      {/if}
    </p>
    {#if result.total === 0}
      <div class="empty card">
        <h2>{t(locale, "empty.title")}</h2>
        <p>{t(locale, "jobs.empty.help")}</p>
        <p><button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button></p>
      </div>
    {:else}
      <div class="card-grid">
        {#each result.page as view}
          {@const applyUrl = safeHttpUrl(primaryApplicationUrl(view.summary, view.job.applicationUrl))}
          {@const officialUrl = officialJobHref(view.job)}
          {@const current = view.summary.current[0]}
          {@const applyLabel = view.job.applicationMethod === "official_instructions" ? t(locale, "action.officialInstructions") : t(locale, "action.applyNow")}
          {@const master = isMasterEligible(view.job)}
          <article class="card result-card">
            <div class="card-head">
              <p class="muted">{text(view.employer.displayName, locale)}{view.job.city ? ` · ${text(view.job.city, locale)}` : ''}</p>
              <span class={`status-badge status-${view.summary.opportunityStatus}`}>{windowStatusLabel(view.summary.opportunityStatus, locale)}</span>
            </div>
            <h3>
              {#if officialUrl}
                <a class="external" href={officialUrl} rel="noopener noreferrer" target="_blank">
                  {text(view.job.title, locale)}
                  <ExternalIcon />
                  <span class="visually-hidden">{t(locale, "action.external")}</span>
                </a>
              {:else}
                {text(view.job.title, locale)}
              {/if}
            </h3>
            {#if locale === "zh-CN" && view.job.title.en && view.job.title.en !== view.job.title["zh-CN"]}
              <p class="muted original-title" style="font-size: 0.9em; margin-top: -0.5rem; margin-bottom: 0.75rem;">
                {view.job.title.en}
              </p>
            {/if}
            <div class="card-metrics">
              <div>
                <p class="metric-label">{t(locale, salaryTaxKey(view.job.salary.tax) === "salary.tax.gross" ? "jobs.gross" : "jobs.salary")}</p>
                <p class="metric-value">
                  {#if view.job.paidStatus === "confirmed" && view.job.salary.amount == null}
                    {t(locale, "jobs.salaryUnknown")}
                  {:else if view.job.salary.amount != null}
                    {formatSalary(view.job.salary, locale)}
                  {:else}
                    {t(locale, "status.unknown")}
                  {/if}
                </p>
              </div>
              <div>
                <p class="metric-label">{t(locale, "jobs.language")}</p>
                <p class="metric-value">{view.job.workingLanguages.map((code) => languageName(code, locale)).join(", ")}</p>
              </div>
            </div>
            <div class="tags tags-secondary">
              {#if master}
                <span class="tag">{t(locale, "jobs.master")}</span>
              {:else}
                <span class="tag">{t(locale, "jobs.notMaster")}</span>
              {/if}
              <span class="tag">{t(locale, `jobs.phd.${view.job.doctoralEnrollment === "not_required" ? "no" : view.job.doctoralEnrollment === "unspecified" ? "unknown" : view.job.doctoralEnrollment}`)}</span>
              {#if view.job.salary.basisFte != null}
                <span class="tag">{t(locale, "jobs.fte")}{fieldSep(locale)}{view.job.salary.basisFte}</span>
              {/if}
              {#if view.job.employmentFte != null}
                <span class="tag">{t(locale, "jobs.workloadFte")}{fieldSep(locale)}{view.job.employmentFte}</span>
              {/if}
              {#if view.job.employmentStartsAt}
                <span class="tag">{t(locale, "jobs.employmentStart")}{fieldSep(locale)}{formatDate(view.job.employmentStartsAt, locale, "date")}</span>
              {/if}
              <span class="tag">{t(locale, `jobs.track.${jobTrackOf(view.job)}`)}</span>
            </div>
            {#if current}
              <p><strong>{roundLabel(current, locale)}</strong> · {windowRange(current, locale)}</p>
            {/if}
            <details class="job-tech-details" style="margin-top: 0.5rem; font-size: 0.85em;">
              <summary style="cursor: pointer; color: var(--color-text-muted, #666);">{t(locale, "jobs.dataDisclosure")}</summary>
              <div style="padding-top: 0.25rem; color: var(--color-text-muted, #666);">
                <p><strong>{t(locale, "jobs.sourceOriginal")}</strong>: {jobSourceTitle(view.job)}</p>
                {#if view.job.verifiedAt}
                  <p><strong>{t(locale, "jobs.verifiedDate")}</strong>: {view.job.verifiedAt}</p>
                {/if}
                <p><strong>{t(locale, "jobs.host")}</strong>: {hostOf(view.job.applicationUrl || view.job.sourceUrl)}</p>
              </div>
            </details>
            <div class="actions">
              {#if applyUrl && canApply(view.summary)}
                <OfficialLink {locale} href={applyUrl} label={applyLabel} primary />
                {#if officialUrl && officialUrl !== applyUrl}
                  <OfficialLink {locale} href={officialUrl} />
                {/if}
              {:else if officialUrl}
                <OfficialLink {locale} href={officialUrl} label={applyLabel} />
              {/if}
              <a class="btn" href={withBase(`/${locale}/research-jobs/${view.job.id}`)}>{t(locale, "action.siteInterpretation")}</a>
            </div>
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
