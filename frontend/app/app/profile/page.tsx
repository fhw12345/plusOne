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
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
          <p className="text-foreground/70 mt-1 text-sm">
            Tell us what you love and hate — we&apos;ll bake it into every trip.
          </p>
        </div>
        <Link href="/app" className="border-foreground/20 rounded border px-3 py-1.5 text-sm">
          Back to trips
        </Link>
      </header>
      <ProfileForm />
    </main>
  );
}
