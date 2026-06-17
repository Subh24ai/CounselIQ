import { resolve } from "path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // Match Next.js: use the automatic JSX runtime so test files don't need to
  // import React explicitly.
  esbuild: { jsx: "automatic", jsxImportSource: "react" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["./src/test-setup.ts"],
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
