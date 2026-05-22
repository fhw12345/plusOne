"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { refineTrip } from "@/lib/api/trips";
import type {
  RefineTripBody as RefineTripBodyT,
  RefineTripResponse as RefineTripResponseT,
} from "@/lib/schemas/trips";

/**
 * Trigger a refine on a completed trip.
 *
 * On success: invalidates the trip detail + the report list so the page
 * refetches once the new cycle's `trip_complete` SSE event lands. We
 * deliberately do NOT manage the SSE feed here — `useTripStream` is
 * keyed by trip_id, so the existing stream picks up the refine cycle's
 * events automatically.
 */
export function useRefineTrip(tripId: string | null) {
  const qc = useQueryClient();

  return useMutation<RefineTripResponseT, Error, RefineTripBodyT>({
    mutationFn: (body: RefineTripBodyT) => {
      if (!tripId) {
        return Promise.reject(new Error("trip_id_missing"));
      }
      return refineTrip(tripId, body);
    },
    onSuccess: () => {
      if (!tripId) return;
      // The new report only exists once the cycle completes — but bumping
      // staleness for the trip detail + reports list lets the page kick a
      // refetch as soon as the `trip_complete` event lands. The trip-list
      // page also refreshes its `latest_report_id` on next visit.
      qc.invalidateQueries({ queryKey: ["trip", tripId] });
      qc.invalidateQueries({ queryKey: ["trip-reports", tripId] });
    },
  });
}
