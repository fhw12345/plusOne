"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/lib/api/client";
import { requestLink } from "@/lib/api/auth";
import { EmailSchema } from "@/lib/schemas/auth";
import { useState } from "react";

const FormSchema = z.object({ email: EmailSchema });
type FormValues = z.infer<typeof FormSchema>;

export default function LoginPage() {
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(FormSchema),
    mode: "onSubmit",
    defaultValues: { email: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      await requestLink(values.email);
      setSubmitted(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setServerError(
          "the inbox door is shut on our end right now. give it a minute and try again.",
        );
      } else {
        setServerError("something snagged. try once more.");
      }
    }
  };

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
          i&apos;ll send you a link &mdash; like a sticky note, but in your inbox.
        </p>

        <div style={{ marginTop: 56, maxWidth: 480, position: "relative" }}>
          <div
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

            {submitted ? (
              <div role="status">
                <p className="hand" style={{ fontSize: 24 }}>
                  okay &mdash; sent. <span className="highlight">check your inbox.</span>
                </p>
                <p className="scrawl" style={{ marginTop: 6 }}>
                  the link will look like a sticky note. click it and you&apos;re in.
                </p>
                <p className="annot" style={{ marginTop: 22, fontSize: 16 }}>
                  ps &mdash; if it doesn&apos;t show up, peek in the spam folder.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit(onSubmit)} noValidate>
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
                  <span className="hint">
                    i&apos;ll never sell this. or use it for anything except finding you.
                  </span>
                  {errors.email ? (
                    <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
                      {errors.email.message}
                    </span>
                  ) : null}
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                    marginTop: 12,
                  }}
                >
                  <button
                    className="btn"
                    type="submit"
                    disabled={isSubmitting}
                    style={{ opacity: isSubmitting ? 0.6 : 1 }}
                  >
                    {isSubmitting ? "sending…" : "send the link"}
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
              </form>
            )}
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
