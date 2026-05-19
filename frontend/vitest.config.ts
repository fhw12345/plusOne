import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, configDefaults } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    // Keep vitest's built-in excludes (node_modules, dist, .idea, .git, .cache),
    // and additionally exclude Next.js build output and Playwright territory.
    exclude: [
      ...configDefaults.exclude,
      ".next/**",
      "e2e/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
});
