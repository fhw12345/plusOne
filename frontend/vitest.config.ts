import { defineConfig, configDefaults } from "vitest/config";

export default defineConfig({
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
