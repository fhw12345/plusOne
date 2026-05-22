"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { requestCode, verify } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { VerifyBody, type VerifyBody as VerifyBodyT } from "@/lib/schemas/auth";
import { useAuthStore } from "@/store/auth";

const RESEND_COOLDOWN_S = 60;

function mapVerifyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 400) {
      const detail = typeof err.message === "string" ? err.message : "";
      if (detail.includes("expired")) return "your code timed out. one more time?";
      return "the code didn't match. try again?";
    }
    if (err.status === 503) {
      return "the inbox door is shut on our end right now. give it a minute and try again.";
    }
  }
  return "something snagged on the wire. one more try?";
}

function VerifyInner() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);
  const params = useSearchParams();
  const emailFromQuery = params.get("email") ?? "";

  const [serverError, setServerError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  // Resend cooldown ticks down once a second when armed.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<VerifyBodyT>({
    resolver: zodResolver(VerifyBody),
    mode: "onSubmit",
    defaultValues: { email: emailFromQuery, code: "" },
  });

  const onSubmit = async (values: VerifyBodyT) => {
    setServerError(null);
    try {
      const res = await verify(values);
      setSession(res.access_token, res.user);
      router.push("/app");
    } catch (err) {
      setServerError(mapVerifyError(err));
    }
  };

  const onResend = async () => {
    if (cooldown > 0) {
      setServerError("hold on a sec — i just sent one.");
      return;
    }
    setServerError(null);
    try {
      // The backend `request-code` route branches on the user's verified
      // state — for an unverified email it sends a verify_email code, not a
      // login code. See PRD §8 note under /verify.
      await requestCode({ email: emailFromQuery });
      setCooldown(RESEND_COOLDOWN_S);
    } catch (err) {
      setServerError(mapVerifyError(err));
    }
  };

  return (
    <div style={{ position: "relative", maxWidth: 580 }}>
      <h1 className="hand-xxl">check your inbox</h1>
      <p className="scrawl" style={{ fontSize: 19, maxWidth: 480, marginTop: 14 }}>
        we sent a six-digit code. it&rsquo;s good for ten minutes.
      </p>

      <div
        style={{
          position: "relative",
          marginTop: 48,
          padding: "32px 36px 36px",
          background: "hsl(var(--paper-2))",
          boxShadow: "0 14px 28px -14px hsl(0 0% 0% / .22)",
          transform: "rotate(-.8deg)",
          maxWidth: 480,
        }}
      >
        <span
          className="tape tape--yellow"
          style={{
            top: -12,
            left: "50%",
            width: 110,
            height: 24,
            transform: "translateX(-50%) rotate(2deg)",
          }}
        />

        {emailFromQuery ? (
          <p className="annot" style={{ display: "block", marginBottom: 14, fontSize: 14 }}>
            sent to {emailFromQuery}
          </p>
        ) : null}

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          {/* email goes along in the body — hidden from the user but kept
              honest by zod */}
          <input type="hidden" {...register("email")} />

          <div className="field">
            <label htmlFor="code">the code</label>
            <input
              id="code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              {...register("code")}
              aria-invalid={errors.code ? "true" : "false"}
            />
            <span className="hint">just the numbers.</span>
            {errors.code ? (
              <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                {errors.code.message}
              </span>
            ) : null}
            {errors.email ? (
              <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                {errors.email.message}
              </span>
            ) : null}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 12 }}>
            <button
              type="submit"
              className="btn"
              disabled={isSubmitting}
              style={{ opacity: isSubmitting ? 0.6 : 1 }}
            >
              {isSubmitting ? "letting you in…" : "let me in"}
            </button>
            <button
              type="button"
              onClick={onResend}
              disabled={cooldown > 0}
              className="link-hand"
              style={{
                background: "none",
                border: 0,
                padding: 0,
                font: "inherit",
                fontSize: 16,
                opacity: cooldown > 0 ? 0.6 : 1,
                cursor: cooldown > 0 ? "default" : "pointer",
              }}
            >
              {cooldown > 0 ? `hold on… (${cooldown})` : "resend the code"}
            </button>
          </div>

          {serverError ? (
            <p
              role="alert"
              className="annot"
              style={{ marginTop: 18, fontSize: 15, display: "block" }}
            >
              {serverError}
            </p>
          ) : null}
        </form>
      </div>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <div className="shell" style={{ maxWidth: 720 }}>
      <p className="crest" style={{ marginTop: 18 }}>
        <span className="crest-dot" />
        PLUS &middot; ONE &middot; one more step
      </p>

      <section style={{ marginTop: 60, position: "relative" }}>
        <Suspense
          fallback={
            <p className="scrawl" style={{ fontSize: 19 }}>
              one sec&hellip;
            </p>
          }
        >
          <VerifyInner />
        </Suspense>
      </section>

      <footer style={{ marginTop: 140, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">PLUS &middot; ONE &middot; v0.1</p>
      </footer>
    </div>
  );
}
