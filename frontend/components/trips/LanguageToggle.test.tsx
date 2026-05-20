import { describe, expect, it, beforeEach } from "vitest";
import { renderToString } from "react-dom/server";

import { LanguageToggle } from "@/components/trips/LanguageToggle";
import { useReportPrefsStore } from "@/store/reportPrefs";

describe("LanguageToggle (SSR markup)", () => {
  beforeEach(() => {
    useReportPrefsStore.setState({ language: "original" });
  });

  it("renders a radiogroup with two options (zh, en)", () => {
    const html = renderToString(<LanguageToggle />);
    expect(html).toMatch(/role="radiogroup"/);
    const radios = html.match(/role="radio"/g) ?? [];
    expect(radios).toHaveLength(2);
  });

  it("renders the two language labels", () => {
    const html = renderToString(<LanguageToggle />);
    expect(html).toContain("中文");
    expect(html).toContain("English");
  });

  it("renders each option with its data-language attribute", () => {
    const html = renderToString(<LanguageToggle />);
    expect(html).toMatch(/data-language="zh"/);
    expect(html).toMatch(/data-language="en"/);
  });

  it("renders all radios as unchecked on first SSR paint (pre-hydration)", () => {
    // ``useReportPrefsHasHydrated`` reports false on the server, so no
    // option is highlighted until rehydrate completes on the client.
    const html = renderToString(<LanguageToggle />);
    const unchecked = html.match(/aria-checked="false"/g) ?? [];
    expect(unchecked).toHaveLength(2);
  });

  it("setLanguage on the store flips the value", () => {
    // Sanity check — the component reads from this store at runtime.
    useReportPrefsStore.getState().setLanguage("zh");
    expect(useReportPrefsStore.getState().language).toBe("zh");
    useReportPrefsStore.getState().setLanguage("en");
    expect(useReportPrefsStore.getState().language).toBe("en");
    useReportPrefsStore.getState().setLanguage("original");
    expect(useReportPrefsStore.getState().language).toBe("original");
  });
});
