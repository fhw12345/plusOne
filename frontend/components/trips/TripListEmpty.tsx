"use client";

import Link from "next/link";

export function TripListEmpty() {
  return (
    <div className="border-foreground/10 flex flex-col items-center gap-3 rounded border border-dashed px-6 py-10 text-center">
      <p className="text-base font-medium">No trips yet</p>
      <p className="text-foreground/60 max-w-sm text-sm">
        Your first trip is one click away. Tell us where you&apos;re going and we&apos;ll find the
        local picks tourists miss.
      </p>
      <Link
        href="/app/trips/new"
        className="bg-foreground text-background mt-2 rounded px-4 py-2 text-sm font-medium"
      >
        Plan a new trip
      </Link>
    </div>
  );
}
