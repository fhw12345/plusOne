"use client";

import * as React from "react";

interface ChipInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  max?: number;
  ariaLabel?: string;
  id?: string;
}

export function ChipInput({
  value,
  onChange,
  placeholder = "add and press enter",
  max = 50,
  ariaLabel,
  id,
}: ChipInputProps) {
  const [draft, setDraft] = React.useState("");
  const atMax = value.length >= max;

  const commit = React.useCallback(
    (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed) return;
      if (value.length >= max) return;
      const lower = trimmed.toLowerCase();
      if (value.some((v) => v.toLowerCase() === lower)) {
        setDraft("");
        return;
      }
      onChange([...value, trimmed]);
      setDraft("");
    },
    [value, onChange, max],
  );

  const remove = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(draft);
    } else if (e.key === "Backspace" && draft.length === 0 && value.length > 0) {
      remove(value.length - 1);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          maxHeight: 128,
          overflowY: "auto",
        }}
        aria-label={`${ariaLabel ?? "Chips"} list`}
      >
        {value.map((chip, index) => (
          <li
            key={`${chip}-${index}`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "4px 10px",
              fontSize: 15,
              background: "hsl(var(--paper-3))",
              color: "hsl(var(--ink))",
              borderRadius: 2,
              transform: `rotate(${((index % 5) - 2) * 0.4}deg)`,
            }}
          >
            <span>{chip}</span>
            <button
              type="button"
              onClick={() => remove(index)}
              aria-label={`remove ${chip}`}
              style={{
                background: "none",
                border: 0,
                color: "hsl(var(--ink-3))",
                cursor: "pointer",
                fontSize: 16,
                lineHeight: 1,
                padding: 0,
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => {
          if (draft.trim().length > 0) commit(draft);
        }}
        placeholder={atMax ? `that's ${max}. delete one to add more.` : placeholder}
        aria-label={ariaLabel}
        disabled={atMax}
        style={{
          font: "inherit",
          fontSize: 16,
          padding: "6px 4px",
          background: "transparent",
          border: 0,
          borderBottom: "1px dashed hsl(var(--kraft))",
          color: "hsl(var(--ink))",
          opacity: atMax ? 0.55 : 1,
          outline: "none",
        }}
      />
    </div>
  );
}
