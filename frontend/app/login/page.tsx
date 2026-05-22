"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/lib/api/client";
import {
  login,
  loginWithCode,
  requestCode,
} from "@/lib/api/auth";
import {
  CodeSchema,
  EmailSchema,
  LoginBody,
  type LoginBody as LoginBodyT,
} from "@/lib/schemas/auth";
import { useAuthStore } from "@/store/auth";

type Tab = "password" | "code";

const RequestForm = z.object({ email: EmailSchema });
type RequestFormT = z.infer<typeof RequestForm>;

const SubmitCodeForm = z.object({
  email: EmailSchema,
  code: CodeSchema,
});
type SubmitCodeFormT = z.infer<typeof SubmitCodeForm>;

const RESEND_COOLDOWN_S = 60;

function mapLoginError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 423) return "you've tried too many times. wait 15 minutes.";
    if (err.status === 401) {
      const detail = typeof err.message === "string" ? err.message : "";
      if (detail === "email_not_verified") {
        return "your email's still unread. go check the code we sent.";
      }
      return "wrong password or unknown name. try again?";
    }
    if (err.status === 400) return "the code didn't match. try again?";
    if (err.status === 503) {
      return "the inbox door is shut on our end right now. give it a minute and try again.";
    }
  }
  return "something snagged on the wire. one more try?";
}

function PasswordTab() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginBodyT>({
    resolver: zodResolver(LoginBody),
    mode: "onSubmit",
    defaultValues: { identifier: "", password: "" },
  });

  const onSubmit = async (values: LoginBodyT) => {
    setServerError(null);
    try {
      const res = await login(values);
      setSession(res.access_token, res.user);
      router.push("/app");
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 401 &&
        err.message === "email_not_verified"
      ) {
        router.push(`/verify?email=${encodeURIComponent(values.identifier)}`);
        return;
      }
      setServerError(mapLoginError(err));
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <div className="field">
        <label htmlFor="identifier">name or email</label>
        <input
          id="identifier"
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          {...register("identifier")}
          aria-invalid={errors.identifier ? "true" : "false"}
        />
        <span className="hint">whichever you remember.</span>
        {errors.identifier ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.identifier.message}
          </span>
        ) : null}
      </div>

      <div className="field">
        <label htmlFor="password">password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          {...register("password")}
          aria-invalid={errors.password ? "true" : "false"}
        />
        {errors.password ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.password.message}
          </span>
        ) : null}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 12 }}>
        <button
          className="btn"
          type="submit"
          disabled={isSubmitting}
          style={{ opacity: isSubmitting ? 0.6 : 1 }}
        >
          {isSubmitting ? "letting you in…" : "let me in"}
        </button>
        <span className="annot" style={{ fontSize: 16 }}>
          &uarr; press it
        </span>
      </div>

      {serverError ? (
        <p role="alert" className="annot" style={{ marginTop: 18, fontSize: 15, display: "block" }}>
          {serverError}
        </p>
      ) : null}
    </form>
  );
}

