<script lang="ts">
  import { findJob, findOffering } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import { text } from "../lib/format";
  import { loadSavedIds, toggleSaved } from "../lib/storage";
  import type { CatalogSnapshot, UiLocale } from "../lib/types";

  let { catalog, locale }: { catalog: CatalogSnapshot; locale: UiLocale } = $props();
  let ids = $state<string[]>([]);
  let now = $state(new Date());

  $effect(() => {
    ids = loadSavedIds();
  });

  function remove(id: string) {
    ids = toggleSaved(id);
  }
</script>

<p class="disclaimer">{t(locale, "saved.localOnly")}</p>
{#if ids.length === 0}
  <div class="empty card">
    <h2>{t(locale, "saved.empty")}</h2>
  </div>
{:else}
  <div class="card-grid">
    {#each ids as id}
      {@const [kind, entityId] = id.split(":")}
      {@const offering = kind === "offering" ? findOffering(catalog, entityId, now) : null}
      {@const job = kind === "job" ? findJob(catalog, entityId, now) : null}
      <article class="card">
        {#if offering}
          <h3><a href={`/${locale}/programmes/${offering.offering.id}`}>{text(offering.offering.title, locale)}</a></h3>
          <p class="muted">{text(offering.institution.displayName, locale)}</p>
          {#if offering.summary.opportunityStatus === "closed"}
            <p class="notice">{t(locale, "status.closed")}</p>
          {/if}
        {:else if job}
          <h3><a href={`/${locale}/research-jobs/${job.job.id}`}>{text(job.job.title, locale)}</a></h3>
          <p class="muted">{text(job.employer.displayName, locale)}</p>
          {#if job.summary.opportunityStatus === "closed"}
            <p class="notice">{t(locale, "jobs.closedNotice")}</p>
          {/if}
        {:else}
          <p>{id}</p>
        {/if}
        <button class="btn" type="button" onclick={() => remove(id)}>{t(locale, "action.remove")}</button>
      </article>
    {/each}
  </div>
{/if}
