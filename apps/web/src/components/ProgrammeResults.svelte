<script lang="ts">
  import {
    defaultFilterQuery,
    filterOfferings,
    primaryApplicationUrl,
  } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import {
    hostOf,
    ownershipLabel,
    recognitionKey,
    roundLabel,
    teachingLanguageLabel,
    text,
    formatTuition,
    windowRange,
    windowStatusLabel,
  } from "../lib/format";
  import { saveTeachingLanguage } from "../lib/storage";
  import type { CatalogSnapshot, FilterQuery, UiLocale } from "../lib/types";
  import SaveButton from "./SaveButton.svelte";
  import CompareButton from "./CompareButton.svelte";

  let { catalog, locale }: { catalog: CatalogSnapshot; locale: UiLocale } = $props();

  let query = $state(defaultFilterQuery());
  let now = $state(new Date());

  function readQuery(): FilterQuery {
    const params = new URLSearchParams(window.location.search);
    const teaching = params.get("teachingLanguage");
    return defaultFilterQuery({
      teachingLanguage: teaching === "en" || teaching === "cs" || teaching === "all" ? teaching : null,
      includeJointRequired: params.get("includeJoint") === "1",
      search: params.get("q") ?? "",
      degree: (params.get("degree") as FilterQuery["degree"]) || "all",
      city: params.get("city") || "all",
      ownership: (params.get("ownership") as FilterQuery["ownership"]) || "all",
      listedOnly: params.get("listedOnly") === "1",
      status: (params.get("status") as FilterQuery["status"]) || "all",
      orientation: (params.get("orientation") as FilterQuery["orientation"]) || "all",
      sort: params.get("sort") === "deadline" ? "deadline" : "default",
      page: Number(params.get("page") || "1") || 1,
    });
  }

  $effect(() => {
    query = readQuery();
    if (query.teachingLanguage) saveTeachingLanguage(query.teachingLanguage);
    const onPop = () => {
      query = readQuery();
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  });

  let result = $derived(filterOfferings(catalog, query, now, locale));
  let cities = $derived([...new Set(catalog.institutions.map((item) => item.city[locale]))].sort());
  let pageCount = $derived(Math.max(1, Math.ceil(result.total / query.pageSize)));

  function hrefWith(patch: Record<string, string | null>): string {
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(patch)) {
      if (value == null || value === "" || value === "all") params.delete(key);
      else params.set(key, value);
    }
    const qs = params.toString();
    return `${window.location.pathname}${qs ? `?${qs}` : ""}`;
  }
</script>

