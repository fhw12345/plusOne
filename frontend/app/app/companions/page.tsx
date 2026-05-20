"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CompanionCard } from "@/components/companions/CompanionCard";
import { CompanionDialog } from "@/components/companions/CompanionDialog";
import { DeleteCompanionDialog } from "@/components/companions/DeleteCompanionDialog";
import { Button } from "@/components/ui/button";
import { useCompanions } from "@/hooks/useCompanions";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import type { CompanionResponse } from "@/lib/schemas/companions";
import { useAuthStore } from "@/store/auth";

const _COMPANION_CAP = 20;

export default function CompanionsPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  const [editing, setEditing] = useState<CompanionResponse | undefined>(undefined);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CompanionResponse | undefined>(undefined);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const { data, isLoading, isError } = useCompanions();
  const companions = data?.companions ?? [];
  const atCap = companions.length >= _COMPANION_CAP;

  const openCreate = () => {
    setEditing(undefined);
    setDialogOpen(true);
  };
  const openEdit = (c: CompanionResponse) => {
    setEditing(c);
    setDialogOpen(true);
  };
  const openDelete = (c: CompanionResponse) => {
    setDeleteTarget(c);
    setDeleteOpen(true);
  };

  if (!hydrated || !token) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Companions</h1>
          <p className="text-foreground/70 mt-1 text-sm">
            People you travel with. Their preferences feed into every trip plan.
          </p>
        </div>
        <Link href="/app" className="border-foreground/20 rounded border px-3 py-1.5 text-sm">
          Back to trips
        </Link>
      </header>

      {atCap ? (
        <p
          role="alert"
          className="rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          You&apos;ve reached the {_COMPANION_CAP}-companion limit. Delete one to add more.
        </p>
      ) : null}

      <div className="flex items-center justify-end">
        <Button type="button" onClick={openCreate} disabled={atCap}>
          Add companion
        </Button>
      </div>

      {isLoading ? <p className="text-foreground/60 text-sm">Loading companions…</p> : null}
      {isError ? (
        <p role="alert" className="text-sm text-red-600">
          Couldn&apos;t load your companions.
        </p>
      ) : null}

      {!isLoading && !isError && companions.length === 0 ? (
        <p className="text-foreground/60 text-sm">No companions yet. Add one above.</p>
      ) : null}

      <ul className="flex flex-col gap-3">
        {companions.map((c) => (
          <li key={c.id}>
            <CompanionCard companion={c} onEdit={openEdit} onDelete={openDelete} />
          </li>
        ))}
      </ul>

      <CompanionDialog open={dialogOpen} onOpenChange={setDialogOpen} companion={editing} />
      <DeleteCompanionDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        companion={deleteTarget}
      />
    </main>
  );
}
