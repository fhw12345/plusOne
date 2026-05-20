"use client";

import * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useCompanions } from "@/hooks/useCompanions";

interface CompanionSelectorProps {
  value: string[];
  onChange: (ids: string[]) => void;
}

/**
 * Per-trip companion picker. Lists all of the user's companions (created_at
 * ASC, matching the backend) as checkbox rows; emits the selected id array.
 *
 * Empty list = "all companions" on the backend (CreateTripBody default).
 * The label here says "Companions on this trip" to make the picker semantic
 * to the user — the empty-means-all logic is invisible.
 */
export function CompanionSelector({ value, onChange }: CompanionSelectorProps) {
  const { data, isLoading, isError } = useCompanions();
  const companions = data?.companions ?? [];

  const toggle = (id: string, checked: boolean) => {
    if (checked) {
      if (!value.includes(id)) onChange([...value, id]);
    } else {
      onChange(value.filter((v) => v !== id));
    }
  };

  const selectAll = () => onChange(companions.map((c) => c.id));
  const selectNone = () => onChange([]);

  if (isLoading) {
    return <p className="text-foreground/60 text-sm">Loading companions…</p>;
  }
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Couldn&apos;t load companions.
      </p>
    );
  }
  if (companions.length === 0) {
    return (
      <p className="text-foreground/60 text-sm">
        You don&apos;t have any companions yet. Add some from the Companions page to include them on
        a trip.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Companions on this trip</span>
        <div className="flex gap-3 text-xs">
          <button
            type="button"
            onClick={selectAll}
            className="text-foreground/70 underline-offset-2 hover:underline"
          >
            Select all
          </button>
          <button
            type="button"
            onClick={selectNone}
            className="text-foreground/70 underline-offset-2 hover:underline"
          >
            None
          </button>
        </div>
      </div>
      <ul className="border-foreground/10 flex flex-col gap-1 rounded-md border p-2">
        {companions.map((c) => {
          const checked = value.includes(c.id);
          const checkboxId = `companion-${c.id}`;
          return (
            <li key={c.id} className="flex items-center gap-2 px-1 py-1">
              <Checkbox
                id={checkboxId}
                checked={checked}
                onCheckedChange={(state) => toggle(c.id, state === true)}
              />
              <Label htmlFor={checkboxId} className="cursor-pointer">
                {c.name}
              </Label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
