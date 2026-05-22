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
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
  usePathname: () => "/login",
}));

import LoginPage from "@/app/login/page";

describe("LoginPage (SSR markup)", () => {
  it("renders the heading and sub copy verbatim", () => {
    const html = renderToString(<LoginPage />);
    expect(html).toContain("let me in");
    expect(html).toContain("password, or a code. your call.");
  });

  it("renders both tab toggles", () => {
    const html = renderToString(<LoginPage />);
    expect(html).toContain('role="tab"');
    expect(html).toContain(">password<");
    expect(html).toContain(">by code<");
  });

  it("starts on the password tab — identifier + password inputs visible", () => {
    const html = renderToString(<LoginPage />);
    expect(html).toContain("name or email");
    expect(html).toContain("whichever you remember.");
    expect(html).toContain(">let me in<");
  });

  it("does not include banned phrases", () => {
    const html = renderToString(<LoginPage />);
    expect(html).not.toContain("Submitting…");
    expect(html).not.toContain("Loading…");
    expect(html).not.toContain("Powered by AI");
    expect(html).not.toContain("Login");
    expect(html).not.toContain("magic link");
    expect(html).not.toContain("send the link");
  });

  it("links to /register from the password tab", () => {
    const html = renderToString(<LoginPage />);
    expect(html).toMatch(/href="\/register"/);
  });
});
