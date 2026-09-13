<script lang="ts">
  import { tick, type Snippet } from "svelte";
  import { applyInertOutside, getFocusable, restoreFocus, wrapTab, type InertSession } from "../lib/modal";

  let {
    open = $bindable(false),
    labelledBy,
    label,
    desktopQuery,
    id,
    class: className = "",
    element = "div",
    persist = true,
    onsubmit,
    children,
  }: {
    open: boolean;
    labelledBy?: string;
    label?: string;
    desktopQuery: string;
    id?: string;
    class?: string;
    element?: "div" | "form";
    persist?: boolean;
    onsubmit?: (event: SubmitEvent) => void;
    children: Snippet;
  } = $props();

  let panel: HTMLElement | undefined = $state();
  let backdrop: HTMLElement | undefined = $state();
  let isDesktop = $state(false);
  let trigger: HTMLElement | null = null;
  let inertSession: InertSession | null = null;

  const modal = $derived(open && !isDesktop);

  $effect(() => {
    const media = window.matchMedia(desktopQuery);
    const sync = () => {
      isDesktop = media.matches;
      if (media.matches) open = false;
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  });

  $effect(() => {
    if (!modal) return;
    const active = document.activeElement;
    if (active instanceof HTMLElement) trigger = active;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        open = false;
        return;
      }
      if (panel) wrapTab(event, panel);
    };
    window.addEventListener("keydown", onKey, true);
    let cancelled = false;
    void tick().then(() => {
      if (cancelled || !panel) return;
      const keep = [panel, backdrop].filter((node): node is HTMLElement => node != null);
      inertSession = applyInertOutside(keep);
      const heading = labelledBy ? panel.querySelector<HTMLElement>(`#${CSS.escape(labelledBy)}`) : null;
      (heading ?? getFocusable(panel)[0] ?? panel).focus();
    });
    return () => {
      cancelled = true;
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey, true);
      inertSession?.restore();
      inertSession = null;
      const restoreTo = trigger;
      trigger = null;
      restoreFocus(restoreTo, isDesktop ? panel : null);
    };
  });
</script>

{#if modal}
  <div bind:this={backdrop} class="sheet-backdrop" aria-hidden="true" onclick={() => (open = false)}></div>
{/if}
{#if modal || persist}
  <svelte:element
    this={element}
    {id}
    class={className}
    bind:this={panel}
    role={modal ? "dialog" : undefined}
    aria-modal={modal ? "true" : undefined}
    aria-labelledby={modal && labelledBy ? labelledBy : undefined}
    aria-label={modal && label && !labelledBy ? label : undefined}
    tabindex={modal ? -1 : undefined}
    onsubmit={onsubmit}
  >
    {@render children()}
  </svelte:element>
{/if}
