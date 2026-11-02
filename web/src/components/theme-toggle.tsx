"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";
const EVENT = "pitchiq-theme";

function current(): Theme {
  const set = document.documentElement.dataset.theme as Theme | undefined;
  return set ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function subscribe(onChange: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    mq.removeEventListener("change", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

/** Toggles data-theme on <html>; the choice is remembered per browser. */
export function ThemeToggle() {
  const theme = useSyncExternalStore<Theme | null>(subscribe, current, () => null);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      onClick={() => {
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem("theme", next);
        } catch {}
        window.dispatchEvent(new Event(EVENT));
      }}
      className="rounded-md border border-border px-2 py-1 text-sm text-fg-2 hover:text-fg"
    >
      {theme === "dark" ? "☀︎" : "☾"}
    </button>
  );
}

/** Inline script (runs before paint) so a stored theme never flashes. */
export const themeScript = `try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;
