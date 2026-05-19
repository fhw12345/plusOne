import { TripEvent, TripEventName, type TripEvent as TripEventT } from "@/lib/schemas/events";
import { useAuthStore } from "@/store/auth";

export interface TripStreamHandlers {
  onEvent: (event: TripEventT) => void;
  onError: (e: Event) => void;
  onClose: () => void;
}

export interface TripStreamHandle {
  close: () => void;
}

function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

/**
 * Opens an SSE stream to /api/trips/{id}/stream and dispatches each parsed
 * event to `handlers.onEvent`. The JWT is appended as `?access_token=` —
 * EventSource cannot set Authorization headers, so the backend exposes a
 * narrow query-param fallback for SSE only (see PRD §4.1).
 *
 * Returns a `{ close() }` handle. Callers MUST invoke `close()` on unmount
 * AND on error to disable EventSource's native auto-reconnect (which would
 * otherwise hammer the backend with a guaranteed-401 on token expiry).
 */
export function openTripStream(
  tripId: string,
  token: string,
  handlers: TripStreamHandlers,
): TripStreamHandle {
  const url = `${getApiBase()}/api/trips/${tripId}/stream?access_token=${encodeURIComponent(token)}`;
  const source = new EventSource(url);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    source.close();
    handlers.onClose();
  };

  const handleFrame = (raw: string) => {
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }
    const parsed = TripEvent.safeParse(payload);
    if (parsed.success) {
      handlers.onEvent(parsed.data);
    }
  };

  // The generic onmessage handler covers any frame whose `event:` field is
  // absent or `message`. Backend always sets `event: <name>`, so this is a
  // safety net.
  source.onmessage = (e) => handleFrame(e.data);

  // Register a typed listener for each known event name. Browsers route SSE
  // frames to the matching `addEventListener` handler based on the
  // `event:` field.
  for (const name of TripEventName.options) {
    source.addEventListener(name, (e) => handleFrame((e as MessageEvent).data));
  }

  source.onerror = (e) => {
    handlers.onError(e);
    // Disable EventSource's auto-reconnect: against a 401 it would hammer
    // the backend, and surfacing the error to the user is more useful than
    // a silent retry loop.
    close();
  };

  return { close };
}

/**
 * Convenience that reads the JWT from the auth store at call time. Returns
 * `null` when no token is present (caller should gate on hydration first).
 */
export function openTripStreamWithStoredToken(
  tripId: string,
  handlers: TripStreamHandlers,
): TripStreamHandle | null {
  const token = useAuthStore.getState().token;
  if (!token) return null;
  return openTripStream(tripId, token, handlers);
}
