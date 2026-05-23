"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";

import { TripCard } from "@/components/trips/TripCard";
import { TripListEmpty } from "@/components/trips/TripListEmpty";
import { AdminWireLink } from "@/components/AdminWireLink";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import { useTrips } from "@/hooks/useTrips";
import { logout } from "@/lib/api/auth";
import type { TripListItem } from "@/lib/schemas/trips";
import { useAuthStore } from "@/store/auth";

function SkeletonGallery() {
  return (
    <section className="gallery" style={{ marginTop: 28 }} aria-hidden="true" aria-busy="true">
      {[0, 1, 2].map((i) => (
        <article
          key={i}
          className="photo-card"
          style={{
            // alternating gentle tilt so even the skeleton reads scrapbook
            transform: `rotate(${i % 2 === 0 ? -1.2 : 1.4}deg)`,
            background: "hsl(var(--paper-2))",
            opacity: 0.7,
          }}
        >
          <div
            className="photo"
            style={{
              background:
                "repeating-linear-gradient(135deg, hsl(var(--kraft) / .25) 0 14px, hsl(var(--paper-3)) 14px 28px)",
            }}
          />
          <p className="cap muted" style={{ fontStyle: "italic" }}>
            arriving by next post
          </p>
        </article>
      ))}
    </section>
  );
}

export default function AppPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const clear = useAuthStore((s) => s.clear);
  const { data: user, isLoading: userLoading } = useCurrentUser();
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
      /* best effort */
    }
    clear();
    router.replace("/");
    router.refresh();
  };

  const trips = useTrips();
  const flatTrips = useMemo<TripListItem[]>(
    () => trips.data?.pages.flatMap((p) => p.trips) ?? [],
    [trips.data],
  );

  if (!hydrated || !token || userLoading || !user) {
    return (
      <div className="shell">
        <p className="scrawl" style={{ marginTop: 80, fontSize: 19 }}>
          one sec &mdash; pulling your notes&hellip;
        </p>
      </div>
    );
  }

  return (
    <div className="shell">
      <nav className="nav-strip" style={{ marginBottom: 32 }}>
        <p className="crest" style={{ marginRight: "auto" }}>
          <span className="crest-dot" />
          PLUS &middot; ONE
        </p>
        <Link className="is-on" href="/app">
          your readings
        </Link>
        <span className="sep" />
        <Link href="/app/trips/new" title="plan a new trip">
          new reading
        </Link>
        <span className="sep" />
        <Link href="/app/companions">who you bring</Link>
        <span className="sep" />
        <Link href="/app/profile">about you</Link>
        <AdminWireLink />
        <span className="sep" />
        <button type="button" onClick={onSignOut} className="muted" style={{ font: "inherit" }}>
          log out
        </button>
      </nav>

      <header style={{ position: "relative", padding: "12px 0 32px" }}>
        <span
          className="tape tape--yellow"
          style={{ top: -8, left: 240, width: 96, height: 24, transform: "rotate(-3deg)" }}
        />
        <h1 className="hand-xxl">your readings</h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 540, marginTop: 14 }}>
          every place i&rsquo;ve looked into for you. the freshest one is up top.
        </p>

        <div
          style={{
            position: "absolute",
            top: 18,
            right: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 14,
          }}
        >
          <span className="stamp">
            for {user.email.split("@")[0]}
            <span className="ymd">notebook 01</span>
          </span>
          <Link href="/app/trips/new" className="btn btn--red">
            + new reading
          </Link>
        </div>
      </header>

      {trips.isLoading ? <SkeletonGallery /> : null}

      {trips.isError ? (
        <div
          role="alert"
          className="ticket"
          style={{ marginTop: 32, ["--tilt" as never]: "-.5deg" }}
        >
          <div className="stamp-row">
            <span className="type" style={{ color: "hsl(var(--signal-snag))" }}>
              hit a wall
            </span>
            <span className="type-sm">couldn&rsquo;t open the notebook</span>
          </div>
          <p className="body">
            something snagged on the wire.{" "}
            <button
              type="button"
              onClick={() => trips.refetch()}
              className="link-hand"
              style={{ font: "inherit", fontSize: 16, background: "none", border: 0, padding: 0 }}
            >
              try this one again
            </button>
            ?
          </p>
        </div>
      ) : null}

      {trips.isSuccess && flatTrips.length === 0 ? <TripListEmpty /> : null}

      {trips.isSuccess && flatTrips.length > 0 ? (
        <>
          <section className="gallery" style={{ marginTop: 28 }}>
            {flatTrips.map((trip, i) => (
              <TripCard key={trip.trip_id} trip={trip} index={i} />
            ))}
          </section>

          {trips.hasNextPage ? (
            <p style={{ textAlign: "center", marginTop: 32 }}>
              <button
                type="button"
                onClick={() => trips.fetchNextPage()}
                disabled={trips.isFetchingNextPage}
                className="btn"
                style={{ opacity: trips.isFetchingNextPage ? 0.55 : 1 }}
              >
                {trips.isFetchingNextPage ? "pulling more…" : "+ pull the next page"}
              </button>
            </p>
          ) : null}
        </>
      ) : null}

      <p className="annot" style={{ display: "inline-block", marginTop: 60, fontSize: 16 }}>
        &uarr; tap any card to flip it open.
      </p>

      <footer style={{ marginTop: 100, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">
          PLUS &middot; ONE &middot; reading no. {flatTrips.length || "—"} &middot; v0.1
        </p>
      </footer>
    </div>
  );
}
