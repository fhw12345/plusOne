"use client";

import Link from "next/link";
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
      <div className="shell">
        <p className="scrawl" style={{ marginTop: 80, fontSize: 19 }}>
          one sec &mdash; sharpening the pencil&hellip;
        </p>
      </div>
    );
  }

  return (
    <div className="shell" style={{ maxWidth: 980 }}>
      <nav className="nav-strip" style={{ marginBottom: 32 }}>
        <p className="crest" style={{ marginRight: "auto" }}>
          <span className="crest-dot" />
          PLUS &middot; ONE
        </p>
        <Link href="/app">your readings</Link>
        <span className="sep" />
        <Link className="is-on" href="/app/trips/new">
          new reading
        </Link>
        <span className="sep" />
        <Link href="/app/companions">who you bring</Link>
        <span className="sep" />
        <Link href="/app/profile">about you</Link>
      </nav>

      <header style={{ position: "relative", padding: "12px 0 36px" }}>
        <span
          className="tape tape--yellow"
          style={{ top: -8, left: 320, width: 96, height: 24, transform: "rotate(4deg)" }}
        />
        <h1 className="hand-xxl">where are you headed?</h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 580, marginTop: 14 }}>
          tell me where &amp; what you&rsquo;re hoping for. i&rsquo;ll go look.
        </p>

        <span className="stamp" style={{ position: "absolute", top: 22, right: 0 }}>
          new reading
          <span className="ymd">about to start</span>
        </span>
      </header>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "1.5fr 1fr",
          gap: 36,
          alignItems: "start",
        }}
      >
        <TripForm />

        <aside style={{ position: "relative", paddingTop: 12 }}>
          <div
            style={{
              position: "relative",
              padding: "24px 26px 28px",
              background: "hsl(var(--paper-2))",
              transform: "rotate(1deg)",
              border: "1px solid hsl(var(--kraft))",
            }}
          >
            <p className="type" style={{ marginBottom: 14 }}>
              what i&rsquo;ll do
            </p>
            <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 12 }}>
              {[
                "ask around on reddit — r/{place}, r/japantravel, the deeper subs",
                "cross-check on 小红书 — the chinese travelers know the quiet ones",
                "settle disagreements by going deeper, not louder",
                "write you a short notebook page. yours to keep.",
              ].map((text, i) => (
                <li
                  key={i}
                  className="scrawl"
                  style={{ position: "relative", paddingLeft: 22, fontSize: 16 }}
                >
                  <span style={{ position: "absolute", left: 0, top: 2, color: "hsl(var(--red))" }}>
                    {i + 1}.
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>

          <div
            className="sticky"
            style={{
              position: "static",
              marginTop: 30,
              ["--tilt" as never]: "-4deg",
              width: "100%",
            }}
          >
            <strong>a tip ↓</strong>
            the more specific your &ldquo;avoid&rdquo; list, the better. &ldquo;no tourist
            traps&rdquo; is fine. &ldquo;no chains, no places with english menus on the
            front&rdquo; is better.
          </div>
        </aside>
      </section>

      <footer style={{ marginTop: 100, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">PLUS &middot; ONE &middot; new reading &middot; v0.1</p>
      </footer>
    </div>
  );
}
