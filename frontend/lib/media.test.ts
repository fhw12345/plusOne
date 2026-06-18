import { describe, expect, it, vi } from "vitest";

import { resolveMediaUrl } from "@/lib/media";

describe("resolveMediaUrl", () => {
  it("keeps remote URLs untouched", () => {
    expect(resolveMediaUrl("https://img.example/a.jpg")).toBe("https://img.example/a.jpg");
  });

  it("routes backend media paths through NEXT_PUBLIC_API_URL", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8010");

    expect(resolveMediaUrl("/media/xhs/a/file.webp")).toBe(
      "http://localhost:8010/media/xhs/a/file.webp",
    );

    vi.unstubAllEnvs();
  });
});

