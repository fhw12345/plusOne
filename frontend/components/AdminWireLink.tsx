"use client";

import Link from "next/link";

import { useCurrentUser } from "@/hooks/useCurrentUser";

interface AdminWireLinkProps {
  /** When true, render with the active "is-on" class. */
  active?: boolean;
}

/**
 * Conditional nav-strip entry for the admin log panel. Rendered only when
 * the current user has `is_admin: true`. Each page nav-strip pulls this
 * in next to the other entries — we keep it as its own component so the
 * admin check lives in one place.
 */
export function AdminWireLink({ active = false }: AdminWireLinkProps) {
  const { data: user } = useCurrentUser();
  if (!user?.is_admin) return null;
  return (
    <>
      <span className="sep" />
      <Link className={active ? "is-on" : undefined} href="/admin/logs">
        the wire
      </Link>
    </>
  );
}
