import { notFound } from "next/navigation";

import { ReportView } from "@/components/trips/ReportView";
import { getSharedTrip } from "@/lib/api/trips";
import type { TripDetail } from "@/lib/schemas/trips";

interface SharePageProps {
  params: Promise<{ token: string }>;
}

// Server component — no auth, no JS-only hooks needed for the read.
// Renders the shared report or surfaces a 404 page for missing /
// expired / revoked tokens (notFound() emits a real 404 so search
// engines don't index dead links).
export default async function SharedTripPage({ params }: SharePageProps) {
  const { token } = await params;

  let payload;
  try {
    payload = await getSharedTrip(token);
  } catch {
    notFound();
  }

  // ``ReportView`` takes the same shape as authed ``TripDetail`` for the
  // fields it actually renders. We map the shared payload onto that
  // shape (with a synthetic ``latest_report_id``) so the same component
  // serves both surfaces.
  const tripForView: TripDetail = {
    trip_id: payload.trip_id,
    destination: payload.destination,
    status: payload.status,
    latest_report_id: null,
    content: payload.content,
  };

  return (
    <main className="shell" data-shared-trip-page="true" style={{ maxWidth: 920 }}>
      <header style={{ position: "relative", padding: "12px 0 28px" }}>
        <span
          className="tape tape--mint"
          style={{ top: -8, left: 60, width: 96, height: 24, transform: "rotate(-3deg)" }}
        />
        <p className="crest" style={{ marginBottom: 6 }}>
          <span className="crest-dot" />
          PLUS &middot; ONE &middot; shared reading
        </p>
        <h1 className="hand-xxl">{payload.destination}</h1>
        <p className="scrawl" style={{ marginTop: 12, fontSize: 17 }}>
          read-only &mdash; expires{" "}
          <span className="type" style={{ fontSize: 12 }}>
            {new Date(payload.expires_at).toLocaleString()}
          </span>
        </p>
      </header>
      <ReportView trip={tripForView} readonly />
    </main>
  );
}