{#if query.teachingLanguage == null}
  <div class="empty card">
    <h2>{t(locale, "teaching.unset.notice")}</h2>
  </div>
{:else}
  <div class="layout-list">
    <details class="filter-drawer card" open>
      <summary>{t(locale, "filter.drawer")}</summary>
      <form class="filters" method="get">
        <input type="hidden" name="teachingLanguage" value={query.teachingLanguage} />
        <label>
          <span class="field-label">{t(locale, "search.placeholder")}</span>
          <input type="search" name="q" value={query.search} placeholder={t(locale, "search.placeholder")} />
        </label>
        <label class="checkbox-row">
          <input type="checkbox" name="includeJoint" value="1" checked={query.includeJointRequired} />
          {t(locale, "teaching.joint")}
        </label>
        <label>
          {t(locale, "filter.degree")}
          <select name="degree">
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="bachelor" selected={query.degree === "bachelor"}>{t(locale, "degree.bachelor")}</option>
            <option value="master" selected={query.degree === "master"}>{t(locale, "degree.master")}</option>
            <option value="doctorate" selected={query.degree === "doctorate"}>{t(locale, "degree.doctorate")}</option>
          </select>
        </label>
        <label>
          {t(locale, "filter.city")}
          <select name="city">
            <option value="all">{t(locale, "filter.all")}</option>
            {#each cities as city}
              <option value={city} selected={query.city === city}>{city}</option>
            {/each}
          </select>
        </label>
        <label>
          {t(locale, "filter.ownership")}
          <select name="ownership">
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="public" selected={query.ownership === "public"}>{t(locale, "institution.public")}</option>
            <option value="private" selected={query.ownership === "private"}>{t(locale, "institution.private")}</option>
            <option value="state" selected={query.ownership === "state"}>{t(locale, "institution.state")}</option>
            <option value="unknown" selected={query.ownership === "unknown"}>{t(locale, "institution.unknown")}</option>
          </select>
        </label>
        <label class="checkbox-row">
          <input type="checkbox" name="listedOnly" value="1" checked={query.listedOnly} />
          {t(locale, "filter.recognition.listedOnly")}
        </label>
        <label>
          {t(locale, "filter.status")}
          <select name="status">
            <option value="all">{t(locale, "filter.all")}</option>
            <option value="open" selected={query.status === "open"}>{t(locale, "status.open")}</option>
            <option value="upcoming" selected={query.status === "upcoming"}>{t(locale, "status.upcoming")}</option>
            <option value="closed" selected={query.status === "closed"}>{t(locale, "status.closed")}</option>
          </select>
        </label>
        <label>
          {t(locale, "sort.default")}
          <select name="sort">
            <option value="default" selected={query.sort === "default"}>{t(locale, "sort.default")}</option>
            <option value="deadline" selected={query.sort === "deadline"}>{t(locale, "sort.deadline")}</option>
          </select>
        </label>
        <button class="btn primary" type="submit">{t(locale, "filter.apply")}</button>
        <a class="btn" href={`/${locale}/programmes?teachingLanguage=${query.teachingLanguage}`}>{t(locale, "filter.clear")}</a>
      </form>
    </details>

    <div>
      <div class="results-head">
        <p>
          {#if query.teachingLanguage === "en"}{t(locale, "teaching.selected.en")}
          {:else if query.teachingLanguage === "cs"}{t(locale, "teaching.selected.cs")}
          {:else}{t(locale, "teaching.selected.all")}{/if}
          · {t(locale, "filter.count", { n: result.total })}
        </p>
        <a href={`/${locale}/`}>{t(locale, "teaching.change")}</a>
      </div>

      {#if result.total === 0}
        <div class="empty card">
          <h2>{t(locale, "empty.title")}</h2>
          <p>{t(locale, "empty.help")}</p>
        </div>
      {:else}
        <div class="card-grid">
          {#each result.page as view}
            {@const applyUrl = primaryApplicationUrl(view.summary, view.offering.applicationUrl)}
            {@const current = view.summary.current[0]}
            <article class="card">
              <p class="muted">{text(view.institution.displayName, locale)} · {text(view.institution.city, locale)}</p>
              <h3>
                <a href={`/${locale}/programmes/${view.offering.id}`}>{text(view.offering.title, locale)}</a>
              </h3>
              <div class="tags">
                <span class="tag">{teachingLanguageLabel(view.offering.teachingLanguages, view.offering.languageMode, locale)}</span>
                <span class="tag">{t(locale, `degree.${view.offering.degree === "unknown" ? "master" : view.offering.degree}`)}</span>
                {#if view.offering.durationSemesters}
                  <span class="tag">{t(locale, "detail.semesters", { n: view.offering.durationSemesters })}</span>
                {/if}
                <span class="tag">{t(locale, "detail.tuition")}：{formatTuition(view.offering.tuition, locale)}</span>
                <span class={`tag ownership-${view.institution.ownership}`}>{ownershipLabel(view.institution.ownership, locale)}</span>
                <span class={`tag cscse-${view.institution.cscseReference.lookupStatus}`}>{t(locale, recognitionKey(view.institution.cscseReference.lookupStatus))}</span>
                <span class={`tag status-${view.summary.opportunityStatus}`}>{windowStatusLabel(view.summary.opportunityStatus, locale)}</span>
              </div>
              {#if current}
                <p>
                  <strong>{roundLabel(current, locale)}</strong>
                  · {windowRange(current, locale)}
                </p>
              {:else}
                <p>{t(locale, "application.opensUnknown")} — {t(locale, "status.unknown")}</p>
              {/if}
              {#each view.offering.additionalLanguageRequirements as extra}
                {#if extra.requirement === "required"}
                  <p class="notice">{extra.note ? text(extra.note, locale) : t(locale, "teaching.additional")}</p>
                {/if}
              {/each}
              {#each view.institution.cscseReference.notices.filter((item) => item.active) as notice}
                <p class="notice">{t(locale, "recognition.notice")}：{text(notice.text, locale)}</p>
              {/each}
              <div class="actions">
                {#if applyUrl && view.summary.opportunityStatus === "open"}
                  <a class="btn primary" href={applyUrl} rel="noopener noreferrer" target="_blank">
                    {t(locale, "action.official")}
                    <span class="muted">({hostOf(applyUrl)} · {t(locale, "action.external")})</span>
                  </a>
                {/if}
                <a class="btn" href={`/${locale}/programmes/${view.offering.id}`}>{t(locale, "action.siteInterpretation")}</a>
                <SaveButton {locale} id={`offering:${view.offering.id}`} />
                <CompareButton {locale} id={`offering:${view.offering.id}`} />
              </div>
              <p class="disclaimer">{t(locale, "detail.notSubmitted")}</p>
            </article>
          {/each}
        </div>
        {#if pageCount > 1}
          <p class="actions">
            {#if query.page > 1}
              <a class="btn" href={hrefWith({ page: String(query.page - 1) })}>{t(locale, "pagination.prev")}</a>
            {/if}
            <span>{t(locale, "pagination.page", { n: query.page })}</span>
            {#if query.page < pageCount}
              <a class="btn" href={hrefWith({ page: String(query.page + 1) })}>{t(locale, "pagination.next")}</a>
            {/if}
          </p>
        {/if}
      {/if}
    </div>
  </div>
{/if}
