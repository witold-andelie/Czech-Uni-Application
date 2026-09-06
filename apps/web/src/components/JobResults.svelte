<script lang="ts">
  import { defaultJobFilterQuery, filterJobs, primaryApplicationUrl } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import { hostOf, roundLabel, text, windowRange, windowStatusLabel } from "../lib/format";
  import type { CatalogSnapshot, JobFilterQuery, UiLocale } from "../lib/types";
  import SaveButton from "./SaveButton.svelte";

  let { catalog, locale }: { catalog: CatalogSnapshot; locale: UiLocale } = $props();
  let query = $state(defaultJobFilterQuery());
  let now = $state(new Date());

  function readQuery(): JobFilterQuery {
    const params = new URLSearchParams(window.location.search);
    const applied = params.get("applied") === "1";
    return defaultJobFilterQuery({
      masterEligible: applied ? params.get("masterEligible") === "1" : true,
      doctoralEnrollment: (params.get("phd") as JobFilterQuery["doctoralEnrollment"]) || "all",
      workingLanguage: params.get("lang") || "all",
      search: params.get("q") ?? "",
      page: Number(params.get("page") || "1") || 1,
    });
  }

  $effect(() => {
    query = readQuery();
  });

  let result = $derived(filterJobs(catalog, query, now, locale));
</script>

<div class="layout-list">
  <form class="filters card" method="get">
    <input type="hidden" name="applied" value="1" />
    <label class="checkbox-row">
      <input type="checkbox" name="masterEligible" value="1" checked={query.masterEligible} />
      {t(locale, "jobs.master")}
    </label>
    <p class="disclaimer">{t(locale, "jobs.postdocExcluded")}</p>
    <label>
      {t(locale, "jobs.phd")}
      <select name="phd">
        <option value="all">{t(locale, "filter.all")}</option>
        <option value="not_required" selected={query.doctoralEnrollment === "not_required"}>{t(locale, "jobs.phd.no")}</option>
        <option value="optional" selected={query.doctoralEnrollment === "optional"}>{t(locale, "jobs.phd.optional")}</option>
        <option value="required" selected={query.doctoralEnrollment === "required"}>{t(locale, "jobs.phd.required")}</option>
        <option value="unspecified" selected={query.doctoralEnrollment === "unspecified"}>{t(locale, "jobs.phd.unknown")}</option>
      </select>
    </label>
    <label>
      {t(locale, "jobs.language")}
      <select name="lang">
        <option value="all">{t(locale, "filter.all")}</option>
        <option value="en" selected={query.workingLanguage === "en"}>{t(locale, "lang.en")}</option>
        <option value="cs" selected={query.workingLanguage === "cs"}>{t(locale, "lang.cs")}</option>
      </select>
    </label>
    <label>
      {t(locale, "search.placeholder")}
      <input type="search" name="q" value={query.search} />
    </label>
    <button class="btn primary" type="submit">{t(locale, "filter.apply")}</button>
  </form>

  <div>
    <p class="muted">{t(locale, "filter.count", { n: result.total })}</p>
    {#if result.total === 0}
      <div class="empty card">
        <h2>{t(locale, "empty.title")}</h2>
        <p>{t(locale, "empty.help")}</p>
      </div>
    {:else}
      <div class="card-grid">
        {#each result.page as view}
          {@const applyUrl = primaryApplicationUrl(view.summary, view.job.applicationUrl)}
          {@const current = view.summary.current[0]}
          {@const applyLabel = view.job.applicationMethod === "official_instructions" ? t(locale, "action.officialInstructions") : t(locale, "action.applyNow")}
          <article class="card">
            <p class="muted">{text(view.employer.displayName, locale)} · {text(view.job.city, locale)}</p>
            <h3>
              {#if applyUrl && view.summary.opportunityStatus !== "closed"}
                <a href={applyUrl} rel="noopener noreferrer" target="_blank">{text(view.job.title, locale)}</a>
              {:else}
                {text(view.job.title, locale)}
              {/if}
            </h3>
            <div class="tags">
              <span class="tag">{t(locale, "jobs.master")}</span>
              <span class="tag">{t(locale, `jobs.phd.${view.job.doctoralEnrollment === "not_required" ? "no" : view.job.doctoralEnrollment === "unspecified" ? "unknown" : view.job.doctoralEnrollment}`)}</span>
              <span class="tag">{t(locale, "jobs.language")}：{view.job.workingLanguages.join(", ")}</span>
              <span class={`tag status-${view.summary.opportunityStatus}`}>{windowStatusLabel(view.summary.opportunityStatus, locale)}</span>
              {#if view.job.paidStatus === "confirmed" && view.job.salary.amount == null}
                <span class="tag">{t(locale, "jobs.salaryUnknown")}</span>
              {:else if view.job.salary.amount != null}
                <span class="tag">{t(locale, "jobs.gross")} {view.job.salary.amount} {view.job.salary.currency}</span>
              {/if}
            </div>
            {#if current}
              <p><strong>{roundLabel(current, locale)}</strong> · {windowRange(current, locale)}</p>
            {/if}
            <div class="actions">
              {#if applyUrl && view.summary.opportunityStatus === "open"}
                <a class="btn primary" href={applyUrl} rel="noopener noreferrer" target="_blank">
                  {applyLabel}
                  <span class="muted">({hostOf(applyUrl)})</span>
                </a>
              {/if}
              <a class="btn" href={`/${locale}/research-jobs/${view.job.id}`}>{t(locale, "action.siteInterpretation")}</a>
              <SaveButton {locale} id={`job:${view.job.id}`} />
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>
</div>
