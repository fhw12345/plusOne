type EvidenceSource = "reddit" | "xiaohongshu" | "foursquare" | string;

export interface EvidenceLike {
  source?: EvidenceSource;
  url?: string;
  snippet?: string;
}

export interface EvidenceLink {
  href: string;
  label: string;
  host: string;
  title?: string;
}

const SOURCE_LABEL: Record<string, string> = {
  reddit: "reddit",
  xiaohongshu: "xhs",
  foursquare: "place data",
};

export function sourceLabel(source: string | undefined): string {
  if (!source) return "source";
  return SOURCE_LABEL[source] ?? source;
}

export function shortHost(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url.slice(0, 40);
  }
}

export function evidenceLink(ev: EvidenceLike, candidateName?: string): EvidenceLink | null {
  const source = ev.source;
  const url = ev.url?.trim();
  if (!url) return null;

  if (source === "xiaohongshu" && shouldUseXhsSearchLink(url)) {
    const href = buildXhsSearchUrl(candidateName, ev.snippet);
    return {
      href,
      label: "xhs search",
      host: shortHost(href),
      title: "Open a public search for this XHS source.",
    };
  }

  const label = sourceLabel(source);
  const host = shortHost(url);
  return {
    href: url,
    label: host ? `${label} - ${host}` : label,
    host,
  };
}

function shouldUseXhsSearchLink(url: string): boolean {
  try {
    const parsed = new URL(url);
    if (!parsed.hostname.includes("xiaohongshu.com")) return false;
    return !parsed.searchParams.has("xsec_token");
  } catch {
    return true;
  }
}

function buildXhsSearchUrl(candidateName: string | undefined, snippet: string | undefined): string {
  const terms = compactTerms([candidateName, snippet]).slice(0, 120);
  const query = ["site:xiaohongshu.com/explore", terms].filter(Boolean).join(" ");
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
}

function compactTerms(values: Array<string | undefined>): string {
  return values
    .flatMap((value) => (value ?? "").split(/\s+/))
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" ");
}
