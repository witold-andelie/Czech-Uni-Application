<script lang="ts">
  import { subscribeNow } from "../lib/clock";
  import {
    canApply,
    evaluateWindow,
    primaryApplicationUrl,
    safeHttpUrl,
    summarizeWindows,
    windowCanApply,
  } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import { fieldSep, hostOf, roundLabel, text, windowRange, windowStatusLabel } from "../lib/format";
  import type { ApplicationWindow, UiLocale } from "../lib/types";
  import { applySafetyToWindow, overlayWholeClosed, subscribeSafetyOverlay, type SafetyOverlay } from "../lib/safetyStatus";
  import ExternalIcon from "./ExternalIcon.svelte";

  let {
    locale,
    windows,
    wholeClosed = false,
    fallbackUrl = null,
    applyLabel,
    noticeIsNotApplication = false,
    entityId = null,
    initialOverlay = null,
  }: {
    locale: UiLocale;
    windows: ApplicationWindow[];
    wholeClosed?: boolean;
    fallbackUrl?: string | null;
    applyLabel: string;
    noticeIsNotApplication?: boolean;
    entityId?: string | null;
    initialOverlay?: SafetyOverlay | null;
  } = $props();

  let overlay = $state<SafetyOverlay | null>(initialOverlay);
  let overlayStale = $state(false);
  let liveWholeClosed = $derived(wholeClosed || Boolean(entityId && overlayWholeClosed(overlay, entityId)));
  let liveWindows = $derived(windows.map((window) => applySafetyToWindow(window, overlay)));
  let now = $state(new Date());
  let summary = $derived(summarizeWindows(liveWindows, now, liveWholeClosed));
  let applyUrl = $derived(safeHttpUrl(primaryApplicationUrl(summary, fallbackUrl)));
  let officialFallback = $derived(safeHttpUrl(fallbackUrl));
  let current = $derived(summary.current[0]);

  $effect(() => {
    void liveWindows;
    return subscribeNow((value) => {
      now = value;
    }, () => liveWindows);
  });

  $effect(() => {
    if (!entityId) return;
    return subscribeSafetyOverlay((value, meta) => {
      overlayStale = meta.stale;
      if (value) overlay = value;
    });
  });
</script>

{#if overlayStale}
  <p class="notice">{t(locale, "jobs.safetyStale")}</p>
{/if}

<section class="summary-grid">
  <div class="panel">
    <p class="muted">{t(locale, "application.currentRound")}</p>
    <p>{windowStatusLabel(summary.opportunityStatus, locale)}</p>
    {#if current}
      <p>{roundLabel(current, locale)} · {windowRange(current, locale)}</p>
    {/if}
  </div>
</section>

<section class="panel">
  <h2>{t(locale, "application.timeline")}</h2>
  {#if liveWholeClosed}
    <div class="notice" style="margin-bottom: 1rem;">
      <p><strong>{t(locale, "application.opportunityClosed")}</strong></p>
      <p class="muted">{t(locale, "application.opportunityClosedHistory")}</p>
    </div>
  {/if}
  {#if liveWindows.length === 0}
    <p>{t(locale, "application.roundUnknown")}</p>
  {/if}
  {#each liveWindows as window}
    {@const rawState = evaluateWindow(window, now)}
    {@const state = liveWholeClosed ? "closed" : rawState}
    {@const href = safeHttpUrl(window.applicationUrl)}
    <article>
      <h3>{roundLabel(window, locale)} {window.roundLabelOriginal ? `· ${window.roundLabelOriginal}` : ""}</h3>
      <p>{windowRange(window, locale)}</p>
      <p class={`tag status-${state}`}>{windowStatusLabel(state, locale)}</p>
      {#if window.applicantScope}
        <p>{t(locale, "application.scope")}{fieldSep(locale)}{text(window.applicantScope, locale)}</p>
      {/if}
      {#if window.conditionalOnVacancies}
        <p class="notice">{t(locale, "application.vacanciesConditional")}</p>
      {/if}
      {#if href && windowCanApply(window, now, liveWholeClosed)}
        <p>
          <a class="external" href={href} rel="noopener noreferrer" target="_blank">
            {t(locale, "action.official")} ({hostOf(href)})
            <ExternalIcon />
            <span class="visually-hidden">{t(locale, "action.external")}</span>
          </a>
        </p>
      {:else if href && (liveWholeClosed || state === "closed")}
        <p>
          <a class="external" href={href} rel="noopener noreferrer" target="_blank">
            {t(locale, "action.viewOfficialNotice")} ({hostOf(href)})
            <ExternalIcon />
            <span class="visually-hidden">{t(locale, "action.external")}</span>
          </a>
        </p>
        <p class="muted">{liveWholeClosed ? t(locale, "application.opportunityClosed") : t(locale, "application.roundClosed")}</p>
      {:else if state === "closed" || liveWholeClosed}
        <p class="muted">{liveWholeClosed ? t(locale, "application.opportunityClosed") : t(locale, "application.roundClosed")}</p>
      {:else}
        <p class="muted">{t(locale, "application.roundNotOpen")}</p>
      {/if}
    </article>
  {/each}
</section>

<div class="actions">
  {#if applyUrl && canApply(summary)}
    <a class="btn primary external" href={applyUrl} rel="noopener noreferrer" target="_blank">
      {applyLabel} · {hostOf(applyUrl)}
      <ExternalIcon />
      <span class="visually-hidden">{t(locale, "action.external")}</span>
    </a>
  {:else if officialFallback}
    <a class="btn external" href={officialFallback} rel="noopener noreferrer" target="_blank">
      {noticeIsNotApplication ? applyLabel : t(locale, "action.officialLink")} · {hostOf(officialFallback)}
      <ExternalIcon />
      <span class="visually-hidden">{t(locale, "action.external")}</span>
    </a>
    {#if noticeIsNotApplication}
      <p class="muted">{t(locale, "application.noticeIsNotApplication")}</p>
    {/if}
  {/if}
  <slot />
</div>
