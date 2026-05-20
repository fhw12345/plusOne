"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type Perspective = "zh" | "en" | "fused";

// Output-language toggle (PRD batch 2k §6.7). ``original`` renders the
// source-language items (the existing ``content.items`` payload — used
// when no translation exists OR the user opts out of translation).
export type ReportLanguage = "original" | "en" | "zh";

export interface ReportPrefsState {
  perspective: Perspective;
  setPerspective: (p: Perspective) => void;
  language: ReportLanguage;
  setLanguage: (l: ReportLanguage) => void;
}

// Mirrors the pattern in ``store/auth.ts``: ``skipHydration: true`` so SSR
// and first client paint agree, then a separate ``useReportPrefsHasHydrated``
// hook flips after ``persist.rehydrate()`` resolves. See PRD batch2i §4.7.
export const useReportPrefsStore = create<ReportPrefsState>()(
  persist(
    (set) => ({
      perspective: "fused",
      setPerspective: (perspective) => set({ perspective }),
      language: "original",
      setLanguage: (language) => set({ language }),
    }),
    {
      name: "plus-one-report-prefs",
      storage: createJSONStorage(() =>
        typeof window === "undefined"
          ? {
              getItem: () => null,
              setItem: () => undefined,
              removeItem: () => undefined,
            }
          : window.localStorage,
      ),
      partialize: (state) => ({
        perspective: state.perspective,
        language: state.language,
      }),
      skipHydration: true,
    },
  ),
);
