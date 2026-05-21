"use client";

import { useSyncExternalStore, useEffect } from "react";

const STORAGE_KEY = "plusone.view";
const PRINTED_CLASS = "printed-view";

type View = "scrapbook" | "printed";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getSnapshot(): View {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "printed" ? "printed" : "scrapbook";
}

function getServerSnapshot(): View {
  return "scrapbook";
}

export function ViewToggle() {
  const view = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    document.documentElement.classList.toggle(PRINTED_CLASS, view === "printed");
  }, [view]);

  function toggle() {
    const next: View = view === "printed" ? "scrapbook" : "printed";
    window.localStorage.setItem(STORAGE_KEY, next);
    window.dispatchEvent(new StorageEvent("storage", { key: STORAGE_KEY, newValue: next }));
  }

  const label = view === "printed" ? "switch to scrapbook" : "switch to printed";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      style={{
        position: "fixed",
        bottom: "16px",
        right: "16px",
        zIndex: 50,
        padding: "8px 12px",
        fontFamily: "var(--font-hand), cursive",
        fontSize: "16px",
        color: "hsl(var(--ink))",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(var(--kraft))",
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}
