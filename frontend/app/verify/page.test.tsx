import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  // useSearchParams in the verify page reads `?email=...`. Returning a
  // populated URLSearchParams here lets the inner form render at SSR time
  // instead of falling back to the Suspense placeholder.
  useSearchParams: () => new URLSearchParams("email=friend%40somewhere.com"),
  useParams: () => ({}),
  usePathname: () => "/verify",
}));

import VerifyPage from "@/app/verify/page";

describe("VerifyPage (SSR markup)", () => {
  it("renders the heading and sub copy verbatim", () => {
    const html = renderToString(<VerifyPage />);
    expect(html).toContain("check your inbox");
    expect(html).toContain("six-digit code");
  });

  it("ships the verify form markup with the 6-digit code field", () => {
    const html = renderToString(<VerifyPage />);
    expect(html).toContain("the code");
    expect(html).toContain("just the numbers.");
    expect(html).toMatch(/maxlength="6"/i);
    expect(html).toMatch(/inputmode="numeric"/i);
    expect(html).toMatch(/autocomplete="one-time-code"/i);
  });

  it("ships the let-me-in CTA and resend link", () => {
    const html = renderToString(<VerifyPage />);
    expect(html).toContain("let me in");
    expect(html).toContain("resend the code");
  });

  it("renders the 'sent to' annotation with the query email", () => {
    const html = renderToString(<VerifyPage />);
    // React injects comment markers between text nodes — match around them.
    expect(html).toMatch(/sent to .*friend@somewhere\.com/);
  });

  it("does not include banned phrases", () => {
    const html = renderToString(<VerifyPage />);
    expect(html).not.toContain("Submitting…");
    expect(html).not.toContain("Loading…");
    expect(html).not.toContain("Powered by AI");
    expect(html).not.toContain("magic link");
  });
});
