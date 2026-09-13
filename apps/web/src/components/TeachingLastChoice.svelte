<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import { t } from "../lib/i18n";
  import { readTeachingLanguage } from "../lib/storage";
  import type { UiLocale } from "../lib/types";

  let { locale }: { locale: UiLocale } = $props();
  let last = $state<ReturnType<typeof readTeachingLanguage>>(null);

  $effect(() => {
    last = readTeachingLanguage();
    for (const card of document.querySelectorAll<HTMLAnchorElement>(".choice-card")) {
      const href = card.getAttribute("href") || "";
      const selected = last != null && href.includes(`teachingLanguage=${last}`);
      card.classList.toggle("selected", selected);
      if (selected) card.setAttribute("aria-current", "true");
      else card.removeAttribute("aria-current");
    }
  });

  function lastLabel(choice: "en" | "cs" | "all"): string {
    if (choice === "en") return t(locale, "teaching.en");
    if (choice === "cs") return t(locale, "teaching.cs");
    return t(locale, "teaching.all");
  }
</script>

{#if last}
  <p>
    <a class="btn" href={withBase(`/${locale}/programmes?teachingLanguage=${last}`)}>
      {t(locale, "teaching.continue", { label: lastLabel(last) })}
    </a>
  </p>
{/if}
