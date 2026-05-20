"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";

import { TripCard } from "@/components/trips/TripCard";
import { TripListEmpty } from "@/components/trips/TripListEmpty";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import { useTrips } from "@/hooks/useTrips";
import { logout } from "@/lib/api/auth";
import type { TripListItem } from "@/lib/schemas/trips";
import { useAuthStore } from "@/store/auth";

function SkeletonList() {
  return (
    <ul className="flex flex-col gap-3" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <li
          key={i}
          className="bg-foreground/10 h-16 animate-pulse rounded border border-transparent"
        />
      ))}
    </ul>
  );
}

export default function AppPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clear = useAuthStore((s) => s.clear);
  const { data: user, isLoading: userLoading } = useCurrentUser();
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

  const trips = useTrips();
  const flatTrips = useMemo<TripListItem[]>(
    () => trips.data?.pages.flatMap((p) => p.trips) ?? [],
    [trips.data],
  );

  if (!hydrated || !token || userLoading || !user) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight">My Trips</h1>
          <p className="text-foreground/60 text-sm">Hello, {user.email}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/app/trips/new"
            className="bg-foreground text-background rounded px-3 py-1.5 text-sm font-medium"
          >
            Plan a new trip
          </Link>
          <Link
            href="/app/profile"
            className="border-foreground/20 rounded border px-3 py-1.5 text-sm"
          >
            Profile
          </Link>
          <Link
            href="/app/companions"
            className="border-foreground/20 rounded border px-3 py-1.5 text-sm"
          >
            Companions
          </Link>
          <button
            type="button"
            onClick={onSignOut}
            className="border-foreground/20 rounded border px-3 py-1.5 text-sm"
          >
            Sign out
          </button>
        </div>
      </header>

      {trips.isLoading ? <SkeletonList /> : null}

      {trips.isError ? (
        <p role="alert" className="text-sm text-red-600">
          Couldn&apos;t load your trips.{" "}
          <button
            type="button"
            onClick={() => trips.refetch()}
            className="underline underline-offset-2"
          >
            Try again
          </button>
        </p>
      ) : null}

      {trips.isSuccess && flatTrips.length === 0 ? <TripListEmpty /> : null}

      {trips.isSuccess && flatTrips.length > 0 ? (
        <>
          <ul className="flex flex-col gap-3">
            {flatTrips.map((trip) => (
              <TripCard key={trip.trip_id} trip={trip} />
            ))}
          </ul>
          {trips.hasNextPage ? (
            <button
              type="button"
              onClick={() => trips.fetchNextPage()}
              disabled={trips.isFetchingNextPage}
              className="border-foreground/20 self-center rounded border px-4 py-2 text-sm disabled:opacity-50"
            >
              {trips.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
