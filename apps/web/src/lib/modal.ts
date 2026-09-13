const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "summary",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function cycleTabIndex(count: number, current: number, reverse: boolean): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return reverse ? count - 1 : 0;
  if (reverse) return current <= 0 ? count - 1 : current - 1;
  return current >= count - 1 ? 0 : current + 1;
}

export function isDisplayed(el: HTMLElement): boolean {
  if (el.hidden || el.closest("[hidden]")) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  return el.getClientRects().length > 0;
}

export function getFocusable(root: ParentNode): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)].filter((el) => {
    if (el.getAttribute("aria-hidden") === "true") return false;
    if (el.closest("[inert]")) return false;
    return isDisplayed(el);
  });
}

export function wrapTab(event: KeyboardEvent, root: HTMLElement): void {
  if (event.key !== "Tab") return;
  const items = getFocusable(root);
  if (items.length === 0) {
    event.preventDefault();
    root.focus();
    return;
  }
  const active = document.activeElement;
  const current = items.findIndex((el) => el === active);
  const atEdge = event.shiftKey ? current <= 0 : current === -1 || current === items.length - 1;
  if (!atEdge) return;
  event.preventDefault();
  items[cycleTabIndex(items.length, current, event.shiftKey)]?.focus();
}

export type InertSession = { restore: () => void };

export function applyInertOutside(keep: HTMLElement[]): InertSession {
  const changed: HTMLElement[] = [];

  function visit(parent: Element): void {
    for (const child of parent.children) {
      if (!(child instanceof HTMLElement)) continue;
      if (keep.some((node) => child === node || child.contains(node))) {
        if (keep.includes(child)) continue;
        visit(child);
        continue;
      }
      if (!child.inert) {
        child.inert = true;
        changed.push(child);
      }
    }
  }

  visit(document.body);
  return {
    restore() {
      for (const el of changed) el.inert = false;
    },
  };
}

export function restoreFocus(trigger: HTMLElement | null, panel?: HTMLElement | null): void {
  const active = document.activeElement;
  if (active instanceof HTMLElement && isDisplayed(active) && !active.closest("[inert]")) {
    if (panel?.contains(active) || active === trigger) return;
  }
  if (trigger && isDisplayed(trigger) && !trigger.closest("[inert]")) {
    trigger.focus();
    return;
  }
  if (panel && isDisplayed(panel)) {
    const first = getFocusable(panel)[0];
    (first ?? panel).focus();
  }
}
