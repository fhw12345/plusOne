"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useCurrentUser } from "@/hooks/useCurrentUser";
import { installAdminConsoleTap, uninstallAdminConsoleTap } from "@/lib/admin/console-tap";

function AdminConsoleTapMount() {
  // Reading useCurrentUser here is safe — the query is gated by `enabled`
  // so signed-out users don't trigger a /me request.
  const { data: user } = useCurrentUser();

  // Re-install whenever the user identity flips. The tap itself is
  // idempotent for the same user and a no-op for non-admins.
  useEffect(() => {
    installAdminConsoleTap(user ?? null);
  }, [user]);

  // Full restore on unmount of the provider tree.
  useEffect(() => {
    return () => uninstallAdminConsoleTap();
  }, []);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  // One client per mount — `useState(() => ...)` guarantees we don't recreate
  // it on every render (would invalidate caches and lose in-flight queries).
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AdminConsoleTapMount />
      {children}
    </QueryClientProvider>
  );
}
