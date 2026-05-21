"use client";

import { useId, useState } from "react";

import { tiltStyle } from "@/lib/scrapbook/tilt";
import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";

export interface ItemCardProps {
  item: JoinedItem;
  index?: number;
}

const VERDICT_BY_CLASS: Record<string, { text: string; signal: "live" | "done" | "wait" | "snag" }> = {
  local_gem: { text: "this one ★", signal: "done" },
  tourist_trap: { text: "skip", signal: "snag" },
  neutral: { text: "okay-ish", signal: "wait" },
  insufficient: { text: "thin signal", signal: "wait" },
};

const PERLANG_TINT: Record<string, string> = {
  local_gem: "hsl(var(--signal-done))",
  tourist_trap: "hsl(var(--signal-snag))",
  neutral: "hsl(var(--ink-3))",
  insufficient: "hsl(var(--ink-3))",
};

function shortHost(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url.slice(0, 40);
  }
}

function truncate(s: string, n = 140): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1).trimEnd() + "…";
}

const TAPE_BY_INDEX = ["tape--mint", "tape--blue", "tape--yellow", "tape--red"] as const;

export function ItemCard({ item, index = 0 }: ItemCardProps) {
  const view = item as JoinedItemView;
  const name = view.candidate?.name ?? "untitled";
  const evidence = view.evidence ?? [];
  const evidenceCount = evidence.length;
  const verdict = view.classification ? VERDICT_BY_CLASS[view.classification] ?? null : null;
  const confidence =
    typeof view.confidence === "number" && !Number.isNaN(view.confidence)
      ? Math.round(view.confidence * 100)
      : null;
  const area = view.candidate?.area ?? null;
  const style = view.candidate?.style ?? null;
  const summary = view.summary ?? "";
  const rationale = view.candidate?.rationale ?? "";
  const classificationEn = view.classification_en ?? null;
  const classificationZh = view.classification_zh ?? null;
  const hasPerLang = classificationEn != null || classificationZh != null;

  const [open, setOpen] = useState(false);
  const bodyId = useId();
  const tape = TAPE_BY_INDEX[index % TAPE_BY_INDEX.length];
  const areaStyleLine = [area, style].filter(Boolean).join(" · ");

  return (
    <article
      className="place-card"
      style={{
        position: "relative",
        padding: "20px 22px",
        background: "hsl(var(--paper))",
        border: "1px solid hsl(var(--kraft))",
        boxShadow: "0 6px 14px -10px hsl(0 0% 0% / .25)",
        ...tiltStyle(name + index),
        transform: "rotate(var(--tilt, 0deg))",
      }}
    >
      <span className={`tape ${tape} cnr`} />

      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div style={{ flex: "1 1 60%", minWidth: 0 }}>
          <p className="hand" style={{ fontSize: 26, lineHeight: 1.1, color: "hsl(var(--ink))" }}>
            {name}
          </p>
          {areaStyleLine ? (
            <p className="scrawl" style={{ fontSize: 14, marginTop: 4 }}>
              {areaStyleLine}
            </p>
          ) : null}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
          {verdict ? (
            <span
              className="verdict"
              style={{ position: "static", fontSize: 16, lineHeight: 1 }}
            >
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  marginRight: 6,
                  verticalAlign: 1,
                  background: `hsl(var(--signal-${verdict.signal}))`,
                }}
              />
              {verdict.text}
            </span>
          ) : null}
          {confidence !== null ? (
            <span className="type" style={{ color: "hsl(var(--ink-3))" }}>
              ~{confidence}%
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls={bodyId}
            aria-label={`${open ? "fold up" : "unfold"} ${name}`}
            className="link-hand"
            style={{ font: "inherit", fontSize: 16, background: "none", border: 0, padding: 0 }}
          >
            {open ? "fold up" : "unfold →"}
          </button>
        </div>
      </header>

      {hasPerLang ? (
        <div
          data-testid="per-lang-badges"
          aria-label="Per-language classifications"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            marginTop: 10,
            fontSize: 14,
            color: "hsl(var(--ink-3))",
          }}
        >
          {classificationEn != null ? (
            <span data-perlang="en" style={{ color: PERLANG_TINT[classificationEn] }}>
              <span className="type" style={{ marginRight: 4 }}>
                EN
              </span>
              {classificationEn}
            </span>
          ) : null}
          {classificationZh != null ? (
            <span data-perlang="zh" style={{ color: PERLANG_TINT[classificationZh] }}>
              <span className="type" style={{ marginRight: 4 }}>
                ZH
              </span>
              {classificationZh}
            </span>
          ) : null}
          {evidenceCount > 0 ? (
            <span style={{ color: "hsl(var(--ink-3))" }}>
              <span className="type" style={{ marginRight: 4 }}>
                sources
              </span>
              {evidenceCount}
            </span>
          ) : null}
        </div>
      ) : evidenceCount > 0 ? (
        <p className="scrawl" style={{ fontSize: 14, marginTop: 10, color: "hsl(var(--ink-3))" }}>
          <span className="type" style={{ marginRight: 4 }}>
            sources
          </span>
          {evidenceCount}
        </p>
      ) : null}

      <div
        id={bodyId}
        hidden={!open}
        style={{
          display: open ? "block" : "none",
          marginTop: 16,
          paddingTop: 16,
          borderTop: "1px dotted hsl(var(--kraft))",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {summary ? (
            <p className="hand" style={{ fontSize: 18, lineHeight: 1.3, color: "hsl(var(--ink))" }}>
              {summary}
            </p>
          ) : null}
          {evidence.length > 0 ? (
            <div>
              <p className="type" style={{ marginBottom: 6 }}>
                where it came up
              </p>
              <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 8 }}>
                {evidence.map((ev, idx) => {
                  const url = ev?.url ?? "";
                  const snippet = ev?.snippet ?? "";
                  const source = ev?.source ?? "source";
                  const label = `${source} · ${shortHost(url)}`;
                  return (
                    <li key={idx} style={{ fontSize: 14 }}>
                      {url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="link-hand"
                          style={{ fontSize: 15 }}
                        >
                          {label}
                        </a>
                      ) : (
                        <span style={{ color: "hsl(var(--ink-2))" }}>{label}</span>
                      )}
                      {snippet ? (
                        <p
                          className="scrawl"
                          style={{ fontSize: 14, color: "hsl(var(--ink-3))", marginTop: 2 }}
                        >
                          {truncate(snippet)}
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
          {rationale ? (
            <p className="scrawl" style={{ fontSize: 14, color: "hsl(var(--ink-3))" }}>
              <span className="type" style={{ marginRight: 4 }}>
                why
              </span>
              {rationale}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}
