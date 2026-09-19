<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import { subscribeNow } from "../lib/clock";
  import { isPublicJob, jobOpportunityClosed, jobTrackOf, officialJobHref, summarizeWindows } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import { hostOf, text } from "../lib/format";
  import { applySafetyToJob, applySafetyToWindow, subscribeSafetyOverlay, type SafetyOverlay } from "../lib/safetyStatus";
  import type { ApplicationWindow, ResearchJob, UiLocale } from "../lib/types";
  import ExternalIcon from "./ExternalIcon.svelte";

  let {
    locale,
    jobs,
    windows,
    initialOverlay = null,
  }: {
    locale: UiLocale;
    jobs: ResearchJob[];
    windows: ApplicationWindow[];
    initialOverlay?: SafetyOverlay | null;
  } = $props();

  let overlay = $state<SafetyOverlay | null>(initialOverlay);
  let now = $state(new Date());
  let liveJobs = $derived(jobs.map((job) => applySafetyToJob(job, overlay)));
  let liveWindows = $derived(windows.map((window) => applySafetyToWindow(window, overlay)));
  let visible = $derived(
    liveJobs
      .map((job) => {
        const jobWindows = liveWindows.filter((window) => window.ownerId === job.id);
        const summary = summarizeWindows(jobWindows, now, jobOpportunityClosed(job));
        return { job, summary };
      })
      .filter((view) => isPublicJob(view.job, view.summary)),
  );

  $effect(() => {
    return subscribeNow((value) => {
      now = value;
    }, () => liveWindows);
  });

  $effect(() => {
    return subscribeSafetyOverlay((value, meta) => {
      if (!meta.stale && value) overlay = value;
    });
  });
</script>

{#if visible.length > 0}
  <h2>{t(locale, "nav.research")}</h2>
  <ul>
    {#each visible as view (view.job.id)}
      {@const officialUrl = officialJobHref(view.job)}
      <li>
        <a href={withBase(`/${locale}/research-jobs/${view.job.id}`)}>{text(view.job.title, locale)}</a>
        {" · "}
        {t(locale, `jobs.track.${jobTrackOf(view.job)}`)}
        {#if officialUrl}
          {" · "}
          <a class="external" href={officialUrl} rel="noopener noreferrer" target="_blank" data-official-detail>
            {t(locale, "action.officialVacancyDescription")}
            <ExternalIcon />
            <span class="muted">({hostOf(officialUrl)})</span>
            <span class="visually-hidden">{t(locale, "action.external")}</span>
          </a>
        {/if}
      </li>
    {/each}
  </ul>
{/if}
