"use client";

import * as React from "react";

import { useCompanions } from "@/hooks/useCompanions";
import { tiltFor } from "@/lib/scrapbook/tilt";

interface CompanionSelectorProps {
  value: string[];
  onChange: (ids: string[]) => void;
}

const CHIP_TAPES = ["", "chip--blue", "chip--yellow", "chip--red"] as const;

/**
 * Per-trip companion picker rendered as scrapbook "chips" — each is a button
 * that toggles via `is-on`. Empty selection = all companions, matching the
 * backend CreateTripBody default.
 */
export function CompanionSelector({ value, onChange }: CompanionSelectorProps) {
  const { data, isLoading, isError } = useCompanions();
  const companions = data?.companions ?? [];

  const toggle = (id: string) => {
    if (value.includes(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  };

  if (isLoading) {
    return (
      <p className="scrawl" style={{ fontSize: 15 }}>
        pulling your usual crowd&hellip;
      </p>
    );
  }
  if (isError) {
    return (
      <p role="alert" className="annot" style={{ display: "block" }}>
        couldn&rsquo;t open the address book.
      </p>
    );
  }
  if (companions.length === 0) {
    return (
      <p className="scrawl" style={{ fontSize: 15 }}>
        no companions in the book yet &mdash;{" "}
        <a href="/app/companions" className="link-hand" style={{ fontSize: 15 }}>
          add one
        </a>
        , or skip & go solo.
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "12px 14px", paddingTop: 8 }}>
      {companions.map((c, i) => {
        const checked = value.includes(c.id);
        const extra = CHIP_TAPES[i % CHIP_TAPES.length];
        const tilt = tiltFor(c.id).toFixed(2);
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => toggle(c.id)}
            className={`chip ${extra} ${checked ? "is-on" : ""}`.trim()}
            style={{ ["--tilt" as never]: `${tilt}deg` }}
            aria-pressed={checked}
          >
            {c.name}
          </button>
        );
      })}
      <a
        href="/app/companions"
        className="link-hand"
        style={{ fontSize: 16, alignSelf: "center" }}
      >
        + add someone
      </a>
    </div>
  );
}
