"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import { useAuthStore } from "@/store/auth";

interface LogEntry {
  ts: string;
  level: string;
  source: "backend" | "frontend";
  message: string;
  logger?: string | null;
}

const MAX_PER_PANE = 1000;

function levelColor(level: string): string {
  const up = level.toUpperCase();
  if (up === "ERROR" || up === "CRITICAL" || up === "FATAL") {
    return "hsl(var(--signal-snag))";
  }
  if (up === "WARN" || up === "WARNING") {
    return "hsl(var(--signal-wait))";
  }
  if (up === "DEBUG" || up === "TRACE") {
    return "hsl(var(--ink-3))";
  }
  // INFO + log + anything else falls back to primary ink.
  return "hsl(var(--ink))";
}

function formatTs(iso: string): string {
  // HH:mm:ss.SSS — no Date.toLocaleString reliance (varies by locale).
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

interface PaneProps {
  title: string;
  rows: LogEntry[];
  paused: boolean;
  onTogglePaused: () => void;
  onClear: () => void;
  tilt: string;
}

function Pane({ title, rows, paused, onTogglePaused, onClear, tilt }: PaneProps) {
  const bodyRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom on new rows unless paused.
  useEffect(() => {
    if (paused) return;
    const el = bodyRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [rows, paused]);

  return (
    <div
      style={{
        position: "relative",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(var(--kraft))",
        boxShadow: "0 12px 24px -16px hsl(0 0% 0% / .22)",
        transform: `rotate(${tilt})`,
        padding: "18px 18px 16px",
        display: "flex",
        flexDirection: "column",
        minHeight: 480,
        maxHeight: "70vh",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 12,
          marginBottom: 10,
          paddingBottom: 8,
          borderBottom: "1px dotted hsl(var(--kraft))",
        }}
      >
        <p className="type" style={{ marginRight: "auto" }}>
          {title}
        </p>
        <button
          type="button"
          onClick={onTogglePaused}
          className="link-hand"
          style={{
            background: "none",
            border: 0,
            padding: 0,
            font: "inherit",
            fontSize: 14,
          }}
        >
          {paused ? "let it run" : "hold the page"}
        </button>
        <button
          type="button"
          onClick={onClear}
          className="link-hand"
          style={{
            background: "none",
            border: 0,
            padding: 0,
            font: "inherit",
            fontSize: 14,
          }}
        >
          clear the page
        </button>
      </div>

      <div
        ref={bodyRef}
        style={{
          flex: 1,
          overflowY: "auto",
          fontFamily: "'Courier New', monospace",
          fontSize: 13,
          lineHeight: 1.5,
          color: "hsl(var(--ink))",
        }}
      >
        {rows.length === 0 ? (
          <p className="scrawl" style={{ fontSize: 15, opacity: 0.7 }}>
            nothing on the wire yet&hellip;
          </p>
        ) : (
          rows.map((row, i) => (
            <div
              key={`${row.ts}-${i}`}
              style={{
                display: "grid",
                gridTemplateColumns: "92px 56px 1fr",
                gap: 8,
                padding: "2px 0",
                color: levelColor(row.level),
              }}
            >
              <span style={{ color: "hsl(var(--ink-3))" }}>{formatTs(row.ts)}</span>
              <span style={{ textTransform: "lowercase" }}>{row.level.toLowerCase()}</span>
              <span style={{ wordBreak: "break-word", whiteSpace: "pre-wrap" }}>{row.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function AdminLogsPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const { data: user, isLoading: userLoading } = useCurrentUser();

  const [backendRows, setBackendRows] = useState<LogEntry[]>([]);
  const [frontendRows, setFrontendRows] = useState<LogEntry[]>([]);
  const [backendPaused, setBackendPaused] = useState(false);
  const [frontendPaused, setFrontendPaused] = useState(false);
  // Paused panes still receive rows — they queue here so they don't drop on
  // the floor while the user reads. On unpause we splice the queue in.
  const backendQueue = useRef<LogEntry[]>([]);
  const frontendQueue = useRef<LogEntry[]>([]);

  useEffect(() => {
    if (!hydrated) return;
    if (!token) {
      router.replace("/login");
      return;
    }
    if (!userLoading && user && !user.is_admin) {
      router.replace("/app");
    }
  }, [hydrated, token, user, userLoading, router]);

  // Open the SSE connection once we know the user is admin.
  // EventSource cannot carry an Authorization header, so we put the JWT on
  // the query string. The backend admin SSE route accepts `?token=...` as an
  // alternative to the Bearer header for exactly this workaround.
  // Cookies are also sent via `withCredentials: true` so a cookie-based
  // session works too.
  useEffect(() => {
    if (!hydrated || !token || !user?.is_admin) return;

    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const url = `${base}/api/admin/logs/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url, { withCredentials: true });

    const onLog = (e: MessageEvent) => {
      let entry: LogEntry | null = null;
      try {
        entry = JSON.parse(e.data) as LogEntry;
      } catch {
        return;
      }
      if (!entry || (entry.source !== "backend" && entry.source !== "frontend")) {
        return;
      }
      const target = entry.source;
      const queue = target === "backend" ? backendQueue.current : frontendQueue.current;
      const paused = target === "backend" ? backendPaused : frontendPaused;
      const setter = target === "backend" ? setBackendRows : setFrontendRows;

      if (paused) {
        queue.push(entry);
        if (queue.length > MAX_PER_PANE) queue.splice(0, queue.length - MAX_PER_PANE);
        return;
      }
      setter((prev) => {
        const next = prev.concat(entry as LogEntry);
        if (next.length > MAX_PER_PANE) next.splice(0, next.length - MAX_PER_PANE);
        return next;
      });
    };

    es.addEventListener("log", onLog as EventListener);
    // Treat the default message event the same way — the backend uses a
    // named "log" event but we accept both to be defensive.
    es.onmessage = onLog;

    return () => {
      es.removeEventListener("log", onLog as EventListener);
      es.close();
    };
    // We intentionally re-create the EventSource only when the token or
    // admin-ness flips. Pause state is read live via refs above so it
    // doesn't churn the connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, token, user?.is_admin]);

  // Flush queued rows on unpause.
  useEffect(() => {
    if (backendPaused) return;
    if (backendQueue.current.length === 0) return;
    const drained = backendQueue.current.splice(0);
    setBackendRows((prev) => {
      const next = prev.concat(drained);
      if (next.length > MAX_PER_PANE) next.splice(0, next.length - MAX_PER_PANE);
      return next;
    });
  }, [backendPaused]);

  useEffect(() => {
    if (frontendPaused) return;
    if (frontendQueue.current.length === 0) return;
    const drained = frontendQueue.current.splice(0);
    setFrontendRows((prev) => {
      const next = prev.concat(drained);
      if (next.length > MAX_PER_PANE) next.splice(0, next.length - MAX_PER_PANE);
      return next;
    });
  }, [frontendPaused]);

  const gate = useMemo(() => {
    if (!hydrated) return "wait" as const;
    if (!token) return "wait" as const;
    if (userLoading || !user) return "wait" as const;
    if (!user.is_admin) return "deny" as const;
    return "ok" as const;
  }, [hydrated, token, user, userLoading]);

  if (gate !== "ok") {
    return (
      <div className="shell">
        <p className="scrawl" style={{ marginTop: 80, fontSize: 19 }}>
          one sec&hellip;
        </p>
      </div>
    );
  }

  return (
    <div className="shell" style={{ maxWidth: 1200 }}>
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
        <Link href="/app/companions">who you bring</Link>
        <span className="sep" />
        <Link href="/app/profile">about you</Link>
        <span className="sep" />
        <Link className="is-on" href="/admin/logs">
          the wire
        </Link>
      </nav>

      <header style={{ position: "relative", padding: "12px 0 28px" }}>
        <span
          className="tape tape--red"
          style={{ top: -8, left: 220, width: 96, height: 24, transform: "rotate(-3deg)" }}
        />
        <h1 className="hand-xxl">the wire (admin)</h1>
        <p className="annot" style={{ marginTop: 12, fontSize: 15 }}>
          live. last 1000. clears on restart.
        </p>
      </header>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 18,
          alignItems: "stretch",
        }}
      >
        <Pane
          title="backend"
          rows={backendRows}
          paused={backendPaused}
          onTogglePaused={() => setBackendPaused((p) => !p)}
          onClear={() => setBackendRows([])}
          tilt="-0.3deg"
        />
        <Pane
          title="frontend"
          rows={frontendRows}
          paused={frontendPaused}
          onTogglePaused={() => setFrontendPaused((p) => !p)}
          onClear={() => setFrontendRows([])}
          tilt="0.3deg"
        />
      </section>

      <footer style={{ marginTop: 80, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">PLUS &middot; ONE &middot; the wire &middot; v0.1</p>
      </footer>
    </div>
  );
}
