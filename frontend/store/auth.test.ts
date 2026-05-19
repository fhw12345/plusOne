import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/store/auth";

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  it("starts empty", () => {
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("setSession populates token and user", () => {
    useAuthStore.getState().setSession("jwt-abc", { id: "u1", email: "a@b.test" });
    const state = useAuthStore.getState();
    expect(state.token).toBe("jwt-abc");
    expect(state.user).toEqual({ id: "u1", email: "a@b.test" });
  });

  it("clear resets token and user", () => {
    useAuthStore.getState().setSession("jwt-abc", { id: "u1", email: "a@b.test" });
    useAuthStore.getState().clear();
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });
});
