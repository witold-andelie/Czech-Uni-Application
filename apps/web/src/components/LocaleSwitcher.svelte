<script lang="ts">
  import { LOCALES, t, switchLocalePath, isModifiedLocaleClick } from "../lib/i18n";
  import { saveUiLocale } from "../lib/storage";
  import type { UiLocale } from "../lib/types";

  let { locale, pathname, search = "" }: { locale: UiLocale; pathname: string; search?: string } = $props();
  let currentSearch = $state(search);

  $effect(() => {
    const refresh = () => {
      currentSearch = window.location.search || search;
    };
    refresh();
    saveUiLocale(locale);
    window.addEventListener("popstate", refresh);
    window.addEventListener("listquerychange", refresh);
    return () => {
      window.removeEventListener("popstate", refresh);
      window.removeEventListener("listquerychange", refresh);
    };
  });

  function onLocaleClick(event: MouseEvent, item: UiLocale) {
    saveUiLocale(item);
    if (item === locale) {
      event.preventDefault();
      return;
    }
    if (isModifiedLocaleClick(event)) return;
    event.preventDefault();
    const href = switchLocalePath(window.location.pathname, window.location.search || currentSearch, item);
    location.replace(href);
  }
</script>

<nav class="locale-switch" aria-label={t(locale, "locale.label")}>
  {#each LOCALES as item}
    <a
      href={switchLocalePath(pathname, currentSearch, item)}
      hreflang={item}
      lang={item}
      aria-current={item === locale ? "true" : undefined}
      onclick={(event) => onLocaleClick(event, item)}
    >
      {t(locale, `locale.${item}`)}
    </a>
  {/each}
</nav>
