import { createServer } from "node:http";

const PORT = Number(process.env.FAKE_MAESTRO_PORT ?? "24333");
const FIXTURE_IMAGE_URL =
  "data:image/gif;base64,R0lGODlhAQABAPAAAMzMzP///yH5BAAAAAAALAAAAAABAAEAAAICRAEAOw==";

const candidates = [
  {
    name: "Menya Itto",
    area: "Shinkoiwa",
    style: "tsukemen ramen",
    rationale: "local-favorite ramen counter with stronger source signal than the obvious chains.",
  },
  {
    name: "Ichiran Shibuya",
    area: "Shibuya",
    style: "tonkotsu chain",
    rationale: "useful tourist-trap control: popular and convenient, but heavily chain-coded.",
  },
  {
    name: "Tsuta",
    area: "Yoyogi-Uehara",
    style: "shoyu ramen",
    rationale: "well-known but still a serious bowl, good for a neutral comparison card.",
  },
  {
    name: "Afuri Harajuku",
    area: "Harajuku",
    style: "yuzu shio ramen",
    rationale: "popular with mixed local and visitor signal, worth checking rather than assuming.",
  },
  {
    name: "Nakiryu",
    area: "Otsuka",
    style: "tantanmen ramen",
    rationale: "small destination ramen stop with enough quality signal to round out the route.",
  },
];

