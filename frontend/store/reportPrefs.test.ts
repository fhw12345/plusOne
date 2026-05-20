import { beforeEach, describe, expect, it } from "vitest";

import { useReportPrefsStore } from "@/store/reportPrefs";

describe("useReportPrefsStore", () => {
  beforeEach(() => {
    useReportPrefsStore.setState({ perspective: "fused" });
  });

  it("defaults to 'fused' perspective", () => {
    expect(useReportPrefsStore.getState().perspective).toBe("fused");
  });

  it("setPerspective updates the value to 'zh'", () => {
    useReportPrefsStore.getState().setPerspective("zh");
    expect(useReportPrefsStore.getState().perspective).toBe("zh");
  });

  it("setPerspective updates the value to 'en'", () => {
    useReportPrefsStore.getState().setPerspective("en");
    expect(useReportPrefsStore.getState().perspective).toBe("en");
  });

  it("setPerspective round-trips back to 'fused'", () => {
    useReportPrefsStore.getState().setPerspective("zh");
    useReportPrefsStore.getState().setPerspective("fused");
    expect(useReportPrefsStore.getState().perspective).toBe("fused");
  });
});
