"use client";

import Link from "next/link";

export function TripListEmpty() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 16,
        marginTop: 40,
        padding: "36px 32px",
        background: "hsl(var(--paper-2))",
        boxShadow: "0 10px 22px -12px hsl(0 0% 0% / .18)",
        transform: "rotate(-.6deg)",
        maxWidth: 520,
        position: "relative",
      }}
    >
      <span
        className="tape tape--yellow"
        style={{
          top: -10,
          left: "50%",
          width: 120,
          height: 24,
          transform: "translateX(-50%) rotate(3deg)",
        }}
      />
      <p className="hand" style={{ fontSize: 26 }}>
        the notebook&rsquo;s empty so far. plan a trip and i&rsquo;ll start a reading.
      </p>
      <p className="scrawl">
        tell me where you&rsquo;re going. i&rsquo;ll ask around and write you a short list.
      </p>
      <Link href="/app/trips/new" className="btn btn--red">
        + new reading
      </Link>
    </div>
  );
}
