import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderToString } from "react-dom/server";

// Force useCityIndex to a deterministic state per test by stubbing its
// module entirely — keeps these tests pure SSR-string assertions
// (no jsdom / no @testing-library/react in this repo).
const cityIndexMock = vi.fn();
vi.mock("@/hooks/useCityIndex", () => ({
  useCityIndex: () => cityIndexMock(),
}));

import { DestinationCombobox } from "@/components/trips/DestinationCombobox";

const SAMPLE = [
  { n: "Tokyo", c: "Japan", p: 37400000 },
  { n: "Delhi", c: "India", p: 30290000 },
  { n: "Kyoto", c: "Japan", p: 1460000 },
];

describe("DestinationCombobox (SSR markup)", () => {
  beforeEach(() => {
    cityIndexMock.mockReset();
  });

  it("renders the input with scrapbook placeholder", () => {
    cityIndexMock.mockReturnValue({ status: "loading" });
    const html = renderToString(<DestinationCombobox value="" onChange={() => {}} />);
    expect(html).toContain('placeholder="kyoto, paris, mendoza…"');
  });

  it("input has role=combobox and aria-autocomplete=list", () => {
    cityIndexMock.mockReturnValue({ status: "loading" });
    const html = renderToString(<DestinationCombobox value="" onChange={() => {}} />);
    expect(html).toMatch(/role="combobox"/);
    expect(html).toMatch(/aria-autocomplete="list"/);
    expect(html).toMatch(/aria-controls="dest-listbox"/);
  });

  it("does NOT render the listbox on initial SSR (open is false by default)", () => {
    cityIndexMock.mockReturnValue({ status: "ready", cities: SAMPLE });
    const html = renderToString(<DestinationCombobox value="" onChange={() => {}} />);
    expect(html).not.toMatch(/role="listbox"/);
    // aria-expanded should be false at first paint.
    expect(html).toMatch(/aria-expanded="false"/);
  });

  it("respects custom inputId for label htmlFor binding", () => {
    cityIndexMock.mockReturnValue({ status: "loading" });
    const html = renderToString(
      <DestinationCombobox value="" onChange={() => {}} inputId="custom-dest" />,
    );
    expect(html).toMatch(/id="custom-dest"/);
  });

  it("renders value attribute reflecting controlled value", () => {
    cityIndexMock.mockReturnValue({ status: "loading" });
    const html = renderToString(<DestinationCombobox value="Hakone, Japan" onChange={() => {}} />);
    expect(html).toContain('value="Hakone, Japan"');
  });

  it("marks aria-invalid when error prop is set", () => {
    cityIndexMock.mockReturnValue({ status: "loading" });
    const html = renderToString(
      <DestinationCombobox value="" onChange={() => {}} error="required" />,
    );
    expect(html).toMatch(/aria-invalid="true"/);
  });

  it("input is never disabled even when index is loading", () => {
    cityIndexMock.mockReturnValue({ status: "loading" });
    const html = renderToString(<DestinationCombobox value="" onChange={() => {}} />);
    expect(html).not.toMatch(/disabled/);
  });

  it("input is never disabled when index is in error state", () => {
    cityIndexMock.mockReturnValue({
      status: "error",
      error: new Error("network"),
    });
    const html = renderToString(<DestinationCombobox value="" onChange={() => {}} />);
    expect(html).not.toMatch(/disabled/);
    // No visible error toast — silent degrade.
    expect(html).not.toContain("network");
  });
});
