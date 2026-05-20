"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import { TripForm } from "@/components/trips/TripForm";
import { useAuthStore } from "@/store/auth";

export default function NewTripPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  if (!hydrated || !token) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Plan a trip</h1>
        <p className="text-foreground/70 mt-1 text-sm">
          Tell us where you&apos;re going and we&apos;ll surface local picks beyond the usual
          tourist traps.
        </p>
      </header>
      <TripForm />
    </main>
  );
}
