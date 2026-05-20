"use client";

import * as React from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { VisitedCity } from "@/lib/schemas/profile";

interface VisitedCitiesFieldProps {
  value: VisitedCity[];
  onChange: (value: VisitedCity[]) => void;
}

/**
 * Inline editable list of visited cities. Each row: city + year (required),
 * rating + feedback (optional). No reorder, no aggregation — see PRD §2
 * Non-goals.
 */
export function VisitedCitiesField({ value, onChange }: VisitedCitiesFieldProps) {
  const addRow = () => {
    onChange([
      ...value,
      { city: "", year: new Date().getFullYear(), rating: null, feedback: null },
    ]);
  };

  const updateRow = (index: number, patch: Partial<VisitedCity>) => {
    onChange(value.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const removeRow = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3" aria-label="Visited cities list">
        {value.map((row, index) => (
          <li key={index} className="border-foreground/10 rounded-md border p-3">
            <div className="flex items-start gap-2">
              <div className="grid flex-1 grid-cols-1 gap-2 sm:grid-cols-2">
                <div className="flex flex-col gap-1">
                  <Label htmlFor={`vc-city-${index}`}>City</Label>
                  <Input
                    id={`vc-city-${index}`}
                    value={row.city}
                    onChange={(e) => updateRow(index, { city: e.target.value })}
                    maxLength={100}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor={`vc-year-${index}`}>Year</Label>
                  <Input
                    id={`vc-year-${index}`}
                    type="number"
                    min={1900}
                    max={2100}
                    value={row.year}
                    onChange={(e) => updateRow(index, { year: Number(e.target.value) || row.year })}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor={`vc-rating-${index}`}>Rating (1-5)</Label>
                  <Input
                    id={`vc-rating-${index}`}
                    type="number"
                    min={1}
                    max={5}
                    value={row.rating ?? ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      updateRow(index, { rating: raw === "" ? null : Number(raw) });
                    }}
                  />
                </div>
                <div className="flex flex-col gap-1 sm:col-span-2">
                  <Label htmlFor={`vc-feedback-${index}`}>Feedback</Label>
                  <Textarea
                    id={`vc-feedback-${index}`}
                    rows={2}
                    maxLength={500}
                    value={row.feedback ?? ""}
                    onChange={(e) => updateRow(index, { feedback: e.target.value || null })}
                  />
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => removeRow(index)}
                aria-label={`Remove row ${index + 1}`}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Button type="button" variant="outline" size="sm" onClick={addRow}>
        <Plus className="mr-1 h-4 w-4" /> Add city
      </Button>
    </div>
  );
}
