"use client";

import * as React from "react";

import type { VisitedCity } from "@/lib/schemas/profile";

interface VisitedCitiesFieldProps {
  value: VisitedCity[];
  onChange: (value: VisitedCity[]) => void;
}

const FIELD_INPUT_STYLE: React.CSSProperties = {
  font: "inherit",
  fontSize: 16,
  padding: "6px 4px",
  background: "transparent",
  border: 0,
  borderBottom: "1px dashed hsl(var(--kraft))",
  color: "hsl(var(--ink))",
  outline: "none",
  width: "100%",
};

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
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <ul
        style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 14 }}
        aria-label="Visited cities list"
      >
        {value.map((row, index) => (
          <li
            key={index}
            style={{
              position: "relative",
              padding: "16px 18px",
              background: "hsl(var(--paper))",
              border: "1px solid hsl(var(--kraft))",
              transform: `rotate(${((index % 3) - 1) * 0.4}deg)`,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <div
                style={{
                  flex: 1,
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 14,
                }}
              >
                <div className="field" style={{ marginBottom: 0 }}>
                  <label htmlFor={`vc-city-${index}`}>city</label>
                  <input
                    id={`vc-city-${index}`}
                    value={row.city}
                    onChange={(e) => updateRow(index, { city: e.target.value })}
                    maxLength={100}
                    style={FIELD_INPUT_STYLE}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <label htmlFor={`vc-year-${index}`}>year</label>
                  <input
                    id={`vc-year-${index}`}
                    type="number"
                    min={1900}
                    max={2100}
                    value={row.year}
                    onChange={(e) => updateRow(index, { year: Number(e.target.value) || row.year })}
                    style={FIELD_INPUT_STYLE}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <label htmlFor={`vc-rating-${index}`}>star rating (1-5)</label>
                  <input
                    id={`vc-rating-${index}`}
                    type="number"
                    min={1}
                    max={5}
                    value={row.rating ?? ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      updateRow(index, { rating: raw === "" ? null : Number(raw) });
                    }}
                    style={FIELD_INPUT_STYLE}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0, gridColumn: "1 / -1" }}>
                  <label htmlFor={`vc-feedback-${index}`}>what stuck</label>
                  <textarea
                    id={`vc-feedback-${index}`}
                    rows={2}
                    maxLength={500}
                    value={row.feedback ?? ""}
                    onChange={(e) => updateRow(index, { feedback: e.target.value || null })}
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={() => removeRow(index)}
                aria-label={`remove row ${index + 1}`}
                className="link-hand"
                style={{
                  font: "inherit",
                  fontSize: 22,
                  background: "none",
                  border: 0,
                  padding: 0,
                  color: "hsl(var(--ink-3))",
                  alignSelf: "flex-start",
                }}
              >
                ×
              </button>
            </div>
          </li>
        ))}
      </ul>
      <button type="button" onClick={addRow} className="btn" style={{ alignSelf: "flex-start" }}>
        + add a city
      </button>
    </div>
  );
}
