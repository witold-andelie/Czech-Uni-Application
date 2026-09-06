<script lang="ts">
  import { findOffering } from "../lib/catalog";
  import { t } from "../lib/i18n";
  import { formatTuition, ownershipLabel, recognitionKey, teachingLanguageLabel, text, windowRange } from "../lib/format";
  import { loadCompareIds } from "../lib/storage";
  import type { CatalogSnapshot, OfferingView, UiLocale } from "../lib/types";

  let { catalog, locale }: { catalog: CatalogSnapshot; locale: UiLocale } = $props();
  let views = $state<OfferingView[]>([]);
  let now = $state(new Date());

  $effect(() => {
    views = loadCompareIds()
      .filter((id) => id.startsWith("offering:"))
      .map((id) => findOffering(catalog, id.slice("offering:".length), now))
      .filter((item): item is OfferingView => item != null);
  });
</script>

{#if views.length === 0}
  <div class="empty card">
    <h2>{t(locale, "compare.empty")}</h2>
  </div>
{:else}
  <p class="disclaimer">{t(locale, "compare.limit")}</p>
  <div class="compare-wrap">
    <table class="compare-table">
      <thead>
        <tr>
          <th></th>
          {#each views as view}
            <th><a href={`/${locale}/programmes/${view.offering.id}`}>{text(view.offering.title, locale)}</a></th>
          {/each}
        </tr>
      </thead>
      <tbody>
        <tr>
          <th>{t(locale, "detail.institution")}</th>
          {#each views as view}<td>{text(view.institution.displayName, locale)}</td>{/each}
        </tr>
        <tr>
          <th>{t(locale, "institution.ownership")}</th>
          {#each views as view}<td>{ownershipLabel(view.institution.ownership, locale)}</td>{/each}
        </tr>
        <tr>
          <th>{t(locale, "recognition.label")}</th>
          {#each views as view}<td>{t(locale, recognitionKey(view.institution.cscseReference.lookupStatus))}</td>{/each}
        </tr>
        <tr>
          <th>{t(locale, "teaching.label")}</th>
          {#each views as view}<td>{teachingLanguageLabel(view.offering.teachingLanguages, view.offering.languageMode, locale)}</td>{/each}
        </tr>
        <tr>
          <th>{t(locale, "detail.tuition")}</th>
          {#each views as view}<td>{formatTuition(view.offering.tuition, locale)}</td>{/each}
        </tr>
        <tr>
          <th>{t(locale, "application.currentRound")}</th>
          {#each views as view}
            <td>
              {#if view.summary.current[0]}
                {windowRange(view.summary.current[0], locale)}
              {:else}
                {t(locale, "status.unknown")}
              {/if}
            </td>
          {/each}
        </tr>
      </tbody>
    </table>
  </div>
{/if}
