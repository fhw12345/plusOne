export function resolveMediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (!url.startsWith("/media/")) return url;
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return `${base}${url}`;
}
