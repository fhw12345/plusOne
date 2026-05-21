"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ProfileForm } from "@/components/profile/ProfileForm";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import { useAuthStore } from "@/store/auth";

export default function ProfilePage() {
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
      <div className="shell">
        <p className="scrawl" style={{ marginTop: 80, fontSize: 19 }}>
          one sec &mdash; fetching your notes&hellip;
        </p>
      </div>
    );
  }

  return (
    <div className="shell" style={{ maxWidth: 920 }}>
      <nav className="nav-strip" style={{ marginBottom: 32 }}>
        <p className="crest" style={{ marginRight: "auto" }}>
          <span className="crest-dot" />
          PLUS &middot; ONE
        </p>
        <Link href="/app">your readings</Link>
        <span className="sep" />
        <Link href="/app/trips/new" title="plan a new trip">new reading</Link>
        <span className="sep" />
        <Link href="/app/companions">who you bring</Link>
        <span className="sep" />
        <Link className="is-on" href="/app/profile">
          about you
        </Link>
      </nav>

      <header style={{ position: "relative", padding: "12px 0 32px" }}>
        <span
          className="tape tape--mint"
          style={{ top: -8, left: 220, width: 110, height: 24, transform: "rotate(-4deg)" }}
        />
        <h1 className="hand-xxl">about you</h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 560, marginTop: 14 }}>
          a few notes so i can plan around you, not just the city. nothing fancy &mdash; the
          dealbreakers matter most.
        </p>
      </header>

      <section
        style={{
          position: "relative",
          padding: "30px 32px 36px",
          background: "hsl(var(--paper-2))",
          border: "1px solid hsl(var(--kraft))",
          boxShadow: "0 12px 24px -16px hsl(0 0% 0% / .2)",
          maxWidth: 720,
        }}
      >
        <span
          className="tape tape--yellow"
          style={{ top: -10, left: 36, width: 100, height: 24, transform: "rotate(2deg)" }}
        />
        <ProfileForm />
      </section>

      <footer
        style={{ marginTop: 100, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}
      >
        <p className="type">PLUS &middot; ONE &middot; about you &middot; v0.1</p>
      </footer>
    </div>
  );
}
