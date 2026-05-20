"use client";

import * as React from "react";
import { X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface ChipInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  max?: number;
  ariaLabel?: string;
  id?: string;
}

/**
 * Reusable chip-style multi-string input. Add on Enter or comma; remove via
 * the X on each chip. Dedupes case-insensitively. Caps at `max` (default 50,
 * matching the backend's per-list bound).
 */
export function ChipInput({
  value,
  onChange,
  placeholder = "Add and press Enter",
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
      // Quick-delete the last chip on Backspace when input is empty.
      remove(value.length - 1);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <ul
        className="flex max-h-32 flex-wrap gap-2 overflow-y-auto"
        aria-label={`${ariaLabel ?? "Chips"} list`}
      >
        {value.map((chip, index) => (
          <li
            key={`${chip}-${index}`}
            className="bg-muted text-foreground inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs"
          >
            <span>{chip}</span>
            <button
              type="button"
              onClick={() => remove(index)}
              aria-label={`Remove ${chip}`}
              className="text-foreground/60 hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </li>
        ))}
      </ul>
      <Input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => {
          // Commit on blur so users don't lose a typed-but-not-Enter'd chip.
          if (draft.trim().length > 0) commit(draft);
        }}
        placeholder={atMax ? `Maximum ${max} reached` : placeholder}
        aria-label={ariaLabel}
        disabled={atMax}
        className={cn(atMax && "opacity-60")}
      />
    </div>
  );
}
