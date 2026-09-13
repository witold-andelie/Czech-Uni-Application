<script lang="ts">
  import type { Snippet } from "svelte";
  import { t } from "../lib/i18n";
  import type { UiLocale } from "../lib/types";
  import ModalDialog from "./ModalDialog.svelte";

  let {
    open = $bindable(false),
    locale,
    labelledBy,
    resultCount,
    id,
    onsubmit,
    children,
  }: {
    open: boolean;
    locale: UiLocale;
    labelledBy: string;
    resultCount: number;
    id: string;
    onsubmit: (event: SubmitEvent) => void;
    children: Snippet;
  } = $props();
</script>

<ModalDialog
  bind:open
  {labelledBy}
  desktopQuery="(min-width: 768px)"
  {id}
  class="filters card"
  element="form"
  {onsubmit}
>
  <div class="filter-sheet-toolbar">
    <h2 id={labelledBy} class="visually-hidden" tabindex="-1">{t(locale, "filter.drawer")}</h2>
    <button class="btn filter-sheet-close" type="button" onclick={() => (open = false)}>
      {t(locale, "filter.close")}
    </button>
  </div>
  {@render children()}
  <div class="filter-sheet-bar">
    <button class="btn primary" type="button" onclick={() => (open = false)}>
      {t(locale, "filter.viewResults", { n: resultCount })}
    </button>
  </div>
</ModalDialog>
