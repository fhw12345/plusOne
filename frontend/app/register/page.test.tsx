import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

// next/navigation must be mocked before importing the page module — SSR
// rendering otherwise blows up with "invariant expected app router to be
// mounted" because hooks like `useRouter` require a router context.
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
  usePathname: () => "/register",
}));

import RegisterPage from "@/app/register/page";
import { RegisterBody } from "@/lib/schemas/auth";

describe("RegisterPage (SSR markup)", () => {
  it("renders the heading and four labelled inputs", () => {
    const html = renderToString(<RegisterPage />);
    expect(html).toContain("save your page");
    expect(html).toContain("username");
    expect(html).toContain("your email");
    expect(html).toContain("password");
    expect(html).toContain("say it again");
    expect(html).toContain("save the page");
  });

  it("includes the PRD hint copy verbatim", () => {
    const html = renderToString(<RegisterPage />);
    expect(html).toContain("lowercase, letters and numbers. 3 to 32.");
    expect(html).toContain("at least 10. one letter, one number. that");
    expect(html).toContain("just to be sure.");
  });

  it("does not include banned phrases", () => {
    const html = renderToString(<RegisterPage />);
    expect(html).not.toMatch(/\bSubmit\b/);
    expect(html).not.toContain("Submitting…");
    expect(html).not.toContain("Loading…");
    expect(html).not.toContain("Powered by AI");
    expect(html).not.toContain("Register");
    expect(html).not.toContain("Login");
  });
});

describe("RegisterBody (zod validation)", () => {
  const base = {
    username: "alice99",
    email: "alice@x.test",
    password: "letmein123!",
    confirm: "letmein123!",
  };

  it("accepts a well-formed payload", () => {
    const r = RegisterBody.safeParse(base);
    expect(r.success).toBe(true);
  });

  it("rejects a short username", () => {
    const r = RegisterBody.safeParse({ ...base, username: "al" });
    expect(r.success).toBe(false);
    if (!r.success) {
      const msg = r.error.issues.map((i) => i.message).join("|");
      expect(msg).toMatch(/lowercase, letters and numbers/i);
    }
  });

  it("rejects an uppercase username", () => {
    const r = RegisterBody.safeParse({ ...base, username: "Alice" });
    expect(r.success).toBe(false);
  });

  it("rejects a weak password (no digit)", () => {
    const r = RegisterBody.safeParse({
      ...base,
      password: "abcdefghij",
      confirm: "abcdefghij",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const msg = r.error.issues.map((i) => i.message).join("|");
      expect(msg).toMatch(/ten characters and a number/i);
    }
  });

  it("rejects a password shorter than 10", () => {
    const r = RegisterBody.safeParse({
      ...base,
      password: "short1",
      confirm: "short1",
    });
    expect(r.success).toBe(false);
  });

  it("rejects a mismatched confirm", () => {
    const r = RegisterBody.safeParse({
      ...base,
      confirm: "different123",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const msg = r.error.issues.map((i) => i.message).join("|");
      expect(msg).toMatch(/don't match/i);
    }
  });

  it("rejects a bad email", () => {
    const r = RegisterBody.safeParse({ ...base, email: "not-an-email" });
    expect(r.success).toBe(false);
  });
});
