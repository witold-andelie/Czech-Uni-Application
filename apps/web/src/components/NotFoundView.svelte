<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import { t, localeFromPathname, LOCALES } from "../lib/i18n";
  import type { UiLocale } from "../lib/types";

  let locale = $state<UiLocale>("zh-CN");

  $effect(() => {
    locale = localeFromPathname(window.location.pathname);
  });
</script>

<main id="main" class="page">
  <section class="empty card">
    <h1>{t(locale, "error.notFound")}</h1>
    <p>{t(locale, "error.notFound.help")}</p>
    <div class="actions">
      <a class="btn primary" href={withBase(`/${locale}/`)}>{t(locale, "error.home")}</a>
      <a class="btn" href={withBase(`/${locale}/programmes`)}>{t(locale, "nav.programmes")}</a>
    </div>
    <p>
      {#each LOCALES as item, index}
        {#if index > 0}{" · "}{/if}
        <a href={withBase(`/${item}/`)} lang={item} hreflang={item}>{t(locale, `locale.${item}`)}</a>
      {/each}
    </p>
  </section>
</main>