function CodeTab() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);
  const [phase, setPhase] = useState<"request" | "submit">("request");
  const [email, setEmail] = useState("");
  const [serverError, setServerError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  // Tick the resend cooldown once a second once it's armed. Cleared on
  // unmount so we don't leak the interval if the user flips tabs mid-flow.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const requestForm = useForm<RequestFormT>({
    resolver: zodResolver(RequestForm),
    mode: "onSubmit",
    defaultValues: { email: "" },
  });

  const submitForm = useForm<SubmitCodeFormT>({
    resolver: zodResolver(SubmitCodeForm),
    mode: "onSubmit",
    defaultValues: { email: "", code: "" },
  });

  const onRequest = async (values: RequestFormT) => {
    setServerError(null);
    try {
      await requestCode({ email: values.email });
      setEmail(values.email);
      submitForm.reset({ email: values.email, code: "" });
      setPhase("submit");
      setCooldown(RESEND_COOLDOWN_S);
    } catch (err) {
      setServerError(mapLoginError(err));
    }
  };

  const onResend = async () => {
    if (cooldown > 0) {
      setServerError("hold on a sec — i just sent one.");
      return;
    }
    setServerError(null);
    try {
      await requestCode({ email });
      setCooldown(RESEND_COOLDOWN_S);
    } catch (err) {
      setServerError(mapLoginError(err));
    }
  };

  const onSubmitCode = async (values: SubmitCodeFormT) => {
    setServerError(null);
    try {
      const res = await loginWithCode(values);
      setSession(res.access_token, res.user);
      router.push("/app");
    } catch (err) {
      setServerError(mapLoginError(err));
    }
  };

  if (phase === "request") {
    return (
      <form onSubmit={requestForm.handleSubmit(onRequest)} noValidate>
        <div className="field">
          <label htmlFor="code-email">your email</label>
          <input
            id="code-email"
            type="email"
            autoComplete="email"
            placeholder="friend@somewhere.com"
            {...requestForm.register("email")}
            aria-invalid={requestForm.formState.errors.email ? "true" : "false"}
          />
          {requestForm.formState.errors.email ? (
            <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
              {requestForm.formState.errors.email.message}
            </span>
          ) : null}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 12 }}>
          <button
            className="btn"
            type="submit"
            disabled={requestForm.formState.isSubmitting}
            style={{ opacity: requestForm.formState.isSubmitting ? 0.6 : 1 }}
          >
            {requestForm.formState.isSubmitting ? "sending…" : "send me a code"}
          </button>
        </div>

        {serverError ? (
          <p role="alert" className="annot" style={{ marginTop: 18, fontSize: 15, display: "block" }}>
            {serverError}
          </p>
        ) : null}
      </form>
    );
  }

  return (
    <form onSubmit={submitForm.handleSubmit(onSubmitCode)} noValidate>
      <p className="annot" style={{ display: "block", marginBottom: 14 }}>
        sent to {email}
      </p>

      <div className="field">
        <label htmlFor="code">the code</label>
        <input
          id="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          {...submitForm.register("code")}
          aria-invalid={submitForm.formState.errors.code ? "true" : "false"}
        />
        <span className="hint">just the numbers.</span>
        {submitForm.formState.errors.code ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {submitForm.formState.errors.code.message}
          </span>
        ) : null}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 12 }}>
        <button
          className="btn"
          type="submit"
          disabled={submitForm.formState.isSubmitting}
          style={{ opacity: submitForm.formState.isSubmitting ? 0.6 : 1 }}
        >
          {submitForm.formState.isSubmitting ? "letting you in…" : "let me in"}
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
          {cooldown > 0 ? `hold on… (${cooldown})` : "send another one"}
        </button>
      </div>

      {serverError ? (
        <p role="alert" className="annot" style={{ marginTop: 18, fontSize: 15, display: "block" }}>
          {serverError}
        </p>
      ) : null}
    </form>
  );
}

export default function LoginPage() {
  const [tab, setTab] = useState<Tab>("password");

  return (
    <div className="shell" style={{ maxWidth: 720 }}>
      <p className="crest" style={{ marginTop: 18 }}>
        <span className="crest-dot" />
        PLUS &middot; ONE &middot; say hello
      </p>

      <section style={{ position: "relative", paddingTop: 60 }}>
        <span
          className="tape tape--mint"
          style={{ top: 32, left: 24, width: 110, height: 26, transform: "rotate(-5deg)" }}
        />
        <span
          className="tape tape--yellow"
          style={{ top: 38, right: 80, width: 80, height: 22, transform: "rotate(7deg)" }}
        />

        <h1 className="hand-xxl" style={{ marginBottom: 16 }}>
          let me in
        </h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 460, transform: "rotate(-.4deg)" }}>
          password, or a code. your call.
        </p>

        <div style={{ marginTop: 56, maxWidth: 480, position: "relative" }}>
          <div
            style={{
              position: "relative",
              padding: "36px 38px 42px",
              background: "hsl(var(--paper-2))",
              boxShadow:
                "0 16px 30px -16px hsl(0 0% 0% / .22), 0 2px 4px hsl(0 0% 0% / .08)",
              transform: "rotate(-1deg)",
            }}
          >
            <span
              className="tape tape--blue"
              style={{
                top: -12,
                left: "50%",
                width: 110,
                height: 24,
                transform: "translateX(-50%) rotate(2deg)",
              }}
            />

            <div
              role="tablist"
              aria-label="how you want to sign in"
              style={{ display: "flex", gap: 10, marginBottom: 22 }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={tab === "password"}
                onClick={() => setTab("password")}
                className="btn"
                style={{
                  opacity: tab === "password" ? 1 : 0.55,
                  fontSize: 15,
                  padding: "8px 14px",
                }}
              >
                password
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "code"}
                onClick={() => setTab("code")}
                className="btn"
                style={{
                  opacity: tab === "code" ? 1 : 0.55,
                  fontSize: 15,
                  padding: "8px 14px",
                }}
              >
                by code
              </button>
            </div>

            {tab === "password" ? <PasswordTab /> : <CodeTab />}

            <p className="annot" style={{ marginTop: 22, fontSize: 14 }}>
              no page yet?{" "}
              <a className="link-hand" href="/register" style={{ fontSize: 14 }}>
                save one
              </a>
              .
            </p>
          </div>
        </div>
      </section>

      <footer style={{ marginTop: 120, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">
          PLUS &middot; ONE &middot; v0.1 &middot; tokyo &middot; taipei &middot; everywhere quiet
        </p>
      </footer>
    </div>
  );
}
