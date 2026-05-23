"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CompanionCard } from "@/components/companions/CompanionCard";
import { CompanionDialog } from "@/components/companions/CompanionDialog";
import { DeleteCompanionDialog } from "@/components/companions/DeleteCompanionDialog";
import { AdminWireLink } from "@/components/AdminWireLink";
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
      <div className="shell">
        <p className="scrawl" style={{ marginTop: 80, fontSize: 19 }}>
          one sec &mdash; opening the address book&hellip;
        </p>
      </div>
    );
  }

  return (
    <div className="shell" style={{ maxWidth: 980 }}>
      <nav className="nav-strip" style={{ marginBottom: 32 }}>
        <p className="crest" style={{ marginRight: "auto" }}>
          <span className="crest-dot" />
          PLUS &middot; ONE
        </p>
        <Link href="/app">your readings</Link>
        <span className="sep" />
        <Link href="/app/trips/new" title="plan a new trip">
          new reading
        </Link>
        <span className="sep" />
        <Link className="is-on" href="/app/companions">
          who you bring
        </Link>
        <span className="sep" />
        <Link href="/app/profile">about you</Link>
        <AdminWireLink />
      </nav>

      <header style={{ position: "relative", padding: "12px 0 32px" }}>
        <span
          className="tape tape--blue"
          style={{ top: -8, left: 240, width: 96, height: 24, transform: "rotate(3deg)" }}
        />
        <h1 className="hand-xxl">who you bring</h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 560, marginTop: 14 }}>
          the people you travel with. their tastes &amp; dealbreakers feed every reading.
        </p>

        <div
          style={{
            position: "absolute",
            top: 18,
            right: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 12,
          }}
        >
          <button
            type="button"
            onClick={openCreate}
            disabled={atCap}
            className="btn btn--red"
            style={{ opacity: atCap ? 0.5 : 1 }}
          >
            + add someone
          </button>
          <span className="annot" style={{ fontSize: 14 }}>
            {companions.length} / {_COMPANION_CAP} in the book
          </span>
        </div>
      </header>

      {atCap ? (
        <div
          role="alert"
          className="ticket"
          style={{ marginBottom: 24, ["--tilt" as never]: ".4deg" }}
        >
          <div className="stamp-row">
            <span className="type" style={{ color: "hsl(var(--signal-snag))" }}>
              full house
            </span>
            <span className="type-sm">{_COMPANION_CAP} max</span>
          </div>
          <p className="body">the book&rsquo;s full. delete someone to make room.</p>
        </div>
      ) : null}

      {isLoading ? (
        <p className="scrawl" style={{ fontSize: 16 }}>
          pulling the names&hellip;
        </p>
      ) : null}
      {isError ? (
        <p role="alert" className="annot" style={{ display: "block" }}>
          couldn&rsquo;t open the address book.
        </p>
      ) : null}

      {!isLoading && !isError && companions.length === 0 ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: 14,
            padding: "32px 28px",
            background: "hsl(var(--paper-2))",
            transform: "rotate(-.5deg)",
            border: "1px solid hsl(var(--kraft))",
            maxWidth: 520,
          }}
        >
          <p className="hand" style={{ fontSize: 24 }}>
            no one in the book yet.
          </p>
          <p className="scrawl">
            companions ride along on a reading &mdash; i&rsquo;ll match the picks to who&rsquo;s
            with you.
          </p>
          <p className="scrawl">
            add the people you usually travel with &mdash; i&rsquo;ll plan around their tastes.
          </p>
          <button type="button" onClick={openCreate} className="btn">
            + add the first one
          </button>
        </div>
      ) : null}

      {companions.length > 0 ? (
        <section className="gallery" style={{ marginTop: 12 }}>
          {companions.map((c) => (
            <CompanionCard key={c.id} companion={c} onEdit={openEdit} onDelete={openDelete} />
          ))}
        </section>
      ) : null}

      <CompanionDialog open={dialogOpen} onOpenChange={setDialogOpen} companion={editing} />
      <DeleteCompanionDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        companion={deleteTarget}
      />

      <footer style={{ marginTop: 100, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">PLUS &middot; ONE &middot; who you bring &middot; v0.1</p>
      </footer>
    </div>
  );
}
