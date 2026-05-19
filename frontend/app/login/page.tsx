"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/lib/api/client";
import { requestLink } from "@/lib/api/auth";
import { EmailSchema } from "@/lib/schemas/auth";

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
        setServerError("Email delivery is not configured on the server. Please try again later.");
      } else {
        setServerError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-bold tracking-tight">Sign in</h1>
      <p className="text-muted-foreground text-sm">
        Enter your email and we&apos;ll send you a magic link to sign in. No password required.
      </p>

      {submitted ? (
        <div role="status" className="border-foreground/20 rounded border p-4 text-sm">
          <p className="font-medium">Check your inbox</p>
          <p className="text-muted-foreground mt-1">
            We sent you a sign-in link. Click it to continue.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <label className="flex flex-col gap-2 text-sm">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              className="border-foreground/20 rounded border px-3 py-2 text-base"
              {...register("email")}
              aria-invalid={errors.email ? "true" : "false"}
            />
            {errors.email ? (
              <span role="alert" className="text-sm text-red-600">
                {errors.email.message}
              </span>
            ) : null}
          </label>

          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-foreground text-background rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {isSubmitting ? "Sending…" : "Send magic link"}
          </button>

          {serverError ? (
            <p role="alert" className="text-sm text-red-600">
              {serverError}
            </p>
          ) : null}
        </form>
      )}
    </main>
  );
}