function jsonResponse(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function anthropicMessage(text) {
  return {
    id: `msg_fake_${Date.now()}`,
    type: "message",
    role: "assistant",
    model: "fake-maestro-ci",
    content: [{ type: "text", text }],
    stop_reason: "end_turn",
    stop_sequence: null,
    usage: { input_tokens: 100, output_tokens: 50 },
  };
}

function routeResponse(body) {
  const system = String(body.system ?? "").toLowerCase();
  const model = String(body.model ?? "").toLowerCase();

  if (system.includes("clarifier")) return JSON.stringify({ questions: [] });
  if (system.includes("producer agent")) return JSON.stringify({ candidates });
  if (system.includes("joiner agent")) return JSON.stringify(joinerPayload());
  if (system.includes("itinerary scheduler")) return JSON.stringify(itineraryPayload(body));
  if (system.includes("controller agent") || model.includes("haiku")) {
    return JSON.stringify({
      should_continue: false,
      reasoning: "fixture run has enough usable coverage",
      summary: "tokyo ramen source sweep complete",
    });
  }
  return "fixture translation unavailable";
}

function joinerPayload() {
  return {
    tl_dr:
      "tokyo ramen still rewards side streets over the obvious line. use the chains as context, then spend the real meals on counters with local wait-and-return signal.",
    items: [
      item("Menya Itto", "Shinkoiwa", "tsukemen ramen", "local_gem", 0.86, [
        evidence(
          "reddit",
          "https://reddit.com/r/ramen/comments/post_1",
          "Menya Itto in Shinkoiwa is the real deal, a local favorite and worth the wait.",
          0.8,
        ),
        evidence(
          "xiaohongshu",
          "https://www.xiaohongshu.com/explore/xhs_1",
          "local regulars line up here; very few tourists; weekday lunch is calmer.",
          0.8,
        ),
        evidence(
          "foursquare",
          "https://foursquare.com/v/ChIJplaceItto",
          "Menya Itto, Shinkoiwa, Tokyo.",
          null,
        ),
      ]),
      item("Ichiran Shibuya", "Shibuya", "tonkotsu chain", "tourist_trap", 0.78, [
        evidence(
          "reddit",
          "https://reddit.com/r/JapanTravel/comments/post_2",
          "Ichiran is a chain; fine, but an hour wait for airport tonkotsu energy.",
          -0.6,
        ),
        evidence(
          "xiaohongshu",
          "https://www.xiaohongshu.com/explore/xhs_2",
          "chain shop; tourist queue and photos are fine, but it does not represent Tokyo ramen.",
          -0.7,
        ),
      ]),
      item("Tsuta", "Yoyogi-Uehara", "shoyu ramen", "neutral", 0.68, [
        evidence(
          "reddit",
          "https://reddit.com/r/JapanTravel/comments/post_2",
          "Tsuta is worth a ticket if the route already takes you nearby.",
          0.2,
        ),
      ]),
      item("Afuri Harajuku", "Harajuku", "yuzu shio ramen", "neutral", 0.62, [
        evidence(
          "reddit",
          "https://reddit.com/r/JapanTravel/comments/post_2",
          "Afuri is a reasonable yuzu shio option, more obvious than hidden.",
          0.2,
        ),
      ]),
      item("Nakiryu", "Otsuka", "tantanmen ramen", "local_gem", 0.72, [
        evidence(
          "foursquare",
          "https://foursquare.com/v/ChIJplaceNakiryu",
          "Nakiryu, Otsuka, Tokyo ramen counter.",
          null,
        ),
      ]),
    ],
  };
}

function item(name, area, style, classification, confidence, evidenceRows) {
  const evidenceJson = JSON.stringify(evidenceRows);
  const classificationEn = evidenceJson.includes("reddit") ? classification : null;
  const classificationZh = evidenceJson.includes("xiaohongshu") ? classification : null;
  return {
    candidate: {
      name,
      area,
      style,
      rationale: `${name} is part of the deterministic CI ramen fixture set.`,
    },
    classification,
    classification_en: classificationEn,
    classification_zh: classificationZh,
    confidence,
    match_scores: null,
    evidence: evidenceRows,
    image_url: imageFor(name),
    image_source: "fixture",
    summary: `${name} reads as ${classification.replace("_", " ")} in the fixture evidence.`,
    long_description:
      "Small, source-backed card from the CI fixture run. Enough signal to render the itinerary surface without calling an external LLM gateway.",
  };
}

function evidence(source, url, snippet, sentiment) {
  return { source, url, snippet, sentiment };
}

function imageFor(name) {
  return `${FIXTURE_IMAGE_URL}#${encodeURIComponent(name)}`;
}

function itineraryPayload(body) {
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const content = messages
    .map((message) => (typeof message?.content === "string" ? message.content : ""))
    .join("\n");
  let parsedItems = [];
  try {
    const parsed = JSON.parse(content);
    parsedItems = Array.isArray(parsed) ? parsed : [];
  } catch {
    parsedItems = [];
  }
  const indices =
    parsedItems.length > 0
      ? parsedItems
          .map((item) => Number(item?.index))
          .filter((index) => Number.isInteger(index) && index >= 0)
      : Array.from(content.matchAll(/"index"\s*:\s*(\d+)/g)).map((match) => Number(match[1]));
  const unique = Array.from(new Set(indices)).slice(0, 9);
  const slots = unique.map((index, idx) => ({
    period: idx % 3 === 0 ? "morning" : idx % 3 === 1 ? "afternoon" : "evening",
    item_index: index,
    note: idx === 0 ? "start before the queue" : null,
  }));
  return {
    days: [
      { day_index: 1, date: null, theme: "counter ramen day", slots: slots.slice(0, 2) },
      { day_index: 2, date: null, theme: "shibuya context", slots: slots.slice(2, 4) },
      { day_index: 3, date: null, theme: "last bowls", slots: slots.slice(4) },
    ],
  };
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"));
      } catch {
        resolve({});
      }
    });
  });
}

const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    jsonResponse(res, 200, { status: "ok" });
    return;
  }
  if (req.method !== "POST" || !req.url?.endsWith("/messages")) {
    jsonResponse(res, 404, { error: "not_found" });
    return;
  }
  const body = await readBody(req);
  jsonResponse(res, 200, anthropicMessage(routeResponse(body)));
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`fake maestro listening on http://127.0.0.1:${PORT}\n`);
});

process.on("SIGTERM", () => server.close(() => process.exit(0)));
process.on("SIGINT", () => server.close(() => process.exit(0)));
