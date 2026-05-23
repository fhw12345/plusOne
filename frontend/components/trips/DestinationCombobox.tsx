"use client";

import * as React from "react";

import { useCityIndex } from "@/hooks/useCityIndex";
import { formatCity, searchCities, type City } from "@/lib/cities";

interface DestinationComboboxProps {
  value: string;
  onChange: (next: string) => void;
  onBlur?: () => void;
  error?: string;
  /** id for the input — defaults to "dest" so existing <label htmlFor> still binds. */
  inputId?: string;
}

const LIMIT = 8;
const LISTBOX_ID = "dest-listbox";
const OPTION_ID_PREFIX = "dest-option-";

const NO_MATCH_COPY = "doesn't ring a bell — type it anyway, i'll figure it out.";

/**
 * Hand-rolled ARIA combobox for the trip destination field.
 *
 * - Opens on focus (or as soon as the city index is ready).
 * - Filters via leading-substring on the city name as the user types.
 * - ↓/↑ moves highlight, Enter commits, Esc closes without changing value.
 * - Free-typing is always allowed — Enter with no highlight commits the raw
 *   input, and the parent form's submit path is never blocked.
 *
 * The component is uncontrolled-with-prop: input value is owned by the
 * parent (via react-hook-form's Controller), highlight + open state are
 * local.
 */
export function DestinationCombobox({
  value,
  onChange,
  onBlur,
  error,
  inputId = "dest",
}: DestinationComboboxProps) {
  const cityIndex = useCityIndex();
  const ready = cityIndex.status === "ready";

  const [open, setOpen] = React.useState(false);
  const [highlight, setHighlight] = React.useState(-1);

  const containerRef = React.useRef<HTMLDivElement | null>(null);

  const suggestions = React.useMemo<readonly City[]>(
    () => (cityIndex.status === "ready" ? searchCities(value, cityIndex.cities, LIMIT) : []),
    [cityIndex, value],
  );

  // Clamp highlight to current suggestion bounds during render — when the
  // user types and the list shrinks, the old index might point past the end
  // (or to a stale entry). Doing this here instead of in an effect avoids
  // the cascading-render lint and a flash of mis-highlighted row.
  const safeHighlight = highlight >= 0 && highlight < suggestions.length ? highlight : -1;

  // Click outside closes the dropdown.
  React.useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const commit = (city: City) => {
    onChange(formatCity(city));
    setOpen(false);
    setHighlight(-1);
  };

  const onFocus = () => {
    if (ready) setOpen(true);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!ready) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setHighlight(suggestions.length > 0 ? 0 : -1);
        return;
      }
      if (suggestions.length === 0) return;
      setHighlight((safeHighlight + 1) % suggestions.length);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setHighlight(suggestions.length > 0 ? suggestions.length - 1 : -1);
        return;
      }
      if (suggestions.length === 0) return;
      setHighlight((safeHighlight - 1 + suggestions.length) % suggestions.length);
      return;
    }
    if (e.key === "Enter") {
      if (open && safeHighlight >= 0) {
        e.preventDefault();
        const picked = suggestions[safeHighlight];
        if (picked) commit(picked);
      }
      // else: let the form submit naturally with the raw value.
      return;
    }
    if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
        setHighlight(-1);
      }
      return;
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
    if (ready && !open) setOpen(true);
  };

  const activeOptionId =
    open && safeHighlight >= 0 ? `${OPTION_ID_PREFIX}${safeHighlight}` : undefined;

  const showNoMatch = open && ready && value.trim().length > 0 && suggestions.length === 0;

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <input
        id={inputId}
        type="text"
        role="combobox"
        autoComplete="off"
        spellCheck={false}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={LISTBOX_ID}
        aria-activedescendant={activeOptionId}
        aria-invalid={error ? "true" : "false"}
        placeholder="kyoto, paris, mendoza…"
        value={value}
        onChange={onInputChange}
        onFocus={onFocus}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
      />
      {open && (suggestions.length > 0 || showNoMatch) ? (
        <ul
          id={LISTBOX_ID}
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            zIndex: 20,
            margin: 0,
            padding: "6px 0",
            listStyle: "none",
            background: "hsl(var(--paper-2))",
            border: "1px solid hsl(var(--kraft))",
            boxShadow: "0 12px 24px -10px hsl(0 0% 0% / .25)",
            maxHeight: 320,
            overflowY: "auto",
          }}
        >
          {suggestions.map((city, i) => {
            const id = `${OPTION_ID_PREFIX}${i}`;
            const isActive = i === safeHighlight;
            return (
              <li
                key={`${city.n}|${city.c}`}
                id={id}
                role="option"
                aria-selected={isActive}
                onMouseDown={(e) => {
                  // mousedown (not click) so we beat the input's blur.
                  e.preventDefault();
                  commit(city);
                }}
                onMouseEnter={() => setHighlight(i)}
                style={{
                  padding: "6px 14px",
                  cursor: "pointer",
                  background: isActive ? "hsl(var(--mint) / .35)" : "transparent",
                  fontFamily: "var(--font-hand, inherit)",
                  fontSize: 16,
                  lineHeight: 1.4,
                }}
              >
                {formatCity(city)}
              </li>
            );
          })}
          {showNoMatch ? (
            <li
              role="presentation"
              style={{
                padding: "6px 14px",
                fontStyle: "italic",
                fontSize: 14,
                color: "hsl(var(--ink) / .65)",
                fontFamily: "var(--font-hand, inherit)",
              }}
            >
              {NO_MATCH_COPY}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
