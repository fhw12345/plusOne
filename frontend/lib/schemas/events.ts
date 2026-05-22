import { z } from "zod";

// SSE event names match the backend's publish() callsites in
// backend/src/plus_one/services/trip_runner.py:164-289.
export const TripEventName = z.enum([
  "started",
  "iteration_start",
  "producer",
  "joiner",
  "controller",
  "cycle_aborted",
  "trip_complete",
  "refine_started",
]);
export type TripEventName = z.infer<typeof TripEventName>;

// Each variant uses `.passthrough()` so an unknown future field on a
// known event doesn't break parse. Discriminated on `name` so TS
// narrowing on `.name` works inside switches.

const StartedEvent = z
  .object({
    name: z.literal("started"),
    trip_id: z.string(),
  })
  .passthrough();

const IterationStartEvent = z
  .object({
    name: z.literal("iteration_start"),
    depth: z.number().int().nonnegative(),
    data: z.object({}).passthrough(),
  })
  .passthrough();

const ProducerEvent = z
  .object({
    name: z.literal("producer"),
    depth: z.number().int().nonnegative(),
    data: z
      .object({
        n_candidates: z.number().int().nonnegative(),
        notes: z.string().optional(),
      })
      .passthrough(),
  })
  .passthrough();

const JoinerEvent = z
  .object({
    name: z.literal("joiner"),
    depth: z.number().int().nonnegative(),
    data: z
      .object({
        n_in: z.number().int().nonnegative(),
        n_out: z.number().int().nonnegative(),
        notes: z.string().optional(),
      })
      .passthrough(),
  })
  .passthrough();

const ControllerEvent = z
  .object({
    name: z.literal("controller"),
    depth: z.number().int().nonnegative(),
    data: z
      .object({
        should_continue: z.boolean(),
        reasoning: z.string().optional().default(""),
        notes: z.string().optional(),
      })
      .passthrough(),
  })
  .passthrough();

const CycleAbortedEvent = z
  .object({
    name: z.literal("cycle_aborted"),
    depth: z.number().int().nonnegative().optional(),
    data: z
      .object({
        reason: z.string(),
      })
      .passthrough(),
  })
  .passthrough();

const TripCompleteEvent = z
  .object({
    name: z.literal("trip_complete"),
    trip_id: z.string(),
    status: z.string(),
    report_id: z.string().nullable().optional(),
  })
  .passthrough();

// Batch-2u: emitted once at the start of a refine cycle. Carries the
// previous report id (for context) and the verbatim user hint.
const RefineStartedEvent = z
  .object({
    name: z.literal("refine_started"),
    trip_id: z.string(),
    previous_report_id: z.string(),
    hint: z.string(),
  })
  .passthrough();

export const TripEvent = z.discriminatedUnion("name", [
  StartedEvent,
  IterationStartEvent,
  ProducerEvent,
  JoinerEvent,
  ControllerEvent,
  CycleAbortedEvent,
  TripCompleteEvent,
  RefineStartedEvent,
]);
export type TripEvent = z.infer<typeof TripEvent>;
