"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { exchange, me } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth";

function ExchangeInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const token = searchParams.get("token");
  const [asyncError, setAsyncError] = useState<"stale" | "bad" | null>(null);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    (async () => {
      try {
        const { access_token } = await exchange(token);
        setSession(access_token, { id: "", email: "" });
        const user = await me();
        if (cancelled) return;
        setSession(access_token, user);
        router.replace("/app");
      } catch {
        if (!cancelled) setAsyncError("stale");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [router, setSession, token]);

  if (!token) {
    return <ExchangeError variant="bad" />;
  }

  if (asyncError) {
    return <ExchangeError variant={asyncError} />;
  }

  return (
    <div style={{ position: "relative", maxWidth: 580 }}>
      <span className="stamp" style={{ position: "absolute", top: -22, right: 24 }}>
        verifying
        <span className="ymd">just a sec</span>
      </span>

      <h1 className="hand-xxl">unpacking the link&hellip;</h1>

      <div
        style={{
          position: "relative",
          marginTop: 50,
          padding: "30px 32px",
          background: "hsl(var(--tape-yellow) / .85)",
          boxShadow: "0 10px 20px -8px hsl(0 0% 0% / .22)",
          transform: "rotate(-1.5deg)",
          maxWidth: 440,
        }}
      >
        <p className="hand" style={{ fontSize: 26, lineHeight: 1.18 }}>
          <span className="muted type" style={{ display: "block", marginBottom: 8 }}>
            your magic link
          </span>
          welcome back.
          <br />
          pinning your notes&hellip;
        </p>
        <p className="scrawl" style={{ marginTop: 14 }}>
          i&rsquo;ll redirect you in a sec.
        </p>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 56 }}>
        <span className="type">progress</span>
        <span style={{ display: "inline-flex", gap: 6 }}>
          <i style={{ width: 24, height: 6, background: "hsl(var(--red))", display: "inline-block" }} />
          <i
            style={{
              width: 24,
              height: 6,
              background: "hsl(var(--red))",
              display: "inline-block",
              animation: "pulse 1.4s var(--ease-soft) infinite",
            }}
          />
          <i style={{ width: 24, height: 6, background: "hsl(var(--kraft))", display: "inline-block" }} />
        </span>
        <span className="annot" style={{ fontSize: 14 }}>
          unpacking, then pinning
        </span>
      </div>
    </div>
  );
}

function ExchangeError({ variant }: { variant: "stale" | "bad" }) {
  const isStale = variant === "stale";
  return (
    <div style={{ position: "relative", maxWidth: 580 }}>
      <h1 className="hand-xxl">unpacking the link&hellip;</h1>

      <div role="alert" className="ticket" style={{ marginTop: 40, ["--tilt" as never]: "-.6deg" }}>
        <div className="stamp-row">
          <span className="type">{isStale ? "stale link" : "bad link"}</span>
          <span className="type-sm">
            {isStale ? "expires after 15 min" : "token didn't match"}
          </span>
        </div>
        <p className="body">
          {isStale ? (
            <>
              this link&rsquo;s gone stale &mdash; let me{" "}
              <Link href="/login" className="link-hand" style={{ fontSize: 16 }}>
                send a fresh one
              </Link>
              .
            </>
          ) : (
            <>
              this link doesn&rsquo;t look right.{" "}
              <Link href="/login" className="link-hand" style={{ fontSize: 16 }}>
                start over
              </Link>
              ?
            </>
          )}
        </p>
      </div>
    </div>
  );
}

export default function AuthExchangePage() {
  return (
    <div className="shell" style={{ maxWidth: 720 }}>
      <p className="crest" style={{ marginTop: 18 }}>
        <span className="crest-dot" />
        PLUS &middot; ONE &middot; letting you in
      </p>

      <section style={{ marginTop: 80, position: "relative" }}>
        <Suspense
          fallback={
            <p className="scrawl" style={{ fontSize: 19 }}>
              unpacking the link&hellip;
            </p>
          }
        >
          <ExchangeInner />
        </Suspense>
      </section>

      <footer style={{ marginTop: 140, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">PLUS &middot; ONE &middot; v0.1</p>
      </footer>
    </div>
  );
}
