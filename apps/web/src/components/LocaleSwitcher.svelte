<script lang="ts">
  import { LOCALES, t, switchLocalePath } from "../lib/i18n";
  import { saveUiLocale } from "../lib/storage";
  import type { UiLocale } from "../lib/types";

  let { locale, pathname }: { locale: UiLocale; pathname: string } = $props();
  let search = $state("");

  $effect(() => {
    search = window.location.search;
    saveUiLocale(locale);
  });
</script>

<nav class="locale-switch" aria-label={t(locale, "locale.label")}>
  {#each LOCALES as item}
    <a
      href={switchLocalePath(pathname, search, item)}
      hreflang={item}
      lang={item}
      aria-current={item === locale ? "true" : undefined}
      onclick={() => saveUiLocale(item)}
    >
      {t(locale, `locale.${item}`)}
    </a>
  {/each}
</nav>
