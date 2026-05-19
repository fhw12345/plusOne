import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openTripStream } from "@/lib/sse";
import type { TripEvent } from "@/lib/schemas/events";

interface FakeListener {
  type: string;
  handler: (e: unknown) => void;
}

class FakeEventSource {
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  closed = false;
  listeners: FakeListener[] = [];
  static last: FakeEventSource | null = null;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
  }

  addEventListener(type: string, handler: (e: unknown) => void): void {
    this.listeners.push({ type, handler });
  }

  close(): void {
    this.closed = true;
  }

  // Test helpers
  fireNamed(name: string, data: unknown): void {
    const json = JSON.stringify(data);
    for (const l of this.listeners) {
      if (l.type === name) l.handler({ data: json } as MessageEvent);
    }
  }

  fireError(): void {
    if (this.onerror) this.onerror({} as Event);
  }
}

const originalEventSource = globalThis.EventSource;

describe("openTripStream", () => {
  beforeEach(() => {
    (globalThis as { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
  });

  afterEach(() => {
    if (originalEventSource) {
      (globalThis as { EventSource: typeof EventSource }).EventSource = originalEventSource;
    } else {
      delete (globalThis as Partial<{ EventSource: typeof EventSource }>).EventSource;
    }
  });

  it("builds URL with the access_token query param", () => {
    openTripStream("trip-123", "jwt-abc&%", {
      onEvent: () => {},
      onError: () => {},
      onClose: () => {},
    });
    expect(FakeEventSource.last).not.toBeNull();
    expect(FakeEventSource.last!.url).toContain("/api/trips/trip-123/stream");
    // Token must be URL-encoded.
    expect(FakeEventSource.last!.url).toContain("access_token=jwt-abc%26%25");
  });

  it("dispatches a parsed event for a known SSE name", () => {
    const events: TripEvent[] = [];
    openTripStream("trip-123", "jwt", {
      onEvent: (e) => events.push(e),
      onError: () => {},
      onClose: () => {},
    });
    FakeEventSource.last!.fireNamed("started", { name: "started", trip_id: "trip-123" });
    expect(events.length).toBe(1);
    expect(events[0]!.name).toBe("started");
  });

  it("ignores an unparseable frame", () => {
    const events: TripEvent[] = [];
    openTripStream("trip-123", "jwt", {
      onEvent: (e) => events.push(e),
      onError: () => {},
      onClose: () => {},
    });
    FakeEventSource.last!.fireNamed("started", { name: "bogus" });
    expect(events.length).toBe(0);
  });

  it("close() closes the EventSource and fires onClose once", () => {
    const onClose = vi.fn();
    const handle = openTripStream("trip-123", "jwt", {
      onEvent: () => {},
      onError: () => {},
      onClose,
    });
    handle.close();
    handle.close();
    expect(FakeEventSource.last!.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("onerror closes the stream and fires onError + onClose", () => {
    const onError = vi.fn();
    const onClose = vi.fn();
    openTripStream("trip-123", "jwt", {
      onEvent: () => {},
      onError,
      onClose,
    });
    FakeEventSource.last!.fireError();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(FakeEventSource.last!.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
