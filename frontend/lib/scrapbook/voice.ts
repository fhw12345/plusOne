import type { TripEvent } from "@/lib/schemas/events";

type Pool = readonly string[];

const STARTED: Pool = [
  "setting up. coffee in hand.",
  "okay, starting on {destination}.",
  "let me see what's out there for {destination}.",
];

const ITERATION_BY_DEPTH: readonly Pool[] = [
  ["asking around on reddit. people are loud here, takes a sec to find the quiet ones."],
  ["going one more round — there's a name that keeps coming up i want to verify."],
  ["okay, deeper pass. checking the ones with mixed signal."],
  ["last pass — pulling the loose threads together."],
];

const PRODUCER_GENERIC: Pool = [
  "pulled {n} candidates. reading through.",
  "{n} names so far. saving the ones that show up twice.",
  "now checking the next source. cross-referencing.",
  "confirming addresses + hours with google places.",
];

const JOINER: Pool = [
  "some of these come up twice — saving the doubles. {n_out} confirmed.",
  "{n_out} survived the cross-check. the rest were one-off mentions.",
  "two of them disagree — interesting. going one more round to figure out which side is right.",
];

const CONTROLLER_CONTINUE: Pool = [
  "i want to know more before i call it. another pass.",
  "not enough quiet picks yet — let me look one more time.",
];
const CONTROLLER_STOP: Pool = [
  "tying it all together now.",
  "that's about as far as i should push it — composing what i have.",
];

// kept as dead code for forward-compat — backend doesn't emit cycle_complete yet
// (see PRD §10 open question 1).
export const CYCLE_COMPLETE: Pool = [
  "done. let me lay it out for you.",
  "okay, that's everything. writing it up.",
];

const TRIP_COMPLETE_OK: Pool = ["done — pinned at the top.", "all in. check the cards on the left."];

const ABORTED: Record<string, Pool> = {
  maestro: ["hit a wall — couldn't get through to my notes app. give me a sec and try again?"],
  empty: [
    "couldn't find anything good there. either too quiet a corner, or i need a different angle. want to try again with more detail?",
  ],
  validation: ["something looked off in what i pulled — not going to write it up half-baked. one more try?"],
  unknown: ["something snapped mid-thought. not your fault. try again?"],
};

export const HEARTBEAT: Pool = [
  "still reading…",
  "…hang on, this thread is dense.",
  "give me a moment.",
];

function pick(pool: Pool, index: number): string {
  if (pool.length === 0) return "";
  return pool[index % pool.length] ?? "";
}

function substitute(line: string, replacements: Record<string, string | number | undefined>): string {
  return line.replace(/\{(\w+)\}/g, (_, key) => {
    const v = replacements[key];
    if (v === undefined || v === null) return "";
    return String(v);
  });
}

function classifyAbort(reason: string): keyof typeof ABORTED {
  const r = reason.toLowerCase();
  if (r.includes("maestro") || r.includes("llm") || r.includes("provider")) return "maestro";
  if (r.includes("empty") || r.includes("no candidate") || r.includes("candidates")) return "empty";
  if (r.includes("validation") || r.includes("schema") || r.includes("parse")) return "validation";
  return "unknown";
}

export interface VoiceLine {
  line: string;
  annot?: string;
}

/**
 * Map an SSE event to a human-voice line. `index` is the per-event-name
 * occurrence count in the current cycle (used for round-robin so the
 * user never sees the same sentence twice).
 *
 * `context.destination` may be supplied so {destination} expands. We
 * pull n/n_in/n_out straight from event.data when present.
 */
export function voiceFor(
  event: TripEvent,
  index: number,
  context: { destination?: string } = {},
): VoiceLine {
  switch (event.name) {
    case "started":
      return { line: substitute(pick(STARTED, index), { destination: context.destination }) };

    case "iteration_start": {
      const pool = ITERATION_BY_DEPTH[Math.min(event.depth, ITERATION_BY_DEPTH.length - 1)] ?? ITERATION_BY_DEPTH[0];
      return { line: pick(pool ?? [], index) };
    }

    case "producer": {
      const line = substitute(pick(PRODUCER_GENERIC, index), {
        n: event.data.n_candidates,
      });
      return { line };
    }

    case "joiner": {
      const line = substitute(pick(JOINER, index), {
        n_in: event.data.n_in,
        n_out: event.data.n_out,
      });
      return { line };
    }

    case "controller": {
      const pool = event.data.should_continue ? CONTROLLER_CONTINUE : CONTROLLER_STOP;
      return { line: pick(pool, index) };
    }

    case "cycle_aborted": {
      const bucket = classifyAbort(event.data.reason);
      return { line: pick(ABORTED[bucket] ?? ABORTED.unknown ?? [], index) };
    }

    case "trip_complete": {
      if (event.status === "aborted") {
        return { line: pick(ABORTED.unknown ?? [], index) };
      }
      return { line: pick(TRIP_COMPLETE_OK, index) };
    }

    case "refine_started": {
      // Batch-2u: surface the user's tweak so the field log makes the
      // context shift obvious. Hint is verbatim so we don't bother
      // rotating through a pool — there's only one for this cycle.
      return { line: "tweaking — pulling the previous reading + your hint." };
    }
  }
}

export function heartbeatLine(index: number): string {
  return pick(HEARTBEAT, index);
}
