/**
 * One-time dataset builder for the destination combobox.
 *
 * Preferred path (when network is available, per PRD §4):
 *   1. Download SimpleMaps World Cities Basic CSV → scripts/data/simplemaps-worldcities-basic.csv
 *   2. Run `pnpm tsx scripts/build-cities.ts`
 *   3. Output → public/data/cities-15k.json
 *
 * This script reads a CSV with columns: city,city_ascii,lat,lng,country,iso2,iso3,admin_name,capital,population,id
 * filters to population >= 15000, dedups by (name,country), sorts by population desc,
 * and writes a {n,c,p}[] array.
 *
 * It is NOT run by CI. The CSV at scripts/data/*.csv is gitignored.
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

type City = { n: string; c: string; p: number };

const __dirname = dirname(fileURLToPath(import.meta.url));
const CSV_PATH = resolve(__dirname, "data", "simplemaps-worldcities-basic.csv");
const OUT_PATH = resolve(__dirname, "..", "public", "data", "cities-15k.json");
const MIN_POP = 15_000;

function parseCsv(text: string): Record<string, string>[] {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length === 0) return [];
  const headerLine = lines[0]!;
  const header = splitCsvLine(headerLine);
  return lines.slice(1).map((line) => {
    const cells = splitCsvLine(line);
    const row: Record<string, string> = {};
    for (let i = 0; i < header.length; i++) {
      const key = header[i];
      if (key !== undefined) row[key] = cells[i] ?? "";
    }
    return row;
  });
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuote = !inQuote;
      }
    } else if (ch === "," && !inQuote) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function main(): void {
  if (!existsSync(CSV_PATH)) {
    console.error(`[build-cities] CSV not found at ${CSV_PATH}`);
    console.error(`[build-cities] See lib/cities/README.md for download instructions.`);
    process.exit(1);
  }
  const csv = readFileSync(CSV_PATH, "utf8");
  const rows = parseCsv(csv);
  const seen = new Set<string>();
  const cities: City[] = [];
  for (const row of rows) {
    const name = (row["city"] || row["city_ascii"] || "").trim();
    const country = (row["country"] || "").trim();
    const pop = Number(row["population"] || 0);
    if (!name || !country) continue;
    if (!Number.isFinite(pop) || pop < MIN_POP) continue;
    const key = `${name.toLowerCase()}|${country.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    cities.push({ n: name, c: country, p: pop });
  }
  cities.sort((a, b) => b.p - a.p);
  writeFileSync(OUT_PATH, JSON.stringify(cities));
  console.log(
    `[build-cities] wrote ${cities.length} cities to ${OUT_PATH} (uncompressed ${(JSON.stringify(cities).length / 1024).toFixed(1)} KB)`,
  );
}

main();
