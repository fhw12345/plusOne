"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { register as registerApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { RegisterBody, type RegisterBody as RegisterBodyT } from "@/lib/schemas/auth";

function mapRegisterError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      const detail = typeof err.message === "string" ? err.message : "";
      // The backend distinguishes which uniqueness constraint blew up via
      // the `detail` string. Fall back to email if it's unclear.
      if (detail.includes("username")) return "that username's taken.";
      return "that email's already in the book.";
    }
    if (err.status === 400) {
      const detail = typeof err.message === "string" ? err.message : "";
      if (detail.includes("password")) {
        return "password needs ten characters and a number. one more pass?";
      }
      if (detail.includes("username")) {
        return "username's lowercase, letters and numbers, three to thirty-two.";
      }
      if (detail.includes("email")) {
        return "that email doesn't look right. typo?";
      }
      return "something snagged on the wire. one more try?";
    }
    if (err.status === 503) {
      return "the inbox door is shut on our end right now. give it a minute and try again.";
    }
  }
  return "something snagged on the wire. one more try?";
}

export default function RegisterPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterBodyT>({
    resolver: zodResolver(RegisterBody),
    mode: "onSubmit",
    defaultValues: { username: "", email: "", password: "", confirm: "" },
  });

  const onSubmit = async (values: RegisterBodyT) => {
    setServerError(null);
    try {
      await registerApi({
        username: values.username,
        email: values.email,
        password: values.password,
      });
      router.push(`/verify?email=${encodeURIComponent(values.email)}`);
    } catch (err) {
      setServerError(mapRegisterError(err));
    }
  };

  return (
    <div className="shell" style={{ maxWidth: 720 }}>
      <p className="crest" style={{ marginTop: 18 }}>
        <span className="crest-dot" />
        PLUS &middot; ONE &middot; new page
      </p>

      <section style={{ position: "relative", paddingTop: 60 }}>
        <span
          className="tape tape--mint"
          style={{ top: 28, left: 18, width: 104, height: 24, transform: "rotate(-6deg)" }}
        />
        <span
          className="tape tape--yellow"
          style={{ top: 36, right: 60, width: 88, height: 22, transform: "rotate(6deg)" }}
        />

        <h1 className="hand-xxl" style={{ marginBottom: 16 }}>
          save your page
        </h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 460, transform: "rotate(-.4deg)" }}>
          username, email, a password. that&rsquo;s it.
        </p>

        <div style={{ marginTop: 56, maxWidth: 520, position: "relative" }}>
          <form
            onSubmit={handleSubmit(onSubmit)}
            noValidate
            style={{
              position: "relative",
              padding: "36px 38px 42px",
              background: "hsl(var(--paper-2))",
              boxShadow: "0 16px 30px -16px hsl(0 0% 0% / .22), 0 2px 4px hsl(0 0% 0% / .08)",
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

            <div className="field">
              <label htmlFor="username">username</label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                {...register("username")}
                aria-invalid={errors.username ? "true" : "false"}
              />
              <span className="hint">lowercase, letters and numbers. 3 to 32.</span>
              {errors.username ? (
                <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                  {errors.username.message}
                </span>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="email">your email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="friend@somewhere.com"
                {...register("email")}
                aria-invalid={errors.email ? "true" : "false"}
              />
              <span className="hint">i&rsquo;ll send a code here. no marketing, no resale.</span>
              {errors.email ? (
                <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                  {errors.email.message}
                </span>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="password">password</label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                {...register("password")}
                aria-invalid={errors.password ? "true" : "false"}
              />
              <span className="hint">
                at least 10. one letter, one number. that&rsquo;s the floor.
              </span>
              {errors.password ? (
                <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                  {errors.password.message}
                </span>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="confirm">say it again</label>
              <input
                id="confirm"
                type="password"
                autoComplete="new-password"
                {...register("confirm")}
                aria-invalid={errors.confirm ? "true" : "false"}
              />
              <span className="hint">just to be sure.</span>
              {errors.confirm ? (
                <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                  {errors.confirm.message}
                </span>
              ) : null}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 16 }}>
              <button
                className="btn"
                type="submit"
                disabled={isSubmitting}
                style={{ opacity: isSubmitting ? 0.6 : 1 }}
              >
                {isSubmitting ? "saving…" : "save the page"}
              </button>
              <span className="annot" style={{ fontSize: 16 }}>
                &uarr; press it
              </span>
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

            <p className="annot" style={{ marginTop: 22, fontSize: 14 }}>
              already have one?{" "}
              <a className="link-hand" href="/login" style={{ fontSize: 14 }}>
                let me in
              </a>
              .
            </p>
          </form>
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
