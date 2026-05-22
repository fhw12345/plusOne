"use client";

import { useId, useState } from "react";

import { tiltStyle } from "@/lib/scrapbook/tilt";
import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import { resolveClassification } from "@/lib/trips/resolveClassification";
import type { Perspective } from "@/store/reportPrefs";

export interface ItemCardProps {
  item: JoinedItem;
  index?: number;
  // PRD batch-2r §4.2(d): passed by ReportTabs from the same store read
  // (avoids each card re-subscribing). Defaults to ``fused`` so callers
  // outside the tabbed report (and old tests) keep today's behaviour.
  perspective?: Perspective;
  // PRD batch-2p §4.2: the trip's party (user_id + companion_ids), used
  // together with ``partyNames`` to render per-person ``match_scores``
  // labels in the expanded view. Both are optional — without them the
  // match line is hidden (no labels = no signal worth showing).
  party?: { user_id: string; companion_ids: string[] } | null;
  partyNames?: Record<string, string>;
}

// PRD batch-2r §4.2(d): which evidence sources to keep per perspective.
// `google_places` is the "neutral" source and stays in every view.
// Unknown / future sources fall through and are kept (defensive — we
// don't want to silently drop new providers).
function filterEvidenceByPerspective(
  evidence: NonNullable<JoinedItemView["evidence"]>,
  perspective: Perspective,
): NonNullable<JoinedItemView["evidence"]> {
  if (perspective === "fused") return evidence;
  return evidence.filter((ev) => {
    const source = ev?.source;
    if (source == null) return true;
    if (source === "google_places") return true;
    if (perspective === "zh") return source === "xiaohongshu";
    if (perspective === "en") return source === "reddit";
    return true;
  });
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

export function ItemCard({
  item,
  index = 0,
  perspective = "fused",
  party = null,
  partyNames,
}: ItemCardProps) {
  const view = item as JoinedItemView;
  const name = view.candidate?.name ?? "untitled";
  const allEvidence = view.evidence ?? [];
  const evidence = filterEvidenceByPerspective(allEvidence, perspective);
  const evidenceCount = evidence.length;
  const effectiveClassification = resolveClassification(item, perspective);
  const verdict = effectiveClassification ? VERDICT_BY_CLASS[effectiveClassification] ?? null : null;
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

  // Batch-2p: build the per-person match line for the expanded view.
  // Order: user first (label "you"), then companions in party order.
  // We only render the row when (a) match_scores exists, (b) the trip
  // has at least one companion (no signal otherwise), and (c) at least
  // one person in the party has a score we can show.
  const matchEntries: Array<{ label: string; score: number }> = [];
  if (party && view.match_scores) {
    const userVal = view.match_scores[party.user_id];
    if (typeof userVal === "number") {
      matchEntries.push({ label: "you", score: userVal });
    }
    for (const cid of party.companion_ids) {
      const val = view.match_scores[cid];
      if (typeof val !== "number") continue;
      const rawName = partyNames?.[cid] ?? "";
      const label = rawName.trim() ? rawName.trim().toLowerCase() : "friend";
      matchEntries.push({ label, score: val });
    }
  }
  const showMatchLine =
    matchEntries.length > 0 &&
    party != null &&
    party.companion_ids.length > 0;

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
          {showMatchLine ? (
            <p
              data-testid="match-line"
              className="scrawl"
              style={{ fontSize: 14, color: "hsl(var(--ink-3))" }}
            >
              <span className="type" style={{ marginRight: 4 }}>match</span>
              {" "}
              {matchEntries
                .map((entry) => `${entry.label}: ${entry.score.toFixed(1)}`)
                .join(" · ")}
            </p>
          ) : null}
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
