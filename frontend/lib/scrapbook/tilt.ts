export function tiltFor(seed: string): number {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  const normalized = ((hash >>> 0) % 1000) / 1000;
  return -2.5 + normalized * 5;
}

export function tiltStyle(seed: string): { "--tilt": string } {
  return { "--tilt": `${tiltFor(seed).toFixed(3)}deg` };
}
