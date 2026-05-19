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
  // Token absence is a pure derivation of search params — compute it during
  // render, not in an effect, to avoid the cascading-setState lint rule.
  const token = searchParams.get("token");
  const [asyncError, setAsyncError] = useState(false);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    (async () => {
      try {
        const { access_token } = await exchange(token);
        // Write the JWT into the store BEFORE calling me(), so apiFetch
        // picks it up on the Authorization header.
        setSession(access_token, { id: "", email: "" });
        const user = await me();
        if (cancelled) return;
        setSession(access_token, user);
        router.replace("/app");
      } catch {
        if (!cancelled) setAsyncError(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [router, setSession, token]);

  if (!token || asyncError) {
    return (
      <p className="text-sm">
        This sign-in link is invalid or expired.{" "}
        <Link href="/login" className="underline underline-offset-4">
          Request a new one
        </Link>
        .
      </p>
    );
  }
  return <p className="text-sm">Signing you in…</p>;
}

export default function AuthExchangePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
      <Suspense fallback={<p className="text-sm">Signing you in…</p>}>
        <ExchangeInner />
      </Suspense>
    </main>
  );
}
