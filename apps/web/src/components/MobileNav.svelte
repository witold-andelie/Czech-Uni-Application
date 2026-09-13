<script lang="ts">
  import { t } from "../lib/i18n";
  import { NAV_ITEMS, navHref } from "../lib/nav";
  import type { UiLocale } from "../lib/types";
  import LocaleSwitcher from "./LocaleSwitcher.svelte";
  import ModalDialog from "./ModalDialog.svelte";

  let { locale, pathname, search = "" }: { locale: UiLocale; pathname: string; search?: string } = $props();
  let open = $state(false);
</script>

<div class="mobile-nav">
  <button
    type="button"
    class="btn nav-toggle"
    aria-expanded={open}
    aria-controls="mobile-drawer"
    onclick={() => (open = !open)}
  >
    {open ? t(locale, "nav.closeMenu") : t(locale, "nav.openMenu")}
  </button>
</div>

<ModalDialog
  bind:open
  labelledBy="mobile-nav-title"
  desktopQuery="(min-width: 768px)"
  id="mobile-drawer"
  class="nav-drawer"
  persist={false}
>
  <h2 id="mobile-nav-title" class="visually-hidden" tabindex="-1">{t(locale, "nav.main")}</h2>
  <nav class="nav-drawer-links">
    {#each NAV_ITEMS as item}
      <a
        href={navHref(locale, item.path)}
        aria-current={pathname.includes(item.match) ? "page" : undefined}
        onclick={() => (open = false)}
      >
        {t(locale, item.key)}
      </a>
    {/each}
  </nav>
  <LocaleSwitcher {locale} {pathname} {search} />
</ModalDialog>
