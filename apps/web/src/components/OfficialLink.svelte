<script lang="ts">
  import { hostOf } from "../lib/format";
  import { t } from "../lib/i18n";
  import type { UiLocale } from "../lib/types";
  import ExternalIcon from "./ExternalIcon.svelte";

  let {
    locale,
    href,
    label,
    primary = false,
  }: {
    locale: UiLocale;
    href: string;
    label?: string;
    primary?: boolean;
  } = $props();
</script>

<a class="btn external" class:primary={primary} href={href} rel="noopener noreferrer" target="_blank">
  {label ?? t(locale, "action.officialLink")}
  <ExternalIcon />
  <span class="muted">({hostOf(href)})</span>
  <span class="visually-hidden">{t(locale, "action.external")}</span>
</a>
