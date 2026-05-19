"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import { logout } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth";

export default function AppPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clear = useAuthStore((s) => s.clear);
  const { data: user, isLoading } = useCurrentUser();
  // Sign-out intent: when the user clicks Sign out, route them to landing
  // (not /login). The auth-gate effect below would otherwise see the cleared
  // token and bounce them to /login, racing the navigation.
  const signingOut = useRef(false);

  useEffect(() => {
    if (signingOut.current) return;
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  const onSignOut = async () => {
    signingOut.current = true;
    try {
      await logout();
    } catch {
      // Best-effort: even if the server call fails, clear local state.
    }
    router.replace("/");
    clear();
  };

  if (!hydrated || !token || isLoading || !user) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Hello, {user.email}</h1>
        <button
          type="button"
          onClick={onSignOut}
          className="border-foreground/20 rounded border px-3 py-1.5 text-sm"
        >
          Sign out
        </button>
      </header>
      <p className="text-muted-foreground text-sm">
        Welcome to Plus One. Trip planning UI lands next.
      </p>
      <Link
        href="/app/trips/new"
        className="border-foreground/20 rounded border px-3 py-2 text-sm font-medium"
      >
        Plan a trip
      </Link>
    </main>
  );
}
