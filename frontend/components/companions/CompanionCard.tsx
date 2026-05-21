"use client";

import { tiltStyle } from "@/lib/scrapbook/tilt";
import type { CompanionResponse } from "@/lib/schemas/companions";

interface CompanionCardProps {
  companion: CompanionResponse;
  onEdit: (companion: CompanionResponse) => void;
  onDelete: (companion: CompanionResponse) => void;
}

const TOP = 3;
const TAPES = ["tape--mint", "tape--blue", "tape--yellow", "tape--red"] as const;

function topItems(items: readonly string[]): { shown: string[]; extra: number } {
  return { shown: items.slice(0, TOP), extra: Math.max(0, items.length - TOP) };
}

function pickTape(seed: string): (typeof TAPES)[number] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0;
  return TAPES[Math.abs(h) % TAPES.length]!;
}

export function CompanionCard({ companion, onEdit, onDelete }: CompanionCardProps) {
  const loves = topItems(companion.explicit_preferences.loves);
  const hates = topItems(companion.explicit_preferences.hates);
  const dietary = topItems(companion.constraints.dietary);
  const tape = pickTape(companion.id);

  return (
    <article
      className="photo-card is-typed"
      style={{ ...tiltStyle(companion.id), display: "flex", flexDirection: "column" }}
    >
      <span className={`tape ${tape} cnr`} />

      <div
        className="photo"
        data-label={companion.name}
        style={{ minHeight: 96 }}
      />
      <p className="cap">{companion.name}</p>

      <div style={{ display: "grid", gap: 8, marginTop: 6 }}>
        {loves.shown.length > 0 ? (
          <p className="scrawl" style={{ fontSize: 15 }}>
            <span className="type" style={{ marginRight: 6 }}>
              loves
            </span>
            {loves.shown.join(" · ")}
            {loves.extra > 0 ? ` +${loves.extra}` : null}
          </p>
        ) : null}
        {hates.shown.length > 0 ? (
          <p className="scrawl" style={{ fontSize: 15, color: "hsl(var(--signal-snag))" }}>
            <span className="type" style={{ marginRight: 6, color: "hsl(var(--signal-snag))" }}>
              avoid
            </span>
            {hates.shown.join(" · ")}
            {hates.extra > 0 ? ` +${hates.extra}` : null}
          </p>
        ) : null}
        {dietary.shown.length > 0 ? (
          <p className="scrawl" style={{ fontSize: 15 }}>
            <span className="type" style={{ marginRight: 6 }}>
              diet
            </span>
            {dietary.shown.join(" · ")}
            {dietary.extra > 0 ? ` +${dietary.extra}` : null}
          </p>
        ) : null}
        {companion.constraints.mobility || companion.constraints.max_walking != null ? (
          <p className="scrawl" style={{ fontSize: 14, color: "hsl(var(--ink-3))" }}>
            {companion.constraints.mobility ? `${companion.constraints.mobility}` : null}
            {companion.constraints.mobility && companion.constraints.max_walking != null
              ? " · "
              : ""}
            {companion.constraints.max_walking != null
              ? `${companion.constraints.max_walking} km/day`
              : null}
          </p>
        ) : null}
      </div>

      <div
        style={{
          display: "flex",
          gap: 14,
          marginTop: "auto",
          paddingTop: 18,
          borderTop: "1px dotted hsl(var(--kraft))",
        }}
      >
        <button
          type="button"
          onClick={() => onEdit(companion)}
          aria-label={`edit ${companion.name}`}
          className="link-hand"
          style={{ font: "inherit", fontSize: 16, background: "none", border: 0, padding: 0 }}
        >
          edit
        </button>
        <button
          type="button"
          onClick={() => onDelete(companion)}
          aria-label={`delete ${companion.name}`}
          className="link-hand"
          style={{
            font: "inherit",
            fontSize: 16,
            background: "none",
            border: 0,
            padding: 0,
            color: "hsl(var(--signal-snag))",
          }}
        >
          remove
        </button>
      </div>
    </article>
  );
}
