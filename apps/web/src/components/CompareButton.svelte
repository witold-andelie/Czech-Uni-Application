<script lang="ts">
  import { loadCompareIds, toggleCompare } from "../lib/storage";
  import { t } from "../lib/i18n";
  import type { UiLocale } from "../lib/types";

  let { id, locale }: { id: string; locale: UiLocale } = $props();
  let compared = $state(false);
  let limited = $state(false);

  $effect(() => {
    compared = loadCompareIds().includes(id);
  });

  function onClick() {
    const result = toggleCompare(id);
    compared = result.ids.includes(id);
    limited = result.limited;
  }
</script>

<button type="button" class="btn" aria-pressed={compared} onclick={onClick}>
  {compared ? t(locale, "action.compared") : t(locale, "action.compare")}
</button>
{#if limited}
  <span class="muted">{t(locale, "compare.limit")}</span>
{/if}
