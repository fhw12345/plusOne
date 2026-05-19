"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
}

export interface AuthState {
  token: string | null;
  user: AuthUser | null;
  setSession: (token: string, user: AuthUser) => void;
  clear: () => void;
}

// `skipHydration: true` is load-bearing: the server has no localStorage, so
// reading it during SSR would produce a different first render than the
// client's second render → React hydration error. The Providers component
// triggers `useAuthStore.persist.rehydrate()` after mount; gate any auth-
// dependent UI behind `useHasHydrated()` until that finishes.
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setSession: (token, user) => set({ token, user }),
      clear: () => set({ token: null, user: null }),
    }),
    {
      name: "plus-one-auth",
      storage: createJSONStorage(() =>
        typeof window === "undefined"
          ? // SSR-safe noop storage; never actually used because skipHydration is on.
            {
              getItem: () => null,
              setItem: () => undefined,
              removeItem: () => undefined,
            }
          : window.localStorage,
      ),
      partialize: (state) => ({ token: state.token, user: state.user }),
      skipHydration: true,
    },
  ),
);
