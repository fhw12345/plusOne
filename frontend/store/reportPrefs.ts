"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type Perspective = "zh" | "en" | "fused";

export interface ReportPrefsState {
  perspective: Perspective;
  setPerspective: (p: Perspective) => void;
}

// Mirrors the pattern in ``store/auth.ts``: ``skipHydration: true`` so SSR
// and first client paint agree, then a separate ``useReportPrefsHasHydrated``
// hook flips after ``persist.rehydrate()`` resolves. See PRD batch2i §4.7.
export const useReportPrefsStore = create<ReportPrefsState>()(
  persist(
    (set) => ({
      perspective: "fused",
      setPerspective: (perspective) => set({ perspective }),
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
      partialize: (state) => ({ perspective: state.perspective }),
      skipHydration: true,
    },
  ),
);
