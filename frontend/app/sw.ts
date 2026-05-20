import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { NetworkOnly, Serwist } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    // Injected by @serwist/next at build time. Holds the precache manifest of
    // built artifacts (the Next chunks under _next/static/...). Matches
    // next-pwa's implicit precache behaviour.
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  // Mirrors next-pwa's `skipWaiting: true` so users don't get stuck on the
  // old SW for an extra navigation after deploy.
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  // `defaultCache` is the @serwist/next preset closest to next-pwa@5.6's
  // cache.js defaults (parity table documented in PRD §3.3). The single
  // difference (explicit RSC NetworkFirst rule) does not change the
  // observable strategy class on any request — only the cache name.
  runtimeCaching: [
    {
      // SSE safety: bypass the SW for all backend API calls. The trip stream
      // endpoint (/api/trips/{id}/stream) must reach the network untouched —
      // a NetworkFirst handler with a 10s timeout would race the stream and
      // fall back to (an empty) cache. /api/backend/* (the rewrite target)
      // already matches /api/, so a single prefix check suffices.
      matcher: ({ url, sameOrigin }) =>
        sameOrigin && url.pathname.startsWith("/api/"),
      handler: new NetworkOnly(),
      method: "GET",
    },
    ...defaultCache,
  ],
});

serwist.addEventListeners();
