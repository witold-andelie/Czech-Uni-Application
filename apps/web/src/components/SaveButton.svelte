<script lang="ts">
  import { loadSavedIds, toggleSaved } from "../lib/storage";
  import { t } from "../lib/i18n";
  import type { UiLocale } from "../lib/types";

  let { id, locale }: { id: string; locale: UiLocale } = $props();
  let saved = $state(false);

  $effect(() => {
    saved = loadSavedIds().includes(id);
  });

  function onClick() {
    saved = toggleSaved(id).includes(id);
  }
</script>

<button type="button" class="btn" aria-pressed={saved} onclick={onClick}>
  {saved ? t(locale, "action.saved") : t(locale, "action.save")}
</button>
