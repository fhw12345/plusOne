import { describe, expect, it, beforeEach } from "vitest";
import { renderToString } from "react-dom/server";

import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import { useReportPrefsStore } from "@/store/reportPrefs";

describe("PerspectiveToggle (SSR markup)", () => {
  beforeEach(() => {
    useReportPrefsStore.setState({ perspective: "fused" });
  });

  it("renders a radiogroup with three options", () => {
    const html = renderToString(<PerspectiveToggle />);
    expect(html).toMatch(/role="radiogroup"/);
    const radios = html.match(/role="radio"/g) ?? [];
    expect(radios).toHaveLength(3);
  });

  it("renders the three perspective labels", () => {
    const html = renderToString(<PerspectiveToggle />);
    expect(html).toContain("中文社区");
    expect(html).toContain("English community");
    expect(html).toContain("blended");
  });

  it("renders each option with its data-perspective attribute", () => {
    const html = renderToString(<PerspectiveToggle />);
    expect(html).toMatch(/data-perspective="zh"/);
    expect(html).toMatch(/data-perspective="en"/);
    expect(html).toMatch(/data-perspective="fused"/);
  });

  it("renders all radios as unchecked on first SSR paint (pre-hydration)", () => {
    // ``useReportPrefsHasHydrated`` reports false on the server, so no
    // option is highlighted until rehydrate completes on the client.
    const html = renderToString(<PerspectiveToggle />);
    const unchecked = html.match(/aria-checked="false"/g) ?? [];
    expect(unchecked).toHaveLength(3);
  });

  it("setPerspective on the store flips the value", () => {
    // Sanity check — the component reads from this store at runtime.
    useReportPrefsStore.getState().setPerspective("zh");
    expect(useReportPrefsStore.getState().perspective).toBe("zh");
    useReportPrefsStore.getState().setPerspective("en");
    expect(useReportPrefsStore.getState().perspective).toBe("en");
  });
});
