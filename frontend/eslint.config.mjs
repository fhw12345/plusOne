import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

const config = [
  {
    ignores: ["public/sw.js", "public/workbox-*.js", "public/worker-*.js"],
  },
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/consistent-type-imports": "warn",
      "react/jsx-curly-brace-presence": ["warn", "never"],
    },
  },
];

export default config;
